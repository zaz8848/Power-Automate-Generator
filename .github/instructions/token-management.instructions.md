---
name: token-management
description: Token 获取/刷新/scope 管理 SOP + Azure App Registration 用途约束
applyTo: "**"
---

# Token 管理 SOP

> **核心原则**：所有租户凭据 + 环境信息**只从 `profiles/<tenant>.json` 读**，
> SOP 和脚本里**禁止硬编码** clientId / clientSecret / tenantId / orgUrl / envId。
> 新用户的 profile 通过 `/configure-profile` skill 创建。

## 获取优先级

| 优先级 | 方式 | 何时用 |
|---|---|---|
| 1（推荐） | `python scripts/configure_profile.py <profile> --env <name> --get-token` | 任何场景，自动用 profile 的 refreshToken 刷一个 Dataverse access_token |
| 2 | 手动 ``POST /oauth2/v2.0/token`` （grant_type=refresh_token） | 需要其它 scope（Flow / Graph / PowerApps）时；从 profile 读 client* 字段 |
| 3（首次） | `python scripts/configure_profile.py <profile>` 走 Authorization Code Flow | profile 还没 refreshToken / refreshToken 过期（>90 天） |
| 4（兜底） | 浏览器 MSAL 拦截 | App 不可用时；从浏览器 Network panel 拿 Bearer token |

## Profile schema 速读

```jsonc
// profiles/<tenant>.json (schema v2)
{
  "tenantId": "...",         // Azure AD tenant GUID
  "clientId": "...",         // App Registration Application ID
  "clientSecret": "...",     // App Registration Secret VALUE
  "refreshToken": "...",     // 由 configure_profile.py 自动写入
  "defaultEnvironment": "dev",
  "environments": [
    { "name": "dev",  "environmentId": "...", "dataverseUrl": "https://orgXXXX.crm.dynamics.com" },
    { "name": "prod", "environmentId": "...", "dataverseUrl": "https://orgYYYY.crm.dynamics.com" }
  ]
}
```

读 profile 时：

```powershell
$profile = Get-Content "profiles/$ProfileName.json" -Raw | ConvertFrom-Json
$envName = $EnvOverride ?? $profile.defaultEnvironment
$env     = $profile.environments | Where-Object { $_.name -eq $envName } | Select -First 1
$orgUrl  = $env.dataverseUrl.TrimEnd('/')
$envId   = $env.environmentId
```

```python
# Python
import json
prof = json.load(open(f"profiles/{profile_name}.json", encoding="utf-8-sig"))
env_name = env_override or prof["defaultEnvironment"]
env = next(e for e in prof["environments"] if e["name"] == env_name)
org_url, env_id = env["dataverseUrl"].rstrip("/"), env["environmentId"]
```

## Refresh Token 自动续期（手动版，需要非 Dataverse scope 时用）

```powershell
$profile = Get-Content "profiles/$ProfileName.json" -Raw | ConvertFrom-Json
$body = @{
    grant_type    = "refresh_token"
    client_id     = $profile.clientId
    client_secret = $profile.clientSecret
    refresh_token = $profile.refreshToken
    scope         = "<目标 scope> offline_access"
}
$resp = Invoke-RestMethod -Uri "https://login.microsoftonline.com/$($profile.tenantId)/oauth2/v2.0/token" `
    -Method POST -Body $body -ContentType "application/x-www-form-urlencoded"
# 用 $resp.access_token 调 API
# 用 $resp.refresh_token 写回 profile.refreshToken（refresh_token 每次刷新会轮转）
```

## Scope 对照表

| 目标 API | scope 模板（替换 ``$orgUrl`` / ``$envId`` 为 profile 值） |
|---|---|
| Dataverse Web API | ``$orgUrl/user_impersonation offline_access`` |
| Flow Management API | ``https://service.flow.microsoft.com/.default offline_access`` |
| Power Platform API | ``https://api.powerplatform.com/.default offline_access`` |
| SharePoint REST API | ``https://<tenant>.sharepoint.com/.default offline_access`` |
| Microsoft Graph | ``https://graph.microsoft.com/.default offline_access`` |
| PowerApps API（含 Swagger） | ``https://service.powerapps.com/.default offline_access``（URL 加 ``$filter=environment eq '$envId'``）|

**注意**：``.default`` 和 resource-specific scope（如 ``user_impersonation``）不能混在同一个请求中。每个 scope 需要单独刷一次 token，**每次用上一次返回的 refresh_token**（refresh_token 会轮转）。

## 一次性批量刷多 scope（4-scope 模板）

当一轮工作要同时调 Dataverse + Flow + Graph + PowerApps 4 个 API 时，**串行**刷 4 次：

```powershell
$profile = Get-Content "profiles/$ProfileName.json" -Raw | ConvertFrom-Json
$env = $profile.environments | Where-Object { $_.name -eq $profile.defaultEnvironment } | Select -First 1
$rt = $profile.refreshToken

function Refresh-Scope($scope) {
    $body = @{
        grant_type='refresh_token'
        client_id=$profile.clientId
        client_secret=$profile.clientSecret
        refresh_token=$rt
        scope=$scope
    }
    $r = Invoke-RestMethod -Uri "https://login.microsoftonline.com/$($profile.tenantId)/oauth2/v2.0/token" -Method POST -Body $body -ContentType "application/x-www-form-urlencoded"
    $script:rt = $r.refresh_token   # 轮转
    return $r.access_token
}

$dvToken    = Refresh-Scope "$($env.dataverseUrl.TrimEnd('/'))/user_impersonation offline_access"
$flowToken  = Refresh-Scope "https://service.flow.microsoft.com/.default offline_access"
$graphToken = Refresh-Scope "https://graph.microsoft.com/.default offline_access"
$paToken    = Refresh-Scope "https://service.powerapps.com/.default offline_access"

# 把最新 rt 写回 profile.refreshToken
$profile.refreshToken = $rt
$profile | ConvertTo-Json -Depth 10 | Set-Content "profiles/$ProfileName.json"
```

## 浏览器 MSAL 拦截（仅 lab 调试 / 紧急）

- App OAuth 失败时的兜底；外部用户应该用 `/configure-profile` 而非这条路径
- **绝对不要清理 localStorage 的 accesstoken 条目** — 清了 refresh token 也会丢（2026-05-26 踩坑）
- 刷新 3 次仍 401，告知用户重新跑 `/configure-profile`


## Azure App Registration 用途约束（2026-05-27 定义）

**App 的唯一用途：用 OAuth2 token 调用 Power Platform / Dataverse / SharePoint API**

App Registration `Automate-Generator-API` 是为了让 AI 工具链能：
1. 通过 Client ID + Client Secret 获取 OAuth2 access token
2. 用该 token 调用 Dataverse Web API（读写 workflow/connectionreference 等）
3. 用该 token 调用 Flow Management API / Power Platform API（部署/更新/查询 flow）
4. 用该 token 调用 SharePoint REST API（获取文件夹/文件列表等前置参数）
5. 用该 token 调用 Power Automate Management API（管理 flow）

**严禁用途**：
- ❌ 不用来开发 Azure 资源（Azure Functions / Logic Apps / Cognitive Services 等）
- ❌ 不用来替代 Power Automate connector（flow 内部仍用 connector）
- ❌ 不用来做 AI 推理（不调 Azure OpenAI / AI Builder API）
- ❌ 不改变项目方向 — 本项目是 Power Automate flow 生成器，不是 Azure 开发项目

**优先级**：优先用 App token 调 API；App token 不可用时回退到浏览器 MSAL token 拦截方式
