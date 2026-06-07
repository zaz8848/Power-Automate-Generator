---
name: scan-environment
description: |
  扫描某个 Power Platform 环境，列出 flow / connector / connectionReference，
  可选 "学习" 模式批量调用 /learn-component。
  用户说"扫环境"/"scan environment"/"list flows"/"看看这个 env 有什么"时使用。
applyTo: '**'
---

# /scan-environment — 环境扫描 SOP

---

## 触发条件

- 用户说 "扫环境 / scan environment / list flows"
- 用户说 "看看 <envName> 有什么 flow"
- 用户说 "学习这个环境所有 flow"（→ 进入"学习模式"）

---

## 输入

- `<envName>` 或 `<envId>`（不给则用当前默认环境）
- 模式：`list`（默认） / `learn`（批量学组件）

---

## 执行步骤

### Step 1 — 解析环境

```powershell
$envs = Get-Content "environments.json" -Raw | ConvertFrom-Json
$env = $envs | Where-Object { $_.displayName -eq $envName -or $_.id -eq $envId }
```

如果 `environments.json` 不存在或没匹配 → 报告并提示 `/configure-profile`。

### Step 2 — 拉 token

```powershell
.\scripts\_get_tokens.ps1
# 产出 $dvToken / $flowToken / $graphToken / $powerappsToken
```

### Step 3 — 列 flows

```powershell
# Flow Management API
$flows = Invoke-RestMethod -Uri "https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/$($env.id)/flows?api-version=2016-11-01&`$top=50" -Headers @{Authorization="Bearer $flowToken"}
```

**⚠️ 已知坑**：`$top` 上限 50，多于此数要分页。

### Step 4 — 列 connectionReferences（Dataverse）

```powershell
$crefs = Invoke-RestMethod -Uri "$($env.dataverseUrl)/api/data/v9.2/connectionreferences?`$select=connectionreferencelogicalname,connectorid,connectionreferencedisplayname" -Headers @{Authorization="Bearer $dvToken"}
```

### Step 5 — 输出报告

```markdown
**环境**: <envName> (id: ..., dataverse: ...)

**Flows** (N 条):
| # | DisplayName | Type | State | FlowId |
|---|---|---|---|---|

**ConnectionReferences** (M 条):
| LogicalName | Connector | DisplayName |
|---|---|---|

**Connectors in use** (K 个，去重):
- shared_office365
- shared_commondataserviceforapps
- ...
```

### Step 6 — 学习模式（可选）

如果用户进入 `learn` 模式：

1. 对每个 flow 拉 `definition`（GET `/flows/{flowId}?$expand=...`）
2. 遍历 triggers + actions，每个 connector+operationId 调 `/learn-component`
3. 汇总报告：新增 X 个组件，跳过 Y 个已存在

**对于 Workflow 类型**：额外拉 `associatedData.graph`，学新的 graph node config 模板。

---

## 输出落盘

- 扫描结果 → 临时写到 `_scan_<envName>_<date>.json`（带 `_` 前缀，不进 git）
- 学到的组件 → 直接更新 `components/` + `_catalog.json`
- **不要**把 flow definition 永久落 `flows/` 目录（除非用户明确要"学习这个 flow 的部署形态"）

---

## 成功标志

- [ ] 列出全量 flow 数 + connector 数 + connectionRef 数
- [ ] learn 模式下报告新增 / 跳过的组件数
- [ ] 无 token 失效 / 403 错误

---

## 禁止事项

- ❌ DELETE 任何 flow（项目硬约束）
- ❌ DELETE 任何 connectionReference
- ❌ 把扫描结果直接同步到 DevTool（含敏感数据，必须先脱敏）
- ❌ 用 `contains` 模糊匹配 Dataverse 字段

---

## 后置动作

- 学完一批组件 → 提示 `/sync-to-devtool`
- 发现 flow 失败 run → 提示用户是否查 run 详情（用 `scripts/_run_detail.ps1` 等调试工具，**不属于本 skill 范围**）
