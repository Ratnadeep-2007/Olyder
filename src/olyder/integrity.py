"""In-process fingerprints of independently supplied acceptance tests.

A tampering detector is NOT an OS sandbox; its guarantees only hold while the
Olyder process and its memory remain trusted. Builder workspaces still need
independent filesystem/credential isolation for hostile code.
"""
from __future__ import annotations

import hashlib
import os
from fnmatch import fnmatchcase
from pathlib import Path, PureWindowsPath

from .config import Spec, safe_path

TRUSTED_PYTEST_CONFIG = (
    "pyproject.toml",
    "pytest.toml",
    ".pytest.toml",
    "pytest.ini",
    ".pytest.ini",
    "tox.ini",
    "setup.cfg",
    "conftest.py",
)
_PYTEST_EXECUTABLES = frozenset({"pytest", "pytest.exe", "py.test", "py.test.exe"})


def _explicit_pytest(check: dict) -> bool:
    argv = check["argv"]
    return (
        PureWindowsPath(argv[0]).name.casefold() in _PYTEST_EXECUTABLES
        or any(flag == "-m" and module.casefold() == "pytest"
               for flag, module in zip(argv, argv[1:]))
    )


def trusted_pytest_config(spec: Spec) -> tuple[str, ...]:
    """Root files that can redirect an explicitly requested pytest run.

    Only known names at the project root are scoped in. Missing names are still
    reserved by ProtectedWorkspace so a builder cannot create them later.
    Without an explicit pytest command, ordinary project configuration remains
    editable and legacy behaviour is unchanged.
    """
    if any(check.get("type") == "command" and _explicit_pytest(check) for check in spec.checks):
        return TRUSTED_PYTEST_CONFIG
    return ()


def _test_like(value: str) -> bool:
    path = Path(value)
    name = path.name.lower()
    parts = {p.lower() for p in path.parts}
    return (
        "tests" in parts
        or name.startswith(("test_", "acceptance_"))
        or name.endswith(("_test.py", ".feature"))
    )


def root_test_asset(name: str) -> bool:
    path = Path(name)
    return len(path.parts) == 1 and any(
        fnmatchcase(path.name.casefold(), pattern)
        for pattern in ("test_*.py", "*_test.py", "acceptance_*.py", "*.feature")
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
    candidates.update(path for path in root.iterdir() if root_test_asset(path.name))
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
    for name in trusted_pytest_config(spec):
        candidate = root / name
        if candidate.exists() or candidate.is_symlink():
            candidates.add(candidate)
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
    """Report protected paths that differ from ``baseline`` in either direction.

    ``baseline`` stays a plain path-to-digest mapping, so snapshots written by
    earlier versions remain usable. Additions are compared from the current
    snapshot as well, which catches a test tree or pytest config file that was
    absent when the baseline was taken. A policy that starts tracking a new
    existing path may therefore report that path once on an old baseline; the
    conservative result is intentional.
    """
    current = snapshot(spec)
    return sorted(
        relative
        for relative in baseline.keys() | current.keys()
        if baseline.get(relative) != current.get(relative)
    )
