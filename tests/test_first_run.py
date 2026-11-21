"""Exercise the public CLI from an empty working directory."""
import json
from pathlib import Path

import pytest

from olyder.cli import main


@pytest.mark.parametrize(("flags", "code", "status"), [
    ([], 0, "passed"),
    (["--fail"], 1, "failed"),
])
def test_demo_reports_real_verification(tmp_path, monkeypatch, capsys, flags, code, status):
    monkeypatch.chdir(tmp_path)
    assert main(["demo", *flags]) == code
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == status
    assert summary["budget"]["spent"] == 0
    assert Path(summary["paths"]["html"]).is_file()
    assert Path(summary["paths"]["markdown"]).is_file()
    report = json.loads(Path(summary["paths"]["json"]).read_text(encoding="utf-8"))
    assert report["status"] == status
    assert report["verification_target"] == "built_in_demo"
    assert not report.get("artifact_refs")
    assert report["metrics"]["execution_coverage_percent"] == 100
    assert [check["status"] for check in report["checks"]] == [
        "pass", "pass" if code == 0 else "fail",
    ]
    assert not (tmp_path / "olyder.json").exists()


def test_demo_keeps_other_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    normal_report = tmp_path / ".olyder" / "report.json"
    normal_report.parent.mkdir()
    normal_report.write_text("existing report", encoding="utf-8")
    paths = []
    for flags, exit_code in [([], 0), (["--fail"], 1)]:
        assert main(["demo", *flags]) == exit_code
        paths.append(Path(json.loads(capsys.readouterr().out)["paths"]["json"]))
    assert paths[0] != paths[1]
    assert all(path.is_file() for path in paths)
    assert normal_report.read_text(encoding="utf-8") == "existing report"


def test_missing_spec_explains_how_to_start(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["verify"]) == 2
    error = capsys.readouterr().err
    assert "olyder init" in error
    assert "--spec PATH" in error
    assert not (tmp_path / ".olyder").exists()


def test_blocked_check_counts_as_selected_only(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("Install here", encoding="utf-8")
    (tmp_path / "olyder.json").write_text(json.dumps({
        "goal": "Verify documentation and unit checks",
        "checks": [
            {"id": "readme", "type": "file", "path": "README.md", "contains": "Install"},
            {"id": "unit", "type": "command", "argv": ["python", "-m", "unittest"]},
        ],
    }), encoding="utf-8")
    assert main(["verify"]) == 1
    summary = json.loads(capsys.readouterr().out)
    report = json.loads(Path(summary["paths"]["json"]).read_text(encoding="utf-8"))
    assert report["status"] == "blocked"
    assert report["full_suite_selected"] is True
    assert report["full_suite_executed"] is False
    assert report["metrics"]["executed_checks"] == 1
    assert report["metrics"]["blocked_checks"] == 1
