import os
import base64
from openai import OpenAI

endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "https://bc-gpt-test.services.ai.azure.com/openai/v1")
deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-image-2")
api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")

client = OpenAI(
    base_url=endpoint,
    api_key=api_key
)

prompt = """Generate a minimalist Microsoft Azure reference architecture diagram (PowerPoint-ready) using ONLY official Azure product icons (Azure Architecture Icons set).
The diagram must look human-designed and corporate, NOT AI-generated poster art.

Style constraints (very important):
- White background, flat vector style, no gradients, no glow, no 3D, no cartoon, no cute illustrations.
- Use consistent icon size, consistent line weight, consistent arrow style.
- Minimal text: only short product names under icons (1 line each). No paragraphs, no long captions, no numbered sections.
- No fancy frames, no heavy containers, no decorative shapes. Use whitespace for grouping.
- Do NOT crop, rotate, flip, or distort any Azure icons.

Layout: horizontal left-to-right flow with simple arrows.

Include ONLY these Azure components (icons + short labels):
Ingress:
- Azure Front Door
- Azure Application Gateway (WAF implied, do not add extra WAF box)

AI Core (center focus, 4 icons in a row or 2x2 grid):
- Azure AI Foundry (Agent Orchestration)
- Azure OpenAI
- Azure AI Speech
- Azure AI Content Safety

Data & Security (below AI Core as a small row):
- Azure Cosmos DB
"""

img = client.images.generate(
    model=deployment_name,
    prompt=prompt,
    n=1,
    size="1024x1024",
    quality="low"
)

image_bytes = base64.b64decode(img.data[0].b64_json)
with open("output.png", "wb") as f:
    f.write(image_bytes)