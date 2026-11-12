"""Minimal MCP stdio server for IDEs/agents. No automatic shell or network access."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from .config import load_spec
from .engine import plan, verify_once
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


def process(msg: dict, workspace: Path) -> dict | None:
    method, req_id = msg.get("method"), msg.get("id")
    if req_id is None:
        return None
    base = {"jsonrpc": "2.0", "id": req_id}
    try:
        if method == "initialize":
            value = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "olyder", "version": "0.2.0"}}
        elif method == "ping":
            value = {}
        elif method == "tools/list":
            value = {"tools": TOOLS}
        elif method == "tools/call":
            params = msg.get("params", {})
            if not isinstance(params, dict):
                return {**base, "error": {"code": -32602, "message": "Invalid params"}}
            name = params.get("name")
            spec = load_spec(workspace / "olyder.json")
            budget = Budget(int(spec.raw.get("limits", {}).get("max_tokens", 30000)))
            if name == "olyder_plan":
                result = plan(spec, budget)
            elif name == "olyder_verify":
                result = verify_once(spec, allow_exec=False, use_ai=False, allow_network=False, budget=budget)
            else:
                return {**base, "error": {"code": -32601, "message": "Unknown tool"}}
            value = {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}], "isError": False}
        else:
            return {**base, "error": {"code": -32601, "message": "Method not found"}}
        return {**base, "result": value}
    except (OSError, ValueError, KeyError) as exc:
        return {**base, "result": {"content": [{"type": "text", "text": f"Olyder: {str(exc)[:240]}"}], "isError": True}}


def serve(workspace: Path) -> int:
    for raw in sys.stdin:
        try:
            msg = json.loads(raw)
            response = process(msg, workspace)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except (ValueError, TypeError) as exc:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {type(exc).__name__}"}}) + "\n")
            sys.stdout.flush()
    return 0
