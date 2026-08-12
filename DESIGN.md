# Design notes

How [`chess-results`](https://pypi.org/project/chess-results/) is built and why.
The [README](README.md) is the user-facing description; this is for anyone
changing the code. Throughout, `chess-results` is this library and
[chess-results.com](https://chess-results.com) is the site it reads. Measurements
here were taken against particular tournaments and will move as the code does.

## What it is for

A Swiss tournament is a sequence of pairings, and every pairing depends on what
came before it: each player's score, the colours they have had, whether they were
floated up or down, and whether they have taken a bye. chess-results.com
publishes all of that, but scattered across several views and only in the present
tense — the round pages describe the round in front of you, not the tournament so
far.

This library assembles those views into one per-player history, keyed by player,
covering every round. From that history it can report standings, colour and float
records and colour preferences, and write the tournament out in the format FIDE
pairing engines read, so the next round can be computed.

Nothing persists between runs except cached pages. Each invocation fetches what
it needs, builds the history in memory, and reports from it; there is no store to
migrate and no state to keep in step.

## Shape

Three layers, kept apart so the parsers can be exercised offline against saved
pages. Nothing below the fetch layer knows HTTP exists.

| Layer | Module | Responsibility |
| --- | --- | --- |
| Parse | `parse.py` | HTML → dataclasses. Stateless, no network. |
| Assemble | `tournament.py` | Per-round tables → per-player histories. |
| Fetch | `client.py` | HTTP, round discovery, cache policy, orchestration. |

`models.py` holds the dataclasses. `trf.py` and `cli.py` consume an assembled
`Tournament`; `cache.py` is policy only. `congress.py` sits above the lot and is
the one type not read off a page — see below.

### The one type the site does not publish

A UK weekend congress is five or six graded sections played in one hall under one
set of prize rules, and chess-results numbers each section separately with
*nothing* joining them: no congress page, no parent identifier, no link. The
grouping lives in the entry form and the prize list, and nowhere in the data.

`Congress` therefore takes its sections and their names from the caller. That
makes it the exception to "everything here is something the site said", and the
reason it belongs in the library anyway is that the alternative is every congress
user writing the same loop and the same section tag — as this library's own first
consumer did, for a year, before this existed.

It deliberately offers no merged `players` dictionary. Players are keyed by name,
so merging would drop one of two players sharing a name with no error and no
trace. `find()` returns every match with its section, and `section_of()` answers
`None` rather than guessing when there are two.

This guards a rare case, not a common one. On Frome 2026 — 191 players, five
sections — no name appears twice. Ten surnames span sections, four of them
looking like families, and every one has a distinct first name: names are
`"Surname, Firstname"`, so relatives are precisely the case that does *not*
collide. The real risk is two unrelated people with the same full name, and the
only thing a congress changes is that merging five sections gives the
coincidence a field several times larger to miss. A collision *within* one
section already collides at `Tournament` level, so nothing here can help that.

Two shapes are easy to confuse. A **`Pairing`** is one row of a round's table and
holds two players. A **`Play`** is what *one* player did in one round. `add_round`
turns each `Pairing` into one or two `Play` objects, and a `Player` is a name plus
an ordered list of them.

## Where the data comes from

| View | URL | Parsed by |
| --- | --- | --- |
| Round pairings | `art=2&rd=N` | `parse_pairings` |
| Starting rank | `art=0` | `parse_starting_rank` |
| Starting-rank crosstable | `art=5` | `parse_crosstable`, `parse_published_totals` |
| Not paired | `art=40` | `parse_not_paired` |

A scrape walks the rounds from 1 upward until a page has no games, then fetches
the crosstable. The starting rank supplies numbers, titles, ratings and
federations, which pairing pages often omit.

`art=40` lists only the players who have missed a round, as a grid of one column
per round marked `*` not paired, `bye` a bye, `0F` a forfeit. It is the most
direct statement of who was absent when, and one small page rather than a whole
crosstable to mine, so `ChessResults.not_paired()` exposes it and
`likely_withdrawn` accepts it. It cannot replace the crosstable: a *requested*
half-point bye prints `*` exactly as a withdrawal does, so it does not say what a
missed round was worth, and a forfeit lists only the player who defaulted.

Three views are deliberately unparsed. `art=1` (ranking list) carries no
withdrawal marker. `art=9` (player info) does, but costs one request per player.
`art=3` is an alphabetical list, and `art=4` is `art=5`'s data keyed by current
rank, which a caller holding the crosstable can produce by sorting.

## The central problem: byes vanish

A round's pairing page lists byes and unpaired players only while that round is
the current one. Once a later round is paired, those rows are **deleted**.

A player who took a full-point bye in round 6 therefore has no round 6 anywhere on
the round pages once round 7 is out, and their score comes out a point light.
Through round 8 of the 2026 British Championship this affects four players —
Chapman, Cooke, Nevska and Ruddy, one bye each across rounds 5 to 8. It is not a
display option; the same happens with and without `turdet`.

The data is not lost upstream. The starting-rank crosstable keeps the whole
record, one row per player, one column per round:

```
106  Chapman Luke   52b0  77w0  84w0  104b½  96w0  -1  92b½    2
```

`-1` is a pairing-allocated bye, `-½` a requested one, `-0` a round the player
took no part in. Both views come from the same Swiss-Manager upload, so this is
the round view choosing to stop showing something the source still holds.

So `tournament()` fetches the crosstable too and fills in any round a player is
missing. Rounds read from a pairing page win, since those carry board numbers and
pre-round scores the crosstable does not publish. Recovered rounds are marked:

```python
[p.round for p in event.players["Ruddy, Rachel"].plays if p.from_crosstable]  # [5]
```

Only rounds already fetched are filled, so the crosstable never introduces a round
of its own, and since a *game* row is never deleted from a round page, a recovered
play is always a bye or an absence. `crosstable=False` (`--no-crosstable`) skips
the request and accepts the four wrong scores.

This behaviour is observed, not documented. chess-results.com publishes no changelog
or issue tracker and the [Swiss-Manager](https://swiss-manager.at)
manuals do not mention it, so treat this as what the pages were seen to do in
August 2026 rather than a guarantee.

## Reading tables that keep changing shape

Tournaments differ in which columns they publish, so nothing is read by position.
Each table's header row drives the parse. chess-results.com emits one header mixing
`<th>` with `<td>` — the two player-name columns are `td` — so both are read
together to get a header that aligns with the data rows.

Column *names* vary as well as their presence:

- **Ratings** are `Rtg`, or `RtgI` and `RtgN` where an event is rated nationally
  and internationally at once.
- **A player's total** is `Pts.` where the event publishes one, `TB1` otherwise.
  `TB1` is a tie-break, which on many events happens to be the score and on others
  is a rating. `parse_published_totals` prefers `Pts.`, falls back to `TB1`, and
  rejects whatever it picks if any value exceeds the number of rounds played.

Every request carries `lan=1`, because the parsers key off English labels and the
words "bye" and "not paired"; `zeilen=99999`, because a list is otherwise
paginated at 150 rows with nothing in the page to say so; and follows redirects,
because chess-results.com 302s the bare domain to a numbered mirror. Every
logical fetch is therefore two HTTP requests, which is worth remembering against
the counts below.

## Checking the reading

Two views of one upload give something to check against. Both checks are
tripwires: they are clean on every fixture and against live events, so a hit means
a parser has misread something rather than chess-results.com being inconsistent.

- **`check_published_totals`** requires the round-by-round cells parsed from a
  crosstable row to sum to the total that row publishes. It compares the
  crosstable against *itself*, not against the assembled history — a published
  total and an assembled score cover the same rounds only sometimes.
- **`Tournament.disagreements`** records any field where a round page and the
  crosstable contradict each other. A value one view holds and the other lacks is
  not a contradiction: the crosstable is often the fresher capture, and a round
  page carries no result until the game finishes.

The CLI prints disagreements to stderr, so piped output stays clean.

## Caching

Pages are given lifetimes by how volatile they are. A round that has finished,
with a later round already paired, never changes again; the newest round always
might, because a result can be corrected before the next pairing is published.
Settled rounds are recorded in a JSON sidecar so the knowledge survives runs.

| Page | Lifetime |
| --- | --- |
| Starting rank | 1 day — fixed once the event begins |
| Round still in play, or the newest round | 5 minutes (`--cache-ttl`) |
| Finished round, superseded by a later one | 30 days |
| Crosstable | 30 days, replaced when it falls behind |

The crosstable takes the long lifetime despite looking live. It carries the
current round's results, but those are never read from it — the round page is the
authority there. What is read is the byes and absences round pages delete, which
are settled the moment they are written. So instead of expiring on a timer it is
*replaced* when a cached copy stops covering what is needed: when it holds fewer
rounds than the scrape does, or while the newest round is still being played,
where a stale copy would read as a contradiction rather than an old page.

[requests-cache](https://requests-cache.readthedocs.io) fixes a response's expiry
when it stores it, so a lifetime cannot be lengthened after the fact. The two
ways around that suit different cases. **Rewriting** the stored entry
in place costs nothing and suits a settled round, whose content is final and only
whose expiry is wrong. **Refreshing** refetches, and suits the crosstable, whose
content really has gone out of date.

In practice a cold run on a finished 9-round event is about twelve logical
fetches: the starting rank, nine rounds, an empty probe past the last, and the
crosstable. A repeat run costs two — the newest round and the probe — or none
within the five-minute window.

The CLI caches by default in `~/.cache/chess-results`; `--no-cache` bypasses it,
`--cache-dir` moves it. The library does not, so a caller keeps control:

```python
ChessResults(cache=True)  # or pass your own CachedSession
```

## Retries

A scrape is a dozen requests, so one transient failure part-way through would lose
the run. Sessions the client builds carry a urllib3 `Retry` on 429 and the 5xx
family — three attempts, backing off about 0.5s, 1s, 2s, honouring `Retry-After`.
GET and HEAD only. 404 is excluded deliberately: that is chess-results.com answering
that no such tournament exists, not failing.

```python
ChessResults(retries=0)     # opt out
ChessResults(session=mine)  # your session, your transport policy
```

A session you pass in is never mounted over — `client.retrying_adapter()` is
exported so you can mount it yourself.

## Predicting the next round

`chess_results.trf` writes FIDE
[TRF(x)](https://handbook.fide.com/files/handbook/C04Annex2_TRF16.pdf), which
[bbpPairings](https://github.com/BieremaBoyzProgramming/bbpPairings) and
[JaVaFo](https://www.rrweb.org/javafo/JaVaFo.htm) read.
`examples/predict_next_round.py` scrapes a tournament, resolves any unfinished
games from assumptions you supply, and shells out to bbpPairings — which is a
separate program, not a dependency: the engine is checked for before anything is
fetched, since the alternative is a dozen requests against chess-results.com to
reach an error that was knowable from a path.

```bash
python examples/predict_next_round.py 1452107 --engine ~/bbpPairings/bbpPairings.exe \
    --assume "Mcshane, Luke J=1"
```

`examples/validate_prediction.py` scores a prediction against the round the
arbiter actually published:

```bash
python examples/validate_prediction.py 1452107 --round 8 \
    --engine ~/bbpPairings/bbpPairings.exe --total-rounds 9
```

Three rounds of the 2026 British Championship, each reproduced from the rounds
before it:

| | Round 7 | Round 8 | Round 9 |
| --- | --- | --- | --- |
| Boards published | 51 | 51 | 50 |
| Exact, no withdrawal information | 37 | 44 | 42 |
| Exact, withdrawals inferred | 39 | 49 | 44 |
| Exact, withdrawals supplied | **51** | **51** | **50** |
| Right pair, wrong colour | 0 | 0 | 0 |
| Bye recipient | correct | correct | correct |

Given an accurate field the engine reproduces all three exactly — every board,
every colour, the right player on the bye. **The accuracy of the field is the
whole error term.** Nothing here suggests the engines disagree with
Swiss-Manager, or that the rule version matters.

The columns are not comparable with each other: "no withdrawal information" is
what a live prediction has, while "supplied" takes the absent players from the
published round and so uses hindsight. The gap between them is the cost of not
knowing who has left, and it is the dominant term because a single departure
changes floats and the bye for everyone below.

`Tournament.likely_withdrawn` closes part of that gap by inference — a player
whose last rounds are all unpaired, or who never occupied a round. A requested
bye is deliberately not treated as a signal. It finds 12 of the 18 absences
across those three rounds; the remaining six leave no trace, three of them having
played the previous round in full and simply not come back.
`predict_next_round.py` applies it by default (`--no-infer-withdrawals` opts out)
and takes `--withdrawn` if you know more.

Two limits on what prediction can be expected to do:

- **Round 2 does not reproduce**, even with the correct field: six boards differ,
  all inside the 42-player group on zero after round 1. Not the field, colours,
  the encoding of a late entrant's missing round, or same-federation avoidance —
  each was tested. A group that large and that flat admits many legal pairings,
  and the checker exits 0 without calling the published one illegal. Expect this
  on any round 2.
- **A mid-round prediction is dominated by its assumptions.** Round 9 predicted
  from a live round 8 with ten unfinished games filled in as draws got the top 12
  boards exactly right in the arbiter's own order, and 29 of 50 overall — five
  guesses were wrong, and each wrong score moves a player into a different
  scoregroup. Trust the scoregroups whose games are settled; say so about the
  rest.

Board *order* is not part of an engine's output. Engines emit a set of pairs and
the arbiter's software numbers the boards, so compare pairings as sets — by
position gives a badly misleading match rate.

## Fixed boards

Swiss-Manager lets an arbiter pin a player to one board for the whole event,
usually on access or health grounds. chess-results.com marks them with a footnote and
explains it in a legend under the pairing table, which this library reads:

```python
hebden = event.players["Hebden, Mark L"]
hebden.fixed_board         # True
hebden.fixed_board_number  # 14
```

The footnote says only *that* a player is pinned, never to which board, so the
number is inferred from the boards they played: the longest unbroken run, most
recent winning a tie. A run rather than the most frequent board, because a pin
need not start at round 1 — Hebden played 23, 18 and 1 before settling on 14 from
round 4, and by then every board had been played exactly once.

It remains a heuristic: two rounds on one board by coincidence look like a pin,
and a pin the arbiter could not honour one round looks like two shorter ones.

A fixed board constrains where a game is played, not who plays whom, so it never
changes a pairing — but it is a second reason board numbers do not follow from
scores.

## What this does not read

Three shapes produce a page nothing can be read from, and all three used to
assemble into an empty tournament — a field, no rounds, and a confident report of
nothing at all. Each is now detected and refused with its reason, as a subclass
of `TournamentError`, so a caller catches one thing and the CLI prints one line.

- **Team tournaments** (`TeamTournamentError`). The round page pairs *teams*,
  carrying match points and naming no player; the individual boards sit on a
  second view as one sub-table per match. `parse_pairings` reads nothing from
  either, which is safe — no team is mistaken for a player.
- **Round robins** (`RoundRobinError`). Two views differ from their Swiss
  equivalents. The pairings page holds **every round at once**, under repeated
  "Round N on …" headings in a single table, and ignores `rd` — so a parser
  reading it would file all nine rounds' games under whichever round it asked
  for. And the crosstable is a grid of *opponents* rather than of rounds:

  ```
  Swiss:       No. | Name | Rtg | FED | 1.Rd | 2.Rd | … | Pts.
  Round robin: No. | Name | Rtg |  1   |  2   | …    | 9 | Pts.
  ```

  `parse_crosstable` reads nothing from that, while `parse_published_totals`
  still finds the `Pts.` column beside it — so the cross-check compares nine
  totals against nothing and reports no disagreement. A check that goes quiet
  because it has nothing to compare is worse than no check, which is why this is
  refused outright rather than left to the tripwire.

  `is_combined_pairings` detects it from the repeated headings rather than from
  the tournament type, which the page does not state. One heading is what an
  ordinary Swiss round page carries; more than one means the rounds have been
  combined.
- **Tournaments that have not started** (`TournamentNotStartedError`). Not a
  limitation but a state, and the commonest of the three: chess-results publishes
  an entry list as soon as registration opens, often months ahead. Six round-robin
  tournament numbers were tried while hunting for a played one, and four had not
  begun.

Also unread, but no error, since these are simply outside what it collects:
**most tournament metadata** — no organiser, time control, dates, playing
schedule, or the tie-break columns of the final ranking.

For the site's tables as published, including the metadata and tie-breaks,
[chessResults](https://cran.r-project.org/package=chessResults) is an R package
covering that ground.

## Things worth knowing

- **Players are keyed by name.** Pairing pages identify players by name, and only
  some tournaments publish starting numbers there. Where the starting-rank list is
  available its numbers are attached and are what `ranking_order()` sorts on. Two
  players sharing a name in one event will collide, as will one player named
  differently on two views — which shows up as a field one larger than it should
  be.
- **Floats are inferred** by comparing the two players' displayed pre-round
  scores. They are not published. A pairing-allocated bye counts as a downfloat.
- **Byes are ambiguous in the source.** An opponent shown as `bye` is a
  pairing-allocated bye, worth a full point in a FIDE Swiss but a half at some
  congresses — hence `bye_value`. `not paired` with a value shown is a requested
  bye and keeps what the page displays. The crosstable is unambiguous about what
  happened and is the authority wherever a round page has dropped the row, but it
  prints every pairing-allocated bye as a full point regardless of what the event
  awards, so a bye recovered from it is rescored to `Tournament.bye_value`. That
  is a correctness matter, not a display one: `to_trf` declares a non-standard
  value as bbpPairings' `BBU` line, and the engine recomputes every score from the
  results and refuses the file if the totals disagree.
- **Points are written two ways in one tournament.** Round-by-round cells use `½`;
  a total is rendered in the server's locale and can arrive as `4,5`. A comma is
  always a decimal separator here, no points value being large enough to need a
  thousands separator.
- **Be polite.** The client sleeps between requests (`delay`, default 1s), pacing
  only those that actually reach the server, and identifies itself.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

320 tests, none touching the network. Fixtures are real saved pages from five
tournaments, chosen for the ways they differ:

| Event | What it covers |
| --- | --- |
| 2026 British Championship | The main set: mid-event and played out, byes, withdrawals, forfeits both ways round, no starting-rank columns |
| Frome congress section | A different column layout, starting-rank numbers, twelve requested half-point byes |
| 19th Arad Open | 209 players, so pagination; `RtgI`/`RtgN`; a `Pts.` column beside real tie-breaks |
| Jeddah qualifier | Caught live with a round unpaired — the only state in which `art=40` can be tested for advance warning |
| Chinese National Youth Team | A team event |
| USSA Closed 2026 Open | A round robin: every round on one page, an opponent-grid crosstable |
| Warsaw IM norm event | A tournament that had not started — a field and no games |

Rounds 6 and 7 have two fixtures each, because the same round looks different
depending on when it was caught: the mid-round captures still have their bye rows,
the played-out ones have had them deleted. Which one a test wants is the point of
the pair, so neither holds the plain name — ask `conftest._round_fixture(rnd,
played_out=...)`.

The Jeddah set cannot be regenerated: `art=40` ignores `&rd=`, so that mid-event
state existed only while the round was live.

To add a fixture, save the page with `curl -sL` — the `-L` matters — plus `lan=1`
and `zeilen=99999`.
