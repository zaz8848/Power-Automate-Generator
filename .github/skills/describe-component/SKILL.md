---
name: describe-component
description: |
  在创建任何 flow 节点之前，先查组件库，输出该 component 的完整契约
  （inputSchema / outputSchema / 已知坑 / graphTemplate）。
  用户说"查组件 X"/"describe component"/"这个 operation 怎么用"时使用，
  /create-flow 在 Step 2 必须对每个节点调用本 skill。
applyTo: '**'
---

# /describe-component — 组件查询 SOP

> 用途：**禁止 AI 凭记忆编 connector 参数**。所有节点参数必须从组件库读，找不到就跑 `/learn-component`。

---

## 触发条件

- 用户说 "查组件 X" / "describe component X"
- 用户说 "这个 operation 怎么用 / 有哪些参数"
- `/create-flow` 在 Step 2 对每个节点自动调用本 skill

---

## 输入

任一即可：
- `<componentId>`（如 `shared_office365_GetEmailsV3`）
- `<connector>` + `<operationId>`（如 `shared_office365` + `GetEmailsV3`）
- 内置类型名（如 `Compose` / `If` / `Switch` / `Foreach`）

---

## 执行步骤

### Step 1 — 优先在组件库找

```powershell
# 1) OpenAPI action
$file = "components\actions\openapi\<connector>_<operationId>.json"

# 2) 内置 action
$file = "components\actions\<type>.json"   # compose.json / condition.json ...

# 3) Trigger
$file = "components\triggers\<connector>_<operationId>.json"

if (Test-Path $file) { Get-Content $file -Raw | ConvertFrom-Json }
```

### Step 2 — 输出结构化报告

````markdown
**Component**: `shared_office365_GetEmailsV3`
**Type**: `OpenApiConnection`
**Verified**: ✅ (learnedFrom: <flowId>, learnedAt: 2026-05-26)

**inputSchema** (必填 / 可选):
| 参数 | 类型 | 必填 | 示例 | 说明 |
|---|---|---|---|---|
| folderPath | string | ✅ | "Inbox" | 邮件文件夹路径 |
| fetchOnlyUnread | boolean | ❌ | true | 仅未读 |

**outputSchema**: { "value": [{ id, subject, body, from, to, ... }] }

**已知踩坑**:
- 某某参数为空会 500
- ...

**graphTemplate** (Workflow 用):
```json
{ "type": "openApiConnection", "data": { "config": {...} } }
```

**clientdata 模板**:
```jsonc
"<NodeName>": {
  "type": "OpenApiConnection",
  "inputs": { ... },
  "runAfter": { ... }
}
```
````

### Step 3 — 找不到时

**禁止 AI 凭记忆编**，必须：

1. 报告 "❌ 组件库无此 component"
2. 提示用户：`/learn-component shared_<connector> <operationId>` 学完再用
3. 列出**相近**组件供用户对照（用 `_catalog.json` 搜 connector 下所有 operationId）

---

## 成功标志

- [ ] 组件查到并输出全部 4 块（inputSchema / outputSchema / 已知坑 / clientdata 模板）
- [ ] 或明确报告 "未找到，请先 /learn-component"

---

## 禁止事项

- ❌ 找不到组件就编 schema（哪怕"看起来就该这样"）
- ❌ 用 connector 显示名搜索（必须用 `shared_*` 规范名）
- ❌ 输出未经组件库验证的"经验性"参数

---

## 数据来源

- `components/_catalog.json` — 全量索引
- `components/actions/openapi/*.json` — 113 个 OpenAPI action
- `components/actions/*.json` — 17 个 built-in
- `components/triggers/*.json` — 21 个 trigger
- `components/connectors/*.json` — 29 个 connector（含 swaggerUrl）
