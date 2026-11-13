# Olyder v0.3.0: enhancement validation and next release gates

**Date:** 2026-11-13. **Repository baseline:** v0.2.0 (`4b8cda0`).
**Test setup:** locally reproducible Python 3.13/Linux; GitHub Actions subsequently checks Python 3.11 and 3.13 on both Ubuntu and Windows.

## Functional and non-functional changes

| Category | Priority | Hypothesis and acceptance oracle | Implementation | Evidence |
| --- | --- | --- | --- | --- |
| Security (non-functional) | P0 | Provider-issued redirect must not send a dummy API key to another host | Dedicated non-redirecting `urllib` opener in `models.py` | Local 301/302/307/308 fake-provider tests; no destination requests |
| Verification integrity (functional + security) | P0 | A builder rewriting an executable acceptance test must never produce a passing final verdict | In-process fingerprints of existing test files/trees + explicit `protected_paths` | Two malicious-builder fixtures and explicit custom-fixture test |
| Quota correctness (functional) | P1 | Two identical-sized token reservations cannot both be settled using the first ticket | Unique one-use `Reservation` ticket carrying the estimate | Duplicate/foreign/release/validation regression tests |
| Reliability (non-functional) | P1 | A check returning HTTP 200 after an expired deadline cannot be counted as passed | Bound HTTP timeout by remaining deadline and fail closed after execution | Slow local test server fixture |
| Privacy (non-functional) | P1 | Common printed auth tokens must not appear in report check details | `privacy.redact` applied to recorded results | Bearer/basic/password/URL-credentials examples |

### Reproduction

```bash
python -m pip install -e '.[dev]'
python -m pytest -q tests/test_enhancement_probes.py
python -m pytest -q
```

**Local outcome:** 18 additional hardening regressions passed. Full suite **150 passed, 1 optional live-browser test skipped**. These checks never require real AI subscriptions or credentials. The v0.2.0 comparison suite remained unchanged except one test double was switched from patching `urllib.urlopen` to patching Olyder's new `_open_model_request` adapter.

The test evidence establishes only those specific expected outcomes; it is not an independent external security certification. Acceptance test fingerprints can be bypassed by hostile code that can edit unprotected imports, reconfigure the environment, retain background processes, or interfere with the trusted process. Runtime OS isolation remains essential.

## Research validation and next engineering phases

1. **P0 OS-enforced builder isolation (non-functional):** least-privilege containers / WSL2 / Windows sandbox, with separately mounted read-only verification tests and isolated credentials. A path-hash detector is a defense-in-depth feature, not a replacement. See OWASP agent and MCP security: https://owasp.github.io/DevSecOpsGuideline/2-Process/2-2-Develop/2-2-5-AI-Agent-and-MCP-Security/
2. **P1 process-tree cancellation and egress control (non-functional):** test nested child processes and remote DNS/redirect attempts under approved and denied conditions. Local timeout alone does not guarantee descendant termination.
3. **P1 real agent adapter and billing evidence (functional):** Codex CLI `exec --json` exposes event data and a `turn.completed.usage` summary; use a provider-aware parser plus a contract fixture before claiming measured external-builder tokens. See https://learn.chatgpt.com/docs/non-interactive-mode . Do not assume Claude/OpenCode event schemas match.
4. **P2 real-browser trace and replay (functional/reliability):** record Playwright traces only on failure/retry for CI; official guidance notes always-on tracing has overhead. See https://playwright.dev/docs/trace-viewer . The optional live Chromium smoke remains unverified in this environment.
5. **P2 change-aware reruns (performance):** measure wall-clock savings and regression misses. Permit selective interim retries only with a conservative dependency map, and always run the *full locked acceptance suite* for the final verdict. Benchmark against all-tests baseline on at least 10 varied repositories and report p50/p95 speed and false-negative rates, not a fabricated percentage.
6. **P2 independent product acceptance evaluation (functional):** mutation test known-bad implementations and measure detection rate; don't confuse passing declared checks with complete requirement coverage.

## Release-gate guidance

Promote only when required CI platforms pass, no new expected failures remain, and tests are actually executed (not only mocked). Never label a simulated browser or stub-model run as a production interoperability pass.
