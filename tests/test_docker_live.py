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
