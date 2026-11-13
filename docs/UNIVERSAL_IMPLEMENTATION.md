# Universal engine implementation plan and audit

Base: 92a91f4, branch feat/v0.5-verification-efficiency; clean, matches origin on 2026-11-13.
Policy: planning=deep, context_depth=dependency, verification_depth=full, delegation=none.

Audit: CLI/MCP, deterministic checks, optional model review, agent JSONL parsers and Docker/host execution work. Requirement coverage, retry modes and Decimal ledger have tests. Missing: reusable adapter/backend protocols, SDK, detached harness, runtime dollars, durable run state, safe resumption, selection mapping, plugin permission contracts and executable comparisons. Existing 99-case matrix must remain unchanged.

Chosen architecture: stdlib protocols plus explicitly registered integrations; existing engine remains a compatibility layer. New SDK orchestration owns detached builder/harness workspaces, immutable snapshots, resource admission, events and checkpoint state. CLI routes mutating runs through SDK; legacy direct engine API remains documented for compatibility. Host mode requires an unsafe grant; Docker must never fall back. Local HTTP is optional and read-only. Plugins are either trusted explicitly registered Python objects or explicit argv manifests executed with granted permissions, never auto-imported workspace code.

- [ ] P0a: interfaces.py/adapters.py/backends.py; conformance tests; preserve existing parsers.
- [ ] P0b: workspace.py builds proposals without protected assets and assembles trusted harnesses; adversarial tests.
- [ ] P0c: accounting.py and SDK dollar admission/critic reserve/pricing/provenance; strict unknown stop; fake provider tests.
- [ ] P1: state.py atomic SQLite checkpoints, cancellation, safe resume; impact.py conservative selection; repair/research evidence.
- [ ] P2: SDK, CLI status/resume/cancel/report/doctor, read-only MCP/API, permission-checked plugin example.
- [ ] P3: full regression, macOS matrix, ten-task offline paired baseline/modes, packaging, docs and PR update.

Each slice: tests first, observe red, implement, targeted green, regression evidence. No paid model call, merge, tag or release without approval. Source usage is never a provider invoice; unknown is never zero. No optimization may accept without the full mandatory suite.
