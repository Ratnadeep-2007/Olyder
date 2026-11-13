# Threat model (v0.3)

## Trust boundaries

1. Project specs and workspace files may be untrusted. `--allow-exec` authorizes configured commands to run with the caller's OS identity.
2. Builder agents have potentially broad system access. **This release does not restrict their filesystem or network capabilities**. Use an external sandbox and least-privilege credentials.
3. Model APIs receive the independent verifier prompt containing acceptance criteria and test-result tails. Treat these as potentially confidential. Do not enable `--ai` unless permitted.
4. External source text and HTML content are untrusted evidence, not system instructions. The research summarizer is explicitly instructed not to follow document instructions; this is a mitigation, not a proof against prompt injection.
5. Browser/HTTP checks may exercise real services with side effects. Only use test accounts and sandbox/staging environments.

## Current mitigations

- No shell=True execution.
- Explicit execution and remote network consent flags.
- Symlink-resolved file checks restricted to selected root.
- Locked spec hash and in-memory acceptance-test fingerprints across builder/verification iterations; detect changed declared tests but **do not prevent** malicious code from modifying workspaces, imports, or the verifier itself.
- Time/iteration limits for repair cycle, fail-closed late HTTP outcomes, and subprocess timeouts.
- Report HTML escaping and bounded captured output; model API redirects are refused to protect authorization headers.
- Read-only MCP operation surface with no command or network execution.

## Known gaps

- Command and browser sandboxes; comprehensive DNS rebinding/SSRF mitigation. HTTP and research-source redirects are refused, but browser-driven navigation and subprocess networking still require runtime isolation.
- Comprehensive secret masking, classification and prevention of secret-bearing AI prompts. Common patterns are redacted from check evidence but unrecognized secrets may leak.
- Recursive process-tree kill on timeout for child processes.
- OS-level filesystem and process isolation for builders/verifiers.
- Comprehensive model-account quota reporting, external coding-agent metering, and source provenance integrity. Internal reservations have unique one-use identities.

No production-security claim should be made until these gaps have independently tested mitigations.

## Regression evidence

See [99-scenario matrix and environment constraints](QA_99.md). Local and nonlocal network opt-ins are different; explicit consent does not create an OS sandbox.
