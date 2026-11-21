# Contributing to Olyder

## Get a local baseline

Fork and clone the project, then use a Python 3.11+ virtual environment.

```sh
python -m pip install -e ".[dev]"
python -m pytest -q
olyder demo
```

The demo reports are under `.olyder/demo/pass/`. For a project with an executable
check, see [the cart-pricing example](examples/demo-app/). Browser, Docker, and
ACP integration coverage has separate runtime prerequisites.

## Propose an improvement

Use the **Verification or setup problem** issue form for a reproducible bug.
Good first contributions include a small model-free fixture, a verified
[Antigravity setup](docs/ANTIGRAVITY.md) example for another platform, and an
improvement to the [GitHub Actions starter](docs/GITHUB_ACTIONS.md).
For a verdict problem, include the Olyder version, operating system, Python
version, and a small acceptance spec and report with private data removed.

Keep pull requests narrow. Include a regression check for behavior changes and
give the exact commands you ran. Keep new scenario runners opt-in for execution
and preserve the existing acceptance matrix.

Use GitHub's private reporting channel for security bugs when enabled. Keep real
credentials, private repository data, and sensitive reports out of issues and
pull requests.
