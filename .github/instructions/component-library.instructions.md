---
name: component-library
description: 组件库学习/查询/生成 SOP — 引导 AI 到正确的组件文件
applyTo: "**"
---

# 组件库操作 SOP

## 组件库位置

组件模板数据存放在 `components/` 目录下：
- `components/connectors/` — 连接器定义（每个连接器一个 JSON）
- `components/triggers/` — 触发器模板
- `components/actions/` — action 模板（按类型和连接器分）
- `components/patterns/` — 多步骤组合模式
- `components/_catalog.json` — 全局索引（所有已学习组件的汇总）

## 命令路由

### 学习命令

| 用户说 | AI 动作 |
|---|---|
| "学习 flow `<名称/ID>`" | 1. 通过 Flow Management API 读该 flow 的 definition → 2. 拆解 triggers/actions/connectionReferences → 3. **从 Swagger 提取每个 operationId 的 input/output schema** → 4. 新增/更新 `components/` 下对应文件（含 schema） → 5. 更新 `_catalog.json` → 6. 汇报结果 |
| "学习当前环境所有 flow" | 遍历所有 category=5 workflow → 逐个执行上述学习流程 → 批量汇报 |
| "我做了一个新 flow，你来学" | 用户提供 flow 名或 ID → 同上 |
| "更新组件 `<组件名>`" | 用户提供修正 → 更新 `components/` 对应文件 |

**学习 Workflow 类型**：
学习命令对 Workflow 和普通 flow 通用。区别在于 Workflow 的 clientdata 中某个 trigger 的 `metadata.associatedData.graph` 包含编排画布信息（nodes/edges/connectionReferences/nodeActionMapping）。学习时：
1. 同样拆解 triggers/actions/connectionReferences → 学习组件（与普通 flow 一致）
2. **额外保存** `associatedData.graph` 结构到 flow JSON（存入 `flows/{env}/workflow/`），作为 Workflow 生成的参考模板

**注意**：Workflow 的触发器名**不固定**（可以是 `manual`、`________` 或其他名称），检测时必须遍历所有 trigger 的 `metadata.associatedData.graph`，不能只查 `triggers.manual`。

**Dataverse 优先**：通过 Flow API (`GET .../flows`) 只能看到当前用户有权限的 flow。要查其他用户创建的 flow，必须通过 Dataverse Web API (`GET .../workflows`) 查询。

### 查询命令

| 用户说 | AI 动作 |
|---|---|
| "这个组件/操作是什么？`<名称>`" | 查 `components/_catalog.json` → 找到则读对应文件并解释 → 没找到则提示"未学习" |
| "有哪些已学习的组件？" | 读 `components/_catalog.json` → 列出所有已学习的连接器/触发器/action |
| "XX 连接器支持哪些操作？" | 读 `components/connectors/<connector>.json` → 列出 operations |

### 生成时的组件库查询

生成 flow 时，AI 必须先查组件库：
1. **先确认类型** → 问用户："生成普通 Power Automate flow 还是 Workflow？"（如果用户没明确说）
2. 解析用户需求 → 确定需要哪些 trigger/action
3. 读 `components/_catalog.json` 查找匹配组件
4. **有** → 读对应 JSON 文件获取模板 → 填入参数
5. **没有** → 问用户："我没学过 `<操作名>` 这个组件，你能指给我一个用了它的 flow 吗？学习后我就能用了。"
6. **如果是 Workflow** → 除了生成 `definition`，还需生成 `associatedData.graph`（见 flow-operations SOP）

## 组件文件格式

每个组件 JSON 文件的标准结构见 `PROJECT_BLUEPRINT.md` §3.2。

关键字段：
- `id` — 唯一标识
- `connector` — 所属连接器
- `operationId` — API 操作 ID
- `type` — action 类型（OpenApiConnection / Compose / If / Foreach / Query 等）
- `learnedFrom` — 来源 flow 的 workflowid
- `template` — clientdata 片段模板（可直接嵌入生成的 clientdata）
- `parameters` — 参数定义 + 示例值
- `inputSchema` — 从 Swagger 提取的输入参数 schema（必须有）
- `outputSchema` — 从 Swagger 提取的输出 response schema（必须有）
- `swaggerLearned` — 是否已从 Swagger 提取过 schema（true/false）
- `verified` — 是否已在真实 flow 中验证
- `graphConvertible` — clientdata→graph 可转换性（`true` / `"partial"` / `false`）
- `graphNodeType` — 对应的 Copilot Studio graph node type（`connector` / `m365Copilot` / `agent` / `classify` / `builtinFunction` 等）
- `graphNotes` — graph 转换时的注意事项（仅 partial 组件有）

## Swagger Schema 提取规则（2026-05-27 新增）

学习 OpenAPI connector action 时，**必须同步从 Swagger 提取 input/output schema**：

1. 获取 Swagger: `GET api.powerapps.com/providers/Microsoft.PowerApps/apis/{connector}?$select=properties.swagger`（或用 connector 文件中的 `swaggerUrl`）
2. 在 Swagger 的 `paths` 中找到 `operationId` 对应的路径
3. 提取 `parameters`（输入参数定义）和 `responses.200.schema`（输出 schema）
4. 存入组件文件的 `inputSchema` 和 `outputSchema` 字段

**为什么必须做这一步**：
- 生成 flow 时引用 action 输出字段（如 `outputs('xxx')?['body/Path']`），必须基于 schema 确认字段名存在
- 2026-05-27 踩坑：引用了 SharePoint CreateFile 不存在的 `body/{Link}` 字段，导致 contentUrl 为空

## 写入约束

- 组件库文件只通过学习 SOP 更新，不手动编辑
- 每次学习完成后必须更新 `_catalog.json`
- 同一个 `connector + operationId` 的组件不重复创建，只更新
