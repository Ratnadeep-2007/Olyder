# Current threat model ? universal SDK development branch

## Assets and boundaries

Trusted: the user's locked contract, original acceptance scripts/data, selected runtime image/backend, Olyder process, explicit Python integrations and local run storage. Untrusted: builder code/output, proposed implementation, external source excerpts, model opinions and executable plugin contents. Root/admin compromise or hostile trusted Python callbacks are outside the sandbox claim.

The Docker builder receives only a writable detached implementation directory. It never receives the original test tree, locked contract file, manifest, SQLite store or verifier snapshot mount. Verification assembles original trusted assets and proposed source into a separate read-only command-check mount. Neither a source hash nor a Git worktree alone provides containment. Unsafe host mode explicitly abandons the OS boundary and is for trusted machines/tasks only.

## Controls

- Typed permissions at SDK, CLI and local MCP boundaries. MCP defaults to file-only verification; run is exposed only by server startup grants. HTTP is loopback/authenticated/read-only and refuses browser origins.
- No shell interpolation, no Docker socket, non-root container user, read-only root, dropped capabilities, no-new-privileges, bounded CPU/memory/PIDs and network none by default. Bridge opt-in is unrestricted, not an allowlist.
- Case-insensitive protected-path comparison, unavailable-oracle rejection, regular-file-only bounded snapshots, source/trusted digest checks, preserved directory topology, final full acceptance, and application integrity checks. Builder-supplied acceptance assets are rejected rather than used.
- Monetary reservations/checkpoints precede expensive calls. Unknown spend is preserved; verifier funds are independent. Repeated reservation callbacks cannot transfer funds twice. Explicit manual billing receipts retain their origin. No provider hard-cap claim is made.
- Time/iteration/progress limits, per-check movement and regressions, process-tree cleanup on cancellation/timeouts, final output-size checks, bounded live event metadata and observer error isolation. AI concerns cannot override deterministic failures or missing coverage.
- Redirect refusal on research/model requests, explicit sources and network grants, source hashes/dates and untrusted excerpts. Retrieval is an observation, not corroboration of truth. No automatic broad crawl or redirect approval occurs.
- Reports escape HTML and bound/redact evidence; raw agent logs are private temporary files and are not retained by default. Known credential files are excluded from snapshots; traces are opt-in. Local storage is sensitive, with explicit retention/deletion.

## Remaining risks and confidence limits

No comprehensive DNS-rebinding/SSRF defense, container-escape assurance, malicious image certification, detached-host-process guarantee, hard provider quota or exhaustive secret scanner is claimed. HTTP/browser checks and trusted Python plugins run with host privileges. Multi-file application is not transactional. An operator must reconcile uncertain in-flight requests rather than replay them. The legacy engine.run_loop API retains a weaker fingerprint-only boundary for compatibility. Live vendor accounts, rootless/egress proxy configurations, live browser workflows and official benchmark harnesses remain unverified. See KNOWN_LIMITATIONS.md and the per-task implementation report.

## Evidence

Original 99-scenario matrix remains unchanged. New fixtures cover detached oracle visibility/tampering, case variants, missing scripts, directory replacement, FIFO rejection, reserve concurrency/idempotence, unknown billing, cancellation, revision conflicts, resume restrictions, explicit plugins, real local HTTP authentication and full-suite regression sentinels. The hosted Docker job also executes the protected SDK with a real Python builder/container. Evidence is in docs/validation; distinguish hosted jobs from skipped local integration tests.
