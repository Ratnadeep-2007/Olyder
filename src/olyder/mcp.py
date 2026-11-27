"""Minimal MCP stdio server for IDEs/agents. No automatic shell or network access."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import __version__
from .config import load_spec
from .engine import plan, verify_once
from .privacy import redact, redact_values
from .quota import Budget

MAX_MCP_FRAME_BYTES = 1024 * 1024  # Upper bound per newline-delimited request.

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


_TASK_ARGS = {
    "olyder_agent_inbox": (),
    "olyder_agent_ack": ("message_id",),
    "olyder_task_status": ("run_id",),
    "olyder_task_submit": ("run_id", "revision"),
}
_TASK_DESCRIPTIONS = {
    "olyder_agent_inbox": "Receive unacknowledged messages for the connected agent.",
    "olyder_agent_ack": "Acknowledge a received message by its stable ID.",
    "olyder_task_status": "Read an assigned task and its current proposal revision.",
    "olyder_task_submit": "Submit the assigned proposal revision for verification.",
}
TASK_TOOLS = [{
    "name": name, "description": _TASK_DESCRIPTIONS[name],
    "inputSchema": {"type": "object", "properties": {key: {"type": "string"} for key in keys},
                    "required": list(keys), "additionalProperties": False},
} for name, keys in _TASK_ARGS.items()]


def _task_tool(name, arguments, workspace, binding, controller_key, permissions):
    from . import communication, coordination
    from .state import StateError

    try:
        if (not isinstance(arguments, dict) or set(arguments) != set(_TASK_ARGS[name])
                or any(not isinstance(value, str) or len(value) > 64 for value in arguments.values())):
            raise communication.CommunicationError("Invalid task tool arguments")
        agent_id, session = binding
        if name == "olyder_agent_inbox":
            result = {"messages": communication.inbox(workspace, agent_id, session)}
        elif name == "olyder_agent_ack":
            result = communication.acknowledge(workspace, agent_id, session, arguments["message_id"])
        else:
            run_id = arguments["run_id"]
            result = coordination.task_status(workspace, run_id, agent_binding=binding)
            if name == "olyder_task_submit":
                revision = arguments["revision"]
                if revision != result["proposal_revision"]:
                    raise coordination.TaskError("Proposal revision is invalid or stale")
                # A repeated submission over a reconnected session cannot rerun checks.
                if result["submitted_revision"] != revision:
                    result = coordination.submit_task(workspace, run_id, revision,
                                                      agent_id=agent_id, agent_session=session)
                if controller_key is not None and result["phase"] == "submitted":
                    result = coordination.verify_task(workspace, run_id, controller_key=controller_key,
                                                      permissions=permissions)
        encoded = json.dumps(redact_values(result), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > MAX_MCP_FRAME_BYTES // 2:
            raise communication.CommunicationError("Task response exceeds the MCP bound; use the local CLI")
        return {"content": [{"type": "text", "text": encoded}], "isError": False}
    except (communication.CommunicationError, coordination.TaskError, StateError) as exc:
        return {"content": [{"type": "text", "text": redact(str(exc))[:240]}], "isError": True}


def process(msg: dict, workspace: Path, *, run_permissions=None, sandbox='host',
            docker_image='python:3.13-slim', task_agent=None, task_controller_key=None,
            task_permissions=None) -> dict | None:
    if not isinstance(msg,dict):
        return {'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Request must be an object'}}
    method, req_id = msg.get("method"), msg.get("id")
    if req_id is None:
        return None
    base = {"jsonrpc": "2.0", "id": req_id}
    try:
        if method == "initialize":
            value = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "olyder", "version": __version__},
            }
        elif method == "ping":
            value = {}
        elif method == "tools/list":
            value = {"tools": TOOLS + (TASK_TOOLS if task_agent else [])
                     + ([RUN_TOOL] if run_permissions and run_permissions.execute_builder else [])}
        elif method == "tools/call":
            params = msg.get("params", {})
            if not isinstance(params, dict):
                return {**base, "error": {"code": -32602, "message": "Invalid params"}}
            name = params.get("name")
            if not isinstance(name, str):
                return {**base, "error": {"code": -32602, "message": "Invalid tool name"}}
            if name in _TASK_ARGS:
                if task_agent is None:
                    return {**base, "error": {"code": -32601, "message": "Unknown tool"}}
                value = _task_tool(name, params.get("arguments", {}), workspace, task_agent,
                                   task_controller_key, task_permissions)
                return {**base, "result": value}
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
        return {**base, "result": {"content": [{"type": "text", "text": f"Olyder: {redact(str(exc))[:240]}"}], "isError": True}}
    except Exception as exc:
        # A failing third-party adapter or runtime error must not terminate the
        # stdio server or echo arbitrary exception text (which can contain data).
        return {**base, "result": {"content": [{"type": "text",
                 "text": "Olyder: internal tool failure (" + type(exc).__name__ + ")"}],
                 "isError": True}}


def serve(workspace: Path, *, run_permissions=None, sandbox='host', docker_image='python:3.13-slim',
          task_agent=None, task_controller_key=None, task_permissions=None) -> int:
    """Serve bounded UTF-8 JSON-RPC frames without unbounded readline allocations.

    stdio MCP is line-delimited. Oversized frames are drained in small pieces so
    the following valid request on the same connection is not lost. Never echo
    malformed input or credentials to stdout.
    """
    stream = getattr(sys.stdin, 'buffer', sys.stdin)
    while True:
        raw = stream.readline(MAX_MCP_FRAME_BYTES + 1)
        if not raw:
            break
        newline = raw.endswith(b'\n' if isinstance(raw, bytes) else '\n')
        size = len(raw) if isinstance(raw, bytes) else len(raw.encode('utf-8'))
        if size > MAX_MCP_FRAME_BYTES:
            while not newline:
                segment = stream.readline(8192)
                if not segment:
                    break
                newline = segment.endswith(b'\n' if isinstance(segment, bytes) else '\n')
            response = {'jsonrpc': '2.0', 'id': None, 'error':
                        {'code': -32600, 'message': 'MCP frame exceeds size limit'}}
        else:
            try:
                msg = json.loads(raw.decode('utf-8') if isinstance(raw, bytes) else raw)
                response = process(msg, workspace, run_permissions=run_permissions,
                                   sandbox=sandbox, docker_image=docker_image, task_agent=task_agent,
                                   task_controller_key=task_controller_key, task_permissions=task_permissions)
            except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
                response = {'jsonrpc': '2.0', 'id': None, 'error':
                            {'code': -32700, 'message': 'Parse error: ' + type(exc).__name__}}
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + '\n')
            sys.stdout.flush()
    return 0
