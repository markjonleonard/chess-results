# TODO

Open work on chess-results, roughly in the order it is worth doing.

## Before this goes anywhere

- [ ] **Publish to PyPI as `chess-results`.** Still free as at 2026-08-10, on both
      normalisations. Rehearsing on TestPyPI first, via
      `.github/workflows/publish.yml` — TestPyPI only by design, so there is no path to
      the real index until an upload has been watched working.

      **Trusted Publishing, not an API token.** GitHub mints a short-lived OIDC token
      the index exchanges for upload rights: nothing in repository secrets, nothing on
      a laptop, and the upload acts as the repository rather than as a user — which
      also sidesteps this machine defaulting to the wrong GitHub account.

      **The TestPyPI rehearsal succeeded on 2026-08-10**, run 31385337061, uploading
      `0.1.0.dev1`. Both install paths were then verified from the index in clean
      venvs — the wheel, and the sdist via `--no-binary`, which is the one that
      exercises building from source. The console script lands on `PATH`, the import
      works, `py.typed` ships, and the three runtime dependencies resolve while the
      `dev` extras correctly do not.

      Beware verifying this in the global pyenv: the editable install satisfies
      `chess-results` already, so pip reports "already satisfied" and never contacts
      the index at all. It looks like a pass and tests nothing. Use a throwaway venv:

          pip install --index-url https://test.pypi.org/simple/ \
                      --extra-index-url https://pypi.org/simple/ chess-results

      The fallback index is required — requests, beautifulsoup4 and requests-cache are
      not mirrored on TestPyPI.

      **What is left is the real index**, and it is blocked on one thing needing a
      login: registering a **pending** publisher on pypi.org. The project does not
      exist there, so there is nothing to attach an ordinary publisher to; the first
      upload converts it. Project `chess-results`, owner `markjonleonard`, repo
      `chess-results`, workflow `release.yml`, environment `pypi`. All five must match
      or the exchange is refused — and note two differ from the TestPyPI publisher
      already registered, which is the easy mistake.

      Releasing is then `git tag v0.1.0 && git push origin v0.1.0`.
      `.github/workflows/release.yml` fires on `v*` rather than a button, so a release
      is tied to one commit rather than to whatever `main` happens to be. It runs the
      suite first — a tag push matches neither of CI's triggers, so without that a
      release could ship code nothing had run against — then refuses to upload unless
      the tag matches the built version, compared after PEP 440 normalisation.

      The metadata is clean: `twine check --strict` passes on both artifacts, and the
      licence is the SPDX `License-Expression: MIT` of PEP 639 rather than the
      deprecated classifiers. Both workflows run that same `--strict` check before
      uploading, so a fault fails the build instead of burning a version number.
