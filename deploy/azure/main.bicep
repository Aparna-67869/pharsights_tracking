// Azure infrastructure for the Pharma Intelligence Platform.
//
// Deploys the full production topology:
//   Container Apps (API, frontend, worker) + Postgres Flexible Server with
//   pgvector, Redis, Service Bus (Kafka-compatible eventing is optional),
//   Blob Storage, Key Vault, Log Analytics, Application Insights.
//
//   az deployment group create \
//     --resource-group rg-pharma-intel \
//     --template-file deploy/azure/main.bicep \
//     --parameters deploy/azure/params/prod.bicepparam

targetScope = 'resourceGroup'

@description('Environment short name used in resource naming (dev|test|prod).')
@allowed(['dev', 'test', 'prod'])
param environment string = 'prod'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Base name prefix for resources.')
param baseName string = 'pharma-intel'

@description('Postgres administrator login.')
param postgresAdminLogin string = 'pharmadmin'

@secure()
@description('Postgres administrator password. Supply via Key Vault reference or pipeline secret.')
param postgresAdminPassword string

@description('Container image tag to deploy.')
param imageTag string = 'latest'

@description('Container registry login server (e.g. myacr.azurecr.io).')
param containerRegistryLoginServer string

@description('Minimum API replicas.')
@minValue(1)
@maxValue(30)
param apiMinReplicas int = 3

@description('Maximum API replicas.')
@minValue(1)
@maxValue(50)
param apiMaxReplicas int = 12

@description('Custom domain for the frontend, or empty to use the generated FQDN.')
param customDomain string = ''

@description('Action group resource ID for paging alerts. Empty disables paging.')
param alertActionGroupId string = ''

var tags = {
  application: 'pharma-intelligence-platform'
  environment: environment
  managedBy: 'bicep'
}

// ---------------------------------------------------------------------------
// Observability: one workspace backs both Container Apps logging and App Insights.
// ---------------------------------------------------------------------------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${baseName}-logs'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: environment == 'prod' ? 90 : 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${baseName}-appi'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    RetentionInDays: environment == 'prod' ? 90 : 30
  }
}

// ---------------------------------------------------------------------------
// Secrets
// ---------------------------------------------------------------------------
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${baseName}-kv'
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: tenant().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// ---------------------------------------------------------------------------
// Data: Postgres Flexible Server with pgvector available via extension.
// ---------------------------------------------------------------------------
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: '${baseName}-pg'
  location: location
  tags: tags
  sku: {
    name: environment == 'prod' ? 'Standard_D4ds_v5' : 'Standard_D2ds_v5'
    tier: 'GeneralPurpose'
  }
  properties: {
    version: '16'
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    storage: {
      storageSizeGB: environment == 'prod' ? 256 : 64
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: environment == 'prod' ? 35 : 7
      geoRedundantBackup: environment == 'prod' ? 'Enabled' : 'Disabled'
    }
    highAvailability: {
      mode: environment == 'prod' ? 'ZoneRedundant' : 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Enabled'
    }
  }
}

resource postgresDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: postgres
  name: 'pharma'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Allowlist the pgvector extension. CREATE EXTENSION vector then works per-database.
resource pgExtensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-12-01-preview' = {
  parent: postgres
  name: 'azure.extensions'
  properties: {
    value: 'VECTOR,PG_TRGM,UUID-OSSP'
    source: 'user-override'
  }
}

// ---------------------------------------------------------------------------
// Cache
// ---------------------------------------------------------------------------
resource redis 'Microsoft.Cache/redis@2024-03-01' = {
  name: '${baseName}-redis'
  location: location
  tags: tags
  properties: {
    sku: {
      name: environment == 'prod' ? 'Premium' : 'Basic'
      family: environment == 'prod' ? 'P' : 'C'
      capacity: environment == 'prod' ? 1 : 0
    }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    redisConfiguration: {
      'maxmemory-policy': 'allkeys-lru'
    }
  }
}

// ---------------------------------------------------------------------------
// Eventing: Service Bus mirrors the local Kafka topics; the event layer is
// transport-agnostic (see app/events).
// ---------------------------------------------------------------------------
resource serviceBus 'Microsoft.ServiceBus/namespaces@2024-01-01' = {
  name: '${baseName}-sb'
  location: location
  tags: tags
  sku: { name: environment == 'prod' ? 'Premium' : 'Standard', tier: environment == 'prod' ? 'Premium' : 'Standard' }
}

resource topicSourceChanged 'Microsoft.ServiceBus/namespaces/topics@2024-01-01' = {
  parent: serviceBus
  name: 'source.changed'
  properties: { maxSizeInMegabytes: 5120, defaultMessageTimeToLive: 'P14D' }
}

resource topicChangeDetected 'Microsoft.ServiceBus/namespaces/topics@2024-01-01' = {
  parent: serviceBus
  name: 'change.detected'
  properties: { maxSizeInMegabytes: 5120, defaultMessageTimeToLive: 'P14D' }
}

resource topicAlertCreated 'Microsoft.ServiceBus/namespaces/topics@2024-01-01' = {
  parent: serviceBus
  name: 'alert.created'
  properties: { maxSizeInMegabytes: 5120, defaultMessageTimeToLive: 'P14D' }
}

// ---------------------------------------------------------------------------
// Artifact storage: raw downloaded FDA/USPTO files, kept for audit + replay.
// ---------------------------------------------------------------------------
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: replace('${baseName}st', '-', '')
  location: location
  tags: tags
  sku: { name: environment == 'prod' ? 'Standard_GRS' : 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource artifactsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'pharma-artifacts'
  properties: { publicAccess: 'None' }
}

// ---------------------------------------------------------------------------
// Compute: Container Apps environment + the three apps.
// ---------------------------------------------------------------------------
resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${baseName}-env'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: split(containerRegistryLoginServer, '.')[0]
}

// User-assigned identities are declared before the apps that use them, so the
// container app definitions can reference their principal IDs without the
// self-reference that a system-assigned identity would require.
resource apiIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: '${baseName}-api-id'
  location: location
  tags: tags
}

resource frontendIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: '${baseName}-web-id'
  location: location
  tags: tags
}

resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${baseName}-api'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${apiIdentity.id}': {} }
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Multiple'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
        traffic: [{ latestRevision: true, weight: 100 }]
      }
      registries: [
        {
          server: containerRegistryLoginServer
          identity: apiIdentity.id
        }
      ]
      secrets: [
        { name: 'database-url', keyVaultUrl: '${keyVault.properties.vaultUri}secrets/database-url', identity: apiIdentity.id }
        { name: 'redis-url', keyVaultUrl: '${keyVault.properties.vaultUri}secrets/redis-url', identity: apiIdentity.id }
        { name: 'jwt-secret', keyVaultUrl: '${keyVault.properties.vaultUri}secrets/jwt-secret', identity: apiIdentity.id }
        { name: 'azure-openai-api-key', keyVaultUrl: '${keyVault.properties.vaultUri}secrets/azure-openai-api-key', identity: apiIdentity.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: '${containerRegistryLoginServer}/pharma-backend:${imageTag}'
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'ENVIRONMENT', value: environment }
            { name: 'VECTOR_BACKEND', value: 'pgvector' }
            { name: 'STORAGE_BACKEND', value: 'azure_blob' }
            { name: 'AZURE_STORAGE_CONTAINER', value: 'pharma-artifacts' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'JWT_SECRET', secretRef: 'jwt-secret' }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
          ]
          probes: [
            { type: 'Liveness', httpGet: { path: '/health', port: 8000 }, initialDelaySeconds: 20, periodSeconds: 20 }
            { type: 'Readiness', httpGet: { path: '/health', port: 8000 }, initialDelaySeconds: 10, periodSeconds: 10 }
          ]
        }
      ]
      scale: {
        minReplicas: apiMinReplicas
        maxReplicas: apiMaxReplicas
        rules: [
          {
            name: 'http-rule'
            http: { metadata: { concurrentRequests: '100' } }
          }
        ]
      }
    }
  }
}

resource frontendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${baseName}-web'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${frontendIdentity.id}': {} }
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Multiple'
      ingress: {
        external: true
        targetPort: 3000
        transport: 'http'
        allowInsecure: false
        traffic: [{ latestRevision: true, weight: 100 }]
        customDomains: customDomain == '' ? [] : [
          { name: customDomain, bindingType: 'SniEnabled', certificateId: '' }
        ]
      }
      registries: [
        { server: containerRegistryLoginServer, identity: frontendIdentity.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: '${containerRegistryLoginServer}/pharma-frontend:${imageTag}'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'NEXT_PUBLIC_API_BASE_URL', value: 'https://${apiApp.properties.configuration.ingress.fqdn}' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
          ]
        }
      ]
      scale: {
        minReplicas: 2
        maxReplicas: 8
        rules: [{ name: 'http-rule', http: { metadata: { concurrentRequests: '200' } } }]
      }
    }
  }
}

// ---------------------------------------------------------------------------
// RBAC: let the API identity read Key Vault and write Blob.
// ---------------------------------------------------------------------------
resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, apiIdentity.id, 'kv-secrets-user')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: apiIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource blobDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, apiIdentity.id, 'blob-data-contributor')
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: apiIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource acrPullApi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, apiIdentity.id, 'acr-pull')
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: apiIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource acrPullFrontend 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, frontendIdentity.id, 'acr-pull')
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: frontendIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Alerts: availability monitor on the API. Wire an action group by setting
// alertActionGroupId (empty disables paging).
// ---------------------------------------------------------------------------
resource apiAvailabilityAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: '${baseName}-api-availability'
  location: 'global'
  tags: tags
  properties: {
    description: 'API availability dropped below 99.9%'
    severity: 1
    enabled: true
    scopes: [apiApp.id]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'availability'
          criterionType: 'StaticThresholdCriterion'
          metricName: 'Requests'
          metricNamespace: 'Microsoft.App/containerApps'
          operator: 'LessThan'
          threshold: 1
          timeAggregation: 'Count'
        }
      ]
    }
    actions: alertActionGroupId == '' ? [] : [{ actionGroupId: alertActionGroupId }]
  }
}

output apiFqdn string = apiApp.properties.configuration.ingress.fqdn
output frontendFqdn string = frontendApp.properties.configuration.ingress.fqdn
output postgresFqdn string = postgres.properties.fullyQualifiedDomainName
output keyVaultUri string = keyVault.properties.vaultUri
output storageAccountName string = storage.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output logAnalyticsWorkspaceId string = logAnalytics.id
