import json
import os
import sys
import tempfile
import time

import pytest

from olyder.adapters import ExecutableAgent,bind_model
from olyder.backends import DockerBackend
from olyder.config import load_spec
from olyder.control import RunControl,ResourceLimit,activate
from olyder.execution import managed_run
from olyder.sdk import run,Permissions
from olyder.state import RunStore
from olyder.workspace import ProtectedWorkspace,WorkspaceViolation


def basic(root,command=None):
    (root/'app.py').write_text('value=1')
    spec=root/'olyder.json';spec.write_text(json.dumps({'goal':'one','checks':[
        {'id':'oracle','type':'command','argv':[sys.executable,'-c',command or 'from app import value;assert value==1']}],
        'builder':{'argv':[sys.executable,'-c','pass']}}))
    return spec


def test_custom_model_not_fabricated():
    with pytest.raises(ValueError):
        bind_model(ExecutableAgent('custom',[sys.executable,'-c','pass']),'not_forwarded')


def test_root_uid_mapping_only_touches_detached_tree(tmp_path,monkeypatch):
    builder=tmp_path/'builder';builder.mkdir();(builder/'app.py').write_text('value=1')
    original=tmp_path/'original';original.mkdir();(original/'keep').write_text('same')
    calls=[]
    monkeypatch.setattr(os,'getuid',lambda:0,raising=False)
    monkeypatch.setattr(os,'chown',lambda path,uid,gid,**kw:calls.append((path,uid,gid)),raising=False)
    DockerBackend().prepare_detached(builder,writable=True)
    assert calls and all(uid==65534 and gid==65534 and __import__('pathlib').Path(path).is_relative_to(builder) for path,uid,gid in calls)
    assert (original/'keep').read_text()=='same'


def test_refused_directory_removal_preserves_original_files(tmp_path):
    root=tmp_path/'project';root.mkdir();spec=basic(root)
    (root/'pkg').mkdir();(root/'pkg'/'main.py').write_text('keep')
    (root/'pkg'/'__pycache__').mkdir();(root/'pkg'/'__pycache__'/'cache').write_text('private')
    ws=ProtectedWorkspace(load_spec(spec),tmp_path/'state')
    (ws.builder/'pkg'/'main.py').unlink();(ws.builder/'pkg').rmdir();ws.harness()
    with pytest.raises(WorkspaceViolation):
        ws.apply()
    assert (root/'pkg'/'main.py').read_text()=='keep'


def test_verifier_output_directory_not_applied_as_source(tmp_path):
    spec=basic(tmp_path,"from pathlib import Path;Path('check-output').mkdir();from app import value;assert value==1")
    result=run(spec,permissions=Permissions(allow_exec=True,execute_builder=True,unsafe_host=True))
    assert result['status']=='passed'
    assert not (tmp_path/'check-output').exists()


def test_verifier_cannot_repair_input_and_claim_proposal_passed(tmp_path):
    spec=basic(tmp_path,"from pathlib import Path;Path('app.py').write_text('value=42');from app import value;assert value==42")
    result=run(spec,permissions=Permissions(allow_exec=True,execute_builder=True,unsafe_host=True))
    assert result['status']=='blocked'
    assert (tmp_path/'app.py').read_text()=='value=1'


def test_report_failure_keeps_terminal_execution_checkpoint(tmp_path,monkeypatch):
    spec=basic(tmp_path)
    def fail(*args,**kwargs):
        raise OSError('fixture report failure')
    monkeypatch.setattr('olyder.sdk.save_report',fail)
    result=run(spec,permissions=Permissions(allow_exec=True))
    state=RunStore(tmp_path/'.olyder'/'runs').read(result['run_id'])
    assert state['phase']=='completed'
    assert result['functional_verdict']=='passed'
    assert result['artifact_status']=='failed'
    assert result['status']=='blocked'


@pytest.mark.skipif(os.name=='nt',reason='POSIX process group after leader exit')
def test_cleanup_group_after_leader_exits(tmp_path):
    marker=tmp_path/'child-survived'
    child=f"import time;from pathlib import Path;time.sleep(.5);Path({str(marker)!r}).write_text('bad')"
    leader=f"import subprocess,sys;subprocess.Popen([sys.executable,'-c',{child!r}]);print('x'*100,flush=True)"
    with activate(RunControl(time.monotonic()+5,max_output_bytes=10)),tempfile.TemporaryFile(mode='w+t') as out:
        with pytest.raises(ResourceLimit):
            managed_run([sys.executable,'-c',leader],cwd=tmp_path,stdout=out,timeout=2)
    time.sleep(.7)
    assert not marker.exists()
