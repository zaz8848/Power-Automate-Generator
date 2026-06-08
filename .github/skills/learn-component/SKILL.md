---
name: learn-component
description: |
  当 /describe-component 找不到组件时，从 Swagger 学习新 connector action /
  trigger，写入 components/ 并更新 _catalog.json。
  用户说"学习 X"/"learn component"/"扫一下这个 connector"时使用。
applyTo: '**'
---

# /learn-component — 组件学习 SOP

---

## 触发条件

- `/describe-component` 找不到组件，自动建议本 skill
- 用户说 "学习 shared_X 的 Y operation"
- 用户说 "把这个 flow 学了"（→ 调 `/scan-environment` 的子流程）

---

## 输入

- `<connector>`（如 `shared_office365`）必填
- `<operationId>`（如 `GetEmailsV3`）— 单个学习时必填
- 或：`<flowId>` — 从真实 flow 反向学

---

## 执行步骤

### Step 1 — 拉 Swagger

```powershell
# 1) 找 connector swaggerUrl
$conn = Get-Content "components\connectors\<connector>.json" -Raw | ConvertFrom-Json
$swaggerUrl = $conn.swaggerUrl

# 2) 拉 Swagger（需要 PowerApps token，scope: service.powerapps.com/.default）
#    从当前 profile 手动刷一个：
$profile = Get-Content "profiles/<tenant>.json" -Raw | ConvertFrom-Json
$body = @{ grant_type='refresh_token'; client_id=$profile.clientId; client_secret=$profile.clientSecret; refresh_token=$profile.refreshToken; scope='https://service.powerapps.com/.default offline_access' }
$paToken = (Invoke-RestMethod -Uri "https://login.microsoftonline.com/$($profile.tenantId)/oauth2/v2.0/token" -Method POST -Body $body -ContentType "application/x-www-form-urlencoded").access_token

$swagger = Invoke-RestMethod -Uri $swaggerUrl -Headers @{Authorization="Bearer $paToken"}
```

详见 `token-management.instructions.md` “一次性批量刷多 scope” 节（根据用户需要的 API 拿对应 token）。

### Step 2 — 提取指定 operation 的 schema

从 `swagger.paths` 找到 operationId 对应的 path，提取：
- `parameters[]` → `inputSchema`
- `responses['200'].schema` → `outputSchema`
- `x-ms-summary` / `description` → `notes`

### Step 3 — 生成组件文件

```jsonc
// components/actions/openapi/<connector>_<operationId>.json
{
  "id": "<connector>_<operationId>",
  "connector": "<connector>",
  "operationId": "<operationId>",
  "type": "OpenApiConnection",
  "learnedFrom": "<flowId 或 'swagger'>",
  "learnedAt": "2026-06-07",
  "verified": false,                  // ⚠️ 必须 false，直到实战部署成功
  "swaggerLearned": true,
  "template": { /* clientdata 片段 */ },
  "inputSchema": { /* 从 Swagger 提取 */ },
  "outputSchema": { /* 从 Swagger 提取 */ },
  "parameters": { /* 参数示例 */ },
  "graphConvertible": true,
  "graphNodeType": "connector",
  "notes": "..."
}
```

### Step 4 — 更新 `_catalog.json`

```powershell
$catalog = Get-Content "components\_catalog.json" -Raw | ConvertFrom-Json
$catalog.actions.openapi += @{
    id = "<connector>_<operationId>"
    file = "actions/openapi/<connector>_<operationId>.json"
    verified = $false
}
$catalog.lastUpdated = (Get-Date -Format "yyyy-MM-dd")
$catalog | ConvertTo-Json -Depth 10 | Set-Content "components\_catalog.json"
```

### Step 5 — 报告

```
✅ 学到 1 个新组件: shared_office365_GetEmailsV3
   ├─ 文件: components/actions/openapi/shared_office365_GetEmailsV3.json
   ├─ verified: false (待实战验证)
   └─ 提示: 部署成功后跑 /create-flow 用一次，再手动改 verified=true
```

---

## 反向学（从真实 flow）

输入 `<flowId>` 时改走：

```powershell
# 拉 flow definition
$flow = Invoke-RestMethod -Uri "https://api.flow.microsoft.com/.../flows/$flowId" -Headers $h
# 遍历 actions / triggers，每个对应 connector + operationId 都跑 Step 2-4
```

**特别注意：检查 graph 节点是否是「画布原生节点」**

读取 flow 的 `clientdata.properties.definition.triggers.*.metadata.associatedData.graph.nodes[]` 时，**每个 node 的 `type` 字段**要跟下面这张表比对：

| 画布 type | 定义层 type | 学习去向 |
|---|---|---|
| `connector` | OpenApiConnection | 按 Step 2-4 学 → `components/actions/openapi/<connector>_<op>.json` |
| `start` | trigger | 按 Step 2-4 学 → `components/triggers/<name>.json` |
| `builtinFunction` | Compose / ParseJson / Filter / Select 等 | 按 Step 2-4 学 → `components/actions/<name>.json` |
| `ifElse` / `switch` / `foreach` | If / Switch / Foreach | 内置，无需新建组件 |
| `m365Copilot` | OpenApiConnection (shared_m365copilotv2) | 按 Step 2-4 学 |
| `classify` | OpenApiConnection (PerformBoundAction + GPT) | 学 connector，标 `graphConvertible="partial"` |
| **`agent`** | OpenApiConnection (shared_agentnode/InvokeDefinition or InvokeAgent) | **⚠️ 不要按 Step 2-4 学单 connector，而是按 `components/actions/agent-node.json` 格式完整记录 mode / inlineTools / simpleProperties / jsonSchema / instructionsRich 等画布原生字段** |
| 其它**陌生** type | — | **⚠️ 发现新画布原生节点！停下来报告用户，按 agent-node.json 范式建独立组件文件**（不是 connector 组件） |

**判断"是不是画布原生节点"的硬规则**：
- node `data.config` 里**没有** `apiName` 字段 → 多半是原生节点
- node `data.config` 里有 `apiName="shared_xxx"` + `operationId` → 是 connector 节点，按 Step 2-4 走
- 看到原生节点 → 优先看是否已存在 `components/actions/<type>-node.json` 或 `components/actions/<type>.json`，没有就新建；同时给对应的 connector 组件加 `graphCanvasOverride.useInstead` 指针

---

## 成功标志

- [ ] `components/actions/openapi/` 或 `triggers/` 多了一个新文件
- [ ] `_catalog.json` 已更新（数量 +1）
- [ ] 报告了 verified=false 待验证

---

## 禁止事项

- ❌ 学完直接标 `verified=true`（必须实战部署成功才能改）
- ❌ Swagger 拉不到就编 schema
- ❌ 覆盖已有 verified=true 的组件文件（先备份）

---

## 后置动作

学完一批后，提示用户：
- 跑 `/create-flow` 实战验证
- 或 `/sync-to-devtool` 推到 DevTool 公开仓
