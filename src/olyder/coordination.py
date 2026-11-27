"""Local, pull-based coordination over the protected verifier and RunStore."""
from __future__ import annotations

import hashlib
import hmac
import json
import platform
import re
import time
from pathlib import Path
from uuid import uuid4

from . import __version__, communication
from .config import load_spec
from .control import Cancelled, ResourceLimit, RunControl
from .engine import plan
from .privacy import redact
from .report import save_report
from .sdk import Permissions, _checker_digest, _digest, _verify_saved_proposal
from .state import RunStore
from .workspace import ProtectedWorkspace, directories, file_modes


class TaskError(RuntimeError):
    pass


_SUBMITTABLE = {"assigned", "repair_required", "needs_review", "blocked", "verified"}
_VERDICT_PHASE = {"passed": "verified", "failed": "repair_required", "needs_review": "needs_review",
                  "blocked": "blocked", "cancelled": "cancelled"}
_POLICY_VERSION = 1


def _key_digest(key) -> str:
    if not isinstance(key, str) or not 32 <= len(key) <= 256:
        raise TaskError("A controller key of 32 to 256 characters is required")
    return hashlib.sha256(key.encode()).hexdigest()


def _authorize(state, key):
    if not hmac.compare_digest(_key_digest(key), state["controller_key_digest"]):
        raise TaskError("Invalid controller key")


def _task(workspace, run_id):
    root = Path(workspace).resolve()
    store = RunStore(root / ".olyder" / "runs")
    state = store.read(run_id)
    if state.get("kind") != "external_task":
        raise TaskError("Run is not an external task")
    return root, store, state


def _load_inputs(root, store, state):
    if state["checker_sha256"] != _checker_digest():
        raise TaskError("Verifier changed. Open a new task.")
    path = Path(state["spec_path"])
    contract_path = store.path(state["run_id"]) / "contract.json"
    if path.resolve().parent != root or _digest(path) != state["spec_sha256"]:
        raise TaskError("Approved specification changed")
    spec = load_spec(contract_path)
    if spec.digest != state["spec_sha256"]:
        raise TaskError("Saved contract changed")
    saved = ProtectedWorkspace.reopen(store.path(state["run_id"]) / "workspace", state["manifest_sha256"])
    if saved.root != root:
        raise TaskError("Saved workspace does not match the task")
    return spec, saved


def _verification_input(saved):
    """Describe exactly the files and metadata the harness must start with."""
    proposal = saved.validate()
    trusted = {name: sha for name, sha in saved.baseline.items() if saved.is_protected(name)}
    files = {**trusted, **proposal}
    modes = {**{name: saved.baseline_modes[name] for name in trusted}, **file_modes(saved.builder, proposal)}
    dirs = directories(saved.builder) | {name for name in saved.baseline_dirs if saved.is_protected(name)}
    dirs.update(parent.as_posix() for name in files.keys() | dirs
                for parent in Path(name).parents if parent != Path("."))
    return files, modes, dirs


def _revision(inputs):
    files, modes, dirs = inputs
    return hashlib.sha256(json.dumps([files, modes, sorted(dirs)], sort_keys=True).encode()).hexdigest()


def _require_revision(expected, current):
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or expected != current:
        raise TaskError("Proposal revision is invalid or stale")


def _view(state, saved, revision):
    return {
        "schema_version": 1, "run_id": state["run_id"], "task_id": state["run_id"],
        "phase": "cancelled" if state.get("cancel_requested") else state["phase"].removeprefix("task_"),
        "agent_id": state["agent_id"], "agent_session": state.get("agent_session"), "spec_sha256": state["spec_sha256"],
        "proposal": str(saved.builder), "proposal_revision": revision,
        "submitted_revision": state.get("submitted_revision"),
        "verified_revision": state.get("verified_revision"),
        "attempt": state["attempt"], "task_plan": state["task_plan"],
        "result": state.get("result"), "repair": state.get("repair"),
        "submission": state.get("submission"), "verification": state.get("verification"),
        "completion": state.get("completion"),
    }


def open_task(spec_path, *, agent_id=None, required_capabilities=(), controller_key,
              backend="host", docker_image="python:3.13-slim"):
    """The controller freezes the oracle before handing an isolated proposal to an agent."""
    spec = load_spec(spec_path)
    if agent_id is None:
        selected = communication.route(spec.root, required_capabilities)
        agent_id = selected["agent_id"]
    else:
        if not isinstance(agent_id, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", agent_id):
            raise TaskError("Invalid agent identifier")
        if required_capabilities:
            raise TaskError("Choose an explicit agent or capability routing")
        selected = communication.agent(spec.root, agent_id)
        if selected is not None and not selected["available"]:
            raise TaskError("Selected agent is disconnected")
    if backend not in ("host", "docker"):
        raise TaskError("External tasks require the host or Docker backend")
    key_digest = _key_digest(controller_key)
    limit = spec.raw.get("limits", {}).get("max_iterations", 3)
    if not 1 <= limit <= 20:
        raise TaskError("External task max_iterations must be between 1 and 20")
    store = RunStore(spec.root / ".olyder" / "runs")
    state = store.create({
        "kind": "external_task", "phase": "task_opening",
        "agent_id": agent_id, "agent_session": selected["session"] if selected else None,
        "controller_key_digest": key_digest,
        "spec_path": str(spec.path), "spec_sha256": spec.digest,
        "checker_sha256": _checker_digest(), "execution_backend": backend, "docker_image": docker_image,
        "attempt": 0, "max_attempts": limit, "task_plan": plan(spec),
    })
    run_dir = store.path(state["run_id"])
    contract = run_dir / "contract.json"
    saved = ProtectedWorkspace(spec, run_dir / "workspace")
    contract.write_bytes(spec.path.read_bytes())
    if _digest(contract) != spec.digest:
        raise TaskError("Contract changed during task opening")
    revision = _revision(_verification_input(saved))
    assignment = {**_event(state, "task.assigned"), "proposal": str(saved.builder),
                  "proposal_revision": revision, "goal": spec.goal}
    state = store.update(state["run_id"], state["revision"], {
        "phase": "task_assigned",
        "manifest_sha256": saved.evidence()["manifest_sha256"],
    }, notification=communication.notification(state, assignment))
    return _view(state, saved, revision)


def _check_agent(root, state, agent_id, session):
    if agent_id != state["agent_id"] or session != state.get("agent_session"):
        raise TaskError("Task is assigned to another agent session")
    if session is not None:
        communication.bound_agent(root, agent_id, session)


def task_status(workspace, run_id, *, agent_binding=None):
    root, store, state = _task(workspace, run_id)
    if agent_binding is not None:
        _check_agent(root, state, *agent_binding)
    _spec, saved = _load_inputs(root, store, state)
    return _view(state, saved, _revision(_verification_input(saved)))


def submit_task(workspace, run_id, proposal_revision, *, agent_id, agent_session=None):
    """Record a submission. The sender cannot submit a verdict or permissions."""
    root, store, state = _task(workspace, run_id)
    _check_agent(root, state, agent_id, agent_session)
    if state.get("cancel_requested"):
        raise TaskError("Task is unavailable to the submitting agent")
    phase = state["phase"].removeprefix("task_")
    if phase not in _SUBMITTABLE and phase != "submitted":
        raise TaskError("Task is not accepting submissions")
    _spec, saved = _load_inputs(root, store, state)
    _require_revision(proposal_revision, _revision(_verification_input(saved)))
    if phase == "submitted" and state["submitted_revision"] == proposal_revision:
        return _view(state, saved, proposal_revision)
    if state["attempt"] >= state["max_attempts"]:
        raise TaskError("Task verification attempt limit reached")
    state = store.update(run_id, state["revision"], {
        "phase": "task_submitted", "submitted_revision": proposal_revision,
        "submission": {**_event({**state, "submitted_revision": proposal_revision}, "task.submitted"),
                       "sender": agent_id, "correlation_id": None},
        "verified_revision": None, "result": None, "repair": None, "verification": None,
    })
    return _view(state, saved, proposal_revision)


def _repair(state, result):
    findings = []
    for check in result["checks"]:
        if check["status"] != "fail":
            continue
        check_id = check["id"]
        findings.append({
            "id": hashlib.sha256(f"{state['run_id']}:{check_id}".encode()).hexdigest(),
            "status": "confirmed_failure", "check_id": check_id, "type": check["type"],
            "requirement_ids": [identifier for identifier, coverage in result["requirement_coverage"].items()
                                if check_id in coverage["check_ids"]],
            "observation": check["details"], "evidence_ref": f"checks/{check_id}",
        })
    return {
        **_event(state, "repair.requested"), "recipient_agent_id": state["agent_id"],
        "findings": findings, "protected_acceptance_inputs": True,
        "required_action": "Change implementation files and submit the new proposal revision",
    }


def _event(state, name):
    return {"schema_version": 1, "event": name, "message_id": uuid4().hex,
            "run_id": state["run_id"], "task_id": state["run_id"], "timestamp": time.time(),
            "sender": "olyder", "correlation_id": (state.get("submission") or {}).get("message_id"),
            "attempt": state["attempt"], "spec_sha256": state["spec_sha256"],
            "proposal_revision": state.get("submitted_revision")}


def verify_task(workspace, run_id, *, controller_key, permissions=None):
    root, store, state = _task(workspace, run_id)
    _authorize(state, controller_key)
    permissions = permissions or Permissions()
    if not isinstance(permissions, Permissions) or permissions.execute_builder:
        raise TaskError("External task verification needs verifier-only permissions")
    if state["phase"] != "task_submitted" or state.get("cancel_requested"):
        raise TaskError("Task has no pending submission")
    spec, saved = _load_inputs(root, store, state)
    expected = _verification_input(saved)
    revision = _revision(expected)
    _require_revision(state["submitted_revision"], revision)
    state = store.update(run_id, state["revision"], {
        "phase": "task_verifying", "attempt": state["attempt"] + 1,
    })
    control = RunControl(time.monotonic() + spec.raw.get("limits", {}).get("max_seconds", 600),
                         cancelled=lambda: store.read(run_id).get("cancel_requested", False))
    try:
        result = _verify_saved_proposal(saved, spec, permissions, control,
                                        isolation=state["execution_backend"], image=state["docker_image"],
                                        expected_input=expected)
        _require_revision(revision, _revision(_verification_input(saved)))
        _load_inputs(root, store, state)
        control.check()
    except ResourceLimit:
        result = {"status": "blocked", "stop_reason": "resource_limit"}
    except (Cancelled, KeyboardInterrupt):
        result = {"status": "cancelled", "stop_reason": "user_cancelled"}
    except (OSError, ValueError, RuntimeError) as exc:
        result = {"status": "blocked", "stop_reason": "verification_integrity_or_execution",
                  "verifier_note": redact(str(exc))[:1000]}
    result.update(run_id=run_id, task_id=run_id, proposal_revision=revision, spec_sha256=spec.digest,
                  policy_version=_POLICY_VERSION, checker_sha256=state["checker_sha256"],
                  environment={"python": platform.python_version(), "platform": platform.system(),
                               "olyder": __version__, "backend": state["execution_backend"]})
    try:
        result["paths"] = save_report(result, store.path(run_id) / "attempts" / str(state["attempt"]))
        result["report_sha256"] = _digest(Path(result["paths"]["json"]))
    except OSError:
        result.update(status="blocked", stop_reason="artifact_generation_failed")
    phase = _VERDICT_PHASE[result["status"]]
    latest = store.read(run_id)
    if latest.get("cancel_requested"):
        phase = "cancelled"
        result.update(status="cancelled", stop_reason="user_cancelled")
    elif latest["revision"] != state["revision"]:
        raise TaskError("Task changed during verification")
    verification = {**_event(state, "verification.completed" if phase == "verified"
                             else "verification.blocked" if phase == "blocked"
                             else "verification.finished"), "status": result["status"]}
    repair = _repair(state, result) if phase == "repair_required" else None
    state = store.update(run_id, latest["revision"], {
        "phase": f"task_{phase}", "result": result, "verification": verification,
        "verified_revision": revision if phase == "verified" else None, "repair": repair,
    }, notification=communication.notification(state, repair or verification))
    return _view(state, saved, revision)


def _check_completion(root, store, state, revision):
    _spec, saved = _load_inputs(root, store, state)
    _require_revision(revision, _revision(_verification_input(saved)))
    _require_revision(revision, state["verified_revision"])
    result = state["result"]
    if (result["status"] != "passed" or not result["full_suite_executed"]
            or not result["checks"] or any(check["status"] != "pass" for check in result["checks"])
            or result["policy_version"] != _POLICY_VERSION
            or result["spec_sha256"] != state["spec_sha256"]
            or result["proposal_revision"] != revision):
        raise TaskError("Verification does not support completion")
    if _digest(Path(result["paths"]["json"])) != result["report_sha256"]:
        raise TaskError("Verification report changed")
    return saved, result


def complete_task(workspace, run_id, proposal_revision, *, controller_key):
    """Authorize only the exact verified revision within the local task boundary."""
    root, store, state = _task(workspace, run_id)
    _authorize(state, controller_key)
    if state["phase"] not in ("task_verified", "task_completed") or state.get("cancel_requested"):
        raise TaskError("Task has no eligible verification")
    saved, result = _check_completion(root, store, state, proposal_revision)
    if state["phase"] == "task_completed":
        return _view(state, saved, proposal_revision)
    completion = {
        **_event(state, "completion.approved"),
        "policy_version": _POLICY_VERSION, "checker_sha256": state["checker_sha256"],
        "environment": result["environment"], "check_ids": [check["id"] for check in result["checks"]],
        "evidence": result["paths"], "report_sha256": result["report_sha256"],
        "manifest_sha256": state["manifest_sha256"],
    }
    state = store.update(run_id, state["revision"], {
        "phase": "task_completed", "completion": completion,
    }, notification=communication.notification(state, completion))
    return _view(state, saved, proposal_revision)


def task_gate(workspace, run_id, proposal_revision):
    """Read a current approval without creating one or enabling any execution."""
    root, store, state = _task(workspace, run_id)
    if state["phase"] != "task_completed" or state.get("cancel_requested"):
        raise TaskError("Task has no controller approval")
    _check_completion(root, store, state, proposal_revision)
    if store.read(run_id)["revision"] != state["revision"]:
        raise TaskError("Task changed during gate evaluation")
    return state["completion"]
