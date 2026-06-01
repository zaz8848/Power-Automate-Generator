# Generate component files from extracted raw data
# Reads _extracted_raw.json and creates structured component files

$OutputDir = "d:\A_Code\Automate Generator\components"
$rawData = Get-Content "$OutputDir\_extracted_raw.json" -Raw | ConvertFrom-Json

# ---- Helper: Normalize connector name for file paths ----
function Get-ConnectorBaseName {
    param([string]$ConnectorName)
    # Remove trailing _1, _2, -1, etc. for file grouping
    return $ConnectorName -replace '[-_]\d+$', ''
}

# ---- Helper: Clean template for storage (remove expression values, keep structure) ----
function ConvertTo-CleanJson {
    param($Object)
    return $Object | ConvertTo-Json -Depth 30 -Compress:$false
}

# =========================================
# 1. Generate OpenAPI action component files
# =========================================
Write-Host "`n=== Generating OpenAPI Action Components ===" -ForegroundColor Cyan

# Create openapi directory
$openapiDir = "$OutputDir\actions\openapi"
if (-not (Test-Path $openapiDir)) { New-Item -ItemType Directory -Path $openapiDir -Force | Out-Null }

$actionCatalog = @()
foreach ($prop in $rawData.components.PSObject.Properties) {
    $comp = $prop.Value
    $connector = $comp.connector
    $opId = $comp.operationId
    $baseName = Get-ConnectorBaseName $connector
    $fileName = "${connector}_${opId}.json"
    
    # Build clean template
    $templateObj = $comp.template
    
    # Get first template key and fix host.connectionName
    $firstKey = ($templateObj.PSObject.Properties | Select-Object -First 1).Name
    $templateAction = $templateObj.$firstKey
    
    # Ensure host uses connectionName (not connection)
    if ($templateAction.inputs -and $templateAction.inputs.host) {
        $host_ = $templateAction.inputs.host
        if ($host_.connection -and -not $host_.connectionName) {
            $host_ | Add-Member -NotePropertyName 'connectionName' -NotePropertyValue $host_.connection -Force
            $host_.PSObject.Properties.Remove('connection')
        }
    }
    
    $componentFile = [ordered]@{
        id = $comp.id
        connector = $connector
        connectorBase = $baseName
        operationId = $opId
        apiId = $comp.apiId
        type = $comp.type
        learnedFrom = $comp.learnedFrom
        learnedFromName = $comp.learnedFromName
        learnedAt = (Get-Date -Format 'yyyy-MM-dd')
        verified = $true
        environment = $comp.environment
        template = $templateObj
    }
    
    $componentFile | ConvertTo-Json -Depth 30 | Out-File "$openapiDir\$fileName" -Encoding utf8
    Write-Host "  Created: actions/openapi/$fileName"
    
    $actionCatalog += [ordered]@{
        id = $comp.id
        connector = $connector
        operationId = $opId
        type = $comp.type
        file = "actions/openapi/$fileName"
        flowCount = $comp.learnedFrom.Count
    }
}

# =========================================
# 2. Generate trigger component files
# =========================================
Write-Host "`n=== Generating Trigger Components ===" -ForegroundColor Cyan

$triggerCatalog = @()
foreach ($prop in $rawData.triggerComponents.PSObject.Properties) {
    $trig = $prop.Value
    
    if ($trig.connector) {
        # OpenAPI trigger
        $connector = $trig.connector
        $opId = $trig.operationId
        $fileName = "${connector}_${opId}.json"
        
        # Fix host.connectionName
        $templateObj = $trig.template
        $firstKey = ($templateObj.PSObject.Properties | Select-Object -First 1).Name
        $templateTrig = $templateObj.$firstKey
        if ($templateTrig.inputs -and $templateTrig.inputs.host) {
            $host_ = $templateTrig.inputs.host
            if ($host_.connection -and -not $host_.connectionName) {
                $host_ | Add-Member -NotePropertyName 'connectionName' -NotePropertyValue $host_.connection -Force
                $host_.PSObject.Properties.Remove('connection')
            }
        }
        
        $trigFile = [ordered]@{
            id = $trig.id
            connector = $connector
            operationId = $opId
            apiId = $trig.apiId
            type = $trig.type
            kind = $trig.kind
            learnedFrom = $trig.learnedFrom
            learnedFromName = $trig.learnedFromName
            learnedAt = (Get-Date -Format 'yyyy-MM-dd')
            verified = $true
            environment = $trig.environment
            template = $templateObj
        }
        
        $trigFile | ConvertTo-Json -Depth 30 | Out-File "$OutputDir\triggers\$fileName" -Encoding utf8
        Write-Host "  Created: triggers/$fileName"
        
        $triggerCatalog += [ordered]@{
            id = $trig.id
            connector = $connector
            operationId = $opId
            type = $trig.type
            file = "triggers/$fileName"
            flowCount = $trig.learnedFrom.Count
        }
    } else {
        # Built-in trigger (Recurrence, Request, etc.)
        $trigType = $trig.type
        $trigKind = if ($trig.kind) { $trig.kind } else { "none" }
        $fileName = "$trigType-$trigKind".ToLower() + ".json"
        
        $trigFile = [ordered]@{
            id = $trig.id
            type = $trigType
            kind = $trigKind
            learnedFrom = $trig.learnedFrom
            learnedFromName = $trig.learnedFromName
            learnedAt = (Get-Date -Format 'yyyy-MM-dd')
            verified = $true
            template = $trig.template
        }
        
        $trigFile | ConvertTo-Json -Depth 30 | Out-File "$OutputDir\triggers\$fileName" -Encoding utf8
        Write-Host "  Created: triggers/$fileName"
        
        $triggerCatalog += [ordered]@{
            id = $trig.id
            type = $trigType
            kind = $trigKind
            file = "triggers/$fileName"
            flowCount = $trig.learnedFrom.Count
        }
    }
}

# =========================================
# 3. Update built-in action component files
# =========================================
Write-Host "`n=== Updating Built-in Action Components ===" -ForegroundColor Cyan

$builtinCatalog = @()
foreach ($prop in $rawData.builtinActions.PSObject.Properties) {
    $act = $prop.Value
    $actType = $act.type
    
    # Map type to filename
    $fileNameMap = @{
        'Compose' = 'compose.json'
        'If' = 'condition.json'
        'Foreach' = 'foreach.json'
        'Query' = 'filter-array.json'
        'Http' = 'http.json'
        'Join' = 'join.json'
        'ParseJson' = 'parse-json.json'
        'Response' = 'response.json'
        'Scope' = 'scope.json'
        'Select' = 'select.json'
        'Switch' = 'switch.json'
        'Terminate' = 'terminate.json'
        'Until' = 'until.json'
        'InitializeVariable' = 'variables.json'
        'SetVariable' = 'variables.json'
        'AppendToArrayVariable' = 'variables.json'
        'AppendToStringVariable' = 'variables.json'
        'IncrementVariable' = 'variables.json'
        'Wait' = 'wait.json'
    }
    
    $fileName = $fileNameMap[$actType]
    if (-not $fileName) { $fileName = "$($actType.ToLower()).json" }
    
    # For variable types, we'll group them
    if ($actType -in @('SetVariable','AppendToArrayVariable','AppendToStringVariable','IncrementVariable')) {
        # These get added to variables.json as additional templates
        continue  # will handle below
    }
    
    $builtinFile = [ordered]@{
        id = $actType
        type = $actType
        learnedFrom = $act.learnedFrom
        learnedFromName = $act.learnedFromName
        learnedAt = (Get-Date -Format 'yyyy-MM-dd')
        verified = $true
        templates = $act.templates
    }
    
    $builtinFile | ConvertTo-Json -Depth 30 | Out-File "$OutputDir\actions\$fileName" -Encoding utf8
    Write-Host "  Updated: actions/$fileName"
    
    $builtinCatalog += [ordered]@{
        id = $actType
        type = $actType
        file = "actions/$fileName"
        flowCount = $act.learnedFrom.Count
    }
}

# Handle variable types - combine into one file
$varTypes = @('InitializeVariable','SetVariable','AppendToArrayVariable','AppendToStringVariable','IncrementVariable')
$varTemplates = @()
$varLearnedFrom = @()
$varLearnedFromName = @()
foreach ($vt in $varTypes) {
    $key = "builtin|$vt"
    $prop = $rawData.builtinActions.PSObject.Properties | Where-Object { $_.Name -eq $key }
    if ($prop) {
        $act = $prop.Value
        foreach ($t in $act.templates) {
            $varTemplates += [ordered]@{ type = $vt; name = $t.name; template = $t.template }
        }
        $varLearnedFrom += $act.learnedFrom
        $varLearnedFromName += $act.learnedFromName
    }
}
if ($varTemplates.Count -gt 0) {
    $varFile = [ordered]@{
        id = 'Variables'
        types = $varTypes
        learnedFrom = ($varLearnedFrom | Select-Object -Unique)
        learnedAt = (Get-Date -Format 'yyyy-MM-dd')
        verified = $true
        templates = $varTemplates
    }
    $varFile | ConvertTo-Json -Depth 30 | Out-File "$OutputDir\actions\variables.json" -Encoding utf8
    Write-Host "  Updated: actions/variables.json"
    
    $builtinCatalog += [ordered]@{
        id = 'Variables'
        types = $varTypes
        file = 'actions/variables.json'
    }
}

# =========================================
# 4. Generate _catalog.json
# =========================================
Write-Host "`n=== Generating _catalog.json ===" -ForegroundColor Cyan

$catalog = [ordered]@{
    version = '2.0.0'
    generatedAt = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')
    summary = [ordered]@{
        totalOpenApiActions = $actionCatalog.Count
        totalTriggers = $triggerCatalog.Count
        totalBuiltinActions = $builtinCatalog.Count
        environments = @(
            'orgdf331f66.crm5.dynamics.com'
            '{dataverseOrg}'
            'orgc954877b.crm5.dynamics.com'
        )
        flowsAnalyzed = ($rawData.components.PSObject.Properties | ForEach-Object { $_.Value.learnedFrom } | ForEach-Object { $_ } | Select-Object -Unique).Count
    }
    connectors = @()
    triggers = $triggerCatalog
    builtinActions = $builtinCatalog
    openApiActions = $actionCatalog
}

# Group actions by connector for connector summary
$connectorGroups = $actionCatalog | Group-Object -Property { (Get-ConnectorBaseName $_.connector) }
foreach ($group in $connectorGroups) {
    $catalog.connectors += [ordered]@{
        connector = $group.Name
        operations = $group.Group | ForEach-Object { $_.operationId } | Sort-Object -Unique
        operationCount = ($group.Group | ForEach-Object { $_.operationId } | Sort-Object -Unique).Count
    }
}

$catalog | ConvertTo-Json -Depth 10 | Out-File "$OutputDir\_catalog.json" -Encoding utf8
Write-Host "`n_catalog.json updated with $($actionCatalog.Count) actions, $($triggerCatalog.Count) triggers, $($builtinCatalog.Count) built-in actions"

# =========================================
# 5. Update connector files
# =========================================
Write-Host "`n=== Updating Connector Files ===" -ForegroundColor Cyan

$connectorDir = "$OutputDir\connectors"
foreach ($group in $connectorGroups) {
    $connectorBase = $group.Name
    $connectorFile = "$connectorDir\$connectorBase.json"
    
    $operations = @()
    foreach ($act in $group.Group) {
        $operations += [ordered]@{
            operationId = $act.operationId
            type = $act.type
            componentFile = $act.file
            flowCount = $act.flowCount
        }
    }
    
    # Also add triggers for this connector
    $connTriggers = $triggerCatalog | Where-Object { 
        $_.connector -and (Get-ConnectorBaseName $_.connector) -eq $connectorBase 
    }
    $trigOps = @()
    foreach ($t in $connTriggers) {
        $trigOps += [ordered]@{
            operationId = $t.operationId
            type = $t.type
            isTrigger = $true
            componentFile = $t.file
            flowCount = $t.flowCount
        }
    }
    
    $connData = [ordered]@{
        connector = $connectorBase
        learnedAt = (Get-Date -Format 'yyyy-MM-dd')
        operations = $operations
        triggers = $trigOps
    }
    
    # If file exists, preserve any existing fields like prerequisites
    if (Test-Path $connectorFile) {
        try {
            $existing = Get-Content $connectorFile -Raw | ConvertFrom-Json
            if ($existing.prerequisites) {
                $connData.prerequisites = $existing.prerequisites
            }
            if ($existing.apiId) {
                $connData.apiId = $existing.apiId
            }
        } catch {}
    }
    
    $connData | ConvertTo-Json -Depth 10 | Out-File $connectorFile -Encoding utf8
    Write-Host "  Updated: connectors/$connectorBase.json ($($operations.Count) actions, $($trigOps.Count) triggers)"
}

Write-Host "`n=== DONE ===" -ForegroundColor Green
