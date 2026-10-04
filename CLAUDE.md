# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Layout

`src/chess_results/` is the package (see Architecture below); `tests/` is fixtures-only
pytest, one file per module plus cross-cutting concerns (`test_forfeit.py`,
`test_not_paired.py`, `test_unreadable_tournaments.py`); `examples/` holds
`predict_next_round.py`, the bbpPairings integration point (see Pairing prediction below).
`README.md` is the short overview and `USAGE.md` the full guide to every command, option and
Python call. `DESIGN.md` and `PERSONAL-NOTES.md` are working notes for the human maintainer, not
generated or read by any code.

## Commands

```bash
pip install -e ".[dev]"                     # editable install with pytest + ruff

pytest                                      # whole suite (offline; fixtures only)
pytest tests/test_crosstable.py             # one file
pytest -k "bye"                             # one pattern
pytest tests/test_tournament.py::TestStandings::test_scoregroups_are_ordered_high_to_low

ruff check .                                # lint (config in pyproject.toml)
ruff format .                               # formatter is adopted; keep it clean
mypy --strict src/chess_results examples    # clean, and CI enforces it — keep it that way
```

Repository, distribution and import name all agree: `chess-results` / `chess-results` /
`chess_results`. `__init__.py` is the single source of the version — hatch reads
`__version__` from it, so do not add a `version` key to `pyproject.toml`.

The README is also PyPI's long description, so its links are absolute and point at
`main`; at build time `hatch-fancy-pypi-readme` rewrites them to the release's
`blob/vX.Y.Z/` tag, so PyPI describes the version it installs. `USAGE.md` never reaches
PyPI, so its links are relative and stay within whichever version is being read.

The local checkout directory name is incidental: nothing reads it, so it may or may
not match.

`pyproject.toml` sets `pythonpath = ["src", "."]`, so pytest resolves imports without an
install. The package *is* also installed editable into the global pyenv 3.13.3 — the
install is one `.pth` in site-packages holding the single line
`/Users/mark.leonard/repos/personal/chess-results/src`, so `import chess_results` and the
`chess-results` console script both work from any directory and `PYTHONPATH=src` is
redundant. Two consequences worth holding on to:

- It resolves to the **working tree**, not a commit: uncommitted edits are live, and
  checking out another branch silently swaps the code under every project on that
  interpreter. No venv isolates this.
- Only metadata changes need a re-run of `pip install -e ".[dev]"` — new or changed
  dependencies, entry points, or a `__version__` bump. Until then `pip show` and
  `importlib.metadata.version` report the stale version while the imported code is current.
  Editing modules under `src/chess_results/` needs nothing.

Live smoke test against a real tournament (1452107 is the 2026 British Championship, the
event the fixtures come from):

```bash
chess-results standings 1452107              # console script, same as python -m chess_results.cli
chess-results colours 1452107 --after 6
chess-results pairing-sheet 1452107 --after 8 # the printable sheet
```

`--json` is a common option (in `_shared`, so it parses either side of the subcommand) and
every command honours it; each builds its JSON from the same assembled objects as its table.
The JSON never clips a name, and a list report carries `total` and `truncated` so `--limit`
cannot pass for the whole. The full command set is `players`, `standings`, `pairings`, `pairing-sheet`, `colours`
(`colors` accepted as a synonym), `history`, `unfinished`, `dump` (JSON export), `sections`
and `search`. All but `search` take a tournament number, and all but `dump`, `players`,
`sections` and `search` an `--after N` round selector; see
USAGE.md for the complete option table (`--rounds`, `--bye-value`, `--delay`, `--no-cache`,
`--limit`, `--name-width`).

## Architecture

A three-layer pipeline. Keep the layers separate — the parse layer must stay free of HTTP
so the tests can run offline against saved pages.

| Layer | Module | Responsibility |
| --- | --- | --- |
| Parse | `parse.py` | HTML → dataclasses. Stateless, no network. |
| Assemble | `tournament.py` | Per-round tables → per-player histories. |
| Fetch | `client.py` | HTTP, round auto-detection, cache policy, orchestration. |

`models.py` holds the dataclasses; `trf.py`, `sheet.py` and `cli.py` are consumers of the
assembled `Tournament`. `cache.py` is policy only.

`sheet.py` renders a round as fixed-width text for a printer, and is the only module whose
audience is a player at a noticeboard rather than a program. Two consequences that look
like over-engineering and are not:

- **It assigns board numbers rather than enumerating them.** An engine emits a set of
  pairs and no ordering, so `assign_boards` sorts pairs by their better player's position
  in `ranking_order` — top scoregroup on board 1. `sheet_from_round`, by contrast, keeps
  the *published* numbers, which are the arbiter's own and beat any convention.
- **It places fixed boards rather than footnoting them.** A pin is usually an access
  requirement, so `fixed_board_number` wins over the ranking and the pair is moved to that
  board. What cannot be honoured becomes a `PairingSheet.warnings` entry printed on the
  sheet — never an exception, because a sheet an arbiter corrects by hand beats no sheet
  five minutes before a round.
- **The players not playing come from the field, not the page.** `sheet_from_round`
  builds the bye and "not paired" rows from `Player.plays`, not from `Tournament.rounds`,
  so a page that leaves a player out still yields the whole round. A test that compares
  the sheet against `Tournament.rounds` asserts whatever the page said against itself;
  assert against the field instead.
- **The three kinds of non-game are a point apart** and must not print alike; see
  `NOT_PLAYING_TEXT`. Frome's Standard section has a full-point bye among half-point ones,
  which is the fixture that shows it.

Note `fixed_board_number` reads boards off plays that pass `counts_for_colour`, so a
synthetic `Play` with no `colour` yields `None` and any test built from one will silently
find no pin.

`render` keeps the result column off by default while the CLI turns it on. That split is
deliberate: the module is a primitive and holds no view, the command holds the view.

`congress.py` holds several `Tournament`s as one event and is **the one type not read
off a page**: chess-results publishes nothing that groups the sections of a congress, so
the grouping and the section names come from the caller. It offers no merged `players`
dict on purpose, because merging name-keyed sections would silently drop one of two
players sharing a name. `find()` returns every match with its section instead. Note this
guards a *rare* case: Frome 2026's 191 players across five sections contain no repeated
name, and the ten surnames that span sections all differ in first name, because
"Surname, Forename" is what keeps families apart. Do not restate it as a likely one.
`Tournament.rows()` / `Congress.rows()` are the flat one-record-per-player-per-round
export; note `score` scores an `UNPAIRED` round 0, which callers must read against
`kind` rather than sum blindly.

The two shapes are easy to confuse: **`Pairing`** is one row of a round's table (two
players), **`Play`** is what one player did in one round. `add_round` turns each `Pairing`
into one or two `Play` objects.

## Search and sections

`ChessResults.search` and `.sections` read chess-results' tournament database
(`TurnierSuche.aspx`), not a tournament, and differ from every other fetch in four ways.

- **It is a form post.** The page must be fetched first for its view state and posted back
  with it, so a search is two requests, and neither is cached: a cache does not store a
  post, and the form is fetched with `expire_after=0` so stale view state is never replayed.
- **The site's names are not the tournament's names.** It cuts them at 50 characters,
  silently, so a congress title loses its section label off the end (without a fix all of
  Milton Keynes 2026's sections look the same); and it drops the space where a name had a line
  break, so Hull 4NCL 2024's rows read `2024Under 1500` and every label came out glued to the
  year. `parse_search_results` sets `SearchResult.name_inexact` for a name of 49 or more
  characters or one with a run-together word (which also fires on `McShane`, costing one
  request), and `sections()` reads the real name from the starting-rank page for those alone.
  An all-capitals run-together such as `2024OPEN` is not detected.
- **The result table sits inside layout tables** whose rows would repeat it, so the parser
  takes only a table with no table nested in it.
- **The entrant count (`n`) comes with the row**, so `sections()` needs no tournament page.
- **A bad page is retried once, then `SearchError`.** The site has returned a non-result page
  with a success status that went away on the next try; urllib3's retry does not see it and does
  not cover POST. The CLI exits 1 for it, against 2 for a tournament it cannot read.

`sections()` groups by inference: same organiser (director, then the first two words of the
name, when it is empty) and the same start date or the same end date. Either, because Hull
4NCL 2026's lower sections start a day after its Open and all end together. `sections.py` holds that and the
label rule, is pure, and its limits are written at the top of that module and in USAGE.md.

## The non-obvious things

These cost real debugging to find. Do not "simplify" them away.

**A published round's bye rows are one cell short.** A round's pairing page lists its games,
then a row for each player with no game: `bye`, or `not paired` with any points a requested
bye earned. Once the round's games are published the table gains a trailing `PGN` column,
and those rows are not given its cell, so `parse_pairings` pads a row exactly one cell short
when `PGN` is what it lacks. Without that, the alignment guard drops every bye and absence
from every published round. That looks exactly like chess-results deleting them once a
later round is paired, and it is not: the rows stay. Checked against the tool's own HTTP
cache (`~/.cache/chess-results/http.sqlite`, latest fetch per URL), 68 round pages from 14
tournaments, 37 of them fetched after the next round had been paired, list all 242 players
their crosstables have off the board, and the only pages that ever read short were the 18
with a `PGN` column (the British and both Swindon sections). If a page ever does look short,
check its column count before blaming the site.

The starting-rank crosstable (`art=5`) states the same record, so `tournament()` fetches it
and `add_crosstable` cross-checks every round and fills any round a player still has no row
for. On real pages it fills nothing (zero plays across those 14 tournaments), so its tests
run against `british_with_gaps` and its siblings in `conftest.py`, which drop the rows to
make a gap. **Keep the request anyway; this was decided on 2026-10-04.** Its job is the
cross-check: one request per run sets every round page against a second view, so a
misread page surfaces as a warning instead of a quietly wrong score. Do not drop it or make
it opt-in to save the request. `check_published_totals` requires the cells we read from a crosstable row to sum
to the total that row publishes, and `tournament()` runs it. All 108 agree.

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
contradiction in `Tournament.disagreements`; the CLI prints those to stderr. Note that one
view holding a value the other lacks is deliberately not a contradiction: the crosstable is
often the fresher capture, and a round page carries no result until the game finishes.

**A live round's own bye can trip this comparison — treat that specific shape of hit as
chess-results.com, not a parser bug.** Caught on tnr1484240 (2nd Swindon Chess Congress,
Major section, 2026-08-31) mid-round 6 (8 of 28 results in): `kind` disagreed, `pairing_bye`
from the round page against `unpaired` from the crosstable, for the one player floating down
to the bye that round. A `--no-cache` re-fetch reproduced it identically, and the raw pages
confirm it is not our parsers disagreeing with each other: `art=2&rd=6` lists the player's row
as `bye`, while `art=5`'s crosstable prints `-0` (not paired, no round-6 opponent) in the same
player's round-6 cell. The crosstable has not yet caught up with the *current* round's bye.
Sibling section tnr1484241 hit the `check_published_totals` shape of it two days earlier, so
this looks like a property of the congress's live rounds generally rather than one section's
fluke. Nothing trips this on a finished round: the 14 tournaments in the HTTP cache,
assembled offline with their bye and "not paired" rows compared too, disagree only on
Torquay's then-newest round 2 (below). This is a live-round-only failure mode. It does not
corrupt anything downstream: `add_crosstable` only compares where the round page already has
a play, never overwrites it, so `Jones, Michael R` still shows the correct `bye` in
`standings` while the warning fires.

**For this specific comparison, the round finishing is what clears it — the next round need
not be paired.** Watched live on tnr1489316 (4th Torquay Riviera Congress PM Open,
2026-09-06): the same shape of disagreement (`Walley, A Clive` requested-bye, `Costello,
Colin A` pairing-bye, both `unpaired` in the crosstable) was present mid-round-2 (11 of 12
results in) and gone on a `--no-cache` re-fetch once the 12th result was in — while round 3
was still unpaired (`event.last_round` stayed 2). That is the opposite trigger from
`check_published_totals` below, where a fresh fetch with the round fully finished still read
the stale total and only the next round pairing was ever confirmed to help. Do not assume
one comparison's trigger for the other: this one settles on the round's own completion,
that one needs the next round paired.

**`check_published_totals` is a different comparison, and the newest round's byes can trip
it — durably, not just while live.** It checks the crosstable against itself,
summing a row's round-by-round cells against that row's own `Pts.`/`TB1` column, so unlike
the round-page comparison above it needs no second view to disagree with. Caught on tnr1484241
(2nd Swindon Congress, Minor section, 2026-08-29): two players who had just taken a
round-3 requested bye showed cells summing higher than the row's own published total —
`1b½ 8w0 -½` sums to 1.0, but `Pts.` read `0,5`, with `Rk.` matching the stale figure. The
first catch was mid-round (29 of 30 results in); a second, fresh, uncached fetch once every
round-3 result was in showed the identical stale `0,5` — so finishing the round is not what
fixes this, and the theory that it would was wrong. Every other requested bye in the same
tournament, all from rounds 1 and 2, sums correctly; only the two in the round chess-results
still treats as current are wrong, which points at the round still being current rather than
at anything about halves or byes generally. A round stops being current when the next one is
paired, and pairing later rounds does clear it: the cached crosstable fetched on
2026-09-03, covering rounds 1-6, has both players' cells and totals agreeing (2.5 and 2.0).
Whether round 4's pairing alone was enough is not pinned down, since nothing was fetched
between it and round 6. This does not corrupt anything downstream either way: `Tournament`'s assembled score comes from the round page, not from this total,
so `standings` and `pairings` were both already correct while the warning fired.

Searched for upstream attribution and found none: [chess-results.com](https://chess-results.com) has no public
issue tracker or changelog, and the [Swiss-Manager](https://swiss-manager.at) manuals do not mention it. So the crosstable
lagging a live round is observed, undocumented behaviour — do not go looking for a citation,
there isn't one.

The crosstable is not the only second view. **`art=40`, linked in the nav bar as "not paired",
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
checked against a live event on 2026-08-10**, tournament 1473782, caught with round 2
half-played and round 3 unpaired. The page carried a column for all seven rounds, with a
marker in round 1 only. It is observation, not inference; the `jeddah2026_*`
fixtures are that capture and cannot be regenerated, because the page ignores `&rd=`
and there is only ever the current one.

The other two views were surveyed the same way, and neither helps: **`art=1`**, the
ranking list, keeps a withdrawn player in place with their frozen score and carries no
marker of any kind (note it prints scores with a decimal comma). **`art=9`**, player
info, needs `&snr=<starting number>` and renders an empty shell without one; it does
show a missed round explicitly, as a `not paired` row with opponent SNo `-2`, but that
is one request per player (108 for a field) to learn what one crosstable already says.

**Three shapes are refused rather than read**, all subclasses of `TournamentError`, all
for the same reason: each produces a page nothing parses from, and an empty tournament is
indistinguishable from one that has not been played. `TeamTournamentError` (the round page
pairs teams), `RoundRobinError` (`is_combined_pairings` — every round on one page under
repeated "Round N on" headings, and an opponent-grid crosstable that `parse_crosstable`
reads nothing from while `parse_published_totals` still finds its totals, leaving the
cross-check with nothing to compare), and `TournamentNotStartedError` (no round assembled
at all). Do not "helpfully" make any of them return an empty `Tournament`.

**A round robin's pairing rows carry one trailing empty cell more than the header**, so the
alignment guard in `parse_pairings` drops every row. Tempting to relax — do not, on its
own: with the guard relaxed all nine rounds parse and every one is filed under whichever
round was requested, turning a silent nothing into silent nonsense. Section-aware parsing
would have to come first.

**An unpaired round still renders a table.** It contains only the withdrawn players' "not
paired" rows. Round auto-detection therefore requires at least one `PlayKind.GAME`; without
that check the scraper invents rounds and makes the whole active field look withdrawn.

**The starting-rank page's tournament-details table (organiser, time control, dates, ...)
is only there before the event starts.** `parse_tournament_details` reads it where present,
but "present" is not "whenever the organiser filled it in" — it is "whenever the organiser
filled it in *and* the event has not yet been paired". Confirmed on tnr1449763 (MEGA BIG
NORMS WARSAW SUMMER '26 IM ROUND-ROBIN - B): the pre-event fixture
(`warsaw2026_notstarted_startingrank.html`) carries the whole block (`Organizer`,
`Federation`, `Chief Arbiter`, `Time control`, `Location`, `Number of rounds`,
`Tournament type`, `Rating calculation`, `Date`, `Rating-Ø`, `Pairing program`), and a
live re-fetch of the same tournament after it had finished carries none of it: `Time
control` and `Organizer` are both absent from the raw response. The 2026 British and every
other mid-or-post-event fixture in the suite already carry none of it either, which used to
read as "this organiser didn't fill the parameters in" -- Warsaw shows that is not the whole
story. Not confirmed: whether it disappears the moment round 1 is paired, or only once the
event is further along — nobody has caught a mid-event organiser who'd filled the block in,
so there's nothing yet to check against. Either way it is harmless for `players`, which is
exactly the command that runs before a round exists and therefore the one place this data
is most likely to still be there.

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
whole round — it fills one player's gap inside a round we have. A round page lists every
game it pairs, so the only rows it can be missing are byes and "not paired". A recovered play
is always one of those two, and both are already right: a pairing bye takes `"D"`, and an
unpaired player takes nothing, having floated nowhere. Measured across every fixture,
the gapped ones included, the number of recovered *games* is zero.

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
`None` — silently, since an unrated player is a legitimate thing for a field to contain.
`_RATING_LABELS` tries `Rtg`, then `RtgI`, then `RtgN`.

**An unrated player's rating is not blank — it is the literal digit `0`.** Confirmed on
tnr1484241 (2nd Swindon Congress, Minor section, 2026-08-30): several players carry `Rtg` 0
while the column is populated for everyone else, so `_int()` parses it as `Player.rating = 0`
rather than `None`. Nothing downstream should treat that `0` as a real rating — the FIDE
performance-rating calculation in `Tournament.performance_rating` is the one consumer that
would otherwise be badly wrong (an unrated opponent counting as rating 0 instead of the FIDE
default of 1400 dragged one real player's figure from a true 1473 down to 913), so it treats a
`0` the same as a missing rating rather than checking only `is not None`. Any future numeric
use of `rating` needs the same care.

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
read results from it; the round page is the authority. What we read is the byes and
absences of rounds already played, to check and back up the round pages, and those never
change again.
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

**The starting-rank list gets the same "while it is still live" refetch, for a reason found
the hard way.** It was assumed fixed once an event began (the "1 day" above),
because starting numbers are supposed to be assigned once and never move. **Caught wrong on
tnr1484241** (2nd Swindon Congress, Minor section, 2026-08-30): an arbiter moved one
misplaced entry mid-event, and the sixteen players below it all shifted down one seat.
`add_crosstable` joins entirely by starting number (`tournament.py`'s `by_number` map), so a
starting-rank page cached from before the renumbering went on attributing every shifted
player's crosstable row to whoever now held their *old* number -- 201 false "disagreements"
where a fresh fetch of the same tournament found the true 3. It is not only the crosstable
join that a stale number corrupts: `ranking_order`, the pairing sheet's board assignment and
the TRF export all read `Player.start_no` too. `client.tournament()` now refetches the
starting rank with `refresh=True` whenever the real tournament might still be live: its own
last fetched round is unfinished, *or* `rounds=` bounded the scrape, in which case
`event.unfinished()` cannot see far enough to say either way and the honest assumption is
that it might be. That is not `crosstable_is_stale()` itself, whose round-coverage branch has
no equivalent here because there is no round-by-round coverage to fall behind on. It is
the same reasoning as its liveness branch: nothing here can drift once an event has
settled, only while it has not, or while a caller has chosen not to look far enough to
tell.

**requests-cache fixes expiry at write time**, which shapes both of the above. A round
cached while live keeps the 5-minute lifetime even once `round_ttl` starts asking for 30
days, so it used to be refetched on the old schedule purely to be rewritten. The
two ways round it are not interchangeable: `_extend_cached_lifetime` rewrites the
stored entry in place and costs nothing, which is what a settled round gets; `refresh=True`
replaces the entry with a fresh fetch, which is what the crosstable needs because its
content, not merely its expiry, has gone out of date. Using refresh for the round pages
would spend the request the fix exists to avoid.

The library is uncached by default (`ChessResults(cache=True)` opts in); the CLI caches by
default.

## CI

`.github/workflows/ci.yml`, on push to `main`, every pull request and `workflow_dispatch`.
`lint` runs `ruff check`, `ruff format --check` and `mypy --strict` (the last against both
`src/chess_results` and `examples`) on 3.13; `test` runs `pytest` across 3.10-3.13 with
`fail-fast: false`. No secrets and no network allowance -- the suite is fixtures only.

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

## Tests

Fixtures are real saved pages, mostly from the 2026 British Championship caught mid-event,
plus a congress section with a different column layout (it publishes starting-rank
numbers and has half-point byes). Nothing in the suite touches the network.

Several rounds have two fixtures on purpose, because the same round looks different
depending on when it was caught. `_r6_midround.html` and `_r7_midround.html` are the earlier
captures: six games still in progress in one, a paired-but-unplayed round in the other.
Their `_r6_finished.html` / `_r7_finished.html` counterparts are the same rounds played
out. The r6 pair also shows the `PGN` column: the finished page has one, with its bye and
"not paired" rows a cell short, and the mid-round page has none.

**Neither capture holds the plain `_r6.html` name, deliberately.** Which one a test wants is
the whole point of the pair, so there is no default to fall into: ask `conftest._round_fixture(rnd,
played_out=...)` for the name rather than building `f"..._r{rnd}.html"`, which is what the
old naming quietly encouraged. `_r8_unpaired_only.html` is the "round not yet paired" page,
and `_r8.html` is round 8 played.

`_r9.html` and `_crosstable_final.html` were captured on 2026-08-09 for the two defaulted
games (see `test_forfeit.py`); round 9 was still being played, so **there is no
complete-tournament fixture** — rounds 1-8 are as far as a fully-decided event goes. For
the same reason round 9's page has no `PGN` column.

`conftest.py` offers `british` (full pipeline, crosstable reconciled, mid-event; what most
tests want), `british_rounds_only` (round pages alone, which already hold every bye and
absence, so it agrees with `british`), `british_played_out` (rounds 1-8 with every game
decided, needed by anything asserting on real `to_trf` output, which refuses unfinished
games), the three `_with_gaps` variants of those (the bye and "not paired" rows dropped
from every `PGN` page, the only way to give `add_crosstable` something to fill) and
`frome_round_one` (a congress section with a different column layout and twelve half-point
byes; built from its round page alone, because feeding the Frome crosstable to
`parse_starting_rank` yields comma-less names that will not join).

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
The field *is* read: a team event's `art=0` lists teams (`SNo | Team | ...`, no `Name`), so
`entrants` asks `is_team_list` and, when it says so, reads the players from `art=16`
(`cnyt2026_g14_playerrank.html`), which `parse_starting_rank` handles as it stands.
`cnyt2026_g14_startingrank.html` is that `art=0`, captured on 2026-10-04 after the event had
finished, by when it had become a team ranking; the other `cnyt2026_g14_*` fixtures are from
round 1.

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

- **Withdrawals are the whole error term.** Given the field the arbiter paired,
  bbpPairings reproduces every round of the 2026 British Championship exactly, colours and
  bye included: rounds 2 to 9 at 53, 53, 53, 52, 52, 51, 51 and 50 of as many boards (round
  2 needing the field described next), and the checker replays rounds 1 and 3-8 from the
  finished file without a single difference.
- **The field that was paired is not always the field that played.** Round 2 of the British
  was paired with Mannion (No. 59, lost round 1, never played again) still in and Brown
  (No. 108, missed round 1, played only round 2) out; Brown then took Mannion's place, with
  his white, against Bhatia. `validate_prediction.py`'s "true withdrawals" run removes the
  players who did not *play*, so it puts Brown in, and the 42-player group on zero splits
  one place differently: six boards in a cyclic shift, 47 of 53. That shift was once put
  down to Swiss-Manager and bbpPairings choosing differently among legal pairings, and it is
  not; drop Brown, keep Mannion, swap the name on Bhatia's board, and all 53 boards match.
  `likely_withdrawn` happens to flag Brown (no round occupied yet) and miss Mannion, which is
  why its "inferred" run scores 52 of 53, beating the hindsight run. The checker reports the
  same six boards for round 2 and always will, because a TRF records who played, not who
  was paired. So before blaming either engine for a mismatch, look for a substitution: a
  player whose only game is the round in question, on the board of one whose last game was
  the round before.
  Blind — with no withdrawal information, which is what a live
  prediction actually has — rounds 7-9 give 37/51, 44/51 and 42/50. Every single miss
  is a player who had stopped playing, which nothing published says: a withdrawn player
  shows only as `not paired` in the rounds already missed. Do not reach for a rules-version
  or engine-disagreement explanation for a mismatch until the field has been checked.
  `Tournament.likely_withdrawn` guesses the field from trailing `UNPAIRED` rounds and takes
  those three to 39/51, 49/51 and 44/50. It reads the `not paired` rows the round pages list,
  so round pages alone give the same answer as a reconciled history. For a history missing
  those rows, `not_paired=` (the parsed `art=40` page) restores exactly the crosstable's
  answer at every round of the 2026 British for one request, as the gapped fixtures show. It
  buys nothing on top of either, by construction.

Predictions made mid-round need a result for every unfinished game, and those assumptions
dominate the outcome below the top boards. On 2026-08-08, round 9 predicted from a live
round 8 with ten games filled in as draws got the top 12 boards exactly right, in the
arbiter's own order, but only 29 of 50 overall — five of the ten filler draws were wrong,
and each wrong score moves a player into a different scoregroup. Trust the scoregroups whose
games are settled; say so explicitly about the rest.
