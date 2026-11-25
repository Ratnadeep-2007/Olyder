"""Best-effort defense-in-depth for accidental credential exposure in evidence.

This is not a DLP engine. Never pass sensitive source data to external models.
"""
from __future__ import annotations

import re

# Conventional credential names, matched as whole field names so unrelated
# values such as ``token_count`` and ``status`` stay readable.
_CREDENTIAL_NAMES = (
    r"authorization|proxy[-_]?authorization|"
    r"api[-_]?key|x[-_]?api[-_]?key|api[-_]?secret|"
    r"access[-_]?token|refresh[-_]?token|id[-_]?token|auth[-_]?token|"
    r"session[-_]?token|token|bearer|"
    r"password|passwd|secret|client[-_]?secret|"
    r"credentials?|private[-_]?key"
)
_CREDENTIAL_FIELD = re.compile(rf"(?i)(?:{_CREDENTIAL_NAMES})")

# Quoted JSON key/value pairs: replace only the value so the document stays
# valid JSON and the surrounding evidence is untouched.
_JSON_CREDENTIAL = re.compile(
    rf'(?i)("(?:{_CREDENTIAL_NAMES})"\s*:\s*)"(?:[^"\\]|\\.)*"'
)

_PATTERNS = (
    re.compile(r"(?i)(\bauthorization\s*:\s*(?:bearer|basic)\s+)[^\s\"']+"),
    re.compile(r"(?i)(\b(?:bearer|basic)\s+)[^\s\"']+"),
    re.compile(r"(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|client[_-]?secret)\s*[:=]\s*)[\"']?[^\s\"']+"),
    re.compile(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@"),
)


def redact(text: str) -> str:
    output = _JSON_CREDENTIAL.sub(r'\1"[REDACTED]"', text)
    for rule in _PATTERNS:
        if rule.pattern.startswith('(?i)(https?://)'):
            output = rule.sub(r"\1[REDACTED]@", output)
        else:
            output = rule.sub(r"\1[REDACTED]", output)
    return output


def redact_values(value):
    """Keep report keys and replace recognized credential values with a redaction marker."""
    if isinstance(value,str):
        return redact(value)
    if isinstance(value,list):
        return [redact_values(v) for v in value]
    if isinstance(value,dict):
        return {
            key: "[REDACTED]"
            if isinstance(key,str) and _CREDENTIAL_FIELD.fullmatch(key)
            else redact_values(item)
            for key,item in value.items()
        }
    return value
