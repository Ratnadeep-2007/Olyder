import json
import sys

import pytest

from olyder.impact import select_checks
from olyder.sdk import Permissions, resume, run
from olyder.state import RunStore


CHECKS=[{'id':'a','type':'command','paths':['a.py'],'depends_on':[]},
        {'id':'b','type':'command','paths':['b.py'],'depends_on':['a']},
        {'id':'http','type':'http'}]


def test_explicit_mapping_and_dependents():
    selected,reason=select_checks(CHECKS,{'a.py'},set())
    assert selected=={'a','b','http'}
    assert reason=='explicit_dependency_mapping'


def test_failed_check_always_eligible():
    selected,_=select_checks(CHECKS,{'b.py'},{'a'})
    assert 'a' in selected


@pytest.mark.parametrize('checks,changed', [
    ([{'id':'a','type':'command'}],{'a.py'}),
    ([{'id':'a','type':'command','paths':['a.py'],'depends_on':['missing']}],{'a.py'}),
    ([{'id':'a','type':'command','paths':['a.py'],'depends_on':['a']}],{'a.py'}),
    (CHECKS,{'unknown.py'}),
    ([{'id':'a','type':'command','paths':'a.py'}],{'a.py'})])
def test_ambiguous_impact_runs_full(checks,changed):
    assert select_checks(checks,changed,set())[0]=={c['id'] for c in checks}


def test_resume_rechecks_without_rebuilding(tmp_path):
    path=tmp_path/'olyder.json'
    (tmp_path/'value').write_text('ok')
    path.write_text(json.dumps({'goal':'ok','checks':[{'id':'file','type':'file','path':'value'}]}))
    first=run(path)
    resumed=resume(first['run_id'],tmp_path)
    assert resumed['status']=='passed'
    assert resumed['resumed_verification_only']


def test_uncertain_builder_is_never_replayed(tmp_path):
    store=RunStore(tmp_path/'.olyder'/'runs')
    state=store.create({'phase':'builder_started'})
    result=resume(state['run_id'],tmp_path)
    assert result['status']=='blocked'
    assert result['stop_reason']=='uncertain_inflight_execution'


def test_full_final_suite_catches_unsound_declared_mapping(tmp_path):
    (tmp_path/'a').write_text('0');(tmp_path/'b').write_text('0')
    value="int(open('a').read().split('#')[0])"
    builder="from pathlib import Path;p=Path('a');p.write_text('1' if '#first' in p.read_text() else '0#first')"
    config={'goal':'Do not miss a hidden regression','incremental':True,
        'builder':{'argv':[sys.executable,'-c',builder]},'checks':[
            {'id':'a','type':'command','paths':['a'],'argv':[sys.executable,'-c','assert '+value+'==1']},
            {'id':'hidden','type':'command','paths':['b'],'argv':[sys.executable,'-c','assert '+value+'==0']}],
        'limits':{'max_seconds':30,'max_iterations':3}}
    path=tmp_path/'olyder.json';path.write_text(json.dumps(config))
    result=run(path,permissions=Permissions(allow_exec=True,execute_builder=True,unsafe_host=True))
    assert result['status']=='failed'
    assert result['full_suite_executed']
    assert result['checks'][1]['status']=='fail'
    assert result['verification_selection'][1]['selected']==['a']
