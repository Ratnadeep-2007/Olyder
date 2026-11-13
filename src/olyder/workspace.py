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
import stat
from pathlib import Path

from .integrity import protected_paths

IGNORE = {'.git', '.olyder', '.venv', '.wheel-smoke', '__pycache__',
          '.pytest_cache', 'node_modules', '.mypy_cache', '.ruff_cache'}


class WorkspaceViolation(RuntimeError):
    pass


def _read_regular(path, limit=100_000_000):
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)|getattr(os,'O_BINARY',0)
    descriptor=os.open(path,flags)
    with os.fdopen(descriptor,'rb') as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise WorkspaceViolation('Only regular workspace files are allowed')
        data=source.read(limit+1)
        if len(data)>limit:
            raise WorkspaceViolation('File exceeds snapshot byte bound')
        return data


def _link(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def secret_path(name):
    return any(p in ('.env','.npmrc','.pypirc','.netrc','.aws','.ssh') or
               p.startswith('.env.') and p!='.env.example' for p in Path(name).parts)


def tree(root: Path, *, max_bytes=100_000_000, include_secrets=False) -> dict[str, str]:
    result = {}
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in dirs + files:
            if name in IGNORE or not include_secrets and secret_path(name):
                continue
            path = parent/name
            if _link(path):
                raise WorkspaceViolation('Symlink/reparse point rejected: '+path.relative_to(root).as_posix())
        dirs[:] = sorted(d for d in dirs if d not in IGNORE and (include_secrets or not secret_path(d)))
        for name in sorted(files):
            if name in IGNORE or not include_secrets and secret_path(name):
                continue
            p = parent/name
            if not stat.S_ISREG(p.lstat().st_mode):
                raise WorkspaceViolation('Special workspace file rejected: '+p.relative_to(root).as_posix())
            size = p.stat().st_size
            total += size
            if total > max_bytes or len(result) >= 20000:
                raise WorkspaceViolation('Workspace snapshot exceeds 100 MB / 20000 files')
            result[p.relative_to(root).as_posix()] = hashlib.sha256(_read_regular(p,max_bytes)).hexdigest()
    return result


def _copy(source, target, names):
    for name in names:
        src, dst = source/name, target/name
        if _link(src):
            raise WorkspaceViolation('Source changed to symlink during snapshot')
        if dst.is_dir():
            raise WorkspaceViolation('File/directory collision in proposal')
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(_read_regular(src))
        dst.chmod(stat.S_IMODE(src.lstat().st_mode)&0o777)


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
        return secret_path(name)

    def is_protected(self, name):
        return any(name == p or name.startswith(p+'/') for p in self.protected)

    def validate(self):
        if tree(self.trusted) != self.baseline:
            raise WorkspaceViolation('Trusted snapshot changed')
        proposed = tree(self.builder,include_secrets=True)
        forbidden = [n for n in proposed if self.is_protected(n) or self.secret(n) or
                     any(p.startswith(n+'/') for p in self.protected)]
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
        replacement_dirs=[]
        for name in proposed:
            destination=self.root/name
            if destination.is_dir():
                for directory,dirs,files in os.walk(destination,followlinks=False):
                    parent=Path(directory)
                    if any((parent/f).relative_to(self.root).as_posix() not in editable for f in files):
                        raise WorkspaceViolation('Directory replacement would remove ignored/private files')
                    if any(_link(parent/d) for d in dirs):
                        raise WorkspaceViolation('Directory replacement contains links')
                replacement_dirs.append(destination)
        for name in sorted(editable - proposed.keys()):
            (self.root/name).unlink()
        for destination in replacement_dirs:
            for directory,dirs,files in os.walk(destination,topdown=False):
                Path(directory).rmdir()
        _copy(self.builder, self.root, proposed)
        applied={n:h for n,h in tree(self.root).items() if not self.is_protected(n)}
        if applied!=proposed:
            raise WorkspaceViolation('Applied implementation does not match verified proposal')

    def evidence(self):
        return {'trusted_snapshot_sha256': hashlib.sha256(
            json.dumps(self.baseline, sort_keys=True).encode()).hexdigest(),
            'protected_paths': sorted(self.protected),
            'manifest_sha256': hashlib.sha256((self.state/'manifest.json').read_bytes()).hexdigest()}
