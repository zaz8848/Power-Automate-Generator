---
name: create-flow
description: >
  Create, deploy, and manage Power Automate Cloud Flows programmatically via REST API.
  Supports both regular PA flows and Copilot Studio Workflows (with graph canvas).
  USE WHEN: 创建 flow、部署 flow、生成 Power Automate、建自动化流程、create flow、deploy flow、
  generate Power Automate、build automation。
  Supports multiple tenants via profiles.
argument-hint: Describe the flow you want to create, e.g. "create a flow that sends Teams notification when SharePoint list item is created"
---

# Create Power Automate Flow

This skill generates and deploys Power Automate Cloud Flows via REST API.
It supports regular PA flows, Agent flows, and Copilot Studio Workflows (with visual graph canvas).

## Path Resolution

This skill is part of the **Automate Generator** project.
Resolve the project root from this SKILL.md's file path — it is 4 levels up (`.github/skills/create-flow/SKILL.md` → project root).

```powershell
# Compute once at the start of any session
$SKILL_ROOT = "D:\A_Code\Automate Generator-public"  # ← AI: replace with actual resolved path
```

All paths below use `$SKILL_ROOT` as the project root. Adjust if the user cloned to a different location.

## Prerequisites

- A configured profile in `$SKILL_ROOT/profiles/` directory (run `/configure-profile` first if not set up)
- Valid refresh token in the profile (run `/configure-profile` to obtain one)
- Python 3.x (only needed for Workflow type — `definition_to_graph.py`)

---

## Phase 1: Profile & Requirements

### Step 1: Load Profile

```powershell
$profilePath = "$SKILL_ROOT\profiles\{profileName}.json"
$profile = Get-Content $profilePath -Raw | ConvertFrom-Json
```

The user should specify which profile to use. Profile format: see `$SKILL_ROOT/profiles/profile-template.json`.

### Step 2: Confirm Flow Type

Ask the user if not clear:

| Type | What it includes | Trigger pattern | Graph canvas |
|---|---|---|---|
| **Regular PA flow** | `definition` only | Various (Recurrence, OpenApiConnectionWebhook, etc.) | No |
| **Agent flow** | `definition` only (uses Copilot Studio connector actions) | `Request` kind `Button` | No |
| **Workflow** | `definition` + `associatedData.graph` | `Request` kind `Button` (trigger name varies!) | Yes |

**Key distinction**: Agent flows and regular PA flows have no structural difference at the API level — the only difference is which connector actions they use internally. Workflows are structurally different because they include the `associatedData.graph` in a trigger's metadata.
| **Workflow** | `definition` + `associatedData.graph` (visual canvas in Copilot Studio) |

### Step 3: Analyze Requirements

Parse the user's request into:
1. **Trigger** — what starts the flow (email arrival, schedule, manual, webhook, PowerApps button, virtual agent, etc.)
2. **Actions** — what the flow does (send email, create record, call agent, query Dataverse, etc.)
3. **Branching logic** — conditions, switches, loops, scopes
4. **If Workflow** — confirm Agent schemaName if using Agent actions (query Dataverse `bots` table or flow-dictionary)

---

## Phase 2: Component & Connection Lookup

### Step 4: Query Component Library

Check the component catalog to find templates for each required trigger/action:

```powershell
$catalog = Get-Content "$SKILL_ROOT\components\_catalog.json" -Raw | ConvertFrom-Json
```

For each required action:
- **Found** → Read the component JSON file for `template`, `inputSchema`, `outputSchema`
- **Not found** → Tell user: "I haven't learned the `{action}` component yet. Can you point me to an existing flow that uses it? I'll learn from it."

**CRITICAL — Output field validation**: Before referencing any action output field (e.g. `outputs('xxx')?['body/Path']`), **verify the field exists in the component's `outputSchema`**. Never guess field names — this has caused real bugs (e.g. SharePoint `CreateFile` returns `body/Path` but `body/{Link}` is always null).

### Step 5: Check Dynamic Parameters

For **every** action, read its component file's `inputSchema` and look for parameters with `x-ms-dynamic-list` or `x-ms-dynamic-values`.

These values **must not be hardcoded** — they must be fetched via API:
1. Find the `dynamicList.operationId` in the Swagger
2. Call that API through the connector's connection to get valid options
3. Present options to user or auto-match based on their description

**Common dynamic parameters**: Agent ID, SharePoint Site/Library, Dataverse Table Name, Copilot Agent, etc.

**Consequence of skipping**: Deployment may succeed but actions fail at runtime, or Copilot Studio canvas shows "Required" errors.

### Step 6: Get Connections & Connection References

```powershell
# Get token for Flow API
$flowToken = & "$SKILL_ROOT\.github\skills\create-flow\get-token.ps1" `
  -ProfilePath $profilePath `
  -Scope "https://service.flow.microsoft.com/.default offline_access"

# Get connections for a specific connector
$conns = Invoke-RestMethod `
  -Uri "https://api.powerapps.com/providers/Microsoft.PowerApps/apis/{connectorName}/connections?`$filter=environment eq '$($profile.environmentId)'&api-version=2016-11-01" `
  -Headers @{Authorization="Bearer $paToken"}
  # Note: PowerApps API needs scope: https://service.powerapps.com/.default offline_access
```

For Workflow type, also get `connectionReferenceLogicalName` from Dataverse:

```powershell
$dvToken = & "$SKILL_ROOT\.github\skills\create-flow\get-token.ps1" `
  -ProfilePath $profilePath `
  -Scope "https://$($profile.dataverseOrg)/user_impersonation offline_access"

$connRefs = Invoke-RestMethod `
  -Uri "https://$($profile.dataverseOrg)/api/data/v9.2/connectionreferences?`$select=connectionreferencelogicalname,connectorid,connectionid" `
  -Headers @{Authorization="Bearer $dvToken"}
```

---

## Phase 3: Build Flow JSON

### Step 7: Construct clientdata

Start from the base template at `$SKILL_ROOT/.github/skills/create-flow/flow-template.json`, or use a complete example from `$SKILL_ROOT/flow-templates/` as reference.

**Real-world flow templates** (in `$SKILL_ROOT/flow-templates/`):
- `manual-hello-world.json` — Simplest possible flow (button trigger + Compose)
- `email-auto-reply.json` — Email trigger + OpenAPI connector pattern
- `scheduled-sharepoint-to-teams.json` — Recurrence + multi-connector pattern

#### Two connectionReferences formats (critical distinction)

**Flow Management API format** (used in POST/PATCH body):
```json
"connectionReferences": {
  "shared_office365": {
    "connectionName": "{connectionId}",
    "source": "Embedded",
    "id": "/providers/Microsoft.PowerApps/apis/shared_office365",
    "tier": "NotSpecified"
  }
}
```
- `connectionName` = actual connection ID (GUID like `shared-office365-ea776d9f-...`)
- `source` = `"Embedded"` (use creator's identity) or `"Invoker"` (use runner's identity)

**Dataverse/Copilot Studio format** (used in graph `connectionReferences` and Dataverse clientdata):
```json
"connectionReferences": {
  "shared_office365": {
    "api": { "name": "shared_office365" },
    "connection": {
      "connectionReferenceLogicalName": "af_sharedoffice365_abc12"
    },
    "runtimeSource": "invoker"
  }
}
```
- `connectionReferenceLogicalName` = from Dataverse `connectionreferences` table

**When to use which**: POST/PATCH to Flow Management API → use first format. Graph `connectionReferences` inside Workflow → use second format.

#### connectionReferences (Flow API format)

```json
"connectionReferences": {
  "shared_sharepointonline": {
    "connectionName": "{connectionId}",
    "source": "Embedded",
    "id": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
    "tier": "NotSpecified"
  }
}
```

- The **key name** (e.g. `shared_sharepointonline`) is referenced by actions as `connectionName`
- `connectionName` value = the actual connection ID (GUID or `shared_xxx-{guid}`)
- `id` = the API path for the connector

#### definition (triggers + actions)

Build from component templates. Fill in `host`, `parameters`, and `inputs` for each action.

#### Action host node format

```json
"host": {
  "apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
  "operationId": "PostItem",
  "connectionName": "shared_sharepointonline"
}
```

- Use `connectionName` (**not** `connection`) — Power Automate Code View sometimes shows `connection`, but clientdata requires `connectionName`
- Value = the key name in `connectionReferences` (not the connection GUID)

#### @@odata.type escaping (CRITICAL)

All `@odata.type` in the definition **must** be written as `@@odata.type`. Power Automate's template engine interprets `@` as expression syntax.

**Example**:
```json
"body": {
  "@@odata.type": "Microsoft.Dynamics.CRM.expando",
  "value@@odata.type": "Collection(Microsoft.Dynamics.CRM.expando)"
}
```

**Symptom if missed**: `TemplateValidationError: expected LeftParenthesis`

#### Naming convention

- **Action/trigger/case names**: English only (e.g. `Send_Email`, `Query_Agent`, `Classify_Switch`)
- **Chinese only in**: email body content, Agent prompt text (user-facing content)
- **Flow displayName**: Must start with `[AutoGen]` prefix (e.g. `[AutoGen] Email Quote Workflow v4`)

### Step 8: Build complete JSON

Assemble the full POST body:

```json
{
  "properties": {
    "displayName": "[AutoGen] {Flow Name}",
    "definition": {
      "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
      "contentVersion": "1.0.0.0",
      "parameters": {
        "$authentication": { "defaultValue": {}, "type": "SecureObject" },
        "$connections": { "defaultValue": {}, "type": "Object" }
      },
      "triggers": { /* from component templates */ },
      "actions": { /* from component templates */ },
      "outputs": {}
    },
    "connectionReferences": { /* from Step 7 */ }
  },
  "schemaVersion": "1.0.0.0"
}
```

Save to a temp file. **Use UTF-8 encoding** to preserve Chinese characters:
```powershell
[System.IO.File]::WriteAllText($flowJsonPath, $jsonString, [System.Text.Encoding]::UTF8)
```

### Copilot Studio Agent Integration (ExecuteCopilotAsyncV2)

When the flow calls a Copilot Studio Agent:

```json
{
  "Query_Agent": {
    "type": "OpenApiConnection",
    "inputs": {
      "parameters": {
        "Copilot": "{agent_schemaName}",
        "body/message": "Your prompt text here",
        "body/attachments": [
          {
            "contentUrl": "https://{sharepoint-domain}/sharing-link",
            "contentType": "application/pdf",
            "name": "document.pdf"
          }
        ]
      },
      "host": {
        "apiId": "/providers/Microsoft.PowerApps/apis/shared_microsoftcopilotstudio",
        "operationId": "ExecuteCopilotAsyncV2",
        "connectionName": "shared_microsoftcopilotstudio"
      }
    },
    "runAfter": { "Previous_Action": ["Succeeded"] }
  }
}
```

**Agent output reference**: Use `body('Query_Agent')?['lastResponse']` — NOT `outputs('Query_Agent')?['body/text']`.

**Attachment pitfall**: Agent does NOT download files via direct `contentUrl`. It needs SharePoint/OneDrive **sharing links** (e.g. `/:b:/g/...?e=...`). Direct file paths cause "Please upload the PDF" responses.

---

## Phase 4: Deploy

### Step 9: POST Deploy

```powershell
$flowToken = & "$SKILL_ROOT\.github\skills\create-flow\get-token.ps1" `
  -ProfilePath $profilePath `
  -Scope "https://service.flow.microsoft.com/.default offline_access"

# Read file as bytes to avoid encoding corruption
$flowBytes = [System.IO.File]::ReadAllBytes($flowJsonPath)

$result = Invoke-RestMethod `
  -Uri "https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/$($profile.environmentId)/flows?api-version=2016-11-01" `
  -Method POST `
  -Headers @{Authorization="Bearer $flowToken"; "Content-Type"="application/json; charset=utf-8"} `
  -Body $flowBytes
```

### Step 10: Deployment Safety

**If POST returns 400/404 — DO NOT blindly retry!**

The flow may have already been created despite the error. Check first:

```powershell
Start-Sleep -Seconds 5
$recent = Invoke-RestMethod `
  -Uri "https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/$($profile.environmentId)/flows?`$orderby=properties/createdTime desc&`$top=3&api-version=2016-11-01" `
  -Headers @{Authorization="Bearer $flowToken"}
```

- **Same-name flow found** → Use PATCH to fix it, don't POST again
- **Not found** → Fix the JSON issue, then retry POST

### Step 11: Workflow Plan Switch (Workflow only)

After deploying a Workflow, switch it from User Plan to Copilot Studio Plan:

```powershell
$entityId = $result.properties.workflowEntityId

$dvToken = & "$SKILL_ROOT\.github\skills\create-flow\get-token.ps1" `
  -ProfilePath $profilePath `
  -Scope "https://$($profile.dataverseOrg)/user_impersonation offline_access"

Invoke-RestMethod `
  -Uri "https://$($profile.dataverseOrg)/api/data/v9.2/workflows($entityId)" `
  -Method PATCH `
  -Headers @{Authorization="Bearer $dvToken"; "Content-Type"="application/json"} `
  -Body '{"modernflowtype": 1}'
```

- `modernflowtype = 0` → User Plan (default)
- `modernflowtype = 1` → Copilot Studio Plan (required for Workflows)
- Only needs to be set once at creation time

---

## Phase 5: Workflow Graph (Workflow only)

Skip this phase entirely for regular PA flows and Agent flows.

### Step 12: Generate graph from definition

Run the conversion script:

```powershell
python "$SKILL_ROOT\scripts\definition_to_graph.py" $flowJsonPath -o $outputJsonPath --conn-refs $connRefMappingPath
```

The script auto-converts most nodes but marks `_needsAI=true` on nodes it can't fully convert.

### Step 13: Process `_needsAI` nodes

AI must manually handle these node types:

| Node type | What to fill |
|---|---|
| `classify` | Extract `categories[]` + `examples[]` + `inputRich` from GPT prompt in the definition |
| `agent` | Parse `body/message` expressions → generate `instructionsRich.segments[]` (alternating `static` + `token`) |

### Step 14: Graph connectionReferences format

Graph uses a **different format** from Flow API clientdata:

| Property | Flow API (clientdata) | Copilot Studio (graph) |
|---|---|---|
| Connector ref | `connectionName` + `source` + `id` | `api.name` + `connection.connectionReferenceLogicalName` + `runtimeSource` |
| Action node type | `OpenApiConnection` | `connector` |
| M365 Copilot type | — | `m365Copilot` |
| Agent type | — | `agent` (needs `mode`/`botSchemaName`/`instructionsRich`) |
| Classify type | `PerformBoundAction` + GPT prompt | Native `classify` (`categories[]` + `inputRich` + `model`) |

### Step 15: PATCH graph into flow

The graph goes into the trigger's `metadata.associatedData`:

```json
{
  "properties": {
    "definition": { /* full definition with connectionReferenceName in each action host */ },
    "connectionReferences": { /* same as Phase 3 */ }
  }
}
```

**PATCH-specific requirements**:
- Every action's `host` must include `connectionReferenceName` (value = the key name in `connectionReferences`)
- PATCH body must contain **both** `definition` and `connectionReferences`
- The trigger name for Workflows is **not fixed** — scan all triggers for `metadata.associatedData.graph`

### Step 16: Ensure 1:1 node-action correspondence

**Every action in the definition MUST have a corresponding node in the graph.** If they don't match:
- Copilot Studio UI's Save button will delete unmatched actions from the definition
- This can corrupt the flow and cause "unpublished active row" 500 errors
- Once "unpublished active row" occurs, the flow is unrecoverable — must recreate

---

## Phase 6: Finalize

### Step 17: Save & Report

1. Save flow JSON to the consuming project's `flows/` directory (or the user's preferred location)
2. Update `flow-dictionary.json` if it exists in the target environment directory
3. Report to user:
   - Flow ID
   - Flow state (Started/Stopped)
   - Copilot Studio canvas link (for Workflows): `https://copilotstudio.microsoft.com/environments/{envId}/bots/{botId}/canvas`

---

## Known Pitfalls (Complete List)

| Issue | Symptom | Fix |
|---|---|---|
| `@odata.type` not escaped | `TemplateValidationError: expected LeftParenthesis` | Use `@@odata.type` |
| PowerShell `Set-Content` corrupts Chinese | Garbled JSON | Use `[System.IO.File]::ReadAllBytes()` / `ReadAllText()` |
| POST 400 but flow already created | Duplicate flows | Check recent flows before retrying |
| graph nodes ≠ definition actions | Copilot Studio deletes unmatched actions → "unpublished active row" | Ensure 1:1 correspondence |
| `unpublished active row` 500 | PATCH/Publish all fail | Must recreate flow (unrecoverable) |
| Missing `connectionReferenceName` in PATCH | PATCH error | Add `connectionReferenceName` to each action's `host` |
| Swagger 200 response has no schema | `outputSchema` empty | Check 201 → 202 → default response schema |
| Dynamic parameters hardcoded | Canvas shows "Required", runtime fails | Fetch via dynamic API call |
| `host.connection` instead of `host.connectionName` | Actions don't bind to connector | Always use `connectionName` in clientdata |
| `body/{Link}` on SharePoint CreateFile | Returns null | Use `body/Path` or `body/Id` instead — verify with `outputSchema` |
| Connector node type in graph | Blank box in canvas | Use `connector` (not `openApiConnection`) |
| Graph connectionReferences wrong format | `Cannot read connectionReferenceLogicalName` | Use `api.name` + `connection.connectionReferenceLogicalName` format |
| ParseJSON missing config | Canvas shows "Required" | Must have `operationId=parsejson` + `parametersSchema` + `parameters.schema` |

## API Endpoint Reference

| Operation | Method | Endpoint | Token Scope |
|---|---|---|---|
| Create flow | POST | `https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/{envId}/flows?api-version=2016-11-01` | `service.flow.microsoft.com` |
| Update flow | PATCH | Same + `/{flowId}` | Same |
| List flows | GET | Same + `?api-version=2016-11-01` | Same |
| Flow details | GET | Same + `/{flowId}?api-version=2016-11-01` | Same |
| Run history | GET | Same + `/{flowId}/runs?api-version=2016-11-01` | Same |
| Run actions | GET | Same + `/{flowId}/runs/{runId}/actions?api-version=2016-11-01` | Same |
| Action I/O | GET | Same + `/{flowId}/runs/{runId}/actions/{actionName}/repetitions?api-version=2016-11-01` | Same |
| Resubmit | POST | Same + `/{flowId}/triggers/{triggerName}/histories/{runId}/resubmit?api-version=2016-11-01` | Same |
| Dataverse workflow | GET | `https://{dataverseOrg}/api/data/v9.2/workflows({id})` | `{dataverseOrg}` |
| Connection refs | GET | `https://{dataverseOrg}/api/data/v9.2/connectionreferences` | Same |

## Scope Reference

| API | Scope |
|---|---|
| Flow Management | `https://service.flow.microsoft.com/.default offline_access` |
| Dataverse | `https://{dataverseOrg}/user_impersonation offline_access` |
| PowerApps | `https://service.powerapps.com/.default offline_access` |
| Power Platform | `https://api.powerplatform.com/.default offline_access` |
| SharePoint | `https://{tenant}.sharepoint.com/.default offline_access` |
| Microsoft Graph | `https://graph.microsoft.com/.default offline_access` |

**Note**: `.default` and resource-specific scopes (like `user_impersonation`) cannot be mixed in one request. Each API needs its own token.
