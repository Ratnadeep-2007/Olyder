"""Olyder v0.4.0: agent telemetry, fail-closed Docker policy, process cleanup."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from olyder.agents import AgentUsage, agent_argv, parse_agent_log
from olyder.execution import ExecutionError, docker_argv, managed_run
from olyder.checks import run_checks
from olyder.cli import main
from olyder.config import ConfigError, load_spec
from olyder.engine import run_loop


@pytest.mark.parametrize("provider,prefix", [
    ("codex", ["codex", "exec", "--json"]),
    ("opencode", ["opencode", "run", "--format", "json"]),
])
def test_supported_agent_templates(provider, prefix):
    cmd = agent_argv(provider, "TEST PROMPT")
    assert cmd[:len(prefix)] == prefix
    assert cmd[-1] == "TEST PROMPT"
    assert "--dangerously-bypass-approvals-and-sandbox" not in cmd


def test_reject_unknown_agent():
    with pytest.raises(ValueError):
        agent_argv("unknown", "test")


def test_codex_usage_counts_completed_turns():
    usage = AgentUsage("codex")
    for event in (
        {"type":"turn.started"},
        {"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":4,"output_tokens":5,"reasoning_output_tokens":2}},
        {"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":6}},
    ):
        usage.accept(json.dumps(event))
    snap = usage.snapshot()
    assert snap["observed_tokens"] == 33
    assert snap["input_tokens"] == 22
    assert snap["output_tokens"] == 11
    assert snap["usage_complete"]
    assert snap["quota_enforced"] is False


def test_opencode_usage_dedupes_id_and_cache():
    usage = AgentUsage("opencode")
    e = {"type":"step_finish","part":{"id":"p1","reason":"stop","tokens":{
        "input":6,"output":3,"reasoning":1,"cache":{"read":4,"write":2},"total":16}}}
    usage.accept(json.dumps(e)); usage.accept(json.dumps(e))
    snap = usage.snapshot()
    assert snap["observed_tokens"] == 16
    assert snap["input_tokens"] == 8
    assert snap["cached_tokens"] == 4
    assert snap["usage_events"] == 1
    assert snap["usage_complete"]


def test_opencode_missing_final_step_is_not_zero():
    usage = AgentUsage("opencode")
    usage.accept('{"type":"text","part":{"text":"done"}}')
    snap = usage.snapshot()
    assert snap["observed_tokens"] is None
    assert not snap["usage_complete"]


def test_agent_error_marks_incomplete():
    usage = AgentUsage("codex")
    usage.accept('{"type":"turn.failed"}')
    assert usage.snapshot()["status"] == "failed"
    assert not usage.snapshot()["usage_complete"]


def test_non_json_event_is_bounded_and_counted():
    usage = AgentUsage("codex")
    usage.accept("bad json")
    usage.accept("x" * 1_000_001)
    assert usage.snapshot()["malformed_events"] == 2


def test_docker_default_policy_restricts_network_and_permissions(tmp_path):
    with patch("olyder.execution.shutil.which", return_value="/usr/bin/docker"):
        cmd = docker_argv(["python", "-m", "pytest"], tmp_path, image="python:3.13-slim", writable=False)
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert cmd[cmd.index("--network")+1] == "none"
    assert "--read-only" in cmd
    assert "--cap-drop=ALL" in cmd
    assert "--security-opt=no-new-privileges=true" in cmd
    assert "--pids-limit=128" in cmd
    assert ",readonly" in cmd[cmd.index("--mount") + 1]
    assert cmd[-3:] == ["python", "-m", "pytest"]


def test_docker_builder_mount_rw_and_explicit_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_AGENT_TOKEN", "DONT_EXPOSE_ON_COMMAND_LINE")
    with patch("olyder.execution.shutil.which", return_value="/usr/bin/docker"):
        cmd = docker_argv(["echo", "ok"], tmp_path, image="test/image:1", writable=True,
                          network="bridge", env_names=("FAKE_AGENT_TOKEN",))
    assert "DONT_EXPOSE_ON_COMMAND_LINE" not in " ".join(cmd)
    assert cmd[cmd.index("--network")+1] == "bridge"
    assert ",readonly" not in cmd[cmd.index("--mount") + 1]
    assert cmd[-3:] == ["test/image:1", "echo", "ok"]


@pytest.mark.parametrize("invalid", ["", "-bad", "invalid image", "\t"])
def test_docker_rejects_bad_image(tmp_path, invalid):
    with patch("olyder.execution.shutil.which", return_value="docker"):
        with pytest.raises(ExecutionError):
            docker_argv(["echo", "ok"], tmp_path, image=invalid, writable=False)


def test_docker_fails_closed_without_executable(tmp_path):
    with patch("olyder.execution.shutil.which", return_value=None):
        with pytest.raises(ExecutionError, match="refusing to run on host"):
            docker_argv(["echo", "ok"], tmp_path, image="test", writable=False)


def test_missing_docker_blocks_check(tmp_path):
    with patch("olyder.execution.shutil.which", return_value=None):
        r = run_checks([{"id":"run", "type":"command", "argv":["python", "-c", "print('x')"]}],
                       tmp_path, allow_exec=True, sandbox="docker")
    assert r[0].status == "blocked"
    assert "Docker" in r[0].details


def test_managed_subprocess_returns_stdout(tmp_path):
    with tempfile.TemporaryFile(mode="w+t") as out:
        status = managed_run([sys.executable, "-c", "print('hi')"], cwd=tmp_path, stdout=out, timeout=3)
        out.seek(0)
        assert out.read().strip() == "hi"
    assert status.returncode == 0 and not status.timed_out


def test_managed_process_timeout(tmp_path):
    with tempfile.TemporaryFile(mode="w+t") as out:
        status = managed_run([sys.executable, "-c", "import time;time.sleep(5)"], cwd=tmp_path, stdout=out, timeout=0.15)
    assert status.timed_out
    assert status.elapsed_seconds < 3


@pytest.mark.skipif(os.name == "nt", reason="Unix process group behavior")
def test_timeout_terminates_process_group_child(tmp_path):
    marker = tmp_path / "child_survived.txt"
    # Child writes a marker after 0.7 seconds; parent waits 4 seconds.
    code = ("import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"
            f"\"import time;from pathlib import Path;time.sleep(.7);Path({str(marker)!r}).write_text('oops')\"]);time.sleep(4)")
    with tempfile.TemporaryFile(mode="w+t") as out:
        status = managed_run([sys.executable, "-c", code], cwd=tmp_path, stdout=out, timeout=0.1)
    time.sleep(0.9)
    assert status.timed_out
    assert not marker.exists(), "Child from timed out command was not terminated"


def test_config_rejects_unknown_provider(tmp_path):
    spec = {"goal":"x","checks":[{"id":"readme","type":"file","path":"README.md"}],"builder":{"provider":"bad"}}
    p = tmp_path / "olyder.json"; p.write_text(json.dumps(spec))
    with pytest.raises(ConfigError):
        load_spec(p)


def test_cli_blocks_unisolated_builder_without_unsafe_host(tmp_path, capsys):
    spec = {"goal":"x","checks":[{"id":"readme","type":"file","path":"README.md"}],"builder":{"argv":[sys.executable,"-c","print('ok')"]}}
    p = tmp_path / "olyder.json"; p.write_text(json.dumps(spec))
    rc = main(["run", "--spec", str(p), "--output", str(tmp_path/"out"), "--allow-exec", "--execute-builder"])
    assert rc == 2
    assert "--unsafe-host" in capsys.readouterr().err


def test_cli_blocks_bridge_without_network_consent(tmp_path, capsys):
    spec = {"goal":"x","checks":[{"id":"readme","type":"file","path":"README.md"}]}
    p = tmp_path / "olyder.json"; p.write_text(json.dumps(spec))
    rc = main(["run", "--spec", str(p), "--docker-network", "bridge"])
    assert rc == 2


def test_fake_codex_adapter_end_to_end(tmp_path, monkeypatch):
    from olyder import engine
    (tmp_path / "README.md").write_text("ok")
    config = {"goal":"x","checks":[{"id":"readme","type":"file","path":"README.md"}],
              "builder":{"provider":"codex"},"limits":{"max_iterations":1,"max_seconds":10,"max_tokens":2000}}
    spec_path = tmp_path / "olyder.json"; spec_path.write_text(json.dumps(config))
    monkeypatch.setattr(engine,"agent_argv", lambda provider,prompt: [sys.executable,"-c",
        "import json;print(json.dumps({'type':'turn.completed','usage':{'input_tokens':7,'output_tokens':3}}))"])
    result = run_loop(load_spec(spec_path),allow_exec=True,execute_builder=True,use_ai=False,
                      allow_network=False,output=tmp_path/"out")
    assert result["status"] == "passed"
    assert result["agent_usage"]["observed_tokens"] == 10
    assert result["agent_usage"]["complete"]


def test_incomplete_agent_telemetry_not_reported_as_full_pass(tmp_path, monkeypatch):
    from olyder import engine
    (tmp_path / "README.md").write_text("ok")
    config = {"goal":"x","checks":[{"id":"readme","type":"file","path":"README.md"}],
              "builder":{"provider":"opencode"},"limits":{"max_iterations":1,"max_seconds":10,"max_tokens":2000}}
    spec_path = tmp_path / "olyder.json"; spec_path.write_text(json.dumps(config))
    monkeypatch.setattr(engine,"agent_argv", lambda provider,prompt: [sys.executable,"-c", "print('not-json')"])
    result = run_loop(load_spec(spec_path),allow_exec=True,execute_builder=True,use_ai=False,
                      allow_network=False,output=tmp_path/"out")
    assert result["status"] == "needs_review"
    assert result["agent_usage"]["observed_tokens"] is None


def test_agent_usage_soft_cap_stops_retry(tmp_path, monkeypatch):
    from olyder import engine
    config = {"goal":"x","checks":[{"id":"readme","type":"file","path":"README.md"}],
              "builder":{"provider":"codex"},"limits":{"max_iterations":3,"max_seconds":10,"max_tokens":2000,"max_agent_tokens":2}}
    p = tmp_path / "olyder.json"; p.write_text(json.dumps(config))
    monkeypatch.setattr(engine,"agent_argv", lambda provider,prompt: [sys.executable,"-c",
        "import json;print(json.dumps({'type':'turn.completed','usage':{'input_tokens':3,'output_tokens':1}}))"])
    result = run_loop(load_spec(p),allow_exec=True,execute_builder=True,use_ai=False,
                      allow_network=False,output=tmp_path/"out")
    assert result["status"] == "blocked"
    assert result["attempts"] == 0
    assert result["agent_usage"]["observed_tokens"] == 4
