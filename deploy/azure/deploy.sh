#!/usr/bin/env bash
# End-to-end Azure deployment for the Pharma Intelligence Platform.
#
#   ./deploy/azure/deploy.sh rg-pharma-intel prod
#
# Requires: az CLI (logged in), docker, and the repo root as the working dir.
# Idempotent: re-running redeploys infrastructure and rolls the apps to the new
# image tag.
set -euo pipefail

RESOURCE_GROUP="${1:-rg-pharma-intel}"
ENVIRONMENT="${2:-prod}"
LOCATION="${LOCATION:-eastus}"
BASE_NAME="${BASE_NAME:-pharma-intel}"
REGISTRY="${REGISTRY:-pharmaintel.azurecr.io}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo latest)}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

log "Resource group $RESOURCE_GROUP ($LOCATION)"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# postgresAdminPassword is read from the environment by prod.bicepparam, so it
# must be present here. It never touches the filesystem.
if [[ -z "${PG_ADMIN_PASSWORD:-}" ]]; then
  echo "PG_ADMIN_PASSWORD is not set. Export it (from Key Vault) before deploying." >&2
  exit 1
fi

log "Infrastructure (Bicep)"
DEPLOYMENT_OUTPUT=$(az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --name "${BASE_NAME}-infra-$(date +%Y%m%d%H%M%S)" \
  --template-file "$REPO_ROOT/deploy/azure/main.bicep" \
  --parameters "$REPO_ROOT/deploy/azure/params/${ENVIRONMENT}.bicepparam" \
  --parameters imageTag="$IMAGE_TAG" containerRegistryLoginServer="$REGISTRY" \
  --query properties.outputs --output json)

api_fqdn=$(jq -r '.apiFqdn.value' <<<"$DEPLOYMENT_OUTPUT")
pg_fqdn=$(jq -r '.postgresFqdn.value' <<<"$DEPLOYMENT_OUTPUT")
kv_uri=$(jq -r '.keyVaultUri.value' <<<"$DEPLOYMENT_OUTPUT")
storage_account=$(jq -r '.storageAccountName.value' <<<"$DEPLOYMENT_OUTPUT")
echo "API:        https://$api_fqdn"
echo "Postgres:   $pg_fqdn"
echo "Key Vault:  $kv_uri"

log "Key Vault secrets"
# Container Apps resolve these Key Vault references on every revision start, so
# the secrets must exist before the apps are revised.
set_secret() {
  local name="$1" value="$2"
  az keyvault secret set --vault-name "${kv_uri##*/}" --name "$name" --value "$value" --output none
  echo "  set $name"
}
set_secret database-url "postgresql+psycopg://pharmadmin:${PG_ADMIN_PASSWORD}@${pg_fqdn}:5432/pharma?sslmode=require"
set_secret jwt-secret "${JWT_SECRET:-$(openssl rand -hex 32)}"
set_secret redis-url "${REDIS_URL:-rediss://${BASE_NAME}-redis.redis.cache.windows.net:6380/0}"
set_secret kafka-bootstrap-servers "${KAFKA_BOOTSTRAP_SERVERS:-${BASE_NAME}-sb.servicebus.windows.net:9093}"
set_secret azure-storage-connection-string "$(az storage account show-connection-string --name "$storage_account" --resource-group "$RESOURCE_GROUP" --query connectionString --output tsv)"
set_secret azure-openai-endpoint "${AZURE_OPENAI_ENDPOINT:-https://${BASE_NAME}-aoai.openai.azure.com/}"
set_secret azure-openai-api-key "${AZURE_OPENAI_API_KEY:-}"
set_secret slack-webhook-url "${SLACK_WEBHOOK_URL:-}"
set_secret teams-webhook-url "${TEAMS_WEBHOOK_URL:-}"

log "Build and push images"
az acr login --name "${REGISTRY%%.*}"
docker build -t "$REGISTRY/pharma-backend:$IMAGE_TAG" "$REPO_ROOT/backend"
docker build -t "$REGISTRY/pharma-frontend:$IMAGE_TAG" "$REPO_ROOT/frontend" \
  --build-arg "NEXT_PUBLIC_API_BASE_URL=https://$api_fqdn"
docker push "$REGISTRY/pharma-backend:$IMAGE_TAG"
docker push "$REGISTRY/pharma-frontend:$IMAGE_TAG"

log "Roll apps to $IMAGE_TAG"
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file "$REPO_ROOT/deploy/azure/main.bicep" \
  --parameters "$REPO_ROOT/deploy/azure/params/${ENVIRONMENT}.bicepparam" \
  --parameters imageTag="$IMAGE_TAG" containerRegistryLoginServer="$REGISTRY" \
  --output none

log "Schema bootstrap"
az containerapp exec \
  --name "${BASE_NAME}-api" \
  --resource-group "$RESOURCE_GROUP" \
  --command "python -m scripts.bootstrap" || \
  echo "WARN: could not exec bootstrap; run it manually from a job"

log "Done. API health:"
curl -fsS "https://$api_fqdn/health" && echo
