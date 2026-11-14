# Olyder interoperability and assurance roadmap (research, 2026-11-14)

This is a **future compatibility plan**, not a claim that every listed protocol is
implemented. The existing v0.5 feature branch is unreleased and stays on PR #4.

## Scope and confirmed baseline

Olyder's universal Python SDK and CLI already run independently of any editor.
Its current MCP endpoint is local **stdio with the 2025-03-26 handshake**,
read-only by default. Its existing plugin contract is **Olyder-specific**, not
Agent Client Protocol (ACP), and its optional loopback HTTP API is **not an MCP
HTTP transport**. Docker is optional. The latest code hardens stdio against
oversized frames and redacts caught tool error messages.

Universal core != universal out-of-the-box interoperability. A client/agent
must explicitly support a compatible contract or be adapted.

## P0. Truthful protocol compatibility and conformance

- **MCP (current):** Retain the honest 2025-03-26 stdio handshake; bound
  frame size and sanitize failures. Run an actual independent MCP client
  handshake and tool invocation as an integration test. Verify read-only
  defaults and server-owned permissions. Do not advertise protocols on the
  basis of tool names alone.
- **MCP (2026-07-28):** Research and implement a separate versioned
  connection path based on current official SDKs. This revision has
  stateless per-request metadata and discovery, and is NOT enabled by simply
  changing the `protocolVersion` string in an old `initialize` reply.
  Add both old/new protocol conformance tests before claiming support.
  Keep local stdio as the first supported transport; remote MCP needs real
  authorization, transport, origin and token-handling design.
- **ACP:** Agent Client Protocol enables editor-to-agent interoperability
  beyond IDE-specific wrappers. Evaluate a dedicated ACP adapter/bridge
  and run the public ACP TCK. ACP is different from MCP; do not represent
  MCP tools as an ACP implementation.
- **No IDE-specific core:** Thin adapters or process launchers for
  VS Code, Cursor and JetBrains must all call the same Olyder SDK.

## P1. Reproducibility and provider-independent telemetry

- Model Olyder lifecycle events with optional OpenTelemetry GenAI semantic
  conventions, including agent/tool spans and provider-usage provenance.
- Default to **metadata only**: no raw source code, prompts, passwords, agent
  hidden thoughts, or HTTP auth headers in exported spans.
- Distinguish request estimates, agent observations and invoice charges; an
  unknown value remains unknown. Avoid counting nested provider spans twice.
- Add configuration negotiation tests for missing capabilities, cancellation,
  streamed responses, and version-incompatible plugins.
- Test one complete independent agent/IDE client for every advertised
  protocol rather than only parser fixtures.

## P1. Security and execution boundaries

- Never treat an explicitly unsafe host process as an OS sandbox.
- Keep builder proposals separate from protected verification assets.
- Restrict network egress when remote models are authorized; Docker bridge
  without an allowlist is not a restricted-provider-only network.
- Review malicious plugin manifests, symlink/reparse points, inherited
  environment variables, subprocess-tree cleanup and artifact secrets.
- Treat local reports/snapshots as potentially sensitive.

## P2. Performance, reliability and product adoption

- Make full verification mandatory before a PASS; measure whether opt-in
  incremental checks reduce overall time without false passes.
- Benchmark on **real agent tasks** with user-authorized budgets and
  provider invoice reconciliation. Offline fixture timing is not model
  quality or spending evidence.
- Reduce per-run snapshot/checkpoint overhead on tiny projects only if
  cross-platform integrity and recovery tests stay green.
- Improve `olyder doctor` to explain selected backend, supported protocol
  revisions, and unmet capabilities without probing untrusted executables.
- Publish a conformance matrix: actual OS/runtime, client/agent version,
  observed status, limitations and reproducible evidence.

## External references (accessed 2026-11-14)

- ACP design and ecosystem: https://agentclientprotocol.com/
- ACP conformance kit: https://github.com/agentclientprotocol/acp-tck
- JetBrains ACP overview: https://www.jetbrains.com/acp/
- MCP specification 2026-07-28:
  https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP stdio transport:
  https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/stdio.mdx
- MCP version migration:
  https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28
- OpenTelemetry GenAI agent spans:
  https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md
- OWASP Agentic Skills Top 10:
  https://owasp.github.io/www-project-agentic-skills-top-10/

## Gate to a universal-platform claim

Do not release as IDE/agent universal until independent MCP and ACP
conformance, at least one real editor integration, cross-platform isolation
and cancellation evidence, and honest billing provenance are recorded.
A successful smoke test of a named subprocess adapter alone is insufficient.
