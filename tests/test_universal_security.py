import json
import sys

import pytest

from olyder.accounting import PricingSnapshot
from olyder.cli import main
from olyder.ledger import BudgetLedger
from olyder.sdk import Permissions, run
from olyder.state import RunStore, StateError


def test_cached_tokens_subset_not_double_charged():
    pricing=PricingSnapshot('fixture','model','2026-11-13','2','4','1')
    assert pricing.estimate({'input_tokens':100,'cached_tokens':40,'output_tokens':10,'usage_complete':True})=='0.0002'
    assert pricing.estimate({'input_tokens':100,'cached_tokens':101,'output_tokens':10,'usage_complete':True}) is None


def test_ledger_crash_restore_preserves_unknown_and_pending():
    ledger=BudgetLedger('run','1',strict=True)
    ledger.reserve('pending','0.2');ledger.reserve('unknown','0.2');ledger.settle('unknown',None)
    restored=BudgetLedger.restore(json.loads(json.dumps(ledger.checkpoint())))
    assert restored.snapshot()==ledger.snapshot()
    restored.reconcile('unknown','0.1')
    restored.settle('pending','0.2')
    assert restored.snapshot()['spent_actual']=='0.3'


def test_corrupted_database_fails_safely(tmp_path):
    (tmp_path/'runs.sqlite3').write_bytes(b'not a database')
    with pytest.raises(StateError):
        RunStore(tmp_path)


def test_known_credentials_never_snapshotted(tmp_path):
    from olyder.config import load_spec
    from olyder.workspace import ProtectedWorkspace
    project=tmp_path/'project';project.mkdir()
    (project/'.env').write_text('TOKEN=FAKE_SECRET')
    (project/'.npmrc').write_text('FAKE_TOKEN')
    (project/'olyder.json').write_text(json.dumps({'goal':'ok','checks':[{'id':'ok','type':'file','path':'value'}]}))
    detached=ProtectedWorkspace(load_spec(project/'olyder.json'),tmp_path/'state')
    assert not (detached.trusted/'.env').exists()
    assert not (detached.builder/'.npmrc').exists()


def test_prune_requires_explicit_apply_and_retains_uncertain(tmp_path):
    store=RunStore(tmp_path)
    completed=store.create({'phase':'completed','accounting':{}})
    uncertain=store.create({'phase':'builder_started'})
    listed=store.prune(older_than_days=0)
    assert completed['run_id'] in listed['run_ids'] and not listed['deleted']
    assert uncertain['run_id'] not in listed['run_ids']
    store.prune(older_than_days=0,apply=True)
    assert store.read(uncertain['run_id'])['phase']=='builder_started'


def test_custom_model_critic_and_receipt(tmp_path):
    class Provider:
        api_version=1
        def complete(self,prompt,**kwargs):
            assert 'observed_tests' in prompt
            return {'content':'{"concerns":[],"note":"Only supplied evidence reviewed"}',
                'provider':'fixture','model':'fixture','usage':{'input_tokens':10,'output_tokens':5,'total_tokens':15}}
    (tmp_path/'value').write_text('ok')
    path=tmp_path/'olyder.json';path.write_text(json.dumps({'goal':'ok','checks':[
        {'id':'ok','type':'file','path':'value'}], 'budget':{'max_cost_usd':'1','verifier_reserve_usd':'0.2'}}))
    result=run(path,use_ai=True,model_provider=Provider())
    assert result['status']=='passed'
    assert result['accounting']['observations'][0]['observed_tokens']==15
    request=result['accounting']['observations'][0]['request_id']
    state=RunStore(tmp_path/'.olyder'/'runs').reconcile(result['run_id'],request,'0.01','fixture-receipt')
    assert state['accounting']['ledger']['spent_actual']=='0.01'
    assert state['result']['budget_verdict']=='reconciled'


def test_third_party_style_plugin_executes_real_check(tmp_path,capsys):
    from pathlib import Path
    manifest=json.loads((Path(__file__).parents[1]/'examples/plugins/hello-agent.json').read_text())
    manifest['name']='example-conformance-agent';manifest['argv'][0]=sys.executable
    plugin=tmp_path/'manifest.json';plugin.write_text(json.dumps(manifest))
    spec=tmp_path/'olyder.json';spec.write_text(json.dumps({'goal':'greet','builder':{'provider':manifest['name']},
        'checks':[{'id':'oracle','type':'command','argv':[sys.executable,'-c',"from hello import greet;assert greet()=='Hello Olyder'"]}]}))
    assert main(['run','--spec',str(spec),'--output',str(tmp_path/'out'),'--plugin',str(plugin),
        '--grant-plugin',manifest['name'],'--allow-exec','--execute-builder','--unsafe-host'])==0
    assert (tmp_path/'hello.py').exists()
