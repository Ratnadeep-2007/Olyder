"""Optional live Docker security smoke, run in CI with OLYDER_LIVE_DOCKER=1."""
from __future__ import annotations

import os
import shutil

import pytest

from olyder.checks import run_checks

pytestmark = pytest.mark.skipif(
    os.getenv("OLYDER_LIVE_DOCKER") != "1" or shutil.which("docker") is None,
    reason="Real Docker runtime smoke requires OLYDER_LIVE_DOCKER=1 and Docker",
)


def test_readonly_workspace_prevents_test_mutation(tmp_path):
    (tmp_path / "locked.txt").write_text("protected", encoding="utf-8")
    code = ("from pathlib import Path\n"
            "try:\n Path('locked.txt').write_text('tampered')\nexcept OSError:\n raise SystemExit(0)\n"
            "raise SystemExit(1)\n")
    result = run_checks([{"id": "readonly", "type": "command", "argv": ["python", "-c", code], "timeout": 35}],
                        tmp_path, allow_exec=True, sandbox="docker")
    assert result[0].status == "pass", result[0].details
    assert (tmp_path / "locked.txt").read_text(encoding="utf-8") == "protected"


def test_default_container_blocks_external_egress(tmp_path):
    code = ("import socket\n"
            "try:\n socket.create_connection(('1.1.1.1', 443), timeout=1)\n"
            "except OSError:\n raise SystemExit(0)\nraise SystemExit(1)\n")
    result = run_checks([{"id": "egress", "type": "command", "argv": ["python", "-c", code], "timeout": 35}],
                        tmp_path, allow_exec=True, sandbox="docker")
    assert result[0].status == "pass", result[0].details


def test_sdk_builder_cannot_see_detached_oracle(tmp_path):
    import json
    from olyder.sdk import run, Permissions
    (tmp_path/'tests').mkdir()
    (tmp_path/'tests'/'oracle.py').write_text('from answer import value;assert value==42')
    (tmp_path/'answer.py').write_text('value=0')
    builder="from pathlib import Path;assert not Path('tests').exists();assert not Path('olyder.json').exists();Path('answer.py').write_text('value=42')"
    spec=tmp_path/'olyder.json';spec.write_text(json.dumps({'goal':'42',
        'builder':{'argv':['python','-c',builder]},'checks':[{'id':'oracle','type':'command',
            'argv':['python','-c',"exec(open('tests/oracle.py').read())"],'timeout':35}],
        'limits':{'max_seconds':90,'max_iterations':1}}))
    result=run(spec,permissions=Permissions(allow_exec=True,execute_builder=True),backend='docker')
    assert result['status']=='passed', result
    assert (tmp_path/'answer.py').read_text()=='value=42'
    assert (tmp_path/'tests'/'oracle.py').read_text()=='from answer import value;assert value==42'
