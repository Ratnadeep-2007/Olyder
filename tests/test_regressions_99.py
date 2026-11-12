"""Follow-up behavioral regressions discovered during the 99-case QA cycle."""
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
import pytest

from olyder.config import ConfigError, load_spec
from olyder.engine import run_loop, verify_once
from olyder.quota import Budget
from olyder.research import collect
from olyder.checks import run_checks
from olyder.models import ModelError, chat


def spec(root, checks=None, **overrides):
    data = {"goal":"observed outcome", "checks":checks if checks is not None else [{"id":"present","type":"file","path":"test.txt"}]}
    data.update(overrides)
    f=root / "olyder.json"
    f.write_text(json.dumps(data))
    return load_spec(f)


def test_external_source_blocked_means_needs_review(tmp_path):
    (tmp_path/"test.txt").write_text("done")
    result=verify_once(spec(tmp_path, sources=["https://example.org/test"]),allow_network=False)
    assert result["status"] == "needs_review"
    assert result["metrics"]["sources_unavailable"] == 1


def test_external_source_not_unreasonably_loops_builder(tmp_path):
    (tmp_path/"test.txt").write_text("done")
    run=run_loop(spec(tmp_path, sources=["https://example.org/test"]),allow_exec=False,execute_builder=False,use_ai=False,allow_network=False,output=tmp_path/"report")
    assert run["status"] == "needs_review" and run["attempts"] == 1


def test_research_refuses_302_redirect(monkeypatch):
    import olyder.research as research
    redirects=[]
    class Handler:
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            redirects.append(newurl)
            return None
    class FakeOpener:
        def open(self, req, timeout):
            raise HTTPError(req.full_url,302,"found",{"Location":"http://169.254.169.254/latest/meta-data"},None)
    monkeypatch.setattr(research.request,"build_opener",lambda *_:FakeOpener())
    data=collect(["https://sample.invalid/"],network_allowed=True)
    assert data[0]["status"]=="blocked"
    assert "Redirect refused" in data[0]["reason"]


def test_browser_fill_requires_explicit_value(tmp_path):
    data={"id":"fill","type":"browser","url":"http://localhost/","steps":[{"action":"fill","selector":"#password"}]}
    with pytest.raises(ConfigError): spec(tmp_path,[data])


def test_url_regex_syntax_checked_before_run(tmp_path):
    data={"id":"url","type":"browser","url":"http://localhost/","steps":[{"action":"expect_url","pattern":"["}]}
    with pytest.raises(ConfigError): spec(tmp_path,[data])


def test_http_metadata_endpoint_not_contacted_by_default(tmp_path,monkeypatch):
    import olyder.checks as checks
    sent=[]
    monkeypatch.setattr(checks.request,"build_opener",lambda *_: sent.append(1))
    data=spec(tmp_path,[{"id":"metadata","type":"http","url":"http://169.254.169.254/latest/meta-data/"}])
    result=verify_once(data,allow_exec=True,allow_network=False)
    assert result["status"]=="blocked" and not sent


def test_quota_cannot_double_settle():
    b=Budget(3000)
    r=b.reserve("short",20)
    b.settle(r,13)
    with pytest.raises(ValueError): b.settle(r,13)


def test_quota_cannot_double_release():
    b=Budget(3000)
    r=b.reserve("short",20)
    b.release(r)
    with pytest.raises(ValueError): b.release(r)


def test_model_unconfigured_does_not_consume_tokens(monkeypatch):
    monkeypatch.delenv("OLYDER_MODEL",raising=False)
    monkeypatch.delenv("OLYDER_API_KEY",raising=False)
    b=Budget(3000)
    with pytest.raises(ModelError): chat("test",b,system="test")
    assert b.snapshot()["spent"] == 0


def test_loop_uses_full_criteria_on_retry(tmp_path):
    s=spec(tmp_path,[{"id":"a","type":"file","path":"a"},{"id":"b","type":"file","path":"b"}],builder={"argv":[sys.executable,"-c","from pathlib import Path;Path('a').touch();Path('b').touch()"]})
    out=run_loop(s,allow_exec=True,execute_builder=True,use_ai=False,allow_network=False,output=tmp_path/"output")
    assert out["status"]=="passed"
    assert {x["id"] for x in out["checks"]} == {"a","b"}
