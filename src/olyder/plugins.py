"""Explicit plugin contracts. No workspace code discovery or implicit imports.

Executable agent manifests receive the same detached workspace/backend as builtins.
Python verifiers/exporters/backend factories are trusted application code; they
are never an isolation mechanism and must be registered explicitly by the caller.
"""
import json
from pathlib import Path

from .adapters import ExecutableAgent, register_agent

_verifiers = {}
_exporters = {}


def load_agent_manifest(path, *, grants):
    path=Path(path)
    if path.is_symlink() or path.stat().st_size>64000:
        raise ValueError('Plugin manifest must be a small regular file')
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data,dict) or data.get('api_version')!=1 or data.get('kind')!='agent':
        raise ValueError('Unsupported executable plugin contract')
    name=data.get('name')
    if not isinstance(name,str) or not name.replace('-','_').isidentifier():
        raise ValueError('Invalid plugin name')
    if name not in grants:
        raise PermissionError('Explicit named plugin grant required: '+name)
    permissions=data.get('permissions')
    if not isinstance(permissions,list) or not all(isinstance(p,str) for p in permissions) or set(permissions) != {'execute','write_workspace'}:
        raise ValueError('Agent plugins must declare execute and write_workspace permissions')
    protocol = data.get('protocol', 'executable')
    if protocol == 'acp-v1':
        if data.get('telemetry', 'unknown') != 'unknown':
            raise ValueError('ACP client telemetry is not independently verified')
        from .acp_external import ACPProcessAgent
        adapter = ACPProcessAgent(name, data.get('argv'))
    elif protocol == 'executable':
        adapter = ExecutableAgent(name, data.get('argv'), data.get('telemetry', 'unknown'))
    else:
        raise ValueError('Unsupported agent transport protocol')
    register_agent(adapter)
    return adapter


def register_verifier(name, verifier, *, trusted=False, api_version=1):
    if not trusted or api_version!=1 or not callable(verifier) or name in _verifiers:
        raise ValueError('Trusted compatible verifier registration required')
    _verifiers[name]=verifier


def verify_plugin(check,root,permissions):
    name=check['type'].removeprefix('plugin:')
    if name not in _verifiers:
        raise ValueError('Verifier plugin not registered')
    # The permissions are explicit input; trusted code can still bypass them.
    value=_verifiers[name](check,root,permissions)
    if not isinstance(value,tuple) or len(value)!=2 or type(value[0]) is not bool or not isinstance(value[1],str):
        raise ValueError('Verifier must return (boolean, evidence text)')
    return value


def register_exporter(name, exporter, *, trusted=False, api_version=1):
    if not trusted or api_version!=1 or not callable(exporter) or name in _exporters:
        raise ValueError('Trusted compatible exporter registration required')
    _exporters[name]=exporter


def export(name, report):
    value=_exporters[name](report)
    if not isinstance(value,str) or len(value)>2_000_000:
        raise ValueError('Exporter must return bounded text')
    return value
