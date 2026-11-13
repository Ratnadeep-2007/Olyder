# v0.5 architecture and implementation record

Status: incomplete foundation branch. Version remains 0.4.0. Main is unchanged.

Policy record: planning=deep; context_depth=dependency; verification_depth=full; delegation=none. Reasons: security boundaries, shared execution engine, backward-compatible configuration.

Chosen approach: add small stdlib modules to the existing engine. A rewrite would discard tested adapters; a mandatory gateway/database would impair local adoption. The acceptance contract remains authoritative across modes. No mandatory runtime dependency was added.

Implemented: contracts.py validates schema versions 1/2 and requirement IDs/check references; coverage_map maps requirements to checks/results/evidence references. Version 1 or absent maps each check to a mandatory requirement. Version 2 may declare requirements explicitly. Empty mandatory coverage requires review. Manual verification is not self-authorized by spec fields.

verify_once cannot accept a subset as full acceptance, checks locked spec bytes before/after verification, records requested critic availability, and never lets the critic override a deterministic failure. Reports expose coverage and selected check sets in JSON/Markdown/HTML. Full suites run on every loop attempt; no incremental cache or efficiency claim exists.

policy.py provides opt-in economy/balanced/thorough stagnation limits of 1/2/3 unchanged transitions after the initial observation. Passing a previously failed check counts as progress only without regressions. Blockers/regressions stop automated continuation. A builder needs more than 15 seconds remaining, reserved for final checks. This is an admission reserve, not guaranteed sufficient time for arbitrary suites. Legacy specs preserve the old scheduler. New init configs choose balanced.

ledger.py is an IN-PROCESS LIBRARY ONLY. Decimal USD admission preserves verifier funds, uses request IDs and an RLock, reconciles unknown outcomes and records actual overruns. It is not connected to agent/model execution, not persistent, and cannot claim strict provider enforcement. Strict reconciliation prevents new reservations after unknown settlement; no gateway capability is implemented. Old quota.py remains the runtime token ledger.

Next slices, in order: (1) detached acceptance assets and trusted harness, including adversarial mount/symlink checks; (2) durable journal/recovery and runtime monetary admission with explicit provenance, required critic reserve and pricing snapshots; (3) richer footprint/signature scheduler and unified cancellation/deadlines; (4) conservative incremental selection with full final suite; (5) ten executable paired tasks and controlled provider pilot.

Release checklist: only requirement coverage, subset verdict safeguards, local ledger primitives, opt-in retry defaults and adapter flag review have partial evidence. D1 detached protection, D2 runtime budget integration, D3 complete deadlines, D4 incremental checks, D7 checkpoints, F3/F4/F5 required matrices and F6 paired benchmarks remain incomplete. Do not tag/release this branch as v0.5.
