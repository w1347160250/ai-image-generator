import base64
from openai import OpenAI

import os

endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "https://bc-gpt-test.services.ai.azure.com/openai/v1")
deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-image-2")
api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")

client = OpenAI(
    base_url=endpoint,
    api_key=api_key,
    timeout=300.0,      # ✅ 关键：5 分钟超时
    max_retries=2       # ✅ 防止偶发网络抖动
)

with open("reference.png", "rb") as f:
    img = client.images.edit(
        model=deployment_name,
        prompt="给他换身衣服",
        image=f,
        n=1,
        size="1024x1024"
    )

# 保存结果
image_bytes = base64.b64decode(img.data[0].b64_json)
with open("output.png", "wb") as out:
    out.write(image_bytes)

print("✅ output.png 已生成了")
