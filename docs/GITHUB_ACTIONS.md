# Test AI-generated code in GitHub Actions

Use Olyder to report the verdict for a pull request's acceptance criteria.
Start with a file check, then connect the tests your project already runs.

## Call the reusable workflow

Copy the [starter spec](../examples/github-actions/olyder.json) to your
repository root as `olyder.json` and replace its sample assertion with a
condition your project must meet. In `.github/workflows/olyder.yml`, add:

```yaml
name: Olyder acceptance
on: pull_request
permissions:
  contents: read
jobs:
  acceptance:
    uses: Ratnadeep-2007/Olyder/.github/workflows/verify.yml@main
```

Replace `main` with a reviewed full commit SHA for a stable reference. By
default the workflow verifies `olyder.json` with executable checks disabled.
Use `with.spec-path` for a spec elsewhere in the repository and
`with.artifact-name` for a distinct report name if calling the workflow more
than once in a run. No API key or model call is required.

The summary records the checked-out commit, spec SHA-256, verdict, and up
to ten failing or blocked check IDs. A pull request event normally checks out
GitHub's test merge commit. Download the `olyder-report` artifact for the
HTML, Markdown, and JSON reports. A spec error leaves a diagnostic in the
verification step log. [Reusing workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)

## Use a standalone workflow

Use this option to customize the runner or install project dependencies in the
same job before verifying. The starter checks files with no API key, model
call, or executable check.

1. Copy [the workflow](../examples/github-actions/olyder.yml) into your
   repository at `.github/workflows/olyder.yml`.
2. Copy [the starter spec](../examples/github-actions/olyder.json) to the root
   of your repository as `olyder.json`. Change the goal and assertion to match
   something meaningful in your project. The sample expects a heading starting
   with `## Install` in `README.md`.
3. Open a pull request. Look for the `acceptance` job in the pull request checks.
   Its workflow summary shows the verdict and check counts. Download the
   `olyder-report` artifact for the HTML, Markdown, and JSON evidence.

Both workflows install `olyder==0.5.0b2` from PyPI. For a local trial,
install the same version and run `olyder verify` against your spec.

## Make it a required check

Once the first run succeeds, configure your branch rules to require the
Olyder job as named in your pull request checks. A failed or blocked verdict
exits `1`. A spec error exits `2`. If there is no report, the summary
directs you to the job log. The reporting steps run after a verification
failure so you can inspect the evidence without changing the job's exit result.
[GitHub status checks](https://docs.github.com/en/pull-requests/reference/status-checks)

## Add your existing test suite

For a reviewed workflow and trusted test environment, install your project's
test dependencies, add a `command` check such as the one below, and change
the verification step to run `olyder verify --allow-exec` with the same
`--spec` and `--output` arguments.

```json
{"id": "unit-tests", "type": "command", "argv": ["python", "-m", "pytest", "-q"]}
```

The starter uses the `pull_request` event and a read-only repository token.
For self-contained tests, such as the [cart-pricing example](../examples/demo-app/),
the reusable workflow accepts `with.allow-exec: true` after you review the
configured commands. It runs in a separate Ubuntu job with Python 3.13 and
Olyder. Use the standalone workflow or your existing CI job when tests need
additional setup.

Keep fork workflows on GitHub-hosted runners with no secrets and treat
PR-controlled commands and test code as executable. Review captured test output
before publishing it as an artifact. When acceptance criteria act as a merge
gate, require review for changes to `olyder.json`, the workflow, and test assets.
[GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use)
