---
name: scan-environment
description: >
  Scan a Power Platform environment to discover existing flows, connectors, connections, and connection references.
  Also supports learning flow components into the component library.
  USE WHEN: 扫描环境、查看有哪些 flow、list flows、scan environment、discover connectors、
  查 connectionReference、look up connections、学习 flow.
argument-hint: Specify profile name and what to scan (flows, connectors, connections, or learn a specific flow)
---

# Scan Environment

Discovers resources in a Power Platform environment and optionally learns flow components.

## Path Resolution

Resolve the project root from this SKILL.md's path — it is 4 levels up (`.github/skills/scan-environment/SKILL.md` → project root).

```powershell
$SKILL_ROOT = "D:\A_Code\Automate Generator-public"  # ← AI: replace with actual resolved path
```

---

## Step 1: Load Profile

```powershell
$profilePath = "$SKILL_ROOT\profiles\{profileName}.json"
$profile = Get-Content $profilePath -Raw | ConvertFrom-Json
```

## Step 2: Choose What to Scan

Ask the user what they want to discover:

| Target | Description |
|---|---|
| **Flows** | List all flows in the environment (name, ID, state, type) |
| **Connectors** | List available connectors and their operations |
| **Connections** | List active connections (connector + connection ID) |
| **Connection References** | List Dataverse connection references (for Workflow generation) |
| **Dataverse Workflows** | List category=5 workflows (cloud flows stored in Dataverse) |
| **Learn a flow** | Extract components from a specific flow into the component library |

## Step 3: Get Token & Query

### Scan Flows (Flow Management API)

```powershell
$flowToken = & "$SKILL_ROOT\.github\skills\create-flow\get-token.ps1" `
  -ProfilePath $profilePath `
  -Scope "https://service.flow.microsoft.com/.default offline_access"

# List all flows
$flows = Invoke-RestMethod `
  -Uri "https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/$($profile.environmentId)/flows?api-version=2016-11-01" `
  -Headers @{Authorization="Bearer $flowToken"}

# Display summary
$flows.value | ForEach-Object {
    [PSCustomObject]@{
        Name   = $_.properties.displayName
        ID     = $_.name
        State  = $_.properties.state
        Type   = if ($_.properties.definitionSummary.triggers[0].swaggerOperationId -like "*virtualagent*") { "Workflow" } else { "Regular" }
        Modified = $_.properties.lastModifiedTime
    }
} | Format-Table -AutoSize
```

### Scan Connectors (PowerApps API)

```powershell
$paToken = & "$SKILL_ROOT\.github\skills\create-flow\get-token.ps1" `
  -ProfilePath $profilePath `
  -Scope "https://service.powerapps.com/.default offline_access"

$connectors = Invoke-RestMethod `
  -Uri "https://api.powerapps.com/providers/Microsoft.PowerApps/apis?`$filter=environment eq '$($profile.environmentId)'&api-version=2016-11-01" `
  -Headers @{Authorization="Bearer $paToken"}

$connectors.value | ForEach-Object {
    [PSCustomObject]@{
        Name    = $_.properties.displayName
        ApiName = $_.name
        Tier    = $_.properties.tier
    }
} | Format-Table -AutoSize
```

### Scan Connections

```powershell
# Uses same PowerApps token as connectors
$connections = Invoke-RestMethod `
  -Uri "https://api.powerapps.com/providers/Microsoft.PowerApps/connections?`$filter=environment eq '$($profile.environmentId)'&api-version=2016-11-01" `
  -Headers @{Authorization="Bearer $paToken"}

$connections.value | ForEach-Object {
    [PSCustomObject]@{
        Connector    = $_.properties.apiId.Split('/')[-1]
        ConnectionId = $_.name
        Status       = $_.properties.statuses[0].status
        CreatedBy    = $_.properties.createdBy.displayName
    }
} | Format-Table -AutoSize
```

### Scan Connection References (Dataverse)

```powershell
$dvToken = & "$SKILL_ROOT\.github\skills\create-flow\get-token.ps1" `
  -ProfilePath $profilePath `
  -Scope "https://$($profile.dataverseOrg)/user_impersonation offline_access"

$connRefs = Invoke-RestMethod `
  -Uri "https://$($profile.dataverseOrg)/api/data/v9.2/connectionreferences?`$select=connectionreferencelogicalname,connectorid,connectionid,connectionreferencedisplayname" `
  -Headers @{Authorization="Bearer $dvToken"}

$connRefs.value | ForEach-Object {
    [PSCustomObject]@{
        DisplayName    = $_.connectionreferencedisplayname
        LogicalName    = $_.connectionreferencelogicalname
        Connector      = ($_.connectorid -split '/')[-1]
        ConnectionId   = $_.connectionid
    }
} | Format-Table -AutoSize
```

### Scan Dataverse Workflows

```powershell
# Uses same Dataverse token
$workflows = Invoke-RestMethod `
  -Uri "https://$($profile.dataverseOrg)/api/data/v9.2/workflows?`$filter=category eq 5&`$select=name,workflowid,statecode,modifiedon,clientdata&`$orderby=modifiedon desc" `
  -Headers @{Authorization="Bearer $dvToken"}

$workflows.value | ForEach-Object {
    [PSCustomObject]@{
        Name       = $_.name
        WorkflowId = $_.workflowid
        State      = if ($_.statecode -eq 1) { "Active" } else { "Draft" }
        Modified   = $_.modifiedon
    }
} | Format-Table -AutoSize
```

## Step 4: Learn Flow Components (Optional)

When the user says "learn flow X", extract its components into the component library:

### 4a: Get Flow Definition

```powershell
# Via Flow Management API (current user's flows)
$flowDetail = Invoke-RestMethod `
  -Uri "https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/$($profile.environmentId)/flows/{flowId}?api-version=2016-11-01" `
  -Headers @{Authorization="Bearer $flowToken"}

$definition = $flowDetail.properties.definition
$connRefs = $flowDetail.properties.connectionReferences
```

Or via Dataverse (any user's flows):

```powershell
$wfDetail = Invoke-RestMethod `
  -Uri "https://$($profile.dataverseOrg)/api/data/v9.2/workflows({workflowId})?`$select=clientdata,name" `
  -Headers @{Authorization="Bearer $dvToken"}

$clientdata = $wfDetail.clientdata | ConvertFrom-Json
$definition = $clientdata.properties.definition
```

### 4b: Extract & Save Components

For each trigger and action in the definition:

1. Identify the connector and `operationId`
2. Check if component already exists in `$SKILL_ROOT/components/`
3. If new → create component JSON file with `template`, `parameters`, `learnedFrom`
4. **Fetch Swagger** to extract `inputSchema` and `outputSchema`:
   ```powershell
   $swagger = Invoke-RestMethod `
     -Uri "https://api.powerapps.com/providers/Microsoft.PowerApps/apis/{connectorName}?`$select=properties.swagger&api-version=2016-11-01" `
     -Headers @{Authorization="Bearer $paToken"}
   ```
5. Update `$SKILL_ROOT/components/_catalog.json` with the new component entry

### 4c: Workflow-specific Learning

If the flow is a Workflow (has `associatedData.graph` in any trigger's metadata):
1. Learn all triggers/actions/connectionReferences (same as regular flow)
2. **Also save** the `associatedData.graph` structure for future Workflow generation reference
3. Save the full flow JSON to `flows/{env}/workflow/` directory

**Note**: Workflow trigger names are not fixed — scan ALL triggers for `metadata.associatedData.graph`.

## Step 5: Report Results

Present findings in a table format. For flow learning, report:
- Number of new components learned
- Number of existing components updated
- Any components with missing Swagger schemas (mark `swaggerLearned: false`)

## Scope Reference

| Target | API | Token Scope |
|---|---|---|
| Flows | Flow Management API | `https://service.flow.microsoft.com/.default offline_access` |
| Connectors | PowerApps API | `https://service.powerapps.com/.default offline_access` |
| Connections | PowerApps API | `https://service.powerapps.com/.default offline_access` |
| Connection Refs | Dataverse | `https://{dataverseOrg}/user_impersonation offline_access` |
| Dataverse Workflows | Dataverse | `https://{dataverseOrg}/user_impersonation offline_access` |
