---
name: flow-operations
description: Flow 创建/修改/排查/Resubmit 的完整 API SOP — 确保 AI 用正确的 API 和参数操作 Flow
applyTo: "**"
---

# Flow 操作 SOP

## 2026-06-07 重大更新（Copilot Studio Preview 拓包验证）

据据：`flows/zaf-prod/_save_capture_2026-06-07.json`（浏览器 fetch/XHR hook 抓捖 18 条 UI Save 的请求）。

**变更要点**：

1. **“Dataverse 直写 workflow 不可用” 说法废弃** —— Copilot Studio Preview UI 现在就是直接 `POST {orgUrl}/api/data/v9.2/workflows`，返回 `201 Created`。创建时 body 要同时带齐 `name` / `category=5` / `type=1` / `modernflowtype=1` / `primaryentity="none"` / `clientdata`（6 个顶层字段）。代替 Flow Management API。
2. **`modernflowtype` 不需二次 PATCH** —— 创建时一次性带入即可，Workflow / 普通 Flow 都是这么走。下面 Phase 6 原“创建后 PATCH `modernflowtype=1`”的步骤 ❌ 过时。
3. **`checkFlowAlerts` 是独立后端** —— 不是前端校验，是 Copilot Studio 保存后调的 lint API，详见下面《校验 API》章节。
4. **graph node 的 `data.config` 有完整字段集** —— 原本我们只存了 `operationId`，现实测还要 `operationName` / `displayName` / `category` / `categoryDisplayName` / `iconUri` / `brandColor` / `description` / `parametersSchema` / `outcomes[].outcomeSchema`。组件库要补 `graphTemplate` 字段装这些，详见 `component-library.instructions.md`。

## API 端点参考

> **所有 `{orgUrl}` / `{envId}` 占位符**都从用户当前 profile 读取：
> `{orgUrl} = profile.environments[<envName>].dataverseUrl`
> `{envId} = profile.environments[<envName>].environmentId`
> 详见 `.github/instructions/token-management.instructions.md` “Profile schema 速读” 节。

| 操作 | 方法 | 端点 | Token scope |
|---|---|---|---|
| **创建 flow / workflow (首选)** | POST | `{orgUrl}/api/data/v9.2/workflows` | `{orgUrl}/user_impersonation` |
| **创建 flow (旧路径)** | POST | `https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/{envId}/flows?api-version=2016-11-01` | `service.flow.microsoft.com` |
| **保存后 lint 校验** | POST | `https://{envIdNoDash}.{region}.environment.api.powerplatform.com/powerautomate/flows/{flowId}/checkFlowAlerts?api-version=1` | `service.flow.microsoft.com` |
| **修改 flow** | PATCH | `https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/{envId}/flows/{flowId}?api-version=2016-11-01` | `service.flow.microsoft.com` |
| **查询 flow 列表** | GET | `https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/{envId}/flows?api-version=2016-11-01` | 同上 |
| **查看 flow 详情** | GET | 同上 `/{flowId}?api-version=2016-11-01` | 同上 |
| **查看 run history** | GET | 同上 `/{flowId}/runs?api-version=2016-11-01` | 同上 |
| **查看 run action** | GET | 同上 `/{flowId}/runs/{runId}/actions?api-version=2016-11-01` | 同上 |
| **Resubmit run** | POST | 同上 `/{flowId}/triggers/{triggerName}/histories/{runId}/resubmit?api-version=2016-11-01` | 同上 |
| **读 Dataverse workflow** | GET | `{orgUrl}/api/data/v9.2/workflows({workflowid})` | 同 Dataverse 一行 |
| **查 connectionReference** | GET | `{orgUrl}/api/data/v9.2/connectionreferences` | 同上 |

## 环境选择

在 chat 里用户说 “在 ZAF Prod / 在 prod / 用 contoso / --env prod” 时，AI 按这个优先级选：

1. 用户明说的 env name → 查当前 profile `environments[].name` 匹配
2. 用户没说 → 用 `profile.defaultEnvironment`
3. 用户说了某个不在 environments[] 中的 env → 提示用户先编辑 profile 加进去（或跳 `/configure-profile`）

## 创建 Flow

### Workflow 端到端生成 SOP（2026-05-29 固化）

**适用场景**：用户说"帮我生成一个 Workflow"时，按此 checklist 执行。

#### Phase 1：需求解析

1. **确认类型** — 普通 PA flow 还是 Workflow？（用户没说就问）
2. **拆解需求** → 列出所需的 trigger + 每个 action（含分支逻辑）
3. **确认 Agent** — 如果用到 Agent，确认 Agent schemaName（查 flow-dictionary 或 Dataverse `bots` 表）

#### Phase 2：组件查询

4. **查 `components/_catalog.json`** → 确认每个 action 是否已学习
5. **缺组件** → 问用户"我没学过 XX，能指给我一个用了它的 flow 吗？"
6. **查组件的 `inputSchema` / `outputSchema`** → 确认参数名和输出字段（**不要猜字段名**）
7. **查组件的 `graphConvertible`** → 标记哪些需要 AI 处理 graph
8. **动态参数值处理（通用规则，每个 action 都必须检查）**：
   - 读组件文件的 `inputSchema`，找所有带 `x-ms-dynamic-list` 或 `x-ms-dynamic-values` 的参数
   - 这些参数的值**不能硬编码猜测**，必须调用对应的 API 获取可选值
   - 获取方式：从 Swagger 找到 `dynamicList.operationId`，通过 connector 的 connection 调用该 API
   - **常见动态参数**：Agent ID、SharePoint Site/Library、Dataverse Table Name、Copilot Agent 等
   - 获取后列出可选值让用户选择，或根据用户需求描述自动匹配
   - **违反后果**：不查动态值 → 部署可能成功但运行时参数无效，或前端报错 "Required"

#### Phase 3：Connection 准备

9. **查 connection ID** — 优先从 flow-dictionary 里已有 flow 复用；没有则查 `GET api.powerapps.com/.../apis/{connector}/connections?$filter=environment eq '{envId}'`
10. **查 `connectionReferenceLogicalName`** — 从 Dataverse `connectionreferences` 表按 `connectionid` 匹配
    ```
    GET .../api/data/v9.2/connectionreferences?$select=connectionreferencelogicalname,connectorid,connectionid
    ```

#### Phase 4：生成 definition（clientdata）

11. **构建 flow JSON** — 含 `connectionReferences`（Flow API 格式：`connectionName` + `source: "Embedded"` + `id`）+ `definition`（triggers + actions）
12. **`@@odata.type` 转义** — definition 中所有 `@odata.type` 必须写成 `@@odata.type`（Power Automate 模板引擎会解析 `@` 开头的内容）
13. **action host 节点** — 用 `connectionName`（不是 `connection`），值 = `connectionReferences` 的 key 名
14. **命名规范** — action 名/trigger 名/case 名全英文，仅邮件正文/Agent prompt 正文用中文

#### Phase 5：生成 graph（Workflow 专属）

15. **跑 Python 脚本** — `python scripts/definition_to_graph.py <flow.json> -o <output.json> --conn-refs <mapping.json>`
16. **AI 处理 `_needsAI` 节点**：
    - **classify 节点** → 从 GPT prompt 提取 `categories[]` + `examples[]` + `inputRich`
    - **agent 节点** → 解析 `body/message` 中的表达式 → 生成 `instructionsRich.segments[]`（static + token 交替）
17. **graph connectionReferences** — 用 Copilot Studio 格式：`api.name` + `connection.connectionReferenceLogicalName` + `runtimeSource`
18. **注入 graph** → 放入 trigger 的 `metadata.associatedData`（graph + nodeActionMapping）

#### Phase 6：部署（2026-06-07 重写 - Dataverse 直写路径）

19. **读 profile + 获取 token** —
    ```powershell
    $profile = Get-Content "profiles/$ProfileName.json" -Raw | ConvertFrom-Json
    $env     = $profile.environments | Where-Object { $_.name -eq ($EnvName ?? $profile.defaultEnvironment) } | Select -First 1
    $orgUrl  = $env.dataverseUrl.TrimEnd('/')
    # 拿 Dataverse access token（scope 必须是 $orgUrl/user_impersonation，不是别的 env 的）
    $dvToken = (python scripts/configure_profile.py "profiles/$ProfileName.json" --env $env.name --get-token)[-1]
    ```
20. **POST 创建** — `POST $orgUrl/api/data/v9.2/workflows`。body 6 个顶层字段：
    ```jsonc
    {
      "name": "[AutoGen] My Workflow",
      "category": 5,             // Cloud Flow
      "type": 1,                 // Definition
      "modernflowtype": 1,       // 创建时一次性带入，不需二次 PATCH
      "primaryentity": "none",
      "clientdata": "{...stringified JSON...}"   // 含 graph (Workflow) 或不含 graph (普通 Flow)
    }
    ```
    返回 `201 Created`，响应体含新 `workflowid`。
21. **调 checkFlowAlerts (可选 / 保存后 lint)** — `POST {envApi}/powerautomate/flows/{flowId}/checkFlowAlerts?api-version=1`，body 是**不含 graph 的简化 definition**，返回 `{errors:[], warnings:[]}`。错误需在下一次 PATCH 修正。
22. **部署防护** — POST 返回错误时**不要盲目重试**，先查 `GET .../workflows?$orderby=createdon desc&$top=3` 检查是否已创建。

#### Phase 6-Legacy：走 Flow Management API（旧路径，仅在 Dataverse 路径报错时 fallback）

23a. POST `https://api.flow.microsoft.com/.../environments/{envId}/flows?api-version=2016-11-01`，body 是 Flow API 格式（`properties.definition` + `properties.connectionReferences`）。成功后另需 `PATCH .../workflows({entityId})` 设 `modernflowtype=1`（旧路径才需要二次 PATCH）。

#### Phase 7：PATCH graph（如果 Phase 5 的 graph 没在 Phase 4 一起 POST）

23. **PATCH 定义 + graph** — 每个 action 的 host 必须加 `connectionReferenceName`（值 = connectionReferences 的 key 名）
24. **PATCH body** — 必须同时含 `definition` + `connectionReferences`

#### Phase 8：收尾

25. **保存 flow JSON** → `flows/{env}/workflow/<名称>.json`
26. **更新 flow-dictionary.json** — 新增条目（displayName / flowId / workflowEntityId / state / localPath）
27. **汇报结果** — Flow ID / 状态 / Copilot Studio 画布链接

### 已知踩坑清单

| 坑 | 表现 | 解法 |
|---|---|---|
| `@odata.type` 未转义 | POST 返回 `TemplateValidationError: expected LeftParenthesis` | 所有 `@odata.type` → `@@odata.type` |
| PowerShell Set-Content 损坏中文 | JSON 中中文变乱码 | 用 `[System.IO.File]::ReadAllBytes()` 读，或 Python 处理 |
| Swagger API 缺 `$filter` | 返回 400 | 必须加 `$filter=environment eq '{envId}'` |
| graph connectionReferences 格式不对 | Copilot Studio 报 `Cannot read connectionReferenceLogicalName` | graph 内用 `api.name` + `connection.connectionReferenceLogicalName` 格式 |
| graph node type 错误 | 节点在画布上渲染为空白框 | 用 `connector`（不是 `openApiConnection`），`agent`/`classify` 等原生类型 |
| POST 400 但 flow 已创建 | 重复创建同名 flow | POST 报错后先查询再决定重试还是 PATCH |
| PATCH 缺 connectionReferenceName | PATCH 报错 | 每个 action 的 host 加 `connectionReferenceName` |
| Swagger 200 response 无 schema | outputSchema 为空 | 依次检查 201 → 202 → default 的 response schema |
| definition 和 graph 节点不 1:1 对应 | Copilot Studio UI Save 删除不在 graph 里的 action → definition 破损 → "unpublished active row" 锁死 | 每个 definition action 必须在 graph 里有对应节点 |
| "unpublished active row" 500 | PATCH/Publish 全部 500 | 只能重建新版本，无法解锁 |
| connector parameters 不完整 | 画布报 "Required" | graph connector node 的 parameters 必须包含所有 parametersSchema.required 字段 |
| ParseJSON 缺正确 config | 画布报 "Required" | 必须有 `operationId=parsejson` + `parametersSchema` + `parameters.schema`（示例值格式） |

### 硬约束：Flow 命名前缀

**所有 AI 创建的 flow 必须以 `[AutoGen]` 前缀开头**。例如：
- `[AutoGen] Email Quote Workflow v4`
- `[AutoGen] Service Email Workflow v2`

### Flow 字典（`flow-dictionary.json`）

每个环境目录下维护一个 `flow-dictionary.json`，记录该环境所有已部署 flow 的索引。

**用途**：
- 后续修改 flow 时，通过字典查 flowId，不用每次调 API
- 查看哪些 flow 有本地 JSON 文件，哪些没有
- 接力开发时快速了解环境里有什么

**结构**：
```json
{
  "generatedAt": "2026-05-29T...",
  "environment": "ZAF Prod",
  "environmentId": "9ffec6fe-...",
  "totalFlows": 30,
  "flows": [
    {
      "displayName": "flow 名称",
      "flowId": "xxx-xxx-xxx",
      "workflowEntityId": "yyy-yyy-yyy",
      "state": "Started",
      "localPath": "flows/zaf-prod/workflow/xxx.json"  // null 表示没有本地文件
    }
  ]
}
```

**维护时机**：
- **创建 flow 后** → 新增条目
- **删除/标记删除 flow 后** → 更新 state
- **首次进入新环境** → 通过 `GET .../flows` 初始化整个字典

### Workflow Plan 切换（2026-05-29 发现）

Workflow 必须切换到 **Copilot Studio plan** 才是真正的 Workflow。通过 Dataverse API 设置：

```powershell
# 1. 部署 flow 后，获取 workflowEntityId（从 Flow API 返回的 properties.workflowEntityId）
# 2. PATCH Dataverse workflows 表的 modernflowtype 字段
PATCH {orgUrl}/api/data/v9.2/workflows({workflowEntityId})
Body: {"modernflowtype": 1}
```

- `modernflowtype = 0` → User Plan（默认）
- `modernflowtype = 1` → Copilot Studio Plan（Workflow 必须用这个）
- **仅创建时需要设置一次**，后续更新 flow 定义（PATCH definition）不需要重复设置

### 命名与语言规范（2026-05-29）

- **action 名称**：全部用英文（如 `Query_Agent`、`Classify_Switch`、`Reply_Email`）
- **graph node 名称**：全部用英文（如 `Start`、`Classify`、`Query Agent`、`Generate Quote`）
- **trigger 名称**：全部用英文（如 `manual`、`When_email_arrives`）
- **switch case 名称**：全部用英文（如 `Inquiry`、`AfterSales`、`Other`）
- **flow displayName**：用英文（如 `[AutoGen] Email Quote Workflow`）
- **唯一用中文的场景**：邮件正文模板（`body/message`）、Agent prompt 正文——因为最终用户看到的内容需要中文
- **参数名/字段引用**：保持原始英文不动（如 `body/from`、`body/subject`）

### Workflow 生成规则（2026-05-29 新增）

**Workflow 与普通 flow 的结构差异**：
- 普通 flow：只有 `definition`（triggers + actions）
- Workflow：`definition` + 某个 trigger 的 `metadata.associatedData.graph`（编排画布，触发器名不固定）

**`associatedData` 结构**：
```json
{
  "graph": {
    "name": "Workflow 名称",
    "nodes": [
      {
        "id": "start-{guid}",        // 起始节点，固定 type="start"
        "name": "Start",
        "type": "start",
        "version": 1,
        "position": { "x": 250, "y": 270 },
        "data": {
          "config": { "triggerType": "manual" },
          "outcomes": [{ "id": "default", "label": "Default", "outcomeSchema": {...} }]
        },
        "measured": { "width": 240, "height": 66 }
      },
      {
        "id": "{type}-{guid}",       // action 节点
        "name": "操作显示名",
        "type": "builtinFunction|m365Copilot|openApiConnection|...",
        "version": 1,
        "position": { "x": 566, "y": 271 },   // 按节点顺序递增 x，间距约 316px
        "data": {
          "config": { "operationId": "...", "parameters": {...}, ... },
          "outcomes": [{ "id": "default", "label": "Default", "outcomeSchema": {...} }]
        },
        "measured": { "width": 240, "height": 66 }
      }
    ],
    "edges": [
      { "id": "edge-{sourceId}-{targetId}", "source": "{sourceNodeId}", "target": "{targetNodeId}" }
    ],
    "connectionReferences": { ... },  // 同 flow 顶层 connectionReferences
  },
  "nodeActionMapping": {
    "{nodeId}": ["{actionName}"]      // node ID → definition.actions 中的 action 名
  }
}
```

**graph 推导规则**（从 definition 生成）：

**自动化脚本**：`scripts/definition_to_graph.py`（Python）可自动转换，用法：
```bash
python scripts/definition_to_graph.py <flow.json> -o <output.json> [--conn-refs <mapping.json>]
```
脚本会标记 `_needsAI=true` 的节点，AI 只需处理这些节点。

**Copilot Studio graph 与 Flow API 的关键格式差异**：

| 项目 | Flow API (clientdata) | Copilot Studio (graph) |
|---|---|---|
| connectionReferences | `connectionName` + `source` + `id` | `api.name` + `connection.connectionReferenceLogicalName` + `runtimeSource` |
| 普通 action node type | — | `connector`（不是 `openApiConnection`） |
| M365 Copilot node type | — | `m365Copilot` |
| Agent node type | — | `agent`（需要 `mode`/`botSchemaName`/`instructionsRich`） |
| Classify node | `PerformBoundAction` + GPT prompt | 原生 `classify`（`categories[]` + `inputRich` + `model`） |
| edges | — | 需要 `targetHandle: "input"`，classify 出口用 `category:{id}` 或 `default-category` |
| node config | — | 需要 `parametersSchema` + `outcomeSchema` + `iconUri` + `brandColor` |

### Graph node 类型对照表（AI 拼装 Workflow 时按需求选）

| 需求 | graph node `type` | 对应组件文件 | definition 层 host.operationId |
|---|---|---|---|
| 任意 OpenAPI 连接器操作（Office365 / SharePoint / Dataverse CRUD 等） | `connector` | `components/actions/openapi/shared_<connector>_<op>.json` | 同 operationId |
| 触发器：手动按钮 | `start` (子类 manual/button) | `components/triggers/request-button.json` | — |
| 触发器：来自 connector（如 OnNewEmail） | `start` (子类 connector) | 对应 trigger 组件文件 | 同 trigger operationId |
| 内置数据操作（Compose / ParseJson / Filter / Select / Join …） | `builtinFunction` | `components/actions/<name>.json` | 同 operationId |
| If / 条件分支 | `ifElse` | `components/actions/condition.json` | — |
| Switch / 多路分支 | `switch` | （内置） | — |
| Foreach 循环 | `foreach` | `components/actions/foreach.json` | — |
| **AI 分类邮件/文本到 N 个 category** | `classify` | `components/actions/openapi/shared_commondataserviceforapps_PerformBoundAction.json` (内联 GPT) | `PerformBoundAction` |
| **AI 处理任务、可挂 MCP / 工具、可结构化输出** | **`agent`** | **`components/actions/agent-node.json`** ← **优先用这个** | `InvokeDefinition` (mode=inline) or `InvokeAgent` (mode=invoke) |
| 触发 M365 Copilot（Office 文档总结等） | `m365Copilot` | `components/actions/openapi/shared_m365copilotv2_StartChat.json` | `StartChat` |

**重点提示**：

- `agent` 节点是 Copilot Studio Preview 引入的**画布原生节点**。它的 `data.config` 跟普通 `connector` 节点**完全不同**（含 `mode` / `inlineInstructions` / `inlineTools[]` / `simpleProperties` / `jsonSchema` / `instructionsRich` 等字段）。**永远从 `components/actions/agent-node.json` 取模板**，不要从 `shared_agentnode_InvokeDefinition.json` 凑（那个文件只描述 definition 层）。
- `agent` 节点 `mode=inline` 时 definition 走 `InvokeDefinition`；`mode=invoke`（引用现有 agent）走 `InvokeAgent`。
- `outputMode=structured-simple` 时下游 If/Switch 表达式直接用 `body('NodeName')?['structuredOutput/<field>']`，**不需要 ParseJson + int() 转换**（v6 已验证）。

**组件文件中的 `graphConvertible` 字段**：
- `true` — 脚本可自动转换（connector / m365Copilot / built-in）
- `"partial"` — 结构可转但需要 AI 处理内容（classify 提取 categories、agent 解析 instructionsRich）

**`connectionReferenceLogicalName` 获取方式**：
查 Dataverse `connectionreferences` 表，按 `connectionid` 匹配：
```
GET .../api/data/v9.2/connectionreferences?$select=connectionreferencelogicalname,connectorid,connectionid
```

**转换流程**：
1. AI 生成 definition（clientdata）后，调 `definition_to_graph.py` 生成 graph
2. 脚本输出标记 `_needsAI` 的节点 → AI 只处理这些节点（填 categories/instructionsRich）
3. 合并后 PATCH 到已部署的 flow

### 部署防护（2026-05-27 踩坑 — 重复创建）

**POST 部署 flow 时，即使返回 400/404 错误，flow 可能已经被创建了。**

防护措施：
- **不要盲目重试** POST — 错误可能是 connectionReference 验证失败，但 flow 已经创建
- 遇到 POST 错误时，**等 5 秒后查询** `GET .../flows?$orderby=properties/createdTime desc&$top=3`，检查是否已有同名 flow
- 有同名 flow → 用 PATCH 修复，不要再 POST
- 没有 → 修复 JSON 后重试 POST

### PATCH Flow 注意事项（2026-05-27 踩坑）

- PATCH 时 definition 中每个 action 的 `host` 节点必须包含 `connectionReferenceName`（GET 返回的定义只有 `connectionName`，PATCH 时需要补上）
- `connectionReferenceName` 的值 = `connectionReferences` 对象中的 **key 名**（如 `shared_sharepointonline`），不是 `connectionReferenceLogicalName`
- PATCH body 必须同时包含 `definition` 和 `connectionReferences`
- `connectionReferences` 中每个条目需要：`connectionName`（connection ID）、`source: "Embedded"`、`id`（API path）

## Flow 排查步骤

1. 查看 run history: `GET .../flows/{flowId}/runs`
2. 找到失败的 run → 查看 actions: `GET .../runs/{runId}/actions`
3. 定位失败的 action → **通过 repetitions 端点获取 inputs/outputs**
4. 修复 flow 定义 → PATCH 更新 → resubmit 验证

### 获取 Action 的 inputs/outputs（2026-05-27 发现）

直接 `GET .../actions/{actionName}` 不返回 inputsLink/outputsLink。
**必须通过 repetitions 端点**：
```
GET .../runs/{runId}/actions/{actionName}/repetitions?api-version=2016-11-01
```
返回的每个 repetition 包含 `properties.outputsLink.uri`（有时也有 `inputsLink.uri`）。
用该 URI 的值直接 `GET`（无需 Authorization header，URL 自带 SAS token）即可获取完整 inputs/outputs JSON。

**注意**：`inputsLink` 有时为 null，此时无法通过 API 看到 action 的输入参数。

## Resubmit Flow

```
POST .../flows/{flowId}/triggers/{triggerName}/histories/{runId}/resubmit?api-version=2016-11-01
Body: {}
```
- 返回 202 Accepted 表示成功
- triggerName 通常是 flow definition 中 triggers 对象的 key 名

## 已部署 Flow 状态

| Flow | ID | 状态 |
|---|---|---|
| Test-List Top5 to Teams | `282debe2-636f-771c-9fe6-7532ba610292` | Started ✅ |
| Test-List Grouped Email Report | `8aab0abd-052d-b5f8-8b33-92c346e8055a` | Started ✅ |
| Smart Invoice v3.1 (AsyncV2 Fixed) | `8722e7ed-c011-3ecd-0c02-86da70be7fa9` | Started（Agent PDF 问题） |
| Smart Invoice v2 (Multimodal) | `cb1cfb73-1f28-11fc-c728-1f59852defd0` | Started |

## Host 节点格式规则（从 connector-prerequisites 合并）

clientdata 中 `host` 节点必须用 `connectionName`，**不是** `connection`：
```json
✅ "host": { "apiId": "...", "operationId": "...", "connectionName": "shared_sharepointonline" }
❌ "host": { "apiId": "...", "operationId": "...", "connection": "shared_sharepointonline" }
```
Power Automate Code View 有时显示 `connection`，但 clientdata 写入必须用 `connectionName`。

## SharePoint 触发器 folderId 编码规则

`OnNewFile` 触发器的 `folderId` 需要**双重 URL 编码**：
- `/` → `%252f`，空格 → `%2b`
- 在 `metadata` 中加映射：编码路径 → 人类可读路径

## 已知限制 & 踩坑记录

### Copilot Studio Agent 附件限制（2026-05-27 确认）

ExecuteCopilotAsyncV2 connector 的 `body/attachments[].contentUrl` 参数：
- Agent **不会**主动通过 contentUrl 去下载文件
- Agent **需要** SharePoint/OneDrive 的**分享链接格式**（如 `/:b:/g/...?e=...`）才可能读到文件
- 即使 contentUrl 指向有效的 SharePoint 文件路径（如 `https://sharepoint.com/sites/.../file.pdf`），Agent 仍然回复 "Please upload the PDF"
- 从学习到的真实 flow 模板看，成功的 contentUrl 使用的是 OneDrive **分享链接** URL 格式
- 要解决此问题，可能需要在 Copilot Studio 中给 Agent 配置 SharePoint 作为知识源，或使用 Direct Line API 传文件

### SharePoint CreateFile 输出字段（2026-05-27 确认）

`body` 实际包含的属性（通过 repetitions API 验证）：
- `Path` — 服务器相对路径（如 `/Shared Documents/temp_xxx.pdf`）
- `Name` — 文件名
- `Id` — URL 编码的路径标识
- `FileLocator` — base64 编码的 dataset + id
- `DisplayName`, `ETag`, `IsFolder`, `ItemId`, `LastModified`, `MediaType`, `Size`
- **`{Link}` 为空（null）** — 不可用！不要引用此字段

### Action 输出字段验证规则（2026-05-27 教训）

在 flow 中引用 action 的输出字段之前，**必须先查 Swagger 或通过 repetitions API 查看实际输出**，验证字段名和值。
不要凭猜测使用 `body/{Link}` 等动态属性名——很可能返回 null。

### shared_agentnode/InvokeDefinition 输出双形态（2026-06-04 确认）

**同一个 connector + 同一个 operationId，同一个 flow 里两个 Agent 节点输出 shape 不一致**：
- 同步返回（一般场景）：`body = { conversationId, status, result }` ← `result` 是 JSON 字符串，几 KB
- 流式返回（触发条件未明，可能与 model/prompt 长度有关）：`body = { message, activities }` ← `message` 才是最终 JSON，`activities` 含 100+ streaming chunks，可达 100+ KB

**修法**：Parse 节点 content 用 coalesce 兜底：
```
@{coalesce(body('Agent_Node')?['result'], body('Agent_Node')?['message'])}
```

**踩坑案例**：V5 Service Email Workflow 的 `Return_Agent_Query` 走流式、`Tech_Assistance_Agent` 走同步，同样表达式 `?['result']` 在 Return 分支永远 null，Parse 报 `content expects value but got null`。

### ParseJson schema=string 时数值比较必须 int() 转换（2026-06-04）

ParseJson 节点 schema 里把数值字段写成 string 示例（如 `"orderAmount":"123"`），Parse 出来的就是 string 类型。If/Switch 节点用 `lessOrEquals` / `less` 等数值比较时**必须显式转换**：
```
@less(int(body('Parse_Agent_Response')?['orderAmount']), 200)
```
不转直接比较 → 字符串字典序比较（`"1299" < "200"` 为 true），逻辑全错。

### Dataverse salesorder/invoice 的 totalamount 写入坑（2026-06-04）

`salesorders` / `invoices` / `quotes` 表的 `totalamount` 是 rollup-like 字段：
- POST 创建时即使 body 带 `totalamount: 129.99`，记录建出来仍是 0
- **必须 PATCH 二次写入**才能持久化
- 同理 `totaltax` / `totalamountlessfreight` / `totallineitemamount` 都有这个行为

### Dataverse overriddencreatedon 在新建时生效（2026-06-04 确认）

跟一般认知相反：**新建 record 时 body 里带 `overriddencreatedon: "2026-06-01T..."` 是会生效的**，会把 `createdon` 字段反向设置成这个时间。用来造历史测试数据非常有用（如造"3 天前"的订单）。
- 字段格式：ISO 8601
- 限制：只能往**过去**回溯，不能设未来

### Flow Management API $top 上限 50（2026-06-04）

`GET .../flows?api-version=2016-11-01&$top=200` → 400 `InvalidTopInQueryString`。
Flow Mgmt API 的 `$top` 上限是 **50**，不是常见的 100/200。要更多记录用 `$skiptoken` 翻页。

### Dataverse EntityDefinitions 不支持 startswith 过滤（2026-06-04）

`GET /EntityDefinitions?$filter=startswith(LogicalName,'msdyn_approv')` → 400 `The "startswith" function isn't supported for Metadata Entities`。
**解法**：GET 全表 `?$select=LogicalName,EntitySetName` 再客户端 `Where-Object` / `filter` 过滤。

### Approvals API 必带 assignedTo/id filter（2026-06-04）

```
GET /providers/Microsoft.ProcessSimple/environments/{envId}/approvalRequests?api-version=2016-11-01
```
不带 `$filter` → 400 `A $filter query specifying properties/assignedTo/id is required`。
正确：
```
?$filter=properties/assignedTo/id eq '{userObjectId}' and properties/status eq 'Active'
```
`userObjectId` 从 Graph `GET /me` 拿。

### Advanced Approvals 不发 Outlook 邮件（2026-06-04 ⚠️ 重要）

`shared_advancedapprovals` connector 的 `RequestForInformation` 操作 ≠ 标准 `shared_approvals`。Advanced Approvals **不通过 Outlook 邮件**送审批 Adaptive Card：
- ❌ Outlook inbox 没有 "Tech Reply Review" 邮件
- ❌ Outlook Junk / Other tab 没有
- ❌ Power Automate Approvals 页面（`make.powerautomate.com/.../approvals/received`）也看不到（那里只显示标准 Approvals）
- ❌ Dataverse `msdyn_flow_approvalrequest*` 表不存这个（那是标准 Approvals 的表）
- ✅ **审批通过 Teams Approvals app 或 Adaptive Card webhook 推送**

**生成 flow 时的影响**：
- 如果要 AI/API 端到端测试 → **不要用 Advanced Approvals**，用标准 `shared_approvals/StartAndWaitForAnApproval` 才能在 Outlook 收审批 + 可通过 API 自动响应
- 如果客户场景必须用 Advanced Approvals → 测试时必须人工去 Teams 点

**已知未解**：Advanced Approvals 的 RFI 请求存在哪个表 / 怎么通过 API 响应 — 暂未找到。

### 测试发邮件触发 Flow：禁止同账号自发自收（2026-06-04）

Office 365 Outlook trigger `OnNewEmailV3` 监听目标 inbox 新邮件：
- ❌ 用目标账号自己给自己发邮件 → trigger 不一定触发（同账号同 mailbox 的内部 message 可能不计为 "new email"）
- ✅ 用**同租户的另一个账号**或**外部邮箱**发，trigger 稳定触发

### Power Automate Approvals 页面 URL 必须带 envId（2026-06-04）

`https://make.powerautomate.com/approvals/received` 默认进 tenant default 环境（Contoso default），看不到其他环境的 approvals。
**正确**：
```
https://make.powerautomate.com/environments/{envId}/approvals/received
```

### 测试 Agent 时邮件正文禁止硬编码 Agent 应自查的数据（2026-06-04 用户偏好）

发测试邮件时，**不要在正文里写金额、日期、订单号等 Agent 应该从 Dataverse 自查的数据**。否则无法验证 Agent 是真的通过 MCP 查数据，还是从邮件正文直接抄。

正确写法：邮件只描述"我要退某个产品"或"我有什么问题"，让 Agent 自己从发件人邮箱 → account → salesorder/incident 全链路查。
