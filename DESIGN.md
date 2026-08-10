# Design notes

How chess-results is built and why. These notes describe internals, and they
carry measurements taken against particular tournaments — expect both to move as
the code changes. The [README](README.md) is the stable, user-facing description.

## Prior art

There is an [R package](https://cran.r-project.org/package=chessResults) that
scrapes chess-results, but no maintained Python equivalent. This library keeps
the things a Swiss pairing depends on: who played whom, with which colour, who
floated up or down, and who took a bye.

## Byes disappear, so the crosstable is scraped too

A round's pairing page lists byes and unpaired players only while that round is
the current one. Once a later round is paired, those rows are **deleted**. Round
7 of the 2026 British Championship shows its pairing-allocated bye; rounds 4, 5
and 6 show nothing at all, though two of them had one.

Scrape after the fact and a full-point bye is simply gone — the player has no
such round anywhere on the round pages, and their score comes out a point light.
This is not a display option; it is the same with and without `turdet`.

This is observed behaviour, not documented behaviour. chess-results.com publishes
no changelog or issue tracker, and nothing in the Swiss-Manager manuals describes
it, so whether it is deliberate or a defect is not something you can find out from
outside. Treat the description here as what the pages were seen to do in August
2026, not as a guarantee.

What can be said is that the data is not lost upstream: the same event's crosstable
still carries every bye that the round pages have dropped. Both views are rendered
from the same Swiss-Manager upload, so the record survives in the source and it is
the `art=2` round view that stops showing it. Swiss-Manager is not the culprit.

The starting-rank crosstable (`art=5`) keeps the whole record, one row per
player, one column per round:

```
106  Chapman Luke   52b0  77w0  84w0  104b½  96w0  -1  92b½    2
```

`-1` is a pairing-allocated bye, `-½` a requested one, `-0` a round the player
took no part in. So `tournament()` fetches the crosstable as well and fills in
any round a player is missing. Results already read from a pairing page are left
alone — those carry board numbers and pre-round scores, which the crosstable does
not publish. Recovered rounds are marked:

```python
[p.round for p in event.players["Ruddy, Rachel"].plays if p.from_crosstable]   # [5]
```

Across the full 108-player field this takes every computed score to agreement
with the published totals; without it, two are wrong. Pass `crosstable=False`
(`--no-crosstable`) to skip the extra request.

## Caching

A round that has finished, with a later round already paired, never changes again,
so it is cached for far longer than one still in play. The client records which
rounds have settled in a small JSON file beside the cache, so the knowledge
survives between runs:

| Page | Lifetime |
| --- | --- |
| Starting rank | 1 day — fixed once the event begins |
| Round still in play, or the newest round | 5 minutes (`--cache-ttl`) |
| Finished round, superseded by a later one | 30 days |
| Crosstable | 30 days, replaced when it falls behind |

The newest round is never treated as settled even when every result is in, because
a result can still be corrected before the next pairing is published.

The crosstable is the interesting one. It looks live — it carries the current
round's results — but we never read results from it; the round page is the
authority there. What we read is the byes and absences that round pages delete
once a later round is paired, and those are settled the moment they are written.
So it is cached for 30 days and *replaced* when a cached copy stops being good
enough, which happens when it covers fewer rounds than we hold (it could not
supply the newest round's bye) or when the newest round is still being played
(the two views are also compared, and a stale copy would look like a
contradiction rather than an old page). A finished tournament therefore fetches
it once and never again.

The CLI caches by default, in `~/.cache/chess-results`; `--no-cache` bypasses
it and `--cache-dir` moves it. The library does not, so a caller keeps control:

```python
ChessResults(cache=True)                      # or pass your own CachedSession
```

Against a 7-round event this took repeat runs from 18 network requests to zero.
One caveat: requests-cache fixes a response's expiry when it stores it, so a
round that settles between runs is fetched once more before it takes the long
lifetime. It costs one extra fetch per round, once. The crosstable sidesteps
this by forcing a refresh rather than shortening a lifetime it can no longer
change; the same trick would work for round pages if it ever seems worth it.

## Retries

A scrape is one request per round plus the crosstable and the starting rank, so a
single transient failure part-way through loses the whole run. Sessions the client
builds carry a urllib3 `Retry` on 429 and the 5xx family — three attempts, backing
off about 0.5s, 1s, 2s, honouring `Retry-After`. GET and HEAD only, and 404 is
excluded on purpose: that is chess-results answering that no such tournament
exists, not failing.

```python
ChessResults(retries=0)                       # opt out
ChessResults(session=mine)                    # your session, your transport policy
```

A session you pass in is never mounted over — `client.retrying_adapter()` is
exported so you can mount it yourself if you want it.

## Predicting the next round

`chess_results.trf` writes FIDE TRF(x), which
[bbpPairings](https://github.com/BieremaBoyzProgramming/bbpPairings) and JaVaFo
read. `examples/predict_next_round.py` scrapes a live tournament, resolves any
unfinished games from assumptions you supply, and shells out to bbpPairings:

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

Rounds 7 and 8 of the 2026 British Championship, each reproduced from the rounds
before it:

| | Round 7 | Round 8 |
| --- | --- | --- |
| Boards published | 51 | 51 |
| Exact, no withdrawal information | 37 | 44 |
| Exact, withdrawals supplied | **51** | **51** |
| Right pair, wrong colour | 0 | 0 |
| Bye recipient | correct | correct |

Given an accurate field, bbpPairings reproduces both rounds exactly: every board,
every colour, and the right player on the bye. **Withdrawals account for every
difference.** Nothing here suggests the engines disagree with Swiss-Manager, or
that the rule version matters — the whole error term is not knowing who has left.

The two figures are not comparable. The blind one is what a genuine live
prediction achieves; the second supplies the absent players from the published
round and so uses hindsight. Read the gap between them as the cost of the missing
information:

- **Withdrawals are invisible until the round is published.** chess-results does
  not say who has withdrawn, and a player leaving changes floats and the bye for
  everyone below them. Worse, the scraper cannot even infer it: the round the
  player last appeared in will have had its "not paired" rows deleted once the
  next round was paired. Pass `--withdrawn` if you know.
- **The field must come from the crosstable, not the round page.** Deriving it
  from a superseded round page reclassifies that round's bye recipient as a
  withdrawal, which produces plausible and entirely wrong match rates.

Board *order* is not part of a pairing engine's output — engines emit a set of
pairs, and the arbiter's software numbers the boards. Compare pairings as sets.

## Fixed boards

Swiss-Manager lets an arbiter pin a player to one board number for the whole
event, usually on access or health grounds. chess-results marks them with a
footnote and explains it in a legend under the pairing table, which this library
reads:

```python
hebden = event.players["Hebden, Mark L"]
hebden.fixed_board          # True
hebden.fixed_board_number   # 14
```

The flag says only *that* a player has a fixed board, never which one, so the
number is read back from the boards they actually played on. In the 2026 British
Championship, Hebden played boards 23, 18 and 1 in the first three rounds and
then board 14 in every round after, while his score moved from 3 to 4.

This constrains where a game is played, not who plays whom, so it never changes
a pairing — but it is a second reason not to expect board numbers to follow from
scores, alongside the fact that engines do not emit an ordering at all.

## What gets parsed

| View | chess-results URL | Function |
| --- | --- | --- |
| Round pairings | `art=2&rd=N` | `parse_pairings` |
| Starting rank | `art=0` | `parse_starting_rank` |
| Starting-rank crosstable | `art=5` | `parse_crosstable` |

Parsing is driven by each table's header row rather than fixed column offsets.
chess-results emits one header row that mixes `<th>` with `<td>` (the two player
name columns are `td`), and tournaments switch columns on and off — the starting
rank `No.` columns in particular are absent from some events. Reading `th` and
`td` together gives a header that aligns with the data rows whichever columns a
tournament publishes.

Pages are always requested with `lan=1`: the parsers key off English column
labels and the words "bye" and "not paired".

## Things worth knowing

- **Players are keyed by name.** chess-results pairing pages identify players by
  name, and only some tournaments publish starting numbers there. Where the
  starting rank list is available its numbers are attached to each player, and
  that is what `ranking_order()` sorts on. Two players sharing a name in one
  event will collide.
- **Floats are inferred**, by comparing the two players' displayed pre-round
  scores. That is what the published data supports; it is not read from the
  arbiter's own float records.
- **Byes are ambiguous in the source.** An opponent shown as `bye` is a
  pairing-allocated bye, worth a full point in a FIDE Swiss but a half at some
  congresses — hence `bye_value`. `not paired` with a value shown is a requested
  bye and keeps whatever the page displays. The crosstable is unambiguous about
  *what happened*, and is the authority wherever a round page has dropped the
  row, but it prints every pairing-allocated bye as a full point regardless of
  what the event awards, so a bye recovered from it is rescored to
  `Tournament.bye_value`. That is not cosmetic: `to_trf` declares a non-standard
  value as bbpPairings' `BBU` line, and the engine recomputes every player's
  score from their results and refuses the file if the totals disagree.
- **Be polite.** The client sleeps between requests (`delay`, default 1s), only
  pacing requests that actually reach the server, and identifies itself.

## Tests

The test tools are in the `dev` extra, which the README's install line leaves out:

```bash
pip install -e ".[dev]"
pytest
```

Fixtures are real pages from two tournaments with different column layouts: the
2026 British Championship caught mid-event (rounds 1-6 played with six games
unfinished, round 7 paired but unplayed, byes and withdrawals present, no
starting-rank columns) and a congress section that does publish them.
