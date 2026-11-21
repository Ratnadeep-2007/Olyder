# Beta readiness research

**Question.** What should a first-time visitor be able to verify in five minutes,
and what evidence should a maintainer require before publishing?

Research was checked on 2026-11-21 against the public repository, official
documentation, and the release candidate at `e51ac79`. OpenCode investigated
first-use and adjacent tools. Antigravity independently investigated acceptance
integrity, process environments, and publication trust. Codex compared both
against the release candidate's actual execution paths.

| Decision | Evidence | Tradeoff |
| --- | --- | --- |
| Lead with a real, credential-free demo | pytest's introduction shows a user-authored assertion and a failure. Pre-commit offers a local run that uses the same checks as its normal workflow. Olyder's public source demo previously required cloning and running from a particular folder. [pytest](https://docs.pytest.org/en/stable/getting-started.html) · [pre-commit](https://pre-commit.com/#quick-start) | Fixed example data is easy to try. The adjacent README recipe is necessary to teach how to verify a user's own project. |
| Protect the harness that determines the verdict | pytest can take its configuration and fixtures from files outside the tests directory. pytest 9 adds TOML configuration filenames. Existing and absent conventional root inputs matter on both pytest 8 and 9. [pytest configuration](https://docs.pytest.org/en/stable/reference/customize.html) · [pytest fixture discovery](https://docs.pytest.org/en/stable/reference/fixtures.html) | Protecting entire standard root configs is predictable. It also keeps packaging edits in protected files outside the builder loop. Use explicit paths for custom and nested acceptance assets. |
| Narrow the environment change to Olyder credentials | Python subprocesses inherit the parent environment by default. Playwright also defaults Chromium's launch environment to its own. Explicit environment mappings let Olyder keep its own tokens in the parent and retain runtime variables. [Python 3.11](https://docs.python.org/3.11/library/subprocess.html#subprocess.run) · [Playwright](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-option-env) | A general allowlist would impose a new compatibility policy for developer tools and CI. Host isolation continues to depend on the execution environment. |
| Keep the current approval-gated release path | The repository already builds and inspects the wheel and sdist. PyPI Trusted Publishing exchanges OIDC identity for short-lived upload credentials. Attestations record the publisher identity and artifact digest. [Olyder release runbook](PYPI_RELEASE.md) · [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) · [PyPI attestations](https://docs.pypi.org/attestations/) | Clean-install evidence is available before the owner configures their publisher and authorizes the public upload. |
| Give contributors a short path to a reproducible issue or contribution | The GitHub Open Source Guides recommend documenting how maintainers work and making participation clear. [Open Source Guides](https://opensource.guide/best-practices/) | README navigation and contributor instructions are measurable improvements. Their effect on stars, forks, and adoption needs observation after publication. |

## What to measure after release

Check public discovery and provenance, a clean installation from PyPI, time from
install to a real verdict, successful setup across supported platforms, and
whether new issues include reproducible evidence. Treat stars and forks as
signals of interest. Track usage through available aggregate release and package
metrics.

## GitHub discovery and Antigravity

Research on 2026-11-21 compared a copyable PR workflow, a Marketplace Action,
and Antigravity plugin packaging. Antigravity's App, CLI, and IDE all support
Olyder's existing skill paths. A short guide with invocation and executable
setup addresses the immediate onboarding gap. [Google Antigravity skills](https://antigravity.google/docs/skills)

The pull-request starter uses the existing CLI and reports, so adopters can
inspect it before copying and can run it without provider credentials. An
independent Antigravity brief reached the same priority and suggested revisiting
Marketplace packaging after stable adoption. GitHub repository search supports
topics, descriptions, and READMEs. Use those surfaces to describe concrete
workflows and measure adoption through successful verification runs and
reproducible issues. No keyword search volumes were established.
[GitHub repository search](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories)

## Follow-up engineering

1. Specify versioned strict validation for built-in checks, with a compatibility
   path for existing specs and registered plugins.
2. Extend protected input declarations for nested or custom test roots and
   verifier dependencies that cannot be inferred safely.
3. Test supported MCP revisions against independent clients before changing
   advertised protocol support. The 2026-07-28 revision has different version
   discovery semantics. [MCP versioning](https://modelcontextprotocol.io/specification/versioning)
