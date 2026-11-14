"""Execution preparation adapters; process handling stays in execution.py."""
import os
import shutil
import stat
from pathlib import Path

from .execution import docker_argv
from .interfaces import API_VERSION, Capabilities


class HostBackend:
    name = 'host'
    api_version = API_VERSION

    def __init__(self, unsafe_authorized=False):
        self.unsafe_authorized = unsafe_authorized

    def capabilities(self):
        return Capabilities(notes='No OS containment; explicit unsafe grant for builders')

    def prepare(self, argv, root, *, writable):
        if writable and not self.unsafe_authorized:
            raise PermissionError('Host builder requires explicit unsafe authorization')
        return list(argv)


class DockerBackend:
    name = 'docker'
    api_version = API_VERSION

    def __init__(self, image='python:3.13-slim', network='none', env_names=()):
        self.image, self.network, self.env_names = image, network, env_names

    def capabilities(self):
        return Capabilities(isolated=True, notes='Requires daemon and reviewed image; bridge is unrestricted')

    def available(self):
        return shutil.which('docker') is not None  # daemon check happens on execution

    def prepare_detached(self, root, *, writable):
        """Map only SDK-owned detached trees, never the caller's original root."""
        if not hasattr(os,'getuid') or os.getuid()!=0:
            return
        from .workspace import WorkspaceViolation, _link
        paths=[root]
        for directory,dirs,files in os.walk(root,followlinks=False):
            paths.extend(Path(directory)/name for name in dirs+files)
            if len(paths)>50000:
                raise WorkspaceViolation('Detached ownership mapping exceeds resource bound')
        for path in paths:
            if _link(path) or not (path.is_dir() or stat.S_ISREG(path.lstat().st_mode)):
                raise WorkspaceViolation('Unsafe detached ownership mapping')
        for path in paths:
            from .control import current
            control=current.get()
            if control:
                control.check()
            os.chown(path,65534,65534,follow_symlinks=False)

    def prepare(self, argv, root, *, writable):
        mapped=[part.replace(str(root),'/workspace') for part in argv]
        return docker_argv(mapped, root, image=self.image, writable=writable,
                           network=self.network, env_names=self.env_names)


_backends = {'host': HostBackend, 'docker': DockerBackend}


def register_backend(name, factory):
    if not name or name in _backends or not callable(factory):
        raise ValueError('Invalid or duplicate backend')
    candidate = factory()
    from .interfaces import ExecutionBackend
    if not isinstance(candidate, ExecutionBackend) or candidate.api_version != API_VERSION:
        raise ValueError('Incompatible execution backend')
    _backends[name] = factory


def get_backend(name, **options):
    if name not in _backends:
        raise ValueError('Unknown execution backend')
    return _backends[name](**options)
