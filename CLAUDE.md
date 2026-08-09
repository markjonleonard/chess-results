# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e ".[dev]"                     # editable install with pytest + ruff

pytest                                      # whole suite (offline; fixtures only)
pytest tests/test_crosstable.py             # one file
pytest -k "bye"                             # one pattern
pytest tests/test_tournament.py::TestStandings::test_scoregroups_are_ordered_high_to_low

ruff check .                                # lint (config in pyproject.toml)
ruff format .                               # formatter is adopted; keep it clean
mypy --strict src/chess_results             # not yet clean; see TODO.md
```

Repository, distribution and import name all agree: `chess-results` / `chess-results` /
`chess_results`. `__init__.py` is the single source of the version — hatch reads
`__version__` from it, so do not add a `version` key to `pyproject.toml`.

The local checkout directory name is incidental — nothing reads it — so it may or may
not match.

`pyproject.toml` sets `pythonpath = ["src", "."]`, so pytest resolves imports without an
install. The package *is* also installed editable into the global pyenv 3.13.3 — the
install is one `.pth` in site-packages holding the single line
`/Users/mark.leonard/repos/personal/chess-results/src`, so `import chess_results` and the
`chess-results` console script both work from any directory and `PYTHONPATH=src` is
redundant. Two consequences worth holding on to:

- It resolves to the **working tree**, not a commit: uncommitted edits are live, and
  checking out another branch silently swaps the code under every project on that
  interpreter. There is no venv isolating this.
- Only metadata changes need a re-run of `pip install -e ".[dev]"` — new or changed
  dependencies, entry points, or a `__version__` bump. Until then `pip show` and
  `importlib.metadata.version` report the stale version while the imported code is current.
  Editing modules under `src/chess_results/` needs nothing.

Live smoke test against a real tournament (1452107 is the 2026 British Championship, the
event the fixtures come from):

```bash
chess-results standings 1452107              # console script, same as python -m chess_results.cli
chess-results colours 1452107 --after 6
```

## Architecture

A three-layer pipeline. Keep the layers separate — the parse layer must stay free of HTTP
so the tests can run offline against saved pages.

| Layer | Module | Responsibility |
| --- | --- | --- |
| Parse | `parse.py` | HTML → dataclasses. Stateless, no network. |
| Assemble | `tournament.py` | Per-round tables → per-player histories. |
| Fetch | `client.py` | HTTP, round auto-detection, cache policy, orchestration. |

`models.py` holds the dataclasses; `trf.py` and `cli.py` are consumers of the assembled
`Tournament`. `cache.py` is policy only.

The two shapes are easy to confuse: **`Pairing`** is one row of a round's table (two
players), **`Play`** is what one player did in one round. `add_round` turns each `Pairing`
into one or two `Play` objects.

## The non-obvious things

These cost real debugging to find. Do not "simplify" them away.

**Byes vanish from superseded rounds.** A round's pairing page lists `bye` and `not paired`
rows only while that round is the current one; once a later round is paired those rows are
*deleted*. A player who took a full-point bye in round 6 then has no round 6 anywhere on the
round pages and scores a point light. The starting-rank crosstable (`art=5`) keeps the whole
record, so `tournament()` fetches it and `add_crosstable` fills any round a player is
missing. This is not a display option — it happens with and without `turdet`. Verify score
changes against the crosstable's published totals; all 108 must agree.

Searched for upstream attribution and found none: chess-results.com has no public issue
tracker or changelog, and the Swiss-Manager manuals do not mention it. So this is observed,
undocumented behaviour — do not go looking for a citation, there isn't one. It is not
Swiss-Manager losing the data, though: the crosstable and the round pages come from the same
upload, and the crosstable still has the byes.

The crosstable is not the only survivor. **`art=40`, linked in the nav bar as "not paired",
lists every player who has missed a round** as a grid of one column per round, marking `*`
not paired, `bye` a bye, `0F` a forfeit. Nothing parses it yet, but it is the most direct
statement of the same facts and is a page rather than a whole crosstable to mine. What it
does *not* do is warn you in advance: a marker appears only for a round that has already
been paired, so it cannot help predict the round you are about to pair. See TODO.md for the
full survey of `art=1`, `art=9` and `art=40`.

**An unpaired round still renders a table.** It contains only the withdrawn players' "not
paired" rows. Round auto-detection therefore requires at least one `PlayKind.GAME`; without
that check the scraper invents rounds and makes the whole active field look withdrawn.

**Parsing is header-driven, never by fixed offsets.** chess-results emits one header row
mixing `<th>` (labelled columns) with `<td>` (the two player-name columns), so `_cells`
reads both. Tournaments switch columns on and off — the starting-rank `No.` columns are
absent from many events. White/black column indices are resolved *relative to the `Result`
column* (`before=i_result` / `after=i_result`); the title is the unlabelled cell immediately
before a name column.

**Players are keyed by name, the crosstable by starting number.** Pairing pages identify
players by name only, on many tournaments. `Tournament.players` is a name-keyed dict;
`add_crosstable` joins through `start_no` taken from the starting-rank list. Two players
sharing a name in one event will collide.

**Floats are inferred**, by comparing the two players' displayed pre-round scores. They are
not published. A pairing-allocated bye counts as a downfloat.

**`lan=1` is mandatory on every request.** The parsers key off English column labels and the
literal words "bye" and "not paired".

**Redirects must be followed.** chess-results 302s the bare domain to a numbered mirror
(S1/S2/S3), so every logical fetch is two HTTP requests. Relevant when counting cache hits.

## Caching

`client.py` asks for a lifetime per page based on how volatile it is: starting rank 1 day,
live or newest round 5 minutes, settled round 30 days. A round is *settled* only once every
game has a result **and** a later round is paired — the newest round never settles, because
a result can be corrected before the next pairing goes out. Settled rounds are recorded in a
JSON sidecar next to the cache so the knowledge survives between runs.

Known caveat, documented in the README: requests-cache fixes expiry at write time, so a
round that settles between runs is fetched once more before it takes the long lifetime.

The library is uncached by default (`ChessResults(cache=True)` opts in); the CLI caches by
default.

## Tests

Fixtures are real saved pages, mostly from the 2026 British Championship caught mid-event,
plus a congress section with a different column layout (it publishes starting-rank
numbers and has half-point byes). Nothing in the suite touches the network.

Two round-6 fixtures exist on purpose: `british2026_champ_r6.html` was captured with six
games still in progress and its bye rows intact, and `british2026_champ_r6_finished.html` is
the completed round with those rows already deleted. The pair is what demonstrates the bye
problem. `british2026_champ_r8_unpaired_only.html` is the "round not yet paired" page.

`conftest.py` offers `british` (full pipeline, crosstable reconciled) and
`british_rounds_only` (round pages alone), so a test can show what reconciliation adds.

To add a fixture, save the page with `curl -sL` (the `-L` matters) and `lan=1`.

## Pairing prediction

`trf.py` writes FIDE TRF(x), which bbpPairings and JaVaFo read; `examples/predict_next_round.py`
shells out to bbpPairings. Two things that have already caused wrong conclusions:

- **Engines emit a set of pairs, not an ordering.** Board numbers come from the arbiter's
  software afterwards. Always compare predicted against actual pairings *as sets* — comparing
  by board position produces a badly misleading match rate.
- **Fixed boards** (`player.fixed_board`, flagged by a `*)` footnote and its legend) pin a
  player to one board all event, usually on access grounds. Presentational only; it never
  changes who plays whom.

- **Withdrawals are the whole error term.** Given the correct field, bbpPairings reproduces
  the 2026 British Championship exactly: rounds 7 and 8 at 51 of 51, round 9 at 50 of 50,
  colours and bye included. Blind — with no withdrawal information, which is what a live
  prediction actually has — the same rounds give 37/51, 44/51 and 42/50. Every single miss
  is a player who had stopped playing and whom the scraper could not see, because the round
  pages delete the evidence. Do not reach for a rules-version or engine-disagreement
  explanation for a mismatch until the field has been checked; that hypothesis was
  entertained once, on a since-retracted "47 of 52" figure that does not reproduce.
  `Tournament.likely_withdrawn` guesses the field from trailing `UNPAIRED` rounds and takes
  those three to 39/51, 49/51 and 44/50. It only works on crosstable-reconciled histories:
  run it against round pages alone and it finds *nobody* for any superseded round, because
  those are exactly the rows chess-results has deleted.

Predictions made mid-round need a result for every unfinished game, and those assumptions
dominate the outcome below the top boards. On 2026-08-08, round 9 predicted from a live
round 8 with ten games filled in as draws got the top 12 boards exactly right, in the
arbiter's own order, but only 29 of 50 overall — five of the ten filler draws were wrong,
and each wrong score moves a player into a different scoregroup. Trust the scoregroups whose
games are settled; say so explicitly about the rest.
