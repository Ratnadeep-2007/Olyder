import json
import sys
import textwrap

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


def test_builder_repairs_using_bounded_structured_feedback(tmp_path):
    builder = textwrap.dedent("""
        import json
        import sys
        from pathlib import Path

        prompt = json.loads(sys.argv[1])
        assert Path(sys.argv[2]) == Path.cwd()
        if prompt["feedback_untrusted"].startswith("Implement"):
            print("All tests passed")  # The verifier must still find the defect.
        else:
            repair = json.loads(prompt["feedback_untrusted"])
            assert prompt["schema_version"] == 1
            assert prompt["attempt"] == 2
            assert len(prompt["run_id"]) == 32
            assert len(prompt["spec_sha256"]) == 64
            assert len(prompt["feedback_untrusted"]) <= 8000
            assert repair["omitted_failures"] > 0
            assert repair["total_failures"] == len(repair["repair"]) + repair["omitted_failures"] == 10
            first = repair["repair"][0]
            assert first["check_id"] == "oracle-0"
            assert first["status"] == "fail"
            assert first["type"] == "command"
            assert first["requirement_ids"] == ["correct-answer"]
            assert first["affected_paths"] == ["answer.py"]
            assert "expected 42, got 0" in first["evidence"]
            assert ("{work" + "space}") in first["evidence"]
            assert "fixture-private" not in first["evidence"]
            Path("answer.py").write_text("answer = 42")
    """)
    checks = [
        {
            "id": f"oracle-{i}", "type": "command", "paths": ["answer.py"],
            "argv": [sys.executable, "-c",
                     "from answer import answer; "
                     "print('expected 42, got', answer, '{workspace}', 'token=fixture-private', 'x' * 1500); "
                     "assert answer == 42"],
        }
        for i in range(10)
    ]
    spec = project(
        tmp_path,
        builder={"argv": [sys.executable, "-c", builder, "{prompt}", "{workspace}"]},
        schema_version=2,
        requirements=[{"id": "correct-answer", "text": "Answer must equal 42",
                       "acceptance_check_ids": [check["id"] for check in checks]}],
        checks=checks,
    )
    result = run(spec, permissions=Permissions(allow_exec=True, execute_builder=True, unsafe_host=True))
    assert result["status"] == "passed"
    assert [attempt["status"] for attempt in result["history"]] == ["failed", "passed"]
    assert result["repaired_check_ids"] == [check["id"] for check in checks]
    assert (tmp_path / "answer.py").read_text() == "answer = 42"


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


def test_live_agent_event_metadata_is_private(tmp_path):
    code="import json,time;print(json.dumps({'type':'text','text':'FAKE_PRIVATE_PROMPT'}),flush=True);time.sleep(.15)"
    events=[]
    result=run(project(tmp_path,code),permissions=Permissions(allow_exec=True,execute_builder=True,unsafe_host=True),sink=events.append,max_iterations=1)
    assert any(e['type']=='agent_event' and e['event_type']=='text' for e in events)
    assert 'FAKE_PRIVATE_PROMPT' not in json.dumps(events)


def test_empty_directory_checks_are_preserved(tmp_path):
    (tmp_path/'empty').mkdir()
    path=tmp_path/'olyder.json';path.write_text(json.dumps({'goal':'directory',
        'checks':[{'id':'directory','type':'file','path':'empty'}]}))
    assert run(path)['status']=='passed'


def test_unittest_module_oracle_resolves_to_trusted_file(tmp_path):
    (tmp_path/'test_value.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_value(self): self.assertEqual(1,1)\n')
    path=tmp_path/'olyder.json';path.write_text(json.dumps({'goal':'unittest',
        'checks':[{'id':'unit','type':'command','argv':[sys.executable,'-m','unittest','test_value','-v']}]}))
    assert run(path,permissions=Permissions(allow_exec=True))['status']=='passed'


def test_final_critic_reserve_survives_failed_repair_attempt(tmp_path):
    class Provider:
        api_version=1
        calls=0
        def complete(self,*args,**kwargs):
            self.calls+=1
            return {'content':'{"concerns":[],"note":"Bounded evidence reviewed"}',
                    'usage':{'input_tokens':10,'output_tokens':5,'total_tokens':15}}
    code="from pathlib import Path;p=Path('answer.py');p.write_text('answer = 42' if '#first' in p.read_text() else 'answer = 0 #first')"
    provider=Provider()
    result=run(project(tmp_path,code,budget={'max_cost_usd':'1','builder_upper_bound_usd':'0.2','verifier_reserve_usd':'0.3'}),
        permissions=Permissions(allow_exec=True,execute_builder=True,unsafe_host=True),use_ai=True,model_provider=provider)
    assert result['status']=='passed'
    assert result['attempts']==2
    assert provider.calls==1


def test_strict_unknown_builder_blocks_paid_critic_but_keeps_test_evidence(tmp_path):
    class Provider:
        api_version=1
        def complete(self,*args,**kwargs):
            raise AssertionError('Unknown strict spend must block further paid calls')
    result=run(project(tmp_path,budget={'max_cost_usd':'1','builder_upper_bound_usd':'0.2',
        'verifier_reserve_usd':'0.3','strict':True}),use_ai=True,model_provider=Provider(),
        permissions=Permissions(allow_exec=True,execute_builder=True,unsafe_host=True))
    assert result['status']=='needs_review'
    assert result['checks'][0]['status']=='pass'
    assert result['independent_critic_status']=='budget_unavailable'

