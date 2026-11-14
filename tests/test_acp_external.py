"""Real ACP v1 agent-client execution tests; SDK dependency is opt-in."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("acp")

from olyder.acp_external import ACPProcessAgent
from olyder.interfaces import AgentAdapter
from olyder.plugins import load_agent_manifest
from olyder.sdk import Permissions, run


FIXTURE = Path(__file__).parent / "fixtures" / "acp_fixture_agent.py"


def _setup(tmp_path, *, agent_name: str, refuse=False):
    project = tmp_path / "project"
    project.mkdir()
    (project / "answer.py").write_text("answer = 0\n", encoding="utf-8")
    manifest = tmp_path / "agent.json"
    argv = [sys.executable, str(FIXTURE)]
    if refuse:
        argv.append("--refuse")
    manifest.write_text(json.dumps({
        "api_version": 1, "kind": "agent", "name": agent_name,
        "protocol": "acp-v1", "argv": argv,
        "permissions": ["execute", "write_workspace"],
    }), encoding="utf-8")
    spec = project / "olyder.json"
    spec.write_text(json.dumps({
        "goal": "Set answer to 42",
        "builder": {"provider": agent_name},
        "checks": [{"id": "answer", "type": "file",
                    "path": "answer.py", "contains": "answer = 42"}],
        "limits": {"max_iterations": 1, "max_tokens": 10000, "max_seconds": 60},
    }), encoding="utf-8")
    return project, manifest, spec


def test_acp_adapter_is_explicit_capability_not_auto_import(tmp_path):
    project, manifest, _ = _setup(tmp_path, agent_name="acp-test-permission")
    with pytest.raises(PermissionError):
        load_agent_manifest(manifest, grants=set())
    adapter = load_agent_manifest(manifest, grants={"acp-test-permission"})
    assert isinstance(adapter, AgentAdapter)
    assert adapter.capabilities().provider_hard_limit is False
    assert adapter.capabilities().structured_usage is False
    command = adapter.command("make the change")
    assert "-m" in command and "olyder.acp_external" in command
    assert "make the change" == command[-1]


def test_real_acp_client_agent_and_protected_apply(tmp_path):
    project, manifest, spec = _setup(tmp_path, agent_name="acp-test-real-builder")
    load_agent_manifest(manifest, grants={"acp-test-real-builder"})
    events = []
    result = run(spec, permissions=Permissions(
        allow_exec=True, execute_builder=True, unsafe_host=True
    ), sink=events.append)
    assert result["status"] == "passed", result
    assert result["full_suite_executed"] is True
    assert (project / "answer.py").read_text(encoding="utf-8") == "answer = 42\n"
    observation = result["accounting"]["observations"][0]
    assert observation["observed_tokens"] is None
    assert observation["billed_cost_usd"] is None


def test_acp_agent_refusal_cannot_claim_pass(tmp_path):
    project, manifest, spec = _setup(
        tmp_path, agent_name="acp-test-refusal", refuse=True
    )
    load_agent_manifest(manifest, grants={"acp-test-refusal"})
    result = run(spec, permissions=Permissions(
        allow_exec=True, execute_builder=True, unsafe_host=True
    ))
    assert result["status"] != "passed"
    assert (project / "answer.py").read_text(encoding="utf-8") == "answer = 0\n"


def test_acp_transport_manifest_rejects_fabricated_usage_and_bad_argv(tmp_path):
    project, manifest, _ = _setup(tmp_path, agent_name="acp-test-invalid")
    payload = json.loads(manifest.read_text())
    payload["telemetry"] = "codex"
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="telemetry"):
        load_agent_manifest(manifest, grants={"acp-test-invalid"})
    with pytest.raises(ValueError):
        ACPProcessAgent("x", [""])
    with pytest.raises(ValueError):
        ACPProcessAgent("x", ["echo", "x" * 5000])


def test_acp_completion_parser_is_fail_closed():
    agent = ACPProcessAgent("acp-unit", ["echo", "hello"])
    good = io.StringIO(json.dumps({
        "type": "olyder.acp.result", "status": "completed",
        "stop_reason": "end_turn",
    }) + "\n")
    outcome = agent.parse(good)
    assert outcome["status"] == "completed"
    assert outcome["usage_complete"] is False
    assert outcome["observed_tokens"] is None
    for response in [
        "not-json\n",
        json.dumps({"type": "olyder.acp.result", "status": "failed"}) + "\n",
        json.dumps({"type": "olyder.acp.result", "status": "completed",
                    "stop_reason": "refusal"}) + "\n",
    ]:
        assert agent.parse(io.StringIO(response))["status"] == "failed"


def test_explicit_container_python_runner(tmp_path):
    _, manifest, _ = _setup(tmp_path, agent_name="acp-test-container-python")
    payload = json.loads(manifest.read_text())
    payload["runner_python"] = "python3"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    adapter = load_agent_manifest(manifest, grants={"acp-test-container-python"})
    # A Docker image's Python path need not match the host interpreter path.
    assert adapter.command("build")[0] == "python3"
    assert adapter.capabilities().isolated is False  # Backend selects isolation.
