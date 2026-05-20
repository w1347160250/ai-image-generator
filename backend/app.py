import base64
import io
import os
import logging
import uuid
import time
from datetime import datetime, timedelta
import requests
from flask import Flask, request, jsonify, send_from_directory
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

if missing_settings:
    raise RuntimeError(
        f"请设置环境变量: {', '.join(missing_settings)}"
    )

client = OpenAI(base_url=ENDPOINT, api_key=API_KEY)

MAX_UPLOAD_IMAGES = 8
MAX_IMAGE_BYTES = 10 * 1024 * 1024


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


def _upload_to_blob(image_bytes: bytes):
    if not AZURE_STORAGE_CONNECTION_STRING or not AZURE_STORAGE_CONTAINER_GENERATED:
        raise RuntimeError(
            "请配置 AZURE_STORAGE_CONNECTION_STRING 和 AZURE_STORAGE_CONTAINER_GENERATED"
        )

    blob_service = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service.get_container_client(AZURE_STORAGE_CONTAINER_GENERATED)
    if not container_client.exists():
        container_client.create_container()

    blob_name = f"generated/{datetime.utcnow().strftime('%Y%m%d')}/{uuid.uuid4().hex}.png"
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


def _upload_reference_to_blob(image_bytes: bytes):
    if not AZURE_STORAGE_CONNECTION_STRING or not AZURE_STORAGE_CONTAINER_REFERENCE:
        raise RuntimeError(
            "请配置 AZURE_STORAGE_CONNECTION_STRING 和 AZURE_STORAGE_CONTAINER_REFERENCE"
        )

    blob_service = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service.get_container_client(AZURE_STORAGE_CONTAINER_REFERENCE)
    if not container_client.exists():
        container_client.create_container()

    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    blob_name = f"reference/{datetime.utcnow().strftime('%Y%m%d')}/{ts}-{uuid.uuid4().hex}.png"
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


def _generate_with_uploaded_images(prompt, size, quality, image_bytes_list):
    if not image_bytes_list:
        return client.images.generate(
            model=DEPLOYMENT,
            prompt=prompt,
            n=1,
            size=size,
            quality=quality,
        )

    retries = 3
    delay_seconds = 2
    last_error = None
    for attempt in range(1, retries + 1):
        image_files = _build_image_files_for_edit(image_bytes_list)
        try:
            return client.images.edit(
                model=DEPLOYMENT,
                image=image_files,
                prompt=prompt,
                n=1,
                size=size,
                quality=quality,
            )
        except RateLimitError as err:
            last_error = err
            if attempt == retries:
                raise RuntimeError("服务当前较忙，请稍后重试。") from err
            time.sleep(delay_seconds * attempt)
        except BadRequestError as err:
            raise RuntimeError(
                "上传图片格式或内容不符合要求，请尝试更换图片（建议 JPG/PNG）后重试。"
            ) from err
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

    # 校验口令
    access_code = getf("access_code", "").strip()
    if not access_code or access_code != ACCESS_CODE:
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

        if uploaded_image_bytes_list:
            # Keep one short-lived URL for debugging / traceability on response.
            reference_url = _upload_reference_to_blob(uploaded_image_bytes_list[0])

    try:
        result = _generate_with_uploaded_images(prompt, size, quality, uploaded_image_bytes_list)
        image_bytes = _extract_image_bytes(result)
        blob_url = _upload_to_blob(image_bytes)
        return jsonify(
            {
                "image_url": blob_url,
                "reference_url": reference_url,
                "input_image_count": len(uploaded_image_bytes_list),
            }
        )
    except RuntimeError as re:
        return jsonify({"error": str(re), "reference_url": reference_url}), 400
    except Exception as e:
        return jsonify({"error": f"生成失败: {str(e)}", "reference_url": reference_url}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
