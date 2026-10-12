using '../main.bicep'

// Production parameter set. Secrets are deliberately NOT stored here — supply
// postgresAdminPassword from the pipeline (az deployment group create
// --parameters postgresAdminPassword=... , or a Key Vault reference) so it never
// lands in git.
param environment = 'prod'
param baseName = 'pharma-intel'
param imageTag = 'latest'
param containerRegistryLoginServer = 'pharmaintel.azurecr.io'
param apiMinReplicas = 3
param apiMaxReplicas = 12
param customDomain = ''

// Read from the environment at deploy time so the credential is never committed.
// Set PG_ADMIN_PASSWORD in the pipeline (sourced from Key Vault / pipeline secret).
param postgresAdminPassword = readEnvironmentVariable('PG_ADMIN_PASSWORD')
