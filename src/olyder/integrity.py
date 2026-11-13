"""In-process fingerprints of independently supplied acceptance tests.

A tampering detector is NOT an OS sandbox; its guarantees only hold while the
Olyder process and its memory remain trusted. Builder workspaces still need
independent filesystem/credential isolation for hostile code.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .config import Spec, safe_path


def _test_like(value: str) -> bool:
    path = Path(value)
    name = path.name.lower()
    parts = {p.lower() for p in path.parts}
    return (
        "tests" in parts
        or name.startswith(("test_", "acceptance_"))
        or name.endswith(("_test.py", ".feature"))
    )


def protected_paths(spec: Spec) -> list[Path]:
    """Protect all existing conventional tests plus user-selected evidence.

    Directly referenced test scripts are protected even outside a tests folder.
    Non-test source code is not protected, so the builder can legitimately fix it.
    """
    root = spec.root.resolve()
    candidates: set[Path] = set()
    for dirname in ("tests", "features", "specs"):
        path = root / dirname
        if path.is_dir():
            candidates.add(path)
    for pattern in ("test_*.py", "*_test.py", "acceptance_*.py", "*.feature"):
        candidates.update(root.glob(pattern))
    for check in spec.checks:
        if check["type"] != "command":
            continue
        for arg in check["argv"]:
            if not _test_like(arg):
                continue
            candidate = root / arg
            if not candidate.is_absolute() or not candidate.is_relative_to(root):
                continue
            if candidate.exists() or candidate.is_symlink():
                candidates.add(candidate)
    for value in spec.raw.get("protected_paths", []):
        candidates.add(safe_path(root, value))
    return sorted(candidates, key=str)


def _path_record(path: Path) -> tuple[str, str]:
    if path.is_symlink():
        return "symlink", os.readlink(path)
    if path.is_file():
        return "file", hashlib.sha256(path.read_bytes()).hexdigest()
    if path.is_dir():
        return "dir", ""
    return "missing", ""


def _digest(path: Path) -> str:
    # Hash names, types, and all file bytes. Directory additions/removals count.
    if path.is_dir() and not path.is_symlink():
        entries = [path, *sorted(path.rglob("*"), key=str)]
    else:
        entries = [path]
    h = hashlib.sha256()
    for item in entries:
        kind, data = _path_record(item)
        name = "." if item == path else item.relative_to(path).as_posix()
        for value in (name, kind, data):
            h.update(value.encode("utf-8", "surrogateescape"))
            h.update(b"\0")
    return h.hexdigest()


def snapshot(spec: Spec) -> dict[str, str]:
    return {str(p.relative_to(spec.root.resolve())): _digest(p) for p in protected_paths(spec)}


def changed(spec: Spec, baseline: dict[str, str]) -> list[str]:
    root = spec.root.resolve()
    mismatches = []
    for relative, previous in baseline.items():
        p = root / relative
        if _digest(p) != previous:
            mismatches.append(relative)
    # If a previously missing test tree now appears, the check harness is no
    # longer the same evidence. New paths under existing directories are caught.
    return mismatches
