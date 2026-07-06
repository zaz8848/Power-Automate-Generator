# Echo-Service — Power-Automate-Generator 反馈日志

> 本文件记录 **Echo-Service** 项目使用 Power-Automate-Generator 时的踩坑/建议。
> 由消费方 `/report-issue` skill 追加维护，永不删除历史。
> 已脱敏（无 token / connectionId / orgUrl / 个人邮箱 / 租户 GUID）。

---
## 来源：Echo-Service（Lenovo Echo 售后邮件自动化状态机）

---

## 2026-06-18T22:10:00+08:00

**Skill / Instruction**: `/create-flow` / `flow-operations.instructions.md`
**Component**: `shared_agentnode` (InvokeAgent) + `shared_commondataserviceforapps` (SubscribeWebhookTrigger)
**Severity**: bug

### 期望
用工具生成的状态机 flow（Dataverse 数据事件触发 + InvokeAgent 调 Copilot Studio agent + SendEmailV2 发信）能一次跑通、不重复触发、agent 能被找到、输出能正确读取。

### 实际（5 个踩坑，逐条）

1. **InvokeAgent 的 `body/agentId` 必须填 agent 的 schemaName，不是 botid GUID**。
   - 填 botid GUID（如 `2a7cec85-...`）→ 运行报 `AgentNotFound`（"agent was not found ... or published"），极具误导性（让人以为是没发布）。
   - 正确：填 bots 表的 `schemaname`（如 `crff8_echointentclassifier_o7aBiR`）→ 立即成功。
   - 建议：组件契约 / `describe-component` 里对 InvokeAgent 的 agentId 明确标注"用 schemaName 非 GUID"。

2. **InvokeAgent 输出结构是嵌套的 `structuredOutput/<field>`，不是顶层**。
   - 返回 body = `{conversationId, status, result(markdown 字符串), structuredOutput{...}}`。
   - 读字段要用 `body('Run_agent')?['structuredOutput/serialNumber']`，写顶层 `['serialNumber']` 读到 null。
   - 建议：契约里给出 InvokeAgent 输出 schema 示例。

3. **InvokeAgent 的 `structuredOutput` 对非 ASCII 字符（em-dash –、emoji 等）有编码损坏**。
   - 同一次调用：`result`（markdown 字符串字段）里的 `–` 正常；`structuredOutput.subject` 里同一个 `–` 变成乱码 `\t6`。
   - 影响：直接把 structuredOutput 的 subject/body 发邮件，客户会收到带乱码的主题/正文。
   - 临时绕行：含特殊排版的文本优先从 `result` 字段取、或在 agent instruction 里限制只用 ASCII 标点。

4. **Dataverse 数据事件触发器（OpenApiConnectionWebhook / SubscribeWebhookTrigger）必须显式设 `subscriptionRequest/filteringattributes`**。
   - 不设 → 默认任意列变化都触发。状态机 flow 自己写回非触发列（如 confidence/aicontext）时，因触发列值仍满足 filterexpression，会反复触发自己 → 重复执行（实测每段跑 2 次，导致重复发邮件、重复建单）。
   - 修复：加 `'subscriptionRequest/filteringattributes': '<触发列逻辑名>'`，只在该列变化时触发。干净测试验证每段恢复只跑 1 次。
   - 建议：这是状态机/单实体多段 flow 的高频坑，应在 instruction 里强约束"数据事件触发器必须带 filteringattributes"。

5. **Flow 表达式：`@if(...)` 里嵌 `@body(...)` / `@concat(...)` 里嵌表达式，内层不能再带 `@`**。
   - 内层要用不带 `@` 的裸表达式（如 `body('X')?['y']`），否则部署报 `TemplateValidationError ... '@' at position N is not expected`。
   - 这条 `flow-operations.instructions.md` 已部分提及（@concat），建议补充 @if 同理。

### 复现步骤
1. 用工具生成一个 Dataverse 行更新触发的 flow，内含 InvokeAgent 节点，agentId 填 botid GUID。
2. 部署激活后触发 → 报 AgentNotFound。
3. 改 agentId 为 schemaName → 通过，但读 agent 输出顶层字段为 null（实为 structuredOutput 子路径）。
4. 修正读取路径后链路跑通，但发现每段 flow 重复执行 2 次（触发器缺 filteringattributes）。
5. 加 filteringattributes 后重复消除。

### 备注
本项目（Echo 售后邮件自动化）状态机 6 段 flow 全程用本工具部署/PATCH，整体可用；以上为踩坑记录，非阻塞性问题，已全部自行绕过并验证修复。脱敏：已移除 token / connectionId / orgUrl / 个人邮箱 / 租户 GUID。

---

## 2026-06-22T00:00:00+08:00

**Skill / Instruction**: `/create-flow` / `flow-operations.instructions.md`
**Component**: `shared_commondataserviceforapps` (SubscribeWebhookTrigger) — 触发器 runtimeConfiguration
**Severity**: bug

### 期望
工具生成 flow 时，**不应**自作主张在 trigger 上加 `runtimeConfiguration: { concurrency: { runs: N } }`（触发器并发控制）。这种东西只能在用户明确主动要求时才加。

### 实际
某次生成的状态机 flow，触发器被加了 `concurrency: { runs: 1 }`（注释写"幂等防重入序列化运行"）。后果：
- `runs=1` 把触发器**串行化**，多条触发互相排队堵死，下游靠状态/事件触发的 flow 看起来像"漏触发"（实为被前面的运行卡住）。Echo 状态机就是因此整条链阻塞，CASE_CREATED 后 Echo6 长时间不起草。
- **平台陷阱**：一旦 trigger 启用了 concurrency，**就无法再用 PATCH/update 关掉**——平台报 `CannotDisableTriggerConcurrency`。唯一移除办法是**删除并重建该 flow**（delete + POST create + 重新激活），代价很大。
- 去掉 concurrency（重建 flow）后，状态机立刻通畅，"漏触发"现象消失。

### 复现步骤
1. 用工具生成一个 Dataverse 行更新触发、含 InvokeAgent 的状态机 flow。
2. 多条记录同时触发 → 下游各段串行排队、像漏触发。
3. 想用 PATCH 去掉 trigger 的 concurrency → 报 `CannotDisableTriggerConcurrency`，只能删 flow 重建。

### 备注
**建议工具强制制止 AI 自作主张加 trigger concurrency**：`runtimeConfiguration` 只允许出现在 **action** 节点上用于 `contentTransfer: { transferMode: 'Chunked' }`（大文件分块上传）这类正当用途；trigger 上的 `concurrency` 只有用户明确要求时才加。

---

## 2026-06-22T00:05:00+08:00

**Skill / Instruction**: `/create-flow` / `flow-operations.instructions.md` / `component-library.instructions.md`
**Component**: `shared_agentnode` (InvokeAgent) — Run agent action 节点
**Severity**: enhancement

### 期望
所有调 Copilot Studio agent 的 action 节点（InvokeAgent / InvokeDefinition，即 "Run agent" 类节点）**默认把 action timeout 设成 `P1D`**（24 小时），不要用平台默认值。

### 实际
InvokeAgent 节点跑 Copilot Studio agent 偶发非常慢（实测文本几十秒~10 分钟，挂载 SharePoint 知识库/PDF 时更久）。平台默认 action timeout 较短时，长 agent 调用可能被超时中断，导致整段 flow 失败。给这类 action 加 `limit: { timeout: 'P1D' }` 后，长 agent 调用不会被误超时。

### 复现步骤
1. 用工具生成含 InvokeAgent 的 flow。
2. agent 调用耗时较长（读 SharePoint 知识库 / 长 prompt）→ 偶发被平台默认超时打断。
3. 给该 action 加 `limit: { timeout: 'P1D' }` → 长调用正常完成。

### 备注
**建议把 `limit: { timeout: 'P1D' }` 作为 Run agent 类节点（InvokeAgent / InvokeDefinition）的默认模板字段**，写进组件库的 graphTemplate / 生成时自动带上，省得每次手动补。本项目已对 Echo2/Echo3/Echo6 的 agent 节点全部手动补上 P1D。

