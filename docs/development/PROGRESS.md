# Olyder development ledger

2026-11-27. Baseline is GitHub `main` at `5f594d0` (0.5.0b2).
Development is on `feat/verification-reliability` in a separate worktree.
Security controls and redaction work are tracked in [PR #14](https://github.com/Ratnadeep-2007/Olyder/pull/14), which was open at baseline.

## Capability audit

These states apply to the cited paths and tests. A line marked VERIFIED covers the tested scope.
Review [architecture](../ARCHITECTURE_V05.md), the [threat model](../THREAT_MODEL.md),
[limitations](../KNOWN_LIMITATIONS.md), and the existing [interoperability roadmap](../INTEROPERABILITY_ROADMAP.md)
before changing their guarantees.

| Area | State and evidence | Gaps and follow-up |
| --- | --- | --- |
| A. Core | VERIFIED for CLI/SDK deterministic verdicts, mandatory coverage, blocked checks, and beta version consistency. See `tests/test_sdk.py`, `test_v05_verdict.py`, and `test_release_metadata.py`. IMPLEMENTED for versioned specs and plugin contracts in `config.py`, `contracts.py`, and `interfaces.py`. | PARTIAL for unified execution and capability diagnostics. The legacy engine has a weaker trust boundary. Built-in check dispatch and validation span `config.py` and `checks.py`. A unified registry and standardized findings contract are MISSING. |
| B. Repository context | PARTIAL. `impact.py` selects checks from explicit path mappings and falls back to the full suite. `workspace.py` applies bounded snapshots and sensitive-file exclusions. | MISSING for automatic language/framework/package-manager/lockfile/test discovery, Git diff and changed-symbol analysis, import graph, related source and test selection, AGENTS.md context indexing, automatic requirement mapping, and an invalidatable incremental index. Start with Git and local parsers. Defer Tree-sitter until a language-specific need is demonstrated. |
| C. Before development | VERIFIED for deterministic planning, spec validation, hashed requirements and protected acceptance inputs. IMPLEMENTED for optional AI planning, manual requirements and user-reviewed executable checks. | PARTIAL for semantic ambiguity, edge-case, security and missing-test suggestions. Contract revision history is MISSING. |
| D. Agents | IMPLEMENTED for CLI, skills, SDK, MCP, structured verification outputs, report retrieval, Codex/OpenCode/Claude and custom adapters, capabilities, timers, cancellation, recovery and usage observation. VERIFIED with synthetic adapters and installed OpenCode help. | BLOCKED for a live OpenCode run by its quota. Claude and Codex live managed runs and Antigravity desktop are unverified here. A managed Antigravity adapter is DEFERRED pending a documented integration and test. |
| E. Correction loop | VERIFIED by synthetic SDK tests for independent checks, feedback, targeted repair, regressions, protected inputs and final coverage. IMPLEMENTED for attempt, time and usage limits, checkpoint recovery, repeated signatures and stall handling. | PARTIAL for longer oscillation cycles and recovery after uncertain provider execution. Agent output stays separate from deterministic verdicts. |
| F. Security scanners | PARTIAL. Command and registered plugin checks can invoke reviewed tools with explicit grants. Report redaction exists. | MISSING for a scanner contract, detection of tool versions and DB freshness, normalized severity/CVE/CWE/location/fingerprints, deduplication, baselines and reviewed suppressions, offline compatibility, SARIF, and scanner-aware repair rescans. Evaluate Gitleaks, OSV-Scanner and Semgrep before wider tooling. |
| G. Review framework | VERIFIED for command-based tests/builds and API checks in local fixtures. IMPLEMENTED for optional browser scenarios and custom quality checks. | PARTIAL for requirement and regression reports. Native reporting for lint/types/complexity/duplication/architecture, performance/memory, mutation/property/flaky-test analysis, licenses, SBOM and provenance is MISSING. Integrate tools as demand becomes concrete. |
| H. Optional AI | IMPLEMENTED for advisory review of criteria and evidence, model endpoints, context/budget limits and unavailable-review handling. VERIFIED that an AI reply cannot override an observed failure. | PARTIAL for configurable review policy and privacy. Diff/context findings with locations, deduplication, focused corroboration, existing-agent review, and independent local/cloud live validation remain open. |
| I. CLI | VERIFIED for example workflows, JSON, policy modes, permission gating, release metadata, help and offline operation. IMPLEMENTED for doctor, status/report/resume/cancel, setup and budget options. | PARTIAL for automatic project inference, diagnostics of callable vendor launchers and conventional terminal presentation. Dedicated security/review commands are DEFERRED until their shared contracts exist. |
| J. Interoperability | IMPLEMENTED for MCP stdio, read-only ACP v1, Python SDK, reusable GitHub Actions and scoped HTTP. Bounded inputs, server permissions, structured errors and run IDs are covered by protocol tests. | PARTIAL for protocol conformance, versioned artifacts and independent real clients. The new MCP handshake, ACP TCK and vendor editor tests remain open. |
| K. Reporting | IMPLEMENTED for JSON, Markdown, HTML, PR summaries, coverage, expected/observed details, checker/spec hashes, run identifiers, environment, duration, usage and attempts. VERIFIED for blocked and passed outcomes in this iteration. | PARTIAL for revision identity, reproduction details, cross-run history and distinct policy statuses. Dedicated findings/SARIF, scanner versions, stable evidence IDs and graphical coverage are MISSING. |
| L. Own security | IMPLEMENTED for threat model, explicit API permissions, credential filtering, path containment, no-network Docker by default and protected acceptance inputs. Existing tests cover report privacy, local API access, symlinks, tampering and resource bounds. | PARTIAL for Windows reparse-point, untrusted instruction and network enforcement evidence. Review and adopt PR #14 through the owner workflow. A tracked SECURITY.md and dependency update configuration are MISSING. |
| M. Efficiency | IMPLEMENTED for reproducible paired fixtures, bounds, explicit incremental selection and no mandatory model cost. Existing results are described in [benchmark notes](../BENCHMARK_V05.md). | PARTIAL for measured startup/verification cost. Measure installation size, memory and context overhead before claiming improvements. Scanner/cache reuse and parallel execution are DEFERRED pending evidence. |
| N. Documentation | IMPLEMENTED for README quickstart, specs, CLI, agents, MCP, CI, examples and limits. Prior CI covers install outside the source tree. | PARTIAL for migration guidance, scanner documentation, fresh editor validation and sustained use on real pull requests. |

## Iteration 1 — OpenCode usage integrity

**Problem.** A `step_finish` with a missing part or token object could be ignored after another step reported counts. Olyder could then present the partial observation as complete and price it.

Scores use the mission weights for developer value, reliability, alignment, feasibility, maintainability, and efficiency, in that order.

| Candidate | Scores | Weighted | Decision |
| --- | --- | ---: | --- |
| Preserve incomplete OpenCode usage | 4/5/5/5/5/5 | 4.70 | Implement. Local repro and existing budget API cover the failure. |
| Add detached Git initialization for OpenCode | 3/4/4/4/3/4 | 3.60 | Defer. Antigravity raised parent Git discovery. Verify with the real CLI and test non-Git compatibility before requiring Git. |
| Accept additional finish reasons | 3/3/4/4/4/5 | 3.50 | Defer. A provider-level reason is insufficient evidence for the format emitted by supported OpenCode releases. |
| Replace CLI supervision with an ACP client | 3/3/3/2/2/3 | 2.80 | Defer. Session and permission negotiation can help future clients. The existing CLI adapter only needs conservative observation today. |

**Acceptance.** Missing or invalid core token counts in any observed finish event keep
`usage_complete` false. Preserve valid observations and the separate completion status.
Complete and duplicate events keep their existing behavior. Incomplete usage has no
price estimate. No new dependency, CLI flag, or report field.

**Change and evidence.** `src/olyder/agents.py` and `tests/test_universal_review.py`.
Four regression cases failed before the fix. One malformed-count case already passed.
After the fix, the affected suites passed 61 tests and the full Linux suite passed
388 with four opt-in checks skipped (three Docker, one Chromium). The native Linux
baseline was 383 passed and four skipped. The first WSL attempt used a Windows
linked worktree and failed the Git-history benchmark check because Linux Git could
not resolve the Windows gitdir path. A Linux-native QA checkout resolved that.

## Iteration 2 — Self-verification and release documentation

**Acceptance.** Keep the development checks in a versioned spec with explicit
requirements and protected test paths. Running the spec with execution permission
must run both check groups. Without permission both groups must remain blocked.
Both runs must use the same contract hash and make zero model calls. The current
limitations page must agree with the release metadata.

**Change and evidence.** `olyder.dev.json` and `docs/KNOWN_LIMITATIONS.md`.
The named spec passed on Linux. Its report contained 67 verification tests and
70 agent tests. With no execution grant it reported both checks blocked and
returned exit 1. Both runs used SHA-256
`448acd089b6c1c4f6efa69cb917fcbf957cb5e17ebd2b4266bf05904d21af743` and zero model calls.
Beta 2 is published on PyPI and matches the checked-in version. [PyPI Beta 2](https://pypi.org/project/Olyder/0.5.0b2/)

Run from the repository root using an environment with the source checkout and pytest available.

```sh
python -m olyder plan --spec olyder.dev.json
python -m olyder verify --spec olyder.dev.json --allow-exec --output .olyder/dogfood
```

The conventional full suite remains a separate validation step. The spec does
not exercise live provider accounts, Docker, or browsers.

## Iteration 3 — Correct MCP server version

**Problem and decision.** MCP initialization identified Olyder as `0.4.0`
even though the CLI and distribution identify themselves as `0.5.0b2`.
Read the version from the shared package constant. Preserve the existing
protocol revision, capability data, and response shape.
[MCP 2025-03-26 lifecycle](https://modelcontextprotocol.io/specification/2025-03-26/basic/lifecycle)

**Change and evidence.** `src/olyder/mcp.py` and `tests/test_release_metadata.py`.
The new test failed against the hardcoded version and passed after the fix.
The final Linux run used Python 3.14.4 and passed 390 tests, including live local
Chromium. Three Docker tests were skipped. The installed Docker client could
not reach the Docker Desktop daemon. The final development-spec report passed
with the same contract hash, two executed checks, and zero model calls.
It contains 68 verification tests and 70 agent tests. Local HTML and JSON
artifacts are under `.olyder/mission-evidence/`.
No new runtime dependencies or performance claims.

## Research and independent review

Sources checked 2026-11-27.

- OpenCode documents newline-delimited JSON for `run --format json`, explicit model
  selection and a separate ACP transport. Local OpenCode 2.3.2 confirmed `--format`,
  `--model` and `--agent` through help. High confidence in the invocation, limited
  confidence in event compatibility across releases without live captures.
  [OpenCode CLI](https://opencode.ai/docs/cli/commands/) · [OpenCode ACP](https://opencode.ai/docs/cli/acp/)
- Upstream tracked a stream that omitted a final finish event. The issue is marked
  closed with a linked patch. It does not establish behavior for the installed
  binary or make missing usage safe to estimate.
  [OpenCode issue 53207](https://github.com/anomalyco/opencode/issues/53207)
- CodeRabbit documents scoped guidance and explicit checks. That supports the
  decision to record concrete requirements separately from advisory guidance.
  The inference is about product design, independent of its internal implementation.
  [CodeRabbit review instructions](https://docs.coderabbit.ai/pr-reviews/review-instructions)
- Antigravity read the absolute worktree and reported Gravitas available. Its review
  raised Git-root discovery and alternate finish reasons as follow-up hypotheses.
  It reported no actionable findings in the accounting change, development spec,
  or MCP version change after inspecting their diffs and tests.
  Both OpenCode panes displayed DeepSeek V4.1 Flash Free and hit their daily limit.
  No OpenCode research reply or live model-backed compatibility evidence was available.

## Continuation checkpoint

1. Verify the OpenCode executable in a disposable project with Git and without Git.
   When quota is available and the provider is authorized, retain the minimum
   redacted event metadata for a complete turn, a tool-using turn, and a provider failure.
   Inspect observed finish reasons and usage before changing protocol assumptions.
2. Validate every verification entry point against a single spec containing passed,
   failed and blocked checks. Reuse that result to design a versioned finding schema.
3. After owner review of PR #14, test the development spec against the merged branch.
   Before adding a scanner integration, choose one tool and validate missing-tool,
   invalid-output and permission-gated cases using reviewed local fixtures.
