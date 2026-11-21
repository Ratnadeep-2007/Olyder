"""Smoke a freshly installed Olyder *wheel*, not an editable source checkout."""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import olyder


def _run(*args: str, cwd: Path | None = None, exit_code: int = 0) -> str:
    outcome = subprocess.run(
        [sys.executable, "-m", "olyder", *args],
        cwd=cwd, capture_output=True, text=True, timeout=30,
    )
    assert outcome.returncode == exit_code, (args, outcome.returncode, outcome.stderr)
    return outcome.stdout


def main() -> None:
    version = "0.5.0b1"
    assert importlib.metadata.version("olyder") == version
    assert olyder.__version__ == version
    assert version in _run("--version")
    assert "setup" in _run("--help")
    diagnostics = json.loads(_run("doctor"))
    assert "agents" in diagnostics
    with tempfile.TemporaryDirectory(prefix="olyder-wheel-smoke-") as d:
        project = Path(d)
        out = _run("setup", "opencode", "--project", str(project))
        assert "Ready for opencode" in out
        for directory in (".agents", ".opencode"):
            path = project / directory / "skills/olyder/SKILL.md"
            assert path.is_file()
            assert "description:" in path.read_text(encoding="utf-8")
        assert "Already installed" in _run("setup", "opencode", "--project", str(project))
        assert not (project / "olyder.json").exists(), "Setup must never invent a project contract"
        for flags, status, code in [((), "passed", 0), (("--fail",), "failed", 1)]:
            demo = json.loads(_run("demo", *flags, cwd=project, exit_code=code))
            assert demo["status"] == status
            assert demo["budget"]["spent"] == 0
            assert (project / demo["paths"]["html"]).is_file()
            report = json.loads((project / demo["paths"]["json"]).read_text(encoding="utf-8"))
            assert report["metrics"]["execution_coverage_percent"] == 100
        assert not (project / "olyder.json").exists()
    print("Installed-wheel smoke passed (version, doctor, native skill, offline pass/fail reports)")


if __name__ == "__main__":
    main()
