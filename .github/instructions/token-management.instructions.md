---
name: token-management
description: Token 获取/刷新/scope 管理 SOP + Azure App Registration 用途约束
applyTo: "**"
---

# Token 管理 SOP

## 获取优先级（2026-05-27 确认）

**优先用 App OAuth2 token，不要用浏览器拦截**

| 优先级 | 方式 | 说明 |
|---|---|---|
| 1（推荐） | **App + Authorization Code Flow + Refresh Token** | 从 `.token-cache.json` 读 refresh token → 自动换新 access token；90 天有效 |
| 2（回退） | **App + Device Code Flow** | refresh token 过期时，生成 device code 让用户在浏览器登录一次 |
| 3（最后手段） | 浏览器 MSAL 拦截 | 只在 App 不可用时才用；从浏览器网络请求拦截 Authorization header |

## Refresh Token 自动续期

```powershell
# 从 .token-cache.json 读取 refresh token
$cache = Get-Content ".token-cache.json" | ConvertFrom-Json
$body = @{
    grant_type    = "refresh_token"
    client_id     = "<YOUR_CLIENT_ID>"
    client_secret = "<YOUR_CLIENT_SECRET>"
    refresh_token = $cache.refresh_token
    scope         = "<目标 scope> offline_access"
}
$resp = Invoke-RestMethod -Uri "https://login.microsoftonline.com/<YOUR_TENANT_ID>/oauth2/v2.0/token" -Method POST -Body $body -ContentType "application/x-www-form-urlencoded"
# 用 $resp.access_token 调 API
# 用 $resp.refresh_token 更新 .token-cache.json
```

## Scope 对照表

| 目标 API | scope |
|---|---|
| Dataverse Web API | `https://<YOUR_ORG>.crm.dynamics.com/user_impersonation offline_access` |
| Flow Management API | `https://service.flow.microsoft.com/.default offline_access` |
| Power Platform API | `https://api.powerplatform.com/.default offline_access` |
| SharePoint REST API | `https://<tenant>.sharepoint.com/.default offline_access` |
| Microsoft Graph | `https://graph.microsoft.com/.default offline_access` |
| PowerApps API（含 Swagger） | `https://service.powerapps.com/.default offline_access`（注意：PowerShell 调需要在 URL 中加 `$filter=environment eq '{envId}'`）|

**注意**：`.default` 和 resource-specific scope（如 `user_impersonation`）不能混在同一个请求中。每个 API 需要单独获取 token。

## 一次性批量刷新多 scope（2026-06-04 固化）

V5 测试场景需要同时调 Dataverse / Flow / Graph / PowerApps 4 个 API。批量刷的方式：**串行刷新，每次用上一步返回的 refresh_token**（refresh_token 每次刷新都会轮转）。

参考实现：`scripts/_get_tokens.ps1`
```powershell
function Get-Token($scope, $rt) {
    $b = @{ grant_type='refresh_token'; client_id=$clientId; client_secret=$secret; refresh_token=$rt; scope=$scope }
    Invoke-RestMethod -Uri "https://login.microsoftonline.com/$tenant/oauth2/v2.0/token" -Method POST -Body $b -ContentType "application/x-www-form-urlencoded"
}
$dv = Get-Token "https://org81bb0a23.crm.dynamics.com/user_impersonation offline_access" $cache.refresh_token
$cache.refresh_token = $dv.refresh_token
$fl = Get-Token "https://service.flow.microsoft.com/.default offline_access" $cache.refresh_token
$cache.refresh_token = $fl.refresh_token
$gr = Get-Token "https://graph.microsoft.com/.default offline_access" $cache.refresh_token
$cache.refresh_token = $gr.refresh_token
# 写入 .token-cache.json 和临时 .tokens.tmp.json
```

输出到 `.tokens.tmp.json`（gitignore），后续脚本读取使用。

## 浏览器 MSAL 拦截（回退方案）

- 遇到 Dataverse/PowerApps API 返回 401 时，**自动刷新页面**（`navigate_page` reload 或导航到 `make.powerapps.com`），等待 10-15 秒后重试
- **绝对不要清理 localStorage 的 accesstoken 条目** — 清了 refresh token 也会丢（2026-05-26 踩坑）
- 如果刷新 3 次仍然 401，才告知用户可能需要重新登录

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
