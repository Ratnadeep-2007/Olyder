"""Keep synthetic credential values out of shareable verification reports."""

import json
from pathlib import Path

from olyder.privacy import redact, redact_values
from olyder.report import save_report


def test_redacts_json_log_credentials_and_keeps_log_parseable():
    log = json.dumps({
        "API_KEY": "fixture key with spaces",
        "password": "fixture with a \"quoted\" word",
        "authorization": "Bearer fixture-token",
        "status": "configured",
    })
    expected = {
        "API_KEY": "[REDACTED]",
        "password": "[REDACTED]",
        "authorization": "[REDACTED]",
        "status": "configured",
    }
    redacted = redact(log)
    assert json.loads(redacted) == expected
    assert redact(redacted) == redacted


def test_redacts_named_fields_in_nested_data_without_mutating_input():
    evidence = {
        "entries": [{"client-secret": "fixture-secret", "token_count": 12}],
        "refresh_token": "fixture-refresh",
        "nested": {"access_token": "fixture-access"},
    }
    assert redact_values(evidence) == {
        "entries": [{"client-secret": "[REDACTED]", "token_count": 12}],
        "refresh_token": "[REDACTED]",
        "nested": {"access_token": "[REDACTED]"},
    }
    assert evidence["entries"][0]["client-secret"] == "fixture-secret"


def test_report_formats_hide_credential_fields_and_keep_check_evidence(tmp_path):
    paths = save_report({
        "goal": "Protect verification evidence",
        "status": "passed",
        "checks": [{
            "id": "configuration",
            "status": "pass",
            "type": "command",
            "duration_ms": 0,
            "details": json.dumps({"api_key": "fixture-report-value", "output": "job finished"}),
        }],
        "environment": {"password": "fixture-environment-value"},
    }, tmp_path)
    for path in paths.values():
        evidence = Path(path).read_text(encoding="utf-8")
        assert "fixture-report-value" not in evidence
        assert "fixture-environment-value" not in evidence
        assert "job finished" in evidence
        assert "REDACTED" in evidence
