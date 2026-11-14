"""Versioned acceptance requirement validation and explicit evidence mapping.

Version 1 (or absent): each declared check is a mandatory requirement.
Version 2: explicit requirements are supported; an unmapped mandatory item
remains unresolved. Manual review is deliberately not self-authorized in JSON.
"""
from .config import ConfigError


def validate_requirements(raw: dict, check_ids: set[str]) -> None:
    version = raw.get('schema_version', 1)
    if type(version) is not int or version not in (1, 2):
        raise ConfigError('Unsupported schema_version; supported: 1, 2')
    if 'requirements' not in raw:
        return
    requirements = raw['requirements']
    if version != 2 or not isinstance(requirements, list) or not requirements:
        raise ConfigError('Explicit requirements require schema_version 2 and a nonempty list')
    seen = set()
    for r in requirements:
        if not isinstance(r, dict):
            raise ConfigError('Requirement must be an object')
        identifier = r.get('id')
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
            raise ConfigError('Requirement ID missing or duplicate')
        seen.add(identifier)
        if not isinstance(r.get('text'), str) or not r['text'].strip():
            raise ConfigError('Requirement text must be nonempty')
        if type(r.get('mandatory', True)) is not bool:
            raise ConfigError('Requirement mandatory must be boolean')
        checks = r.get('acceptance_check_ids', [])
        if not isinstance(checks, list) or any(not isinstance(c, str) for c in checks):
            raise ConfigError('acceptance_check_ids must be strings')
        if len(set(checks)) != len(checks) or not set(checks) <= check_ids:
            raise ConfigError('Requirement references duplicate or unknown checks')


def coverage_map(spec, results: list[dict]) -> dict:
    requirements = spec.raw.get('requirements', [
        {'id': c['id'], 'text': c['id'], 'mandatory': True,
         'acceptance_check_ids': [c['id']]} for c in spec.checks])
    by_id = {r['id']: r for r in results}
    return {r['id']: {
        'mandatory': r.get('mandatory', True),
        'check_ids': r.get('acceptance_check_ids', []),
        'result_ids': [c for c in r.get('acceptance_check_ids', []) if c in by_id],
        'evidence_refs': [f'checks/{c}' for c in r.get('acceptance_check_ids', []) if c in by_id],
        'satisfied': bool(r.get('acceptance_check_ids')) and all(
            by_id.get(c, {}).get('status') == 'pass' for c in r.get('acceptance_check_ids', []))
    } for r in requirements}
