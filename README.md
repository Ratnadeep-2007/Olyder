# Olyder

**Verify agent-written code against checks you define.**

Olyder turns an `olyder.json` acceptance specification into a reproducible verdict
and HTML, Markdown, and JSON evidence. Run it after any coding agent or in CI.
Deterministic verification works with Python 3.11+ and uses zero model tokens.
An optional reviewer can assess the observed evidence, and a repair loop can
send failing checks back to a configured builder.

[![CI](https://github.com/Ratnadeep-2007/Olyder/actions/workflows/ci.yml/badge.svg)](https://github.com/Ratnadeep-2007/Olyder/actions/workflows/ci.yml)
[Quick start](#quick-start) · [Integration guide](docs/UNIVERSAL_GUIDE.md) · [Contribute](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

## Quick start

The first PyPI beta, `0.5.0b1`, is a release candidate. Install from the GitHub
source in a Python virtual environment while publication is pending. This
installation route requires Git and network access. Create an environment with
`python -m venv .venv` and activate it with `source .venv/bin/activate` on
macOS/Linux or `.venv\Scripts\Activate.ps1` in PowerShell.

```sh
python -m pip install "git+https://github.com/Ratnadeep-2007/Olyder.git"
olyder demo
olyder demo --fail
```

The demo uses two file checks in a temporary project. The first command exits
`0` and writes a report under `.olyder/demo/pass/`. The second deliberately fails
one assertion, exits `1`, and writes a separate report under `.olyder/demo/fail/`.
Open `report.html` or read `report.json` to see what ran and why the verdict
changed. Both runs work offline and use zero model tokens. If you already have
a reviewed wheel, install it without package-index access using
`python -m pip install --no-index "/path/to/olyder-0.5.0b1-py3-none-any.whl"`.

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
olyder plan
olyder verify
```

Add a check object to the `checks` array to run your existing test suite.
This example assumes pytest is installed in the verification environment.

```json
{"id": "unit-tests", "type": "command", "argv": ["python", "-m", "pytest", "-q"]}
```

Review all configured commands before running `olyder verify --allow-exec`.
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
| Add local or CI verification | `olyder verify` and an `olyder.json` checked into your repository |
| Give an editor the Olyder skill | `olyder setup opencode`, `setup antigravity`, `setup claude`, or `setup codex`. Add `--global` for all projects |
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
