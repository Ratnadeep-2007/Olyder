"""Specification loading and strict validation. Specifications are intentionally small."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Spec:
    path: Path
    root: Path
    raw: dict
    digest: str

    @property
    def checks(self) -> list[dict]:
        return self.raw["checks"]

    @property
    def goal(self) -> str:
        return self.raw["goal"]


def load_spec(path: str | Path) -> Spec:
    file = Path(path).expanduser().resolve(strict=True)
    if not file.is_file():
        raise ConfigError("Specification must be a file")
    content = file.read_bytes()
    if len(content) > 256_000:
        raise ConfigError("Specification too large (256 KB maximum)")
    try:
        obj = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise ConfigError(f"Invalid JSON: {exc}") from exc
    if not isinstance(obj, dict) or not isinstance(obj.get("goal"), str) or not obj["goal"].strip():
        raise ConfigError("Specification must contain a nonempty string 'goal'")
    checks = obj.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ConfigError("Specify at least one acceptance check")
    ids = set()
    for i, c in enumerate(checks):
        if not isinstance(c, dict):
            raise ConfigError(f"Check {i} must be an object")
        if not isinstance(c.get("id"), str) or not c["id"].strip() or c["id"] in ids:
            raise ConfigError(f"Check {i} has missing or duplicate id")
        ids.add(c["id"])
        kind = c.get("type")
        if kind not in ("file", "command", "http", "browser"):
            raise ConfigError(f"Check {c['id']}: type must be file, command, http or browser")
        if kind == "command":
            argv = c.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
                raise ConfigError(f"Check {c['id']}: argv must be a nonempty string list")
        if kind == "file":
            if not isinstance(c.get("path"), str) or not c["path"].strip():
                raise ConfigError(f"Check {c['id']}: nonempty file path required")
            if "exists" in c and type(c["exists"]) is not bool:
                raise ConfigError(f"Check {c['id']}: exists must be boolean")
        if "contains" in c and not isinstance(c["contains"], str):
            raise ConfigError(f"Check {c['id']}: contains must be a string")
        if kind in ("command", "http", "browser"):
            timeout = c.get("timeout", 60)
            if type(timeout) is not int or not 1 <= timeout <= 300:
                raise ConfigError(f"Check {c['id']}: timeout must be an integer from 1 to 300")
        if kind == "command":
            if "exit_code" in c and (type(c["exit_code"]) is not int or not 0 <= c["exit_code"] <= 255):
                raise ConfigError(f"Check {c['id']}: exit_code must be an integer from 0 to 255")
        if kind in ("http", "browser"):
            u = c.get("url")
            parsed = urlparse(u) if isinstance(u, str) else None
            if not parsed or parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                raise ConfigError(f"Check {c['id']}: valid http(s) URL without embedded credentials required")
        if kind == "http" and "status" in c and (type(c["status"]) is not int or not 100 <= c["status"] <= 599):
            raise ConfigError(f"Check {c['id']}: status must be an HTTP status code")
        if kind == "browser":
            steps = c.get("steps", [])
            if not isinstance(steps, list) or len(steps) > 50:
                raise ConfigError(f"Check {c['id']}: steps must be a list of at most 50 actions")
            required = {
                "click": ("selector",), "fill": ("selector", "value"),
                "expect_text": ("text",), "expect_url": ("pattern",),
                "navigate": ("url",),
            }
            for step in steps:
                if not isinstance(step, dict) or step.get("action") not in required:
                    raise ConfigError(f"Check {c['id']}: invalid browser step")
                if any(not isinstance(step.get(field), str) or not step[field] for field in required[step["action"]] if field != "value"):
                    raise ConfigError(f"Check {c['id']}: missing/invalid browser step value")
                if step["action"] == "fill" and not isinstance(step.get("value"), str):
                    raise ConfigError(f"Check {c['id']}: fill value must be a string")
                if step["action"] == "expect_url":
                    pattern = step["pattern"]
                    if len(pattern) > 300:
                        raise ConfigError(f"Check {c['id']}: URL regex too long")
                    try:
                        __import__("re").compile(pattern)
                    except __import__("re").error as exc:
                        raise ConfigError(f"Check {c['id']}: invalid URL regex") from exc
                if step["action"] == "navigate":
                    target = urlparse(step["url"])
                    if target.scheme not in ("http", "https") or not target.hostname or target.username or target.password:
                        raise ConfigError(f"Check {c['id']}: invalid browser navigation URL")
    sources = obj.get("sources", [])
    if not isinstance(sources, list) or len(sources) > 12 or not all(
        isinstance(s, str) and urlparse(s).scheme == "https" and urlparse(s).hostname
        and not urlparse(s).username and not urlparse(s).password for s in sources
    ):
        raise ConfigError("sources must be at most 12 HTTPS URLs without embedded credentials")
    builder = obj.get("builder", {})
    if not isinstance(builder, dict):
        raise ConfigError("builder must be an object")
    if "argv" in builder and (not isinstance(builder["argv"], list) or not builder["argv"] or not all(isinstance(s, str) and bool(s) for s in builder["argv"])):
        raise ConfigError("builder.argv must be a nonempty string list")
    limits = obj.get("limits", {})
    if not isinstance(limits, dict):
        raise ConfigError("limits must be an object")
    for key in ("max_iterations", "max_tokens", "max_seconds"):
        if key in limits and (type(limits[key]) is not int or limits[key] <= 0):
            raise ConfigError(f"limits.{key} must be positive integer")
    return Spec(file, file.parent, obj, hashlib.sha256(content).hexdigest())


def safe_path(root: Path, path: str) -> Path:
    """Prevent relative paths and symlinks escaping a selected root for file checks."""
    if not path or Path(path).is_absolute():
        raise ConfigError("File check paths must be relative to workspace")
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ConfigError(f"File check path escapes workspace: {path}")
    return candidate


DEFAULT = {
    "goal": "Describe the user-visible outcome and requirements here",
    "checks": [
        {"id": "readme-exists", "type": "file", "path": "README.md", "exists": True},
        {"id": "unit-tests", "type": "command", "argv": ["python", "-m", "unittest", "discover", "-s", "tests"], "timeout": 60}
    ],
    "sources": [],
    "builder": {"argv": ["opencode", "run", "{prompt}"]},
    "limits": {"max_iterations": 3, "max_tokens": 30000, "max_seconds": 600}
}
