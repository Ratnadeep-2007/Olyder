# v0.5 development validation ? incomplete release gate

No v0.5 release is claimed. Base/main: 99b86067c7e676ca1cecc55ecd83f4ba9fe69109. Feature branch: feat/v0.5-verification-efficiency. Package remains 0.4.0.

| Run | Passed | Failed | Skipped | Notes |
|---|---:|---:|---:|---|
| Unchanged v0.4 Windows baseline | 172 | 2 | 4 | Symlink privilege failures |
| Current Windows, Python 3.11.15 | 232 | 2 | 4 | Same two baseline failures |
| Current Ubuntu/WSL, Python 3.14.4 | 235 | 0 | 3 | Complete suite, original 99 cases retained |

Windows failures: test_L2_files[symlink_escape_rejected] and test_no_escape_via_parent_or_symlink fail while creating the fixture (WinError 1314). No original tests were changed, skipped or weakened. Windows skips include Unix-only process-group behavior, two opt-in Docker tests and one opt-in live browser test. Linux skips are the two Docker tests and live browser. WSL is not native GitHub-hosted Ubuntu/Python 3.11/3.13 evidence.

Sixty new tests cover verdict completeness, schema validation, requirements, ledger admission/concurrency/unknown reconciliation, policy progress, CLI modes, spec mutation and reviewer regressions. This does NOT satisfy every required F2-F5 scenario. Initial verdict reproduction: three failures and one passing control. Ledger/policy initial collection failed because the modules did not exist; this is weaker than behavior-level red evidence. Later schema/security cases were added after implementation and are explicitly not claimed test-first. CodeRabbit's three findings each had a failing reproducer before repair.

Commands: `.venv/Scripts/python.exe -m pytest -q --junitxml=final-windows.xml`; Linux `PYTHONPATH=src /var/tmp/olyder-v05-venv/bin/python -m pytest -q --junitxml=final-linux.xml`. JUnit artifacts are retained in validation/; regenerate machine data with `python scripts/summarize_v05_tests.py` after copying new XML there.

Wheel: python -m build --wheel succeeded. Clean .wheel-smoke environment installed the wheel without dependencies, CLI --help succeeded, and sample verify --allow-exec passed. Real sample artifacts: examples/v05/report.{json,md,html}. Build warns about existing deprecated setuptools license metadata. Ruff passed for contracts.py, ledger.py and policy.py only; no repository-wide lint-clean claim. git diff --check passed.

CodeRabbit CLI 0.9.3 reviewed the tracked patch: three minor findings (unused verification reserve, imprecise stop reason, critic-only rebuild). All three reproduced and were fixed. A follow-up including new files is required before treating the review as comprehensive.

Live Docker: BLOCKED, daemon pipe absent. Live browser/provider, strict gateway, official benchmark harnesses and paid pilot: NOT RUN. No paid-provider benchmark calls were made; development-assistant billing is unknown. Native CI is pending the PR. Remaining release blockers are listed in ARCHITECTURE_V05.md and KNOWN_LIMITATIONS.md.
