# Olyder

**Test AI-generated code against acceptance criteria you define.**

Olyder turns an `olyder.json` acceptance specification into a reproducible verdict
and HTML, Markdown, and JSON evidence. Use it with Google Antigravity, Codex,
Claude Code, or OpenCode, or run it in GitHub Actions.
Deterministic verification works with Python 3.11+ and uses zero model tokens.
An optional reviewer can assess the observed evidence, and a repair loop can
send failing checks back to a configured builder.

[![CI](https://github.com/Ratnadeep-2007/Olyder/actions/workflows/ci.yml/badge.svg)](https://github.com/Ratnadeep-2007/Olyder/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/olyder?include_prereleases)](https://pypi.org/project/olyder/)
[Quick start](#quick-start) · [Verify your repository](#verify-your-repository) · [Antigravity skill](docs/ANTIGRAVITY.md) · [GitHub Actions](docs/GITHUB_ACTIONS.md) · [Contribute](CONTRIBUTING.md)

## Quick start

Install the [PyPI beta](https://pypi.org/project/olyder/) with Python
3.11 or newer. Create an environment with `python -m venv .venv` and activate
it with `source .venv/bin/activate` on macOS and Linux or
`.\.venv\Scripts\Activate.ps1` in PowerShell.

```sh
python -m pip install --pre olyder
python -m olyder --version
```

Use the Python interpreter from the environment where you installed Olyder.
The shorter `olyder` command is also available where your system allows the
installed launcher to run.

## See a real test catch a regression

The cart-pricing example expects a 25% discount on a price of 100. With the
discount calculation broken, the unit test receives 100 instead of 75 and
Olyder exits `1`. Restore the calculation and all three unit tests pass
against the same acceptance spec. From an Olyder checkout, run:

```sh
python examples/demo-app/replay_regression.py
```

The replay runs both cases in a temporary copy. Open `report.html` in
`.olyder/pricing-proof/discount-regression/` and
`.olyder/pricing-proof/discount-fixed/` to compare the verdicts and spec hashes.
The replay works offline and makes zero model calls. For an offline smoke
test using only the installed CLI, run `python -m olyder demo`.

## Verify your repository

Save this as `olyder.json` at your project root and replace the sample assertion
with a condition your change must satisfy.

```json
{
  "goal": "The README explains how to install the project",
  "checks": [
    {"id": "install-docs", "type": "file", "path": "README.md", "contains": "Install"}
  ]
}
```

```sh
python -m olyder plan
python -m olyder verify
```

Add a check object to the `checks` array to run your existing test suite.
This example assumes pytest is installed in the verification environment.

```json
{"id": "unit-tests", "type": "command", "argv": ["python", "-m", "pytest", "-q"]}
```

Review all configured commands before running `python -m olyder verify --allow-exec`.
File checks need no execution grant.
HTTP and optional Playwright browser checks require `--allow-exec`, and
non-local URLs also require `--allow-network`. A blocked check leaves acceptance
unverified. See the [cart-pricing example](examples/demo-app/) for a checked-in
spec with a real unit test suite.

Use the same `olyder verify` command in CI and archive `.olyder/report.json` or
`report.html` when the contents are safe to share. Exit `0` means acceptance
passed. Exit `1` covers failed or unresolved acceptance, and `2` covers CLI
or configuration errors. The JSON verdict differentiates failed and blocked checks.
A configuration error leaves earlier reports in place. Use the exit code and
the report paths from the current command when collecting evidence. In CI, use
a fresh `--output` directory per run and archive reports for exits `0` or `1`.
Reports show selected checks and actual execution coverage. If you run
from another directory with `--spec`, the default report directory is relative
to the directory where you launched Olyder. Use `--output` to select it explicitly.

## Choose how to use Olyder

| Use case | Entry point |
| --- | --- |
| Add local or CI verification | `olyder verify` and a checked-in `olyder.json`. Use the [GitHub Actions starter](docs/GITHUB_ACTIONS.md) for pull requests |
| Give an editor the Olyder skill | `python -m olyder setup` with [`antigravity`](docs/ANTIGRAVITY.md), [`codex`](docs/UNIVERSAL_GUIDE.md#use-olyder-in-codex), `opencode`, or `claude`. Add `--global` for all projects |
| Integrate a tool or application | Python [SDK](docs/UNIVERSAL_GUIDE.md) or read-only-by-default stdio `olyder mcp` |
| Connect a compatible ACP editor | Optional [ACP v1 bridge](docs/ACP_BRIDGE.md) via `olyder[acp]` |
| Review evidence with another model | `olyder verify --ai` with a configured OpenAI-compatible endpoint |
| Run bounded correction attempts | Configured Codex, OpenCode, Claude, or executable adapter with explicit builder permissions and a reviewed [Docker sandbox](docs/UNIVERSAL_GUIDE.md) |

`olyder doctor` reports local capabilities. Skills can be installed repeatedly
and preserve customized files unless you pass `--force`.
See the [integration guide](docs/UNIVERSAL_GUIDE.md) for configuration, execution
permissions, resuming runs, and reports. The [scenario examples](docs/EXAMPLES.md)
cover browser, staging, and data workflows.

## Trust and validation

- A successful verdict covers the declared checks in the recorded environment.
  Optional model feedback gets a fresh request with requirements and bounded
  test evidence. It cannot override a deterministic failure.
- Builder runs separate the proposed code from protected acceptance inputs.
  Host mode has no OS isolation. Use separately enforced filesystem, credential,
  and network restrictions for untrusted code.
- Olyder can track its own model calls and record supported builder telemetry.
  Provider hard spending limits and subscription balances are outside its control.
- Reports may contain test output. Review them before saving to shared CI artifacts.
  Browser traces are opt-in and can include sensitive data.

See [known limits](docs/KNOWN_LIMITATIONS.md), the [threat model](docs/THREAT_MODEL.md),
[release validation](docs/PYPI_RELEASE.md), and [beta readiness research](docs/BETA_READINESS.md).
CI covers Linux, Windows, and macOS.
The [historical verification benchmark](docs/BENCHMARK_V05.md) and
[99-scenario evidence](docs/QA_99.md) describe their fixtures and test boundaries.

## Contribute

Fork the repository and run `python -m pip install -e ".[dev]"` followed by
`python -m pytest -q`. The [contributing guide](CONTRIBUTING.md) explains how to
report a reproducible verdict or onboarding problem.

Apache License 2.0.
