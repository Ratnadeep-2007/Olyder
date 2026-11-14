"""Olyder CLI: explicitly opt into code execution, network, and model use."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import DEFAULT, ConfigError, load_spec
from .engine import plan
from .models import ModelError
from .privacy import redact_values
from .quota import Budget, QuotaExceeded


def _json(value, *args, **kwargs):
    return json.dumps(redact_values(value), *args, **kwargs)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="olyder", description="Independent verification and bounded AI repair loops")
    p.add_argument("--version", action="version", version=f"Olyder {__version__}")
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
    skill = sub.add_parser("install-skill", help="Install Olyder skill locally or globally")
    skill.add_argument("--target", choices=["claude", "codex", "opencode", "antigravity", "gemini", "both", "all"], default="both")
    skill.add_argument("--project", default=".")
    skill.add_argument("--global", "-g", dest="global_scope", action="store_true", help="Make the skill available in all projects")
    skill.add_argument("--force", action="store_true", help="Overwrite a customized existing skill")
    setup = sub.add_parser("setup", help="Set up Olyder skills for one or every coding editor")
    setup.add_argument("editor", nargs="?", choices=["antigravity", "gemini", "opencode", "codex", "claude", "all"], default="all")
    setup.add_argument("--project", default=".")
    setup.add_argument("--global", "-g", dest="global_scope", action="store_true", help="Install once for all your projects")
    setup.add_argument("--force", action="store_true", help="Overwrite a customized existing skill")
    acp = sub.add_parser("acp", help="Run optional read-only ACP v1 editor bridge over stdio")
    acp.add_argument("--workspace", default=".")
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
            print(_json(result,indent=2));return 0
        if args.command=='reconcile':
            from .state import RunStore
            state=RunStore(Path(args.workspace).resolve()/'.olyder'/'runs').reconcile(
                args.run_id,args.request_id,args.amount_usd,args.reference)
            print(_json(state['accounting'],indent=2));return 0
        if args.command=='bench':
            from .benchmark import benchmark
            result=benchmark(args.output,repetitions=args.repetitions,repository=args.repository)
            print(_json(result['summary'],indent=2));return 0
        if args.command=='doctor':
            from .diagnostics import doctor
            print(_json(doctor(),indent=2));return 0
        if args.command=='serve':
            import os

            from .api import serve
            serve(args.workspace,token=os.getenv('OLYDER_LOCAL_API_TOKEN',''),port=args.port)
            return 0
        if args.command in ('status','cancel','resume','report'):
            from .sdk import Permissions, resume
            from .state import RunStore
            store=RunStore(Path(args.workspace).resolve()/'.olyder'/'runs')
            if args.command=='cancel':
                result=store.cancel(args.run_id)
            elif args.command=='resume':
                result=resume(args.run_id,args.workspace,permissions=Permissions(allow_exec=args.allow_exec),recover=args.recover)
            else:
                state=store.read(args.run_id)
                result=state.get('result',state) if args.command=='report' else state
            print(_json(result,indent=2))
            return 1 if args.command=='resume' and result['status']!='passed' else 0
        if args.command == "acp":
            try:
                from .acp_bridge import serve as serve_acp
            except ImportError as exc:
                raise ConfigError("ACP bridge requires: pip install 'olyder-agent[acp]'") from exc
            return serve_acp(Path(args.workspace).resolve())
        if args.command == "mcp":
            from .mcp import serve
            from .sdk import Permissions
            if args.execute_builder and (not args.allow_exec or args.sandbox=='host' and not args.unsafe_host):
                raise ConfigError('MCP builder grant needs --allow-exec and --sandbox docker or --unsafe-host')
            return serve(Path(args.workspace).resolve(),run_permissions=Permissions(
                allow_exec=args.allow_exec,execute_builder=args.execute_builder,unsafe_host=args.unsafe_host),
                sandbox=args.sandbox,docker_image=args.docker_image)
        if args.command in ("install-skill", "setup"):
            from .skill_install import install_skill
            target = args.editor if args.command == "setup" else args.target
            installs = install_skill(target, args.project, global_scope=args.global_scope,
                                     force=args.force, repeatable=args.command == "setup")
            for status, file in installs:
                print(f"{status}: {file}")
            if args.command == "setup":
                scope = "every project (global)" if args.global_scope else "this project"
                print(f"Ready for {target} in {scope}. Restart or reload your editor's skills.")
                print("No AI model was called; no project code or acceptance checks were executed.")
            return 0
        if args.command == "init":
            file = Path(args.directory).expanduser().resolve() / "olyder.json"
            if file.exists() and not args.force:
                print(f"Refusing to overwrite {file}; use --force", file=sys.stderr)
                return 2
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(_json(DEFAULT, indent=2) + "\n", encoding="utf-8")
            print(f"Created {file}. Review all configured commands before running with --allow-exec.")
            return 0
        if args.command=='run':
            from .plugins import load_agent_manifest
            for manifest in args.plugin:
                load_agent_manifest(manifest,grants=set(args.grant_plugin))
        spec = load_spec(args.spec)
        budget = Budget(int(spec.raw.get("limits", {}).get("max_tokens", 30000)))
        if args.command == "plan":
            if args.ai:
                from .analysis import run_analysis
                result=run_analysis('plan',spec.path,use_ai=True)
            else:
                result = plan(spec, budget, use_ai=False)
            print(_json(result, indent=2, ensure_ascii=False))
            return 1 if result.get('status') in ('blocked','budget_exhausted','cancelled') else 0
        if args.command == "idea":
            from .analysis import run_analysis
            result = run_analysis('idea',spec.path,allow_network=args.allow_network,use_ai=args.ai)
            out = Path(args.output)
            out.mkdir(parents=True, exist_ok=True)
            (out / "idea-research.json").write_text(_json(result, indent=2, ensure_ascii=False), encoding="utf-8")
            print(_json(result, indent=2, ensure_ascii=False))
            return 1 if result.get('status') in ('blocked','budget_exhausted','cancelled') else 0
        if args.command == "verify":
            from .sdk import Permissions, run
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
            from .sdk import Permissions, run
            result = run(spec.path, mode=args.mode,
                permissions=Permissions(allow_exec=args.allow_exec,
                    execute_builder=args.execute_builder, allow_network=args.allow_network,
                    unsafe_host=args.unsafe_host), use_ai=args.ai, output=Path(args.output),
                max_iterations=args.max_iterations, backend=args.sandbox,
                docker_image=args.docker_image, docker_network=args.docker_network,
                agent=args.agent,
                trace_dir=Path(args.output)/'browser-traces' if args.trace_browser else None)
        print(_json({"status": result["status"], "attempts": result["attempts"], "budget": result["budget"],
            "run_id":result.get('run_id'),'functional_verdict':result.get('functional_verdict'),
            'budget_verdict':result.get('budget_verdict'),'stop_reason':result.get('stop_reason'),
            'artifact_status':result.get('artifact_status'),"agent_usage": result.get("agent_usage"), "paths": result["paths"]}, indent=2))
        return 0 if result["status"] == "passed" else 1
    except (ConfigError, FileNotFoundError, ModelError, QuotaExceeded, ValueError, OSError, RuntimeError) as exc:
        print(f"Olyder error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
