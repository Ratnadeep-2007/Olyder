# Olyder

**Check whether an AI-written change meets your requirements.**

Olyder runs the tests and file checks you choose, then shows what passed, what
failed, and what couldn't run. Keep those checks in an `olyder.json` file so
you can run the same requirements on your machine, from an editor, or on a
GitHub pull request.

[![PyPI](https://img.shields.io/pypi/v/olyder?include_prereleases)](https://pypi.org/project/olyder/)
[![CI](https://github.com/Ratnadeep-2007/Olyder/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Ratnadeep-2007/Olyder/actions/workflows/ci.yml)
[![Apache 2.0 license](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

[Try it](#quick-start) · [Verify your repo](#verify-your-repository) ·
[Connect an editor](#use-olyder-in-your-editor-or-ci) · [Run it on a pull request](#run-it-on-a-pull-request)

## Quick start

Activate a Python 3.11+ virtual environment and run:

```sh
python -m pip install --pre olyder
python -m olyder demo
```

Open `.olyder/demo/pass/report.html` to see the verdict and the two checks
behind it. The demo runs offline after installation and needs no API key.
Use `python -m olyder demo --fail` to see a failed check in
`.olyder/demo/fail/report.html`.
Run `python -m olyder --version` to see which beta you installed.

For a new virtual environment, run `python -m venv .venv`, then activate it
with `source .venv/bin/activate` on macOS or Linux, or
`.\.venv\Scripts\Activate.ps1` in PowerShell.
In PowerShell you can also use `.\.venv\Scripts\python.exe` in place of
`python` in the commands above.

## See a real test catch a regression

A cart should charge **75** after a 25% discount on a price of 100. The
[cart-pricing example](examples/demo-app/) runs the same acceptance spec
against a broken calculation and its fix.

| Change | What the tests found | Verdict |
| --- | --- | --- |
| Discount disabled | `test_discount` gets 100 when it expects 75 | Failed |
| Discount restored | All three pricing tests pass | Passed |

From an Olyder checkout with the package installed, run:

```sh
python examples/demo-app/replay_regression.py
```

The replay uses a temporary copy and makes zero model calls. Compare
`report.html` in `.olyder/pricing-proof/discount-regression/` and
`.olyder/pricing-proof/discount-fixed/`. Both reports record the same spec
hash, so you can see that the requirements held steady while the code changed.

## Verify your repository

Put an `olyder.json` file at your project root and run the commands from that
directory. Start with one condition that matters for the change you're making.
This example checks for the exact text
`## Install` in the project README. A file check matches text anywhere in
the file. Use a command check if you need to validate the document's structure.

```json
{
  "goal": "Readers can find the installation section",
  "checks": [
    {"id": "install-docs", "type": "file", "path": "README.md", "contains": "## Install"}
  ]
}
```

```sh
python -m olyder plan
python -m olyder verify
```

### Read the result

Open `.olyder/report.html` and look under **Acceptance tests**. If
`install-docs` failed, the **Evidence** column tells you what Olyder checked.
Add the missing text to the project README and run verification again.
To keep both reports, give each run a separate output directory, such as
`python -m olyder verify --output .olyder/after-fix`.

![Olyder's HTML report marks install-docs as failed and says the text did not match in README.md](docs/images/readme-check-report.png)

The report directory also contains `report.md` for reviews and `report.json`
for tools.

### Use a test you already run

Add a command check to the `checks` array when the requirement is about
behavior, such as a discount calculation or a generated document containing
an expected field. Use the command you already run in the project. The
Python interpreter in this example needs pytest and your test dependencies.

```json
{"id": "unit-tests", "type": "command", "argv": ["python", "-m", "pytest", "-q"]}
```

If Windows picks a different Python, replace the first `argv` item with the
full path to the interpreter that has pytest installed. Use forward slashes
in the JSON path, for example `C:/work/project/.venv/Scripts/python.exe`.

Review configured commands before running `python -m olyder verify --allow-exec`.
File checks run by default. HTTP and optional Playwright browser checks need
`--allow-exec`, and non-local URLs need `--allow-network` as well. See the
[scenario examples](docs/EXAMPLES.md) for browser and staging checks.

## Run it on a pull request

1. Add the `olyder.json` that you ran locally to your branch.
2. Add the workflow from the [GitHub Actions guide](docs/GITHUB_ACTIONS.md).
   Start with a file check. For a test suite that needs dependencies, run
   Olyder in the same CI job that installs them.
3. Open a pull request. Look for the verdict in the job summary and download
   the `olyder-report` artifact for the evidence. Keep the check on later PRs
   if it catches something you care about reviewing.

## Use Olyder in your editor or CI

| Where | How to start |
| --- | --- |
| **Codex** | Run `python -m olyder setup codex` from your project root. [Codex setup](docs/UNIVERSAL_GUIDE.md#use-olyder-in-codex) |
| **Google Antigravity** | Run `python -m olyder setup antigravity` from your project root. [Antigravity setup](docs/ANTIGRAVITY.md) |
| **GitHub Actions** | Call the reusable workflow to see the verdict on a pull request and download the full report. [GitHub Actions setup](docs/GITHUB_ACTIONS.md) |
| **OpenCode or Claude Code** | Run `python -m olyder setup opencode` or `python -m olyder setup claude`. [Editor setup](docs/UNIVERSAL_GUIDE.md#quick-global-editor-setup) |

Use `python -m olyder doctor` to check local capabilities. Add `--global` to
an editor setup command to install the skill for all your projects.
If your editor's terminal can't launch `olyder`, ask the agent to use
`python -m olyder` from the environment where you installed the package.

For tool integrations, see the [Python SDK and MCP guide](docs/UNIVERSAL_GUIDE.md)
and the [optional ACP bridge](docs/ACP_BRIDGE.md). The integration guide also
covers optional model review and bounded repair attempts.

## Trust and validation

- **Read the evidence.** Exit `0` means the declared checks passed. Exit `1`
  means a check failed or acceptance is unresolved. Exit `2` means a CLI or
  configuration error. The JSON report distinguishes failed and blocked checks.
- **Collect the current report.** Use a fresh `--output` directory per run in CI.
  A configuration error can leave older reports in place. When using `--spec`
  from another directory, the default output is relative to where you ran Olyder.
- **Choose which code can run.** Local checks and builder runs in host mode
  share the host's permissions. Use external isolation for untrusted code.
  Review test output and optional browser traces before sharing reports.
- **Know what the verdict covers.** It covers the declared checks in the
  recorded environment. An optional model review can assess that evidence.
  A failed deterministic check stays failed.

CI runs on Linux, macOS, and Windows. See [known limits](docs/KNOWN_LIMITATIONS.md),
the [threat model](docs/THREAT_MODEL.md), and the [release checks](docs/PYPI_RELEASE.md).
The [verification benchmark](docs/BENCHMARK_V05.md) and
[99-scenario test report](docs/QA_99.md) explain what was tested.

## Contribute

Try Olyder on a change in your own repo. If setup trips you up or a verdict
surprises you, share a small spec and a report with private data removed in
the [issue tracker](https://github.com/Ratnadeep-2007/Olyder/issues/new/choose).
For local development and contribution ideas, see the
[contributing guide](CONTRIBUTING.md).

[Apache License 2.0](LICENSE) · [Changelog](CHANGELOG.md)
