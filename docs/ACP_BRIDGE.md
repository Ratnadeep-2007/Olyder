# Experimental Olyder ACP v1 editor bridge

This integration is **optional, read-only, and not an autonomous coding agent**.
It lets an ACP-compatible editor call Olyder's deterministic project planning,
file-check verification, diagnostics and help through official ACP stdio framing.

## Install and launch

```bash
python -m pip install -e '.[acp]'
olyder acp --workspace /absolute/path/to/project
```

The workspace must contain `olyder.json`. In an ACP client capable of starting
a custom agent process, configure executable `olyder` with arguments
`acp --workspace /absolute/path/to/project`.

For clients that require an interpreter path, use:

```text
/path/to/python -m olyder acp --workspace /absolute/path/to/project
```

A minimal custom agent entry for a Zed-style ACP client:

```json
{
  "agent_servers": {
    "Olyder (read-only)": {
      "type": "custom",
      "command": "/absolute/path/to/python",
      "args": [
        "-m", "olyder", "acp",
        "--workspace", "/absolute/path/to/project"
      ]
    }
  }
}
```

Paths and executable locations differ across Windows, Linux and macOS.
The stdio protocol is an external process interface, not an embedded IDE SDK.

## Supported prompt messages

- `help` — allowed operations and safety restrictions
- `status` — local doctor metadata, no provider or daemon probing
- `plan` — deterministic planning using the existing acceptance specification
- `verify` — only checks that do not require `--allow-exec`. Command, HTTP and
  browser checks remain **blocked** and do not establish full acceptance.

All other prompts are rejected with help text; they are never treated as shell
instructions or sent to an LLM. Images, resource links and embedded content are
not accepted in this initial bridge.

## Security boundaries

- The ACP session `cwd` must resolve to the server-authorized workspace.
- ACP-provided extra directories and external MCP servers are denied.
- The agent neither modifies source files nor starts builders or remote models.
- Protocol transport and schema validation are delegated to the optional
  official `agent-client-protocol` Python dependency.
- The Python SDK currently implements **ACP v1**, not v2. Olyder responds
  with its supported revision instead of claiming v2. There is no remote
  ACP transport, session persistence, prompt history or background coding.
- Process cancellation prevents a cancelled result being presented as
  completed; it is **not** an OS-level hard stop of an in-progress file scan.
- Session IDs exist only during the editor connection, not across restarts.
- Full command, browser, network, and autonomous repair workflows remain
  available via the explicitly authorized Olyder CLI / Python SDK.

## Tests and scope of compatibility

`tests/test_acp_bridge.py` exercises a real independent ACP Python client
over stdio, the project root restriction, unsupported content, safe
verification blocking, and normal streamed updates. The dedicated
`acp-interop` CI job installs the optional dependency and executes these
tests on Ubuntu.

A passing SDK client fixture is **not** blanket ACP v1 TCK certification,
nor a live Zed/Cursor/JetBrains integration result. A named editor live test
and cross-platform ACP interoperability matrix are separate future gates.

### Related specs

- https://agentclientprotocol.com/protocol/v1/overview
- https://agentclientprotocol.github.io/python-sdk/quickstart/
- https://github.com/agentclientprotocol/acp-tck
