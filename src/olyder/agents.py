"""Bounded telemetry parsers and reviewed CLI argument templates for coding agents.

CLI usage is observed after execution; it does NOT enforce provider/subscription limits.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


SUPPORTED = ("codex", "opencode")


def agent_argv(provider: str, prompt: str) -> list[str]:
    if provider == "codex":
        return ["codex", "exec", "--json", "--sandbox", "workspace-write",
                prompt]
    if provider == "opencode":
        return ["opencode", "run", "--format", "json", "--agent", "build", prompt]
    raise ValueError(f"Unsupported coding agent: {provider}")


def _count(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


@dataclass
class AgentUsage:
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    observed_total: int = 0
    usage_events: int = 0
    completed: bool = False
    failed: bool = False
    malformed_events: int = 0
    _seen_parts: set[str] = field(default_factory=set, repr=False)

    def accept(self, raw: str) -> None:
        if len(raw) > 1_000_000:
            self.malformed_events += 1
            return
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            self.malformed_events += 1
            return
        if not isinstance(event, dict):
            self.malformed_events += 1
            return
        kind = event.get("type")
        if self.provider == "codex":
            if kind == "turn.failed":
                self.failed = True
            elif kind == "turn.completed":
                self.completed = True
                usage = event.get("usage")
                if isinstance(usage, dict):
                    if any(type(usage.get(k)) is not int or usage[k]<0 for k in ('input_tokens','output_tokens')):
                        self.malformed_events += 1
                        return
                    self.input_tokens += _count(usage.get("input_tokens"))
                    self.output_tokens += _count(usage.get("output_tokens"))
                    self.cached_tokens += _count(usage.get("cached_input_tokens"))
                    self.reasoning_tokens += _count(usage.get("reasoning_output_tokens"))
                    self.observed_total += _count(usage.get("input_tokens")) + _count(usage.get("output_tokens"))
                    self.usage_events += 1
        elif self.provider == "opencode":
            if kind == "error":
                self.failed = True
            elif kind == "step_finish":
                part = event.get("part")
                if not isinstance(part, dict):
                    return
                identifier = part.get("id")
                if identifier is not None and not isinstance(identifier,str):
                    self.malformed_events+=1
                    return
                if identifier and identifier in self._seen_parts:
                    return
                if identifier:
                    self._seen_parts.add(identifier)
                if part.get("reason") == "stop":
                    self.completed = True
                counts = part.get("tokens")
                if isinstance(counts, dict):
                    if any(type(counts.get(k)) is not int or counts[k]<0 for k in ('input','output')):
                        self.malformed_events += 1
                        return
                    cache = counts.get("cache") or {}
                    if not isinstance(cache, dict):
                        cache = {}
                    inp, out = _count(counts.get("input")), _count(counts.get("output"))
                    cached = _count(cache.get("read"))
                    reasoning = _count(counts.get("reasoning"))
                    written = _count(cache.get("write"))
                    self.input_tokens += inp + written
                    self.output_tokens += out
                    self.cached_tokens += cached
                    self.reasoning_tokens += reasoning
                    self.observed_total += _count(counts.get("total")) or inp + out + cached + reasoning + written
                    self.usage_events += 1

    def snapshot(self) -> dict:
        return {"provider": self.provider, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "cached_tokens": self.cached_tokens,
                "reasoning_tokens": self.reasoning_tokens,
                "observed_tokens": self.observed_total if self.usage_events else None,
                "usage_events": self.usage_events,
                "usage_complete": self.completed and self.usage_events > 0 and not self.failed and not self.malformed_events,
                "status": "failed" if self.failed else "completed" if self.completed else "incomplete",
                "malformed_events": self.malformed_events,
                "quota_enforced": False}


def parse_agent_log(path, provider: str, *, max_lines: int = 100000) -> AgentUsage:
    usage = AgentUsage(provider)
    if hasattr(path, "seek"):
        path.seek(0)
        stream = path
        close = False
    else:
        stream = open(path, "r", encoding="utf-8", errors="replace")
        close = True
    try:
        for i, line in enumerate(stream):
            if i >= max_lines:
                usage.malformed_events += 1
                break
            usage.accept(line)
    finally:
        if close:
            stream.close()
    return usage
