"""Security and reliability regressions added after the v0.2.0 audit.

All scenarios use fake credentials and disposable local fixtures; no paid AI
provider, remote target, or real user data is involved.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from olyder.checks import run_checks
from olyder.config import ConfigError, load_spec
from olyder.engine import run_loop
from olyder.models import ModelError, chat
from olyder.quota import Budget
from olyder.privacy import redact


@contextmanager
def fixture_server(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_model_auth_not_forwarded_by_redirect(monkeypatch, status):
    observed: list[str] = []

    class Destination(BaseHTTPRequestHandler):
        def do_GET(self):
            observed.append(self.headers.get("Authorization", ""))
            self.send_response(200)
            self.end_headers()

        def do_POST(self):
            observed.append(self.headers.get("Authorization", ""))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_):
            pass

    with fixture_server(Destination) as destination:
        class Origin(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(status)
                self.send_header("Location", f"http://127.0.0.1:{destination.server_port}/intercept")
                self.end_headers()

            def log_message(self, *_):
                pass

        with fixture_server(Origin) as origin:
            monkeypatch.setenv("OLYDER_MODEL", "fixture-model")
            monkeypatch.setenv("OLYDER_API_KEY", "FAKE_LOCAL_TEST_KEY")
            monkeypatch.setenv("OLYDER_BASE_URL", f"http://127.0.0.1:{origin.server_port}/v1")
            budget = Budget(3000)
            with pytest.raises(ModelError):
                chat("fixture request", budget, system="test", max_tokens=10)
            assert budget.reserved == 0 and budget.calls == 1
    assert observed == [], "Auth-bearing request followed an untrusted redirect"


def test_model_valid_local_provider_fixture(monkeypatch):
    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/v1/chat/completions"
            assert self.headers["Authorization"] == "Bearer FAKE_LOCAL_TEST_KEY"
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert payload["messages"][0]["role"] == "system"
            data = json.dumps({"choices": [{"message": {"content": "verified"}}], "usage": {"total_tokens": 23}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass

    with fixture_server(Provider) as server:
        monkeypatch.setenv("OLYDER_MODEL", "fixture-model")
        monkeypatch.setenv("OLYDER_API_KEY", "FAKE_LOCAL_TEST_KEY")
        monkeypatch.setenv("OLYDER_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
        budget = Budget(3000)
        assert chat("hello", budget, system="test", max_tokens=10) == "verified"
        assert budget.spent == 23 and budget.reserved == 0


def test_quota_duplicate_settlement_with_equal_sized_reservations():
    budget = Budget(1000)
    first = budget.reserve("same", 10)
    second = budget.reserve("same", 10)
    assert first == second and first.ticket != second.ticket
    budget.settle(first, 9)
    with pytest.raises(ValueError):
        budget.settle(first, 9)
    assert budget.reserved == second
    budget.settle(second, 7)
    assert budget.spent == 16 and budget.calls == 2


def test_quota_foreign_ticket_and_replayed_release():
    a = Budget(1000)
    b = Budget(1000)
    r = a.reserve("same", 10)
    b.reserve("same", 10)
    with pytest.raises(ValueError):
        b.settle(r, 3)
    a.release(r)
    with pytest.raises(ValueError):
        a.release(r)


def test_quota_invalid_actual_does_not_lose_reservation():
    b = Budget(1000)
    r = b.reserve("short", 10)
    with pytest.raises(ValueError):
        b.settle(r, -1)
    assert b.reserved == r
    b.settle(r, 20)
    assert b.spent == 20


def test_deadline_expiry_cannot_claim_http_success(tmp_path):
    class Slow(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(0.12)
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"healthy")
            except (ConnectionResetError, BrokenPipeError):
                pass

        def log_message(self, *_):
            pass

    with fixture_server(Slow) as server:
        case = {"id": "late-http", "type": "http", "url": f"http://127.0.0.1:{server.server_port}/health", "status": 200, "timeout": 3}
        result = run_checks([case], tmp_path, allow_exec=True, deadline=time.monotonic() + 0.025)
    assert result[0].status != "pass", "Check completed after deadline must not pass"


def test_builder_cannot_rewrite_command_acceptance_test(tmp_path):
    test_script = tmp_path / "acceptance_test.py"
    test_script.write_text("raise SystemExit(1)\n", encoding="utf-8")
    config = {
        "goal": "Independent acceptance checks must remain unchanged",
        "checks": [{"id": "acceptance", "type": "command", "argv": [sys.executable, "acceptance_test.py"]}],
        "builder": {"argv": [sys.executable, "-c", "from pathlib import Path; Path('acceptance_test.py').write_text('raise SystemExit(0)\\n')"]},
        "limits": {"max_iterations": 1, "max_seconds": 30, "max_tokens": 5000},
    }
    (tmp_path / "olyder.json").write_text(json.dumps(config), encoding="utf-8")
    result = run_loop(load_spec(tmp_path / "olyder.json"), allow_exec=True, execute_builder=True, use_ai=False, allow_network=False, output=tmp_path / ".olyder")
    assert result["status"] == "blocked"
    assert "acceptance" in result["verifier_note"].lower()
    assert result["acceptance_integrity"]["changed_paths"] == ["acceptance_test.py"]


def test_builder_cannot_rewrite_protected_test_directory(tmp_path):
    folder = tmp_path / "tests"
    folder.mkdir()
    (folder / "test_auth.py").write_text("raise SystemExit(1)\n")
    config = {
        "goal": "Protected tests are not owned by the builder",
        "checks": [{"id": "smoke", "type": "command", "argv": [sys.executable, "-c", "print('done')"]}],
        "builder": {"argv": [sys.executable, "-c", "from pathlib import Path; Path('tests/test_auth.py').write_text('raise SystemExit(0)\\n')"]},
        "limits": {"max_iterations": 1, "max_seconds": 30},
    }
    (tmp_path / "olyder.json").write_text(json.dumps(config), encoding="utf-8")
    result = run_loop(load_spec(tmp_path / "olyder.json"), allow_exec=True, execute_builder=True, use_ai=False, allow_network=False, output=tmp_path / ".olyder")
    assert result["status"] == "blocked"
    assert "tests" in result["acceptance_integrity"]["changed_paths"]


def test_protected_paths_can_guard_custom_fixture(tmp_path):
    (tmp_path / "ground_truth.csv").write_text("expected\n")
    cfg = {
        "goal": "Protect fixture even when not named test",
        "checks": [{"id": "fixture", "type": "file", "path": "ground_truth.csv", "contains": "expected"}],
        "protected_paths": ["ground_truth.csv"],
        "builder": {"argv": [sys.executable, "-c", "from pathlib import Path; Path('ground_truth.csv').write_text('expected\\nmodified')"]},
    }
    (tmp_path / "olyder.json").write_text(json.dumps(cfg), encoding="utf-8")
    result = run_loop(load_spec(tmp_path / "olyder.json"), allow_exec=True, execute_builder=True, use_ai=False, allow_network=False, output=tmp_path / ".olyder")
    assert result["status"] == "blocked"


def test_invalid_protected_path_outside_workspace_rejected(tmp_path):
    cfg = {"goal": "test", "checks": [{"id": "x", "type": "file", "path": "x"}], "protected_paths": ["../outside"]}
    (tmp_path / "olyder.json").write_text(json.dumps(cfg))
    with pytest.raises(ConfigError):
        load_spec(tmp_path / "olyder.json")


def test_command_log_redacts_fake_bearer_secret(tmp_path):
    check = {"id": "log-secret", "type": "command", "argv": [sys.executable, "-c", "print('Authorization: Bearer FAKE_LOCAL_TEST_KEY')"]}
    outcome = run_checks([check], tmp_path, allow_exec=True)
    assert outcome[0].status == "pass"
    assert "FAKE_LOCAL_TEST_KEY" not in outcome[0].details
    assert "[REDACTED]" in outcome[0].details


@pytest.mark.parametrize("untrusted", [
    "password: local_fake_password",
    "token=local_fake_token",
    "Authorization: Basic dGVzdDp0ZXN0",
    "https://fake-user:fake-pass@example.org/api",
])
def test_redact_common_credential_patterns(untrusted):
    result = redact(untrusted)
    assert "[REDACTED]" in result
    for secret in ("local_fake_password", "local_fake_token", "dGVzdDp0ZXN0", "fake-pass"):
        assert secret not in result
