import json
from pathlib import Path

import pytest

from olyder import evals


FIXTURES = Path(__file__).resolve().parents[1] / "evaluations"


def test_offline_checkout_pairs_and_keeps_oracle_out_of_development(tmp_path):
    work = tmp_path / "study"
    report = evals.offline(FIXTURES, work, tasks=["checkout"])
    assert report["kind"] == "offline_scripted"
    assert len(report["rows"]) == 6
    assert all(row["observed_tokens"] is None for row in report["rows"])
    assert any(row["false_completion"] for row in report["rows"])
    assert any(row["completed"] for row in report["rows"])
    assert report["groups"]["A"]["trials"] == report["groups"]["B"]["trials"] == 3
    for case in (work / "workspaces").iterdir():
        assert not any("oracle" in path.name for path in case.iterdir())
    assert json.loads((work / "report.json").read_text()) == report
    (work / "workspaces" / "checkout-1-A" / "app.py").write_text("def solve(value): return 1")
    with pytest.raises(ValueError, match="Submission changed after recording"):
        evals.score(FIXTURES, work, FIXTURES / "offline-oracles-v1.json")


def test_live_plan_requires_explicit_consent_and_same_start(tmp_path):
    params = dict(mode="live", agent="example", model="provider/model@version", token_budget=1000,
                  oracle_sha256="a" * 64, image="sha256:" + "b" * 64)
    with pytest.raises(ValueError, match="authorization"):
        evals.prepare(FIXTURES, tmp_path / "denied", **params)
    root = tmp_path / "study"
    plan = evals.prepare(FIXTURES, root, tasks=["checkout"], allow_live=True, **params)
    assert plan["agent"] == "example"
    for pair in range(1, 4):
        a, b = (root / "workspaces" / f"checkout-{pair}-{group}" for group in ("A", "B"))
        assert {p.name: p.read_bytes() for p in a.iterdir()} == {
            p.name: p.read_bytes() for p in b.iterdir()
        }
    with pytest.raises(ValueError, match="isolated"):
        evals.score(FIXTURES, root, FIXTURES / "offline-oracles-v1.json")


def test_scorer_counts_candidate_exceptions_separately_from_runner_failure(monkeypatch):
    cases = [{"id": "example", "category": "functional", "input": 1, "expected": 1}]
    candidate = b"def solve(value):\n    raise ValueError('bad candidate')\n"
    assert evals._hidden(candidate, cases, image=None)[0]["status"] == "fail"
    monkeypatch.setattr(evals, "_execute", lambda *_args, **_kwargs: (None, "runner unavailable"))
    assert evals._hidden(candidate, cases, image=None)[0]["status"] == "error"
