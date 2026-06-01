---
name: flow-operations
description: Flow 创建/修改/排查/Resubmit 的完整 API SOP — 确保 AI 用正确的 API 和参数操作 Flow
applyTo: "**"
---

# Flow 操作 SOP

## API 端点参考

| 操作 | 方法 | 端点 | Token scope |
|---|---|---|---|
| **创建 flow** | POST | `https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/{envId}/flows?api-version=2016-11-01` | `service.flow.microsoft.com` |
| **修改 flow** | PATCH | 同上 `/{flowId}` | 同上 |
| **查询 flow 列表** | GET | 同上 `/flows?api-version=2016-11-01` | 同上 |
| **查看 flow 详情** | GET | 同上 `/{flowId}?api-version=2016-11-01` | 同上 |
| **查看 run history** | GET | 同上 `/{flowId}/runs?api-version=2016-11-01` | 同上 |
| **查看 run action** | GET | 同上 `/{flowId}/runs/{runId}/actions?api-version=2016-11-01` | 同上 |
| **Resubmit run** | POST | 同上 `/{flowId}/triggers/{triggerName}/histories/{runId}/resubmit?api-version=2016-11-01` | 同上 |
| **读 Dataverse workflow** | GET | `https://{dataverseOrg}/api/data/v9.2/workflows({workflowid})` | `{dataverseOrg}` |
| **查 connectionReference** | GET | `https://{dataverseOrg}/api/data/v9.2/connectionreferences` | 同上 |

## 环境 ID

环境 ID 存储在各租户的 profile JSON 中（`profiles/{profileName}.json` 的 `environmentId` 字段）。

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

#### Phase 6：部署

19. **获取 token** — `scope: https://service.flow.microsoft.com/.default offline_access`（从 `.token-cache.json` 刷新）
20. **POST 部署** — `POST .../environments/{envId}/flows?api-version=2016-11-01`
    - 读文件用 `[System.IO.File]::ReadAllBytes()` 避免编码损坏
    - Header: `Content-Type: application/json; charset=utf-8`
21. **部署防护** — POST 返回 400/404 时**不要盲目重试**，先查 `GET .../flows?$orderby=properties/createdTime desc&$top=3` 检查是否已创建
22. **Copilot Studio Plan 切换**（仅 Workflow）：
    - 从 flow 详情获取 `workflowEntityId`
    - 获取 Dataverse token（scope: `https://{dataverseOrg}/user_impersonation offline_access`）
    - `PATCH .../api/data/v9.2/workflows({entityId})` body: `{"modernflowtype": 1}`

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
PATCH https://{dataverseOrg}/api/data/v9.2/workflows({workflowEntityId})
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

此表由各项目自己的 `flow-dictionary.json` 维护，不在公共仓库中记录。

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
