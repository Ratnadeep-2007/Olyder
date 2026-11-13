# Olyder v0.5 product brief ? development, not released

Primary user: a developer needing independent evidence that a CLI agent met the original specification. Secondary users: maintainers reviewing automated PRs and teams managing limited model credits.

Jobs: verify a patch; authorize a bounded repair; preserve acceptance assets; explain unresolved evidence; export reproducible reports. Success means verified outcomes per dollar and minute, subject to zero false PASS in planted-negative fixtures. Cheaper execution must never weaken mandatory coverage.

Alternatives include Aider auto-testing, OpenHands sandboxes, Harbor evaluation and LiteLLM metering. The differentiation hypothesis is a separate trust boundary combining locked acceptance, independent evidence and reserve-aware admission. This is not validated market leadership. No cloud service, model training or heavyweight dashboard is planned.

Adoption experiment: observe five developers configuring a trusted fixture in under ten minutes, then challenge five planted defects without revealing the oracle. Record setup time, false positives, false negatives and willingness to use the report in a PR. No primary-user interviews have been conducted here.

Risks: users mistake hashes for isolation, token estimates for invoices, or green declared tests for full product correctness. Detached verifier storage and clear functional/budget verdicts are release blockers. See ARCHITECTURE_V05.md for implemented versus planned scope.

| Capability | Impact | Effort | Failure mode | Mitigation | Evidence |
|---|---|---|---|---|---|
| Coverage map | High | Small | Unmapped requirement falsely passes | Review gate | Executed sentinels |
| Decimal ledger | High | Medium | Unknown counted as zero; concurrent overspend | Atomic admission and reconciliation | Executed unit tests; not runtime wired |
| Retry modes | Medium | Small | Progress falsely inferred | Per-check pass/regression deltas | Executed tests |
| Detached harness | Critical | Large | Builder modifies verifier | Separate mounts/identity | NOT implemented |
| Durable recovery | High | Medium | Duplicate charge after crash | Journal and immutable request IDs | NOT implemented |
| Gateway routing | High | Large | Proxy configured but bypassed | End-to-end capability probe | NOT implemented |
