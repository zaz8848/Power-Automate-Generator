# Extract components from all Dataverse environments
# Reads tokens from browser localStorage export, queries flows, extracts actions/triggers

param(
    [string]$OutputDir = "d:\A_Code\Automate Generator\components"
)

# ---- Token loading ----
$raw = Get-Content "c:\Users\ASUS\AppData\Roaming\Code\User\workspaceStorage\01e69b2967807adda5b57dd50ee8f3e1\GitHub.copilot-chat\chat-session-resources\f5db563f-f284-4a53-8483-cbbc73516ccf\toolu_vrtx_019rXPK8M5SQg2qbUBywTw8B__vscode-1779763476276\content.txt" -Raw
$json = $raw -replace '^Result: ',''
$json = $json.Substring(1, $json.Length - 2).Replace('\"','"')
$tokens = $json | ConvertFrom-Json

function Get-AllFlows {
    param([string]$OrgUrl, [string]$Token)
    $h = @{
        'Authorization'="Bearer $Token"
        'Accept'='application/json'
        'OData-MaxVersion'='4.0'
        'OData-Version'='4.0'
        'Prefer'='odata.maxpagesize=250'
    }
    $allFlows = @()
    $url = "https://$OrgUrl/api/data/v9.2/workflows?`$filter=category eq 5 and statecode eq 1&`$select=workflowid,name,clientdata"
    while ($url) {
        $r = Invoke-RestMethod -Uri $url -Headers $h
        $allFlows += $r.value
        $url = $r.'@odata.nextLink'
    }
    return $allFlows
}

# ---- Collect all flows from all environments ----
$envFlows = @{}
foreach ($org in @($tokens.PSObject.Properties)) {
    Write-Host "`n=== Querying $($org.Name) ===" -ForegroundColor Cyan
    try {
        $flows = Get-AllFlows -OrgUrl $org.Name -Token $org.Value
        Write-Host "  Found $($flows.Count) flows"
        $envFlows[$org.Name] = $flows
    } catch {
        Write-Host "  FAILED: $($_.Exception.Response.StatusCode)" -ForegroundColor Red
    }
}

# ---- Parse clientdata and extract components ----
$components = @{}  # key = "connector|operationId" -> component data
$triggerComponents = @{}
$builtinActions = @{}  # Compose, If, Foreach, etc.

foreach ($envEntry in $envFlows.GetEnumerator()) {
    $orgUrl = $envEntry.Key
    foreach ($flow in $envEntry.Value) {
        if (-not $flow.clientdata) { continue }
        try {
            $cd = $flow.clientdata | ConvertFrom-Json
        } catch { continue }
        
        $def = $cd.properties.definition
        if (-not $def) { continue }
        
        # ---- Extract triggers ----
        if ($def.triggers) {
            foreach ($trigProp in $def.triggers.PSObject.Properties) {
                $trigName = $trigProp.Name
                $trig = $trigProp.Value
                $trigType = $trig.type
                $trigKind = $trig.kind
                
                if ($trig.inputs -and $trig.inputs.host) {
                    $connector = $trig.inputs.host.connectionName
                    if (-not $connector) { $connector = $trig.inputs.host.connection }
                    $opId = $trig.inputs.host.operationId
                    $apiId = $trig.inputs.host.apiId
                    
                    if ($connector -and $opId) {
                        $key = "trigger|$connector|$opId"
                        if (-not $triggerComponents[$key]) {
                            $triggerComponents[$key] = @{
                                id = "${connector}_${opId}"
                                connector = $connector
                                operationId = $opId
                                apiId = $apiId
                                type = $trigType
                                kind = $trigKind
                                learnedFrom = @($flow.workflowid)
                                learnedFromName = @($flow.name)
                                environment = @($orgUrl)
                                template = @{
                                    $trigName = $trig
                                }
                            }
                        } else {
                            if ($flow.workflowid -notin $triggerComponents[$key].learnedFrom) {
                                $triggerComponents[$key].learnedFrom += $flow.workflowid
                                $triggerComponents[$key].learnedFromName += $flow.name
                            }
                            if ($orgUrl -notin $triggerComponents[$key].environment) {
                                $triggerComponents[$key].environment += $orgUrl
                            }
                        }
                    }
                } else {
                    # Built-in trigger (Recurrence, Request, etc.)
                    $key = "trigger|builtin|${trigType}_${trigKind}"
                    if (-not $triggerComponents[$key]) {
                        $triggerComponents[$key] = @{
                            id = "${trigType}_${trigKind}"
                            type = $trigType
                            kind = $trigKind
                            learnedFrom = @($flow.workflowid)
                            learnedFromName = @($flow.name)
                            environment = @($orgUrl)
                            template = @{
                                $trigName = $trig
                            }
                        }
                    } else {
                        if ($flow.workflowid -notin $triggerComponents[$key].learnedFrom) {
                            $triggerComponents[$key].learnedFrom += $flow.workflowid
                            $triggerComponents[$key].learnedFromName += $flow.name
                        }
                    }
                }
            }
        }
        
        # ---- Extract actions (recursive for scoped actions) ----
        function Extract-Actions {
            param($Actions, [string]$FlowId, [string]$FlowName, [string]$OrgUrl)
            if (-not $Actions) { return }
            foreach ($actProp in $Actions.PSObject.Properties) {
                $actName = $actProp.Name
                $act = $actProp.Value
                $actType = $act.type
                
                if ($act.inputs -and $act.inputs.host) {
                    # OpenApiConnection action
                    $connector = $act.inputs.host.connectionName
                    if (-not $connector) { $connector = $act.inputs.host.connection }
                    $opId = $act.inputs.host.operationId
                    $apiId = $act.inputs.host.apiId
                    
                    if ($connector -and $opId) {
                        $key = "action|$connector|$opId"
                        if (-not $script:components[$key]) {
                            $script:components[$key] = @{
                                id = "${connector}_${opId}"
                                connector = $connector
                                operationId = $opId
                                apiId = $apiId
                                type = $actType
                                learnedFrom = @($FlowId)
                                learnedFromName = @($FlowName)
                                environment = @($OrgUrl)
                                template = @{
                                    $actName = $act
                                }
                            }
                        } else {
                            if ($FlowId -notin $script:components[$key].learnedFrom) {
                                $script:components[$key].learnedFrom += $FlowId
                                $script:components[$key].learnedFromName += $FlowName
                            }
                            if ($OrgUrl -notin $script:components[$key].environment) {
                                $script:components[$key].environment += $OrgUrl
                            }
                        }
                    }
                } else {
                    # Built-in action (Compose, If, Foreach, Switch, etc.)
                    $key = "builtin|$actType"
                    if (-not $script:builtinActions[$key]) {
                        $script:builtinActions[$key] = @{
                            id = $actType
                            type = $actType
                            learnedFrom = @($FlowId)
                            learnedFromName = @($FlowName)
                            templates = @(@{ name = $actName; template = $act })
                        }
                    } else {
                        if ($FlowId -notin $script:builtinActions[$key].learnedFrom) {
                            $script:builtinActions[$key].learnedFrom += $FlowId
                            $script:builtinActions[$key].learnedFromName += $FlowName
                        }
                        # Keep up to 3 example templates per built-in type
                        if ($script:builtinActions[$key].templates.Count -lt 3) {
                            $script:builtinActions[$key].templates += @{ name = $actName; template = $act }
                        }
                    }
                }
                
                # Recurse into scoped actions
                if ($act.actions) { Extract-Actions -Actions $act.actions -FlowId $FlowId -FlowName $FlowName -OrgUrl $OrgUrl }
                if ($act.else -and $act.else.actions) { Extract-Actions -Actions $act.else.actions -FlowId $FlowId -FlowName $FlowName -OrgUrl $OrgUrl }
                foreach ($caseProp in @($act.cases.PSObject.Properties -ne $null)) {
                    if ($caseProp.Value.actions) { Extract-Actions -Actions $caseProp.Value.actions -FlowId $FlowId -FlowName $FlowName -OrgUrl $OrgUrl }
                }
            }
        }
        
        if ($def.actions) {
            Extract-Actions -Actions $def.actions -FlowId $flow.workflowid -FlowName $flow.name -OrgUrl $orgUrl
        }
    }
}

# ---- Summary ----
Write-Host "`n=== EXTRACTION SUMMARY ===" -ForegroundColor Green
Write-Host "OpenAPI Actions: $($components.Count)"
Write-Host "Triggers: $($triggerComponents.Count)"
Write-Host "Built-in Actions: $($builtinActions.Count)"

Write-Host "`n--- OpenAPI Actions ---"
foreach ($c in ($components.GetEnumerator() | Sort-Object Key)) {
    Write-Host "  $($c.Value.connector) | $($c.Value.operationId) (from $($c.Value.learnedFrom.Count) flows)"
}

Write-Host "`n--- Triggers ---"
foreach ($t in ($triggerComponents.GetEnumerator() | Sort-Object Key)) {
    $val = $t.Value
    if ($val.connector) {
        Write-Host "  $($val.connector) | $($val.operationId) [$($val.type)]"
    } else {
        Write-Host "  [builtin] $($val.type) / $($val.kind)"
    }
}

Write-Host "`n--- Built-in Actions ---"
foreach ($b in ($builtinActions.GetEnumerator() | Sort-Object Key)) {
    Write-Host "  $($b.Value.type) (from $($b.Value.learnedFrom.Count) flows)"
}

# ---- Save extracted data to temp file for next step ----
$extractedData = @{
    components = $components
    triggerComponents = $triggerComponents
    builtinActions = $builtinActions
}
$extractedData | ConvertTo-Json -Depth 20 | Out-File "$OutputDir\_extracted_raw.json" -Encoding utf8
Write-Host "`nRaw data saved to $OutputDir\_extracted_raw.json"
