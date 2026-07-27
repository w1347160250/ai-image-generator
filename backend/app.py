import base64
import io
import os
import logging
import re
import uuid
import time
import threading
from datetime import datetime, timedelta
import requests
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from openai import OpenAI
from azure.storage.blob import BlobServiceClient, ContentSettings, generate_blob_sas, BlobSasPermissions
from openai import BadRequestError, RateLimitError
from PIL import Image

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-image-2").strip()
API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
SESSION_SECRET = os.environ.get("SESSION_SECRET", "").strip()
AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "").strip()
AZURE_STORAGE_CONTAINER = os.environ.get("AZURE_STORAGE_CONTAINER", "").strip()
AZURE_STORAGE_CONTAINER_GENERATED = os.environ.get(
    "AZURE_STORAGE_CONTAINER_GENERATED",
    AZURE_STORAGE_CONTAINER,
).strip()
AZURE_STORAGE_CONTAINER_REFERENCE = os.environ.get(
    "AZURE_STORAGE_CONTAINER_REFERENCE",
    AZURE_STORAGE_CONTAINER,
).strip()

logger.info("Starting Flask app...")
logger.info(f"Using endpoint: {ENDPOINT}")
logger.info(f"Using deployment: {DEPLOYMENT}")

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)

# 口令配置（可用环境变量管理）
ACCESS_CODE = os.environ.get("ACCESS_CODE", "ai2026")

missing_settings = []
if not ENDPOINT:
    missing_settings.append("AZURE_OPENAI_ENDPOINT")
if not API_KEY:
    missing_settings.append("AZURE_OPENAI_API_KEY")
if not SESSION_SECRET:
    missing_settings.append("SESSION_SECRET")

if missing_settings:
    raise RuntimeError(
        f"请设置环境变量: {', '.join(missing_settings)}"
    )

app.secret_key = SESSION_SECRET

client = OpenAI(
    base_url=ENDPOINT,
    api_key=API_KEY,
    timeout=300.0,
    max_retries=2,
)

MAX_UPLOAD_IMAGES = 8
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def is_request_authorized(getf) -> bool:
    """允许 AAD 登录态或现有访问口令中的任意一种鉴权方式。"""
    if session.get("aad_user"):
        return True

    access_code = (getf("access_code", "") or "").strip()
    return bool(access_code) and access_code == ACCESS_CODE


def _extract_from_connection_string(connection_string: str):
    parts = {}
    for item in connection_string.split(";"):
        if "=" in item:
            k, v = item.split("=", 1)
            parts[k] = v
    return parts


def _extract_image_bytes(result):
    if not getattr(result, "data", None):
        raise RuntimeError("模型返回为空")
    first = result.data[0]

    b64_data = getattr(first, "b64_json", None)
    if b64_data:
        return base64.b64decode(b64_data)

    image_url = getattr(first, "url", None)
    if image_url:
        resp = requests.get(image_url, timeout=60)
        if not resp.ok:
            raise RuntimeError(f"下载模型图片失败: status={resp.status_code}")
        return resp.content

    raise RuntimeError("模型未返回 b64_json 或 url")


def _build_prompt_slug(prompt: str, fallback: str = "image") -> str:
    normalized = (prompt or "").strip().lower()
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"[^0-9a-z\u4e00-\u9fff_-]", "", normalized)
    normalized = normalized.strip("-_")
    return (normalized[:24] or fallback)


def _build_blob_filename(prompt: str, prefix: str, index: int | None = None) -> str:
    prompt_slug = _build_prompt_slug(prompt, fallback=prefix)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    short_id = uuid.uuid4().hex[:8]
    index_part = f"-{index}" if index is not None else ""
    return f"{prefix}-{prompt_slug}{index_part}-{timestamp}-{short_id}.png"


def _upload_to_blob(image_bytes: bytes, prompt: str):
    if not AZURE_STORAGE_CONNECTION_STRING or not AZURE_STORAGE_CONTAINER_GENERATED:
        raise RuntimeError(
            "请配置 AZURE_STORAGE_CONNECTION_STRING 和 AZURE_STORAGE_CONTAINER_GENERATED"
        )

    blob_service = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service.get_container_client(AZURE_STORAGE_CONTAINER_GENERATED)
    if not container_client.exists():
        container_client.create_container()

    blob_filename = _build_blob_filename(prompt, prefix="gen")
    blob_name = f"generated/{datetime.utcnow().strftime('%Y%m%d')}/{blob_filename}"
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(
        image_bytes,
        overwrite=True,
        content_settings=ContentSettings(content_type="image/png"),
    )

    account_info = _extract_from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    account_name = account_info.get("AccountName")
    account_key = account_info.get("AccountKey")

    if account_name and account_key:
        sas = generate_blob_sas(
            account_name=account_name,
            container_name=AZURE_STORAGE_CONTAINER_GENERATED,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(days=30),
        )
        return f"{blob_client.url}?{sas}"

    return blob_client.url


def _upload_reference_to_blob(image_bytes: bytes, prompt: str, index: int):
    if not AZURE_STORAGE_CONNECTION_STRING or not AZURE_STORAGE_CONTAINER_REFERENCE:
        raise RuntimeError(
            "请配置 AZURE_STORAGE_CONNECTION_STRING 和 AZURE_STORAGE_CONTAINER_REFERENCE"
        )

    blob_service = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service.get_container_client(AZURE_STORAGE_CONTAINER_REFERENCE)
    if not container_client.exists():
        container_client.create_container()

    blob_filename = _build_blob_filename(prompt, prefix="ref", index=index)
    blob_name = f"reference/{datetime.utcnow().strftime('%Y%m%d')}/{blob_filename}"
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(
        image_bytes,
        overwrite=True,
        content_settings=ContentSettings(content_type="image/png"),
    )

    account_info = _extract_from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    account_name = account_info.get("AccountName")
    account_key = account_info.get("AccountKey")

    if account_name and account_key:
        sas = generate_blob_sas(
            account_name=account_name,
            container_name=AZURE_STORAGE_CONTAINER_REFERENCE,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=2),
        )
        return f"{blob_client.url}?{sas}"

    return blob_client.url


def _get_azure_resource_endpoint(raw_endpoint: str) -> str:
    ep = raw_endpoint.strip().rstrip("/")
    if ep.endswith("/openai/v1"):
        return ep[: -len("/openai/v1")]
    return ep


def _wrap_b64_result(b64_value: str):
    class Dummy:
        pass

    dummy = Dummy()
    dummy.data = [type("Obj", (), {"b64_json": b64_value})()]
    return dummy


def _normalize_to_png_bytes(image_bytes: bytes) -> bytes:
    """Normalize uploaded images to RGB PNG to avoid mode/format incompatibility."""
    if not image_bytes:
        raise ValueError("上传图片为空")

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            converted = img.convert("RGB")
            output = io.BytesIO()
            converted.save(output, format="PNG")
            return output.getvalue()
    except Exception as exc:
        raise ValueError(f"图片解析失败，请上传有效图片文件: {exc}") from exc


def _build_image_files_for_edit(image_bytes_list):
    image_files = []
    for index, image_bytes in enumerate(image_bytes_list, start=1):
        image_file = io.BytesIO(image_bytes)
        image_file.name = f"source_image_{index}.png"
        image_files.append(image_file)
    return image_files


def _format_bad_request_error(err: BadRequestError) -> str:
    body = getattr(err, "body", None)
    message = getattr(err, "message", None) or str(err)
    code = None
    request_id = None

    if isinstance(body, dict):
        error = body.get("error") or {}
        code = error.get("code")
        message = error.get("message") or message

    response = getattr(err, "response", None)
    if response is not None:
        request_id = response.headers.get("x-request-id") or response.headers.get("apim-request-id")

    lowered = (message or "").lower()
    if code == "moderation_blocked" or "rejected by the safety system" in lowered:
        suffix = f"（request_id: {request_id}）" if request_id else ""
        return (
            "请求被安全系统拦截，请调整提示词或更换参考图后重试。"
            "建议避免涉及敏感人物改造、未成年人、暴力、成人化等高风险描述。"
            f"{suffix}"
        )

    return f"图片处理失败: {message}"


def _generate_with_uploaded_images(prompt, size, quality, image_bytes_list):
    if not image_bytes_list:
        try:
            return client.images.generate(
                model=DEPLOYMENT,
                prompt=prompt,
                n=1,
                size=size,
                quality=quality,
            )
        except BadRequestError as err:
            logger.error(f"images.generate BadRequest: {err}")
            raise RuntimeError(_format_bad_request_error(err)) from err

    retries = 3
    delay_seconds = 2
    last_error = None
    for attempt in range(1, retries + 1):
        image_files = _build_image_files_for_edit(image_bytes_list)
        try:
            # Single image: pass file object directly; multiple: pass list
            image_arg = image_files[0] if len(image_files) == 1 else image_files
            return client.images.edit(
                model=DEPLOYMENT,
                image=image_arg,
                prompt=prompt,
                n=1,
                size=size,
            )
        except RateLimitError as err:
            last_error = err
            if attempt == retries:
                raise RuntimeError("服务当前较忙，请稍后重试。") from err
            time.sleep(delay_seconds * attempt)
        except BadRequestError as err:
            logger.error(f"images.edit BadRequest: {err}")
            raise RuntimeError(_format_bad_request_error(err)) from err
        finally:
            for image_file in image_files:
                image_file.close()

    raise RuntimeError(f"图片生成失败: {last_error}")


def _generate_with_optional_reference(prompt, size, quality, reference_bytes, reference_url=None):
    if not reference_bytes:
        return client.images.generate(
            model=DEPLOYMENT,
            prompt=prompt,
            n=1,
            size=size,
            quality=quality,
        )

    # 先尝试 URL 参考图生图（适配 image-2 URL 参考流程）。
    if reference_url:
        resource_endpoint = _get_azure_resource_endpoint(ENDPOINT)
        headers = {
            "api-key": API_KEY,
            "Content-Type": "application/json",
        }
        api_versions = ["2025-04-01-preview", "2024-02-01"]
        url_attempt_errors = []
        payload_candidates = [
            {
                "prompt": prompt,
                "size": size,
                "quality": quality,
                "n": 1,
                "image_url": reference_url,
            },
            {
                "prompt": prompt,
                "size": size,
                "quality": quality,
                "n": 1,
                "image": reference_url,
            },
        ]
        for api_version in api_versions:
            gen_url = (
                f"{resource_endpoint}/openai/deployments/{DEPLOYMENT}/images/generations"
                f"?api-version={api_version}"
            )
            for payload in payload_candidates:
                resp = requests.post(gen_url, headers=headers, json=payload, timeout=60)
                if resp.ok:
                    body = resp.json()
                    if body.get("data"):
                        if body["data"][0].get("b64_json"):
                            return _wrap_b64_result(body["data"][0]["b64_json"])
                        if body["data"][0].get("url"):
                            image_resp = requests.get(body["data"][0]["url"], timeout=60)
                            if image_resp.ok:
                                return _wrap_b64_result(base64.b64encode(image_resp.content).decode("utf-8"))
                else:
                    attempt_error = {
                        "api_version": api_version,
                        "payload_keys": list(payload.keys()),
                        "status": resp.status_code,
                        "response": resp.text,
                    }
                    url_attempt_errors.append(attempt_error)
                    logger.warning(
                        "URL-based generation attempt failed. "
                        f"deployment={DEPLOYMENT}, attempt={attempt_error}"
                    )
        if url_attempt_errors:
            logger.warning(
                "All URL-based attempts failed; switching to edit fallback. "
                f"deployment={DEPLOYMENT}, reference_url={reference_url}, attempts={url_attempt_errors}"
            )

    # URL 流程失败后，回退到编辑接口（字节流）保证兼容性。
    try:
        return client.images.edit(
            model=DEPLOYMENT,
            image=reference_bytes,
            prompt=prompt,
            n=1,
            size=size,
        )
    except Exception as sdk_error:
        logger.warning(f"images.edit via SDK failed. deployment={DEPLOYMENT}, error={sdk_error}")

    # SDK 失败后，兜底使用 Azure deployment 路径调用 edits 接口。
    resource_endpoint = _get_azure_resource_endpoint(ENDPOINT)
    edit_url = (
        f"{resource_endpoint}/openai/deployments/{DEPLOYMENT}/images/edits"
        f"?api-version=2024-02-01"
    )
    headers = {"api-key": API_KEY}
    files = {
        "image": ("reference.png", reference_bytes, "image/png"),
    }
    data = {
        "prompt": prompt,
        "size": size,
        "n": "1",
    }

    resp = requests.post(edit_url, headers=headers, data=data, files=files, timeout=60)
    if resp.ok:
        body = resp.json()
        if body.get("data") and body["data"][0].get("b64_json"):
            return _wrap_b64_result(body["data"][0]["b64_json"])

    try:
        err_text = resp.json()
    except Exception:
        err_text = resp.text

    logger.error(
        "images.edit fallback failed. "
        f"deployment={DEPLOYMENT}, status={resp.status_code}, error={err_text}"
    )
    raise RuntimeError(
        "参考图生图失败：URL 参考方式和编辑方式均失败。"
        f"（deployment={DEPLOYMENT}, status={resp.status_code}, reference_url={reference_url}）"
    )


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/health", methods=["GET"])
def health_check():
    logger.info("Health check endpoint called.")
    return jsonify({"status": "ok", "deployment": DEPLOYMENT})


# --- Async task infrastructure ---
_tasks = {}  # task_id -> {status, result, error, ...}
_tasks_lock = threading.Lock()


def _run_generate_task(task_id, prompt, size, quality, uploaded_image_bytes_list):
    """Background worker that generates image and updates task store."""
    try:
        result = _generate_with_uploaded_images(prompt, size, quality, uploaded_image_bytes_list)
        image_bytes = _extract_image_bytes(result)
        blob_url = _upload_to_blob(image_bytes, prompt)
        with _tasks_lock:
            _tasks[task_id]["status"] = "completed"
            _tasks[task_id]["image_url"] = blob_url
            _tasks[task_id]["image_name"] = blob_url.split("?")[0].rsplit("/", 1)[-1]
    except Exception as exc:
        logger.error(f"Task {task_id} failed: {exc}")
        with _tasks_lock:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(exc)


@app.route("/api/generate", methods=["POST"])
def generate_image():

    is_multipart = (request.content_type or "").startswith("multipart/form-data")
    if is_multipart:
        getf = lambda k, d=None: (request.form.get(k, d) or d)
    else:
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求格式错误"}), 400
        getf = lambda k, d=None: (data.get(k, d) or d)

    # 校验 AAD 登录态或现有访问口令
    if not is_request_authorized(getf):
        return jsonify({"error": "访问口令错误"}), 403

    prompt = getf("prompt", "").strip()
    size = getf("size", "1024x1024")
    quality = getf("quality", "low")
    if not prompt:
        return jsonify({"error": "请输入图片描述"}), 400

    allowed_sizes = {"1024x1024", "1024x1536", "1536x1024"}
    allowed_qualities = {"low", "medium", "high"}

    if size not in allowed_sizes:
        return jsonify({"error": f"不支持的尺寸，可选: {', '.join(allowed_sizes)}"}), 400
    if quality not in allowed_qualities:
        return jsonify({"error": f"不支持的质量，可选: {', '.join(allowed_qualities)}"}), 400

    uploaded_image_bytes_list = []
    reference_url = None
    reference_urls = []
    if is_multipart:
        files = request.files.getlist("images")
        if not files and "image" in request.files:
            files = [request.files["image"]]

        if len(files) > MAX_UPLOAD_IMAGES:
            return jsonify({"error": f"最多上传 {MAX_UPLOAD_IMAGES} 张参考图"}), 400

        for image_file in files:
            if not image_file or not image_file.filename:
                continue
            if not (image_file.mimetype or "").startswith("image/"):
                return jsonify({"error": "上传文件中包含非图片内容"}), 400
            raw_bytes = image_file.read()
            if not raw_bytes:
                return jsonify({"error": "上传的图片为空"}), 400
            if len(raw_bytes) > MAX_IMAGE_BYTES:
                return jsonify({"error": "单张参考图不能超过 10MB"}), 400

            try:
                normalized = _normalize_to_png_bytes(raw_bytes)
            except ValueError as ve:
                return jsonify({"error": str(ve)}), 400
            uploaded_image_bytes_list.append(normalized)

        for index, img_bytes in enumerate(uploaded_image_bytes_list, start=1):
            ref_url = _upload_reference_to_blob(img_bytes, prompt, index)
            reference_urls.append(ref_url)
        if reference_urls:
            reference_url = reference_urls[0]

    # Create async task and return immediately
    task_id = uuid.uuid4().hex
    with _tasks_lock:
        _tasks[task_id] = {
            "status": "processing",
            "reference_url": reference_url,
            "reference_urls": reference_urls or None,
            "input_image_count": len(uploaded_image_bytes_list),
            "image_url": None,
            "image_name": None,
            "error": None,
        }

    thread = threading.Thread(
        target=_run_generate_task,
        args=(task_id, prompt, size, quality, uploaded_image_bytes_list),
        daemon=True,
    )
    thread.start()

    return jsonify({"task_id": task_id, "status": "processing"}), 202


@app.route("/api/task/<task_id>", methods=["GET"])
def get_task_status(task_id):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify({"task_id": task_id, **task})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
