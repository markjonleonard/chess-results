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
mypy --strict src/chess_results             # clean, and CI enforces it — keep it that way
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
not paired, `bye` a bye, `0F` a forfeit. `parse_not_paired` reads it. It is the most direct
statement of the same facts and is a page rather than a whole crosstable to mine, but it
does not replace the crosstable, for two reasons:

- **A requested bye is indistinguishable from an absence.** Only a *pairing-allocated*
  (full-point) bye prints `bye`; a requested half-point bye prints `*`, exactly as a
  withdrawal does. Verified both ways against the crosstables — every one of Frome's round 1
  half-point byes appears as `*`, and every British `bye` marker is a full point. Since
  `likely_withdrawn` deliberately does not treat a requested bye as a signal, the marker is
  consulted only for a round with no play at all — a round page or the crosstable always
  wins where it has spoken, which is why Frome's twelve half-point byes raise no false
  alarm.
- **A forfeit lists only the player who defaulted.** The opponent takes the point without
  appearing at all.

It also does not warn you in advance: a marker appears only for a round that has already
been paired, so it cannot help predict the round you are about to pair. And it ignores
`&rd=` — there is one page, always current, so no mid-event state can be recovered
afterwards. See TODO.md for the full survey of `art=1`, `art=9` and `art=40`.

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

Several rounds have two fixtures on purpose, because the same round looks different
depending on when it was caught. `_r6.html` and `_r7.html` are mid-round captures — six
games still in progress in one, a paired-but-unplayed round in the other — and their
`_r6_finished.html` / `_r7_finished.html` counterparts are the same rounds played out.
The r6 pair is what demonstrates the bye problem: the mid-round page still has its bye
rows, the finished one has had them deleted. `_r8_unpaired_only.html` is the "round not yet
paired" page, and `_r8.html` is round 8 played.

`_r9.html` and `_crosstable_final.html` were captured on 2026-08-09 for the two defaulted
games (see `test_forfeit.py`); round 9 was still being played, so **there is no
complete-tournament fixture** — rounds 1-8 are as far as a fully-decided event goes.
Round 9's page keeps its "not paired" rows, being the current round at capture and the last
round of the event, which makes it the only round page in the set that still lists the
absent players.

`conftest.py` offers `british` (full pipeline, crosstable reconciled, mid-event — what most
tests want), `british_rounds_only` (round pages alone, so a test can show what
reconciliation adds), `british_played_out` (rounds 1-8 with every game decided, needed by
anything asserting on real `to_trf` output, which refuses unfinished games) and
`frome_round_one` (a congress section with a different column layout and twelve half-point
byes; built from its round page alone — feeding the Frome crosstable to `parse_starting_rank`
yields comma-less names that will not join).

`british2026_champ_notpaired_final.html` and `frome2026_open_notpaired.html` are `art=40`
captures, both taken after their events finished. That page ignores `&rd=`, so a mid-event
capture of it cannot be made after the fact — there is only ever the current one. The two
together are what prove the requested-bye limitation above: Frome has half-point byes and
the British does not.

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
  those are exactly the rows chess-results has deleted — **or** pass it `not_paired=`, the
  parsed `art=40` page, which restores exactly the crosstable's answer at every round of the
  2026 British for one request. It buys nothing on top of a crosstable, by construction.

Predictions made mid-round need a result for every unfinished game, and those assumptions
dominate the outcome below the top boards. On 2026-08-08, round 9 predicted from a live
round 8 with ten games filled in as draws got the top 12 boards exactly right, in the
arbiter's own order, but only 29 of 50 overall — five of the ten filler draws were wrong,
and each wrong score moves a player into a different scoregroup. Trust the scoregroups whose
games are settled; say so explicitly about the rest.
