---
name: report-issue
description: |
  当用户在使用 Power-Automate-Generator 的 skill / 组件库 / instructions 时
  遇到问题、踩坑、不准确、想提建议，用这个 skill 把反馈写到 **工具库仓里
  `feedback/` 文件夹下、以「当前使用它的消费方项目名」命名的那个反馈文件**
  （如 `feedback/Echo-Service.md`）。追加式，每个消费方项目一个文件。
  维护方（lab）定期用 `/triage-feedback` 归集这些文件做 triage。
applyTo: '**'
---

# /report-issue — 反馈到工具库 feedback/{项目名}.md SOP

> **核心约束**：本 skill 只往**工具库仓**的 `feedback/{消费方项目名}.md`
> **append** 一条反馈。不发外网请求、不上传用户数据、不改工具库的
> skills / components / instructions 本身（那是维护方 triage 后才做的）。
> 每个消费方项目一个文件，可反馈 N 次，永远追加到同名文件。
>
> **前提（方案 A）**：消费方本地必须有工具库仓的**可写 clone**（不是只通过
> `chat.agentSkillsLocations` 远引用）。定位工具库根 = 本 skill 文件所在目录
> 向上三级（`.github/skills/report-issue/SKILL.md` → 工具库根）。
> 若工具库不可写，退回让用户手动把反馈粘给维护方。

---

## 触发条件

- 用户说 "report issue" / "反馈一下 / 报个 bug / 这个 skill 不对 / 这个组件不准"
- ``/create-flow`` / ``/describe-component`` / ``/learn-component`` /
  ``/scan-environment`` 跑挂时，AI 主动建议用 ``/report-issue``

---

## 执行步骤

### Step 1 — 收集上下文

让 AI 主动收集（无需用户重复输入）：

- 当前触发的 Power-Automate-Generator skill / instruction 文件名
- 涉及的 component / connector / operationId（如果是组件问题）
- 实际错误信息（API status + 简短 message，**不要带 token / connection id /
  envId / orgUrl**）
- 你做了什么操作（一两句话）
- 期望 vs 实际

### Step 2 — 强制脱敏自检

写入前**必须**扫描一遍要落盘的文本，禁止包含：

- 任何 ``Bearer `` token / refresh_token / authorization code
- ``client_secret`` / ``connection_id``
- 完整 ``orgXXXXX.crm*.dynamics.com`` URL（保留 connector / operationId 即可）
- 个人邮箱 / 用户全名 / 租户 ID GUID
- 真实数据（订单号 / 客户名 / 邮件正文）

如果发现敏感数据：替换为 ``<redacted-xxx>`` 占位符并提醒用户复核。

### Step 3 — 追加到工具库 feedback/{项目名}.md

1. **定位工具库根**：本 skill 文件所在目录向上三级
   （`.github/skills/report-issue/` → 工具库根）。
2. **取消费方项目名**：当前消费方 workspace 的根文件夹名（如 `Echo-Service`）。
3. **组合路径**：`{工具库根}/feedback/{消费方项目名}.md`。

如果该文件不存在，先创建并写入文件头（仅一次）：

```markdown
# {消费方项目名} — Power-Automate-Generator 反馈日志

> 本文件记录 **{消费方项目名}** 项目使用 Power-Automate-Generator 时的反馈。
> 由 ``/report-issue`` skill 追加维护，永不删除历史。
> 已脱敏（无 token / connectionId / orgUrl / 个人邮箱 / 租户 GUID）。

```

然后**追加**一条 entry，格式固定：

```markdown

---

## {ISO 日期时间, 如 2026-06-07T11:35:00+08:00}

**Skill / Instruction**: `/create-flow` （或 `flow-operations.instructions.md` 等）
**Component**: `shared_office365_SendEmailV2` （若适用，否则写 N/A）
**Severity**: bug | inaccurate | enhancement | question

### 期望
（一两句话）

### 实际
（一两句话 + 错误信息，已脱敏）

### 复现步骤
1. ...
2. ...

### 备注
（可选：用户附加说明）
```

### Step 4 — 报告

告知用户：

- ✅ 追加成功，`feedback/{消费方项目名}.md` 当前已有 N 条反馈
- 复述写入的关键字段（不再展示敏感数据）
- 提示：维护方会用 `/triage-feedback` 定期归集处理

---

## 禁止事项

- ❌ 把不同消费方项目的反馈混写到同一个文件（每个项目**独立**一个
  `feedback/{项目名}.md`；也不要建 `.copilot-feedback/` 之类旧路径）
- ❌ 修改工具库的 skills / components / instructions（只允许写 `feedback/`；
  改进是维护方 triage 后才做的）
- ❌ 发外网 / GitHub Issue / Email
- ❌ 跳过脱敏自检
- ❌ 输出 entry 前不让用户确认（要在 chat 里展示草稿、得到 "OK / 改" 后再写）

---

## 成功标志

- [ ] 文件 ``feedback/{消费方项目名}.md`` 存在或被新建（在工具库仓内）
- [ ] 文件末尾有一条带 ISO 时间戳的新 entry
- [ ] 用户在 chat 里看到 "已追加，当前 N 条" 的回执

---

## 维护方如何收

反馈直接落在工具库仓的 `feedback/{消费方项目名}.md`。维护方有一个对应的内部
skill ``/triage-feedback``（不公开），会：

- 扫 `feedback/` 下所有 `{项目名}.md` 文件
- 按文件里的 entry 排优先级、改 skill / 组件 / instructions
- 脱敏同步回 Power-Automate-Generator 公开仓，下次 fetch 就有改进

若消费方本地工具库不可写（只是远引用 skills），退回让用户手动把反馈粘给维护方。
