<#
.SYNOPSIS
    Convert a Power Automate flow definition to Workflow graph (associatedData.graph).
    
.DESCRIPTION
    Takes a flow JSON file with a standard definition (triggers + actions) and generates
    the associatedData.graph structure needed for Copilot Studio Workflows.
    
.PARAMETER FlowJsonPath
    Path to the flow JSON file.
    
.PARAMETER OutputPath
    Optional. Output path for the updated JSON. Defaults to overwriting the input file.
    
.PARAMETER TriggerName
    Name of the trigger to inject the graph into. Defaults to the first trigger found.

.EXAMPLE
    .\definition-to-graph.ps1 -FlowJsonPath "flows/zaf-prod/workflow/my-flow.json"
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$FlowJsonPath,
    [string]$OutputPath,
    [string]$TriggerName,
    [string]$WorkflowName
)

if (-not $OutputPath) { $OutputPath = $FlowJsonPath }

# Read flow JSON
$flowJson = Get-Content $FlowJsonPath -Raw -Encoding UTF8
$flow = $flowJson | ConvertFrom-Json

$definition = $flow.properties.definition
$connectionRefs = $flow.properties.connectionReferences

# Determine trigger
if (-not $TriggerName) {
    $TriggerName = $definition.triggers.PSObject.Properties.Name | Select-Object -First 1
}
$trigger = $definition.triggers.$TriggerName

if (-not $WorkflowName) {
    $WorkflowName = $flow.properties.displayName
}

# --- Helper functions ---
function New-Guid-Short { [guid]::NewGuid().ToString() }

# Map action type to graph node type
function Get-NodeType($action) {
    $type = $action.type
    switch ($type) {
        'OpenApiConnection'            { 
            $apiId = $action.inputs.host.apiId
            if ($apiId -match 'shared_m365copilotv2') { return 'm365Copilot' }
            if ($apiId -match 'shared_commondataserviceforapps') {
                $opId = $action.inputs.host.operationId
                if ($opId -eq 'PerformBoundAction' -and $action.inputs.parameters.'actionName' -eq 'Microsoft.Dynamics.CRM.QuickTest') {
                    return 'classify'
                }
            }
            return 'openApiConnection'
        }
        'OpenApiConnectionWebhook'     { 
            $apiId = $action.inputs.host.apiId
            if ($apiId -match 'shared_microsoftcopilotstudio') { return 'agent' }
            return 'openApiConnection'
        }
        'Compose'                      { return 'builtinFunction' }
        'If'                           { return 'condition' }
        'Foreach'                      { return 'foreach' }
        'Switch'                       { return 'switch' }
        'Scope'                        { return 'scope' }
        'Until'                        { return 'until' }
        'Wait'                         { return 'wait' }
        default                        { return 'builtinFunction' }
    }
}

# --- Build graph ---
$nodes = @()
$edges = @()
$nodeActionMapping = @{}

# 1. Start node
$startNodeId = "start-$(New-Guid-Short)"
$triggerConfig = @{ triggerType = "connector" }
if ($trigger.inputs.host) {
    $triggerConfig['connector'] = @{
        apiName = ($trigger.inputs.host.apiId -replace '.*/apis/', '')
        operationName = $trigger.inputs.host.operationId
        connectionName = $trigger.inputs.host.connectionName
    }
}

$startNode = [ordered]@{
    id = $startNodeId
    name = $TriggerName -replace '_', ' '
    type = 'start'
    version = 1
    position = @{ x = 250; y = 270 }
    data = @{
        config = $triggerConfig
        outcomes = @(@{ id = 'default'; label = 'Default' })
    }
    measured = @{ width = 240; height = 66 }
}
$nodes += [PSCustomObject]$startNode

# 2. Process actions recursively
$xStart = 566
$xStep = 316
$currentX = $xStart

function Process-Actions($actionsObj, [ref]$nodes, [ref]$edges, [ref]$mapping, [ref]$posX, $parentNodeId, $yOffset) {
    if (-not $actionsObj) { return }
    
    $prevNodeId = $parentNodeId
    
    foreach ($actionName in $actionsObj.PSObject.Properties.Name) {
        $action = $actionsObj.$actionName
        $nodeType = Get-NodeType $action
        $nodeId = "$nodeType-$(New-Guid-Short)"
        
        $node = [ordered]@{
            id = $nodeId
            name = $actionName -replace '_', ' '
            type = $nodeType
            version = 1
            position = @{ x = $posX.Value; y = $yOffset }
            data = @{
                config = @{}
                outcomes = @(@{ id = 'default'; label = 'Default' })
            }
            measured = @{ width = 240; height = 66 }
        }
        
        # Add config details
        if ($action.inputs.host) {
            $node.data.config['operationId'] = $action.inputs.host.operationId
        }
        
        # Handle Switch outcomes
        if ($action.type -eq 'Switch' -and $action.cases) {
            $outcomes = @()
            foreach ($caseName in $action.cases.PSObject.Properties.Name) {
                $outcomes += @{ id = $caseName.ToLower(); label = $caseName }
            }
            $node.data.outcomes = $outcomes
        }
        
        $nodes.Value += [PSCustomObject]$node
        $mapping.Value[$nodeId] = @($actionName)
        
        # Edge from previous node or parent
        if ($action.runAfter) {
            foreach ($dep in $action.runAfter.PSObject.Properties.Name) {
                # Find node for this dependency
                $depNodeId = $null
                foreach ($key in $mapping.Value.Keys) {
                    if ($mapping.Value[$key] -contains $dep) { $depNodeId = $key; break }
                }
                if ($depNodeId) {
                    $edges.Value += [PSCustomObject]@{ id = "edge-$depNodeId-$nodeId"; source = $depNodeId; target = $nodeId }
                }
            }
        } elseif ($prevNodeId -eq $parentNodeId -and $parentNodeId) {
            $edges.Value += [PSCustomObject]@{ id = "edge-$parentNodeId-$nodeId"; source = $parentNodeId; target = $nodeId }
        }
        
        $posX.Value += $xStep
        
        # Recurse into Switch cases
        if ($action.type -eq 'Switch' -and $action.cases) {
            $caseY = $yOffset - 150
            foreach ($caseName in $action.cases.PSObject.Properties.Name) {
                $caseActions = $action.cases.$caseName.actions
                if ($caseActions -and $caseActions.PSObject.Properties.Count -gt 0) {
                    # Add edge from switch to first case action
                    $edges.Value += [PSCustomObject]@{ 
                        id = "edge-$nodeId-case-$caseName"
                        source = $nodeId
                        target = $null  # Will be filled by recursive call
                        sourceHandle = $caseName.ToLower()
                    }
                    Process-Actions $caseActions $nodes $edges $mapping $posX $nodeId $caseY
                    # Fix the last edge target
                    $lastEdge = $edges.Value[$edges.Value.Count - 1]
                    if ($lastEdge.source -eq $nodeId -and $null -eq $lastEdge.target) {
                        # Remove placeholder edge, recursive call already created proper edges
                        $edges.Value = $edges.Value[0..($edges.Value.Count - 2)]
                    }
                }
                $caseY += 150
            }
        }
        
        $prevNodeId = $nodeId
    }
}

$yBase = 270
Process-Actions $definition.actions ([ref]$nodes) ([ref]$edges) ([ref]$nodeActionMapping) ([ref]$currentX) $startNodeId $yBase

# 3. Build graph object
$graph = [ordered]@{
    name = $WorkflowName
    nodes = $nodes
    edges = $edges
    connectionReferences = $connectionRefs
}

$associatedData = @{
    graph = $graph
    nodeActionMapping = $nodeActionMapping
}

# 4. Inject into trigger metadata
if (-not $trigger.metadata) {
    $trigger | Add-Member -NotePropertyName 'metadata' -NotePropertyValue @{}
}
if ($trigger.metadata -is [PSCustomObject]) {
    if ($trigger.metadata.PSObject.Properties.Name -contains 'associatedData') {
        $trigger.metadata.associatedData = $associatedData
    } else {
        $trigger.metadata | Add-Member -NotePropertyName 'associatedData' -NotePropertyValue $associatedData
    }
} else {
    $trigger.metadata = @{ associatedData = $associatedData }
}

# 5. Save
$flow | ConvertTo-Json -Depth 30 | Set-Content $OutputPath -Encoding UTF8
Write-Host "Graph generated successfully!"
Write-Host "  Nodes: $($nodes.Count) (1 start + $($nodes.Count - 1) actions)"
Write-Host "  Edges: $($edges.Count)"
Write-Host "  Saved to: $OutputPath"
