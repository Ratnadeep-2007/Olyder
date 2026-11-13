"""Execution preparation adapters; process handling stays in execution.py."""
import shutil

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

    def prepare(self, argv, root, *, writable):
        return docker_argv(argv, root, image=self.image, writable=writable,
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
