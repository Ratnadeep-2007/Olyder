"""Minimal MCP stdio server for IDEs/agents. No automatic shell or network access."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .config import load_spec
from .engine import plan, verify_once
from .privacy import redact_values
from .quota import Budget

TOOLS = [
    {
        "name": "olyder_plan",
        "description": "Break project acceptance criteria into implementation tasks without changing them.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}
    },
    {
        "name": "olyder_verify",
        "description": "Run file checks against locked requirements; never runs shell commands or external requests via MCP.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}
    }
]


RUN_TOOL={'name':'olyder_run','description':'Execute the workspace contract using permissions granted when the server started.',
          'inputSchema':{'type':'object','properties':{},'additionalProperties':False}}


def process(msg: dict, workspace: Path, *, run_permissions=None, sandbox='host', docker_image='python:3.13-slim') -> dict | None:
    if not isinstance(msg,dict):
        return {'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Request must be an object'}}
    method, req_id = msg.get("method"), msg.get("id")
    if req_id is None:
        return None
    base = {"jsonrpc": "2.0", "id": req_id}
    try:
        if method == "initialize":
            value = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "olyder", "version": "0.4.0"}}
        elif method == "ping":
            value = {}
        elif method == "tools/list":
            value = {"tools": TOOLS+([RUN_TOOL] if run_permissions and run_permissions.execute_builder else [])}
        elif method == "tools/call":
            params = msg.get("params", {})
            if not isinstance(params, dict):
                return {**base, "error": {"code": -32602, "message": "Invalid params"}}
            name = params.get("name")
            if params.get('arguments',{})!={}:
                return {**base,'error':{'code':-32602,'message':'Tools accept no client-supplied commands or permission flags'}}
            spec = load_spec(workspace / "olyder.json")
            if spec.root != workspace.resolve():
                raise ValueError('Specification escapes MCP workspace')
            budget = Budget(int(spec.raw.get("limits", {}).get("max_tokens", 30000)))
            if name == "olyder_plan":
                result = plan(spec, budget)
            elif name == "olyder_verify":
                result = verify_once(spec, allow_exec=False, use_ai=False, allow_network=False, budget=budget)
            elif name=='olyder_run' and run_permissions and run_permissions.execute_builder:
                from .sdk import run
                result=run(spec.path,permissions=run_permissions,backend=sandbox,docker_image=docker_image)
            else:
                return {**base, "error": {"code": -32601, "message": "Unknown tool"}}
            value = {"content": [{"type": "text", "text": json.dumps(redact_values(result), ensure_ascii=False)}], "isError": False}
        else:
            return {**base, "error": {"code": -32601, "message": "Method not found"}}
        return {**base, "result": value}
    except (OSError, ValueError, KeyError) as exc:
        return {**base, "result": {"content": [{"type": "text", "text": f"Olyder: {str(exc)[:240]}"}], "isError": True}}


def serve(workspace: Path, *, run_permissions=None, sandbox='host', docker_image='python:3.13-slim') -> int:
    for raw in sys.stdin:
        try:
            msg = json.loads(raw)
            response = process(msg, workspace,run_permissions=run_permissions,sandbox=sandbox,docker_image=docker_image)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except (ValueError, TypeError) as exc:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {type(exc).__name__}"}}) + "\n")
            sys.stdout.flush()
    return 0
