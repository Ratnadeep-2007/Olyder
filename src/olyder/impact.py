"""Conservative explicit change-impact selection. No result caching.

Only intermediate iterations may select checks. The SDK always runs the full
authoritative suite before PASS. Dynamic checks are never omitted or cached.
"""
from fnmatch import fnmatchcase


def select_checks(checks, changed, failed):
    all_ids={c['id'] for c in checks}
    graph={c['id']:c.get('depends_on',[]) for c in checks}
    try:
        for identifier, dependencies in graph.items():
            if not isinstance(dependencies,list) or any(d not in all_ids for d in dependencies):
                raise ValueError
        def visit(identifier, stack):
            if identifier in stack:
                raise ValueError
            for dep in graph[identifier]:
                visit(dep,stack|{identifier})
        for identifier in graph:
            visit(identifier,set())
        static=[c for c in checks if c['type'] in ('file','command')]
        for c in static:
            patterns=c.get('paths')
            if not isinstance(patterns,list) or not patterns or any(
                    not isinstance(p,str) or not p or p.startswith(('/','\\')) or '..' in p.split('/') for p in patterns):
                raise ValueError
        if any(not any(fnmatchcase(path,p) for c in static for p in c['paths']) for path in changed):
            raise ValueError
        selected=set(failed) | {c['id'] for c in checks if c['type'] in ('http','browser')}
        selected.update(c['id'] for c in static if any(fnmatchcase(path,p) for path in changed for p in c['paths']))
        while True:
            expanded=selected|{c for c,deps in graph.items() if any(d in selected for d in deps)}
            if expanded==selected:
                break
            selected=expanded
        return (selected or all_ids),'explicit_dependency_mapping'
    except (ValueError,TypeError,KeyError,RecursionError):
        return all_ids,'full_suite_invalid_or_ambiguous_mapping'
