"""
scan_all_envs.py
Pull every Workflow (category=5, modernflowtype=1) from every environment under
a tenant profile, saving each one to flows/{envSlug}/workflow/_scan_{flowId}.json.
Skips flows whose name starts with [AutoGen] / AutoGen / [TO-DELETE].

Environment source priority:
  1. --envs-file <path>          explicit override (file with .environments[] array)
  2. project root environments.json   if it exists (lab-only; contains lab's full tenant scan)
  3. profile.environments[]      always available (set up by /configure-profile)

Usage:
    python scripts/scan_all_envs.py profiles/<tenant>.json
    python scripts/scan_all_envs.py profiles/<tenant>.json --envs-file lab-envs.json
    python scripts/scan_all_envs.py profiles/<tenant>.json --env "ZAF Prod"      # single env
"""
from __future__ import annotations
import json, sys, re, time, argparse
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

ROOT = Path(__file__).resolve().parent.parent
SKIP_PREFIXES = ("[AutoGen]", "AutoGen", "[TO-DELETE]")
TOKEN_URL_TMPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
    return s or "unknown"


def load_envs(profile: dict, envs_file: Path | None) -> list[dict]:
    """Return list of {name, environmentId, dataverseUrl} from priority sources."""
    # 1. explicit override
    if envs_file:
        raw = json.loads(envs_file.read_text(encoding="utf-8-sig"))
        return _normalize(raw)

    # 2. project-root environments.json (lab-only)
    proj_envs = ROOT / "environments.json"
    if proj_envs.exists():
        raw = json.loads(proj_envs.read_text(encoding="utf-8-sig"))
        print(f"[info] using lab environments.json ({proj_envs})", file=sys.stderr)
        return _normalize(raw)

    # 3. profile.environments[]
    print(f"[info] using profile.environments[] ({len(profile.get('environments') or [])} envs)", file=sys.stderr)
    return [
        {"name": e["name"], "environmentId": e["environmentId"], "dataverseUrl": e["dataverseUrl"].rstrip("/")}
        for e in profile.get("environments") or []
    ]


def _normalize(raw) -> list[dict]:
    """Accept either profile-style [{name, environmentId, dataverseUrl}] or
    Power Platform admin export style with linkedEnvironmentMetadata.instanceUrl."""
    items = raw["environments"] if isinstance(raw, dict) and "environments" in raw else raw
    out = []
    for e in items:
        if "dataverseUrl" in e:
            out.append({
                "name": e.get("name") or e.get("displayName") or e.get("environmentId", "unknown"),
                "environmentId": e.get("environmentId") or e.get("id"),
                "dataverseUrl": e["dataverseUrl"].rstrip("/"),
            })
        else:
            meta = e.get("linkedEnvironmentMetadata") or {}
            url = (meta.get("instanceUrl") or "").rstrip("/")
            if not url:
                continue
            out.append({
                "name": e.get("displayName") or e.get("name") or e["id"],
                "environmentId": e["id"],
                "dataverseUrl": url,
            })
    return out


def refresh_token(profile: dict, scope: str, rt: str) -> dict:
    body = {
        "grant_type": "refresh_token",
        "client_id": profile["clientId"],
        "client_secret": profile["clientSecret"],
        "refresh_token": rt,
        "scope": scope,
    }
    r = requests.post(TOKEN_URL_TMPL.format(tenant=profile["tenantId"]), data=body, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code} {r.text[:200]}")
    return r.json()


def list_workflows(org_url: str, access_token: str) -> list[dict]:
    url = (
        f"{org_url}/api/data/v9.2/workflows"
        f"?$filter=category eq 5 and modernflowtype eq 1"
        f"&$select=workflowid,name,clientdata,modernflowtype,statecode,statuscode,createdon"
        f"&$top=200"
    )
    r = requests.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=60)
    if r.status_code != 200:
        print(f"  [ERR] {r.status_code} {r.text[:200]}", file=sys.stderr)
        return []
    return r.json().get("value", [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", help="Path to profile JSON, e.g. profiles/contoso.json")
    ap.add_argument("--env", help="Scan only this env (name from environments list)")
    ap.add_argument("--envs-file", help="Override env source (JSON file)")
    args = ap.parse_args()

    profile_path = Path(args.profile)
    if not profile_path.exists():
        sys.exit(f"Profile not found: {profile_path}")
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))

    if not profile.get("refreshToken") or profile["refreshToken"] == "TODO":
        sys.exit("Profile has no refreshToken. Run: python scripts/configure_profile.py " + str(profile_path))

    envs = load_envs(profile, Path(args.envs_file) if args.envs_file else None)
    if args.env:
        envs = [e for e in envs if e["name"] == args.env]
        if not envs:
            sys.exit(f"No env named '{args.env}' in source. Available: {[e['name'] for e in load_envs(profile, None)]}")

    rt = profile["refreshToken"]
    summary = []
    for env in envs:
        name, org_url, env_id = env["name"], env["dataverseUrl"], env["environmentId"]
        slug = slugify(name)
        print(f"\n=== {name} ({org_url}) ===")
        try:
            tok = refresh_token(profile, f"{org_url}/user_impersonation offline_access", rt)
            rt = tok["refresh_token"]
        except Exception as e:
            print(f"  [skip env] token refresh failed: {e}")
            continue
        flows = list_workflows(org_url, tok["access_token"])
        print(f"  found {len(flows)} workflows")
        saved = 0
        kept_names = []
        for f in flows:
            n = f.get("name") or ""
            if any(n.startswith(p) for p in SKIP_PREFIXES):
                continue
            out_dir = ROOT / "flows" / slug / "workflow"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"_scan_{f['workflowid']}.json").write_text(
                json.dumps(f, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            saved += 1
            kept_names.append(n)
        summary.append({"env": name, "total": len(flows), "saved": saved, "kept_first5": kept_names[:5]})

    profile["refreshToken"] = rt
    profile_path.write_text(json.dumps(profile, indent=4, ensure_ascii=False), encoding="utf-8")

    print("\n=== SUMMARY ===")
    total_saved = 0
    for s in summary:
        print(f"  {s['env']:<40} total={s['total']:<4} saved={s['saved']:<4}  {', '.join(s['kept_first5'])}")
        total_saved += s["saved"]
    print(f"\nTotal workflows saved: {total_saved}")


if __name__ == "__main__":
    main()
