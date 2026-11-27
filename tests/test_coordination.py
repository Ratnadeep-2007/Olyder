import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from olyder import coordination as tasks
from olyder.cli import main
from olyder.sdk import Permissions
from olyder.state import RunStore


KEY = "controller-fixture-key-with-sufficient-length"


def setup_task(tmp_path, **options):
    (tmp_path / "answer.txt").write_text("0")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "oracle.py").write_text(
        "from pathlib import Path\n"
        "assert Path('answer.txt').read_text() == '42', 'Expected answer 42'\n"
    )
    spec = tmp_path / "olyder.json"
    spec.write_text(json.dumps({
        "schema_version": 2, "goal": "Return the expected answer",
        "requirements": [{"id": "correct-answer", "text": "The answer is 42",
                          "acceptance_check_ids": ["oracle"]}],
        "checks": [{"id": "oracle", "type": "command",
                    "argv": [sys.executable, "tests/oracle.py"], "paths": ["answer.txt"]}],
        **options,
    }))
    return tasks.open_task(spec, agent_id="builder-a", controller_key=KEY)


def test_external_agent_submits_repairs_and_controller_completes(tmp_path):
    task = setup_task(tmp_path)
    identifier = task["run_id"]
    proposal = Path(task["proposal"])
    assert not (proposal / "tests").exists()
    assert task["task_plan"]["tasks"][0]["requirement_ids"] == ["correct-answer"]
    assert KEY not in json.dumps(RunStore(tmp_path / ".olyder/runs").read(identifier))

    tasks.submit_task(tmp_path, identifier, task["proposal_revision"], agent_id="builder-a")
    with pytest.raises(tasks.TaskError, match="approval"):
        tasks.task_gate(tmp_path, identifier, task["proposal_revision"])
    blocked = tasks.verify_task(tmp_path, identifier, controller_key=KEY)
    assert blocked["phase"] == "blocked"
    assert blocked["result"]["checks"][0]["status"] == "blocked"
    tasks.submit_task(tmp_path, identifier, task["proposal_revision"], agent_id="builder-a")
    failure = tasks.verify_task(tmp_path, identifier, controller_key=KEY,
                                permissions=Permissions(allow_exec=True))
    assert failure["phase"] == "repair_required"
    repair = failure["repair"]
    assert repair["event"] == "repair.requested"
    assert repair["recipient_agent_id"] == "builder-a"
    finding = repair["findings"][0]
    assert finding["requirement_ids"] == ["correct-answer"]
    assert finding["evidence_ref"] == "checks/oracle"
    assert "Expected answer 42" in finding["observation"]
    assert repair["spec_sha256"] == task["spec_sha256"]

    (proposal / "answer.txt").write_text("42")
    current = tasks.task_status(tmp_path, identifier)
    with pytest.raises(tasks.TaskError, match="revision"):
        tasks.submit_task(tmp_path, identifier, task["proposal_revision"], agent_id="builder-a")
    tasks.submit_task(tmp_path, identifier, current["proposal_revision"], agent_id="builder-a")
    verified = tasks.verify_task(tmp_path, identifier, controller_key=KEY,
                                 permissions=Permissions(allow_exec=True))
    assert verified["phase"] == "verified"
    assert verified["result"]["budget"]["calls"] == 0
    with pytest.raises(tasks.TaskError, match="controller"):
        tasks.complete_task(tmp_path, identifier, current["proposal_revision"], controller_key="wrong")
    approved = tasks.complete_task(tmp_path, identifier, current["proposal_revision"], controller_key=KEY)
    assert approved["phase"] == "completed"
    assert approved["completion"]["event"] == "completion.approved"
    assert tasks.complete_task(tmp_path, identifier, current["proposal_revision"], controller_key=KEY) == approved
    assert approved["completion"]["proposal_revision"] == current["proposal_revision"]
    assert tasks.task_gate(tmp_path, identifier, current["proposal_revision"]) == approved["completion"]
    Path(approved["completion"]["evidence"]["json"]).write_text("{}")
    with pytest.raises(tasks.TaskError, match="report changed"):
        tasks.task_gate(tmp_path, identifier, current["proposal_revision"])
    assert (tmp_path / "answer.txt").read_text() == "0"


def test_verified_revision_cannot_approve_changed_proposal(tmp_path):
    task = setup_task(tmp_path)
    proposal = Path(task["proposal"])
    (proposal / "answer.txt").write_text("42")
    current = tasks.task_status(tmp_path, task["run_id"])
    revision = current["proposal_revision"]
    tasks.submit_task(tmp_path, task["run_id"], revision, agent_id="builder-a")
    tasks.verify_task(tmp_path, task["run_id"], controller_key=KEY,
                      permissions=Permissions(allow_exec=True))
    (proposal / "answer.txt").write_text("0")
    with pytest.raises(tasks.TaskError, match="revision"):
        tasks.complete_task(tmp_path, task["run_id"], revision, controller_key=KEY)


def test_cli_task_flow_and_controller_credential_isolation(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("OLYDER_TASK_CONTROLLER_KEY", KEY)
    spec = tmp_path / "olyder.json"
    spec.write_text(json.dumps({"goal": "Keep the controller key private", "checks": [
        {"id": "environment", "type": "command",
         "argv": [sys.executable, "-c", "import os; assert 'OLYDER_TASK_CONTROLLER_KEY' not in os.environ"]},
    ]}))

    def invoke(*args):
        code = main(["task", *args])
        output = capsys.readouterr()
        assert code == 0, output.err
        assert KEY not in output.out
        return json.loads(output.out)

    task = invoke("open", "--spec", str(spec), "--agent-id", "builder-a")
    identity = [task["run_id"], "--workspace", str(tmp_path)]
    revision = ["--revision", task["proposal_revision"]]
    invoke("submit", *identity, *revision, "--agent-id", "builder-a")
    assert invoke("verify", *identity, "--allow-exec")["phase"] == "verified"
    assert invoke("complete", *identity, *revision)["phase"] == "completed"
    monkeypatch.delenv("OLYDER_TASK_CONTROLLER_KEY")
    assert invoke("gate", *identity, *revision)["gate"] == "open"


def test_one_verifier_claims_submission_and_cancellation_closes_gate(tmp_path, monkeypatch):
    task = setup_task(tmp_path)
    run_id, revision = task["run_id"], task["proposal_revision"]
    tasks.submit_task(tmp_path, run_id, revision, agent_id="builder-a")
    entered, release = Event(), Event()
    verify = tasks._verify_saved_proposal

    def pause(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return verify(*args, **kwargs)

    monkeypatch.setattr(tasks, "_verify_saved_proposal", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(tasks.verify_task, tmp_path, run_id, controller_key=KEY)
        try:
            assert entered.wait(timeout=10)
            with pytest.raises(tasks.TaskError, match="pending submission"):
                tasks.verify_task(tmp_path, run_id, controller_key=KEY)
            with pytest.raises(tasks.TaskError, match="accepting submissions"):
                tasks.submit_task(tmp_path, run_id, revision, agent_id="builder-a")
            RunStore(tmp_path / ".olyder/runs").cancel(run_id)
        finally:
            release.set()
        assert pending.result(timeout=10)["phase"] == "cancelled"
    with pytest.raises(tasks.TaskError, match="approval"):
        tasks.task_gate(tmp_path, run_id, revision)
