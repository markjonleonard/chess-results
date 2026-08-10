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
missing. This is not a display option — it happens with and without `turdet`. Verifying score
changes against the crosstable's published totals is no longer a manual step:
`check_published_totals` requires the cells we read from a row to sum to the total that row
publishes, and `tournament()` runs it. All 108 agree, and always have.

**Which column holds that total is not fixed, and `TB1` is not a safe answer.** Where an
event prints a `Pts.` column, that is the score and `TB1` is a real tiebreak — Arad 2026's
is a rating, so reading it gave the top seed a total of 2369 and reported 208 of its 209
players as disagreeing with themselves. The British and Frome print no `Pts.` at all and
their `TB1` *is* the score, which is what made the rule look general. `parse_published_totals`
therefore prefers `Pts.`, falls back to `TB1`, and then **checks what it got**: no score can
exceed the rounds played, so a column that breaks that is refused and the function returns
`{}`. Reading no totals is a safe "nothing to check against"; reading the wrong ones fails
every player in the event and buries a genuine disagreement.

Where both views *do* have a round, `add_crosstable` compares them and records any
contradiction in `Tournament.disagreements`; the CLI prints those to stderr. Nothing has
ever tripped it — the two come from the same upload — so treat a hit as a parser bug, not as
chess-results being inconsistent. Note that one view holding a value the other lacks is
deliberately not a contradiction: the crosstable is often the fresher capture, and a round
page carries no result until the game finishes.

Searched for upstream attribution and found none: [chess-results.com](https://chess-results.com) has no public
issue tracker or changelog, and the [Swiss-Manager](https://swiss-manager.at) manuals do not mention it. So this is observed,
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
been paired, so it cannot help predict the round you are about to pair. **This was
checked against a live event on 2026-08-10** — tournament 1473782, caught with round 2
half-played and round 3 unpaired — and the page carried a column for all seven rounds
with a marker in round 1 only. It is observation, not inference; the `jeddah2026_*`
fixtures are that capture and cannot be regenerated, because the page ignores `&rd=`
and there is only ever the current one.

The other two views were surveyed the same way, and neither helps: **`art=1`**, the
ranking list, keeps a withdrawn player in place with their frozen score and carries no
marker of any kind (note it prints scores with a decimal comma). **`art=9`**, player
info, needs `&snr=<starting number>` and renders an empty shell without one; it does
show a missed round explicitly, as a `not paired` row with opponent SNo `-2`, but that
is one request per player — 108 for a field — to learn what one crosstable already says.

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

A `Play` recovered from the crosstable therefore has no float: the crosstable prints no
pre-round score, so `points_before` is `None` and `_floats` cannot run. **This costs
nothing, and the reason is worth keeping so nobody "fixes" it.** `add_crosstable` fills
only rounds already fetched (`if entry.round not in self.rounds`), so it never introduces a
whole round — it fills one player's gap inside a round we have. The only rows chess-results
deletes from a round page are byes and "not paired"; a game row is never removed. So a
recovered play is always one of those two, and both are already right: a pairing bye takes
`"D"`, and an unpaired player takes nothing, having floated nowhere. Measured across every
fixture, the number of recovered *games* is zero.

The one way to reach a recovered game is a player whose name differs between the starting
rank and the round pages — the join is by `start_no`, so the crosstable still matches them.
That yields games with no float, but it also yields **two players for one person** and a
field one larger than it should be, which is the name-keying hazard below wearing a
different hat. Fix that, not the float. Note also that `float_direction` has a single
consumer, the `Floats` column of `colours`; it never reaches the TRF, so it cannot affect a
prediction — engines recompute floats themselves.

**`lan=1` is mandatory on every request.** The parsers key off English column labels and the
literal words "bye" and "not paired".

**So is `zeilen`, and this one fails silently.** chess-results paginates a long list at 150
rows, and the truncated page announces itself nowhere a parser can reach — no marker in the
table, no count, nothing. Arad 2026 has 209 players and read as a complete 150-player
tournament: every score, float and prediction drawn from two thirds of the field, and not
one error raised. `client._query` puts `zeilen=99999` on every
request, which is chess-results' own "show all" value. Nothing downstream can detect the
truncation, so it has to be prevented at the request. The British has 108 players, which is
why this survived so long.

**Rating columns vary too.** An event rated on one list prints `Rtg`; one rated nationally
and internationally at once prints `RtgI` and `RtgN` and no `Rtg`, which left every rating
`None` — silently, an unrated player being a legitimate thing for a field to contain.
`_RATING_LABELS` tries `Rtg`, then `RtgI`, then `RtgN`.

**Redirects must be followed.** chess-results 302s the bare domain to a numbered mirror
(S1/S2/S3), so every logical fetch is two HTTP requests. Relevant when counting cache hits.

## Caching

`client.py` asks for a lifetime per page based on how volatile it is: starting rank 1 day,
live or newest round 5 minutes, settled round 30 days. A round is *settled* only once every
game has a result **and** a later round is paired — the newest round never settles, because
a result can be corrected before the next pairing goes out. Settled rounds are recorded in a
JSON sidecar next to the cache so the knowledge survives between runs.

**The crosstable is cached hard too, and replaced rather than expired.** It used to take
the live 5-minute lifetime, flat, on the reasoning that it holds live results — but we never
read results from it, the round page being the authority. What we read is the byes and
absences that round pages delete once a later round is paired, and those never change again.
So it is fetched with `SETTLED_TTL` and `refresh=True` is passed when
`crosstable_is_stale()` says the cached copy will not do, which is the only way round
[requests-cache](https://requests-cache.readthedocs.io) fixing expiry at write time. Two things make it stale:

- **It covers fewer rounds than we hold.** A copy fetched before round 8 existed cannot
  supply round 8's bye, and `add_crosstable` fills only rounds we already have. This is the
  case that matters, and `CrosstableCoverage` (a second JSON sidecar) is what remembers it.
- **The newest round is still being played.** Nothing we *need* changes while results
  arrive, but `add_crosstable` also compares the two views, and against a stale copy that
  comparison would report results the crosstable had not caught yet — turning the
  disagreement tripwire into noise.

Net effect: a finished tournament fetches the crosstable once and then never again; a live
one behaves exactly as before. Do not "simplify" this back to a flat TTL.

**requests-cache fixes expiry at write time**, which shapes both of the above. A round
cached while live keeps the 5-minute lifetime even once `round_ttl` starts asking for 30
days, so it used to be refetched on the old schedule purely to be rewritten. There are two
ways round it and they are not interchangeable: `_extend_cached_lifetime` rewrites the
stored entry in place and costs nothing, which is what a settled round gets; `refresh=True`
replaces the entry with a fresh fetch, which is what the crosstable needs because its
content, not merely its expiry, has gone out of date. Using refresh for the round pages
would spend the very request the fix exists to avoid.

The library is uncached by default (`ChessResults(cache=True)` opts in); the CLI caches by
default.

## CI

`.github/workflows/ci.yml`, on push to `main`, every pull request and `workflow_dispatch`.
`lint` runs `ruff check`, `ruff format --check` and `mypy --strict` on 3.13; `test` runs
`pytest` across 3.10-3.13 with `fail-fast: false`. No secrets and no network allowance --
the suite is fixtures only.

**The dev extra is unpinned on purpose, so expect CI to break without a commit.**
`ruff>=0.5` and `mypy>=1.8` mean CI resolves to the newest release every run, and a new
rule or a changed default can red the badge when nothing in the tree has changed. That is
the trade for not chasing pins. It has happened once already: local ruff was 0.15.12, where
formatting Python blocks inside Markdown is preview-gated; CI got 0.16.2, where it is on by
default, and it reflowed the aligned trailing comments in the README and DESIGN examples.
Hence `exclude = ["*.md"]` under `[tool.ruff.format]`.

So when CI fails and the diff looks innocent, **check the tool version CI installed against
the local one before suspecting the commit**, and reproduce by installing that exact version
rather than guessing -- each guess otherwise costs a push. Note `lint` runs its steps in
order, so a formatting failure means `mypy` never ran at all.

**3.10 is in the matrix because `requires-python` and the classifiers advertise it**, not
because anything needs it: every module carries `from __future__ import annotations` and
there is no 3.11+ stdlib use. Raising the floor would drop a support claim without
simplifying any code. If that claim is ever dropped, change `requires-python`, the
classifiers and the matrix together.

## Releasing

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

## Tests

Fixtures are real saved pages, mostly from the 2026 British Championship caught mid-event,
plus a congress section with a different column layout (it publishes starting-rank
numbers and has half-point byes). Nothing in the suite touches the network.

Several rounds have two fixtures on purpose, because the same round looks different
depending on when it was caught. `_r6_midround.html` and `_r7_midround.html` are the earlier
captures — six games still in progress in one, a paired-but-unplayed round in the other —
and their `_r6_finished.html` / `_r7_finished.html` counterparts are the same rounds played
out. The r6 pair is what demonstrates the bye problem: the mid-round page still has its bye
rows, the finished one has had them deleted.

**Neither capture holds the plain `_r6.html` name, deliberately.** Which one a test wants is
the whole point of the pair, so there is no default to fall into: ask `conftest._round_fixture(rnd,
played_out=...)` for the name rather than building `f"..._r{rnd}.html"`, which is what the
old naming quietly encouraged. `_r8_unpaired_only.html` is the "round not yet paired" page,
and `_r8.html` is round 8 played.

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

The `jeddah2026_*` set is the exception to "taken after their events finished", and the
reason it exists: tournament 1473782 caught mid-round on 2026-08-10, with round 1
complete, round 2 paired and 9 of 16 games played, and round 3 not yet paired. That is
the only state in which the "does it warn in advance?" question can be asked, and it
cannot be recreated — treat these six files as irreplaceable. It is also a smaller field
than the other two (32 players, 7 rounds) with forfeits in round 1.

The `arad2026_a_*` set is a third organiser again (19th Arad Open, Romania, 209 players,
9 rounds, completed) and exists for the column variations it exposed: `RtgI`/`RtgN` instead
of `Rtg`, and a `Pts.` column alongside genuine `TB1`-`TB5` tiebreaks.
`arad2026_a_startingrank_paginated.html` is deliberately the *truncated* 150-row capture,
kept so a test can show what the default page looks like; every other Arad fixture is the
full `zeilen=99999` page.

`cnyt2026_g14_*` is a **team** event (Chinese National Youth Team Championship 2026 G14,
1472122, round 1 paired and unplayed). Its round page pairs teams and names no players, so
`parse_pairings` reads nothing — safe, but indistinguishable from an event that has not
started, which is why `is_team_pairings` exists and `tournament()` raises
`TeamTournamentError` rather than returning an empty event. Note `cnyt2026_g14_boards_r1.html`
(`art=3`) opens with a `Bo.` column, so `has_pairings` says True and only parsing finds out.

To add a fixture, save the page with `curl -sL` (the `-L` matters), `lan=1` and
`zeilen=99999`. Leave any of the three off and you get a redirect page, a German one, or a
silently truncated one.

## Pairing prediction

`trf.py` writes FIDE [TRF(x)](https://handbook.fide.com/files/handbook/C04Annex2_TRF16.pdf), which [bbpPairings](https://github.com/BieremaBoyzProgramming/bbpPairings) and [JaVaFo](https://www.rrweb.org/javafo/JaVaFo.htm) read; `examples/predict_next_round.py`
shells out to bbpPairings. `bbpPairings.exe --dutch <file> -c` is a check mode that parses a
whole tournament and lists discrepancies — use it to verify the format, not just to pair.

**bbpPairings recomputes every player's score from their results and refuses the file if the
total disagrees.** That makes `bye_value` a correctness matter, not a display option: the
crosstable prints every pairing-allocated bye as a full point whatever the event awards, so
a bye recovered from it is rescored to `Tournament.bye_value`, and `to_trf` declares a
non-standard value as a `BBU` line. Get either half wrong and the engine rejects the file
outright.

Two more things that have already caused wrong conclusions:

- **Engines emit a set of pairs, not an ordering.** Board numbers come from the arbiter's
  software afterwards. Always compare predicted against actual pairings *as sets* — comparing
  by board position produces a badly misleading match rate.
- **Fixed boards** (`player.fixed_board`, flagged by a `*)` footnote and its legend) pin a
  player to one board, usually on access grounds. Presentational only; it never changes who
  plays whom. *Which* board is never published, so `fixed_board_number` guesses it from the
  longest unbroken run of one board number — and note the pin need not start at round 1:
  Hebden played 23, 18 and 1 before settling on 14 from round 4.

- **Withdrawals are the whole error term, from round 3 on.** Given the correct field,
  bbpPairings reproduces the 2026 British Championship exactly: rounds 7 and 8 at 51 of 51,
  round 9 at 50 of 50, colours and bye included, and the checker replays rounds 1 and 3-8
  from the finished file without a single difference. **Round 2 is the one exception**, and
  it is not our data: with the correct field it still differs on six boards, all inside the
  42-player group on zero after round 1, and the encoding of a late entrant's missing round
  makes no difference to it (`Z`, blank and `-` all give the same pairing). A group that
  large and that flat admits many legal pairings, and Swiss-Manager and bbpPairings choose
  differently. Expect it on any round 2. Four explanations were tested and all are dead:
  not the field (supplying exactly the two who missed round 2 gives the *best* result, 47
  of 53, against 37 for neither and 33 for either alone); not the encoding of a late
  entrant's missing round, as above; not colours (all 47 agreed boards agree on colour
  too); and not same-federation avoidance (24 of the published 53 boards are between
  players of one federation). What it is, is a six-board cyclic shift confined to that
  scoregroup, the published pairing behaving as though the split fell one place earlier
  than bbpPairings puts it. The checker lists the difference without calling the
  published pairing illegal, and exits 0, so both are presumably legal.
  Blind — with no withdrawal information, which is what a live
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
