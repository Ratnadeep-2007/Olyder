# Olyder PyPI beta release runbook

## Release status

Candidate distribution: **`olyder`**, version **`0.5.0b1`** (first public beta).
This page describes the release procedure. **Merging the PR does not publish a
package; a PyPI project and GitHub release do not exist until the owner completes
the account setup and explicitly releases the tagged build.**

The existing program/CLI/module name remains `olyder`. The distribution was
previously called `olyder-agent` in `pyproject.toml`; it has not previously
been released to PyPI. The package contents are *beta*, not a production
security sandbox, provider hard spending cap, comprehensive ACP client/TCK,
or a model that independently researches the entire internet.

## What CI verifies before publication

1. Existing unit, integration, ACP read-only server, and Docker checks.
2. Build a single **wheel** and **source distribution** using `python -m build`.
3. Validate `pyproject.toml`, wheel and sdist package name and version,
   `olyder` console-script entry point, bundled `SKILL.md`,
   license and README, and absence of common private key/credential files.
4. Validate long-description metadata with `python -m twine check --strict`.
5. Install the **built wheel** in a brand-new Python environment on
   Ubuntu, Windows, and macOS; smoke `python -m olyder --version`,
   `doctor`, `setup opencode`, and repeat setup without overwriting files.
6. Archive the reviewed distribution files as a CI artifact.

These tests do not establish exhaustive application security, actual paid
agent billing, subscription quota enforcement, or universal agent/IDE support.
The ACP client adapter still lives in a separate experimental draft PR.

## Required action by the PyPI owner

### 1. Create your PyPI account (one time)

Sign up or sign in at https://pypi.org/account/register/ and enable
two-factor authentication. **Do not send a password, one-time code,
recovery code or API key to ChatGPT or commit it to GitHub.**

The URL https://pypi.org/project/olyder/ returned 404 during preparation.
That does **not** reserve the name: PyPI may reject a similar, prohibited,
or already-registered name at the actual publish step. If it cannot be
claimed, stop and choose a distinct name before making a release; never
overwrite someone else's project.

### 2. Create an approval-gated GitHub environment

In https://github.com/Ratnadeep-2007/Olyder/settings/environments:

- Create an environment named exactly `pypi`.
- Enable **Required reviewers** if the repository's GitHub plan permits
  it; designate a trusted maintainer and require review before deployment.
- Do not put passwords or API tokens in repository secrets.
- Treat releases as immutable; do not replace published artifacts or reuse
  version numbers.

### 3. Add a *pending* Trusted Publisher on PyPI

Go to https://pypi.org/manage/account/publishing/ while signed in.
Add a GitHub Actions pending publisher with **exactly** these fields:

| PyPI field | Value |
| --- | --- |
| PyPI project name | `olyder` |
| Owner | `Ratnadeep-2007` |
| Repository | `Olyder` |
| Workflow filename | `release-pypi.yml` |
| Environment name | `pypi` |

The pending publisher will only claim the package name on successful first
upload. The name can still be taken or blocked in the meantime. PyPI's
GitHub OIDC identity matching requires these strings to be exact.
For existing projects, configure the publisher in the project's
**Manage > Publishing** section instead.

Official references:

- https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/
- https://docs.pypi.org/trusted-publishers/using-a-publisher/
- https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/

### 4. Approve and merge the validated release preparation PR

Review the diff and successful checks in the release preparation PR. A
maintainer merges it into `main` only after all CI checks pass.
**Do not merge experimental ACP PR #5 as part of this release.**

### 5. Trigger one intentional pre-release

Once the pending publisher and required GitHub environment are configured,
create a GitHub release at
https://github.com/Ratnadeep-2007/Olyder/releases/new

- Target: `main` at the reviewed release-preparation merge commit.
- Tag: `v0.5.0b1` (create it as part of the release).
- Title: `Olyder 0.5.0 beta 1`.
- Mark **Set as a pre-release**.
- Describe known limitations and say clearly this is experimental.
- Choose **Publish release** only when ready for the public PyPI upload.

Publishing that GitHub prerelease triggers `.github/workflows/release-pypi.yml`,
which verifies that the tag's source is already on `main`, confirms the
tag equals the package version, builds/checks/installs the wheel and sdist,
and then waits for `pypi` environment approval before uploading via
short-lived OIDC. If the pending PyPI publisher is not configured,
publication fails safely; do not disable security checks to bypass it.

### 6. Verify the published release externally

After a confirmed successful upload, verify the project page:
https://pypi.org/project/olyder/

In a fresh clean interpreter, run:

```powershell
python -m pip install olyder
python -m olyder --version
python -m olyder setup --global
python -m olyder doctor
```

For deliberate explicit beta installation, use
`python -m pip install --pre "olyder==0.5.0b1"`. The plain
`pip install olyder` command remains the desired user experience.

Verify that the installed `SKILL.md` contains `description:`, that
`.opencode/skills` and the global directories are discoverable by each
editor after restart, and that no agent/mutating checks execute during setup.

### Special Windows note

An existing Application Control policy blocked `pip.exe` for the user
testing Olyder. **Publishing on PyPI does not remove that local block.**
Try `python -m pip` only if your administrator's policy permits it. If
Python or module execution is also blocked on a managed computer, use
an IT-approved installation channel. Never disable or bypass Application
Control to install Olyder.

## Failure/rollback strategy

PyPI published files and version numbers are immutable. If publication
fails before upload, fix the issue and cut a **new tag/version** only if
the original version has been uploaded; if nothing was published, rerunning
the same release workflow may be possible after resolving configuration.
For a bad published beta, release a fixed `0.5.0b2` or later version,
explain the issue, and yank the bad version in PyPI if appropriate. Do not
silently overwrite previously published distributions.

## Maintainer checklist

- [ ] CI: unit, integration, packaging and installed-wheel smoke green.
- [ ] No accidentally included secrets, credentials, binary caches or local state.
- [ ] Distribution name `olyder` allowed by PyPI when publishing.
- [ ] Owner configured pending Trusted Publisher with exact fields.
- [ ] GitHub `pypi` environment requires human approval when available.
- [ ] Reviewed merge on `main`, tag `v0.5.0b1` matches package metadata.
- [ ] GitHub release explicitly marked pre-release.
- [ ] Upload action completed successfully.
- [ ] Fresh pip install, doctor and editor setup verified.
- [ ] Release notes disclose experimental components and budget/security limits.
