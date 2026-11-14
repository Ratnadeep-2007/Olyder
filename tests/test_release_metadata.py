"""Beta package identity and CLI version must stay synchronized."""
from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

import olyder
from olyder.cli import main


def test_package_metadata_matches_module_version():
    source = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["name"] == "olyder"
    assert metadata["project"]["version"] == olyder.__version__ == "0.5.0b1"
    assert metadata["project"]["requires-python"] == ">=3.11"
    assert "acp" in metadata["project"]["optional-dependencies"]


def test_cli_version_matches_package_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "0.5.0b1" in capsys.readouterr().out


def test_release_workflow_only_triggers_on_published_release():
    workflow = (Path(__file__).resolve().parents[1] / ".github" /
                "workflows" / "release-pypi.yml").read_text(encoding="utf-8")
    assert "types: [published]" in workflow
    assert "environment:" in workflow
    assert "name: pypi" in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "merge-base --is-ancestor HEAD origin/main" in workflow
