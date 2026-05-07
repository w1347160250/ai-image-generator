import base64
import os
import logging
import uuid
from datetime import datetime, timedelta
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI
from azure.storage.blob import BlobServiceClient, ContentSettings, generate_blob_sas, BlobSasPermissions

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-image-2").strip()
API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "").strip()
AZURE_STORAGE_CONTAINER = os.environ.get("AZURE_STORAGE_CONTAINER", "").strip()

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
    if not AZURE_STORAGE_CONNECTION_STRING or not AZURE_STORAGE_CONTAINER:
        raise RuntimeError("请配置 AZURE_STORAGE_CONNECTION_STRING 和 AZURE_STORAGE_CONTAINER")

    blob_service = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service.get_container_client(AZURE_STORAGE_CONTAINER)
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
            container_name=AZURE_STORAGE_CONTAINER,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(days=30),
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


def _generate_with_optional_reference(prompt, size, quality, reference_bytes):
    if not reference_bytes:
        return client.images.generate(
            model=DEPLOYMENT,
            prompt=prompt,
            n=1,
            size=size,
            quality=quality,
        )

    # 参考图模式：使用官方 SDK 的 edit 接口，避免手动拼接 Azure REST 路径导致 404。
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
        "参考图生图失败：当前部署可能不支持编辑，或部署名不是图片编辑部署名。"
        f"（deployment={DEPLOYMENT}, status={resp.status_code}）"
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

    reference_bytes = None
    if is_multipart and "image" in request.files:
        image_file = request.files["image"]
        if image_file.filename:
            if not (image_file.mimetype or "").startswith("image/"):
                return jsonify({"error": "参考图必须是图片文件"}), 400
            reference_bytes = image_file.read()
            if not reference_bytes:
                return jsonify({"error": "上传的参考图为空"}), 400
            if len(reference_bytes) > 10 * 1024 * 1024:
                return jsonify({"error": "参考图不能超过 10MB"}), 400

    try:
        result = _generate_with_optional_reference(prompt, size, quality, reference_bytes)
        image_bytes = _extract_image_bytes(result)
        blob_url = _upload_to_blob(image_bytes)
        return jsonify({"image_url": blob_url})
    except RuntimeError as re:
        return jsonify({"error": str(re)}), 400
    except Exception as e:
        return jsonify({"error": f"生成失败: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
