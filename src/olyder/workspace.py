"""Detached proposal and trusted verification trees.

Only the builder directory is mounted writable in an isolated backend. Host
mode is explicitly unsafe: separate directories are not an OS security boundary.
Symlinks/reparse points are rejected, not copied or followed. Local dependencies
are intentionally not copied; install them in a reviewed runtime image.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from .integrity import protected_paths

IGNORE = {'.git', '.olyder', '.venv', '.wheel-smoke', '__pycache__',
          '.pytest_cache', 'node_modules', '.mypy_cache', '.ruff_cache'}


class WorkspaceViolation(RuntimeError):
    pass


def _link(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def tree(root: Path, *, max_bytes=100_000_000) -> dict[str, str]:
    result = {}
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in dirs + files:
            if name in IGNORE:
                continue
            path = parent/name
            if _link(path):
                raise WorkspaceViolation('Symlink/reparse point rejected: '+path.relative_to(root).as_posix())
        dirs[:] = sorted(d for d in dirs if d not in IGNORE)
        for name in sorted(files):
            if name in IGNORE:
                continue
            p = parent/name
            size = p.stat().st_size
            total += size
            if total > max_bytes or len(result) >= 20000:
                raise WorkspaceViolation('Workspace snapshot exceeds 100 MB / 20000 files')
            result[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def _copy(source, target, names):
    for name in names:
        src, dst = source/name, target/name
        if _link(src):
            raise WorkspaceViolation('Source changed to symlink during snapshot')
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


class ProtectedWorkspace:
    def __init__(self, spec, state: Path):
        self.root = spec.root.resolve()
        self.state = state.resolve()
        self.state.mkdir(parents=True, exist_ok=False)
        self.trusted = self.state/'trusted'
        self.builder = self.state/'builder'
        self.verify_root = self.state/'harness'
        self.trusted.mkdir(); self.builder.mkdir()
        self.baseline = tree(self.root)
        self.protected = {'tests', 'features', 'specs', spec.path.relative_to(self.root).as_posix()}
        self.protected.update(p.relative_to(self.root).as_posix() for p in protected_paths(spec))
        _copy(self.root, self.trusted, self.baseline)
        if tree(self.trusted) != self.baseline or tree(self.root) != self.baseline:
            raise WorkspaceViolation('Source changed during snapshot capture')
        _copy(self.trusted, self.builder, [n for n in self.baseline if not self.is_protected(n) and not self.secret(n)])
        self.manifest = {'schema_version': 1, 'root': str(self.root),
                         'baseline': self.baseline, 'protected': sorted(self.protected)}
        (self.state/'manifest.json').write_text(json.dumps(self.manifest, sort_keys=True), encoding='utf-8')

    @classmethod
    def reopen(cls, state: Path, manifest_digest: str):
        obj = cls.__new__(cls)
        obj.state = state.resolve()
        path = obj.state/'manifest.json'
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest_digest:
            raise WorkspaceViolation('Saved workspace manifest changed')
        obj.manifest = json.loads(path.read_text(encoding='utf-8'))
        if obj.manifest.get('schema_version') != 1:
            raise WorkspaceViolation('Unsupported workspace schema')
        obj.root = Path(obj.manifest['root'])
        obj.baseline, obj.protected = obj.manifest['baseline'], set(obj.manifest['protected'])
        obj.trusted, obj.builder, obj.verify_root = (obj.state/n for n in ('trusted','builder','harness'))
        obj.validate()
        return obj

    @staticmethod
    def secret(name):
        return any(p == '.env' or p.startswith('.env.') and p != '.env.example' for p in Path(name).parts)

    def is_protected(self, name):
        return any(name == p or name.startswith(p+'/') for p in self.protected)

    def validate(self):
        if tree(self.trusted) != self.baseline:
            raise WorkspaceViolation('Trusted snapshot changed')
        proposed = tree(self.builder)
        forbidden = [n for n in proposed if self.is_protected(n) or self.secret(n)]
        if forbidden:
            raise WorkspaceViolation('Builder supplied protected or secret paths: '+', '.join(forbidden[:5]))
        return proposed

    def harness(self):
        proposed = self.validate()
        # Resolved target is a fixed child of the run directory, never a task path.
        if self.verify_root.exists():
            if _link(self.verify_root) or self.verify_root.parent != self.state:
                raise WorkspaceViolation('Unsafe verification root')
            shutil.rmtree(self.verify_root)
        self.verify_root.mkdir()
        _copy(self.trusted, self.verify_root, [n for n in self.baseline if self.is_protected(n)])
        _copy(self.builder, self.verify_root, proposed)
        return self.verify_root

    def apply(self):
        proposed = self.validate()
        if tree(self.root) != self.baseline:
            raise WorkspaceViolation('Original workspace changed; proposal not applied')
        editable = {n for n in self.baseline if not self.is_protected(n) and not self.secret(n)}
        for name in sorted(editable - proposed.keys()):
            (self.root/name).unlink()
        _copy(self.builder, self.root, proposed)

    def evidence(self):
        return {'trusted_snapshot_sha256': hashlib.sha256(
            json.dumps(self.baseline, sort_keys=True).encode()).hexdigest(),
            'protected_paths': sorted(self.protected),
            'manifest_sha256': hashlib.sha256((self.state/'manifest.json').read_bytes()).hexdigest()}
