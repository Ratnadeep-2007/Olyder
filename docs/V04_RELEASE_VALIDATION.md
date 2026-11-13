# Olyder v0.4.0 — execution isolation and structured agent telemetry

## What v0.4 introduces

| Deliverable | Mode | Verification evidence | Explicit limitation |
|---|---|---|---|
| Codex CLI adapter | `--agent codex` or `builder.provider=codex` | Fake-CLI integration, official documented JSONL schema | **No real Codex account/session used**; provider quota cannot be enforced |
| OpenCode CLI adapter | `--agent opencode` or `builder.provider=opencode` | Event parser fixtures including duplicate and missing finish events | **No real OpenCode account/session used**; final step usage may be absent |
| Docker execution policy | `--sandbox docker` | Policy tests; Linux CI has actual Docker smoke | Requires trusted Docker daemon/image and correct file permissions; bridge permits unrestricted egress |
| Process-tree timeout | Default for local commands and builder | Subprocess parent/child termination on Linux | Detached/new-session descendants and Windows service processes need further testing |
| Playwright failure traces | `--trace-browser` (opt-in) | Tracing API applied for unsuccessful checks | Live browser still unverified in restricted host; trace ZIPs can contain personal data |
| Agent token accounting | Report `agent_usage` | Codex/OpenCode event parsing and fake-agent integration | Post-hoc measurement only; unknown is not zero; provider spend not bounded mid-turn |
| Quota soft stop | `limits.max_agent_tokens` | Offline fake agent run over cap | Rejects further verification/iterations after exceeding cap; first turn may already exceed it |

## Permission and sandbox controls

- `olyder run --allow-exec --execute-builder` **fails closed** unless `--sandbox docker` or `--unsafe-host` is present.
- `--sandbox docker` runs *builder and command checks* inside Docker. The acceptance check workspace is mounted **read-only**, while the builder workspace is mounted read-write to allow implementation. Olyder still checks protected acceptance assets for tampering. Browser and HTTP tests are run by Olyder on the host and are NOT covered by the Docker command sandbox.
- Docker uses `--read-only`, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, resource limits, `--network none`, `--init`, read-only acceptance mounts and a non-root UID/GID. All options are still subject to Docker host/runtime correctness. Docker daemon socket is **not** mounted.
- Offline Docker (`--network none`) cannot access hosted model endpoints. To connect a coding agent, explicitly pass `--docker-network bridge --allow-network`, use an image with the required CLI installed, and explicitly allow required provider secrets through `builder.env`. Bridge is not an egress allowlist, so the system must not be trusted with hostile tasks and credentials without further isolation.
- `--unsafe-host` is an intentional escape hatch for a trusted developer workspace; the internal Codex sandbox is not equivalent to Docker containment. Any host command may read/write files permitted to the user and make network connections.
- Docker is **never** silently replaced with a host subprocess if the daemon or CLI is unavailable.
- PIDs are capped and Docker workloads get distinct names; on timeout Olyder attempts a forced container remove. This cleanup is best-effort, not a VM-style hard guarantee.

## Structured event accounting

Codex: `codex exec --json ...`; sum `turn.completed.usage.input_tokens + output_tokens` (input may include cached tokens). OpenCode: `opencode run --format json ...`; sum `step_finish.part.tokens` for unique part IDs. The OpenCode CLI can omit the final `step_finish` in some versions. When that happens, report `usage_complete=false` and `observed_tokens=null` if no events exist. **Never claim an accurate total from partial telemetry.** This is intended to be followed by provider-native usage reconciliation and runtime spend controls.

## Test strategy and real-world validation status

1. Existing 99 expected-vs-observed scenarios + core/regression suites remain unchanged.
2. New offline tests cover agent CLI arguments, Codex/OpenCode streamed usage and missing events, Docker fail-closed policy, environment variable allowlists, child process termination, host safety gate, and a fake Codex execution loop.
3. **Linux CI live Docker tests** execute a Python command in the real container and assert (a) no modification of a read-only mounted acceptance file, and (b) disabled external egress. These live tests should be evaluated from the actual GitHub Actions job before claiming OS enforcement validated.
4. Browser traces are opt-in because snapshots can include passwords, cookies and site content. Do not attach trace files to public issues without sanitization.
5. The host running the development tests does not have `docker`, `codex`, or `opencode` installed. No real provider balance, pricing, live browser, adversarial penetration test, arbitrary container escape, or cross-provider production interoperability is claimed.

## Official implementation references

- Codex CLI non-interactive JSONL and `turn.completed` tokens: https://learn.chatgpt.com/docs/non-interactive-mode
- OpenCode CLI JSON run events: https://opencode.ai/docs/cli/commands
- OpenCode missing final event issue: https://github.com/anomalyco/opencode/issues/53207
- Docker runtime options: https://docs.docker.com/reference/cli/docker/container/run/
- Docker seccomp defaults: https://docs.docker.com/engine/security/seccomp/
- Playwright Python tracing: https://playwright.dev/python/docs/api/class-tracing

## Priorities for later release

1. Harden real Docker images and network routing, enforce provider access through a policy proxy, consider rootless Docker or a microVM for hostile inputs.
2. Add real Codex/OpenCode accounts and run a benchmark of 10+ small tasks with provider spend reconciliation, failures, acceptance coverage, and retry efficiency.
3. Implement explicit cancellation hooks, detached process checks on Windows, and a true global timeout covering research + browser + model.
4. Add least-privilege provider token proxy, threat-model updates, PII-safe tracing, dependency-aware selective tests with final full regression.
