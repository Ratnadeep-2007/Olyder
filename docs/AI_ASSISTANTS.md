# Use the Olyder agent validation skill with an AI assistant

Olyder checks AI-generated code against acceptance criteria you define in
`olyder.json`. It runs the checks and writes an HTML, Markdown, and JSON
report showing what passed, failed, or was blocked.
[Official GitHub repository](https://github.com/Ratnadeep-2007/Olyder) ·
[Official PyPI package](https://pypi.org/project/Olyder/) ·
[Skill definition](../skills/olyder/SKILL.md)

## Use a supported editor skill

Install Beta 2 in a Python 3.11+ virtual environment to follow the tested
setup below. From your project root, run the command for your editor.

```sh
python -m pip install "olyder==0.5.0b2"
python -m olyder --version
```

| Editor | Workspace setup |
| --- | --- |
| Codex | `python -m olyder setup codex` |
| Google Antigravity | `python -m olyder setup antigravity` |
| OpenCode | `python -m olyder setup opencode` |
| Claude Code | `python -m olyder setup claude` |

Open the same workspace in the editor. See the [Codex setup guide](UNIVERSAL_GUIDE.md#use-olyder-in-codex)
and [Antigravity setup guide](ANTIGRAVITY.md) for skill discovery. Then ask:

> Use the Olyder skill to verify this project against `olyder.json`.
> Show the verdict, any failed or blocked checks, and the report path.
> Ask me before running executable checks.

## Use a terminal-enabled assistant

Give the assistant the project folder and the Python environment where you
installed Olyder. Start with the [file-only example](../README.md#verify-your-repository)
if the project needs an acceptance spec. The assistant can run these commands
from the project root without an editor-specific skill:

```sh
python -m olyder plan --spec olyder.json
python -m olyder verify --spec olyder.json --output .olyder/assistant-review
```

Open `.olyder/assistant-review/report.html` to see the evidence. Review command
checks before enabling them with `--allow-exec`. The example makes zero
Olyder model calls. Run verification in an isolated environment when checking
untrusted code.

## Connect an MCP client

If your client supports **local stdio MCP**, configure it to launch Olyder
with the full path to the Python interpreter that has Olyder installed.
Use the absolute path to your project in place of `/path/to/project`.

```sh
python -m olyder mcp --workspace /path/to/project
```

For clients that use an `mcpServers` JSON configuration, replace both paths
in this example with the absolute paths on your machine.

```json
{
  "mcpServers": {
    "olyder": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "olyder", "mcp", "--workspace", "/path/to/project"]
    }
  }
}
```

The default server exposes planning and file-only verification. See the
[integration guide](UNIVERSAL_GUIDE.md) for the server's permission model.

## Use a chat assistant to read a report

Share this guide with a browsing assistant, or paste the relevant instructions
into chat. If the assistant has no terminal access, run Olyder yourself and
paste the relevant parts of `report.md` or `report.json`. Remove sensitive
project details and test output before sharing. Ask the assistant to explain
the verdict and cite the evidence for each check it discusses.
