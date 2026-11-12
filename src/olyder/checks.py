"""Execute reproducible acceptance checks with observed evidence, not AI assertions."""
from __future__ import annotations

import re
import subprocess
import tempfile
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib import request, error

from .config import ConfigError, safe_path


@dataclass
class Result:
    id: str
    status: str  # pass | fail | blocked
    type: str
    duration_ms: int
    details: str

    def json(self):
        return asdict(self)


def _run(check: dict, root: Path, allow_exec: bool) -> tuple[bool, str]:
    kind = check["type"]
    if kind == "file":
        p = safe_path(root, check["path"])
        expected = check.get("exists", True)
        if type(expected) is not bool:
            raise ConfigError("file exists must be boolean")
        if (p.exists() == expected) is False:
            return False, f"Expected exists={expected} for {check['path']}"
        if "contains" in check:
            if not p.is_file():
                return False, "File missing or not regular file"
            data = p.read_bytes()[:1_000_000].decode("utf-8", errors="replace")
            return check["contains"] in data, "Text content assertion"
        return True, "File existence assertion"
    if kind == "command":
        if not allow_exec:
            raise PermissionError("Command execution disabled; pass --allow-exec after reviewing spec")
        timeout = min(300, max(1, int(check.get("timeout", 60))))
        try:
            with tempfile.TemporaryFile(mode="w+t", encoding="utf-8", errors="replace") as captured:
                cp = subprocess.run(check["argv"], cwd=root, stdout=captured, stderr=subprocess.STDOUT, text=True, timeout=timeout, errors="replace", shell=False)
                length = captured.tell()
                captured.seek(max(0, length - 3000))
                output = captured.read()
            output = re.sub(r"(?i)(api[_-]?key|token|password)\s*[:=]\s*\S+", r"\1=[REDACTED]", output)
            return cp.returncode == check.get("exit_code", 0), f"Exit {cp.returncode}; tail: {output}"
        except subprocess.TimeoutExpired:
            return False, f"Timed out after {timeout}s"
        except FileNotFoundError as exc:
            return False, f"Executable not found: {exc.filename}"
    if kind == "http":
        if not allow_exec:
            raise PermissionError("HTTP checks disabled; pass --allow-exec after reviewing spec")
        # GET only: no credentials, no arbitrary headers, no POST side effects.
        req = request.Request(check["url"], headers={"User-Agent": "Olyder/0.1"}, method="GET")
        class NoRedirects(request.HTTPRedirectHandler):
            # Never follow a redirect to a different or internal address implicitly.
            # Verify the redirect code explicitly, or declare the final URL as a new check.
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = request.build_opener(NoRedirects)
        try:
            try:
                response = opener.open(req, timeout=min(30, int(check.get("timeout", 10))))
            except error.HTTPError as exc:
                # HTTP 4xx/5xx is an observable response, not a transport failure.
                response = exc
            with response:
                status = response.status
                body = response.read(100_000).decode(errors="replace")
            ok = status == int(check.get("status", 200))
            if "contains" in check:
                ok = ok and check["contains"] in body
            return ok, f"HTTP status {status}; content condition {'checked' if 'contains' in check else 'not configured'}"
        except (error.URLError, TimeoutError) as exc:
            return False, f"HTTP failed: {type(exc).__name__}"
    if kind == "browser":
        if not allow_exec:
            raise PermissionError("Browser checks disabled; pass --allow-exec after reviewing spec")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Browser tests need: pip install 'olyder-agent[browser]' and playwright install chromium")
        with sync_playwright() as pw:
            # Optional executable path permits a system Chromium install; by default
            # Playwright uses its managed browser binary.
            executable = os.getenv("OLYDER_CHROMIUM_PATH")
            browser = pw.chromium.launch(headless=True, executable_path=executable or None)
            context = browser.new_context()
            page = context.new_page()
            try:
                page.goto(check["url"], timeout=20_000)
                for step in check.get("steps", []):
                    action = step.get("action")
                    if action == "click":
                        page.locator(step["selector"]).click(timeout=5000)
                    elif action == "fill":
                        page.locator(step["selector"]).fill(str(step["value"]), timeout=5000)
                    elif action == "expect_text":
                        if str(step["text"]) not in page.locator(step.get("selector", "body")).inner_text(timeout=5000):
                            return False, f"Expected text not found: {str(step['text'])[:120]}"
                    elif action == "expect_url":
                        if not re.search(step["pattern"], page.url):
                            return False, f"URL did not match pattern {step['pattern']}"
                    elif action == "navigate":
                        page.goto(step["url"], timeout=20_000)
                    else:
                        raise ConfigError(f"Unsupported browser action: {action}")
                return True, f"Browser scenario completed; final URL {page.url}"
            finally:
                context.close()
                browser.close()
    raise ConfigError(f"Unsupported check type: {kind}")


def run_checks(checks: list[dict], root: Path, allow_exec: bool = False, only: set[str] | None = None) -> list[Result]:
    out = []
    for check in checks:
        if only is not None and check["id"] not in only:
            continue
        start = time.monotonic()
        try:
            ok, details = _run(check, root, allow_exec)
            status = "pass" if ok else "fail"
        except (PermissionError, RuntimeError) as exc:
            status, details = "blocked", str(exc)
        except (ConfigError, OSError, ValueError, KeyError, re.error) as exc:
            status, details = "fail", f"Invalid check or I/O: {type(exc).__name__}: {str(exc)[:250]}"
        except Exception as exc:
            # Optional browser dependencies may raise provider-specific exceptions.
            # Treat these as failed checks rather than crashing the whole verification run.
            status, details = "fail", f"Unexpected check failure: {type(exc).__name__}"
        out.append(Result(check["id"], status, check["type"], round((time.monotonic()-start)*1000), details[:3000]))
    return out
