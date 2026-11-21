"""The published cart walkthrough demonstrates both verdicts on real tests."""

import json
from pathlib import Path
import subprocess
import sys


def test_reviewed_cart_replay_keeps_the_contract_and_project(tmp_path, monkeypatch):
    example = Path(__file__).resolve().parents[1] / "examples" / "demo-app"
    implementation = (example / "pricing.py").read_bytes()
    spec = (example / "olyder.json").read_bytes()
    output = tmp_path / "report folder"
    monkeypatch.setenv("PATH", str(tmp_path))

    result = subprocess.run(
        [sys.executable, str(example / "replay_regression.py"), "--output", str(output)],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    failed = json.loads((output / "discount-regression" / "report.json").read_text(encoding="utf-8"))
    passed = json.loads((output / "discount-fixed" / "report.json").read_text(encoding="utf-8"))
    assert failed["status"] == "failed"
    assert passed["status"] == "passed"
    assert failed["spec_sha256"] == passed["spec_sha256"]
    assert failed["budget"]["calls"] == passed["budget"]["calls"] == 0
    assert "test_discount" in failed["checks"][1]["details"]
    assert "Ran 3 tests" in passed["checks"][1]["details"]
    assert (example / "pricing.py").read_bytes() == implementation
    assert (example / "olyder.json").read_bytes() == spec
