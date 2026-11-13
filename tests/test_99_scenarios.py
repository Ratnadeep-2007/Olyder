"""99 deterministic, independently asserted scenarios across nine difficulty levels.

Requires no paid model. Browser-tier cases use a deterministic Playwright
adapter substitute because hosted execution environments may block browser
navigation. A separate opt-in live-browser smoke test covers actual Chromium.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
import os
import re
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from urllib import error as urlerror

import pytest

from olyder.checks import run_checks
from olyder.cli import main
from olyder.config import ConfigError, load_spec, safe_path
from olyder.engine import plan, run_loop, verify_once
from olyder.idea import evaluate_idea
from olyder.mcp import process
from olyder.models import ModelError, chat
from olyder.quota import Budget, QuotaExceeded
from olyder.report import save_report
from olyder.research import collect


def write_spec(root: Path, checks=None, **kwargs):
    root.mkdir(parents=True, exist_ok=True)
    doc = {"goal": "Verify actual customer outcomes", "checks": checks if checks is not None else [{"id": "ok", "type": "file", "path": "ok.txt"}]}
    doc.update(kwargs)
    path = root / "olyder.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return load_spec(path)


@pytest.fixture(scope="module")
def local_web():
    visits = []

    class Web(BaseHTTPRequestHandler):
        def do_GET(self):
            visits.append(self.path)
            responses = {
                "/ok": (200, b"orders ready", {}),
                "/created": (201, b"created 123", {}),
                "/missing": (404, b"user not found", {}),
                "/error": (500, b"internal error", {}),
                "/redirect": (302, b"moved", {"Location": "/sensitive"}),
                "/sensitive": (200, b"not followed", {}),
                "/unicode": (200, "caf\u00e9".encode(), {}),
                "/page": (200, b'<html><head><title>Home</title></head><body><h1>Welcome</h1><input id="email"/><button id="go" onclick="document.getElementById(\'msg\').textContent = \'Saved\'">Save</button><p id="msg">Idle</p><a id="next" href="/next">Next</a></body></html>', {"Content-Type": "text/html"}),
                "/next": (200, b"<html><body><h2>Next step</h2></body></html>", {"Content-Type": "text/html"}),
                "/slow": (200, b"slow", {}),
            }
            if self.path == "/slow":
                time.sleep(1.25)
            status, data, headers = responses.get(self.path, (404, b"unknown", {}))
            try:
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Web)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", visits
    finally:
        server.shutdown()
        thread.join(timeout=4)
        server.server_close()


# Level 1: Schema & requirements (11 cases)
SCHEMA_CASES = [
    ("minimal_valid", {}, True),
    ("non_ascii_goal", {"goal": "\u092a\u0921\u0924\u093e\u0933\u0923\u0940"}, True),
    ("empty_goal", {"goal": "   "}, False),
    ("missing_check_list", {"checks": []}, False),
    ("duplicate_check_ids", {"checks": [{"id": "x", "type": "file", "path": "a"}, {"id": "x", "type": "file", "path": "b"}]}, False),
    ("bool_command_timeout", {"checks": [{"id": "x", "type": "command", "argv": ["python"], "timeout": True}]}, False),
    ("invalid_http_scheme", {"checks": [{"id": "x", "type": "http", "url": "ftp://example.com"}]}, False),
    ("embedded_credentials", {"checks": [{"id": "x", "type": "http", "url": "https://user:pass@example.com/"}]}, False),
    ("missing_file_path", {"checks": [{"id": "x", "type": "file"}]}, False),
    ("insecure_research_source", {"sources": ["http://example.com/"]}, False),
    ("empty_builder_argument", {"builder": {"argv": ["python", ""]}}, False),
]


@pytest.mark.parametrize("case,patch,accepted", SCHEMA_CASES, ids=[x[0] for x in SCHEMA_CASES])
def test_L1_schema(tmp_path, case, patch, accepted):
    data = {"goal": "works", "checks": [{"id": "x", "type": "file", "path": "a"}]}
    data.update(patch)
    (tmp_path / "olyder.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if accepted:
        assert load_spec(tmp_path / "olyder.json").goal.strip()
    else:
        with pytest.raises(ConfigError):
            load_spec(tmp_path / "olyder.json")


# Level 2: Filesystem / path boundaries (11 cases)
FILE_CASES = [
    ("existing_file", "present", "ok.txt", True, None, "pass"),
    ("absent_file_expected_absent", "absent", "gone.txt", False, None, "pass"),
    ("missing_file_fails", "absent", "gone.txt", True, None, "fail"),
    ("contains_match", "present", "ok.txt", True, "hello", "pass"),
    ("contains_mismatch", "present", "ok.txt", True, "goodbye", "fail"),
    ("unicode_contains", "unicode", "ok.txt", True, "\u091a\u093e\u091a\u0923\u0940", "pass"),
    ("nested_file", "nested", "nested/ok.txt", True, None, "pass"),
    ("traversal_rejected", "absent", "../secret.txt", True, None, "fail"),
    ("symlink_escape_rejected", "symlink", "link.txt", True, None, "fail"),
    ("directory_not_regular_text_file", "directory", "folder", True, "hello", "fail"),
    ("content_limited_to_first_megabyte", "huge", "big.txt", True, "end-marker", "fail"),
]


@pytest.mark.parametrize("case,mode,path,exists,contains,expected", FILE_CASES, ids=[x[0] for x in FILE_CASES])
def test_L2_files(tmp_path, case, mode, path, exists, contains, expected):
    if mode in ("present", "unicode"):
        (tmp_path / "ok.txt").write_text("hello \u091a\u093e\u091a\u0923\u0940", encoding="utf-8")
    elif mode == "nested":
        (tmp_path / "nested").mkdir()
        (tmp_path / "nested/ok.txt").write_text("hello")
    elif mode == "directory":
        (tmp_path / "folder").mkdir()
    elif mode == "huge":
        (tmp_path / "big.txt").write_bytes(b"x" * 1_000_001 + b"end-marker")
    elif mode == "symlink":
        target = tmp_path.parent / "outside-secret"
        target.write_text("sensitive")
        (tmp_path / "link.txt").symlink_to(target)
    check = {"id": case, "type": "file", "path": path, "exists": exists}
    if contains is not None:
        check["contains"] = contains
    spec = write_spec(tmp_path, [check])
    result = verify_once(spec)
    assert result["checks"][0]["status"] == expected


# Level 3: Command execution / opt-in / output analysis (11 cases)
COMMAND_CASES = [
    ("blocked_without_consent", "print('hello')", False, 0, None, "blocked", None),
    ("simple_success", "print('hello')", True, 0, None, "pass", "hello"),
    ("failure_nonzero", "raise SystemExit(7)", True, 0, None, "fail", None),
    ("expected_nonzero", "raise SystemExit(7)", True, 7, None, "pass", None),
    ("stdout_contains_true", "print('success: payment accepted')", True, 0, "payment accepted", "pass", None),
    ("stdout_contains_false", "print('payment declined')", True, 0, "payment accepted", "fail", None),
    ("stderr_captured", "import sys;sys.stderr.write('failure hint')", True, 0, "failure hint", "pass", None),
    ("cwd_workspace", "import os;print(os.getcwd())", True, 0, "#WORKSPACE#", "pass", None),
    ("secret_redacted", "print('api_key=supersecret')", True, 0, None, "pass", "api_key=[REDACTED]"),
    ("timeout_observed", "import time;time.sleep(2)", True, 0, None, "fail", "Timed out"),
    ("no_shell_injection", "print('safe; touch outside-file')", True, 0, None, "pass", "safe; touch"),
]


@pytest.mark.parametrize("case,code,enabled,exit_code,contains,expected,detail", COMMAND_CASES, ids=[x[0] for x in COMMAND_CASES])
def test_L3_commands(tmp_path, case, code, enabled, exit_code, contains, expected, detail):
    if contains == "#WORKSPACE#":
        contains = str(tmp_path)
    check = {"id": case, "type": "command", "argv": [sys.executable, "-c", code], "exit_code": exit_code, "timeout": 1 if case == "timeout_observed" else 5}
    if contains:
        check["contains"] = contains
    spec = write_spec(tmp_path, [check])
    actual = verify_once(spec, allow_exec=enabled)["checks"][0]
    assert actual["status"] == expected
    if detail:
        assert detail in actual["details"]


# Level 4: HTTP integration / negative expectations / network permissions (11 cases)
HTTP_CASES = [
    ("success_200", "/ok", 200, None, False, True, "pass"),
    ("created_201", "/created", 201, "created", False, True, "pass"),
    ("expected_404", "/missing", 404, "not found", False, True, "pass"),
    ("expected_500", "/error", 500, "internal", False, True, "pass"),
    ("unexpected_404", "/missing", 200, None, False, True, "fail"),
    ("content_found", "/ok", 200, "orders", False, True, "pass"),
    ("content_missing", "/ok", 200, "checkout", False, True, "fail"),
    ("redirect_not_followed", "/redirect", 302, None, False, True, "pass"),
    ("http_requires_opt_in", "/ok", 200, None, False, False, "blocked"),
    ("nonlocal_http_without_network_opt_in", "https://example.org/", 200, None, False, True, "blocked"),
    ("unicode_utf8_content", "/unicode", 200, "caf\u00e9", False, True, "pass"),
]


@pytest.mark.parametrize("case,path,status,contains,network,exec_enabled,expected", HTTP_CASES, ids=[x[0] for x in HTTP_CASES])
def test_L4_http(tmp_path, local_web, case, path, status, contains, network, exec_enabled, expected):
    base, hits = local_web
    url = path if path.startswith("https://") else base + path
    check = {"id": case, "type": "http", "url": url, "status": status, "timeout": 3}
    if contains:
        check["contains"] = contains
    spec = write_spec(tmp_path, [check])
    result = verify_once(spec, allow_exec=exec_enabled, allow_network=network)["checks"][0]
    assert result["status"] == expected
    if case == "redirect_not_followed":
        assert "/sensitive" not in hits


# Level 5: Browser journeys on a real local website (11 cases)
BROWSER_CASES = [
    ("browser_requires_opt_in", "/page", [], False, "blocked"),
    ("load_real_page", "/page", [{"action": "expect_text", "text": "Welcome"}], True, "pass"),
    ("click_button_changes_dom", "/page", [{"action": "click", "selector": "#go"}, {"action": "expect_text", "text": "Saved"}], True, "pass"),
    ("fill_form_field", "/page", [{"action": "fill", "selector": "#email", "value": "customer@example.com"}], True, "pass"),
    ("missing_text_fails", "/page", [{"action": "expect_text", "text": "Purchase complete"}], True, "fail"),
    ("current_url_regex", "/page", [{"action": "expect_url", "pattern": r"/page$"}], True, "pass"),
    ("wrong_url_regex", "/page", [{"action": "expect_url", "pattern": r"/orders$"}], True, "fail"),
    ("navigation_to_next_page", "/page", [{"action": "navigate", "url": "#NEXT#"}, {"action": "expect_text", "text": "Next step"}], True, "pass"),
    ("click_link_navigation", "/page", [{"action": "click", "selector": "#next"}, {"action": "expect_url", "pattern": r"/next$"}], True, "pass"),
    ("invalid_browser_selector_fails", "/page", [{"action": "click", "selector": "#does-not-exist"}], True, "fail"),
    ("browser_external_without_network_consent", "https://example.org/", [], True, "blocked"),
]


@pytest.mark.parametrize("case,path,steps,enabled,expected", BROWSER_CASES, ids=[x[0] for x in BROWSER_CASES])
def test_L5_browser(tmp_path, local_web, monkeypatch, case, path, steps, enabled, expected):
    if shutil.which("chromium"):
        monkeypatch.setenv("OLYDER_CHROMIUM_PATH", shutil.which("chromium"))
    base, _ = local_web
    # Chromium navigation is blocked by this execution environment's administrator.
    # Exercise the Playwright adapter with an explicit deterministic fake; this
    # validates Olyder control flow, NOT a real browser engine or site.
    class FakeLocator:
        def __init__(self, page, selector):
            self.page, self.selector = page, selector
        def click(self, **kwargs):
            if self.selector == "#go":
                self.page.saved = True
            elif self.selector == "#next":
                self.page.url = base + "/next"
            else:
                raise ValueError("selector missing")
        def fill(self, value, **kwargs):
            if self.selector != "#email":
                raise ValueError("selector missing")
            self.page.email = value
        def inner_text(self, **kwargs):
            return "Next step" if self.page.url.endswith("/next") else "Welcome " + ("Saved" if self.page.saved else "Idle")

    class FakePage:
        def __init__(self):
            self.url = ""
            self.saved = False
            self.email = ""
        def goto(self, url, **kwargs):
            self.url = url
        def locator(self, selector):
            return FakeLocator(self, selector)

    class FakeContext:
        def new_page(self): return FakePage()
        def route(self, *args, **kwargs): pass
        def close(self): pass

    class FakeBrowser:
        def new_context(self): return FakeContext()
        def close(self): pass

    class FakeChromium:
        def launch(self, *args, **kwargs): return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    @contextmanager
    def fake_playwright():
        yield FakePlaywright()
    playwright_module = ModuleType("playwright")
    playwright_module.__path__ = []
    sync_api_module = ModuleType("playwright.sync_api")
    sync_api_module.sync_playwright = fake_playwright
    monkeypatch.setitem(sys.modules, "playwright", playwright_module)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api_module)
    url = path if path.startswith("https://") else base + path
    steps = [{**s, "url": base + "/next" if s.get("url") == "#NEXT#" else s.get("url")} if "url" in s else s for s in steps]
    check = {"id": case, "type": "browser", "url": url, "steps": steps, "timeout": 10}
    spec = write_spec(tmp_path, [check])
    result = verify_once(spec, allow_exec=enabled)["checks"][0]
    assert result["status"] == expected, result["details"]


# Level 6: Quota and model-client reliability (11 cases)
QUOTA_CASES = [
    "reserve_settle_actual", "estimate_blocks_overspend", "reserve_exact_boundary", "unicode_estimation", "settle_unknown_charges_reserved", "actual_usage_can_exceed_reservation", "release_restores_budget", "reject_negative_output", "reject_negative_limit", "missing_model_configuration", "network_failure_settles_reservation",
]


@pytest.mark.parametrize("case", QUOTA_CASES)
def test_L6_quota(tmp_path, monkeypatch, case):
    if case == "reject_negative_limit":
        with pytest.raises(ValueError):
            Budget(-1).reserve("x", 10)
    elif case == "missing_model_configuration":
        monkeypatch.delenv("OLYDER_MODEL", raising=False)
        monkeypatch.delenv("OLYDER_API_KEY", raising=False)
        with pytest.raises(ModelError):
            chat("hello", Budget(5000), system="test")
    elif case == "network_failure_settles_reservation":
        import olyder.models as models
        monkeypatch.setenv("OLYDER_MODEL", "test")
        monkeypatch.setenv("OLYDER_API_KEY", "dummy")
        def connection_down(*args, **kwargs):
            raise OSError("network offline")
        monkeypatch.setattr(models, "_open_model_request", connection_down)
        budget = Budget(4000)
        with pytest.raises(ModelError):
            chat("question", budget, system="test")
        assert budget.reserved == 0 and budget.spent > 0
    else:
        budget = Budget(1000)
        if case == "reserve_settle_actual":
            t = budget.reserve("hi", 10);budget.settle(t, 20)
            assert budget.spent == 20 and budget.calls == 1
        elif case == "estimate_blocks_overspend":
            with pytest.raises(QuotaExceeded): budget.reserve("y"*2000, 100)
        elif case == "reserve_exact_boundary":
            n = budget.reserve("z"*10, 10)
            assert n <= 1000 and budget.reserved == n
        elif case == "unicode_estimation":
            n = budget.reserve("\u0928\u092e\u0938\u094d\u0924\u0947", 5)
            assert n >= len("\u0928\u092e\u0938\u094d\u0924\u0947".encode())
        elif case == "settle_unknown_charges_reserved":
            n=budget.reserve("hi", 10);budget.settle(n, None)
            assert budget.spent == n
        elif case == "actual_usage_can_exceed_reservation":
            n=budget.reserve("hi", 10);budget.settle(n, 1200)
            assert budget.spent == 1200 and budget.snapshot()["remaining_estimated"] == 0
        elif case == "release_restores_budget":
            n=budget.reserve("hi", 10);budget.release(n)
            assert budget.reserved == 0 and budget.spent == 0
        elif case == "reject_negative_output":
            with pytest.raises(ValueError): budget.reserve("hi", -500)


# Level 7: Independent verifier correctness (11 cases)
VERIFIER_CASES = [
    ("deterministic_no_ai", None, "passed"),
    ("clean_ai_assessment", '{"concerns":[],"note":"checked"}', "passed"),
    ("ai_concern_forces_review", '{"concerns":["Not enough evidence"],"note":"review"}', "needs_review"),
    ("non_json_response", "oops", "needs_review"),
    ("markdown_fenced_json", '```json\n{"concerns":[],"note":"ok"}\n```', "passed"),
    ("non_string_concern", '{"concerns":[3],"note":"bad"}', "needs_review"),
    ("json_array_instead_object", '["bad"]', "needs_review"),
    ("ai_cannot_override_failed", '{"concerns":[],"note":"pass"}', "failed"),
    ("blocked_takes_priority", '{"concerns":[],"note":"pass"}', "blocked"),
    ("select_none_does_not_pass", '{"concerns":[],"note":"pass"}', "failed"),
    ("no_builder_history_shared", '{"concerns":[],"note":"pass"}', "passed"),
]


@pytest.mark.parametrize("case,answer,expected", VERIFIER_CASES, ids=[x[0] for x in VERIFIER_CASES])
def test_L7_verifier(tmp_path, monkeypatch, case, answer, expected):
    checks = [{"id":"customer-ready", "type":"file", "path":"result.txt"}]
    if case == "blocked_takes_priority":
        checks = [{"id":"tool", "type":"command", "argv":[sys.executable,"-c","print('ok')"]}]
    spec = write_spec(tmp_path, checks)
    if case not in ("ai_cannot_override_failed", "blocked_takes_priority"):
        (tmp_path / "result.txt").write_text("validated")
    if answer is not None:
        def fake_chat(prompt, budget, **kw):
            assert "builder_history" not in prompt
            assert "chain_of_thought" not in prompt
            assert "observed_tests" in prompt
            return answer
        monkeypatch.setattr("olyder.engine.chat", fake_chat)
    result = verify_once(spec, use_ai=answer is not None, only=set() if case == "select_none_does_not_pass" else None)
    assert result["status"] == expected


# Level 8: Execution loop and stop policy (11 cases)
LOOP_CASES = [
    "verify_only_no_builder", "builder_creates_output", "builder_modifies_spec_blocked", "builder_not_found_blocked", "builder_fails_nonzero_blocked", "failure_then_repair", "no_progress_terminates", "max_iterations_stops", "report_files_created", "negative_iteration_rejected", "deadline_exceeded_status",
]


@pytest.mark.parametrize("case", LOOP_CASES)
def test_L8_loop(tmp_path, case, monkeypatch):
    program = "from pathlib import Path;Path('result.txt').write_text('ready')"
    if case == "builder_modifies_spec_blocked":
        program = "from pathlib import Path;Path('olyder.json').write_text('{}')"
    elif case == "builder_fails_nonzero_blocked":
        program = "raise SystemExit(5)"
    elif case in ("no_progress_terminates", "max_iterations_stops"):
        program = "print('still working')"
    elif case == "failure_then_repair":
        program = "from pathlib import Path;p=Path('counter'); n=int(p.read_text())+1 if p.exists() else 1;p.write_text(str(n));Path('result.txt').write_text('ready' if n>=2 else 'wait')"
    builder = ["totally-uninstalled-binary"] if case == "builder_not_found_blocked" else [sys.executable,"-c", program]
    checks = [{"id":"ready", "type":"file", "path":"result.txt", "contains":"ready"}]
    spec = write_spec(tmp_path, checks, builder={"argv": builder}, limits={"max_iterations": 5, "max_tokens": 30000, "max_seconds": 20})
    enabled = case not in ("verify_only_no_builder",)
    if case == "negative_iteration_rejected":
        with pytest.raises(ValueError):
            run_loop(spec, allow_exec=True, execute_builder=True, use_ai=False, allow_network=False, output=tmp_path/"out", max_iterations=-2)
        return
    if case == "deadline_exceeded_status":
        import olyder.engine as engine
        orig = engine.verify_once
        def slow_verify(*args, **kwargs):
            time.sleep(1.2)
            return orig(*args, **kwargs)
        monkeypatch.setattr(engine, "verify_once", slow_verify)
        spec.raw["limits"]["max_seconds"] = 1
    result = run_loop(spec, allow_exec=enabled, execute_builder=enabled, use_ai=False, allow_network=False, output=tmp_path/"out", max_iterations=1 if case == "max_iterations_stops" else None)
    expected = {
        "verify_only_no_builder":"failed", "builder_creates_output":"passed", "builder_modifies_spec_blocked":"blocked", "builder_not_found_blocked":"blocked", "builder_fails_nonzero_blocked":"blocked", "failure_then_repair":"passed", "no_progress_terminates":"failed", "max_iterations_stops":"failed", "report_files_created":"passed", "deadline_exceeded_status":"blocked"
    }[case]
    assert result["status"] == expected, result
    if case == "no_progress_terminates": assert result["attempts"] == 3
    if case == "failure_then_repair": assert result["attempts"] == 2
    if case == "max_iterations_stops": assert result["attempts"] == 1
    if case == "report_files_created": assert all(Path(p).is_file() for p in result["paths"].values())


# Level 9: Agent integrations, reporting and external source gating (11 cases)
INTEGRATION_CASES = [
    "cli_init", "cli_init_refuses_overwrite", "skill_installs", "cli_plan", "mcp_list_tools", "mcp_verify_read_only", "mcp_unknown_tool", "mcp_invalid_params", "mcp_notification_no_reply", "html_escapes_payload", "network_sources_blocked",
]


@pytest.mark.parametrize("case", INTEGRATION_CASES)
def test_L9_integration(tmp_path, case, capsys):
    if case == "cli_init":
        assert main(["init", str(tmp_path)]) == 0
    elif case == "cli_init_refuses_overwrite":
        assert main(["init", str(tmp_path)]) == 0
        assert main(["init", str(tmp_path)]) == 2
    elif case == "skill_installs":
        assert main(["install-skill", "--project", str(tmp_path), "--target", "both"]) == 0
        assert (tmp_path / ".agents/skills/olyder/SKILL.md").is_file()
        assert (tmp_path / ".claude/skills/olyder/SKILL.md").is_file()
    elif case == "cli_plan":
        write_spec(tmp_path)
        assert main(["plan", "--spec", str(tmp_path/"olyder.json")]) == 0
        assert "locked_spec_sha256" in capsys.readouterr().out
    elif case == "mcp_list_tools":
        msg = process({"jsonrpc":"2.0", "id":1, "method":"tools/list"},tmp_path)
        assert {x["name"] for x in msg["result"]["tools"]} == {"olyder_plan","olyder_verify"}
    elif case == "mcp_verify_read_only":
        write_spec(tmp_path,[{"id":"script", "type":"command", "argv":[sys.executable,"-c","open('BAD','w').close()"]}])
        msg=process({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"olyder_verify"}},tmp_path)
        assert "blocked" in msg["result"]["content"][0]["text"]
        assert not (tmp_path/"BAD").exists()
    elif case == "mcp_unknown_tool":
        write_spec(tmp_path)
        msg=process({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"invalid"}},tmp_path)
        assert msg["error"]["code"]==-32601
    elif case == "mcp_invalid_params":
        msg=process({"jsonrpc":"2.0","id":1,"method":"tools/call","params":[]},tmp_path)
        assert msg["error"]["code"]==-32602
    elif case == "mcp_notification_no_reply":
        assert process({"jsonrpc":"2.0","method":"ping"},tmp_path) is None
    elif case == "html_escapes_payload":
        info={"goal":"<script>alert(1)</script>","status":"failed","spec_sha256":"abc","checks":[{"id":"x","status":"fail","type":"file","duration_ms":1,"details":"<img src=x>"}],"sources":[],"budget":{"spent":0}}
        result=save_report(info,tmp_path/"report")
        content=Path(result["html"]).read_text()
        assert "&lt;script&gt;" in content and "<script>alert(1)</script>" not in content
    elif case == "network_sources_blocked":
        result=collect(["https://example.org/"],network_allowed=False)
        assert len(result)==1 and result[0]["status"]=="blocked"
