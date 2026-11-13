import json
import sys

import pytest

from olyder.sdk import run, Permissions


def project(tmp_path, code="from pathlib import Path;Path('answer.py').write_text('answer = 42')", **extra):
    (tmp_path/'tests').mkdir()
    (tmp_path/'tests'/'oracle.py').write_text("from answer import answer;assert answer == 42")
    (tmp_path/'answer.py').write_text('answer = 0')
    config={'goal':'Answer 42','checks':[{'id':'oracle','type':'command',
        'argv':[sys.executable,'-c',"exec(open('tests/oracle.py').read())"]}],
        'builder':{'argv':[sys.executable,'-c',code]}, 'limits':{'max_iterations':3,'max_seconds':30}, **extra}
    path=tmp_path/'olyder.json';path.write_text(json.dumps(config))
    return path


def test_end_to_end_detached_verification_and_apply(tmp_path):
    events=[]
    result=run(project(tmp_path), permissions=Permissions(allow_exec=True,execute_builder=True,unsafe_host=True),sink=events.append)
    assert result['status'] == 'passed'
    assert result['full_suite_executed']
    assert result['run_id']
    assert (tmp_path/'answer.py').read_text() == 'answer = 42'
    assert result['accounting']['observations'][0]['observed_tokens'] is None
    assert result['budget_verdict'] == 'unknown'
    assert any(e['type']=='process_started' for e in events)


def test_builder_tamper_does_not_manufacture_success(tmp_path):
    code="from pathlib import Path;Path('tests').mkdir();Path('tests/oracle.py').write_text('pass')"
    result=run(project(tmp_path,code),permissions=Permissions(allow_exec=True,execute_builder=True,unsafe_host=True))
    assert result['status'] == 'blocked'
    assert result['stop_reason'] == 'integrity_violation'
    assert (tmp_path/'answer.py').read_text() == 'answer = 0'


def test_sdk_mutation_permission_boundary(tmp_path):
    result=run(project(tmp_path),permissions=Permissions(allow_exec=True,execute_builder=True))
    assert result['status'] == 'blocked'
    assert (tmp_path/'answer.py').read_text() == 'answer = 0'


def test_budget_admission_before_builder(tmp_path):
    result=run(project(tmp_path,budget={'max_cost_usd':'1','builder_upper_bound_usd':'0.8',
        'verifier_reserve_usd':'0.3'}),permissions=Permissions(allow_exec=True,execute_builder=True,unsafe_host=True))
    assert result['status'] == 'budget_exhausted'
    assert (tmp_path/'answer.py').read_text() == 'answer = 0'


def test_required_critic_cannot_be_silently_skipped(tmp_path):
    result=run(project(tmp_path,budget={'max_cost_usd':'1','builder_upper_bound_usd':'0.5'}),
        permissions=Permissions(allow_exec=True,execute_builder=True,unsafe_host=True),use_ai=True)
    assert result['status'] != 'passed'

