"""Paired agent evaluation with separate preparation, submission and scoring."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import coordination
from .backends import get_backend
from .control import RunControl, activate
from .execution import docker_argv, managed_run
from .privacy import redact
from .sdk import Permissions
from .workspace import _link, _read_regular


_WORKER = """
import json
import sys

try:
    from app import solve
    value = json.loads(sys.argv[1])
    answer = solve(value)
    print(json.dumps({"answer": answer, "input_after": value}, allow_nan=False))
except Exception:
    print(json.dumps({"candidate_error": True}))
"""


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, data):
    with path.open("x", encoding="utf-8") as output:
        json.dump(data, output, indent=2, allow_nan=False)
        output.write("\n")


def _load_fixtures(fixtures):
    path = Path(fixtures) / "tasks-v1.json"
    content = path.read_bytes()
    data = json.loads(content)
    if data["schema_version"] != 1:
        raise ValueError("Unsupported evaluation fixture version")
    tasks = {task["id"]: task for task in data["tasks"]}
    if len(tasks) != len(data["tasks"]) or any(not re.fullmatch(r"[a-z][a-z0-9-]*", key) for key in tasks):
        raise ValueError("Invalid or duplicate evaluation task ID")
    return tasks, _sha(content)


def _public_source(task):
    cases = repr(task["public"])
    return ("from app import solve\n"
            "import json\n"
            f"for case in {cases}:\n"
            "    actual = solve(case['input'])\n"
            "    if json.dumps(actual, sort_keys=True) != json.dumps(case['expected'], sort_keys=True):\n"
            "        raise AssertionError((case['id'], case['expected'], actual))\n")


def prepare(fixtures, output, *, tasks=None, repetitions=3, mode="offline", allow_live=False,
            agent=None, model=None, token_budget=None, seconds=120, max_attempts=2,
            oracle_sha256=None, image=None):
    if mode not in ("offline", "live"):
        raise ValueError("Unsupported evaluation mode")
    if mode == "live":
        if not allow_live:
            raise ValueError("Live evaluation requires explicit authorization")
        if not agent or not model or type(token_budget) is not int or token_budget <= 0:
            raise ValueError("Live plans require the agent, pinned model version, and token budget")
        if not isinstance(oracle_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", oracle_sha256):
            raise ValueError("Live plans require the private oracle SHA-256 commitment")
        if not isinstance(image, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise ValueError("Live plans require a preloaded Docker image ID (sha256:...)")
    if type(repetitions) is not int or not 3 <= repetitions <= 20:
        raise ValueError("Repetitions must be from 3 to 20")
    if type(seconds) is not int or not 1 <= seconds <= 1800 or type(max_attempts) is not int or not 1 <= max_attempts <= 10:
        raise ValueError("Invalid evaluation time or attempt limits")
    fixtures, digest = _load_fixtures(fixtures)
    chosen = list(fixtures) if tasks is None else list(tasks)
    if not chosen or len(set(chosen)) != len(chosen) or not set(chosen) <= fixtures.keys():
        raise ValueError("Choose existing evaluation task IDs once each")
    root = Path(output).resolve()
    root.mkdir(parents=True)
    (root / "workspaces").mkdir()
    (root / "records").mkdir()
    trials = []
    for identifier in chosen:
        fixture = fixtures[identifier]
        files = {"app.py": fixture["starter"], "test_public.py": _public_source(fixture),
                 "PROMPT.md": fixture["prompt"] + "\n"}
        for repetition in range(1, repetitions + 1):
            for group in ("AB" if repetition % 2 else "BA"):
                label = f"{identifier}-{repetition}-{group}"
                workspace = root / "workspaces" / label
                workspace.mkdir()
                for name, content in files.items():
                    (workspace / name).write_bytes(content.encode())
                trials.append({"id": label, "task": identifier, "repetition": repetition, "group": group,
                               "initial_sha256": {name: _sha(content.encode()) for name, content in files.items()}})
    plan = {"schema_version": 1, "mode": mode, "fixtures_sha256": digest, "oracle_sha256": oracle_sha256,
            "repetitions": repetitions, "agent": agent, "model": model, "token_budget": token_budget,
            "seconds": seconds, "max_attempts": max_attempts, "image": image, "trials": trials}
    _write(root / "plan.json", plan)
    return plan


def _study(fixtures, output):
    tasks, digest = _load_fixtures(fixtures)
    root = Path(output).resolve()
    plan = _read(root / "plan.json")
    if plan["schema_version"] != 1 or plan["fixtures_sha256"] != digest:
        raise ValueError("Fixtures changed since study preparation")
    return tasks, root, plan


def _trial(plan, label):
    for trial in plan["trials"]:
        if trial["id"] == label:
            return trial
    raise ValueError("Unknown evaluation trial")


def _source(root, trial):
    directory = root / "workspaces" / trial["id"]
    source = directory / "app.py"
    if _link(directory.parent) or _link(directory) or _link(source):
        raise ValueError("Submission must be a regular file in the trial workspace")
    return _read_regular(source, limit=128_000)


def _example_solution(task):
    return f"def solve(value):\n    return {task['public'][0]['expected']!r}\n"


def _check_host_source(task, source, image):
    scripted = (task["starter"], task["repair"], _example_solution(task))
    if image is None and all(source != text.encode() for text in scripted):
        raise ValueError("Host execution is restricted to the bundled scripted fixtures")


def _execute(root, args, *, image=None):
    argv = [("python" if image else sys.executable), "-E", *args]
    if image:
        get_backend('docker', image=image).prepare_detached(root, writable=False)
        argv = docker_argv(argv, root, image=image, writable=False)
        argv.insert(2, "--pull=never")
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8", errors="replace") as output:
        try:
            with activate(RunControl(time.monotonic() + 15, max_output_bytes=64_000)):
                status = managed_run(argv, cwd=root, stdout=output, timeout=15)
            if status.timed_out:
                return None, "Check timed out"
            output.seek(0)
            return status.returncode, output.read(64_000)
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
            return None, type(exc).__name__


def _public(task, trial, source, *, image):
    if source is None:
        return {"status": "not_submitted", "seconds": 0, "approved": False}
    _check_host_source(task, source, image)
    with tempfile.TemporaryDirectory(prefix="olyder-eval-public-") as directory:
        root = Path(directory)
        (root / "app.py").write_bytes(source)
        (root / "test_public.py").write_bytes(_public_source(task).encode())
        start = time.perf_counter()
        if trial["group"] == "A":
            code, detail = _execute(root, ["test_public.py"], image=image)
            unavailable = code is None or (image and code in (125, 126, 127))
            status = "passed" if code == 0 else "blocked" if unavailable else "failed"
            return {"status": status, "seconds": time.perf_counter() - start, "details": redact(detail)[:3000]}
        spec = root / "olyder.json"
        _write(spec, {"goal": task["prompt"], "checks": [{"id": "public", "type": "command",
               "argv": [("python" if image else sys.executable), "-E", "test_public.py"], "timeout": 15}],
               "limits": {"max_seconds": 30}})
        key = secrets.token_urlsafe(32)
        opened = coordination.open_task(spec, agent_id="trial-builder", controller_key=key,
                                         backend="docker" if image else "host",
                                         docker_image=image or "python:3.13-slim")
        identifier, revision = opened["run_id"], opened["proposal_revision"]
        coordination.submit_task(root, identifier, revision, agent_id="trial-builder")
        verified = coordination.verify_task(root, identifier, controller_key=key,
                                            permissions=Permissions(allow_exec=True))
        approved = verified["phase"] == "verified"
        if approved:
            coordination.complete_task(root, identifier, revision, controller_key=key)
            coordination.task_gate(root, identifier, revision)
        result = verified["result"]
        return {"status": result["status"], "seconds": time.perf_counter() - start, "approved": approved,
                "checks": result.get("checks", []), "spec_sha256": result["spec_sha256"]}


def _isolation(plan, image):
    if plan["mode"] != "live":
        return
    if image is None or image != plan["image"]:
        raise ValueError("Live evaluation requires the preregistered isolated Docker image")
    try:
        subprocess.run(["docker", "image", "inspect", image], check=True, timeout=8,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("The planned Docker image is unavailable locally") from exc


def public_check(fixtures, output, label, *, image=None):
    tasks, root, plan = _study(fixtures, output)
    _isolation(plan, image)
    trial = _trial(plan, label)
    return _public(tasks[trial["task"]], trial, _source(root, trial), image=image)


def record(fixtures, output, label, receipt, *, image=None, public_attempts=()):
    tasks, root, plan = _study(fixtures, output)
    _isolation(plan, image)
    trial = _trial(plan, label)
    if type(receipt.get("claimed_completion")) is not bool:
        raise ValueError("Record a boolean claimed_completion")
    for key in ("repair_attempts", "human_interventions", "observed_tokens"):
        value = receipt.get(key)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"Invalid metric: {key}")
    for key in ("development_seconds", "actual_usd", "peak_rss_kib"):
        value = receipt.get(key)
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError(f"Invalid metric: {key}")
    if plan["mode"] == "live" and (
            receipt.get("agent") != plan["agent"] or receipt.get("model") != plan["model"]
            or receipt.get("development_seconds") is None or receipt.get("repair_attempts") is None):
        raise ValueError("Live receipts require the planned agent/model, elapsed time, and repair attempts")
    no_submission = receipt.get("no_submission", False)
    if type(no_submission) is not bool or (no_submission and receipt["claimed_completion"]):
        raise ValueError("Invalid missing-submission receipt")
    source = None if no_submission else _source(root, trial)
    public = _public(tasks[trial["task"]], trial, source, image=image)
    _write(root / "records" / f"{label}.json", {
        "trial": label, "source_sha256": _sha(source) if source is not None else None, "public": public,
        "development_public_checks": list(public_attempts),
        "receipt": {k: receipt.get(k) for k in ("claimed_completion", "repair_attempts",
                    "human_interventions", "observed_tokens", "development_seconds", "actual_usd", "peak_rss_kib")},
    })


def _hidden(source, cases, *, image):
    results = []
    with tempfile.TemporaryDirectory(prefix="olyder-eval-score-") as directory:
        root = Path(directory)
        for case in cases:
            # Only the input crosses the process boundary. Keep targets with the scorer.
            (root / "app.py").write_bytes(source)
            code, detail = _execute(root, ["-c", _WORKER, json.dumps(case["input"])], image=image)
            if code is None or (image and code in (125, 126, 127)):
                status = "error"
            else:
                try:
                    actual = json.loads(detail.splitlines()[-1]) if code == 0 else {}
                    passed = json.dumps(actual["answer"], sort_keys=True) == json.dumps(case["expected"], sort_keys=True)
                    if passed and case.get("preserve_input"):
                        passed = actual["input_after"] == case["input"]
                except (ValueError, IndexError, KeyError, TypeError):
                    passed = False
                status = "pass" if passed else "fail"
            results.append({"id": case["id"], "category": case["category"], "status": status})
    return results


def score(fixtures, output, oracle, *, image=None):
    tasks, root, plan = _study(fixtures, output)
    oracle = Path(oracle).resolve()
    _isolation(plan, image)
    if oracle.is_relative_to(root):
        raise ValueError("Keep the scoring oracle outside the study workspace")
    if plan["mode"] == "live" and oracle == (Path(fixtures) / "offline-oracles-v1.json").resolve():
        raise ValueError("Live evaluation requires a private holdout bundle")
    records = []
    for trial in plan["trials"]:
        raw = _read(root / "records" / f"{trial['id']}.json")
        source = _source(root, trial) if raw["source_sha256"] is not None else None
        if raw["trial"] != trial["id"] or (source is not None and raw["source_sha256"] != _sha(source)):
            raise ValueError(f"Submission changed after recording: {trial['id']}")
        records.append((trial, raw, source))
    content = oracle.read_bytes()
    digest = _sha(content)
    if plan["oracle_sha256"] and digest != plan["oracle_sha256"]:
        raise ValueError("Held-out oracle differs from the preregistered digest")
    hidden = json.loads(content)
    if hidden["schema_version"] != 1:
        raise ValueError("Unsupported evaluation oracle version")
    rows = []
    for trial, raw, source in records:
        cases = hidden["tasks"][trial["task"]]
        if not cases:
            raise ValueError("Every task needs a nonempty holdout")
        public_inputs = [case["input"] for case in tasks[trial["task"]]["public"]]
        if any(case["input"] in public_inputs for case in cases):
            raise ValueError("Holdout includes a public input")
        started = time.perf_counter()
        if source is None:
            checks = [{"id": case["id"], "category": case["category"], "status": "not_run"} for case in cases]
        else:
            _check_host_source(tasks[trial["task"]], source, image)
            checks = _hidden(source, cases, image=image)
        failed = [check for check in checks if check["status"] != "pass"]
        receipt = raw["receipt"]
        budget_exceeded = (receipt["development_seconds"] is not None and receipt["development_seconds"] > plan["seconds"]
                           or receipt["repair_attempts"] is not None and 1 + receipt["repair_attempts"] > plan["max_attempts"]
                           or plan["token_budget"] is not None and receipt["observed_tokens"] is not None
                           and receipt["observed_tokens"] > plan["token_budget"])
        approved = raw["public"].get("approved", False) if trial["group"] == "B" else receipt["claimed_completion"]
        rows.append({**trial, **receipt, "source_sha256": raw["source_sha256"], "public": raw["public"],
                     "development_public_checks": raw["development_public_checks"],
                     "hidden": checks, "hidden_passed": len(checks) - len(failed), "hidden_total": len(checks),
                     "completed": not failed and not budget_exceeded, "budget_exceeded": budget_exceeded,
                     "false_completion": any(check['status'] == 'fail' for check in failed) and approved,
                     "undetected_defects": sum(check["status"] == "fail" for check in failed) if raw["public"]["status"] == "passed" else 0,
                     "hidden_errors": sum(check["status"] == "error" for check in failed),
                     "regressions": sum(check["category"] == "regression" and check["status"] == "fail" for check in failed),
                     "security_failures": sum(check["category"] == "access_control" and check["status"] == "fail" for check in failed),
                     "scoring_seconds": time.perf_counter() - started})
    groups = {}
    for group in ("A", "B"):
        selected = [row for row in rows if row["group"] == group]
        regression_cases = sum(check["category"] == "regression" for row in selected for check in row["hidden"])
        groups[group] = {"trials": len(selected),
                         "completion_rate": sum(row["completed"] for row in selected) / len(selected),
                         "hidden_pass_rate": sum(row["hidden_passed"] for row in selected)
                         / sum(row["hidden_total"] for row in selected),
                         "false_completions": sum(row["false_completion"] for row in selected),
                         "undetected_defects": sum(row["undetected_defects"] for row in selected),
                         "security_failures": sum(row["security_failures"] for row in selected),
                         "regressions": sum(row["regressions"] for row in selected),
                         "regression_rate": sum(row["regressions"] for row in selected) / regression_cases if regression_cases else None,
                         "evaluator_errors": sum(row["hidden_errors"] for row in selected),
                         "budget_violations": sum(row["budget_exceeded"] for row in selected),
                         "missing_submissions": sum(row["source_sha256"] is None for row in selected)}
    pairs = {(row["task"], row["repetition"], row["group"]): row for row in rows}
    overhead = [{"task": row["task"], "repetition": row["repetition"],
                 "public_check_delta_seconds": row["public"]["seconds"]
                 - pairs[row["task"], row["repetition"], "A"]["public"]["seconds"]}
                for row in rows if row["group"] == "B"]
    rss = None
    if sys.platform.startswith("linux"):
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report = {"schema_version": 1, "runner_peak_rss_kib": rss, "kind": "offline_scripted" if plan["mode"] == "offline" else "live_recorded",
              "study": plan, "oracle_sha256": digest, "python": platform.python_version(),
              "platform": platform.platform(), "scorer_image": image,
              "rows": rows, "groups": groups, "paired_overhead": overhead}
    _write(root / "report.json", report)
    return report


def offline(fixtures, output, *, tasks=None, repetitions=3):
    plan = prepare(fixtures, output, tasks=tasks, repetitions=repetitions)
    definitions, root, _ = _study(fixtures, output)
    for trial in plan["trials"]:
        task = definitions[trial["task"]]
        app = root / "workspaces" / trial["id"] / "app.py"
        strategy = (trial["repetition"] - 1) % 3
        source = _example_solution(task) if strategy == 0 else task["repair"]
        attempts = []
        start = time.perf_counter()
        if strategy == 2:
            attempts.append(public_check(fixtures, root, trial["id"]))
        app.write_bytes(source.encode())
        attempts.append(public_check(fixtures, root, trial["id"]))
        record(fixtures, root, trial["id"], {
            "claimed_completion": attempts[-1]["status"] == "passed",
            "repair_attempts": int(strategy == 2),
            "human_interventions": 0, "development_seconds": time.perf_counter() - start,
        }, public_attempts=attempts)
    return score(fixtures, root, Path(fixtures) / "offline-oracles-v1.json")


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--fixtures", default="evaluations")
    sub = cli.add_subparsers(dest="operation", required=True)
    for name in ("offline", "prepare-live", "public-check", "record", "score"):
        command = sub.add_parser(name)
        command.add_argument("output")
        if name in ("offline", "prepare-live"):
            command.add_argument("--task", action="append")
            command.add_argument("--repetitions", type=int, default=3)
        else:
            command.add_argument("--image")
        if name in ("public-check", "record"):
            command.add_argument("trial")
        if name == "prepare-live":
            command.add_argument("--allow-live", action="store_true")
            command.add_argument("--agent", required=True)
            command.add_argument("--model", required=True)
            command.add_argument("--token-budget", type=int, required=True)
            command.add_argument("--oracle-sha256", required=True)
            command.add_argument("--image", required=True)
            command.add_argument("--seconds", type=int, default=120)
            command.add_argument("--max-attempts", type=int, default=2)
        elif name == "record":
            command.add_argument("receipt", type=Path)
        elif name == "score":
            command.add_argument("oracle")
    args = cli.parse_args(argv)
    if args.operation == "offline":
        result = offline(args.fixtures, args.output, tasks=args.task, repetitions=args.repetitions)["groups"]
    elif args.operation == "prepare-live":
        result = prepare(args.fixtures, args.output, tasks=args.task, repetitions=args.repetitions, mode="live",
                         allow_live=args.allow_live, agent=args.agent, model=args.model,
                         token_budget=args.token_budget, oracle_sha256=args.oracle_sha256,
                         seconds=args.seconds, max_attempts=args.max_attempts, image=args.image)
    elif args.operation == "public-check":
        result = public_check(args.fixtures, args.output, args.trial, image=args.image)
    elif args.operation == "record":
        record(args.fixtures, args.output, args.trial, _read(args.receipt), image=args.image)
        result = {"recorded": args.trial}
    else:
        result = score(args.fixtures, args.output, args.oracle, image=args.image)["groups"]
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
