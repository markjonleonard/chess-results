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
install — and the package has not in fact been installed here. Ad-hoc `python -c` and
`python -m chess_results.cli` invocations therefore need `PYTHONPATH=src`.

Live smoke test against a real tournament (1452107 is the 2026 British Championship, the
event the fixtures come from):

```bash
python -m chess_results.cli standings 1452107
python -m chess_results.cli colours 1452107 --after 6
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

Reproducing round 7 of the 2026 British Championship from rounds 1–6 gives 47 of 52 pairings
exactly right including colours. The five differences are in the bottom two scoregroups;
the untested hypothesis is that bbpPairings implements the 2025 Dutch rules while the event
was paired under an earlier version.
