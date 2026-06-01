param(
    [string]$Token,
    [string]$EnvId = "9ffec6fe-9e60-eaf8-921d-be20e366a19b",
    [string]$ComponentDir = "d:\A_Code\Automate Generator\components\actions\openapi"
)

$headers = @{ Authorization = "Bearer $Token" }
$fixedCount = 0; $failedCount = 0; $missedOps = @()

# Step 1: Find all components with bad schemas
$badFiles = @()
Get-ChildItem "$ComponentDir\*.json" | ForEach-Object {
    $c = Get-Content $_.FullName -Raw | ConvertFrom-Json
    $needsInput = (-not $c.inputSchema) -or (($c.inputSchema | ConvertTo-Json -Depth 1 -Compress) -eq '{}')
    $needsOutput = (-not $c.outputSchema) -or (($c.outputSchema | ConvertTo-Json -Depth 1 -Compress) -eq '{}')
    if ($needsInput -or $needsOutput) {
        $badFiles += [PSCustomObject]@{
            File = $_.FullName
            OperationId = $c.operationId
            Connector = $c.connector
            ApiName = ($c.connector -replace '-\d+$','' -replace '_(\d+)$','')
        }
    }
}
Write-Host "Found $($badFiles.Count) components needing schema fix"

# Step 2: Group by API name
$byApi = $badFiles | Group-Object -Property ApiName

# Step 3: Fetch Swagger per API and fix
foreach ($group in $byApi) {
    $apiName = $group.Name
    Write-Host "`n--- $apiName ($($group.Count) ops) ---"
    
    $url = "https://api.powerapps.com/providers/Microsoft.PowerApps/apis/${apiName}?api-version=2016-11-01&`$filter=environment eq '${EnvId}'"
    try {
        $apiResp = Invoke-RestMethod -Uri $url -Headers $headers -Method GET -ErrorAction Stop
    } catch {
        Write-Host "  ERROR fetching API: $($_.Exception.Message)"
        $failedCount += $group.Count
        continue
    }
    
    $swagger = $apiResp.properties.swagger
    if (-not $swagger -or -not $swagger.paths) {
        Write-Host "  No swagger/paths returned"
        $failedCount += $group.Count
        continue
    }
    
    # Build operationId map
    $opMap = @{}
    foreach ($pathKey in $swagger.paths.PSObject.Properties.Name) {
        $pathObj = $swagger.paths.$pathKey
        foreach ($method in $pathObj.PSObject.Properties.Name) {
            if ($method -in @('get','post','put','patch','delete')) {
                $op = $pathObj.$method
                if ($op.operationId) {
                    $opMap[$op.operationId] = @{
                        parameters = $op.parameters
                        responses = $op.responses
                    }
                }
            }
        }
    }
    Write-Host "  Swagger has $($opMap.Count) operations"
    
    foreach ($item in $group.Group) {
        $opId = $item.OperationId
        if (-not $opMap.ContainsKey($opId)) {
            Write-Host "  MISS: $opId"
            $missedOps += "$($item.Connector)/$opId"
            $failedCount++
            continue
        }
        
        $opDef = $opMap[$opId]
        $inputSchema = if ($opDef.parameters) { $opDef.parameters } else { @() }
        
        $outputSchema = $null
        foreach ($code in @('200','201','202')) {
            if ($opDef.responses.PSObject.Properties.Name -contains $code) {
                $respObj = $opDef.responses.$code
                if ($respObj.schema) { $outputSchema = $respObj.schema; break }
            }
        }
        if (-not $outputSchema) {
            if ($opDef.responses.PSObject.Properties.Name -contains 'default' -and $opDef.responses.default.schema) {
                $outputSchema = $opDef.responses.default.schema
            } else {
                $outputSchema = @{ type = "object"; description = "No response schema in Swagger" }
            }
        }
        
        # Read JSON as raw text, parse, and rebuild with schemas
        $rawJson = Get-Content $item.File -Raw
        $compContent = $rawJson | ConvertFrom-Json
        
        # Use Add-Member to handle missing properties
        if ($compContent.PSObject.Properties.Name -contains 'inputSchema') {
            $compContent.inputSchema = $inputSchema
        } else {
            $compContent | Add-Member -NotePropertyName 'inputSchema' -NotePropertyValue $inputSchema
        }
        if ($compContent.PSObject.Properties.Name -contains 'outputSchema') {
            $compContent.outputSchema = $outputSchema
        } else {
            $compContent | Add-Member -NotePropertyName 'outputSchema' -NotePropertyValue $outputSchema
        }
        if ($compContent.PSObject.Properties.Name -contains 'swaggerLearned') {
            $compContent.swaggerLearned = $true
        } else {
            $compContent | Add-Member -NotePropertyName 'swaggerLearned' -NotePropertyValue $true
        }
        $compContent | ConvertTo-Json -Depth 20 | Set-Content $item.File -Encoding UTF8
        Write-Host "  OK: $opId"
        $fixedCount++
    }
}

Write-Host "`n========================================="
Write-Host "Fixed: $fixedCount / $($badFiles.Count)"
Write-Host "Failed: $failedCount"
if ($missedOps.Count -gt 0) {
    Write-Host "`nMissed operationIds (not in Swagger):"
    $missedOps | ForEach-Object { Write-Host "  $_" }
}
