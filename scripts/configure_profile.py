"""
configure_profile.py — multi-tenant / multi-environment OAuth helper for /configure-profile skill.

Profile schema v2:
- Top level: tenantId / clientId / clientSecret / refreshToken (per tenant)
- environments[]: list of {name, environmentId, dataverseUrl} (per environment under that tenant)
- defaultEnvironment: which env to use when --env is omitted

Usage:
    # First time: open browser, sign in, paste callback URL, store refreshToken
    python scripts/configure_profile.py profiles/contoso.json

    # Switch default env (no OAuth, just edit file)
    python scripts/configure_profile.py profiles/contoso.json --set-default "ZAF Prod"

    # Get an access token for a specific env (uses stored refreshToken)
    python scripts/configure_profile.py profiles/contoso.json --env "JiaqiDev" --get-token

    # Sanity check: call Dataverse WhoAmI on the chosen env
    python scripts/configure_profile.py profiles/contoso.json --env "JiaqiDev" --whoami
"""
from __future__ import annotations
import json, sys, re, time, webbrowser, urllib.parse, argparse
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

REDIRECT_URI = "https://localhost/callback"
TOKEN_URL_TMPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
AUTH_URL_TMPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"


def load_profile(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"Profile not found: {path}. Copy profiles/profile-template.json first.")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_profile(path: Path, profile: dict) -> None:
    path.write_text(json.dumps(profile, indent=4, ensure_ascii=False), encoding="utf-8")


def pick_env(profile: dict, env_name: str | None) -> dict:
    envs = profile.get("environments") or []
    if not envs:
        sys.exit("Profile has no environments[]. Add at least one.")
    target = env_name or profile.get("defaultEnvironment")
    if not target:
        sys.exit(f"No --env specified and no defaultEnvironment in profile. Available: {[e['name'] for e in envs]}")
    for e in envs:
        if e.get("name") == target:
            return e
    sys.exit(f"Environment '{target}' not in profile. Available: {[e['name'] for e in envs]}")


def validate_creds(profile: dict) -> None:
    missing = [k for k in ("tenantId", "clientId", "clientSecret")
               if not profile.get(k) or str(profile[k]).startswith("<")]
    if missing:
        sys.exit(f"Profile missing or unfilled credentials: {missing}")


def build_authorize_url(profile: dict, env: dict) -> str:
    scope = f"{env['dataverseUrl'].rstrip('/')}/user_impersonation offline_access"
    qs = urllib.parse.urlencode({
        "client_id": profile["clientId"],
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "response_mode": "query",
        "scope": scope,
        "prompt": "select_account",
    })
    return f"{AUTH_URL_TMPL.format(tenant=profile['tenantId'])}?{qs}"


def exchange_code(profile: dict, env: dict, code: str) -> dict:
    body = {
        "grant_type": "authorization_code",
        "client_id": profile["clientId"],
        "client_secret": profile["clientSecret"],
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "scope": f"{env['dataverseUrl'].rstrip('/')}/user_impersonation offline_access",
    }
    r = requests.post(TOKEN_URL_TMPL.format(tenant=profile["tenantId"]), data=body, timeout=30)
    if r.status_code != 200:
        sys.exit(f"Token exchange failed: {r.status_code}\n{r.text}")
    return r.json()


def refresh_access_token(profile: dict, env: dict) -> dict:
    rt = profile.get("refreshToken")
    if not rt or rt == "TODO":
        sys.exit("Profile has no refreshToken yet. Run without --get-token first to do OAuth.")
    body = {
        "grant_type": "refresh_token",
        "client_id": profile["clientId"],
        "client_secret": profile["clientSecret"],
        "refresh_token": rt,
        "scope": f"{env['dataverseUrl'].rstrip('/')}/user_impersonation offline_access",
    }
    r = requests.post(TOKEN_URL_TMPL.format(tenant=profile["tenantId"]), data=body, timeout=30)
    if r.status_code != 200:
        sys.exit(f"Refresh failed: {r.status_code}\n{r.text}")
    return r.json()


def whoami(env: dict, access_token: str) -> None:
    url = f"{env['dataverseUrl'].rstrip('/')}/api/data/v9.2/WhoAmI"
    r = requests.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
    if r.status_code == 200:
        data = r.json()
        print(f"\nWhoAmI OK on env '{env['name']}'")
        print(f"   UserId         = {data.get('UserId')}")
        print(f"   BusinessUnitId = {data.get('BusinessUnitId')}")
        print(f"   OrganizationId = {data.get('OrganizationId')}")
    else:
        sys.exit(f"\nWhoAmI returned {r.status_code}: {r.text[:300]}")


def cmd_oauth(profile_path: Path, profile: dict, env: dict) -> None:
    """First-time OAuth: open browser, get code, exchange for refresh_token, store."""
    auth_url = build_authorize_url(profile, env)
    print("=" * 70)
    print(f"Step 1: Sign in to tenant '{profile.get('_name')}', env '{env['name']}':")
    print()
    print(auth_url)
    print()
    print(f"After sign-in the browser will redirect to {REDIRECT_URI}?code=...")
    print("The browser will show a 'connection refused' error - that's expected.")
    print("Copy the FULL redirect URL from the address bar.")
    print("=" * 70)
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    callback = input(f"\nPaste the full {REDIRECT_URI}?... URL here:\n> ").strip()
    m = re.search(r"[?&]code=([^&]+)", callback)
    if not m:
        sys.exit("No 'code' parameter found. Try again.")
    code = urllib.parse.unquote(m.group(1))

    print("\nStep 2: Exchanging code for refresh_token...")
    tokens = exchange_code(profile, env, code)
    refresh_token = tokens["refresh_token"]
    access_token = tokens["access_token"]
    print(f"   refresh_token length = {len(refresh_token)}")
    print(f"   access_token  length = {len(access_token)}")

    profile["refreshToken"] = refresh_token
    save_profile(profile_path, profile)
    print(f"\nStep 3: Saved refreshToken to {profile_path}")

    cache_path = profile_path.parent.parent / ".token-cache.json"
    cache_path.write_text(json.dumps({
        "refresh_token": refresh_token,
        "obtained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "profile": str(profile_path.name),
        "lastEnv": env["name"],
    }, indent=2), encoding="utf-8")
    print(f"   Also wrote {cache_path}")

    print("\nStep 4: WhoAmI sanity check on env...")
    whoami(env, access_token)
    print(f"\nProfile '{profile.get('_name')}' configured. Use --env <name> to switch among {len(profile['environments'])} envs.")


def cmd_get_token(profile_path: Path, profile: dict, env: dict) -> None:
    """Refresh access token for a specific env using stored refresh_token."""
    tokens = refresh_access_token(profile, env)
    # rotate refresh_token
    profile["refreshToken"] = tokens["refresh_token"]
    save_profile(profile_path, profile)
    print(f"access_token (env={env['name']}, dataverseUrl={env['dataverseUrl']}):")
    print(tokens["access_token"])


def cmd_whoami(profile: dict, env: dict) -> None:
    tokens = refresh_access_token(profile, env)
    whoami(env, tokens["access_token"])


def cmd_set_default(profile_path: Path, profile: dict, env_name: str) -> None:
    envs = profile.get("environments") or []
    if not any(e.get("name") == env_name for e in envs):
        sys.exit(f"Env '{env_name}' not found. Available: {[e['name'] for e in envs]}")
    profile["defaultEnvironment"] = env_name
    save_profile(profile_path, profile)
    print(f"defaultEnvironment set to '{env_name}'")


def cmd_list_envs(profile: dict) -> None:
    print(f"Profile: {profile.get('_name')} ({len(profile.get('environments') or [])} envs, default={profile.get('defaultEnvironment')})")
    for e in profile.get("environments") or []:
        marker = " *" if e["name"] == profile.get("defaultEnvironment") else "  "
        print(f"  {marker} {e['name']:<40} {e['environmentId']:<40} {e['dataverseUrl']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", help="Path to profile JSON, e.g. profiles/contoso.json")
    ap.add_argument("--env", help="Environment name from profile.environments[].name; defaults to defaultEnvironment")
    ap.add_argument("--get-token", action="store_true", help="Refresh and print an access_token for the chosen env")
    ap.add_argument("--whoami", action="store_true", help="Call Dataverse WhoAmI on the chosen env as sanity check")
    ap.add_argument("--set-default", metavar="ENV_NAME", help="Just change defaultEnvironment in the profile, no OAuth")
    ap.add_argument("--list", action="store_true", help="List environments in this profile and exit")
    args = ap.parse_args()

    profile_path = Path(args.profile)
    profile = load_profile(profile_path)

    if args.list:
        cmd_list_envs(profile)
        return

    if args.set_default:
        cmd_set_default(profile_path, profile, args.set_default)
        return

    validate_creds(profile)
    env = pick_env(profile, args.env)

    if args.get_token:
        cmd_get_token(profile_path, profile, env)
        return
    if args.whoami:
        cmd_whoami(profile, env)
        return

    # Default: first-time OAuth
    cmd_oauth(profile_path, profile, env)


if __name__ == "__main__":
    main()
