"""Olyder CLI: explicitly opt into code execution, network, and model use."""
from __future__ import annotations

import argparse
import importlib.resources
import json
import sys
from pathlib import Path

from .config import DEFAULT, ConfigError, load_spec
from .engine import plan, run_loop, verify_once
from .idea import evaluate_idea
from .models import ModelError
from .quota import Budget, QuotaExceeded
from .report import save_report


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="olyder", description="Independent verification and bounded AI repair loops")
    p.add_argument("--version", action="version", version="Olyder 0.4.0")
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Generate a starter acceptance specification")
    init.add_argument("directory", nargs="?", default=".")
    init.add_argument("--force", action="store_true")
    for name in ("plan", "idea", "verify", "run"):
        s = sub.add_parser(name)
        s.add_argument("--spec", default="olyder.json")
        s.add_argument("--output", default=".olyder")
        if name in ("plan", "idea", "verify", "run"):
            s.add_argument("--ai", action="store_true", help="Explicit opt-in: send limited evidence to configured model endpoint")
        if name in ("idea", "verify", "run"):
            s.add_argument("--allow-network", action="store_true", help="Allow approved research URLs")
        if name in ("verify", "run"):
            s.add_argument("--allow-exec", action="store_true", help="Allow user-configured check commands / HTTP / browser execution")
            s.add_argument("--sandbox", choices=["host", "docker"], default="host",
                           help="Docker isolates builder/check commands; host is NOT a sandbox")
            s.add_argument("--docker-image", default="python:3.13-slim",
                           help="Reviewed image with needed tools, used only with --sandbox docker")
            s.add_argument("--trace-browser", action="store_true",
                           help="Opt-in: save browser failure traces (can contain sensitive data)")
        if name == "run":
            s.add_argument("--mode", choices=["economy", "balanced", "thorough"], default=None, help="Retry policy; every mode runs all acceptance checks")
            s.add_argument("--execute-builder", action="store_true", help="Allow configured agent CLI to edit the workspace")
            s.add_argument("--max-iterations", type=int, default=None)
            s.add_argument("--agent", default=None,
                           help="Agent CLI with structured usage telemetry")
            s.add_argument("--unsafe-host", action="store_true",
                           help="Explicitly permit a builder to run on the host without OS isolation")
            s.add_argument("--docker-network", choices=["none", "bridge"], default="none",
                           help="Container egress: bridge is unrestricted (requires --allow-network)")
    skill = sub.add_parser("install-skill", help="Install agent SKILL.md into a project")
    skill.add_argument("--target", choices=["claude", "codex", "opencode", "both"], default="both")
    skill.add_argument("--project", default=".")
    skill.add_argument("--force", action="store_true", help="Overwrite existing skill file")
    mcp = sub.add_parser("mcp", help="Run read-only-by-default MCP JSON-RPC server over stdio")
    mcp.add_argument("--workspace", default=".")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "mcp":
            from .mcp import serve
            return serve(Path(args.workspace).resolve())
        if args.command == "install-skill":
            project = Path(args.project).expanduser().resolve()
            if not project.is_dir():
                raise ConfigError("Project directory does not exist")
            paths = []
            if args.target in ("claude", "both"):
                paths.append(project / ".claude" / "skills" / "olyder" / "SKILL.md")
            if args.target in ("codex", "opencode", "both"):
                paths.append(project / ".agents" / "skills" / "olyder" / "SKILL.md")
            conflicts = [str(f) for f in paths if f.exists() and not args.force]
            if conflicts:
                raise ConfigError("Existing skill; use --force to overwrite: " + ", ".join(conflicts))
            content = importlib.resources.files("olyder").joinpath("data/SKILL.md").read_text(encoding="utf-8")
            for file in paths:
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content, encoding="utf-8")
                print(f"Installed skill: {file}")
            return 0
        if args.command == "init":
            file = Path(args.directory).expanduser().resolve() / "olyder.json"
            if file.exists() and not args.force:
                print(f"Refusing to overwrite {file}; use --force", file=sys.stderr)
                return 2
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(DEFAULT, indent=2) + "\n", encoding="utf-8")
            print(f"Created {file}. Review all configured commands before running with --allow-exec.")
            return 0
        spec = load_spec(args.spec)
        budget = Budget(int(spec.raw.get("limits", {}).get("max_tokens", 30000)))
        if args.command == "plan":
            result = plan(spec, budget, use_ai=args.ai)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if args.command == "idea":
            result = evaluate_idea(spec, network_allowed=args.allow_network, use_ai=args.ai, budget=budget)
            out = Path(args.output)
            out.mkdir(parents=True, exist_ok=True)
            (out / "idea-research.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if args.command == "verify":
            result = verify_once(spec, allow_exec=args.allow_exec, use_ai=args.ai,
                allow_network=args.allow_network, budget=budget, sandbox=args.sandbox,
                docker_image=args.docker_image,
                trace_dir=Path(args.output) / "browser-traces" if args.trace_browser else None)
            result["attempts"] = 1
            result["paths"] = save_report(result, Path(args.output))
        else:
            if args.max_iterations is not None and not 1 <= args.max_iterations <= 20:
                raise ConfigError("--max-iterations must be from 1 to 20")
            if args.execute_builder and not args.allow_exec:
                raise ConfigError("--execute-builder also requires --allow-exec")
            if args.execute_builder and args.sandbox == "host" and not args.unsafe_host:
                raise ConfigError("Builder requires --sandbox docker or explicit --unsafe-host")
            if args.docker_network == "bridge" and not args.allow_network:
                raise ConfigError("Docker bridge networking requires --allow-network")
            from .sdk import run, Permissions
            result = run(spec.path, mode=args.mode,
                permissions=Permissions(allow_exec=args.allow_exec,
                    execute_builder=args.execute_builder, allow_network=args.allow_network,
                    unsafe_host=args.unsafe_host), use_ai=args.ai, output=Path(args.output),
                max_iterations=args.max_iterations, backend=args.sandbox,
                docker_image=args.docker_image, docker_network=args.docker_network,
                agent=args.agent,
                trace_dir=Path(args.output)/'browser-traces' if args.trace_browser else None)
        print(json.dumps({"status": result["status"], "attempts": result["attempts"], "budget": result["budget"], "agent_usage": result.get("agent_usage"), "paths": result["paths"]}, indent=2))
        return 0 if result["status"] == "passed" else 1
    except (ConfigError, FileNotFoundError, ModelError, QuotaExceeded, ValueError, OSError) as exc:
        print(f"Olyder error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
