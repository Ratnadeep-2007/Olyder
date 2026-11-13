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
    sub.add_parser('doctor',help='Read-only setup and capability diagnostics')
    bench=sub.add_parser('bench',help='Run offline paired executable fixtures; never calls paid agents')
    bench.add_argument('--output',default='.olyder/benchmark.json')
    bench.add_argument('--repetitions',type=int,default=3)
    bench.add_argument('--repository',default='.',help='Olyder Git clone containing the pinned v0.4 commit')
    reconcile=sub.add_parser('reconcile',help='Record an explicit user-provided billing receipt')
    reconcile.add_argument('run_id');reconcile.add_argument('request_id')
    reconcile.add_argument('--workspace',default='.')
    reconcile.add_argument('--amount-usd',required=True)
    reconcile.add_argument('--reference',required=True)
    prune=sub.add_parser('prune',help='List expired completed run artifacts; deletion needs --apply')
    prune.add_argument('--workspace',default='.')
    prune.add_argument('--older-than-days',type=int,default=30)
    prune.add_argument('--apply',action='store_true')
    for command in ('status','resume','cancel','report'):
        c=sub.add_parser(command)
        c.add_argument('run_id')
        c.add_argument('--workspace',default='.')
        if command=='resume':
            c.add_argument('--allow-exec',action='store_true')
            c.add_argument('--recover',action='store_true',help='Reverify a checkpointed completed proposal; never replay a builder')
    api=sub.add_parser('serve',help='Optional authenticated loopback read API')
    api.add_argument('--workspace',default='.')
    api.add_argument('--port',type=int,default=8765)
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
            s.add_argument('--plugin',action='append',default=[],help='Explicit executable agent manifest')
            s.add_argument('--grant-plugin',action='append',default=[],help='Authorize a named manifest; backend permissions still apply')
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
    mcp.add_argument('--allow-exec',action='store_true')
    mcp.add_argument('--execute-builder',action='store_true',help='Expose olyder_run only with explicit server-side execution grant')
    mcp.add_argument('--unsafe-host',action='store_true')
    mcp.add_argument('--sandbox',choices=['host','docker'],default='host')
    mcp.add_argument('--docker-image',default='python:3.13-slim')
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command=='prune':
            from .state import RunStore
            result=RunStore(Path(args.workspace).resolve()/'.olyder'/'runs').prune(
                older_than_days=args.older_than_days,apply=args.apply)
            print(json.dumps(result,indent=2));return 0
        if args.command=='reconcile':
            from .state import RunStore
            state=RunStore(Path(args.workspace).resolve()/'.olyder'/'runs').reconcile(
                args.run_id,args.request_id,args.amount_usd,args.reference)
            print(json.dumps(state['accounting'],indent=2));return 0
        if args.command=='bench':
            from .benchmark import benchmark
            result=benchmark(args.output,repetitions=args.repetitions,repository=args.repository)
            print(json.dumps(result['summary'],indent=2));return 0
        if args.command=='doctor':
            from .diagnostics import doctor
            print(json.dumps(doctor(),indent=2));return 0
        if args.command=='serve':
            import os
            from .api import serve
            serve(args.workspace,token=os.getenv('OLYDER_LOCAL_API_TOKEN',''),port=args.port)
            return 0
        if args.command in ('status','cancel','resume','report'):
            from .state import RunStore
            from .sdk import resume, Permissions
            store=RunStore(Path(args.workspace).resolve()/'.olyder'/'runs')
            if args.command=='cancel':
                result=store.cancel(args.run_id)
            elif args.command=='resume':
                result=resume(args.run_id,args.workspace,permissions=Permissions(allow_exec=args.allow_exec),recover=args.recover)
            else:
                state=store.read(args.run_id)
                result=state.get('result',state) if args.command=='report' else state
            print(json.dumps(result,indent=2))
            return 1 if args.command=='resume' and result['status']!='passed' else 0
        if args.command == "mcp":
            from .mcp import serve
            from .sdk import Permissions
            if args.execute_builder and (not args.allow_exec or args.sandbox=='host' and not args.unsafe_host):
                raise ConfigError('MCP builder grant needs --allow-exec and --sandbox docker or --unsafe-host')
            return serve(Path(args.workspace).resolve(),run_permissions=Permissions(
                allow_exec=args.allow_exec,execute_builder=args.execute_builder,unsafe_host=args.unsafe_host),
                sandbox=args.sandbox,docker_image=args.docker_image)
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
        if args.command=='run':
            from .plugins import load_agent_manifest
            for manifest in args.plugin:
                load_agent_manifest(manifest,grants=set(args.grant_plugin))
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
            from .sdk import run, Permissions
            result = run(spec.path, permissions=Permissions(allow_exec=args.allow_exec,
                allow_network=args.allow_network), use_ai=args.ai,backend=args.sandbox,
                docker_image=args.docker_image,output=Path(args.output),
                trace_dir=Path(args.output)/'browser-traces' if args.trace_browser else None)
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
        print(json.dumps({"status": result["status"], "attempts": result["attempts"], "budget": result["budget"],
            "run_id":result.get('run_id'),'functional_verdict':result.get('functional_verdict'),
            'budget_verdict':result.get('budget_verdict'),'stop_reason':result.get('stop_reason'),
            'artifact_status':result.get('artifact_status'),"agent_usage": result.get("agent_usage"), "paths": result["paths"]}, indent=2))
        return 0 if result["status"] == "passed" else 1
    except (ConfigError, FileNotFoundError, ModelError, QuotaExceeded, ValueError, OSError, RuntimeError) as exc:
        print(f"Olyder error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
