# Changelog

## 0.5.0b2 — simpler setup and pull request checks

- Install from PyPI and run Olyder with `python -m olyder`. The Codex and
  Antigravity guides show how to check that your editor found the workspace skill.
- Replay a broken cart discount and its fix with the same tests. Olyder writes
  a report for each result and makes zero model calls.
- Add Olyder to a pull request with a reusable GitHub Actions workflow. The
  run summary shows the verdict and failing checks, and the full report is
  available to download. File checks work by default. Command checks are opt-in.

## 0.5.0b1 — first PyPI beta

- Published to PyPI under the name **Olyder**.
- Offline pass/fail demo with real verification reports, exercised from the built wheel.
- Antigravity setup guide and a GitHub Actions starter with verdict summaries
  and downloadable acceptance evidence.
- Protected test inputs reject new conventional acceptance files and preserve root pytest configuration.
- Managed subprocesses and Chromium exclude Olyder's verifier and local API tokens.
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
