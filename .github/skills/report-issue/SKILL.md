---
name: report-issue
description: |
  当用户在使用 Power-Automate-Generator 的 skill / 组件库 / instructions 时
  遇到问题、踩坑、不准确、想提建议，用这个 skill 把反馈记录到 **用户自己项目里
  的单个滚动反馈文件** ``.copilot-feedback/power-automate-generator.md``。
  用户可定期把这个文件分享给 Power-Automate-Generator 的维护方（lab）做 triage。
applyTo: '**'
---

# /report-issue — 反馈到本地单文件 SOP

> **核心约束**：本 skill 只往**用户自己 workspace 根目录**的
> ``.copilot-feedback/power-automate-generator.md`` **append** 一条反馈。
> 不会修改 Power-Automate-Generator 仓本身、不会发外网请求、不会上传用户数据。
> 用户可以反馈 N 次，永远写同一个文件。

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

### Step 3 — 追加到单文件

文件路径：`{workspaceRoot}/.copilot-feedback/power-automate-generator.md`

如果文件不存在，先创建并写入文件头（仅一次）：

```markdown
# Power-Automate-Generator 反馈日志

> 本文件是单一滚动反馈文件，永远 **append**。
> 由 ``/report-issue`` skill 自动维护。
> 分享给 Power-Automate-Generator 维护方时直接发整个文件即可。

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

- ✅ 追加成功，当前文件已有 N 条反馈
- 复述写入的关键字段（不再展示敏感数据）
- 提示：可随时把整个文件分享给 Power-Automate-Generator 维护方

---

## 禁止事项

- ❌ 创建多个反馈文件（永远只写
  ``.copilot-feedback/power-automate-generator.md`` 一个）
- ❌ 修改 Power-Automate-Generator 仓里的任何文件（你只是它的"用户"，
  无权改它）
- ❌ 发外网 / GitHub Issue / Email
- ❌ 跳过脱敏自检
- ❌ 输出 entry 前不让用户确认（要在 chat 里展示草稿、得到 "OK / 改" 后再写）

---

## 成功标志

- [ ] 文件 ``.copilot-feedback/power-automate-generator.md`` 存在或被新建
- [ ] 文件末尾有一条带 ISO 时间戳的新 entry
- [ ] 用户在 chat 里看到 "已追加，当前 N 条" 的回执

---

## 维护方如何收

Power-Automate-Generator 仓的维护方有一个对应的内部 skill
``/triage-feedback``（不公开），用户可以选择：

- 直接把 ``.copilot-feedback/power-automate-generator.md`` 文件粘到 chat
- 用 ``gh issue create`` 把这个文件贴成一条 GitHub Issue
- 邮件发给维护方

维护方拿到后，会按文件里的 entry 排优先级、改 skill / 组件 / instructions，
脱敏同步回 Power-Automate-Generator 公开仓。下次 fetch 就有改进。
