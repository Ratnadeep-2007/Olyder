"""Practical end-user CLI evaluation using an intentionally broken checkout app.

These are real subprocess CLI executions and Python unittest oracles, not
mocked Olyder statuses or provider/model API results. No paid AI calls.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


BROKEN = """def total(price, quantity, discount_percent=0):
    return round(price * quantity - discount_percent, 2)
"""
FIXED = """def total(price, quantity, discount_percent=0):
    if price < 0 or quantity < 0 or not 0 <= discount_percent <= 100:
        raise ValueError("Invalid pricing inputs")
    return round(price * quantity * (1 - discount_percent / 100), 2)
"""
ORACLE = """import unittest
from app import total


class CheckoutAcceptance(unittest.TestCase):
    def test_cart_total(self):
        self.assertEqual(total(50, 2), 100.0)

    def test_percent_discount(self):
        self.assertEqual(total(100, 2, 25), 150.0)

    def test_invalid_discount(self):
        with self.assertRaises(ValueError):
            total(100, 1, 120)

    def test_invalid_price(self):
        with self.assertRaises(ValueError):
            total(-1, 1, 0)


if __name__ == "__main__":
    unittest.main()
"""


def _project(root: Path, *, with_builder: str | None = None):
    (root / "tests").mkdir()
    (root / "tests" / "test_checkout.py").write_text(ORACLE, encoding="utf-8")
    (root / "app.py").write_text(BROKEN, encoding="utf-8")
    spec = {
        "goal": "Compute correct checkout totals and reject invalid inputs",
        "schema_version": 2,
        "requirements": [
            {"id": "cart", "text": "Correct cart price calculation", "mandatory": True,
             "acceptance_check_ids": ["checkout-oracle"]}
        ],
        "checks": [
            {"id": "checkout-oracle", "type": "command",
             "argv": [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
             "timeout": 12}
        ],
        "limits": {"max_seconds": 35, "max_iterations": 2, "max_tokens": 3000},
    }
    if with_builder is not None:
        spec["builder"] = {"argv": [sys.executable, "-c", with_builder]}
    (root / "olyder.json").write_text(json.dumps(spec), encoding="utf-8")
    return root


def _cli(root: Path, *args: str):
    p = subprocess.run([sys.executable, "-m", "olyder", *args], cwd=root,
                       capture_output=True, text=True, timeout=50)
    report_path = root / ".olyder" / "report.json"
    result = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    return p, result


def test_real_checkout_bug_detected_and_fix_verified(tmp_path):
    root = _project(tmp_path)
    bad, report = _cli(root, "verify", "--allow-exec")
    assert bad.returncode == 1, (bad.stdout, bad.stderr)
    assert report["status"] == "failed"
    assert report["checks"][0]["id"] == "checkout-oracle"
    assert report["checks"][0]["status"] == "fail"
    assert report["full_suite_executed"] is True
    assert report["metrics"]["executed_checks"] == 1
    assert (root / ".olyder/report.md").is_file()
    assert (root / ".olyder/report.html").is_file()
    (root / "app.py").write_text(FIXED, encoding="utf-8")
    good, report = _cli(root, "verify", "--allow-exec")
    assert good.returncode == 0, (good.stdout, good.stderr)
    assert report["status"] == "passed"
    assert report["checks"][0]["status"] == "pass"
    assert report["metrics"]["execution_coverage_percent"] == 100.0
    assert report["requirement_coverage"]["cart"]["satisfied"]


def test_permission_denial_does_not_claim_a_pass(tmp_path):
    root = _project(tmp_path)
    denied, report = _cli(root, "verify")
    assert denied.returncode == 1, (denied.stdout, denied.stderr)
    assert report["status"] == "blocked"
    assert report["checks"][0]["status"] == "blocked"
    assert report["metrics"]["executed_checks"] == 0
    assert (root / "app.py").read_text(encoding="utf-8") == BROKEN


def test_real_builder_repairs_in_detached_proposal_and_applies(tmp_path):
    code = 'from pathlib import Path;Path("app.py").write_text(' + repr(FIXED) + ')'
    root = _project(tmp_path, with_builder=code)
    result, report = _cli(root, "run", "--allow-exec", "--execute-builder", "--unsafe-host")
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert report["status"] == "passed"
    assert report["verification_target"] == "detached_proposal"
    assert report["application_status"] == "complete"
    assert report["full_suite_executed"] is True
    assert report["agent_usage"]["enforced_provider_quota"] is False
    assert (root / "app.py").read_text(encoding="utf-8") == FIXED


def test_builder_attempt_to_replace_acceptance_tests_is_blocked(tmp_path):
    sabotage = 'from pathlib import Path;Path("tests/test_checkout.py").write_text("pass\\n")'
    root = _project(tmp_path, with_builder=sabotage)
    result, report = _cli(root, "run", "--allow-exec", "--execute-builder", "--unsafe-host")
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert report["status"] == "blocked"
    assert report["stop_reason"] == "integrity_violation"
    assert (root / "tests" / "test_checkout.py").read_text(encoding="utf-8") == ORACLE
    assert (root / "app.py").read_text(encoding="utf-8") == BROKEN


def test_host_builder_without_explicit_unsafe_permission_is_rejected(tmp_path):
    code = 'from pathlib import Path;Path("app.py").write_text(' + repr(FIXED) + ')'
    root = _project(tmp_path, with_builder=code)
    result, _ = _cli(root, "run", "--allow-exec", "--execute-builder")
    assert result.returncode == 2
    assert "unsafe-host" in result.stderr or "docker" in result.stderr
    assert (root / "app.py").read_text(encoding="utf-8") == BROKEN


def test_weak_file_only_check_can_pass_with_real_bug(tmp_path):
    root = _project(tmp_path)
    spec_path = root / "olyder.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec.pop("requirements")
    spec["checks"] = [{"id": "exists", "type": "file", "path": "app.py"}]
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    p, report = _cli(root, "verify")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert report["status"] == "passed"
    assert report["checks"][0]["status"] == "pass"
    assert (root / "app.py").read_text(encoding="utf-8") == BROKEN
