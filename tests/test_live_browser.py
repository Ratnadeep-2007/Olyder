"""Explicit opt-in live Chromium smoke test (not counted in the 99-case matrix)."""
import os
import shutil
from pathlib import Path
import pytest
from olyder.checks import run_checks


@pytest.mark.skipif(os.getenv("OLYDER_LIVE_BROWSER") != "1", reason="Set OLYDER_LIVE_BROWSER=1 and install Chromium to run the live browser check")
def test_live_browser_smoke(tmp_path):
    pytest.importorskip("playwright.sync_api")
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium:
        os.environ["OLYDER_CHROMIUM_PATH"] = chromium
    # Browser cannot use arbitrary file: URLs; a local web service is required.
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html><body>real browser passed</body></html>")
        def log_message(self,*args): pass
    with ThreadingHTTPServer(("127.0.0.1",0), H) as server:
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            check={"id":"live", "type":"browser", "url":f"http://127.0.0.1:{server.server_port}/", "steps":[{"action":"expect_text","text":"real browser passed"}]}
            result=run_checks([check],tmp_path,allow_exec=True)
            assert result[0].status == "pass", result[0].details
        finally:
            server.shutdown()
            thread.join(timeout=3)
