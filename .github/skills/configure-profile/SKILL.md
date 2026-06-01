---
name: configure-profile
description: >
  Configure a new tenant/environment profile for the Automate Generator.
  Sets up Azure App Registration credentials, obtains initial OAuth2 refresh token via Device Code Flow.
  USE WHEN: 配置新环境、新租户、添加 profile、configure tenant、set up environment credentials、
  connect to new Power Platform environment.
argument-hint: Provide tenant domain (e.g. contoso.onmicrosoft.com) and environment details
---

# Configure Profile

Sets up a new tenant profile for the Automate Generator to connect to Power Platform environments.

## Path Resolution

Resolve the project root from this SKILL.md's path — it is 4 levels up (`.github/skills/configure-profile/SKILL.md` → project root).

```powershell
$SKILL_ROOT = "D:\A_Code\Automate Generator-public"  # ← AI: replace with actual resolved path
```

---

## Step 1: Check if App Registration Exists

Ask the user:
> "Do you already have an Azure App Registration for Power Platform API access? If yes, provide the Client ID. If no, I'll guide you through creating one."

### If user needs to create an App Registration

Guide them to Azure Portal → Entra ID → App registrations → New registration:

1. **Name**: e.g. `Power-Automate-Admin-API`
2. **Redirect URI**: `https://localhost/callback` (Web platform)
3. **API Permissions** — add and grant admin consent for:

| API | Permission | Type |
|---|---|---|
| Microsoft Graph | `User.Read` | Delegated |
| Microsoft Graph | `Directory.ReadWrite.All` | Delegated |
| Microsoft Graph | `Sites.ReadWrite.All` | Delegated |
| Microsoft Graph | `Mail.ReadWrite` | Delegated |
| Dynamics CRM | `user_impersonation` | Delegated |
| SharePoint | `AllSites.FullControl` | Delegated |
| Flow Service | `User` | Delegated |

4. **Client Secret**: Create one (recommended: 24 months expiry)
5. **Admin Consent**: Grant admin consent for all permissions

## Step 2: Collect Information

Ask the user for (skip items they've already provided):

| Field | Example | Required |
|---|---|---|
| **Profile name** | `contoso-prod` | Yes |
| **Tenant ID** | GUID from Azure Portal | Yes |
| **Client ID** | App Registration Application ID | Yes |
| **Client Secret** | (user types directly — do NOT collect via AI) | Yes |
| **Environment ID** | Power Platform environment GUID | Yes |
| **Dataverse Org URL** | `org12345.crm.dynamics.com` | Yes |
| **Redirect URI** | `https://localhost/callback` | Default OK |

**Finding Environment ID**: User can find it at `admin.powerplatform.microsoft.com` → Environments → select environment → copy from URL or details pane.

**Finding Dataverse Org URL**: In the environment details, look for "Environment URL" (e.g. `https://org12345.crm.dynamics.com/`). Strip the `https://` and trailing `/`.

## Step 3: Create Profile File

Write the profile JSON:

```powershell
$profileData = @{
    _name         = "{profileName}"
    _comment      = "描述这个环境的用途"
    tenantId      = "{tenantId}"
    clientId      = "{clientId}"
    clientSecret  = "{clientSecret}"
    environmentId = "{environmentId}"
    dataverseOrg  = "{dataverseOrg}"
    redirectUri   = "https://localhost/callback"
    refreshToken  = ""
} | ConvertTo-Json -Depth 10

$profilePath = "$SKILL_ROOT\profiles\{profileName}.json"
[System.IO.File]::WriteAllText($profilePath, $profileData, [System.Text.Encoding]::UTF8)
```

## Step 4: Obtain Initial Refresh Token via Device Code Flow

```powershell
$profile = Get-Content $profilePath -Raw | ConvertFrom-Json

# Request device code
$body = @{
    client_id = $profile.clientId
    scope     = "https://service.flow.microsoft.com/.default offline_access"
}
$deviceCode = Invoke-RestMethod `
  -Uri "https://login.microsoftonline.com/$($profile.tenantId)/oauth2/v2.0/devicecode" `
  -Method POST -Body $body

Write-Host "`n=========================================="
Write-Host "Go to:    $($deviceCode.verification_uri)"
Write-Host "Enter code: $($deviceCode.user_code)"
Write-Host "==========================================`n"
Write-Host "Waiting for you to authenticate in the browser..."
```

**Tell the user**: Open the URL in a browser, enter the code, and sign in with their Power Platform account.

Then poll for the token:

```powershell
$pollInterval = [math]::Max($deviceCode.interval, 5)
do {
    Start-Sleep -Seconds $pollInterval
    try {
        $tokenResp = Invoke-RestMethod `
          -Uri "https://login.microsoftonline.com/$($profile.tenantId)/oauth2/v2.0/token" `
          -Method POST -Body @{
            grant_type  = "urn:ietf:params:oauth:grant-type:device_code"
            client_id   = $profile.clientId
            device_code = $deviceCode.device_code
        }
        break
    } catch {
        $errMsg = $_.ErrorDetails.Message | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($errMsg.error -eq "authorization_pending") { continue }
        elseif ($errMsg.error -eq "slow_down") { $pollInterval += 5; continue }
        elseif ($errMsg.error -eq "expired_token") {
            Write-Error "Device code expired. Please run this step again."
            exit 1
        }
        else { throw }
    }
} while ($true)

Write-Host "Authentication successful!" -ForegroundColor Green
```

## Step 5: Save Refresh Token to Profile

```powershell
$profile.refreshToken = $tokenResp.refresh_token
$jsonOut = $profile | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($profilePath, $jsonOut, [System.Text.Encoding]::UTF8)
Write-Host "Refresh token saved to profile." -ForegroundColor Green
```

## Step 6: Verify Connection

Test the profile by listing flows in the environment:

```powershell
$token = & "$SKILL_ROOT\.github\skills\create-flow\get-token.ps1" `
  -ProfilePath $profilePath `
  -Scope "https://service.flow.microsoft.com/.default offline_access"

$flows = Invoke-RestMethod `
  -Uri "https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/$($profile.environmentId)/flows?api-version=2016-11-01&`$top=3" `
  -Headers @{Authorization="Bearer $token"}

Write-Host "Connected! Found $($flows.value.Count) flows in environment." -ForegroundColor Green
```

If this succeeds, report to user:
- Profile name and path
- Environment connected
- Number of flows found
- Reminder: refresh token is valid for ~90 days; `get-token.ps1` auto-renews it on each use

## Common Errors

| Error | Cause | Fix |
|---|---|---|
| `AADSTS70000` / `AADSTS700082` | Refresh token expired (90+ days unused) | Re-run Step 4 (Device Code Flow) |
| `AADSTS65001` | Admin consent not granted | Go to Azure Portal → App → API Permissions → Grant admin consent |
| `AADSTS7000218` | Missing `client_secret` in request | Ensure profile has valid `clientSecret` |
| `authorization_pending` loop forever | User didn't complete browser auth | Remind user to open URL and enter code |
| `expired_token` | Took too long (15 min) | Re-run Step 4 |
| 403 on Flow API | User doesn't have Power Automate license | Check license assignment in M365 admin |
