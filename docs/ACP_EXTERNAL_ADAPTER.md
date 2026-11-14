# Experimental ACP v1 external-agent adapter

**Status:** Development feature. The existing editor-facing ACP read-only bridge is
separate. This module adds a **client** that starts an external ACP v1 coding
agent using the official, optional Python SDK.

The adapter uses Olyder's existing `AgentAdapter` protocol, detached builder
workspace, permission grants, budget admission, and independent acceptance
checks. It does **not** claim that every ACP agent supports direct-workspace
editing or that the ACP TCK has passed.

## How to try it

From a source clone:

```bash
python -m pip install -e ".[acp]"
```

Prepare a reviewed executable plugin manifest (replace `YOUR_AGENT_BINARY`
and flags with a **known ACP v1 agent implementation**):

```json
{
  "api_version": 1,
  "kind": "agent",
  "protocol": "acp-v1",
  "runner_python": "python3",
  "name": "my-acp-agent",
  "argv": ["YOUR_AGENT_BINARY", "ACP_STDIN_MODE"],
  "permissions": ["execute", "write_workspace"]
}
```

Set `builder.provider` to `my-acp-agent` in the project's `olyder.json`.
Supply a complete mandatory acceptance suite. To run inside a reviewed
Docker image, the image must include both `olyder-agent[acp]` and the agent
binary:

```bash
olyder run --spec ./olyder.json --plugin /path/to/agent.json \
  --grant-plugin my-acp-agent --allow-exec --execute-builder \
  --sandbox docker --docker-image YOUR_REVIEWED_IMAGE
```

The optional `runner_python` field selects the interpreter **inside the
chosen execution backend**. For a reviewed Linux container that installs
Olyder and the ACP SDK, use `"runner_python": "python3"`; for a Windows
host virtual environment you can omit the field to use the current Python
interpreter. Do not assume the host's absolute Python path exists in Docker.

Docker does not fall back to host. If a trusted local experiment must use
the host, replace the sandbox flags with `--unsafe-host`, knowing that
the agent can access all resources permitted to your operating-system user.
Use a disposable workspace. Do not run untrusted ACP agents on the host.

## Technical scope

- ACP protocol revision: **v1** through the optional official SDK.
- Session: `initialize`, `session/new`, `session/prompt`. A fresh
  session is created for each Olyder builder turn.
- Agent stdout is reserved for ACP JSON-RPC; Olyder's supervised wrapper
  outputs only a sanitized final status.
- ACP client requests for file reads/writes, terminal launches and
  permission escalation are **denied**. An agent that requires
  client-mediated editor/file tools is **not yet supported**; it may instead
  use its own explicitly sandboxed direct filesystem operations.
- No client-provided extra workspaces or arbitrary MCP servers are supplied.
- Cancellation is controlled by Olyder's process-tree supervisor; the client
  runner does not independently certify detached-child cleanup.
- Token usage and actual billing remain **unknown**. The runner refuses
  to invent cost estimates or mark provider hard caps as supported.
- A refusal, failed protocol handshake, invalid SDK data, missing
  executable or incomplete turn must not satisfy the builder status.
- Olyder's independent verifier decides actual acceptance. Successful ACP
  communication alone is never final PASS.
- A Docker image with matching Python module locations and the optional
  SDK must be built/reviewed; a passing host fixture is not Docker
  compatibility proof for any particular external ACP agent.

## Validation

`tests/test_acp_external.py` uses a real independent ACP Python agent
subprocess. The fixture makes a change inside the detached proposal and
Olyder independently verifies it before applying to the original project.
Other tests cover explicit plugin grants, parser fail-closed behavior, agent
refusals, unsupported usage claims and malformed manifests.

The dedicated `acp-interop` CI matrix runs these tests on Windows, Linux,
and macOS with the optional Python SDK. This is integration proof for the
fixture, not a real commercial-agent certification or the complete ACP TCK.

## Follow-up milestones

1. Formal ACP TCK and independently developed third-party ACP agent pilot.
2. Capability-negotiated client-mediated file/terminal tools with explicit
   scoped grants, audited permission prompts and sandbox lifecycle.
3. Correlated event streaming and model/provider telemetry with provenance.
4. Independent paid-provider task studies with user-authorized budgets.

See also `docs/ACP_BRIDGE.md` for the separate editor-facing ACP server.
