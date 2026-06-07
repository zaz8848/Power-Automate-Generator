"""
extract_graph_templates.py
扫描本地 flows/{env}/workflow/*.json 里所有 graph 节点的 data.config，
按 (graphNodeType, operationId) 聚合，merge 到 components/ 对应文件的 graphTemplate 字段。

约束：
- 跳过 displayName 以 [AutoGen] / AutoGen / [TO-DELETE] 开头的 flow（AI 创建的可能带 bug）
- graphTemplate 字段已存在 + graphTemplateVerified=true 的不覆盖（手工 / 实测优先）
- 仅打报告，不直接写组件文件；要写文件加 --apply

用法：
    python scripts/extract_graph_templates.py             # 只报告
    python scripts/extract_graph_templates.py --apply     # 写组件文件
"""
from __future__ import annotations
import json, sys, os, argparse, hashlib
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent.parent
FLOWS_DIR = ROOT / "flows"
COMPONENTS_DIR = ROOT / "components"
SKIP_NAME_PREFIXES = ("[AutoGen]", "AutoGen", "[TO-DELETE]")


def find_clientdata(flow_json: dict) -> dict | None:
    """Return parsed clientdata.properties or None.

    flows are either raw Dataverse rows (with 'clientdata' as string) or wrapped.
    """
    if isinstance(flow_json, dict):
        if "clientdata" in flow_json and isinstance(flow_json["clientdata"], str):
            try:
                return json.loads(flow_json["clientdata"])
            except Exception:
                return None
        if "properties" in flow_json:
            return flow_json
        # nested Power Automate response: { value: [...] } or { name, clientdata, ... }
    return None


def display_name(flow_json: dict) -> str:
    for k in ("displayName", "name", "DisplayName"):
        v = flow_json.get(k)
        if isinstance(v, str):
            return v
    props = flow_json.get("properties") or {}
    return props.get("displayName") or props.get("name") or ""


def extract_graph_nodes(clientdata_props: dict) -> list[dict]:
    """Return list of graph nodes from trigger.metadata.associatedData.graph.nodes."""
    nodes = []
    props = clientdata_props.get("properties") or clientdata_props
    definition = props.get("definition") or {}
    triggers = definition.get("triggers") or {}
    for trig_name, trig in triggers.items():
        if not isinstance(trig, dict):
            continue
        graph = (((trig.get("metadata") or {}).get("associatedData") or {}).get("graph")) or {}
        for n in graph.get("nodes") or []:
            if isinstance(n, dict):
                nodes.append(n)
    return nodes


def node_key(node: dict) -> tuple[str, str, str] | None:
    """Identify a node by (graphNodeType, apiName, operationKey).

    apiName is only set for connector / m365Copilot nodes (e.g. 'shared_office365').
    operationKey is operationId or operationName.
    """
    ntype = node.get("type") or ""
    cfg = (node.get("data") or {}).get("config") or {}
    op = cfg.get("operationId") or cfg.get("operationName")
    api = cfg.get("apiName") or ""
    if not op:
        if ntype == "start":
            return (ntype, "", cfg.get("triggerType") or "manual")
        return None
    return (ntype, api, op)


def find_component_file(node_type: str, api_name: str, operation: str) -> Path | None:
    """Try to locate the matching component json under components/."""
    if node_type in ("connector", "openApiConnection", "openApiConnectionWebhook", "openApiConnectionNotification"):
        if api_name:
            # apiName like 'shared_office365'; component path: actions/openapi/shared_office365_ReplyToV3.json
            f = COMPONENTS_DIR / "actions" / "openapi" / f"{api_name}_{operation}.json"
            if f.exists():
                return f
            # also try triggers/
            f = COMPONENTS_DIR / "triggers" / f"{api_name}_{operation}.json"
            if f.exists():
                return f
        return None
    if node_type == "m365Copilot":
        if api_name:
            f = COMPONENTS_DIR / "actions" / "openapi" / f"{api_name}_{operation}.json"
            if f.exists():
                return f
        return None
    if node_type == "builtinFunction":
        # operation may be 'compose' or 'composeNew' or 'parsejson'
        # try lowercase exact + strip trailing 'New' variants
        candidates = [
            COMPONENTS_DIR / "actions" / f"{operation.lower()}.json",
        ]
        if operation.lower().endswith("new"):
            candidates.append(COMPONENTS_DIR / "actions" / f"{operation.lower()[:-3]}.json")
        if operation.lower() == "parsejson":
            candidates.append(COMPONENTS_DIR / "actions" / "parse-json.json")
        for c in candidates:
            if c.exists():
                return c
        return None
    if node_type == "start":
        if operation.lower() in ("manual", "button"):
            f = COMPONENTS_DIR / "triggers" / "request-button.json"
            if f.exists():
                return f
        if operation.lower() == "connector":
            return None  # connector-trigger varies by connector
    if node_type == "ifElse":
        f = COMPONENTS_DIR / "actions" / "condition.json"
        return f if f.exists() else None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write merged graphTemplate into component files (only when target lacks it AND graphTemplateVerified is not true)")
    ap.add_argument("--include-autogen", action="store_true", help="Also include AutoGen-prefixed flows")
    args = ap.parse_args()

    # Scan
    flow_files = list(FLOWS_DIR.rglob("workflow/*.json"))
    print(f"Found {len(flow_files)} workflow JSON files under flows/", file=sys.stderr)

    # (type, operation) -> list of (config dict, source_file_rel, flow_name)
    aggregated: dict[tuple[str, str], list[tuple[dict, str, str]]] = defaultdict(list)
    skipped = 0
    skipped_names: list[str] = []
    parsed_ok = 0
    for fp in flow_files:
        if fp.name.startswith("_save_capture") or fp.name.startswith("_live_"):
            continue  # internal dump / capture files
        try:
            raw = fp.read_text(encoding="utf-8-sig")
            flow_json = json.loads(raw)
        except Exception as e:
            print(f"  [skip parse] {fp.relative_to(ROOT)}: {e}", file=sys.stderr)
            continue

        name = display_name(flow_json)
        if not args.include_autogen and any(name.startswith(p) for p in SKIP_NAME_PREFIXES):
            skipped += 1
            skipped_names.append(name)
            continue

        cd = find_clientdata(flow_json)
        if cd is None:
            # maybe flow_json is itself clientdata-shaped
            if "properties" in flow_json and "definition" in (flow_json.get("properties") or {}):
                cd = flow_json
        if cd is None:
            print(f"  [no clientdata] {fp.relative_to(ROOT)}", file=sys.stderr)
            continue
        parsed_ok += 1

        nodes = extract_graph_nodes(cd)
        for n in nodes:
            key = node_key(n)
            if not key:
                continue
            cfg = (n.get("data") or {}).get("config") or {}
            aggregated[key].append((cfg, str(fp.relative_to(ROOT)), name))

    print(f"\nParsed {parsed_ok} flows, skipped {skipped} AutoGen/TO-DELETE flows", file=sys.stderr)

    # Report
    print("\n=== Graph node template inventory ===")
    by_type = Counter(k[0] for k in aggregated)
    for t, c in by_type.most_common():
        print(f"  type={t:<35} unique_(api,op)={c}")
    print(f"  TOTAL unique (type, api, op) combos: {len(aggregated)}")

    # Try to merge into existing component files
    print("\n=== Component file matches ===")
    matched = 0
    apply_count = 0
    for (ntype, api, op), records in sorted(aggregated.items()):
        comp_file = find_component_file(ntype, api, op)
        sample_cfg = records[0][0]
        flow_count = len(records)
        label = f"{ntype}/{api+'/' if api else ''}{op}"
        if comp_file:
            matched += 1
            comp = json.loads(comp_file.read_text(encoding="utf-8-sig"))
            existing = comp.get("graphTemplate")
            verified = comp.get("graphTemplateVerified") is True
            status = "HAS+verified" if (existing and verified) else ("HAS" if existing else "MISSING")
            print(f"  [{status:<13}] {label}  -> {comp_file.relative_to(ROOT)}  ({flow_count} occurrences)")
            if args.apply and not existing and not verified:
                # Build graphTemplate shape (same as compose.json convention)
                gt = {
                    "type": ntype,
                    "version": 1,
                    "data": {
                        "config": sample_cfg,
                        "outcomes": (records[0][0].get("outcomes") if isinstance(records[0][0].get("outcomes"), list) else None)
                    },
                    "measured": {"width": 240, "height": 66},
                    "graphTemplateNotes": f"Auto-merged from {flow_count} flow(s); inspect before relying on it."
                }
                # outcomes are sometimes inside data, sometimes inside config; normalize
                if gt["data"]["outcomes"] is None:
                    # take from any record that has data.outcomes
                    for cfg, _, _ in records:
                        # cfg here is data.config; we don't have data.outcomes at this level; skip
                        break
                    gt["data"].pop("outcomes")
                comp["graphTemplate"] = gt
                comp["graphTemplateVerified"] = False
                comp["graphTemplateSource"] = f"extract_graph_templates.py (auto-merged from {flow_count} flow(s) on " + os.environ.get("USERNAME", "host") + ")"
                comp.setdefault("graphConvertible", True)
                comp.setdefault("graphNodeType", ntype)
                comp_file.write_text(json.dumps(comp, indent=2, ensure_ascii=False), encoding="utf-8")
                apply_count += 1
        else:
            print(f"  [NO MATCH    ] {label}  ({flow_count} occurrences)  -- sample fields: {sorted(sample_cfg.keys())[:10]}")

    print(f"\nMatched {matched} (type, op) combos to component files.")
    if args.apply:
        print(f"APPLIED graphTemplate to {apply_count} component files (only where missing).")
    else:
        print("Dry run; pass --apply to write changes.")
    if skipped_names:
        print(f"\nSkipped flows ({len(skipped_names)}): {', '.join(skipped_names[:10])}{'...' if len(skipped_names) > 10 else ''}")


if __name__ == "__main__":
    main()
