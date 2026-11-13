import io
import json
import sys

import pytest

from olyder.adapters import ExecutableAgent, get_agent, register_agent
from olyder.backends import HostBackend, DockerBackend
from olyder.interfaces import AgentAdapter


@pytest.mark.parametrize('name', ['codex', 'opencode', 'claude'])
def test_builtin_protocol(name):
    adapter = get_agent(name)
    assert isinstance(adapter, AgentAdapter)
    assert adapter.command('hello')[-1] == 'hello'
    assert adapter.capabilities().provider_hard_limit is False


def test_custom_without_core_change():
    adapter = ExecutableAgent('fixture', [sys.executable, '-c', '{prompt}'])
    register_agent(adapter)
    assert get_agent('fixture').command('print(1)')[-1] == 'print(1)'
    assert get_agent('fixture').parse(io.StringIO('done'))['observed_tokens'] is None


def test_claude_cost_is_estimate_not_invoice():
    event = {'type':'result','subtype':'success','is_error':False,
             'total_cost_usd':0.02, 'usage':{'input_tokens':10,'output_tokens':5}}
    usage = get_agent('claude').parse(io.StringIO(json.dumps(event)+'\n'))
    assert usage['observed_tokens'] == 15
    assert usage['estimated_cost_usd'] == '0.02'
    assert usage['billed_cost_usd'] is None


def test_claude_error_cannot_spoof_exit_success():
    usage = get_agent('claude').parse(io.StringIO('{"type":"result","is_error":true}\n'))
    assert usage['status'] == 'failed'


def test_host_needs_authorization(tmp_path):
    with pytest.raises(PermissionError):
        HostBackend().prepare(['echo','ok'], tmp_path, writable=True)
    assert HostBackend(unsafe_authorized=True).prepare(['echo','ok'],tmp_path,writable=True) == ['echo','ok']


def test_docker_does_not_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr('olyder.execution.shutil.which', lambda _: None)
    with pytest.raises(RuntimeError):
        DockerBackend().prepare(['echo','ok'], tmp_path, writable=True)


def test_duplicate_registration_and_bad_command():
    with pytest.raises(ValueError):
        register_agent(get_agent('codex'))
    with pytest.raises(ValueError):
        ExecutableAgent('bad', [''])
