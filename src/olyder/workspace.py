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
import re
import shutil
import stat
from pathlib import Path

from .config import safe_path
from .integrity import _test_like, protected_paths

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


def directories(root, *, include_secrets=False):
    if not root.is_dir() or _link(root):
        raise WorkspaceViolation('Directory root is missing or is a link')
    result=set()
    for directory,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if d.casefold() not in IGNORE and (include_secrets or not secret_path(d))]
        for name in dirs:
            path=Path(directory)/name
            if _link(path):
                raise WorkspaceViolation('Directory links are not allowed')
            result.add(path.relative_to(root).as_posix())
            if len(result)>20000:
                raise WorkspaceViolation('Directory snapshot exceeds size bound')
    return result


def _mkdirs(target, names):
    for name in sorted(names,key=lambda n:(len(Path(n).parts),n)):
        (target/name).mkdir(parents=True,exist_ok=True)


def _acceptance_asset(root, argument):
    reference=argument.split('::',1)[0]
    asset=safe_path(root,reference)
    if asset.exists():
        return asset
    if '/' not in reference and '\\' not in reference and not reference.endswith(('.py','.js','.sh')) and re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',reference):
        parts=reference.split('.')
        for length in range(len(parts),0,-1):
            module=Path(*parts[:length])
            for candidate in (module.with_suffix('.py'),module/'__init__.py'):
                asset=safe_path(root,candidate.as_posix())
                if asset.is_file():
                    return asset
    raise WorkspaceViolation('Acceptance script unavailable: '+argument)


def _link(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def secret_path(name):
    return any(p in ('.env','.npmrc','.pypirc','.netrc','.aws','.ssh') or
               p.startswith('.env.') and p!='.env.example' for p in (part.casefold() for part in Path(name).parts))


def tree(root: Path, *, max_bytes=100_000_000, include_secrets=False) -> dict[str, str]:
    if not root.is_dir() or _link(root):
        raise WorkspaceViolation('Workspace root is missing or is a link')
    result = {}
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in dirs + files:
            if name.casefold() in IGNORE or not include_secrets and secret_path(name):
                continue
            path = parent/name
            if _link(path):
                raise WorkspaceViolation('Symlink/reparse point rejected: '+path.relative_to(root).as_posix())
        dirs[:] = sorted(d for d in dirs if d.casefold() not in IGNORE and (include_secrets or not secret_path(d)))
        for name in sorted(files):
            if name.casefold() in IGNORE or not include_secrets and secret_path(name):
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


def file_modes(root, names):
    return {name:stat.S_IMODE((root/name).lstat().st_mode)&0o777 for name in names}


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
        self.baseline_modes=file_modes(self.root,self.baseline)
        self.baseline_dirs=directories(self.root)
        self.protected = {'tests', 'features', 'specs', spec.path.relative_to(self.root).as_posix()}
        self.protected.update(p.relative_to(self.root).as_posix() for p in protected_paths(spec))
        for value in spec.raw.get('protected_paths',[]):
            captured=safe_path(self.root,value).relative_to(self.root).as_posix()
            if captured not in self.baseline and captured not in self.baseline_dirs:
                raise WorkspaceViolation('Declared verifier asset unavailable: '+value)
        for check in spec.checks:
            if check['type']=='file' and (secret_path(check['path']) or any(
                    part.casefold() in IGNORE for part in Path(check['path']).parts)):
                raise WorkspaceViolation('File check targets a private/excluded asset; use a separately reviewed verifier')
            if check['type']=='command':
                for argument in check['argv'][1:]:
                    if _test_like(argument):
                        asset=_acceptance_asset(self.root,argument)
                        self.protected.add(asset.relative_to(self.root).as_posix())
        _mkdirs(self.trusted,self.baseline_dirs)
        _mkdirs(self.builder,[n for n in self.baseline_dirs if not self.is_protected(n)])
        _copy(self.root, self.trusted, self.baseline)
        if tree(self.trusted) != self.baseline or tree(self.root) != self.baseline:
            raise WorkspaceViolation('Source changed during snapshot capture')
        _copy(self.trusted, self.builder, [n for n in self.baseline if not self.is_protected(n) and not self.secret(n)])
        self.manifest = {'schema_version': 3, 'root': str(self.root),
                         'baseline': self.baseline, 'protected': sorted(self.protected),
                         'baseline_directories':sorted(self.baseline_dirs),'baseline_modes':self.baseline_modes}
        (self.state/'manifest.json').write_text(json.dumps(self.manifest, sort_keys=True), encoding='utf-8')

    @classmethod
    def reopen(cls, state: Path, manifest_digest: str):
        obj = cls.__new__(cls)
        if not state.is_dir() or _link(state):
            raise WorkspaceViolation('Saved workspace is missing or is a link')
        obj.state = state.resolve()
        path = obj.state/'manifest.json'
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest_digest:
            raise WorkspaceViolation('Saved workspace manifest changed')
        obj.manifest = json.loads(path.read_text(encoding='utf-8'))
        if obj.manifest.get('schema_version') != 3:
            raise WorkspaceViolation('Unsupported workspace schema')
        obj.root = Path(obj.manifest['root'])
        obj.baseline, obj.protected = obj.manifest['baseline'], set(obj.manifest['protected'])
        obj.baseline_modes=obj.manifest['baseline_modes']
        obj.baseline_dirs=set(obj.manifest.get('baseline_directories',[]))
        obj.trusted, obj.builder, obj.verify_root = (obj.state/n for n in ('trusted','builder','harness'))
        obj.validate()
        return obj

    @staticmethod
    def secret(name):
        return secret_path(name)

    def is_protected(self, name):
        normalized=name.casefold()
        return any(normalized == p.casefold() or normalized.startswith(p.casefold()+'/') for p in self.protected)

    def validate(self):
        if tree(self.trusted) != self.baseline:
            raise WorkspaceViolation('Trusted snapshot changed')
        if file_modes(self.trusted,self.baseline)!=self.baseline_modes:
            raise WorkspaceViolation('Trusted snapshot permissions changed')
        if directories(self.trusted)!=self.baseline_dirs:
            raise WorkspaceViolation('Trusted snapshot directories changed')
        proposed = tree(self.builder,include_secrets=True)
        candidates=proposed.keys()|directories(self.builder,include_secrets=True)
        forbidden = [n for n in candidates if self.is_protected(n) or self.secret(n) or
                     n in proposed and any(p.casefold().startswith(n.casefold()+'/') for p in self.protected)]
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
        _mkdirs(self.verify_root,[n for n in self.baseline_dirs if self.is_protected(n)])
        _mkdirs(self.verify_root,directories(self.builder))
        _copy(self.trusted, self.verify_root, [n for n in self.baseline if self.is_protected(n)])
        _copy(self.builder, self.verify_root, proposed)
        self.expected_dirs=directories(self.verify_root)
        return self.verify_root

    def apply(self):
        proposed = self.validate()
        if tree(self.root) != self.baseline:
            raise WorkspaceViolation('Original workspace changed; proposal not applied')
        if file_modes(self.root,self.baseline)!=self.baseline_modes:
            raise WorkspaceViolation('Original file permissions changed; proposal not applied')
        if directories(self.root)!=self.baseline_dirs:
            raise WorkspaceViolation('Original directories changed; proposal not applied')
        editable = {n for n in self.baseline if not self.is_protected(n) and not self.secret(n)}
        proposed_dirs=directories(self.builder)
        obsolete=[n for n in self.baseline_dirs if n not in proposed_dirs and not self.is_protected(n) and
                  not any(p.casefold().startswith(n.casefold()+'/') for p in self.protected)]
        for name in obsolete:
            destination=self.root/name
            for directory,dirs,files in os.walk(destination,followlinks=False):
                parent=Path(directory)
                if any((parent/f).relative_to(self.root).as_posix() not in editable for f in files):
                    raise WorkspaceViolation('Directory removal would delete ignored/private files')
                if any(_link(parent/d) or (parent/d).relative_to(self.root).as_posix() not in self.baseline_dirs for d in dirs):
                    raise WorkspaceViolation('Directory removal contains ignored/private directories')
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
        for name in sorted(obsolete,key=lambda n:len(Path(n).parts),reverse=True):
            path=self.root/name
            if path.is_dir():
                path.rmdir()
        _mkdirs(self.root,proposed_dirs)
        _copy(self.builder, self.root, proposed)
        actual=tree(self.root)
        if {n:h for n,h in actual.items() if self.is_protected(n)} != {
                n:h for n,h in self.baseline.items() if self.is_protected(n)}:
            raise WorkspaceViolation('Original acceptance assets changed during application')
        applied={n:h for n,h in actual.items() if not self.is_protected(n)}
        if applied!=proposed:
            raise WorkspaceViolation('Applied implementation does not match verified proposal')
        if file_modes(self.root,proposed)!=file_modes(self.builder,proposed):
            raise WorkspaceViolation('Applied file permissions do not match verified proposal')
        expected=getattr(self,'expected_dirs',None) if self.verify_root.exists() else None
        if expected is None:
            expected=proposed_dirs|{
            n for n in self.baseline_dirs if self.is_protected(n)}
        if directories(self.root)!=expected:
            raise WorkspaceViolation('Applied directory tree does not match verified proposal')

    def evidence(self):
        return {'trusted_snapshot_sha256': hashlib.sha256(
            json.dumps(self.baseline, sort_keys=True).encode()).hexdigest(),
            'protected_paths': sorted(self.protected),
            'manifest_sha256': hashlib.sha256((self.state/'manifest.json').read_bytes()).hexdigest()}
