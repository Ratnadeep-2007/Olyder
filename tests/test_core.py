import json
import sys
from pathlib import Path

import pytest

from olyder.checks import run_checks
from olyder.cli import main
from olyder.config import ConfigError, load_spec, safe_path
from olyder.engine import plan, run_loop, verify_once
from olyder.idea import evaluate_idea
from olyder.mcp import process
from olyder.quota import Budget, QuotaExceeded
from olyder.report import save_report


def spec_at(tmp_path, checks=None, **kwargs):
    data = {"goal": "User can finish a realistic transaction", "checks": checks or [{"id": "present", "type": "file", "path": "output.txt"}], "limits": {"max_iterations": 3, "max_tokens": 10000, "max_seconds": 120}, **kwargs}
    f = tmp_path / "olyder.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    return load_spec(f)


def test_rejects_missing_or_duplicate_checks(tmp_path):
    with pytest.raises(ConfigError):
        spec_at(tmp_path, checks=[{"id":"x","type":"file","path":"a"},{"id":"x","type":"file","path":"b"}])


def test_file_pass_and_fail(tmp_path):
    spec = spec_at(tmp_path)
    assert verify_once(spec)["status"] == "failed"
    (tmp_path / "output.txt").write_text("done")
    observed = verify_once(spec)
    assert observed["status"] == "passed"
    assert observed["metrics"]["pass_rate_of_executed_percent"] == 100.0


def test_no_escape_via_parent_or_symlink(tmp_path):
    outside = tmp_path.parent / "sensitive-item.txt"
    outside.write_text("private")
    with pytest.raises(ConfigError):
        safe_path(tmp_path, "../sensitive-item.txt")
    (tmp_path / "escaped-link").symlink_to(outside)
    with pytest.raises(ConfigError):
        safe_path(tmp_path, "escaped-link")


def test_execution_requires_opt_in(tmp_path):
    spec = spec_at(tmp_path, [{"id":"command","type":"command","argv":[sys.executable,"-c","print('hello')"]}])
    assert verify_once(spec)["status"] == "blocked"
    result = verify_once(spec, allow_exec=True)
    assert result["status"] == "passed"
    assert result["checks"][0]["details"].startswith("Exit 0")


def test_command_failure(tmp_path):
    spec = spec_at(tmp_path, [{"id":"bad","type":"command","argv":[sys.executable,"-c","raise RuntimeError('oops')"]}])
    assert verify_once(spec, allow_exec=True)["status"] == "failed"


def test_budget_fails_closed():
    b = Budget(1000)
    a = b.reserve("short", 200)
    assert b.reserved > 0
    b.settle(a, 50)
    assert b.spent == 50
    with pytest.raises(QuotaExceeded):
        b.reserve("long" * 10000, 500)


def test_repair_loop_builder_creates_file(tmp_path):
    builder_code = "from pathlib import Path; Path('output.txt').write_text('built')"
    spec = spec_at(tmp_path, builder={"argv": [sys.executable, "-c", builder_code]})
    result = run_loop(spec, allow_exec=True, execute_builder=True, use_ai=False, allow_network=False, output=tmp_path / "out")
    assert result["status"] == "passed"
    assert result["attempts"] == 1
    assert Path(result["paths"]["html"]).is_file()


def test_refuses_spec_modification_by_builder(tmp_path):
    builder_code = "from pathlib import Path; Path('olyder.json').write_text('{}')"
    spec = spec_at(tmp_path, builder={"argv": [sys.executable, "-c", builder_code]})
    result = run_loop(spec, allow_exec=True, execute_builder=True, use_ai=False, allow_network=False, output=tmp_path / "out")
    assert result["status"] == "blocked"
    assert "specification" in result["verifier_note"].lower()


def test_run_does_not_call_builder_without_opt_in(tmp_path):
    spec = spec_at(tmp_path, builder={"argv": [sys.executable, "-c", "from pathlib import Path; Path('output.txt').write_text('no')"]})
    result = run_loop(spec, allow_exec=False, execute_builder=False, use_ai=False, allow_network=False, output=tmp_path / "out")
    assert result["status"] == "failed"
    assert not (tmp_path / "output.txt").exists()


def test_plan_is_locked(tmp_path):
    spec = spec_at(tmp_path)
    p = plan(spec)
    assert p["locked_spec_sha256"] == spec.digest
    assert p["tasks"][0]["check_id"] == "present"


def test_blocked_sources_without_network(tmp_path):
    spec = spec_at(tmp_path, sources=["https://example.com/official"])
    result = evaluate_idea(spec, network_allowed=False, use_ai=False, budget=Budget(1000))
    assert result["sources"][0]["status"] == "blocked"


def test_report_escapes_html(tmp_path):
    payload = {"goal": "<script>alert(1)</script>", "status":"failed", "checks":[{"id":"x","status":"fail","type":"file","duration_ms":1,"details":"<img src=x>"}], "spec_sha256":"abc", "attempts":1, "sources":[], "budget":{"spent":0}}
    paths = save_report(payload, tmp_path)
    html = Path(paths["html"]).read_text()
    assert "&lt;script&gt;" in html and "&lt;img" in html
    assert "<script>alert" not in html


def test_mcp_does_not_execute_shell(tmp_path):
    spec_at(tmp_path, [{"id": "danger", "type": "command", "argv": [sys.executable,"-c", "from pathlib import Path; Path('bad').touch()"]}])
    r = process({"jsonrpc":"2.0","id":42,"method":"tools/call","params":{"name":"olyder_verify"}},tmp_path)
    results = json.loads(r["result"]["content"][0]["text"])
    assert results["status"] == "blocked"
    assert not (tmp_path / "bad").exists()


def test_cli_init_and_verify(tmp_path, capsys, monkeypatch):
    assert main(["init", str(tmp_path)]) == 0
    assert (tmp_path / "olyder.json").exists()
    assert main(["init", str(tmp_path)]) == 2
    monkeypatch.chdir(tmp_path)
    assert main(["plan"]) == 0


def test_independent_ai_verifier_receives_no_builder_history(tmp_path, monkeypatch):
    spec = spec_at(tmp_path)
    (tmp_path / "output.txt").write_text("done")
    def fake_chat(prompt, budget, **kwargs):
        assert "builder_history" not in prompt
        assert "thought process" not in prompt
        assert "observed_tests" in prompt
        return json.dumps({"concerns":[], "note":"Only one declared check was covered"})
    monkeypatch.setattr("olyder.engine.chat", fake_chat)
    result = verify_once(spec, use_ai=True)
    assert result["status"] == "passed"
    assert "declared check" in result["verifier_note"]


def test_ai_concerns_never_override_real_tests(tmp_path, monkeypatch):
    spec = spec_at(tmp_path)
    (tmp_path / "output.txt").write_text("done")
    monkeypatch.setattr("olyder.engine.chat", lambda *a, **kw: '{"concerns":["Need a login security test"], "note":"Incomplete"}')
    assert verify_once(spec, use_ai=True)["status"] == "needs_review"


def test_explicit_coverage_when_blocked(tmp_path):
    spec = spec_at(tmp_path, [{"id":"command","type":"command","argv":[sys.executable,"-c","print(1)"]}, {"id":"file","type":"file","path":"olyder.json"}])
    result = verify_once(spec, allow_exec=False)
    assert result["metrics"]["execution_coverage_percent"] == 50.0
    assert result["metrics"]["blocked_checks"] == 1
    assert result["status"] == "blocked"


def test_install_skill_creates_both_files(tmp_path):
    assert main(["install-skill", "--target", "both", "--project", str(tmp_path)]) == 0
    assert (tmp_path / ".claude/skills/olyder/SKILL.md").exists()
    assert (tmp_path / ".agents/skills/olyder/SKILL.md").exists()
    assert main(["install-skill", "--target", "both", "--project", str(tmp_path)]) == 2
    assert main(["install-skill", "--target", "both", "--project", str(tmp_path), "--force"]) == 0


def test_invalid_scenario_fields_rejected_before_execution(tmp_path):
    bad_checks = [
        {"id": "bad-file", "type": "file", "path": "file.txt", "contains": ["not-a-string"]},
        {"id": "bad-timeout", "type": "command", "argv": [sys.executable], "timeout": "10"},
        {"id": "bad-status", "type": "http", "url": "http://localhost:9999", "status": "200"},
        {"id": "bad-host", "type": "http", "url": "https:///no-host"},
        {"id": "bad-step", "type": "browser", "url": "http://localhost:9999", "steps": ["click"]},
        {"id": "bad-navigation", "type": "browser", "url": "http://localhost:9999", "steps": [{"action": "navigate", "url": "file:///etc/passwd"}]},
    ]
    for check in bad_checks:
        with pytest.raises(ConfigError):
            spec_at(tmp_path, checks=[check])


def test_http_expected_404_and_redirect_is_not_followed(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            if self.path == "/not-found":
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"missing record")
            elif self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/should-not-visit")
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host = f"http://127.0.0.1:{server.server_port}"
            spec = spec_at(tmp_path, checks=[
                {"id": "missing", "type": "http", "url": host + "/not-found", "status": 404, "contains": "missing record"},
                {"id": "redirect", "type": "http", "url": host + "/redirect", "status": 302},
            ])
            outcome = verify_once(spec, allow_exec=True)
            assert outcome["status"] == "passed"
            assert hits == ["/not-found", "/redirect"]
        finally:
            server.shutdown()
            thread.join(timeout=3)


def test_source_limit_and_embedded_auth_rejected(tmp_path):
    with pytest.raises(ConfigError):
        spec_at(tmp_path, sources=["https://example.com/page"] * 13)
    with pytest.raises(ConfigError):
        spec_at(tmp_path, sources=["https://user:pass@example.com/secret"])


def test_unexpected_runtime_check_error_is_reported_not_crash(tmp_path, monkeypatch):
    from olyder import checks

    def broken(*_args, **_kwargs):
        raise LookupError("unexpected internal exception")

    monkeypatch.setattr(checks, "_run", broken)
    check = {"id": "unexpected", "type": "file", "path": "test.txt"}
    result = run_checks([check], tmp_path, allow_exec=False)
    assert result[0].status == "fail"
    assert "LookupError" in result[0].details


def test_mcp_rejects_malformed_params_without_crashing(tmp_path):
    malformed = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": ["unsafe"]}
    response = process(malformed, tmp_path)
    assert response["error"]["code"] == -32602
