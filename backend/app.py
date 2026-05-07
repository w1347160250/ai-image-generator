import base64
import os
import logging
import io
import random
import string
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from flask import session, send_file
from itsdangerous import URLSafeTimedSerializer
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-image-2").strip()
API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()

logger.info("Starting Flask app...")
logger.info(f"Using endpoint: {ENDPOINT}")
logger.info(f"Using deployment: {DEPLOYMENT}")

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)

# 配置 session
app.secret_key = os.environ.get("SESSION_SECRET", "change_this_secret")

# 口令配置（可用环境变量管理）
ACCESS_CODE = os.environ.get("ACCESS_CODE", "ai2026")

# 验证码工具
def _generate_captcha_text(length=5):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def _generate_captcha_image(text):
    width, height = 110, 38
    image = Image.new('RGB', (width, height), (255, 255, 255))
    font = ImageFont.load_default()
    draw = ImageDraw.Draw(image)
    for i in range(random.randint(1, 3)):
        draw.line(
            [(random.randint(0, width), random.randint(0, height)),
              (random.randint(0, width), random.randint(0, height))],
            fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)), width=2)
    for i, char in enumerate(text):
        draw.text((10 + i * 18, random.randint(2, 10)), char, font=font, fill=(random.randint(0, 120), random.randint(0, 120), random.randint(0, 120)))
    image = image.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)
    return buf

@app.route("/api/captcha")
def get_captcha():
    text = _generate_captcha_text()
    session['captcha'] = text.lower()
    img = _generate_captcha_image(text)
    return send_file(img, mimetype='image/png')

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


def _generate_with_optional_reference(prompt, size, quality, reference_bytes):
    if not reference_bytes:
        return client.images.generate(
            model=DEPLOYMENT,
            prompt=prompt,
            n=1,
            size=size,
            quality=quality,
        )

    # 参考图模式，直接用 requests 调 REST API
    endpoint_url = ENDPOINT.rstrip("/") + f"/openai/images/generations:submit?api-version=2023-12-01-preview"
    headers = {
        "api-key": API_KEY,
        "Content-Type": "application/json"
    }
    image_b64 = base64.b64encode(reference_bytes).decode("utf-8")
    payload = {
        "model": DEPLOYMENT,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
        "input_image": image_b64
    }
    resp = requests.post(endpoint_url, headers=headers, json=payload)
    if resp.status_code != 200:
        logger.error(f"Azure OpenAI REST API error: {resp.text}")
        raise RuntimeError(f"参考图生图失败: {resp.text}")
    # 兼容异步任务API，需轮询获取结果
    result_url = resp.json().get("resultUrl")
    if not result_url:
        raise RuntimeError("Azure API 未返回 resultUrl")
    # 轮询直到生成完成
    for _ in range(30):
        r = requests.get(result_url, headers=headers)
        if r.status_code == 200:
            result = r.json()
            if result.get("status") == "succeeded":
                class Dummy:
                    pass
                dummy = Dummy()
                dummy.data = [type("Obj", (), {"b64_json": result["data"][0]["b64_json"]})()]
                return dummy
            elif result.get("status") == "failed":
                raise RuntimeError(f"Azure生成失败: {result}")
        import time; time.sleep(2)
    raise RuntimeError("Azure生成超时，请稍后重试")


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

    # 校验验证码
    captcha = getf("captcha", "").strip().lower()
    if not captcha or captcha != session.get('captcha', '').lower():
        session['captcha'] = None
        return jsonify({"error": "验证码错误，请刷新重试"}), 403
    session['captcha'] = None

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
        b64_image = result.data[0].b64_json
        return jsonify({"image": b64_image})
    except RuntimeError as re:
        return jsonify({"error": str(re)}), 400
    except Exception as e:
        return jsonify({"error": f"生成失败: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
