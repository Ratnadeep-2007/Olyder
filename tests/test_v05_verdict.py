"""Sentinels: subset verification and mandatory requirement coverage."""
import json
import time
import pytest
from olyder.config import load_spec
from olyder.engine import verify_once


def fixture(tmp_path, **extra):
    (tmp_path / 'ok').write_text('ok')
    path = tmp_path / 'olyder.json'
    path.write_text(json.dumps({'goal': 'Both files', 'checks': [
        {'id': 'ok', 'type': 'file', 'path': 'ok'},
        {'id': 'absent', 'type': 'file', 'path': 'absent'}], **extra}))
    return load_spec(path)


def test_subset_never_claims_acceptance(tmp_path):
    result = verify_once(fixture(tmp_path), only={'ok'})
    assert result['status'] != 'passed'


def test_expired_requested_critic_is_unresolved(tmp_path):
    spec = fixture(tmp_path)
    (tmp_path / 'absent').touch()
    result = verify_once(spec, use_ai=True, deadline=time.monotonic()-1)
    assert result['independent_critic_status'] == 'deadline_exhausted'


@pytest.mark.parametrize('mandatory', [True, False])
def test_unmapped_requirement(tmp_path, mandatory):
    spec = fixture(tmp_path, schema_version=2, requirements=[{
        'id': 'r1', 'text': 'Review accessibility', 'mandatory': mandatory,
        'acceptance_check_ids': []}])
    (tmp_path / 'absent').touch()
    result = verify_once(spec)
    assert result['status'] == ('needs_review' if mandatory else 'passed')

@pytest.mark.parametrize('invalid', [0, 3, True, '2', None])
def test_reject_unknown_schema(tmp_path, invalid):
    from olyder.config import ConfigError
    with pytest.raises(ConfigError):
        fixture(tmp_path, schema_version=invalid)


@pytest.mark.parametrize('requirements', [[], {}, [None], [
    {'id':'x','text':'one'}, {'id':'x','text':'two'}], [
    {'id':'x','text':'one','acceptance_check_ids':['unknown']}], [
    {'id':'x','text':'one','mandatory':'yes'}], [
    {'id':'x','text':'one','acceptance_check_ids':['ok','ok']}], [
    {'id':'x','text':''}]])
def test_reject_invalid_requirements(tmp_path, requirements):
    from olyder.config import ConfigError
    with pytest.raises(ConfigError):
        fixture(tmp_path, schema_version=2, requirements=requirements)


def test_check_cannot_modify_spec_and_pass(tmp_path):
    import sys
    path = tmp_path / 'olyder.json'
    path.write_text(json.dumps({'goal':'Immutable', 'checks':[{
        'id':'tamper','type':'command','argv':[sys.executable,'-c',
        "from pathlib import Path;Path('olyder.json').write_text('{}')"]}]}))
    result = verify_once(load_spec(path), allow_exec=True)
    assert result['status'] == 'blocked'


def test_ai_cannot_override_failure(tmp_path, monkeypatch):
    monkeypatch.setattr('olyder.engine.chat', lambda *a, **kw: '{"concerns":[],"note":"PASS"}')
    assert verify_once(fixture(tmp_path), use_ai=True)['status'] == 'failed'


def test_ai_unavailable_not_pass(tmp_path, monkeypatch):
    from olyder.models import ModelError
    def unavailable(*a, **kw):
        raise ModelError('No account')
    monkeypatch.setattr('olyder.engine.chat', unavailable)
    spec = fixture(tmp_path)
    (tmp_path / 'absent').touch()
    result = verify_once(spec, use_ai=True)
    assert result['status'] == 'needs_review'
    assert result['independent_critic_status'] == 'unavailable'


def test_adapter_defaults_do_not_auto_approve():
    from olyder.agents import agent_argv
    assert '--auto' not in agent_argv('opencode','x')
    assert '--skip-git-repo-check' not in agent_argv('codex','x')


@pytest.mark.parametrize('mode', ['economy','balanced','thorough'])
def test_cli_modes_keep_full_suite(tmp_path, mode):
    from olyder.cli import main
    spec = fixture(tmp_path)
    output = tmp_path / 'out'
    assert main(['run','--spec',str(spec.path),'--output',str(output),'--mode',mode]) == 1
    result = json.loads((output/'report.json').read_text())
    assert result['policy']['mode'] == mode
    assert result['selected_checks'] == ['ok','absent']
    assert result['status'] == 'failed'


def test_critic_only_failure_never_rebuilds(tmp_path, monkeypatch):
    from olyder import engine
    from olyder.models import ModelError
    spec = fixture(tmp_path)
    (tmp_path/'absent').touch()
    calls = []
    def builder(*a, **kw):
        calls.append(1)
        return 'ok', None
    def critic(*a, **kw):
        raise ModelError('unavailable')
    monkeypatch.setattr(engine, '_invoke_builder', builder)
    monkeypatch.setattr(engine, 'chat', critic)
    result = engine.run_loop(spec, allow_exec=True, execute_builder=True,
        use_ai=True, allow_network=False, output=tmp_path/'out')
    assert result['status'] == 'needs_review'
    assert len(calls) == 1


def test_iteration_exhaustion_has_stop_reason(tmp_path):
    from olyder.engine import run_loop
    spec = fixture(tmp_path)
    result = run_loop(spec, allow_exec=False, execute_builder=False,
        use_ai=False, allow_network=False, output=tmp_path/'out', max_iterations=1)
    assert result['stop_reason'] == 'verification_only'


def test_builder_reserve_still_runs_checks(tmp_path, monkeypatch):
    from olyder import engine
    spec = fixture(tmp_path, limits={'max_seconds':5})
    def forbidden(*a, **kw):
        raise AssertionError('Builder must not be admitted')
    monkeypatch.setattr(engine, '_invoke_builder', forbidden)
    result = engine.run_loop(spec, allow_exec=True, execute_builder=True,
        use_ai=False, allow_network=False, output=tmp_path/'out', mode='balanced')
    assert len(result['checks']) == 2
    assert result['stop_reason'] == 'final_verification_reserve'


def test_late_critic_cannot_accept_expired_run(tmp_path, monkeypatch):
    def late(*a, **kw):
        time.sleep(0.08)
        return '{"concerns":[],"note":"No concerns"}'
    monkeypatch.setattr('olyder.engine.chat', late)
    spec = fixture(tmp_path)
    (tmp_path/'absent').touch()
    result = verify_once(spec, use_ai=True, deadline=time.monotonic()+0.04)
    assert result['status'] == 'blocked'


def test_builder_timeout_verifies_latest_tree(tmp_path, monkeypatch):
    import sys
    from olyder import engine
    from olyder.execution import ExitStatus
    spec = fixture(tmp_path, builder={'argv':[sys.executable,'-c','pass']})
    monkeypatch.setattr(engine, 'managed_run', lambda *a, **kw: ExitStatus(None,True,0))
    result = engine.run_loop(spec, allow_exec=True, execute_builder=True,
        use_ai=False, allow_network=False, output=tmp_path/'out', mode='balanced')
    assert len(result['checks']) == 2
    assert result['status'] == 'blocked'
    assert result['stop_reason'] == 'builder_timeout'
