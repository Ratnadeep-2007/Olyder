# Installation and integration guide

Python 3.11+; no mandatory runtime dependencies. From a clone:

```text
python -m pip install -e .
olyder doctor
olyder verify --spec examples/demo-app/olyder.json --allow-exec
```

The demo runs actual pricing unit tests without a model. Generated example evidence is in docs/examples/universal/. Review executable checks before granting --allow-exec.

## Configuration

`olyder init` creates a starter spec. Preserve goal/check IDs and review builder.argv before enabling mutation. Existing schema-1 specs remain readable; schema 2 adds explicit requirements:

```json
{
  "schema_version": 2,
  "goal": "A greeting function returns the agreed text",
  "requirements": [{"id":"greeting","text":"Return Hello Olyder","mandatory":true,"acceptance_check_ids":["oracle"]}],
  "checks": [{"id":"oracle","type":"command","argv":["python","-c","from hello import greet; assert greet() == 'Hello Olyder'"],"paths":["hello.py"]}],
  "builder": {"provider":"hello-agent"},
  "policy": {"mode":"balanced"},
  "limits": {"max_iterations":3,"max_seconds":120,"max_tokens":30000}
}
```

The hello-agent manifest is a deterministic third-party-style example, not an LLM. Save this spec in a disposable project. Use an absolute manifest path from the Olyder clone:

```text
olyder run --spec olyder.json --plugin /path/to/Olyder/examples/plugins/hello-agent.json --grant-plugin hello-agent --allow-exec --execute-builder --unsafe-host
```

The plugin writes hello.py; the independent Python assertion checks the actual function. This exact workflow is exercised by test_third_party_style_plugin_executes_real_check. Host mode is only for trusted code. For isolation use --sandbox docker --docker-image YOUR_REVIEWED_IMAGE, containing Python/agent/dependencies. Docker never falls back to host. Remote model connectivity needs --docker-network bridge --allow-network; bridge is unrestricted egress. Forward only explicitly reviewed environment variable names in builder.env. Root callers never become root container builders automatically; UID/mount permissions may require a reviewed backend configuration.

Builtins: builder.provider codex, opencode or claude; builder.model is optional. Custom executable arrays remain supported with usage unavailable. Claude flags are documentation/conformance checked only, not live-account verified. Windows script wrappers may need an explicit native argv (for example Node plus the installed CLI entry point); doctor availability is not execution certification.

## Python SDK and trusted integrations

```python
from olyder.sdk import Permissions, run, resume
result = run('olyder.json', permissions=Permissions(allow_exec=True))
assert result['status'] in {'passed','failed','blocked','needs_review','budget_exhausted','cancelled'}
print(result['run_id'], result['functional_verdict'], result['budget_verdict'])
```

Mutation requires execute_builder=True plus an isolated backend or unsafe_host=True. Event callbacks receive metadata through sink=callback. Register trusted AgentAdapter objects with register_agent, trusted execution factories with register_backend, trusted verifier functions with register_verifier(..., trusted=True), exporters with register_exporter(..., trusted=True), and model providers through model_provider=. These Python callbacks have the caller's privileges; they are not untrusted-plugin sandboxes. SDK exporters= selects explicitly registered text exporters. Executable agent manifests require API version 1, a named grant and declared permissions. Unknown formats/versions and automatic workspace imports are rejected.

## Dollars, tokens and review

Optional budget fields: max_cost_usd, builder_upper_bound_usd, verifier_reserve_usd, planner_upper_bound_usd, research_upper_bound_usd, strict. Use decimal strings. These are user-chosen admission allowances, not provider prices. A requested critic requires a positive protected reserve when a dollar cap is configured. It runs after the full deterministic suite succeeds. Missing bounds deny admission. Unknown billing is never zero. strict stops all subsequent paid reservations after unknown spend, including critic calls; required review stays unresolved. A provider can exceed a reviewed allowance mid-turn. Limits apply per job/run, not across concurrent runs or an entire provider account.

Optional budget.pricing accepts a schema-version-1 PricingSnapshot: provider, model, date (ISO date), input_per_million_usd, output_per_million_usd and optional cached_per_million_usd. Supply actual rates yourself; no model prices are fabricated. Cache counts are subsets of normalized input; unknown cache/usage data prevents a precise estimate. Claude total_cost_usd is client-estimated, not an invoice.

`olyder reconcile RUN_ID REQUEST_ID --workspace PROJECT --amount-usd DECIMAL --reference RECEIPT` records an explicit user-provided billing receipt after execution stops. It is labelled user_reconciled_invoice, not provider-queried evidence. `--ai` sends limited goal/check/evidence content only with explicit consent. Plan/idea model calls have their own durable run IDs, planner/research allowances and usage records. No raw private source is transmitted by default. An unavailable requested review stays unresolved.

## State, recovery, cancellation and retention

```text
olyder status RUN_ID --workspace PROJECT
olyder cancel RUN_ID --workspace PROJECT
olyder resume RUN_ID --workspace PROJECT --allow-exec
olyder report RUN_ID --workspace PROJECT
olyder prune --workspace PROJECT --older-than-days 30
```

The default prune command lists candidates. --apply explicitly deletes completed owned run snapshots and their database rows; it retains uncertain in-flight runs. Exported reports/traces outside a run folder must be removed separately. Store data is private locally by default; apply suitable owner-only Windows ACLs on shared machines. Known credential files are not snapshotted, but source files can still contain secrets.

Resume never reruns a builder or paid critic. --recover is an explicit operator assertion that old work has stopped and permits rechecking an interrupted deterministic verifier. In-flight builder/critic requests remain blocked until externally reconciled; start a new authorized run rather than guessing whether a provider billed. A resumed PASS applies to the checkpointed proposal, not arbitrary newer original-workspace edits. Resume does not automatically apply the proposal. Earlier experimental workspace manifests are incompatible; start fresh verification for those runs.

## CLI, IDEs, MCP and HTTP

CLI commands emit JSON. Use the same commands in terminal workflows, VS Code/Cursor/JetBrains terminal tasks, CI jobs or external process launchers; no dedicated IDE extension is required. An MCP-compatible client can launch `olyder mcp --workspace ABSOLUTE_PROJECT_PATH`. Default tools are only olyder_plan and file-only olyder_verify. The client cannot supply commands, paths or permission flags. To expose olyder_run, the server owner must explicitly start MCP with --allow-exec --execute-builder and --sandbox docker (or --unsafe-host for trusted local work). This is local stdio MCP; remote MCP authorization is not implemented.

Optional read HTTP API: set OLYDER_LOCAL_API_TOKEN to a random secret of at least 24 characters, then `olyder serve --workspace PROJECT --port 8765`. It binds 127.0.0.1 only. Send Authorization: Bearer TOKEN to GET /v1/doctor, /v1/plan or /v1/verify. Browser Origin requests and unauthenticated access are denied. There is no HTTP mutation/paid-agent endpoint. A real loopback HTTP test covers authentication and verification.

## Reports and compatibility

JSON/Markdown/HTML report goal, spec digest, run ID, requirement coverage, full-suite status, trusted manifest, selected checks, progress, resource duration, observations, uncertainty, application status and exact stop reason. Reports and traces may contain sensitive data. Do not publish them without review. HTML escapes all metadata and test output and uses no gradients.

The protected CLI run/verify path changes where checks execute: absolute interpreter argv[0] is allowed, test-asset arguments should be relative, unittest module names resolve to trusted files, dependency/VCS/private trees are omitted, and missing oracle assets block. Package dependencies in a reviewed runtime image or use an explicitly reviewed native interpreter. Legacy engine.run_loop remains available but has only its earlier shared-workspace integrity detector. New callers should use olyder.sdk. No cache is used; every final PASS needs the complete fresh mandatory suite.
