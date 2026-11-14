"""ACP v1 editor bridge tests. Official SDK is an optional dependency."""
import asyncio
import json
import sys

import pytest

acp = pytest.importorskip('acp')

from olyder.acp_bridge import OlyderACPAgent, read_only_command, _prompt_text


def _project(tmp_path):
    (tmp_path / 'README.md').write_text('Olyder demo', encoding='utf-8')
    (tmp_path / 'olyder.json').write_text(json.dumps({
        'goal': 'README is present',
        'checks': [{'id': 'readme', 'type': 'file', 'path': 'README.md',
                    'exists': True},
                   {'id': 'exec-denied', 'type': 'command',
                    'argv': [sys.executable, '-c', 'print(123)']}],
    }), encoding='utf-8')
    return tmp_path


def test_acp_dispatch_does_not_grant_execution(tmp_path):
    root = _project(tmp_path)
    report = json.loads(read_only_command(root, 'verify'))
    assert report['status'] != 'passed'  # Command check MUST be blocked.
    assert any(c['status'] == 'blocked' for c in report['checks'])
    assert 'not enabled' in read_only_command(root, 'run all tests').lower()


def test_acp_fixed_command_vocabulary_and_prompt_limits(tmp_path):
    root = _project(tmp_path)
    assert 'read-only' in read_only_command(root, 'help')
    assert 'Unsupported request' in read_only_command(root, 'rm -rf .')
    assert 'only text' in str(pytest.raises(ValueError, _prompt_text,
                         [{'type': 'image', 'data': 'abc'}]).value).lower()
    with pytest.raises(ValueError):
        _prompt_text([{'type': 'text', 'text': 'x' * 4097}])


def test_acp_workspace_and_external_server_denials(tmp_path):
    root = _project(tmp_path)
    agent = OlyderACPAgent(root)
    async def scenario():
        r = await agent.initialize(protocol_version=2)
        assert r.protocol_version == acp.PROTOCOL_VERSION == 1
        with pytest.raises(ValueError):
            await agent.new_session(cwd=str(root.parent))
        with pytest.raises(ValueError):
            await agent.new_session(cwd=str(root), mcp_servers=[{'name': 'untrusted'}])
        with pytest.raises(ValueError):
            await agent.new_session(cwd='.')
        result = await agent.new_session(cwd=str(root), mcp_servers=[])
        return result.session_id
    assert asyncio.run(scenario())


def test_acp_prompt_emits_sdk_message_and_cancel(tmp_path):
    root = _project(tmp_path)
    agent = OlyderACPAgent(root)
    class Sink:
        def __init__(self):
            self.items = []
        async def session_update(self, session_id, update, **kwargs):
            self.items.append((session_id, update))
    sink = Sink()
    agent.on_connect(sink)
    async def scenario():
        sid = (await agent.new_session(cwd=str(root), mcp_servers=[])).session_id
        response = await agent.prompt(sid, [acp.text_block('plan')])
        assert response.stop_reason == 'end_turn'
        assert len(sink.items) == 1
        assert sink.items[0][0] == sid
        assert sink.items[0][1].content.text
        with pytest.raises(ValueError):
            await agent.prompt('missing', [acp.text_block('plan')])
        await agent.cancel(sid)
    asyncio.run(scenario())


def test_real_acp_stdio_client_with_independent_sdk(tmp_path):
    root = _project(tmp_path)
    received = []
    from acp import spawn_agent_process, text_block
    from acp.interfaces import Client

    class RecordingClient(Client):
        async def session_update(self, session_id, update, **kwargs):
            received.append((session_id, update))
        async def request_permission(self, session_id, tool_call, options, **kwargs):
            return {'outcome': {'outcome': 'cancelled'}}

    async def scenario():
        async with spawn_agent_process(
            RecordingClient(), sys.executable, '-m', 'olyder', 'acp',
            '--workspace', str(root),
        ) as (conn, _proc):
            init = await conn.initialize(protocol_version=acp.PROTOCOL_VERSION)
            assert init.protocol_version == 1
            session = await conn.new_session(cwd=str(root), mcp_servers=[])
            turn = await conn.prompt(session_id=session.session_id,
                                     prompt=[text_block('verify')])
            assert turn.stop_reason == 'end_turn'
            assert received and received[-1][0] == session.session_id
            text = received[-1][1].content.text
            assert '"blocked"' in text
    asyncio.run(asyncio.wait_for(scenario(), timeout=25))

def test_acp_overlapping_turns_and_cancellation_are_fail_closed(monkeypatch, tmp_path):
    from threading import Event
    from olyder import acp_bridge

    root = _project(tmp_path)
    agent = OlyderACPAgent(root)
    started, release = Event(), Event()
    observed = []

    class Sink:
        async def session_update(self, *args, **kwargs):
            observed.append(kwargs)
    agent.on_connect(Sink())

    def slow_command(_workspace, _prompt):
        started.set()
        release.wait(timeout=3)
        return 'late response that must not reach the client'

    monkeypatch.setattr(acp_bridge, 'read_only_command', slow_command)

    async def scenario():
        sid = (await agent.new_session(cwd=str(root), mcp_servers=[])).session_id
        first = asyncio.create_task(agent.prompt(sid, [acp.text_block('plan')]))
        assert await asyncio.to_thread(started.wait, 2)
        with pytest.raises(ValueError, match='already running'):
            await agent.prompt(sid, [acp.text_block('verify')])
        await agent.cancel(sid)
        release.set()
        result = await first
        assert result.stop_reason == 'cancelled'
        assert not observed
        await agent.close_session(sid)
        with pytest.raises(ValueError, match='Unknown'):
            await agent.prompt(sid, [acp.text_block('help')])

    try:
        asyncio.run(asyncio.wait_for(scenario(), timeout=8))
    finally:
        release.set()

