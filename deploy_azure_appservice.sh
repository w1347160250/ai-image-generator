#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   export AZURE_OPENAI_API_KEY="..."
#   ./deploy_azure_appservice.sh
# Optional env vars:
#   RESOURCE_GROUP, LOCATION, APP_NAME, SKU, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-ai-image-generator}"
LOCATION="${LOCATION:-eastasia}"
APP_NAME="${APP_NAME:-ai-image-gen-$RANDOM}"
SKU="${SKU:-B1}"
AZURE_OPENAI_ENDPOINT="${AZURE_OPENAI_ENDPOINT:-https://image-2-test-wu3.openai.azure.com/openai/v1}"
AZURE_OPENAI_DEPLOYMENT="${AZURE_OPENAI_DEPLOYMENT:-gpt-image-2}"

if [[ -z "${AZURE_OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: Please export AZURE_OPENAI_API_KEY before running this script."
  exit 1
fi

echo "[1/5] Creating resource group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output table

echo "[2/5] Creating Linux App Service plan..."
az appservice plan create \
  --name "${APP_NAME}-plan" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --is-linux \
  --sku "$SKU" \
  --output table

echo "[3/5] Creating web app..."
az webapp create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --plan "${APP_NAME}-plan" \
  --runtime "PYTHON|3.11" \
  --output table

echo "[4/5] Configuring startup and app settings..."
az webapp config set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --startup-file "gunicorn --chdir backend --bind=0.0.0.0 --timeout 600 app:app" \
  --output table

az webapp config appsettings set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --settings \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true \
    AZURE_OPENAI_API_KEY="$AZURE_OPENAI_API_KEY" \
    AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
    AZURE_OPENAI_DEPLOYMENT="$AZURE_OPENAI_DEPLOYMENT" \
  --output table

echo "[5/5] Deploying current folder as ZIP..."
# Build zip package for deployment
rm -f deploy.zip
zip -r deploy.zip . -x ".git/*" ".venv/*" "__pycache__/*" "*.pyc" "output.png" "deploy.zip"

az webapp deployment source config-zip \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --src "$(pwd)/deploy.zip" \
  --output table

APP_URL="https://${APP_NAME}.azurewebsites.net"
echo "Deployment done."
echo "Web URL: ${APP_URL}"
echo "Health check: ${APP_URL}/"
