---
name: release
description: Release chess-results to PyPI -- version bump, git tag, and the Trusted Publishing workflow (TestPyPI rehearsal, PyPI release, verifying an upload). Use when the user asks to release, publish, or cut a new version of chess-results.
---

Published to PyPI as `chess-results`. Both indexes authenticate by **Trusted Publishing**:
GitHub mints a short-lived OIDC token the index exchanges for upload rights, so there is no
API token in repository secrets and none on a laptop, and the upload acts as the repository
rather than as a user. Never add a token; there is nowhere to put one.

- `.github/workflows/publish.yml` — TestPyPI, manual trigger. Rehearse here on a throwaway
  `0.1.0.devN`.
- `.github/workflows/release.yml` — PyPI, on a `v*` tag. Runs the suite first (a tag push
  matches neither of CI's triggers, so without it a release could ship untested code), then
  refuses to upload unless the tag equals the built version, compared after PEP 440
  normalisation. So a forgotten `__version__` bump fails the build rather than shipping.

To release: set `__version__`, commit, then `git tag vX.Y.Z && git push origin vX.Y.Z`.

**The PyPI page links to the release's tag, not to `main`.** The README's links point at
`main` so GitHub stays current; `hatch-fancy-pypi-readme` (see `pyproject.toml`) rewrites
them to `blob/vX.Y.Z/` when the package is built, so PyPI shows docs for the version it
installs. Nothing to do by hand, but two consequences: the tag must be pushed for those
links to resolve, which the release workflow guarantees by running on the tag; and a
TestPyPI rehearsal of `0.1.0.devN` links to a tag that never exists, which is expected.
Check a release's PyPI page links to its own tag.

Each index needs its own trusted publisher, and the two differ in **two** of five fields —
copying one across is the easy mistake:

| | TestPyPI | PyPI |
| --- | --- | --- |
| Project / Owner / Repository | `chess-results` / `markjonleonard` / `chess-results` | same |
| Workflow | `publish.yml` | `release.yml` |
| Environment | `testpypi` | `pypi` |

A project that does not exist yet takes a *pending* publisher, which the first upload
converts into an ordinary one.

**Verifying an upload needs a throwaway venv.** The editable install already satisfies
`chess-results` in the global pyenv, so pip reports "already satisfied" and never contacts
the index — it looks like a pass and tests nothing. From TestPyPI the fallback index is
required too, requests, beautifulsoup4 and requests-cache not being mirrored there:

```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ chess-results
```

Test the sdist as well as the wheel (`--no-binary chess-results`); only that path exercises
building from source.
