"""Public integration contracts, version 1. No vendor SDK is required.

Python registrations run trusted code in-process. Never auto-import plugins
from a task workspace. Untrusted integrations must use executable manifests.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO, runtime_checkable

API_VERSION = 1


@dataclass(frozen=True)
class Capabilities:
    structured_usage: bool = False
    streaming: bool = False
    cancellation: bool = True
    isolated: bool = False
    provider_hard_limit: bool = False
    requires_git: bool = False
    notes: str = ''


@runtime_checkable
class AgentAdapter(Protocol):
    name: str
    api_version: int

    def command(self, prompt: str) -> list[str]: ...
    def parse(self, stream: TextIO) -> dict: ...
    def capabilities(self) -> Capabilities: ...


@runtime_checkable
class ExecutionBackend(Protocol):
    name: str
    api_version: int

    def capabilities(self) -> Capabilities: ...
    def prepare(self, argv: list[str], root: Path, *, writable: bool) -> list[str]: ...


class ModelProvider(Protocol):
    api_version: int

    def complete(self, prompt: str, *, system: str, max_tokens: int) -> dict:
        """Return content plus optional usage; cost is never presumed billed."""
        ...


class Verifier(Protocol):
    api_version: int

    def verify(self, spec, **permissions) -> dict: ...


class EventSink(Protocol):
    def __call__(self, event: dict) -> None: ...
