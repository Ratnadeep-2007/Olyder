"""Optional ACP v1 *client-side* adapter for external executable coding agents.

The core remains independent of ACP/IDE SDKs. The runner is a separate,
supervised process launched inside Olyder's chosen execution backend.
ACP client tool requests are denied; an external agent may still mutate its
own process workspace under the backend's explicit security grant.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import TextIO

from .interfaces import API_VERSION, Capabilities

_MAX_ARGV = 24
_MAX_ARG_LENGTH = 4096
_MAX_PROMPT_LENGTH = 25000
_MAX_RESULT_LENGTH = 16384


def validate_agent_argv(argv: list[str]) -> tuple[str, ...]:
    if (not isinstance(argv, list) or not 1 <= len(argv) <= _MAX_ARGV or
            any(not isinstance(arg, str) or not arg or len(arg) > _MAX_ARG_LENGTH
                or "\0" in arg for arg in argv)):
        raise ValueError("ACP agent requires a bounded, explicit argument vector")
    if argv[0].startswith("-"):
        raise ValueError("ACP executable name cannot be an option")
    return tuple(argv)


class ACPProcessAgent:
    """AgentAdapter v1 using an optional ACP SDK child runner, without a shell."""

    api_version = API_VERSION

    def __init__(self, name: str, argv: list[str], *, python: str | None = None):
        if not isinstance(name, str) or not name.replace("-", "_").isidentifier():
            raise ValueError("Invalid ACP adapter name")
        self.name = name
        self.argv = validate_agent_argv(argv)
        self.python = python or sys.executable
        if not self.python or "\0" in self.python:
            raise ValueError("Invalid ACP runner interpreter")

    def capabilities(self) -> Capabilities:
        return Capabilities(
            structured_usage=False, streaming=False, cancellation=True,
            provider_hard_limit=False, isolated=False,
            notes=("ACP v1 client runner; event metadata only, provider usage unknown; "
                   "client-mediated filesystem/terminal/permission calls denied; "
                   "workspace safety depends on the selected execution backend"),
        )

    def command(self, prompt: str) -> list[str]:
        if not isinstance(prompt, str) or len(prompt) > _MAX_PROMPT_LENGTH:
            raise ValueError("ACP prompt exceeds size limit")
        return [self.python, "-m", "olyder.acp_external", "--agent-argv",
                json.dumps(self.argv), "--prompt", prompt]

    def parse(self, stream: TextIO) -> dict:
        result = {
            "provider": self.name, "status": "failed", "observed_tokens": None,
            "input_tokens": None, "output_tokens": None, "cached_tokens": None,
            "usage_complete": False, "estimated_cost_usd": None,
            "billed_cost_usd": None, "origin": "acp_v1_client",
        }
        stream.seek(0)
        found = False
        for _ in range(100):
            line = stream.readline(_MAX_RESULT_LENGTH + 1)
            if not line:
                break
            if len(line) > _MAX_RESULT_LENGTH:
                return result
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(event, dict) or event.get("type") != "olyder.acp.result":
                continue
            if found:
                return result  # Duplicate final messages are ambiguous.
            found = True
            if event.get("status") == "completed" and event.get("stop_reason") == "end_turn":
                result["status"] = "completed"
            if isinstance(event.get("stop_reason"), str):
                result["stop_reason"] = event["stop_reason"][:60]
        return result


async def _run_external(agent_argv: tuple[str, ...], prompt: str) -> str:
    """A real independent ACP v1 conversation: init, session/new, session/prompt."""
    from acp import PROTOCOL_VERSION, spawn_agent_process
    from acp.interfaces import Client
    from acp.schema import TextContentBlock

    class DenyingClient(Client):
        # Do not act as a filesystem/terminal/mutation proxy for the agent.
        async def session_update(self, session_id, update, **kwargs):
            return None

        async def request_permission(self, session_id, tool_call, options, **kwargs):
            return {"outcome": {"outcome": "cancelled"}}

        async def read_text_file(self, *args, **kwargs):
            raise PermissionError("ACP client filesystem access is not granted")

        async def write_text_file(self, *args, **kwargs):
            raise PermissionError("ACP client filesystem access is not granted")

        async def create_terminal(self, *args, **kwargs):
            raise PermissionError("ACP client terminal access is not granted")

    cwd = os.getcwd()  # The parent Olyder execution backend selects this cwd.
    async with spawn_agent_process(DenyingClient(), *agent_argv, cwd=cwd) as (conn, _process):
        init = await conn.initialize(protocol_version=PROTOCOL_VERSION)
        if init.protocol_version != PROTOCOL_VERSION:
            raise ValueError("Unsupported ACP protocol version")
        session = await conn.new_session(cwd=cwd, mcp_servers=[])
        if not session.session_id:
            raise ValueError("ACP agent returned an empty session ID")
        outcome = await conn.prompt(
            session_id=session.session_id,
            prompt=[TextContentBlock(type="text", text=prompt)],
        )
        return outcome.stop_reason


def main(argv: list[str] | None = None) -> int:
    args = argparse.ArgumentParser(prog="olyder.acp_external")
    args.add_argument("--agent-argv", required=True)
    args.add_argument("--prompt", required=True)
    parsed = args.parse_args(argv)
    result = {"type": "olyder.acp.result", "status": "failed"}
    try:
        agent_argv = validate_agent_argv(json.loads(parsed.agent_argv))
        if len(parsed.prompt) > _MAX_PROMPT_LENGTH:
            raise ValueError("ACP prompt exceeds size limit")
        stop = asyncio.run(_run_external(agent_argv, parsed.prompt))
        result.update(stop_reason=stop, status="completed" if stop == "end_turn" else "failed")
    except (Exception, KeyboardInterrupt) as exc:
        # Never echo remote errors, prompts, model traces, or unknown credentials.
        result["reason"] = type(exc).__name__
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
