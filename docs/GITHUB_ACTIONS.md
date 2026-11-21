# Test AI-generated code in GitHub Actions

Use Olyder to turn acceptance criteria for a pull request into a CI verdict.
This starter checks the repository's own files and produces evidence without
an API key, model call, or executable check.

1. Copy [the workflow](../examples/github-actions/olyder.yml) into your
   repository at `.github/workflows/olyder.yml`.
2. Copy [the starter spec](../examples/github-actions/olyder.json) to the root
   of your repository as `olyder.json`. Change the goal and assertion to match
   something meaningful in your project. The sample expects a heading starting
   with `## Install` in `README.md`.
3. Open a pull request. Look for the `acceptance` job in the pull request checks.
   Its workflow summary shows the verdict and check counts. Download the
   `olyder-report` artifact for the HTML, Markdown, and JSON evidence.

The workflow's pinned PyPI install requires the public `0.5.0b1` beta. Before
publication, replace the requirement in the install step with
`git+https://github.com/Ratnadeep-2007/Olyder.git@<full-reviewed-commit-sha>`,
using a commit that is already available on GitHub. For a local trial, install
the candidate wheel and run `olyder verify` against the copied spec.

## Make it a required check

Once the first run succeeds, configure your branch rules to require the
`acceptance` check. A failed or blocked verdict exits `1`. A spec error exits
`2` and may produce only a diagnostic in the job log. The reporting steps run
after a verification failure so you can inspect the evidence without changing
the job's exit result. [GitHub status checks](https://docs.github.com/en/pull-requests/reference/status-checks)

## Add your existing test suite

For a reviewed workflow and trusted test environment, install your project's
test dependencies, add a `command` check such as the one below, and change
the verification step to run `olyder verify --allow-exec` with the same
`--spec` and `--output` arguments.

```json
{"id": "unit-tests", "type": "command", "argv": ["python", "-m", "pytest", "-q"]}
```

The starter uses the `pull_request` event and a read-only repository token.
Keep fork workflows on GitHub-hosted runners with no secrets and treat
PR-controlled commands and test code as executable. Review captured test output
before publishing it as an artifact. When acceptance criteria act as a merge
gate, require review for changes to `olyder.json`, the workflow, and test assets.
[GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use)
