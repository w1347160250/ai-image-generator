# Azure Deployment (Frontend Entry + Backend API)

This project can be deployed as a single Azure Web App.
The Flask backend serves both API and frontend static files.

## 1) Prerequisites

- Azure CLI installed
- Logged in with `az login`
- Valid Azure subscription selected with `az account set --subscription "<SUBSCRIPTION_ID_OR_NAME>"`

## 2) Deploy

From project root:

```bash
chmod +x deploy_azure_appservice.sh
export AZURE_OPENAI_API_KEY="<YOUR_AZURE_OPENAI_KEY>"
# Optional overrides:
# export RESOURCE_GROUP="rg-ai-image-generator"
# export LOCATION="eastasia"
# export APP_NAME="ai-image-gen-prod-001"
# export AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com/openai/v1"
# export AZURE_OPENAI_DEPLOYMENT="gpt-image-2"
./deploy_azure_appservice.sh
```

After deployment, open:

- `https://<APP_NAME>.azurewebsites.net/`

## 3) Verify

- Home page loads
- Enter prompt and click generate
- Image appears and can be downloaded

## 4) Update deployment (same app)

Run the script again. It redeploys current code to the same app if `APP_NAME` and `RESOURCE_GROUP` are unchanged.

## 5) Notes

- Keep API key in app settings, not in code.
- For production, consider moving to `S1` or above for better performance.
