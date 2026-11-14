"""Optional ACP v1 editor bridge. No IDE, model or ACP dependency in the core.

Olyder exposes only read-only deterministic plan/verify/status operations.
The official ACP Python SDK owns JSON-RPC transport and schema validation.
No builder, shell, network, paid provider or executable MCP server is accepted.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from acp import (
    PROTOCOL_VERSION, Agent, InitializeResponse, NewSessionResponse,
    PromptResponse, run_agent,
)
from acp.schema import AgentMessageChunk, TextContentBlock

from .privacy import redact, redact_values

MAX_PROMPT_CHARS = 4096
MAX_RESPONSE_CHARS = 12000
HELP = (
    "Olyder ACP v1 (read-only): send 'plan', 'verify', 'status', or 'help'. "
    "Planning is deterministic; verification permits file checks only. "
    "Shell commands, network/browser tests, builders and paid models are NOT "
    "enabled in this editor bridge. Use the reviewed Olyder CLI/SDK to "
    "authorize other operations explicitly."
)


def read_only_command(workspace: Path, text: str) -> str:
    """Interpret a deliberately small fixed command vocabulary, never a shell."""
    cmd = text.strip().lower()
    if cmd in ('', 'help', '/help'):
        return HELP
    if cmd == 'status':
        from .diagnostics import doctor
        return json.dumps(redact_values(doctor()), ensure_ascii=False)
    if cmd not in ('plan', 'verify'):
        return "Unsupported request. " + HELP
    try:
        from .config import load_spec
        from .engine import plan, verify_once
        from .quota import Budget

        spec = load_spec(workspace / 'olyder.json')
        if spec.root != workspace:
            raise ValueError('Specification outside authorized workspace')
        budget = Budget(int(spec.raw.get('limits', {}).get('max_tokens', 30000)))
        if cmd == 'plan':
            result = plan(spec, budget=budget, use_ai=False)
        else:
            result = verify_once(spec, allow_exec=False, use_ai=False,
                                 allow_network=False, budget=budget)
        response = json.dumps(redact_values(result), ensure_ascii=False)
        if len(response) > MAX_RESPONSE_CHARS:
            return response[:MAX_RESPONSE_CHARS] + '... [truncated; consult Olyder CLI report]'
        return response
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return "Olyder request failed: " + redact(type(exc).__name__)


def _prompt_text(blocks: list) -> str:
    if not isinstance(blocks, list) or not blocks:
        return ''
    parts = []
    for block in blocks:
        kind = block.get('type') if isinstance(block, dict) else getattr(block, 'type', None)
        if kind != 'text':
            # Do not accept resource links, images, or embedded content in the
            # initial narrow bridge; they may contain untrusted external data.
            raise ValueError('Only text ACP blocks are supported')
        value = block.get('text') if isinstance(block, dict) else getattr(block, 'text', None)
        if not isinstance(value, str):
            raise ValueError('Invalid text block')
        parts.append(value)
    text = '\n'.join(parts)
    if len(text) > MAX_PROMPT_CHARS:
        raise ValueError('Prompt exceeds editor bridge limit')
    return text


class OlyderACPAgent(Agent):
    """One fixed project root; session IDs cannot select arbitrary workspaces."""

    def __init__(self, workspace: str | Path):
        root = Path(workspace).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError('ACP workspace must be a directory')
        self.workspace = root
        self._sessions: dict[str, dict] = {}
        self._conn = None

    def on_connect(self, conn) -> None:
        self._conn = conn

    async def initialize(self, protocol_version: int, **kwargs) -> InitializeResponse:
        # Version 1 only. Never echo a newer client's version as a false claim.
        return InitializeResponse(protocol_version=PROTOCOL_VERSION)

    async def new_session(self, cwd: str, additional_directories=None,
                          mcp_servers=None, **kwargs) -> NewSessionResponse:
        if additional_directories or mcp_servers:
            raise ValueError('ACP bridge does not accept external roots or MCP servers')
        if not Path(cwd).is_absolute() or Path(cwd).resolve(strict=True) != self.workspace:
            raise ValueError('ACP session cwd must equal authorized Olyder workspace')
        session_id = uuid4().hex
        self._sessions[session_id] = {'cancelled': False}
        return NewSessionResponse(session_id=session_id)

    async def prompt(self, session_id: str, prompt: list, **kwargs) -> PromptResponse:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError('Unknown ACP session')
        session['cancelled'] = False
        text = _prompt_text(prompt)
        # The dispatcher never runs commands or invokes provider models.
        response = await asyncio.to_thread(read_only_command, self.workspace, text)
        if session['cancelled']:
            return PromptResponse(stop_reason='cancelled')
        if self._conn is not None:
            await self._conn.session_update(
                session_id=session_id,
                update=AgentMessageChunk(content=TextContentBlock(type='text', text=response)),
            )
        return PromptResponse(stop_reason='end_turn')

    async def cancel(self, session_id: str, **kwargs) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session['cancelled'] = True

    async def close_session(self, session_id: str, **kwargs):
        self._sessions.pop(session_id, None)
        return None


def serve(workspace: str | Path) -> int:
    """Run optional SDK-backed ACP stdio server; no stdout startup chatter."""
    asyncio.run(run_agent(OlyderACPAgent(workspace)))
    return 0
