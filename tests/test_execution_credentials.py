"""The independent verifier keeps its credentials outside managed workloads."""
import json
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from olyder.checks import run_checks
from olyder.execution import ExecutionError, docker_argv, managed_run


def test_managed_workload_keeps_runtime_env_but_excludes_olyder_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("OLYDER_API_KEY", "test-verifier-token")
    monkeypatch.setenv("OLYDER_LOCAL_API_TOKEN", "test-api-token")
    monkeypatch.setenv("OLYDER_TEST_RUNTIME_VALUE", "preserved")
    names = ["OLYDER_API_KEY", "OLYDER_LOCAL_API_TOKEN", "OLYDER_TEST_RUNTIME_VALUE"]
    script = f"import json, os; print(json.dumps([os.getenv(k) for k in {names!r}]))"
    with tempfile.TemporaryFile() as output:
        result = managed_run([sys.executable, "-c", script], cwd=tmp_path, stdout=output, timeout=5)
        output.seek(0)
        assert result.returncode == 0
        assert json.load(output) == [None, None, "preserved"]
    assert os.environ["OLYDER_API_KEY"] == "test-verifier-token"
    assert os.environ["OLYDER_LOCAL_API_TOKEN"] == "test-api-token"


def test_docker_rejects_forwarding_verifier_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("OLYDER_API_KEY", "test-verifier-token")
    with pytest.raises(ExecutionError, match="credentials"):
        docker_argv(["python"], tmp_path, image="python:3.13-slim",
                    writable=False, env_names=("OLYDER_API_KEY",))


def test_chromium_receives_filtered_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("OLYDER_API_KEY", "test-verifier-token")
    monkeypatch.setenv("OLYDER_LOCAL_API_TOKEN", "test-api-token")
    monkeypatch.setenv("OLYDER_TEST_RUNTIME_VALUE", "preserved")
    playwright = MagicMock()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(
        sync_playwright=playwright,
    ))
    browser_type = playwright.return_value.__enter__.return_value.chromium
    result, = run_checks(
        [{"id": "browser", "type": "browser", "url": "http://localhost:3000"}],
        tmp_path, allow_exec=True,
    )
    assert result.status == "pass"
    environment = browser_type.launch.call_args.kwargs["env"]
    assert "OLYDER_API_KEY" not in environment
    assert "OLYDER_LOCAL_API_TOKEN" not in environment
    assert environment["OLYDER_TEST_RUNTIME_VALUE"] == "preserved"
