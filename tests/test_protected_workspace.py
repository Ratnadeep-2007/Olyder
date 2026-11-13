import json
from pathlib import Path

import pytest

from olyder.config import load_spec
from olyder.workspace import ProtectedWorkspace, WorkspaceViolation


def project(root):
    (root/'tests').mkdir()
    (root/'tests'/'oracle.py').write_text('assert True')
    (root/'app.py').write_text('value = 1')
    (root/'olyder.json').write_text(json.dumps({'goal':'two', 'checks':[
        {'id':'two','type':'file','path':'app.py','contains':'2'}]}))
    return load_spec(root/'olyder.json')


def test_detached_assets_and_proposal(tmp_path):
    root=tmp_path/'project'; root.mkdir()
    workspace=ProtectedWorkspace(project(root), tmp_path/'state')
    assert not (workspace.builder/'tests').exists()
    assert not (workspace.builder/'olyder.json').exists()
    (workspace.builder/'app.py').write_text('value = 2')
    harness=workspace.harness()
    assert (harness/'tests'/'oracle.py').read_text() == 'assert True'
    assert (harness/'app.py').read_text() == 'value = 2'
    assert (root/'app.py').read_text() == 'value = 1'
    workspace.apply()
    assert (root/'app.py').read_text() == 'value = 2'


@pytest.mark.parametrize('path', ['tests/oracle.py','olyder.json','tests/new.py','.env'])
def test_builder_cannot_supply_trusted_assets(tmp_path,path):
    root=tmp_path/'project';root.mkdir()
    workspace=ProtectedWorkspace(project(root),tmp_path/'state')
    target=workspace.builder/path;target.parent.mkdir(exist_ok=True,parents=True)
    target.write_text('spoof')
    with pytest.raises(WorkspaceViolation):
        workspace.harness()


def test_concurrent_original_edit_not_overwritten(tmp_path):
    root=tmp_path/'project';root.mkdir()
    workspace=ProtectedWorkspace(project(root),tmp_path/'state')
    (root/'app.py').write_text('user edit')
    with pytest.raises(WorkspaceViolation):
        workspace.apply()


def test_trusted_snapshot_tampering_blocks(tmp_path):
    root=tmp_path/'project';root.mkdir()
    workspace=ProtectedWorkspace(project(root),tmp_path/'state')
    (workspace.trusted/'tests'/'oracle.py').write_text('spoof')
    with pytest.raises(WorkspaceViolation):
        workspace.harness()
