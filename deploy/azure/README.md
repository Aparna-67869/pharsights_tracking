# Azure Deployment

Two supported topologies. Pick one; both consume the same container images.

| Topology | When | Entry point |
| --- | --- | --- |
| **Container Apps** (recommended default) | Serverless, scale-to-demand, least ops | `deploy.sh` + `main.bicep` |
| **AKS** | Existing cluster, need full Kubernetes control | `../k8s/*.yaml` |

## Container Apps — what gets created

`main.bicep` provisions one resource group containing:

- **Azure Container Apps** — `*-api` (external ingress, 3–12 replicas, HTTP
  concurrency autoscale) and `*-web` (2–8 replicas).
- **Azure Database for PostgreSQL Flexible Server 16** — zone-redundant HA in
  prod, 35-day geo-redundant backups, and the `VECTOR`, `PG_TRGM`, `UUID-OSSP`
  extensions allow-listed. `CREATE EXTENSION vector` then works per database,
  which is what `scripts/bootstrap.py` runs.
- **Azure Cache for Redis** — Premium with TLS 1.2 and `allkeys-lru`.
- **Azure Service Bus** — topics `source.changed`, `change.detected`,
  `alert.created`, mirroring the local Kafka topics.
- **Storage Account** — `pharma-artifacts` container for raw FDA/USPTO files,
  retained for audit and replay. Shared-key access is disabled; the app uses its
  managed identity.
- **Key Vault** — RBAC-authorised, soft-delete and purge protection on. The only
  place a credential lives.
- **Log Analytics + Application Insights** — 90-day retention in prod.
- **Metric alert** — API availability below threshold.

Secrets reach the containers as **Key Vault references resolved by a user-assigned
managed identity**, never as plain environment values. The template declares
`apiIdentity` / `frontendIdentity` up front so the container app definitions can
reference their principal IDs without the self-reference Bicep forbids.

## Deploy

```bash
export PG_ADMIN_PASSWORD="$(az keyvault secret show --vault-name <kv> --name pg-admin-password --query value -o tsv)"
export AZURE_OPENAI_API_KEY="..."
./deploy/azure/deploy.sh rg-pharma-intel prod
```

The script is idempotent and does five things: create the resource group, deploy
infrastructure, write the Key Vault secrets, build and push both images tagged
with the current git SHA, then re-deploy to roll the apps onto that tag.

`prod.bicepparam` reads the Postgres password from `PG_ADMIN_PASSWORD` via
`readEnvironmentVariable`, so it is never written to disk or committed.

## Post-deploy verification

```bash
API=$(az containerapp show -n pharma-intel-api -g rg-pharma-intel --query properties.configuration.ingress.fqdn -o tsv)
curl -fsS "https://$API/health"
curl -fsS "https://$API/api/v1/dashboard/kpis"
```

Then sign in to the frontend as `admin@pharma-intel.local` (seeded by
`scripts/bootstrap`) and confirm the dashboard renders live KPIs.

## Configuration knobs

| Parameter | Default | Purpose |
| --- | --- | --- |
| `environment` | `prod` | Sizing and retention profile |
| `apiMinReplicas` / `apiMaxReplicas` | 3 / 12 | API autoscale bounds |
| `customDomain` | `''` | Frontend custom domain (needs a bound certificate) |
| `alertActionGroupId` | `''` | Paging target for the availability alert |
| `imageTag` | `latest` | Image tag to deploy |

## Cost and scaling notes

- Container Apps scales to zero only if `apiMinReplicas` is set to 0; the default
  keeps 3 warm to protect the 99.9% uptime objective.
- Postgres and Redis are the fixed costs. In non-prod, `environment=dev` drops
  Postgres to Burstable-class storage and Redis to Basic, and disables HA.
- Service Bus Premium is required for the topic feature set used here; the
  Standard tier in non-prod is sufficient for smoke testing.
