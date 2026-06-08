---
name: scan-environment
description: |
  扫描 Power Platform 环境，列 flow / connector / connectionReference，
  或批量拉所有环境的 Workflow 并自动 merge graph node 模板到组件库。
  用户说"扫环境"/"scan environment"/"list flows"/"扫所有环境"/"学一下我现在的 workflow"时使用。
applyTo: '**'
---

# /scan-environment — 环境扫描 SOP

支持 3 种模式，跟用户确认要哪一种再执行。

---

## 触发条件

- 用户说 "扫环境 / scan environment / list flows"
- 用户说 "看看 <envName> 有什么 flow"
- 用户说 "扫所有环境的 workflow / scan all environments"
- 用户说 "学一下我现在所有的 workflow / merge graph templates"

---

## 3 种模式

| 模式 | 触发语 | 做什么 | 风险 |
|---|---|---|---|
| `list` | 默认；"列 flow / list flows / 看看 <env>" | 单环境拉 flow + connector + connectionRef 列表 | 只读 |
| `scan-all-workflows` | "扫所有环境 / scan all envs / 批量拉 workflow" | 32 环境全扫，拉 Workflow（category=5 且 modernflowtype=1）落到 `flows/{envSlug}/workflow/_scan_*.json` | 只读 |
| `learn-graph-templates` | "学 graph / merge graph templates / 补 graphTemplate" | 解析所有本地 workflow JSON，按 `(type, apiName, operationId)` merge 到 `components/` 对应文件的 `graphTemplate` | 写组件库 |

3 种模式可串联：先 `scan-all-workflows` 收数据，再 `learn-graph-templates` merge。

---

## 共同前置

```powershell
# 1. profile 文件必须存在（否则跑 /configure-profile）
$profile = Get-Content "profiles/<tenant>.json" -Raw | ConvertFrom-Json
$envs    = $profile.environments    # schema v2: 环境列表在 profile 里

# 2. profile.refreshToken 必须不是 "TODO"（否则跑 /configure-profile 走 OAuth）
```

> **lab 内部可选**：如果项目根目录有 ``environments.json``（lab 通过其它途径拉的全租户环境总清单），模式 2 ``scan-all-workflows`` 可以扫这个清单的所有环境（即使不在 profile.environments[] 里）。**外部用户场景下永远以 profile.environments[] 为准**。

---

## 模式 1：`list`（单环境）

### Step 1 — 解析环境

```powershell
$envName = $EnvNameOverride ?? $profile.defaultEnvironment
$env     = $profile.environments | Where-Object { $_.name -eq $envName } | Select-Object -First 1
$orgUrl  = $env.dataverseUrl.TrimEnd('/')
$envId   = $env.environmentId
```

### Step 2 — 刷 Dataverse token

```powershell
$dvToken = (python scripts/configure_profile.py "profiles/<tenant>.json" --env $envName --get-token)[-1]
```

详见 `.github/instructions/token-management.instructions.md`。

### Step 3 — 拉数据

```text
GET {orgUrl}/api/data/v9.2/workflows
    ?$filter=category eq 5
    &$select=workflowid,name,modernflowtype,statecode,createdon
    &$top=200

GET {orgUrl}/api/data/v9.2/connectionreferences
    ?$select=connectionreferencelogicalname,connectorid,connectionreferencedisplayname
    &$top=200
```

### Step 4 — 输出报告

```
环境: <envName> (orgUrl: <orgUrl>)
Workflows  (M 条, modernflowtype=1)
普通 Flow  (N 条, modernflowtype 非 1)
ConnectionReferences (K 条)
Connectors in use (去重后)
```

**不**永久落盘到 `flows/`，只在 chat 展示。如果用户说"把这个学了"，再走模式 2 或 `/learn-component`。

---

## 模式 2：`scan-all-workflows`（32 环境批量）

直接调脚本：

```powershell
# 默认：用 profile.environments[]（或 lab 根目录 environments.json 如存在）
python scripts/scan_all_envs.py profiles/<tenant>.json

# 只扫单个 env
python scripts/scan_all_envs.py profiles/<tenant>.json --env "ZAF Prod"

# 显式指定 env 来源文件
python scripts/scan_all_envs.py profiles/<tenant>.json --envs-file my-envs.json
```

脚本行为：
- 遍历环境源：**优先**拼 lab 项目根目录的 `environments.json`（如存在，含 lab 查到的所有环境）；**否则 fallback** 到 `profile.environments[]`
- 对每个环境刷一次 scope 为 `{orgUrl}/user_impersonation offline_access` 的 access_token
- GET `workflows?$filter=category eq 5 and modernflowtype eq 1&$top=200`
- 跳过 `[AutoGen]` / `[TO-DELETE]` 前缀的 flow（项目硬约束）
- 落到 `flows/{envSlug}/workflow/_scan_{workflowid}.json`
- 最终打印 SUMMARY 表（每个环境 total / saved + 前 5 个名字）

### 注意
- `_scan_*.json` 是临时模式（`.gitignore` 已覆盖 `*.tmp.json` 等；如要持久化由用户决定）
- token 在脚本里**滚动刷新**（每次用上一次的 refresh_token 换新的）
- 任一环境失败 → `[skip env]` 并继续下一个，不中断

---

## 模式 3：`learn-graph-templates`（merge 到组件库）

```powershell
# 先 dry-run 看覆盖
python scripts/extract_graph_templates.py

# 确认后写
python scripts/extract_graph_templates.py --apply
```

脚本行为：
- 扫 `flows/{env}/workflow/*.json`（跳过 `_save_capture_*` 和 `_live_*`）
- 跳过 `[AutoGen]` / `[TO-DELETE]` 前缀的 flow
- 对每个 graph node，按 `(type, apiName, operationId)` 聚合
- 匹配到 `components/` 下对应文件
- `--apply` 时**只**给 `graphTemplate` 字段缺失且 `graphTemplateVerified != true` 的组件补上 merged 模板
- 永远不覆盖 `graphTemplateVerified=true` 的（手抓最准）

### 输出

```
matched X (type, op) combos to component files
APPLIED graphTemplate to N component files
NO MATCH 列表 — 提示 /learn-component
```

NO MATCH 的组件需要手工跑 `/learn-component` 单独学。

---

## 成功标志

- [ ] 模式 1：用户拿到单环境清单
- [ ] 模式 2：SUMMARY 显示有 saved>0 的环境
- [ ] 模式 3：APPLIED / NO MATCH 列表清晰，组件库写入符合预期

---

## 禁止事项

- ❌ DELETE 任何 flow（项目硬约束）
- ❌ DELETE 任何 connectionReference
- ❌ 把 `_scan_*.json` / `flows/` 直接同步到 DevTool（含 connection ID 等敏感数据）
- ❌ 用 `contains` 模糊匹配 Dataverse 字段
- ❌ 模式 3 跑 `--apply` 时覆盖 `graphTemplateVerified=true` 的组件
- ❌ 扫描期间硬编码任何环境的 orgUrl / envId（一律从 `profile.environments[]` 读；lab 内部可选 fallback `environments.json`）

---

## 后置动作

- 模式 2 完成 → 提示用户跑模式 3（merge）
- 模式 3 完成 → 提示用户跑 `/sync-to-devtool` 把更新脱敏推到公开仓
- 发现 NO MATCH → 提示用户对每个调 `/learn-component`
