"""Disposable ACP v1 fixture. Writes only into the cwd given by the client.

Not a production coding agent or a paid-model test.
"""
import asyncio
import sys
from pathlib import Path

from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, PROTOCOL_VERSION, run_agent


class FixtureAgent(Agent):
    def __init__(self):
        self.cwd = None

    async def initialize(self, protocol_version, **kwargs):
        return InitializeResponse(protocol_version=PROTOCOL_VERSION)

    async def new_session(self, cwd, **kwargs):
        self.cwd = Path(cwd)
        return NewSessionResponse(session_id="olyder-acp-fixture")

    async def prompt(self, session_id, prompt, **kwargs):
        if session_id != "olyder-acp-fixture" or self.cwd is None:
            raise ValueError("Unexpected ACP session")
        if "--refuse" in sys.argv:
            return PromptResponse(stop_reason="refusal")
        (self.cwd / "answer.py").write_text("answer = 42\n", encoding="utf-8")
        return PromptResponse(stop_reason="end_turn")


async def main():
    await run_agent(FixtureAgent())


if __name__ == "__main__":
    asyncio.run(main())
