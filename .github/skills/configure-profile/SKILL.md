---
name: configure-profile
description: |
  首次使用 Power-Automate-Generator 时，引导用户创建 Azure App Registration、
  填写 profile 文件（一个文件覆盖一个租户下的多个环境）、走 Authorization Code
  Flow 拿 refresh_token，落盘到 `.token-cache.json`。完成后 `/create-flow` /
  `/scan-environment` 才有 token 可用。
  用户说"配置环境"/"configure profile"/"我是第一次用"/"加新租户"/"加新环境"/"切换环境"
  /"add tenant"/"switch env"时使用。
applyTo: '**'
---

# /configure-profile — 多租户多环境配置 SOP

> **Profile schema v2**：一个 profile 文件 = 一个 Azure AD 租户。文件顶部放 App
> Registration 凭据（``tenantId`` / ``clientId`` / ``clientSecret`` / ``refreshToken``），
> ``environments[]`` 列出该租户下所有 Power Platform 环境。运行时用 ``--env <name>``
> 或改 ``defaultEnvironment`` 切环境，**凭据复用，不需重新 OAuth**。
>
> 完成后产出：``profiles/<tenant-name>.json`` + ``.token-cache.json``。
> 后续 ``/create-flow`` / ``/scan-environment`` 等 skill 自动读取。

---

## 触发条件

| 用户说 | AI 做 |
|---|---|
| "configure profile" / "第一次用" / "加新租户" | 走 Step 1-3 完整流程 |
| "加新环境到现有 profile" / "新 env" | 跳到 Step 2.5（只加 environments[] 条目） |
| "切到 XX 环境" / "switch env" | 跑 ``--set-default <name>`` 或 ``--env <name>`` |
| 其它 skill 检测到没 ``.token-cache.json`` | 自动提示用户跑本 skill |

---

## 用户准备

跑 skill 前要有：

1. Power Platform 环境的访问权限（能登 ``make.powerautomate.com``）
2. **Azure AD Global Admin 或 Application Administrator 角色**（建 App + grant consent；没有就找 IT admin）
3. 浏览器（OAuth 登录）
4. Python 3.10+，``pip install requests``

---

## Step 1 — 在 Azure Portal 建 App Registration

**1.1 创建 App**

打开 https://portal.azure.com → ``Microsoft Entra ID`` → ``App registrations`` → ``+ New registration``

- **Name**：``Power-Automate-Generator-<tenant-name>``
- **Supported account types**：``Single tenant``
- **Redirect URI**：Platform=``Web``，URL=``https://localhost/callback``

创建后从 Overview 页拿 ``Application (Client) ID`` 和 ``Directory (Tenant) ID`` 给 AI。

**1.2 加 API 权限**

App > ``API permissions`` > ``+ Add a permission``，按下表逐个加：

| API | Type | Permission | 必须 / 可选 |
|---|---|---|---|
| Dynamics CRM | Delegated | ``user_impersonation`` | 必须 |
| Microsoft Graph | Delegated | ``User.Read`` | 必须 |
| Power Automate | Delegated | ``Flows.Manage.All`` 或 ``User`` | 必须 |
| PowerApps Service | Delegated | ``User`` | 必须 |
| SharePoint | Delegated | ``AllSites.FullControl`` | 可选（用 SP connector 时） |
| Power Automate | Delegated | ``Approvals.Manage.All`` | 可选 |

加完点 ``Grant admin consent for <tenant>``。

**1.3 建 Client Secret**

App > ``Certificates & secrets`` > ``Client secrets`` > ``+ New client secret``
- Description / Expires 按公司 policy 选
- **立刻复制 Value 列**（不是 Secret ID）

---

## Step 2 — 写 profile 文件（一个租户一个）

让用户选个简短 tenant name（如 ``contoso`` / ``fabrikam`` / ``5jkmbs``），AI 把
``profiles/profile-template.json`` 复制到 ``profiles/<tenant>.json``，填顶层凭据：

```json
{
    "_name": "contoso",
    "schemaVersion": 2,
    "tenantId": "...",
    "clientId": "...",
    "clientSecret": "...",
    "refreshToken": "TODO",
    "defaultEnvironment": "<其中一个 env 的 name>",
    "environments": [...]
}
```

### Step 2.5 — 加 environments[] 条目

让用户列出**该租户下要用的所有 Power Platform 环境**（可以一次列全，也可以以后加）。

每个 env 需要 3 个字段：

```json
{
    "name": "dev",
    "environmentId": "<YOUR_ENV_ID>",
    "dataverseUrl": "https://<YOUR_ORG>.crm.dynamics.com"
}
```

获取方式：
- ``environmentId`` 在 ``make.powerautomate.com`` URL 里 ``/environments/<GUID>/``
- ``dataverseUrl`` 在 ``admin.powerplatform.microsoft.com`` > Environments > 点环境 > 右侧 ``Environment URL``

**安全确认**：把 ``profiles/*.json`` 在 ``.gitignore`` 里排除（template 例外）：

```
profiles/*.json
!profiles/profile-template.json
```

---

## Step 3 — 跑 OAuth 拿 refresh_token

```powershell
python scripts/configure_profile.py profiles/<tenant>.json
```

行为：
1. 用 ``defaultEnvironment`` 的 ``dataverseUrl`` 构造 OAuth scope
2. 浏览器自动打开授权页 → 用户登录 + 同意
3. 浏览器跳 ``https://localhost/callback?code=...`` 报 connection refused（正常）
4. 用户复制完整 URL 回粘到终端
5. 脚本换 refresh_token → 写回 profile + ``.token-cache.json``
6. 自动跑 WhoAmI 验证

⚠️ **关键**：refresh_token 是**租户级**的，**所有该租户下的 env 共用同一个**。
切环境时不需要重做 OAuth。

---

## Step 4 — 后续操作

```powershell
# 列出该 profile 下所有 env
python scripts/configure_profile.py profiles/contoso.json --list

# 改默认 env
python scripts/configure_profile.py profiles/contoso.json --set-default "ZAF Prod"

# 临时用某个 env 拿 access_token
python scripts/configure_profile.py profiles/contoso.json --env "JiaqiDev" --get-token

# 验证某 env 真活的
python scripts/configure_profile.py profiles/contoso.json --env "JiaqiDev" --whoami
```

其它 skill（``/create-flow`` / ``/scan-environment``）默认读 ``defaultEnvironment``，
也支持 ``--env <name>`` override。

---

## 多租户场景

要同时支持多个租户（如 Contoso + Fabrikam）：

```
profiles/
  contoso.json     # 32 个环境
  fabrikam.json    # 5 个环境
  profile-template.json
```

每个文件独立 OAuth，独立 refresh_token。在 chat 里说"切到 fabrikam 的 prod"，
AI 用 ``profiles/fabrikam.json --env prod`` 即可。

---

## 成功标志

- [ ] ``profiles/<tenant>.json`` 存在且 schema v2 字段填全
- [ ] ``environments[]`` 至少 1 条
- [ ] ``refreshToken`` 不是 "TODO"
- [ ] ``.token-cache.json`` 存在
- [ ] ``profiles/`` 在 ``.gitignore`` 里（template 例外）
- [ ] ``--whoami`` 在 ``defaultEnvironment`` 上返回 200

---

## 禁止事项

- ❌ 让 AI 自己生成 ``clientSecret`` — 必须 Azure Portal 用户自建
- ❌ 把 ``clientSecret`` / ``refreshToken`` 同步到 DevTool 或任何公开仓
- ❌ 一个 profile 文件混多个租户（schema 只允许 1 个 tenant）
- ❌ 跳过 admin consent
- ❌ ``profiles/<tenant>.json`` 提交进 git
- ❌ ``defaultEnvironment`` 写一个 ``environments[]`` 里不存在的 name

---

## 常见报错

| 报错 | 原因 | 解法 |
|---|---|---|
| ``AADSTS65001: consent required`` | 没 grant admin consent | 回 Azure App > API permissions > Grant admin consent |
| ``AADSTS7000215: Invalid client secret`` | Secret 写错 / 复制了 Secret ID | 回 Azure 重建 Secret 并复制 Value |
| ``AADSTS900971: No reply address`` | redirect URI 没配 | App > Authentication > 加 ``https://localhost/callback`` |
| WhoAmI 401 | scope 拼错 / refresh_token 失效 | 重跑 OAuth |
| WhoAmI 403 | 用户没该环境权限 | 让 admin 在 Power Platform Admin Center 给用户加 Security Role |
| ``Env not in profile`` | ``--env`` 名字拼错 | 跑 ``--list`` 看正确名字 |

---

## 后置动作

- 配完一个 profile → 立刻提示用户用 ``/scan-environment`` 拉一下 ``defaultEnvironment`` 的 flow 列表验证
- 想加新租户 → 重跑本 skill，写 ``profiles/<另一个 tenant>.json``
- 想加同租户新 env → 直接编辑 ``environments[]`` 加一条即可（refresh_token 复用）
