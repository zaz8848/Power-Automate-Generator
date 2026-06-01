"""
definition_to_graph.py — Convert Power Automate clientdata definition to Copilot Studio graph format.

Handles all graphConvertible=true nodes programmatically.
Nodes marked graphConvertible="partial" (classify/agent) are output as stubs
with a flag `needsAI=true` for post-processing by AI.

Usage:
    python definition_to_graph.py <flow_json_path> [--output <output_path>] [--env-id <env_id>]
"""

import json
import sys
import re
import uuid
import argparse
import os
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent
COMPONENTS_DIR = WORKSPACE / "components"

# ── Icon / brand color cache (from connector files) ──────────────────────────
_connector_cache: dict = {}

def _load_connector_info(connector_name: str) -> dict:
    """Load connector icon/brand from component files."""
    if connector_name in _connector_cache:
        return _connector_cache[connector_name]
    
    base = connector_name.split("-")[0].rstrip("0123456789").rstrip("_")
    for suffix in [connector_name, base]:
        path = COMPONENTS_DIR / "connectors" / f"{suffix}.json"
        if path.exists():
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            info = {
                "iconUri": data.get("iconUri", ""),
                "brandColor": data.get("brandColor", "#7B7B7B"),
                "displayName": data.get("displayName", connector_name),
            }
            _connector_cache[connector_name] = info
            return info
    
    _connector_cache[connector_name] = {
        "iconUri": "",
        "brandColor": "#7B7B7B",
        "displayName": connector_name,
    }
    return _connector_cache[connector_name]


def _load_component(connector: str, operation_id: str) -> dict | None:
    """Load action component file."""
    openapi_dir = COMPONENTS_DIR / "actions" / "openapi"
    # Try exact match
    for pattern in [
        f"{connector}_{operation_id}.json",
        f"{connector.replace('-', '_')}_{operation_id}.json",
    ]:
        path = openapi_dir / pattern
        if path.exists():
            with open(path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
    return None


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


# ── Expression parser: extract @{...} tokens from strings ───────────────────
_EXPR_PATTERN = re.compile(r"@\{(.+?)\}")

def _parse_rich_segments(text: str, start_node_id: str, trigger_name: str) -> list[dict]:
    """Parse a string with @{...} expressions into rich segments."""
    segments = []
    last_end = 0
    
    for m in _EXPR_PATTERN.finditer(text):
        # Static text before this expression
        if m.start() > last_end:
            segments.append({"type": "static", "value": text[last_end:m.start()]})
        
        expr = m.group(1)
        # Try to parse common patterns
        token_ref = _parse_expression_to_token_ref(expr, start_node_id, trigger_name)
        if token_ref:
            segments.append({
                "type": "token",
                "value": token_ref.get("outputDisplayName", expr),
                "tokenRef": token_ref,
            })
        else:
            # Can't parse — leave as static with the original @{} wrapper
            segments.append({"type": "static", "value": m.group(0)})
        
        last_end = m.end()
    
    # Remaining static text
    if last_end < len(text):
        segments.append({"type": "static", "value": text[last_end:]})
    
    return segments


def _parse_expression_to_token_ref(expr: str, start_node_id: str, trigger_name: str) -> dict | None:
    """Convert a Power Automate expression to a tokenRef object."""
    # triggerOutputs()?['body/from']
    trigger_match = re.match(r"triggerOutputs\(\)\?\['(.+?)'\]", expr)
    if trigger_match:
        output_alias = trigger_match.group(1)
        output_name = output_alias
        display = output_alias.split("/")[-1].title()
        return {
            "type": "step",
            "stepId": start_node_id,
            "stepName": trigger_name,
            "outputName": output_name,
            "outputDisplayName": display,
            "outputType": "string",
            "outputAlias": output_alias,
        }
    
    # body('Action_Name')?['field']
    body_match = re.match(r"body\('(.+?)'\)\?\['(.+?)'\]", expr)
    if body_match:
        action_name = body_match.group(1)
        field = body_match.group(2)
        return {
            "type": "step",
            "stepId": f"__action__{action_name}",  # Placeholder — will be resolved
            "stepName": action_name.replace("_", " "),
            "outputName": field,
            "outputDisplayName": field.split("/")[-1].title(),
            "outputType": "string",
            "outputAlias": field,
        }
    
    # outputs('Action_Name')?['body']?['field']
    outputs_match = re.match(r"outputs\('(.+?)'\)\?\['body'\]\?\['(.+?)'\]", expr)
    if outputs_match:
        action_name = outputs_match.group(1)
        field = outputs_match.group(2)
        return {
            "type": "step",
            "stepId": f"__action__{action_name}",
            "stepName": action_name.replace("_", " "),
            "outputName": f"body/{field}",
            "outputDisplayName": field.split("/")[-1].title(),
            "outputType": "string",
            "outputAlias": f"body/{field}",
        }
    
    return None


# ── Node type detection ──────────────────────────────────────────────────────
def _detect_graph_node_type(action: dict) -> str:
    """Detect graph node type from action definition."""
    action_type = action.get("type", "")
    host = action.get("inputs", {}).get("host", {})
    api_id = host.get("apiId", "")
    op_id = host.get("operationId", "")
    params = action.get("inputs", {}).get("parameters", {})
    
    if action_type == "OpenApiConnection":
        if "m365copilotv2" in api_id:
            return "m365Copilot"
        if "commondataserviceforapps" in api_id and op_id == "PerformBoundAction":
            action_name = params.get("actionName", "")
            if action_name == "Microsoft.Dynamics.CRM.QuickTest":
                return "classify"
        return "connector"
    
    if action_type == "OpenApiConnectionWebhook":
        if "microsoftcopilotstudio" in api_id:
            return "agent"
        return "connector"
    
    type_map = {
        "Compose": "builtinFunction",
        "ParseJson": "builtinFunction",
        "If": "ifElse",
        "Switch": "switch",
        "Foreach": "loop",
        "Until": "loop",
        "Scope": "scope",
        "Wait": "wait",
        "Terminate": "end",
    }
    return type_map.get(action_type, "builtinFunction")


# ── Node builders ────────────────────────────────────────────────────────────
def _build_connector_node(
    node_id: str, action_name: str, action: dict, position: dict
) -> dict:
    """Build a 'connector' type graph node (fully convertible)."""
    host = action["inputs"]["host"]
    api_name = host.get("apiId", "").split("/")[-1]
    op_name = host.get("operationId", "")
    conn_name = host.get("connectionName", "")
    params = action["inputs"].get("parameters", {})
    
    connector_info = _load_connector_info(api_name)
    component = _load_component(api_name, op_name)
    
    # Build parametersSchema from component
    params_schema = {"type": "object", "properties": {}, "required": []}
    outcome_schema = {"type": "object", "properties": {}}
    if component:
        if component.get("inputSchema"):
            # Convert Swagger parameters to simplified schema
            props = {}
            for p in component["inputSchema"]:
                if isinstance(p, dict) and p.get("name") and p.get("in") != "path":
                    props[p["name"]] = {
                        "type": p.get("type", "string"),
                        "title": p.get("x-ms-summary", p["name"]),
                    }
                    if "x-ms-property-name-alias" not in props[p["name"]]:
                        props[p["name"]]["x-ms-property-name-alias"] = p["name"]
            if props:
                params_schema["properties"] = props
        
        if component.get("outputSchema") and isinstance(component["outputSchema"], dict):
            outcome_schema = component["outputSchema"]
    
    return {
        "id": node_id,
        "name": action_name.replace("_", " "),
        "type": "connector",
        "version": 1,
        "position": position,
        "data": {
            "config": {
                "apiName": api_name,
                "displayName": connector_info["displayName"],
                "iconUri": connector_info["iconUri"],
                "brandColor": connector_info["brandColor"],
                "operationName": op_name,
                "operationType": action.get("type", "OpenApiConnection"),
                "parameters": params,
                "parametersSchema": params_schema,
                "connectionName": conn_name,
            },
            "outcomes": [
                {
                    "id": "default",
                    "label": "Default",
                    "outcomeSchema": outcome_schema,
                }
            ],
        },
        "measured": {"width": 240, "height": 66},
    }


def _build_m365copilot_node(
    node_id: str, action_name: str, action: dict, position: dict
) -> dict:
    """Build an 'm365Copilot' type graph node."""
    host = action["inputs"]["host"]
    params = action["inputs"].get("parameters", {})
    conn_name = host.get("connectionName", "")
    
    return {
        "id": node_id,
        "name": action_name.replace("_", " "),
        "type": "m365Copilot",
        "version": 1,
        "position": position,
        "data": {
            "config": {
                "apiName": "shared_m365copilotv2",
                "displayName": "M365 Copilot",
                "operationName": "StartChat",
                "parameters": params,
                "operationType": "OpenApiConnection",
                "parametersSchema": {
                    "type": "object",
                    "properties": {
                        "body": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string", "title": "Message", "x-ms-property-name-alias": "body/message"},
                                "timezone": {"type": "string", "title": "Time Zone", "x-ms-property-name-alias": "body/timezone"},
                                "preferAsync": {"type": "boolean", "title": "Prefer Async", "x-ms-property-name-alias": "body/preferAsync"},
                                "isConversationVisible": {"type": "boolean", "title": "Is Conversation Visible", "x-ms-property-name-alias": "body/isConversationVisible"},
                            },
                            "required": ["message"],
                            "x-ms-property-name-alias": "body",
                        }
                    },
                    "required": ["body"],
                },
                "iconUri": "https://static.powerapps.com/resource/ppcr/releases/v1.0.1811/1.0.1811.4721/m365copilotv2/icon.png",
                "connectionName": conn_name,
            },
            "outcomes": [
                {
                    "id": "default",
                    "label": "Default",
                    "outcomeSchema": {
                        "type": "object",
                        "properties": {
                            "body": {
                                "type": "object",
                                "properties": {
                                    "response": {"type": "string", "title": "Response", "x-ms-property-name-alias": "body/response"},
                                    "conversationId": {"type": "string", "title": "Conversation ID", "x-ms-property-name-alias": "body/conversationId"},
                                    "citations": {"type": "array", "title": "Citations", "x-ms-property-name-alias": "body/citations"},
                                },
                                "x-ms-property-name-alias": "body",
                            }
                        },
                    },
                }
            ],
        },
        "measured": {"width": 240, "height": 66},
    }


def _build_agent_stub(
    node_id: str, action_name: str, action: dict, position: dict
) -> dict:
    """Build a stub 'agent' node — needs AI to fill instructionsRich."""
    params = action["inputs"].get("parameters", {})
    conn_name = action["inputs"].get("host", {}).get("connectionName", "")
    copilot = params.get("Copilot", "")
    message = params.get("body/message", "")
    
    return {
        "id": node_id,
        "name": action_name.replace("_", " "),
        "type": "agent",
        "version": 1,
        "position": position,
        "data": {
            "config": {
                "mode": "invoke",
                "instructions": message,
                "botSchemaName": copilot,
                "isHitlEscalationEnabled": False,
                "inlineInstructions": "",
                "outputMode": "text",
                "connectionName": conn_name,
                "inlineModel": "Sonnet46",
                "instructionsRich": {"segments": [{"type": "static", "value": message}]},
                "_needsAI": True,
                "_aiTask": "Parse body/message expressions into instructionsRich segments with proper tokenRef",
            },
            "outcomes": [
                {
                    "id": "default",
                    "label": "Default",
                    "outcomeSchema": {
                        "type": "object",
                        "properties": {
                            "result": {"type": "string", "description": "The agent response text"},
                            "conversationId": {"type": "string", "description": "Conversation ID"},
                        },
                        "required": ["result", "conversationId"],
                    },
                }
            ],
        },
        "measured": {"width": 240, "height": 66},
        "_needsAI": True,
    }


def _build_classify_stub(
    node_id: str, action_name: str, action: dict, position: dict
) -> dict:
    """Build a stub 'classify' node — needs AI to extract categories from prompt."""
    params = action["inputs"].get("parameters", {})
    prompt_text = ""
    try:
        config = params.get("item/requestv2", {}).get("$customConfig", {})
        prompts = config.get("prompt", [])
        if prompts and isinstance(prompts, list):
            prompt_text = prompts[0].get("text", "")
    except (AttributeError, IndexError, TypeError):
        pass
    
    conn_name = action["inputs"].get("host", {}).get("connectionName", "")
    
    return {
        "id": node_id,
        "name": action_name.replace("_", " "),
        "type": "classify",
        "version": 1,
        "position": position,
        "data": {
            "config": {
                "input": "",
                "categories": [],
                "examples": [],
                "model": "gpt-41-mini",
                "connectionName": conn_name,
                "inputRich": {"segments": []},
                "_needsAI": True,
                "_aiTask": "Extract categories, descriptions, examples, and inputRich from the GPT prompt",
                "_originalPrompt": prompt_text,
            },
            "outcomes": [{"id": "default-category", "label": "Other"}],
        },
        "measured": {"width": 240, "height": 265},
        "_needsAI": True,
    }


def _build_switch_node(
    node_id: str, action_name: str, action: dict, position: dict
) -> dict:
    """Build a switch node — NOT directly rendered in graph. 
    Switch is typically part of a classify node's nodeActionMapping."""
    cases = action.get("cases", {})
    outcomes = []
    for case_name in cases:
        outcomes.append({"id": case_name.lower(), "label": case_name})
    outcomes.append({"id": "default", "label": "Default"})
    
    return {
        "id": node_id,
        "name": action_name.replace("_", " "),
        "type": "switch",
        "version": 1,
        "position": position,
        "data": {
            "config": {"expression": action.get("expression", "")},
            "outcomes": outcomes,
        },
        "measured": {"width": 240, "height": 66},
        "_isSwitch": True,
    }


def _build_parsejson_node(
    node_id: str, action_name: str, action: dict, position: dict
) -> dict:
    """Build a ParseJSON builtinFunction node with correct Copilot Studio config."""
    inputs = action.get("inputs", {})
    content = inputs.get("content", "")
    schema = inputs.get("schema", {})
    
    # Convert JSON Schema to example values (Copilot Studio format)
    schema_example = {}
    if isinstance(schema, dict) and "properties" in schema:
        for key, val in schema["properties"].items():
            schema_example[key] = "example"
    elif isinstance(schema, dict):
        schema_example = schema
    
    return {
        "id": node_id,
        "name": action_name.replace("_", " "),
        "type": "builtinFunction",
        "version": 1,
        "position": position,
        "data": {
            "config": {
                "operationId": "parsejson",
                "operationName": "parsejson",
                "displayName": "Parse JSON",
                "category": "providers/Microsoft.ProcessSimple/operationGroups/DataOperation",
                "categoryDisplayName": "Data Operations",
                "iconUri": "https://logicappsv2resources.blob.core.windows.net/icons/compose.svg",
                "brandColor": "#8c6cff",
                "parameters": {
                    "content": content,
                    "schema": schema_example,
                },
                "description": "Parse JSON content to make it easier to access properties.",
                "parametersSchema": {
                    "type": "object",
                    "required": ["content"],
                    "properties": {
                        "content": {"type": "string", "title": "Content", "description": "JSON content to parse"},
                        "schema": {"type": "object", "title": "Schema", "description": "JSON schema for the content"},
                    },
                },
            },
            "outcomes": [{"id": "default", "label": "Default"}],
        },
        "measured": {"width": 240, "height": 66},
    }


# ── Main conversion ─────────────────────────────────────────────────────────
def convert_definition_to_graph(flow: dict, conn_ref_logical_names: dict | None = None) -> dict:
    """
    Convert a flow's definition to Copilot Studio graph format.
    
    Args:
        flow: The full flow JSON object.
        conn_ref_logical_names: Optional dict mapping connectionName → connectionReferenceLogicalName
    
    Returns:
        The graph object to inject into trigger.metadata.associatedData
    """
    definition = flow["properties"]["definition"]
    conn_refs = flow["properties"].get("connectionReferences", {})
    display_name = flow["properties"].get("displayName", "Workflow")
    
    # Find trigger
    trigger_name = list(definition["triggers"].keys())[0]
    trigger = definition["triggers"][trigger_name]
    
    # ── Build start node ──
    start_id = _new_id("start")
    trigger_config = {"triggerType": "manual"}
    
    host = trigger.get("inputs", {}).get("host", {})
    if host:
        api_name = host.get("apiId", "").split("/")[-1]
        connector_info = _load_connector_info(api_name)
        trigger_config = {
            "triggerType": "connector",
            "connector": {
                "apiName": api_name,
                "operationName": host.get("operationId", ""),
                "connectionName": host.get("connectionName", ""),
                "inputs": trigger.get("inputs", {}).get("parameters", {}),
                "displayName": trigger_name.replace("_", " "),
                "iconUri": connector_info["iconUri"],
                "brandColor": connector_info["brandColor"],
                "operationType": trigger.get("type", ""),
            },
        }
    
    start_node = {
        "id": start_id,
        "name": trigger_name.replace("_", " "),
        "type": "start",
        "version": 1,
        "position": {"x": 250, "y": 270},
        "data": {
            "config": trigger_config,
            "outcomes": [{"id": "default", "label": "Default", "outcomeSchema": {"type": "object", "properties": {}}}],
        },
        "measured": {"width": 240, "height": 66},
    }
    
    nodes = [start_node]
    edges = []
    node_action_mapping = {}
    action_to_node = {}  # action_name → node_id
    
    # ── Process actions ──
    x_pos = 566
    x_step = 316
    
    def process_actions(actions: dict, parent_node_id: str, y_base: int, depth: int = 0):
        nonlocal x_pos
        
        if not actions:
            return
        
        prev_node_id = parent_node_id
        
        for action_name, action in actions.items():
            node_type = _detect_graph_node_type(action)
            node_id = _new_id(node_type)
            position = {"x": x_pos, "y": y_base}
            
            # Build node based on type
            if node_type == "classify":
                node = _build_classify_stub(node_id, action_name, action, position)
            elif node_type == "agent":
                node = _build_agent_stub(node_id, action_name, action, position)
            elif node_type == "m365Copilot":
                node = _build_m365copilot_node(node_id, action_name, action, position)
            elif node_type == "switch":
                # Switch is paired with the preceding classify node
                node = _build_switch_node(node_id, action_name, action, position)
            elif action.get("type") == "ParseJson":
                node = _build_parsejson_node(node_id, action_name, action, position)
            elif node_type == "connector":
                node = _build_connector_node(node_id, action_name, action, position)
            else:
                # Built-in function stub
                node = {
                    "id": node_id,
                    "name": action_name.replace("_", " "),
                    "type": node_type,
                    "version": 1,
                    "position": position,
                    "data": {"config": {}, "outcomes": [{"id": "default", "label": "Default"}]},
                    "measured": {"width": 240, "height": 66},
                }
            
            action_to_node[action_name] = node_id
            
            # Handle If/Else — recurse into then/else branches
            if action.get("type") == "If":
                node["type"] = "ifElse"
                node["data"]["outcomes"] = [
                    {"id": "true", "label": "Yes"},
                    {"id": "false", "label": "No"},
                ]
                nodes.append(node)
                node_action_mapping[node_id] = [action_name]
                
                # Add edge from previous
                run_after = action.get("runAfter", {})
                if run_after:
                    for dep_name in run_after:
                        if dep_name in action_to_node:
                            edges.append({"id": f"edge-{action_to_node[dep_name]}-{node_id}", "source": action_to_node[dep_name], "target": node_id, "targetHandle": "input"})
                elif prev_node_id == parent_node_id:
                    edges.append({"id": f"edge-{parent_node_id}-{node_id}", "source": parent_node_id, "target": node_id, "targetHandle": "input"})
                
                # Recurse into then branch
                then_actions = action.get("actions", {})
                if then_actions:
                    then_y = y_base - 100
                    process_actions(then_actions, node_id, then_y, depth + 1)
                    first_then = list(then_actions.keys())[0]
                    if first_then in action_to_node:
                        edges.append({"id": f"edge-{node_id}-{action_to_node[first_then]}-true", "source": node_id, "target": action_to_node[first_then], "sourceHandle": "true", "targetHandle": "input"})
                
                # Recurse into else branch
                else_actions = action.get("else", {}).get("actions", {})
                if else_actions:
                    else_y = y_base + 100
                    process_actions(else_actions, node_id, else_y, depth + 1)
                    first_else = list(else_actions.keys())[0]
                    if first_else in action_to_node:
                        edges.append({"id": f"edge-{node_id}-{action_to_node[first_else]}-false", "source": node_id, "target": action_to_node[first_else], "sourceHandle": "false", "targetHandle": "input"})
                
                x_pos += x_step
                prev_node_id = node_id
                continue
            
            # Skip adding switch as a separate node if it follows a classify
            if node_type == "switch" and node.get("_isSwitch"):
                # Merge into classify node's nodeActionMapping
                # Find the classify node this switch belongs to
                run_after = action.get("runAfter", {})
                for dep_name in run_after:
                    if dep_name in action_to_node:
                        classify_node_id = action_to_node[dep_name]
                        if classify_node_id in node_action_mapping:
                            node_action_mapping[classify_node_id].append(action_name)
                        
                        # Process switch cases — create edges from classify to case actions
                        cases = action.get("cases", {})
                        case_y = y_base - 150
                        for case_name, case_def in cases.items():
                            case_actions = case_def.get("actions", {})
                            if case_actions:
                                # Find the classify node to get its outcomes
                                classify_node = next((n for n in nodes if n["id"] == classify_node_id), None)
                                if classify_node and classify_node["type"] == "classify":
                                    source_handle = f"category:{case_name.lower()}"
                                    # Check if there's a matching category id
                                    for outcome in classify_node["data"].get("outcomes", []):
                                        if outcome.get("label") == case_name:
                                            source_handle = outcome["id"]
                                            break
                                
                                process_actions(case_actions, classify_node_id, case_y, depth + 1)
                                
                                # Add edge from classify to first case action
                                first_case_action = list(case_actions.keys())[0]
                                if first_case_action in action_to_node:
                                    edges.append({
                                        "id": f"edge-{classify_node_id}-{action_to_node[first_case_action]}",
                                        "source": classify_node_id,
                                        "target": action_to_node[first_case_action],
                                        "sourceHandle": source_handle,
                                        "targetHandle": "input",
                                    })
                            case_y += 150
                        
                        # Process default case
                        default_actions = action.get("default", {}).get("actions", {})
                        if default_actions:
                            process_actions(default_actions, classify_node_id, case_y, depth + 1)
                            first_default = list(default_actions.keys())[0]
                            if first_default in action_to_node:
                                edges.append({
                                    "id": f"edge-{classify_node_id}-{action_to_node[first_default]}",
                                    "source": classify_node_id,
                                    "target": action_to_node[first_default],
                                    "sourceHandle": "default-category",
                                    "targetHandle": "input",
                                })
                        break
                continue  # Don't add switch as a visible node
            
            nodes.append(node)
            node_action_mapping[node_id] = [action_name]
            
            # Add edges based on runAfter
            run_after = action.get("runAfter", {})
            if run_after:
                for dep_name in run_after:
                    if dep_name in action_to_node:
                        dep_node_id = action_to_node[dep_name]
                        edges.append({
                            "id": f"edge-{dep_node_id}-{node_id}",
                            "source": dep_node_id,
                            "target": node_id,
                            "targetHandle": "input",
                        })
            elif prev_node_id == parent_node_id:
                # First action — connect from parent
                edges.append({
                    "id": f"edge-{parent_node_id}-{node_id}",
                    "source": parent_node_id,
                    "target": node_id,
                    "targetHandle": "input",
                })
            
            x_pos += x_step
            prev_node_id = node_id
    
    process_actions(definition.get("actions", {}), start_id, 270)
    
    # ── Build connectionReferences in Copilot Studio format ──
    graph_conn_refs = {}
    for key, ref in conn_refs.items():
        api_name = ref.get("id", "").split("/")[-1] if ref.get("id") else key
        conn_name = ref.get("connectionName", "")
        logical_name = ""
        if conn_ref_logical_names and conn_name in conn_ref_logical_names:
            logical_name = conn_ref_logical_names[conn_name]
        
        graph_conn_refs[key] = {
            "api": {"name": api_name},
            "connection": {"connectionReferenceLogicalName": logical_name},
            "runtimeSource": "embedded",
            "connectionName": conn_name,
        }
    
    # ── Resolve __action__ placeholder stepIds in tokenRefs ──
    for node in nodes:
        _resolve_action_refs(node, action_to_node)
    
    # ── Assemble graph ──
    graph = {
        "name": display_name,
        "nodes": nodes,
        "edges": edges,
        "connectionReferences": graph_conn_refs,
        "nodeActionMapping": node_action_mapping,
    }
    
    # Report needsAI nodes
    ai_nodes = [n for n in nodes if n.get("_needsAI")]
    
    return {
        "graph": graph,
        "needsAI": len(ai_nodes) > 0,
        "aiNodes": [{"nodeId": n["id"], "name": n["name"], "type": n["type"]} for n in ai_nodes],
    }


def _resolve_action_refs(node: dict, action_to_node: dict):
    """Resolve __action__XXX placeholder stepIds to real node IDs."""
    data_str = json.dumps(node.get("data", {}))
    for action_name, node_id in action_to_node.items():
        placeholder = f"__action__{action_name}"
        if placeholder in data_str:
            data_str = data_str.replace(placeholder, node_id)
    node["data"] = json.loads(data_str)


def inject_graph_into_flow(flow: dict, graph_result: dict, trigger_name: str | None = None):
    """Inject the graph into the flow's trigger metadata."""
    definition = flow["properties"]["definition"]
    if not trigger_name:
        trigger_name = list(definition["triggers"].keys())[0]
    
    trigger = definition["triggers"][trigger_name]
    if "metadata" not in trigger:
        trigger["metadata"] = {}
    
    trigger["metadata"]["associatedData"] = {
        "graph": graph_result["graph"],
        "nodeActionMapping": graph_result["graph"]["nodeActionMapping"],
    }


# ── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Convert flow definition to Copilot Studio graph")
    parser.add_argument("flow_json", help="Path to flow JSON file")
    parser.add_argument("--output", "-o", help="Output path (default: overwrite input)")
    parser.add_argument("--conn-refs", help="JSON file mapping connectionName → logicalName")
    args = parser.parse_args()
    
    with open(args.flow_json, "r", encoding="utf-8-sig") as f:
        flow = json.load(f)
    
    conn_refs = None
    if args.conn_refs:
        with open(args.conn_refs, "r", encoding="utf-8-sig") as f:
            conn_refs = json.load(f)
    
    result = convert_definition_to_graph(flow, conn_refs)
    inject_graph_into_flow(flow, result)
    
    output_path = args.output or args.flow_json
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(flow, f, indent=4, ensure_ascii=False)
    
    print(f"Graph generated: {len(result['graph']['nodes'])} nodes, {len(result['graph']['edges'])} edges")
    if result["needsAI"]:
        print(f"\n⚠️  {len(result['aiNodes'])} node(s) need AI post-processing:")
        for n in result["aiNodes"]:
            print(f"  - {n['name']} ({n['type']}): look for _needsAI and _aiTask in config")
    else:
        print("✅ All nodes fully converted (no AI needed)")
    
    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
