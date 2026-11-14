"""Small, offline, explicit installer for Olyder agent skill definitions.

Paths follow each editor's documented project/global discovery rules. No
editor processes, model APIs, shell commands or config files are invoked.
"""
from __future__ import annotations

import importlib.resources
import os
import tempfile
from pathlib import Path

from .config import ConfigError

_LOCAL = {
    "opencode": (".opencode/skills/olyder/SKILL.md", ".agents/skills/olyder/SKILL.md"),
    "antigravity": (".agents/skills/olyder/SKILL.md",),
    "gemini": (".agents/skills/olyder/SKILL.md",),
    "codex": (".agents/skills/olyder/SKILL.md",),
    "claude": (".claude/skills/olyder/SKILL.md",),
}
_GLOBAL = {
    "opencode": (".config/opencode/skills/olyder/SKILL.md",),
    "antigravity": (".gemini/config/skills/olyder/SKILL.md",),
    "gemini": (".gemini/config/skills/olyder/SKILL.md",),
    "codex": (".agents/skills/olyder/SKILL.md",),
    "claude": (".claude/skills/olyder/SKILL.md",),
}

def skill_paths(target: str, project: str | Path = ".", *, global_scope: bool = False) -> tuple[Path, ...]:
    root = Path.home().expanduser().resolve() if global_scope else Path(project).expanduser().resolve()
    if not root.is_dir():
        raise ConfigError("Global home directory does not exist" if global_scope else
                          "Project directory does not exist")
    targets = {
        "all": ("antigravity", "opencode", "codex", "claude"),
        "both": ("opencode", "codex", "claude"),  # Legacy target name retained.
    }.get(target, (target,))
    lookup = _GLOBAL if global_scope else _LOCAL
    if not all(t in lookup for t in targets):
        raise ConfigError(f"Unsupported skill target: {target}")
    return tuple(dict.fromkeys(root / relative for t in targets for relative in lookup[t]))


def install_skill(target: str, project: str | Path = ".", *, global_scope: bool = False,
                  force: bool = False, repeatable: bool = False) -> list[tuple[str, Path]]:
    paths = skill_paths(target, project, global_scope=global_scope)
    content = importlib.resources.files("olyder").joinpath("data/SKILL.md").read_text(encoding="utf-8")
    # Preflight the entire installation before writing any skill.
    conflicts: list[str] = []
    for path in paths:
        # Do not follow a workspace-supplied symlink into an unexpected directory.
        root = Path.home().expanduser().resolve() if global_scope else Path(project).expanduser().resolve()
        chain = [path, *(p for p in path.parents if p != root and root in p.parents)]
        if any(p.is_symlink() for p in chain):
            conflicts.append(str(path) + " (symlinked path)")
            continue
        if path.exists():
            if path.is_dir():
                conflicts.append(str(path) + " (directory at skill file path)")
            elif not force and (not repeatable or path.read_text(encoding="utf-8") != content):
                conflicts.append(str(path))
    if conflicts:
        raise ConfigError("Existing skill or unsafe path; use --force only for regular existing files: " +
                          ", ".join(conflicts))
    result: list[tuple[str, Path]] = []
    for path in paths:
        if repeatable and path.is_file() and path.read_text(encoding="utf-8") == content:
            result.append(("Already installed", path))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replacement avoids partially written skill instructions.
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                            prefix=".olyder-skill-", suffix=".tmp",
                                            dir=path.parent, delete=False, newline="\n") as out:
                name = out.name
                out.write(content)
            os.replace(name, path)
        finally:
            if name is not None and Path(name).exists():
                Path(name).unlink()
        result.append(("Installed skill", path))
    return result
