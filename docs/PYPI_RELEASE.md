# Olyder PyPI beta release runbook

## Release status

**Olyder `0.5.0b1` is published.** Install the first public beta with
`python -m pip install "olyder==0.5.0b1"`.
The CLI, Python module, and normalized PyPI name are all `olyder`.
[PyPI release](https://pypi.org/project/olyder/0.5.0b1/) · [GitHub prerelease](https://github.com/Ratnadeep-2007/Olyder/releases/tag/v0.5.0b1)

The procedures below record the first release and describe the maintainer
checks for future builds. Merging a pull request and publishing a release are
separate actions. See [known limitations](KNOWN_LIMITATIONS.md) for beta
boundaries.

## What CI verifies before publication

1. Existing unit, integration, ACP read-only server, and Docker checks.
2. Build a single **wheel** and **source distribution** using `python -m build`.
3. Validate `pyproject.toml`, wheel and sdist package name and version,
   `olyder` console-script entry point, bundled `SKILL.md`,
   license and README, and absence of common private key/credential files.
4. Validate long-description metadata with `python -m twine check --strict`.
5. Install the **built wheel** in a brand-new Python environment on
   Ubuntu, Windows, and macOS; smoke `python -m olyder --version`,
   `doctor`, `setup opencode`, repeat setup, and both offline demo verdicts.
6. Archive the reviewed distribution files as a CI artifact.

These tests do not establish exhaustive application security, actual paid
agent billing, subscription quota enforcement, or universal agent/IDE support.
The ACP client adapter still lives in a separate experimental draft PR.

## Required action by the PyPI owner

### 1. Create your PyPI account (one time)

Sign up or sign in at https://pypi.org/account/register/ and enable
two-factor authentication. **Do not send a password, one-time code,
recovery code or API key to ChatGPT or commit it to GitHub.**

### 2. Create an approval-gated GitHub environment

In https://github.com/Ratnadeep-2007/Olyder/settings/environments:

- Create an environment named exactly `pypi`.
- Enable **Required reviewers** if the repository's GitHub plan permits
  it; designate a trusted maintainer and require review before deployment.
- Do not put passwords or API tokens in repository secrets.
- Treat releases as immutable; do not replace published artifacts or reuse
  version numbers.

### 3. Verify the Trusted Publisher on PyPI

Go to **Manage > Publishing** for the existing `olyder` project.
Confirm that the GitHub Actions publisher matches these fields:

| PyPI field | Value |
| --- | --- |
| PyPI project name | `olyder` |
| Owner | `Ratnadeep-2007` |
| Repository | `Olyder` |
| Workflow filename | `release-pypi.yml` |
| Environment name | `pypi` |

For the first upload, these fields were added as a pending publisher. PyPI
converted it into a project publisher on successful upload. GitHub OIDC
identity matching requires the configured values to match exactly.

Official references:

- https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/
- https://docs.pypi.org/trusted-publishers/using-a-publisher/
- https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/

### 4. Approve and merge the validated release preparation PR

Review the diff and successful checks in the release preparation PR. A
maintainer merges it into `main` only after all CI checks pass.
**Do not merge experimental ACP PR #5 as part of this release.**

### 5. Trigger one intentional pre-release

For a new version, update the package metadata and distribution filename
references in the build and release workflows. Confirm the trusted publisher
and required GitHub environment, then create a GitHub release at
https://github.com/Ratnadeep-2007/Olyder/releases/new

- Target: `main` at the reviewed release-preparation merge commit.
- Create a new tag and title matching the version in the reviewed package.
- Mark **Set as a pre-release**.
- Describe known limitations and say clearly this is experimental.
- Choose **Publish release** only when ready for the public PyPI upload.

Publishing that GitHub prerelease triggers `.github/workflows/release-pypi.yml`,
which verifies that the tag's source is already on `main`, confirms the
tag equals the package version, builds/checks/installs the wheel and sdist,
and then waits for `pypi` environment approval before uploading via
short-lived OIDC.

### 6. Verify the published release externally

After a confirmed successful upload, verify the project page:
https://pypi.org/project/olyder/

In a fresh clean interpreter, run:

```powershell
python -m pip install "olyder==0.5.0b1"
python -m olyder --version
python -m olyder setup --global
python -m olyder doctor
```

For future releases, substitute the new version in the installation command.

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
- [ ] The PyPI project has the Trusted Publisher configured with matching fields.
- [ ] GitHub `pypi` environment requires human approval when available.
- [ ] Reviewed merge on `main`, with a new tag matching package metadata.
- [ ] GitHub release explicitly marked pre-release.
- [ ] Upload action completed successfully.
- [ ] Fresh pip install, doctor and editor setup verified.
- [ ] Release notes disclose experimental components and budget/security limits.
