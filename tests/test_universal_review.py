import io
import json
import os
import sys
import tempfile
import time

import pytest

from olyder.accounting import PricingSnapshot
from olyder.adapters import get_agent
from olyder.control import RunControl, activate, Cancelled
from olyder.execution import managed_run
from olyder.impact import select_checks
from olyder.ledger import BudgetLedger
from olyder.quota import QuotaExceeded
from olyder.workspace import ProtectedWorkspace, WorkspaceViolation, tree
from olyder.config import load_spec


def test_verifier_transfer_is_idempotent():
    ledger=BudgetLedger('run','100',verifier_reserve='20')
    ledger.reserve_verifier('v','10');ledger.reserve_verifier('v','10')
    assert ledger.snapshot()['reserve_remaining']=='10'
    with pytest.raises(QuotaExceeded):
        ledger.reserve('builder','90')


def test_opencode_normalized_cached_input():
    usage=get_agent('opencode').parse(io.StringIO(json.dumps({'type':'step_finish','part':{
        'reason':'stop','tokens':{'input':100,'output':10,'total':130,'cache':{'read':20}}}})))
    assert usage['input_tokens']==120
    assert PricingSnapshot('opencode','fixture','2026-11-13','2','4','1').estimate(usage)=='0.00026'


def test_dynamic_plugin_never_omitted():
    checks=[{'id':'a','type':'file','paths':['a']},{'id':'p','type':'plugin:custom'}]
    assert select_checks(checks,{'a'},set())[0]=={'a','p'}


def test_failed_event_observer_does_not_orphan_child(tmp_path):
    def sink(event):
        raise OSError('observer unavailable')
    control=RunControl(time.monotonic()+5,sink=sink)
    with activate(control),tempfile.TemporaryFile(mode='w+t') as out:
        # Observer failures are recorded without surrendering supervision.
        status=managed_run([sys.executable,'-c','pass'],cwd=tmp_path,stdout=out,timeout=2)
    assert status.returncode==0
    assert control.observer_errors


def test_final_output_limit_is_checked(tmp_path):
    control=RunControl(time.monotonic()+5,max_output_bytes=10)
    with activate(control),tempfile.TemporaryFile(mode='w+t') as out:
        with pytest.raises(Cancelled):
            managed_run([sys.executable,'-c',"print('x'*100)"],cwd=tmp_path,stdout=out,timeout=2)


def test_directory_replaced_by_file_matches_verified_tree(tmp_path):
    root=tmp_path/'project';root.mkdir();(root/'module').mkdir();(root/'module'/'old.py').write_text('old')
    path=root/'olyder.json';path.write_text(json.dumps({'goal':'replace','checks':[{'id':'ok','type':'file','path':'module'}]}))
    ws=ProtectedWorkspace(load_spec(path),tmp_path/'state')
    (ws.builder/'module'/'old.py').unlink();(ws.builder/'module').rmdir();(ws.builder/'module').write_text('new')
    ws.harness();ws.apply()
    assert (root/'module').is_file() and (root/'module').read_text()=='new'


@pytest.mark.skipif(os.name=='nt',reason='POSIX FIFO fixture')
def test_fifo_rejected_before_read(tmp_path):
    os.mkfifo(tmp_path/'fifo')
    with pytest.raises(WorkspaceViolation):
        tree(tmp_path)


def test_explicit_recovery_of_interrupted_verifier(tmp_path):
    from olyder.sdk import run,resume
    from olyder.state import RunStore
    (tmp_path/'value').write_text('ok')
    path=tmp_path/'olyder.json';path.write_text(json.dumps({'goal':'ok','checks':[{'id':'ok','type':'file','path':'value'}]}))
    result=run(path)
    store=RunStore(tmp_path/'.olyder'/'runs');state=store.read(result['run_id'])
    store.update(result['run_id'],state['revision'],{'phase':'verifying'})
    assert resume(result['run_id'],tmp_path,recover=True)['status']=='passed'


def test_configured_model_identity_prices_only_requested_model():
    from olyder.adapters import bind_model
    adapter=bind_model(get_agent('codex'),'fixture-model')
    assert '--model=fixture-model' in adapter.command('task')
    usage=adapter.parse(io.StringIO('{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":2}}'))
    assert usage['model']=='fixture-model'
    assert usage['model_origin']=='requested_configuration'


def test_missing_opencode_counts_are_unknown():
    usage=get_agent('opencode').parse(io.StringIO('{"type":"step_finish","part":{"reason":"stop","tokens":{}}}'))
    assert not usage['usage_complete']
    assert usage['observed_tokens'] is None
