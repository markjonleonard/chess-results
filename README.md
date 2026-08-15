# chess-results

[![CI](https://github.com/markjonleonard/chess-results/actions/workflows/ci.yml/badge.svg)](https://github.com/markjonleonard/chess-results/actions/workflows/ci.yml)

Look up a chess tournament on [chess-results.com](https://chess-results.com) and
get the results back as text you can read, or as data you can work with.

For each player it collects who they played, which colour they had, whether they
floated up or down, and whether they took a bye — the things you need to follow a
Swiss tournament, or to work out what the next round's pairings should be.

> **Early days.** Version 0.1.0 is a first release. It works and is tested
> against real tournaments, but it has only been used against a handful of
> events. Expect rough edges, and expect commands and options to change before
> 1.0. If you are relying on it for something that matters, check its answers
> against the tournament's own pages.

## Install

```bash
pip install chess-results
```

Requires Python 3.10 or newer. To work on it instead:

```bash
git clone https://github.com/markjonleonard/chess-results
cd chess-results
pip install -e ".[dev]"
```

## Finding your tournament

Every tournament on chess-results has a number, which appears in the address bar
when you open the event:

```
https://chess-results.com/tnr1452107.aspx
                             ^^^^^^^
```

That number is what you pass to every command below. The examples all use
`1452107`, the 2026 British Championship.

## Command line

Six commands. Each takes a tournament number.

```bash
chess-results standings 1452107              # who is winning
chess-results pairings 1452107               # this round's boards
chess-results pairing-sheet 1452107          # the same, as a page to print
chess-results colours 1452107                # colour and float history
chess-results unfinished 1452107             # games still being played
chess-results dump 1452107 -o event.json     # everything, as a data file
```

Add `--after N` to see the tournament as it stood after a particular round,
rather than as it stands now. Ask for a round the tournament has not reached and
you get the latest one. It shapes what `standings`, `colours`, `pairings` and
`pairing-sheet` report; `dump` always exports the whole event and `unfinished`
always means the round being played.

`colors` is accepted as a synonym for `colours`.

`--limit N` prints the first N rows and then says how many it left out. It counts
rows rather than lines, so `--limit 10` is ten players where `| head -10` is nine
players and a heading. It saves no time — the fetching is done before anything is
printed.

It is refused rather than ignored on two commands. Truncated JSON is no use to
anyone, so not on `dump`; and a pairing sheet missing its last boards is worse
than no sheet, because the players on them go looking for a board that is not
there, so not on `pairing-sheet`.

`--name-width N` sets how much room a player's name gets before it is clipped to
an `…`. The default is 28, narrowed further if your terminal is too small to fit
the table; anything under 8 is treated as 8. Widen it when an event has long
names you want in full:

```bash
chess-results pairings 1452107 6 --name-width 40
```

Not offered on `dump` — JSON has no columns to line up, and clipping a name there
would corrupt data rather than tidy a table. `pairing-sheet` has a `--name-width`
of its own which behaves slightly differently: it is sized for paper rather than
for your terminal, so it is never narrowed to the window.

### All the options

`chess-results <command> --help` prints a command's own options. These affect
what is fetched, and every command takes them:

| Option | What it does |
| --- | --- |
| `--rounds N` | Stop after N rounds instead of discovering them all |
| `--bye-value P` | What a pairing-allocated bye is worth (default 1.0) |
| `--delay S` | Seconds between requests (default 1.0) |
| `--no-cache` | Always refetch, ignoring the cache |
| `--cache-ttl S` | How long to reuse a live round's page (default 300) |
| `--cache-dir D` | Where to keep cached pages |
| `--no-crosstable` | Skip the crosstable request — **scores will be wrong** for anyone whose bye has been dropped from its round page |

These shape the reporting, and not every command takes every one:

| Option | Taken by |
| --- | --- |
| `--after N` | `standings`, `colours`, `pairings`, `pairing-sheet` |
| `--limit N` | `standings`, `colours`, `pairings`, `unfinished` |
| `--name-width N` | `standings`, `colours`, `pairings`, `pairing-sheet` |

`--bye-value` is worth knowing about if your event awards half a point for a
bye: the crosstable prints every pairing-allocated bye as a full point whatever
the tournament actually gives, so this is what rescores it.

### standings

Rank, score, starting number, title and name.

```bash
chess-results standings 1452107 --after 6
```

```
2026 British Chess Championships: Championship — after round 6
   1    5    2  GM  Adams, Michael
   2    5    3  GM  Royal, Shreyas
   3    5    4  IM  Grieve, Harry
   4    5    6  IM  Bazakutsa, Svyatoslav
   5   4½    7  IM  Harvey, Marcus R
   6   4½    9  IM  Czopor, Maciej
```

Mid-round the scores are not comparable — a player whose game has finished counts
this round, one still at the board does not — so the heading says how far the
round has got and each line says what that player is doing. The extra column
appears only while a round is live.

```bash
chess-results standings 1452107
```

```
2026 British Chess Championships: Championship — during round 9: 4 of 50 results in
   1   6½    3  GM  Royal, Shreyas               playing
   2   6½    4  IM  Grieve, Harry                playing
   …
  98    2   62  CM  Stubbs, Oliver               0F
 101    2   95      Jermy, Jaden                 not paired
```

A round paired but not yet started says so instead: `round 9 paired, no results yet`.

### pairings

One round's table: board, both players with the score each carried into the
round, and the result. The latest round unless you name one — `pairings 1452107 6`,
or `--after 6` if you prefer the flag the other commands take.

```bash
chess-results pairings 1452107 6
```

```
2026 British Chess Championships: Championship — round 6 pairings
  Bd  Pts   No      White                        Res    Pts   No      Black
   1   4½    6  IM  Bazakutsa, Svyatoslav        ½-½     4½    4  IM  Grieve, Harry
   2    4    1  GM  Mcshane, Luke J              1-0      4   10  IM  Waldhausen Gordon, Frederick
   …
  52    ½  105  WCM Nevska, Gerda                1                    bye
  53    3   21  IM  Golding, Alex                                     not paired
```

The starting numbers are joined in from the starting-rank list, because most
events leave the `No.` columns off their pairing pages. Byes and "not paired"
rows are shown as chess-results publishes them — which is to say only while the
round is the current one, since they are deleted once the next round is paired.
See [A note on byes](#a-note-on-byes).

### pairing-sheet

The pairings as a page to print and pin to a noticeboard, rather than a table to
read on screen: a repeated heading, form-feed page breaks so a long field prints
as whole sheets, and a result column to pencil into as games finish.

```bash
chess-results pairing-sheet 1452107 --after 8 --subtitle "Starts 14:15 — Great Hall" | lpr
```

```
2026 British Chess Championships: Championship
Round 8 pairings
Starts 14:15 — Great Hall

 Bd  White                    Pts  Result  Black                    Pts
-----------------------------------------------------------------------
  1  GM Adams, Michael         5½   ½-½    GM Royal, Shreyas          6
  2  IM Grieve, Harry          5½   1-0    IM Roberson, Peter T      5½
  3  IM Bazakutsa, Svyatoslav  5½   0-1    GM Williams, Simon K      5½
 ...
  -  WFM Cooke, Suzy G          1          bye
page 1 of 1
```

Name the round positionally, with `--round N`, or with `--after N`; all three
mean the same thing here. Do not reach for `--rounds`, which is unrelated — it
limits how much of the event gets scraped.

A decided game prints its result, a forfeit keeping its `F` so a default does not
read as an ordinary win. A game still to be played leaves the box empty, which is
what makes the sheet something an arbiter can write on. `--no-results` drops the
column and gives its four characters back to names.

Everyone who is not playing keeps a row, with the reason: `bye`, `half-point bye`
or `not paired`. Those are a point apart, so the sheet does not run them
together — and they are rebuilt from the crosstable, because chess-results
deletes them from a round's page once the next round is paired. See
[A note on byes](#a-note-on-byes).

#### Printing a round nobody has played yet

With `--pairs`, the sheet is built from a pairing engine's output instead of a
published round — the case this exists for, when the pairing computer has died
and the wall still needs a sheet.

```bash
# pair the next round and print it, in one go
python examples/predict_next_round.py 1452107 --engine ~/bbpPairings/bbpPairings.exe \
    --sheet round8.txt --subtitle "Starts 14:15 — Great Hall"

# or from an engine output file you already have
chess-results pairing-sheet 1452107 --pairs next.txt | lpr
```

An engine emits a set of pairs and no ordering, so board numbers have to be
chosen rather than read off. This chooses them the way arbiter software does:
strongest pair on board 1, working down the scoregroups. A player with a fixed
board is *placed* on it and marked, since a pin is usually an access requirement
and a footnote nobody transcribes is no use on a wall:

```
 14  GM Hebden, Mark L          4          CM Lishoy Gengis Parataz   4  *
 ...
  -  WFM Cooke, Suzy G          1          bye

* board fixed for this player
```

Anything that cannot be honoured — two pins wanting one board, a pin outside the
round — is printed on the sheet rather than raised as an error. A sheet the
arbiter corrects by hand beats no sheet five minutes before a round.

A published round, by contrast, keeps its **published board numbers**, which are
the arbiter's own and beat any convention this could apply — so no board is moved
and nothing is starred.

**These board numbers are a convention, not a ruling**, and the pairings are only
as good as the results they were computed from. Read
[Predicting the next round](#predicting-the-next-round) before pinning one up.

`--lines-per-page N` sets how many lines a page holds (66 by default, which is
what a printer fed plain text uses on A4 and US Letter). `--no-pages` gives one
continuous sheet with no breaks or page numbers, for reading on screen.

### colours

What the next round's pairing turns on: the colours each player has had, whether
they floated up (`U`) or down (`D`) in each round, and which colour they are due
next.

```bash
chess-results colours 1452107 --after 6
```

```
2026 British Chess Championships: Championship — colour and float history after round 6
 Pts   No  Name                         Colours    Floats     Due
   5    2  Adams, Michael               WBWBWB     ------     W (mild)
   5    3  Royal, Shreyas               BWBWWB     ----U-     W (mild)
   5    4  Grieve, Harry                WBWBWB     ------     W (mild)
   5    6  Bazakutsa, Svyatoslav        WBWWBW     ----D-     B (absolute)
  4½    7  Harvey, Marcus R             BWBWBW     ------     B (mild)
   …
   4    1  Mcshane, Luke J              BWBWBW     ------     B (mild)
```

A player due a colour "absolutely" must get it in the next round; "mild" means
it is only a preference.

### unfinished

The games in the current round that have no result yet, with the scores each
player brought into the round.

```bash
chess-results unfinished 1452107
```

```
round 6: 6 game(s) still unfinished
  bd2    Mcshane, Luke J (4) vs Waldhausen Gordon, Frederick (4)
  bd18   Yao, Lan (3) vs Cancedda-Dupuis, Livio (3)
  bd20   Balaji, Aaravamudhan (3) vs Fellowes, Billy (3)
  bd25   Toma, Katarzyna (2½) vs Kanyamarala, Trisha (2½)
  bd44   Terler, Bohdan (1½) vs Elgar, Tim (1½)
  bd50   Varnam, Liam D (1) vs Vaddhireddy, Sai (1)
```

## From Python

The same information, as objects:

```python
from chess_results import ChessResults

event = ChessResults().tournament(1452107)           # 2026 British Championship
mcshane = event.players["Mcshane, Luke J"]

mcshane.score(after=6)                              # 5.0
"".join(c.value for c in mcshane.colours(after=6))  # 'bwbwbw'
mcshane.colour_preference(after=6)                  # (Colour.BLACK, Preference.MILD)
```

As on the command line, `after=N` pins a figure to a round; leave it off and you
get everything scraped so far.

### A pairing sheet

`pairing-sheet` is a thin wrapper over functions you can call directly, which
take an assembled tournament and touch neither the network nor an engine:

```python
from chess_results import sheet

made = sheet.sheet_from_round(event, 8)          # a published round
print(sheet.render(made, results=True))

pairs = sheet.read_engine_pairs(open("next.txt").read())
made = sheet.sheet_from_pairs(event, pairs)      # an engine's output
made.warnings                                    # what the arbiter must fix by hand
```

`render` leaves the result column off unless asked, where the command turns it
on: it is a primitive and holds no opinion about what your sheet is for.

### A congress of several sections

A weekend congress runs as several graded sections, and chess-results gives each
one its own tournament number with nothing linking them. Name them yourself and
fetch them as one event:

```python
from chess_results import ChessResults

frome = ChessResults().congress(
    {"Open": 1393521, "Major": 1393522, "Standard": 1393526},
    name="Frome Chess Congress 2026",
)

len(frome)                          # 3
frome["Open"].last_round            # 5
frome.section_of("Weaver, Alan")    # 'Standard'
frome.player_count                  # entries across the whole congress
```

The section names are yours: nothing on the site groups a congress, so nothing
can be guessed. Pass `skip_unreadable=True` to record a section this library
refuses — an all-play-all top section, or one that has not started — in
`congress.unreadable` and carry on with the rest, instead of losing the lot.

### Flat rows

Either a tournament or a congress will give you one record per player per round,
which is the shape to hand to a DataFrame, a CSV writer or `json.dump`:

```python
frome.rows()[0]
# {'round': 1, 'board': 1, 'section': 'Open', 'name': 'Jones, Steven A',
#  'colour': 'b', 'score': 1.0, 'kind': 'game', ...}
```

Two things to know before summing anything in there. `score` scores an unpaired
round 0, which is not the same as a round drawn nil — read `kind` alongside it,
or a player who went home after round 2 looks present and beaten in every round
after. And `rating` is the rating the player was paired on, estimates included,
which is not always what the rating list says today.

## Predicting the next round

The library can write your tournament out in the file format that FIDE pairing
engines read, so a program like
[bbpPairings](https://github.com/BieremaBoyzProgramming/bbpPairings) can work out
what the next round's pairings ought to be. See `examples/predict_next_round.py`.

**The engine is not included.** This writes FIDE TRF(x) and hands it over; the
pairing itself is done by bbpPairings, which you build or download separately
and point at with `--engine`. The example checks the path before it fetches
anything, so a wrong one costs you a message rather than a scrape:

```bash
python examples/predict_next_round.py 1452107 --engine ~/bbpPairings/bbpPairings.exe
```

It gets most pairings right and can get all of them right, but it cannot know who
has quietly withdrawn — and one player leaving changes the pairings for everyone
below them. Treat a prediction as a good guess, not an announcement.

## A note on byes

chess-results removes bye and "not paired" rows from a round's page as soon as
the next round is published. Anything reading only those pages will miss byes
taken in earlier rounds and score those players a point light. This library reads
the crosstable as well and puts the missing rounds back, so the scores it reports
agree with the tournament's published totals.

## What it does not do

**Team tournaments and round robins.** chess-results publishes both in formats this does
not read — a team round pairs teams rather than players, and a round robin puts every
round on one page with a crosstable of opponents rather than of rounds. Point it at either
and it says so and stops, rather than reporting an empty tournament.

**Tournaments that have not started** get the same treatment. An entry list often appears
months ahead of the first game, and "this has not started yet" is more use than a table of
zeroes.

**Most of the tournament's own metadata.** It reads the name and nothing else: not the
organiser, the time control, the dates, the playing schedule, or the tie-break columns of
the final ranking. Everything here is built around who played whom, so that is what it
collects.

## Related projects

[**chessResults**](https://codeberg.org/SirfHaru/chessresults) is an R package that also
scrapes chess-results.com, returning a tidy tibble of tournament information, starting
rank, playing schedule, round results and closing rank. If you work in R, or you want the
site's tables as published — including the metadata and tie-breaks this tool skips — it is
the better fit.

The difference is what happens after parsing. This library assembles the round pages into a
per-player history and corrects it: it recovers byes that chess-results deletes from
superseded round pages, tracks colours and floats, and can write the result as FIDE
[TRF(x)](https://handbook.fide.com/files/handbook/C04Annex2_TRF16.pdf) for a pairing engine. That is a narrower job than reproducing the site's tables, and a
different one.

[`trf`](https://pypi.org/project/trf/) reads and writes the FIDE tournament report
format. This library only ever *writes* TRF, and writes it directly, so it takes no
dependency; if you need to read a TRF file that something else produced, that package is
where to look.

## Being a good guest

chess-results is a free service run for the chess community. This library pauses
between requests, remembers pages it has already fetched so it does not ask
twice, and identifies itself. Please leave those defaults alone unless you have a
reason, and do not point it at large numbers of tournaments at once.

## How it works

[DESIGN.md](DESIGN.md) covers the internals: how the pages are parsed, how
caching decides what to keep, how byes are recovered, and how the pairing
predictions were tested.

## Getting help

If something looks wrong, please
[open an issue](https://github.com/markjonleonard/chess-results/issues) and
include the tournament number and the command you ran — that is usually enough to
reproduce it. Tournaments vary more than you would expect in which columns they
publish, so the most likely cause is a column layout this tool has not seen before.

Bug reports and pull requests are both welcome.

## Licence

MIT — see [LICENSE](LICENSE). That covers this code only. It says nothing about
chess-results.com's data or its terms of use, which are the site's to set; check
them before pointing this at anything at scale. Not affiliated with
chess-results.com. Please use it gently.
