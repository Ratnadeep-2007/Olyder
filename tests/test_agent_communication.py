import json
from pathlib import Path

import pytest

from olyder import communication as comm
from olyder import coordination as task
from olyder.herdr_transport import HerdrTransport
from olyder.mcp import process
from olyder.sdk import Permissions
from olyder.state import StateError


KEY = "controller-fixture-key-for-communication-tests"


def project(tmp_path):
    path = tmp_path / "olyder.json"
    (tmp_path / "answer.txt").write_text("0")
    path.write_text(json.dumps({"goal": "Answer 42", "checks": [
        {"id": "answer", "type": "file", "path": "answer.txt", "contains": "42"},
    ]}))
    return path


def test_dynamic_roles_route_and_preserve_messages_across_reconnect(tmp_path):
    spec = project(tmp_path)
    comm.register(tmp_path, "a", "s1", role="reviewer", capabilities=["python"])
    comm.register(tmp_path, "b", "s2", role="builder", capabilities=["python"])
    assert comm.route(tmp_path, ["python"])["agent_id"] == "b"
    comm.change_role(tmp_path, "a", "builder")
    assert comm.route(tmp_path, ["python"])["agent_id"] == "a"
    comm.disconnect(tmp_path, "a")
    opened = task.open_task(spec, controller_key=KEY, required_capabilities=["python"])
    assert opened["agent_id"] == "b"
    assigned, = comm.inbox(tmp_path, "b", "s2")
    assert assigned["event"] == "task.assigned"
    assert assigned["proposal"] == opened["proposal"]
    comm.disconnect(tmp_path, "b")
    comm.register(tmp_path, "b", "s2", role="builder", capabilities=["python"])
    assert comm.inbox(tmp_path, "b", "s2") == [assigned]
    comm.acknowledge(tmp_path, "b", "s2", assigned["message_id"])
    comm.acknowledge(tmp_path, "b", "s2", assigned["message_id"])
    assert comm.inbox(tmp_path, "b", "s2") == []
    comm.register(tmp_path, "b", "new-session", role="builder", capabilities=["python"])
    assert comm.inbox(tmp_path, "b", "new-session") == []
    with pytest.raises((comm.CommunicationError, task.TaskError)):
        task.submit_task(tmp_path, opened["run_id"], opened["proposal_revision"],
                         agent_id="b", agent_session="new-session")


def test_mcp_submission_and_repair_use_bound_session(tmp_path):
    spec = project(tmp_path)
    comm.register(tmp_path, "builder", "session", role="builder", capabilities=["python"])
    opened = task.open_task(spec, agent_id="builder", controller_key=KEY)
    run_id = opened["run_id"]

    def call(name, arguments, binding=("builder", "session"), **options):
        reply = process({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": name, "arguments": arguments}},
                        tmp_path, task_agent=binding, **options)
        assert not reply["result"]["isError"], reply
        return json.loads(reply["result"]["content"][0]["text"])

    assigned, = call("olyder_agent_inbox", {})["messages"]
    call("olyder_agent_ack", {"message_id": assigned["message_id"]})
    submission = {"run_id": run_id, "revision": opened["proposal_revision"]}
    result = call("olyder_task_submit", submission, task_controller_key=KEY,
                  task_permissions=Permissions())
    assert result["phase"] == "repair_required"
    repeated = call("olyder_task_submit", submission, task_controller_key=KEY,
                    task_permissions=Permissions())
    assert repeated["attempt"] == result["attempt"] == 1
    repair, = call("olyder_agent_inbox", {})["messages"]
    assert repair["event"] == "repair.requested"
    assert repair["findings"][0]["check_id"] == "answer"
    (Path(opened["proposal"]) / "answer.txt").write_text("42")
    revision = call("olyder_task_status", {"run_id": run_id})["proposal_revision"]
    assert call("olyder_task_submit", {"run_id": run_id, "revision": revision},
                task_controller_key=KEY, task_permissions=Permissions())["phase"] == "verified"
    with pytest.raises(task.TaskError, match="approval"):
        task.task_gate(tmp_path, run_id, revision)
    task.complete_task(tmp_path, run_id, revision, controller_key=KEY)
    assert task.task_gate(tmp_path, run_id, revision)["event"] == "completion.approved"


def test_default_mcp_does_not_expose_agent_operations(tmp_path):
    reply = process({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, tmp_path)
    assert {tool["name"] for tool in reply["result"]["tools"]} == {"olyder_plan", "olyder_verify"}


def test_mcp_cannot_switch_agent_or_supply_privileged_arguments(tmp_path):
    opened = task.open_task(project(tmp_path), agent_id="manual", controller_key=KEY)
    comm.register(tmp_path, "other", "session", role="leader")
    for name, arguments in (
        ("olyder_task_status", {"run_id": opened["run_id"]}),
        ("olyder_task_submit", {"run_id": opened["run_id"], "revision": opened["proposal_revision"],
                               "agent_id": "manual", "allow_exec": True}),
    ):
        reply = process({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                         "params": {"name": name, "arguments": arguments}},
                        tmp_path, task_agent=("other", "session"))
        assert reply["result"]["isError"]
    assert task.task_status(tmp_path, opened["run_id"])["phase"] == "assigned"


def test_herdr_timeout_preserves_pull_delivery_without_duplicate_push(tmp_path, monkeypatch):
    transport = HerdrTransport()
    observed = {"agent": "editor", "pane_id": "w1:p2", "workspace_id": "w1", "agent_status": "idle",
                "agent_session": {"source": "herdr:editor", "kind": "id", "value": "session-a"}}
    pushes = []

    def call(operation, *args, **_options):
        if operation == "list":
            return {"agents": [observed, {**observed, "pane_id": "w2:p2", "workspace_id": "w2"}]}
        if operation == "get":
            return {"agent": observed}
        pushes.append(args)
        raise comm.CommunicationError("timeout")

    monkeypatch.setattr(transport, "_call", call)
    assert len(transport.discover("w1")) == 1
    entry = transport.enroll(tmp_path, "editor", workspace_id="w1", pane="w1:p2",
                             role="builder", capabilities=["python"])
    task.open_task(project(tmp_path), controller_key=KEY, required_capabilities=["python"])
    outcome = transport.push(tmp_path, "editor")
    assert outcome["status"] == "uncertain"
    assert transport.push(tmp_path, "editor")["status"] == "empty"
    assert len(pushes) == 1
    assert "Answer 42" not in pushes[0][1]
    message, = comm.inbox(tmp_path, "editor", entry["session"])
    assert message["message_id"] == outcome["message_id"]
    assert message["delivery_status"] == "uncertain"
    comm.acknowledge(tmp_path, "editor", entry["session"], outcome["message_id"])
    assert comm.inbox(tmp_path, "editor", entry["session"]) == []


def test_failed_outbox_insert_rolls_back_task_transition(tmp_path):
    comm.register(tmp_path, "editor", "session", role="builder")
    opened = task.open_task(project(tmp_path), agent_id="editor", controller_key=KEY)
    store = comm.store_for(tmp_path)
    state = store.read(opened["run_id"])
    assigned, = comm.inbox(tmp_path, "editor", "session")
    duplicate = (assigned["message_id"], "editor", "session", json.dumps(assigned))

    with pytest.raises(StateError):
        store.update(opened["run_id"], state["revision"], {"phase": "task_verified"},
                     notification=duplicate)

    assert store.read(opened["run_id"]) == state
    assert comm.inbox(tmp_path, "editor", "session") == [assigned]
