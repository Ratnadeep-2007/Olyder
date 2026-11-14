# Changelog

## 0.5.0b1 — first PyPI beta candidate (pending owner approval)

- Distribution renamed from unpublished `olyder-agent` to `olyder` to support
  the intended `pip install olyder` flow when published.
- One-command editor skill setup, including project and global native skill
  locations, conflict-safe repeated installs, and correct `description` metadata.
- GitHub Actions builds/checks wheel and sdist and clean-installs the wheel
  across Windows, Ubuntu and macOS.
- Release-tag and version consistency validation, content/secret checks,
  and PyPI Trusted Publishing through an approval-gated GitHub environment.
- All previously documented limitations remain: no real paid vendor benchmark,
  no provider-enforced quota cap, and no complete ACP TCK. Experimental ACP
  external-client support remains **unmerged** in a separate draft PR.
- First public upload requires the package owner's PyPI account and publisher
  authorization; committing this candidate alone does not publish it.


## Unreleased v0.5 foundations (not release-ready)

- Explicit schema-2 requirement coverage and subset/critic completion guards.
- Decimal ledger library and opt-in progress-aware retry modes.
- Conservative adapter flags and evidence in all report formats.
- Runtime monetary integration, detached harness, durable recovery and paired benchmarks remain outstanding.

## Unreleased universal engine

- Versioned adapter/backend/model/verifier/event interfaces and protected SDK orchestration.
- Detached acceptance snapshots, source application checks and explicit plugin permissions.
- Runtime Decimal admission, verifier reserves, usage provenance, dated pricing and manual receipt reconciliation.
- Transactional run IDs/checkpoints, cancellation, restricted recovery and retention controls.
- Dependency-aware intermediate selection with mandatory final full verification; no result cache.
- CLI diagnostics/state/report/benchmark commands, SDK, server-granted local MCP execution and read-only loopback API.
- Windows/Ubuntu/macOS matrix, Docker SDK smoke, executable paired pilot and new adversarial tests.
- No production tag, hard quota, live paid-vendor benchmark or exhaustive-security claim.
