"""Skill discovery paths and install safety across project and global scopes."""
from pathlib import Path

import pytest

from olyder.cli import main


def test_opencode_project_uses_both_native_and_compat_paths(tmp_path):
    assert main(["setup", "opencode", "--project", str(tmp_path)]) == 0
    assert (tmp_path / ".opencode/skills/olyder/SKILL.md").is_file()
    assert (tmp_path / ".agents/skills/olyder/SKILL.md").is_file()
    assert not (tmp_path / ".claude").exists()


def test_global_one_command_installs_all_native_paths(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    files = [
        home / ".config/opencode/skills/olyder/SKILL.md",
        home / ".gemini/config/skills/olyder/SKILL.md",
        home / ".claude/skills/olyder/SKILL.md",
        home / ".agents/skills/olyder/SKILL.md",
    ]
    assert main(["setup", "--global"]) == 0
    contents = [f.read_text(encoding="utf-8") for f in files]
    assert len(set(contents)) == 1
    assert "description:" in contents[0].split("---", 2)[1]
    before = [f.stat().st_mtime_ns for f in files]
    capsys.readouterr()
    assert main(["setup", "--global"]) == 0
    assert capsys.readouterr().out.count("Already installed") == len(files)
    assert [f.stat().st_mtime_ns for f in files] == before
    assert not (tmp_path / ".agents").exists()  # No project files created.


def test_global_opencode_only_and_gemini_alias(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    assert main(["setup", "opencode", "-g"]) == 0
    assert (home / ".config/opencode/skills/olyder/SKILL.md").is_file()
    assert not (home / ".agents/skills/olyder/SKILL.md").exists()
    assert main(["install-skill", "--target", "gemini", "--global"]) == 0
    assert (home / ".gemini/config/skills/olyder/SKILL.md").is_file()


def test_global_preflight_prevents_partial_install(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    customized = home / ".config/opencode/skills/olyder/SKILL.md"
    customized.parent.mkdir(parents=True)
    customized.write_text("custom skill", encoding="utf-8")
    assert main(["setup", "--global"]) == 2
    assert customized.read_text(encoding="utf-8") == "custom skill"
    assert not (home / ".gemini/config/skills/olyder/SKILL.md").exists()
    assert main(["setup", "--global", "--force"]) == 0
    assert customized.read_text(encoding="utf-8").startswith("---\nname: olyder")


def test_global_install_skill_preserves_non_idempotent_legacy_behavior(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    args = ["install-skill", "--target", "opencode", "--global"]
    assert main(args) == 0
    assert main(args) == 2
    assert main(args + ["--force"]) == 0


def test_symlinked_project_skill_directory_is_rejected(tmp_path):
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    agents = project / ".agents"
    try:
        agents.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Current OS does not permit symlinks")
    assert main(["setup", "antigravity", "--project", str(project), "--force"]) == 2
    assert not (outside / "skills/olyder/SKILL.md").exists()
