"""Best-effort defense-in-depth for accidental credential exposure in evidence.

This is not a DLP engine. Never pass sensitive source data to external models.
"""
from __future__ import annotations

import re

_PATTERNS = (
    re.compile(r"(?i)(\bauthorization\s*:\s*(?:bearer|basic)\s+)\S+"),
    re.compile(r"(?i)(\b(?:bearer|basic)\s+)\S+"),
    re.compile(r"(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|client[_-]?secret)\s*[:=]\s*)[\"']?[^\s\"']+"),
    re.compile(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@"),
)


def redact(text: str) -> str:
    output = text
    for rule in _PATTERNS:
        if rule.pattern.startswith('(?i)(https?://)'):
            output = rule.sub(r"\1[REDACTED]@", output)
        else:
            output = rule.sub(r"\1[REDACTED]", output)
    return output


def redact_values(value):
    """Preserve JSON structure while redacting textual fields, never raw JSON."""
    if isinstance(value,str):
        return redact(value)
    if isinstance(value,list):
        return [redact_values(v) for v in value]
    if isinstance(value,dict):
        return {k:redact_values(v) for k,v in value.items()}
    return value
