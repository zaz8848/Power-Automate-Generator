"""
scan_all_envs.py
扫描 environments.json 里所有有 Dataverse 的环境，拉每个环境的 Workflow（category=5 且 modernflowtype=1），
落到 flows/{envSlug}/workflow/_scan_{flowId}.json，跳过 [AutoGen] / [TO-DELETE]。

依赖：D:\A_Code\Automate Generator\.token-cache.json 有 refresh_token。
"""
from __future__ import annotations
import json, os, sys, re, time, urllib.parse, subprocess
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
ENVS = json.loads((ROOT / "environments.json").read_text(encoding="utf-8-sig"))["environments"]
CACHE = ROOT / ".token-cache.json"
TENANT = "<YOUR_TENANT_ID>"
CLIENT_ID = "<YOUR_CLIENT_ID>"
SECRET = "<YOUR_CLIENT_SECRET>"
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
SKIP_PREFIXES = ("[AutoGen]", "AutoGen", "[TO-DELETE]")


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
    return s or "unknown"


def refresh(scope: str, rt: str) -> dict:
    body = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": SECRET,
        "refresh_token": rt,
        "scope": scope,
    }
    r = requests.post(TOKEN_URL, data=body, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"token refresh failed for scope={scope}: {r.status_code} {r.text[:200]}")
    return r.json()


def list_workflows(org_url: str, access_token: str) -> list[dict]:
    """List workflows category=5, modernflowtype=1 in this env."""
    url = (
        f"{org_url}/api/data/v9.2/workflows"
        f"?$filter=category eq 5 and modernflowtype eq 1"
        f"&$select=workflowid,name,clientdata,modernflowtype,statecode,statuscode,createdon"
        f"&$top=200"
    )
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        timeout=60,
    )
    if r.status_code != 200:
        print(f"  [ERR] list workflows: {r.status_code} {r.text[:200]}", file=sys.stderr)
        return []
    return r.json().get("value", [])


def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8-sig"))
    rt = cache["refresh_token"]

    summary = []
    for env in ENVS:
        meta = env.get("linkedEnvironmentMetadata") or {}
        org_url = (meta.get("instanceUrl") or "").rstrip("/")
        if not org_url:
            continue
        name = env.get("displayName") or env.get("name") or env["id"]
        slug = slugify(name)
        print(f"\n=== {name} ({org_url}) ===")
        try:
            tok = refresh(f"{org_url}/user_impersonation offline_access", rt)
            rt = tok["refresh_token"]
        except Exception as e:
            print(f"  [skip env] token refresh failed: {e}")
            continue
        access = tok["access_token"]
        flows = list_workflows(org_url, access)
        print(f"  found {len(flows)} workflows")
        saved = 0
        kept_names = []
        for f in flows:
            n = f.get("name") or ""
            if any(n.startswith(p) for p in SKIP_PREFIXES):
                continue
            out_dir = ROOT / "flows" / slug / "workflow"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"_scan_{f['workflowid']}.json"
            out_file.write_text(json.dumps(f, indent=2, ensure_ascii=False), encoding="utf-8")
            saved += 1
            kept_names.append(n)
        summary.append({"env": name, "slug": slug, "total": len(flows), "saved": saved, "kept_first5": kept_names[:5]})

    # write rolling cache
    cache["refresh_token"] = rt
    cache["obtained_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    CACHE.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    # final report
    print("\n=== SUMMARY ===")
    total_saved = 0
    for s in summary:
        print(f"  {s['env']:<40} total={s['total']:<4} saved={s['saved']:<4}  {', '.join(s['kept_first5'])}")
        total_saved += s["saved"]
    print(f"\nTotal workflows saved: {total_saved}")


if __name__ == "__main__":
    main()
