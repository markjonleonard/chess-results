---
name: lint-docs
description: Lint chess-results' markdown documentation with Vale (a style/spelling checker), matching CI's docs job -- one-time setup (vale sync, dictionaries) and the run command. Use when editing README.md, DESIGN.md, CLAUDE.md, or other tracked markdown, especially before committing doc changes.
---

The documentation is linted too, by [Vale](https://vale.sh), in CI's `docs` job.
Two things it needs are fetched rather than committed — style packages, which
`vale sync` restores from `.vale.ini`, and the en_GB Hunspell dictionary, which
is LGPL and does not belong vendored into an MIT repository:

```bash
brew install vale
vale sync
mkdir -p .vale/styles/config/dictionaries
for f in en_GB.aff en_GB.dic; do
  curl -sSfL -o ".vale/styles/config/dictionaries/$f" \
    "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/en/$f"
done
vale --minAlertLevel=error $(git ls-files '*.md')
```

Lint the markdown **git tracks**, as CI does, rather than `vale .` — otherwise it
reads build artefacts, Vale's own downloaded documentation and any personal notes
in the checkout.

`British.Spelling` replaces Vale's bundled en_US check, so `color`, `behavior`
and `recognized` are errors here. Add real jargon to
`.vale/styles/config/vocabularies/chess-results/accept.txt`, which takes regular
expressions, rather than weakening the rule. `write-good.E-Prime` is off because
it bans the verb "to be"; `Passive` is off because this prose describes what a
website does to us. Errors fail CI, warnings do not — a hedge is sometimes the
honest word.
