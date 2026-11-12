# Source review and release hardening — Olyder v0.1.0

This is a direct source review of the codebase, **not a CodeRabbit-generated review**. CodeRabbit was not available as an invocable tool in this environment. Use the CodeRabbit GitHub App on a pull request for additional automated review.

## Fixed before first push

| Priority | Area | Finding | Change |
|---|---|---|---|
| High | HTTP checks | Expected `404`/`500` status code was incorrectly treated as a transport failure. | Treat `urllib.error.HTTPError` as an observable response so negative API tests work. |
| High | HTTP checks | Automatic redirects could change the target URL unexpectedly. | Disallow implicit redirects; test the 3xx code explicitly or define a separate check for destination. |
| Medium | Configuration | Malformed browser steps, status codes, timeouts, `contains` values, and source counts were insufficiently validated. | Validate types and bounds eagerly, before execution; reject embedded credentials in URLs. |
| Medium | Check execution | Third-party browser exceptions could abort an entire verification run without a report. | Convert unexpected check exceptions into a failed test result without returning potentially sensitive exception messages. |
| Medium | MCP | Malformed JSON-RPC `params` objects caused an uncaught exception. | Return standard JSON-RPC invalid-params error. |

## Open design / security work

1. **Real sandbox**: the selected project path is not an OS isolation boundary for external agents or commands. Add VM/container/runtime isolation before running untrusted agents.
2. **Quota scope**: Olyder's model token budget does not meter external coding-agent CLIs, subscriptions, or hosted models. An adapter interface is necessary for full accounting.
3. **Network hardening**: URL allowlisting alone is insufficient against SSRF, DNS rebinding, and malicious browser navigation. Only use trusted local specifications and trusted staging systems until network isolation is implemented.
4. **Acceptance completeness**: passing declared checks does not prove unspecified features work. Add scenario discovery, reference datasets, coverage thresholds, and human-defined acceptance criteria.
5. **Process tree and time budgets**: child processes can outlive parent timeouts; some multi-check/network operations can exceed the overall run deadline. Enforce process-group cancellation and end-to-end deadlines.
6. **Sensitive data**: stdout redaction is best-effort. Secrets in logs and source excerpts can reach configured external models; introduce sanitization and field-level opt-in.
7. **Model API**: only one OpenAI-compatible chat endpoint is implemented; test provider-specific compatibility and retry/backoff behavior.

## Release gate

- `PYTHONPATH=src python -m pytest -q` (run without installed package).
- CI matrix tests Linux and Windows with Python 3.11 and 3.13.
- No real model/provider quota, real browser, real Codex/Claude/OpenCode CLI integration, or OS-sandbox security certification was tested in this source review.
