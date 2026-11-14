# Validation report: universal engine branch

This is an incomplete production release gate. Package remains 0.4.0; branch feat/v0.5-verification-efficiency, draft PR #4. Original main baseline: 99b86067c7e676ca1cecc55ecd83f4ba9fe69109. Historical foundation results remain in TEST_RESULTS_V05.json and validation/final-*.xml. Current results are indexed separately in UNIVERSAL_TEST_RESULTS.json with raw artifact SHA256 and individual case status.

| Complete local run | Passed | Failed | Skipped | Environment |
|---|---:|---:|---:|---|
| Original unchanged v0.4 baseline | 172 | 2 | 4 | Windows, symlink privilege absent |
| Foundations before universal work | 234 | 2 | 4 | Windows Python 3.11.15 |
| Foundations before universal work | 237 | 0 | 3 | Ubuntu/WSL Python 3.14.4 |
| Universal engine | 321 | 2 | 7 | Windows Python 3.11.15 |
| Universal engine | 326 | 0 | 4 | Ubuntu/WSL Python 3.14.4 |

The two Windows failures are unchanged original fixtures: test_L2_files[symlink_escape_rejected] and test_no_escape_via_parent_or_symlink fail while creating symlinks with WinError 1314. They were not skipped, weakened or removed. Linux exercises both. Windows skips comprise three opt-in Docker tests, the opt-in live browser case, FIFO/POSIX process-group fixtures and a POSIX ownership fixture. Linux skips are three Docker tests and the live browser. Native hosted jobs are distinct evidence, not inferred from WSL.

All 99 original scenario cases remain. New suites exercise adapter conformance, actual executable-plugin repair, detached hidden tests, missing/case-variant scripts, immutable checker inputs, safe directory replacement, unknown/partial cost, reserve transfer and idempotent settlement, concurrency, strict critic admission, planning/research model admission, cancellation, corrupt state/recovery, dependency mapping/full-suite sentinels, actual loopback API authentication, redaction and HTML/Markdown injection.

Commands used for full local regression:

```text
.venv/Scripts/python.exe -m pytest -q --junitxml=docs/validation/UNIVERSAL_WINDOWS.xml
PYTHONPATH=src /var/tmp/olyder-v05-venv/bin/python -m pytest -q --junitxml=docs/validation/UNIVERSAL_LINUX.xml
python scripts/summarize_universal.py
```

The Linux command runs under Ubuntu WSL from the clone. An initial collection attempt omitted PYTHONPATH and failed to import the package; it was corrected before recording the complete run. No collection failure was counted as a pass.

## Static, packaging and interface evidence

`python -m ruff check src/olyder` passes across the full production source. Import/unused-variable cleanup preserved behavior; optional third-party check exceptions remain fail-closed with a justified narrow lint annotation. `git diff --check -- src tests` passed.

`python -m build --wheel --no-isolation` succeeded. The wheel was force-installed without dependencies in a separate .wheel-smoke environment. Actual installed-wheel CLI help, doctor, sample verification and stdio MCP initialize/tools-list all passed. Reproduce:

```text
python scripts/validate_universal_install.py --python .wheel-smoke/Scripts/python.exe
```

The generated receipt is validation/UNIVERSAL_INSTALL.json. The sample executes three pricing unittest cases and a file assertion, then produces examples/universal/report.json, report.md and report.html. These are actual fixture artifacts, not invented screenshots or manually authored results. The packaged skill is present and matches skills/olyder/SKILL.md. Build warnings concern existing setuptools license metadata; no runtime dependency was added.

## Review, platforms and release limitations

Two CodeRabbit review rounds produced 11 and six findings respectively; fixes and pre-fix/green evidence are documented in REVIEW_UNIVERSAL.md. First-party adversarial sentinels cover additional false-PASS and budget gaps. Later planning/accounting additions did not receive a clean independent review; none is claimed. Red reproduction artifacts are intentionally separate and must not be aggregated into final regression counts.

All seven native jobs passed for source commit 3a34868: Windows, Ubuntu and macOS on Python 3.11/3.13 plus the Linux Docker job. [Actions run 43476719403](https://github.com/Ratnadeep-2007/Olyder/actions/runs/43476719403), with receipt and observed test summaries in validation/UNIVERSAL_CI.json. A macOS API startup timeout was reproduced before the fix: HTTPServer reverse-resolved its fixed loopback address. A failing DNS sentinel preceded the production fix; the real cross-process HTTP/authentication test now passes on both native macOS versions. Server-owned ephemeral port allocation also removes the old test's bind/close race. Earlier failed/cancelled runs are not counted as passes.

| Hosted jobs | Passed per job | Skipped per job | Failed |
|---|---:|---:|---:|
| Ubuntu Python 3.11 / 3.13 | 326 | 4 | 0 |
| macOS Python 3.11 / 3.13 | 326 | 4 | 0 |
| Windows Python 3.11 / 3.13 | 323 | 7 | 0 |
| Separate Linux live Docker | 3 | 0 | 0 |

Local Docker Desktop remains unavailable. Hosted Docker executes three real container tests, including the detached SDK builder/verifier boundary. Live browser, vendor accounts, invoice API/gateway enforcement, rootless/egress proxy, Harbor/SWE-bench and paid model studies were not run. No paid-provider benchmark calls were made. Development-assistant billing is unknown. Offline benchmarking uses deterministic executable agents; see BENCHMARK_V05.md for measured overhead and inconclusive dollar claims.

No original test was deleted, weakened or marked xfail. Missing live integration and broader assurance gates mean this branch is not declared production-verified or released.
