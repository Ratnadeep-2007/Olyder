"""Zero-model, no-network Antigravity quick-setup regression checks."""
from olyder.cli import main


def test_antigravity_quick_setup_is_idempotent(tmp_path, capsys):
    args = ["setup", "antigravity", "--project", str(tmp_path)]
    assert main(args) == 0
    skill = tmp_path / ".agents" / "skills" / "olyder" / "SKILL.md"
    assert skill.is_file()
    content = skill.read_text(encoding="utf-8")
    assert content.startswith("---\nname: olyder\ndescription: ")
    assert "summary:" not in content.split("---", 2)[1]
    before = skill.stat().st_mtime_ns
    capsys.readouterr()
    assert main(args) == 0
    assert "Already installed" in capsys.readouterr().out
    assert skill.stat().st_mtime_ns == before


def test_default_setup_targets_antigravity(tmp_path):
    assert main(["setup", "--project", str(tmp_path)]) == 0
    assert (tmp_path / ".agents" / "skills" / "olyder" / "SKILL.md").is_file()
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / "olyder.json").exists()


def test_customized_skill_is_never_silently_overwritten(tmp_path, capsys):
    file = tmp_path / ".agents" / "skills" / "olyder" / "SKILL.md"
    file.parent.mkdir(parents=True)
    file.write_text("my custom skill", encoding="utf-8")
    assert main(["setup", "antigravity", "--project", str(tmp_path)]) == 2
    assert file.read_text(encoding="utf-8") == "my custom skill"
    assert "Existing skill" in capsys.readouterr().err
    assert main(["setup", "antigravity", "--project", str(tmp_path), "--force"]) == 0
    assert "name: olyder" in file.read_text(encoding="utf-8")


def test_install_skill_explicit_antigravity_alias(tmp_path):
    assert main(["install-skill", "--target", "antigravity", "--project", str(tmp_path)]) == 0
    assert (tmp_path / ".agents" / "skills" / "olyder" / "SKILL.md").exists()


def test_setup_other_editor_targets(tmp_path):
    assert main(["setup", "claude", "--project", str(tmp_path)]) == 0
    assert (tmp_path / ".claude" / "skills" / "olyder" / "SKILL.md").is_file()
    assert main(["setup", "opencode", "--project", str(tmp_path)]) == 0
    assert (tmp_path / ".agents" / "skills" / "olyder" / "SKILL.md").is_file()


def test_setup_rejects_missing_project(tmp_path, capsys):
    assert main(["setup", "--project", str(tmp_path / "missing")]) == 2
    assert "Project directory does not exist" in capsys.readouterr().err
