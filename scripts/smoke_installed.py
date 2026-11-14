"""Smoke a freshly installed Olyder *wheel*, not an editable source checkout."""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import olyder


def _run(*args: str) -> str:
    outcome = subprocess.run(
        [sys.executable, "-m", "olyder", *args],
        capture_output=True, text=True, check=True, timeout=30,
    )
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
    print("Installed-wheel smoke passed (version, doctor, native OpenCode skill, repeat setup)")


if __name__ == "__main__":
    main()
