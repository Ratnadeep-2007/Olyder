"""Regression coverage for the verified acceptance harness boundary.

These tests exercise both legacy in-place snapshots and the detached
ProtectedWorkspace path that the SDK actually uses. The builder may edit
implementation source, but it may not manufacture or redirect acceptance
assets.
"""
import json
import sys

import pytest

from olyder.config import load_spec
from olyder.integrity import changed, snapshot
from olyder.sdk import Permissions, run
from olyder.workspace import ProtectedWorkspace, WorkspaceViolation


def make_spec(root, checks, **extra):
    path = root / "olyder.json"
    path.write_text(json.dumps({"goal": "verified harness", "checks": checks, **extra}), encoding="utf-8")
    return load_spec(path)


def pytest_command():
    return [sys.executable, "-m", "pytest", "-q"]


# Legacy snapshot path: engine.run_loop still uses these functions.

def test_legacy_snapshot_detects_new_canonical_tree(tmp_path):
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    spec = make_spec(tmp_path, [{"id": "smoke", "type": "file", "path": "app.py"}])
    baseline = snapshot(spec)
    assert baseline == {}

    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "injected.feature").write_text("Feature: bypass\n", encoding="utf-8")

    assert changed(spec, baseline) == ["features"]


def test_legacy_snapshot_detects_new_root_test_file(tmp_path):
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    spec = make_spec(tmp_path, [{"id": "smoke", "type": "file", "path": "app.py"}])
    baseline = snapshot(spec)

    (tmp_path / "test_bypass.py").write_text("assert True\n", encoding="utf-8")

    assert changed(spec, baseline) == ["test_bypass.py"]


def test_legacy_snapshot_detects_edit_and_deletion(tmp_path):
    asset = tmp_path / "test_oracle.py"
    asset.write_text("assert True\n", encoding="utf-8")
    spec = make_spec(tmp_path, [{"id": "oracle", "type": "command", "argv": [sys.executable, "test_oracle.py"]}])
    baseline = snapshot(spec)
    assert "test_oracle.py" in baseline

    asset.write_text("assert False\n", encoding="utf-8")
    assert changed(spec, baseline) == ["test_oracle.py"]

    asset.unlink()
    assert changed(spec, baseline) == ["test_oracle.py"]


def test_legacy_snapshot_protects_existing_pytest_config(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\n[tool.pytest.ini_options]\ntestpaths = ['tests']\n",
        encoding="utf-8",
    )
    spec = make_spec(tmp_path, [{"id": "unit", "type": "command", "argv": pytest_command()}])
    baseline = snapshot(spec)
    assert "pyproject.toml" in baseline

    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\n[tool.pytest.ini_options]\naddopts = '-q'\n",
        encoding="utf-8",
    )
    assert changed(spec, baseline) == ["pyproject.toml"]


def test_legacy_snapshot_detects_new_missing_pytest_config(tmp_path):
    spec = make_spec(tmp_path, [{"id": "unit", "type": "command", "argv": pytest_command()}])
    baseline = snapshot(spec)
    assert "conftest.py" not in baseline

    (tmp_path / "conftest.py").write_text("pytest_plugins = []\n", encoding="utf-8")

    assert changed(spec, baseline) == ["conftest.py"]


def test_legacy_snapshot_leaves_unrelated_config_editable(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    spec = make_spec(tmp_path, [{"id": "smoke", "type": "file", "path": "app.py"}])
    baseline = snapshot(spec)
    assert "pyproject.toml" not in baseline

    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'renamed'\n", encoding="utf-8")

    assert changed(spec, baseline) == []


# Detached proposal path used by sdk.run.

def test_proposal_rejects_new_root_test_file(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    spec = make_spec(root, [{"id": "smoke", "type": "file", "path": "app.py"}])
    workspace = ProtectedWorkspace(spec, tmp_path / "state")

    (workspace.builder / "test_bypass.py").write_text("assert True\n", encoding="utf-8")

    with pytest.raises(WorkspaceViolation, match="test_bypass.py"):
        workspace.harness()


def test_proposal_rejects_new_canonical_directory(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    spec = make_spec(root, [{"id": "smoke", "type": "file", "path": "app.py"}])
    workspace = ProtectedWorkspace(spec, tmp_path / "state")

    (workspace.builder / "specs").mkdir()
    (workspace.builder / "specs" / "injected.md").write_text("bypass\n", encoding="utf-8")

    with pytest.raises(WorkspaceViolation, match="specs"):
        workspace.harness()


def test_proposal_rejects_new_root_conftest_for_pytest(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    spec = make_spec(root, [{"id": "unit", "type": "command", "argv": pytest_command()}])
    workspace = ProtectedWorkspace(spec, tmp_path / "state")

    (workspace.builder / "conftest.py").write_text("pytest_plugins = []\n", encoding="utf-8")

    with pytest.raises(WorkspaceViolation, match="conftest.py"):
        workspace.harness()


def test_proposal_rejects_edit_to_existing_pytest_config(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\n[tool.pytest.ini_options]\ntestpaths = ['tests']\n",
        encoding="utf-8",
    )
    spec = make_spec(root, [{"id": "unit", "type": "command", "argv": pytest_command()}])
    workspace = ProtectedWorkspace(spec, tmp_path / "state")
    assert (workspace.builder / "pyproject.toml").read_bytes() == (root / "pyproject.toml").read_bytes()
    assert (workspace.harness() / "pyproject.toml").read_bytes() == (root / "pyproject.toml").read_bytes()

    (workspace.builder / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\n[tool.pytest.ini_options]\naddopts = '-q'\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceViolation, match="pyproject.toml"):
        workspace.harness()


@pytest.mark.parametrize("name", ["pytest.toml", ".pytest.toml", "pytest.ini", ".pytest.ini"])
def test_proposal_rejects_new_pytest_config_when_missing(tmp_path, name):
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    spec = make_spec(root, [{"id": "unit", "type": "command", "argv": pytest_command()}])
    workspace = ProtectedWorkspace(spec, tmp_path / "state")

    (workspace.builder / name).write_text("# Sample configuration\n", encoding="utf-8")

    with pytest.raises(WorkspaceViolation, match=name):
        workspace.harness()


def test_proposal_allows_source_and_unrelated_config_edits(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    spec = make_spec(root, [{"id": "smoke", "type": "file", "path": "app.py"}])
    workspace = ProtectedWorkspace(spec, tmp_path / "state")
    assert (workspace.builder / "pyproject.toml").exists()

    (workspace.builder / "app.py").write_text("value = 2\n", encoding="utf-8")
    (workspace.builder / "pyproject.toml").write_text("[project]\nname = 'renamed'\n", encoding="utf-8")
    harness = workspace.harness()

    assert (harness / "app.py").read_text(encoding="utf-8") == "value = 2\n"
    assert (harness / "pyproject.toml").read_text(encoding="utf-8") == "[project]\nname = 'renamed'\n"
    workspace.apply()
    assert (root / "app.py").read_text(encoding="utf-8") == "value = 2\n"
    assert (root / "pyproject.toml").read_text(encoding="utf-8") == "[project]\nname = 'renamed'\n"


def test_sdk_rejects_builder_supplied_root_test_file(tmp_path):
    (tmp_path / "answer.py").write_text("answer = 0\n", encoding="utf-8")
    path = tmp_path / "olyder.json"
    path.write_text(json.dumps({
        "goal": "No builder-authored acceptance tests",
        "checks": [{"id": "answer", "type": "file", "path": "answer.py", "contains": "answer = 42"}],
        "builder": {"argv": [sys.executable, "-c",
                             "from pathlib import Path; Path('test_bypass.py').write_text('assert True\\n')"]},
        "limits": {"max_iterations": 1, "max_seconds": 30},
    }), encoding="utf-8")

    result = run(path, permissions=Permissions(allow_exec=True, execute_builder=True, unsafe_host=True))

    assert result["status"] == "blocked"
    assert result["stop_reason"] == "integrity_violation"
    assert "test_bypass.py" in result["verifier_note"]
    assert not (tmp_path / "test_bypass.py").exists()


def test_proposal_keeps_existing_nested_fixtures(tmp_path):
    root = tmp_path / "project"
    fixtures = root / "examples"
    fixtures.mkdir(parents=True)
    (fixtures / "test_demo.py").write_text("assert True\n", encoding="utf-8")
    spec = make_spec(root, [{"id": "file", "type": "file", "path": "examples/test_demo.py"}])
    workspace = ProtectedWorkspace(spec, tmp_path / "state")
    assert (workspace.harness() / "examples" / "test_demo.py").is_file()


def test_proposal_protects_nested_pytest_hooks(tmp_path):
    root = tmp_path / "project"
    package = root / "pkg"
    package.mkdir(parents=True)
    (package / "conftest.py").write_text("# Maintainer fixture\n", encoding="utf-8")
    spec = make_spec(root, [{"id": "unit", "type": "command", "argv": pytest_command()}])
    workspace = ProtectedWorkspace(spec, tmp_path / "state")
    (workspace.builder / "pkg" / "app.py").write_text("value = 2\n", encoding="utf-8")
    harness = workspace.harness()
    assert (harness / "pkg" / "conftest.py").is_file()
    assert (harness / "pkg" / "app.py").is_file()

    new_package = workspace.builder / "example"
    new_package.mkdir()
    (new_package / "conftest.py").write_text("# New fixture\n", encoding="utf-8")
    with pytest.raises(WorkspaceViolation, match="example/conftest.py"):
        workspace.harness()


def test_explicit_private_metadata_stays_out_of_builder(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    spec = make_spec(root, [{"id": "unit", "type": "command", "argv": pytest_command()}],
                     protected_paths=["pyproject.toml"])
    workspace = ProtectedWorkspace(spec, tmp_path / "state")
    assert not (workspace.builder / "pyproject.toml").exists()
    assert (workspace.harness() / "pyproject.toml").is_file()
