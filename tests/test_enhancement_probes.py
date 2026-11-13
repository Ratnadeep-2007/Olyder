"""Reproducible enhancement probes, intentionally marked XFAIL until fixed.

Each test expresses the expected secure behavior. XFAIL means the CURRENT
implementation violates that expectation; it is not a successful security test.
No real credentials, external hosts, paid APIs, or destructive operations are used.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from olyder.checks import run_checks
from olyder.config import load_spec
from olyder.engine import run_loop
from olyder.models import chat
from olyder.quota import Budget


@contextmanager
def http_server(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.xfail(strict=True, reason="P0: model client follows cross-origin redirect and forwards a fake bearer credential")
def test_model_credential_does_not_cross_redirect_origin(monkeypatch):
    # A redirect issued by a configured endpoint must NEVER send credentials
    # to another origin. Both endpoints here are local fake fixtures.
    observed = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self):
            observed.append(self.headers.get("Authorization"))
            data = json.dumps({"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 5}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    with http_server(Target) as target:
        class Origin(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{target.server_port}/redirect-target")
                self.end_headers()

            def log_message(self, *args):
                pass

        with http_server(Origin) as origin:
            monkeypatch.setenv("OLYDER_MODEL", "fixture-model")
            monkeypatch.setenv("OLYDER_API_KEY", "FAKE_LOCAL_TEST_KEY")
            monkeypatch.setenv("OLYDER_BASE_URL", f"http://127.0.0.1:{origin.server_port}")
            chat("fixture request", Budget(5000), system="fixture system", max_tokens=10)

    assert not observed, "Bearer authorization was forwarded to a different origin"


@pytest.mark.xfail(strict=True, reason="P1: duplicate settlement accepted when two same-size reservations coexist")
def test_budget_reservation_identity_cannot_be_settled_twice():
    b = Budget(1000)
    first = b.reserve("same", 10)
    b.reserve("same", 10)
    b.settle(first, 5)
    with pytest.raises(ValueError):
        b.settle(first, 5)


@pytest.mark.xfail(strict=True, reason="P1: HTTP checks may report pass after the run deadline")
def test_http_check_fails_closed_when_deadline_expires(tmp_path):
    class SlowHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(0.15)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"healthy")

        def log_message(self, *args):
            pass

    with http_server(SlowHandler) as server:
        checks = [{"id": "slow-http", "type": "http", "url": f"http://127.0.0.1:{server.server_port}/health", "status": 200, "timeout": 5}]
        outcome = run_checks(checks, tmp_path, allow_exec=True, deadline=time.monotonic() + 0.02)
    assert outcome[0].status != "pass", "Deadline-expired result must not be accepted"


@pytest.mark.xfail(strict=True, reason="P0: builder can modify executable acceptance tests without changing the locked spec")
def test_builder_cannot_fake_pass_by_rewriting_acceptance_test(tmp_path):
    test_file = tmp_path / "acceptance_test.py"
    test_file.write_text("raise SystemExit(1)\n", encoding="utf-8")
    spec_data = {
        "goal": "Pass protected, unmodified acceptance checks",
        "checks": [{"id": "locked-test", "type": "command", "argv": [sys.executable, "acceptance_test.py"]}],
        "builder": {"argv": [sys.executable, "-c", "from pathlib import Path; Path('acceptance_test.py').write_text('raise SystemExit(0)\\n')"]},
        "limits": {"max_iterations": 1, "max_seconds": 30, "max_tokens": 5000},
    }
    path = tmp_path / "olyder.json"
    path.write_text(json.dumps(spec_data), encoding="utf-8")
    result = run_loop(
        load_spec(path), allow_exec=True, execute_builder=True, use_ai=False,
        allow_network=False, output=tmp_path / ".olyder"
    )
    assert result["status"] != "passed", "A modified acceptance test must invalidate verification"


@pytest.mark.xfail(strict=True, reason="P1: CLI command details can contain bearer secrets unredacted")
def test_command_output_redacts_bearer_header(tmp_path):
    check = {
        "id": "log-secret", "type": "command",
        "argv": [sys.executable, "-c", "print('Authorization: Bearer FAKE_LOCAL_TEST_KEY')"],
    }
    outcome = run_checks([check], tmp_path, allow_exec=True)
    assert outcome[0].status == "pass"
    assert "FAKE_LOCAL_TEST_KEY" not in outcome[0].details, "Bearer token leaked into verification evidence"
