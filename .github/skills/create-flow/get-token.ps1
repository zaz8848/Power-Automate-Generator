# get-token.ps1 — OAuth2 Refresh Token Flow
# Usage: .\get-token.ps1 -ProfilePath "path\to\profile.json" -Scope "https://service.flow.microsoft.com/.default offline_access"
# Returns: access_token string (also auto-updates refresh_token in profile)

param(
    [Parameter(Mandatory=$true)]
    [string]$ProfilePath,

    [Parameter(Mandatory=$true)]
    [string]$Scope
)

$ErrorActionPreference = "Stop"

$profile = Get-Content $ProfilePath -Raw | ConvertFrom-Json

if (-not $profile.refreshToken -or $profile.refreshToken -like "*待获取*") {
    Write-Error "Profile '$ProfilePath' 没有有效的 refreshToken。请先运行 /configure-profile 获取初始 token。"
    exit 1
}

$body = @{
    grant_type    = "refresh_token"
    client_id     = $profile.clientId
    client_secret = $profile.clientSecret
    refresh_token = $profile.refreshToken
    scope         = $Scope
}

try {
    $resp = Invoke-RestMethod `
        -Uri "https://login.microsoftonline.com/$($profile.tenantId)/oauth2/v2.0/token" `
        -Method POST `
        -Body $body `
        -ContentType "application/x-www-form-urlencoded"

    # Auto-update refresh token if a new one is returned
    if ($resp.refresh_token -and $resp.refresh_token -ne $profile.refreshToken) {
        $profile.refreshToken = $resp.refresh_token
        $profile | ConvertTo-Json -Depth 10 | Set-Content $ProfilePath -Encoding UTF8
        Write-Host "Refresh token updated in profile." -ForegroundColor Green
    }

    # Return the access token
    Write-Output $resp.access_token

} catch {
    $err = $_.Exception.Message
    if ($err -like "*AADSTS70000*" -or $err -like "*AADSTS700082*") {
        Write-Error "Refresh token 已过期。请运行 /configure-profile 重新获取。"
    } else {
        Write-Error "Token 获取失败: $err"
    }
    exit 1
}
