# chess-results

[![CI](https://github.com/markjonleonard/chess-results/actions/workflows/ci.yml/badge.svg)](https://github.com/markjonleonard/chess-results/actions/workflows/ci.yml)

Look up a chess tournament on [chess-results.com](https://chess-results.com) and
get the results back as text you can read, or as data you can work with.

For each player it collects who they played, which colour they had, whether they
floated up or down, and whether they took a bye: the things you need to follow a
Swiss tournament, or to work out what the next round's pairings should be.

Beyond the reports, it can print a round as a **pairing sheet** to put on a
noticeboard, find a tournament by name, list a congress's sections with their entrant
counts, and write a tournament as FIDE
[TRF(x)](https://handbook.fide.com/files/handbook/C04Annex2_TRF16.pdf) for a pairing
engine. Every command can print JSON.

What sets it apart from reading the site's tables is what happens after parsing. It
assembles the round pages into a per-player history and corrects it, recovering the
byes that chess-results.com deletes from earlier rounds' pages. Terms such as *float*
and *pairing-allocated bye* are explained under [Terms](https://github.com/markjonleonard/chess-results#terms).

> **Early days.** Version 0.1.0 is a first release. It works and is tested
> on real tournaments, but it has only been tried on a handful of events.
> Expect rough edges, and expect commands and options to change before 1.0.
> If you rely on it for something that matters, check its answers against the
> tournament's own pages.

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

Every tournament on chess-results.com has a number: the digits after `tnr` in the
address bar when you open the event.

```
https://chess-results.com/tnr1452107.aspx
                             ^^^^^^^
```

Addresses often carry more, such as a server prefix or a query string
(`https://s2.chess-results.com/tnr1452107.aspx?lan=1&art=2&rd=6`). Ignore all of it;
the number is the same. That number is what you pass to every command below. The
examples all use `1452107`, the 2026 British Championship.

If you only have a name, `search` finds the number:

```bash
chess-results search "Derbyshire Congress"
```

and `sections` lists every section of a congress from any one of its numbers. Both
are described in the [usage guide](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md).

## Using it

Ten commands. Each takes a tournament number, except `search`, which takes a name;
`history` also takes a player's name.

```bash
chess-results players 1452107                # the field, before or after the event starts
chess-results standings 1452107              # who is winning
chess-results pairings 1452107               # the current round's pairings
chess-results pairing-sheet 1452107          # the same, as a page to print
chess-results colours 1452107                # colour and float history
chess-results history 1452107 mcshane        # one player's round-by-round record
chess-results unfinished 1452107             # games still being played
chess-results dump 1452107 -o event.json     # everything, as a data file
chess-results sections 823027                # every section of a congress, with entrant counts
chess-results search "Derbyshire Congress"   # find a tournament number by name
```

Add `--json` to any of them for JSON instead of a table. A few examples, captured
during the 2026 British Championship:

```bash
chess-results standings 1452107 --after 6
```

```
2026 British Chess Championships: Championship — after round 6
  Rk  Pts   No      Name
   1    5    1  GM  Mcshane, Luke J
   2    5    2  GM  Adams, Michael
   3    5    3  GM  Royal, Shreyas
   …
```

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
 ...
  -  WFM Cooke, Suzy G          1          bye
page 1 of 1
```

```bash
chess-results sections 1063614
```

```
Derbyshire Congress — 2024-11-23 to 2024-11-24
 1063614  Open             31
 1063618  Major            28
 1063620  Intermediate     40
 1063621  Minor            31
 1063623  Foundation       19
          Total           149
```

`players` is the one command that works before the tournament has started. The rest
need at least one round to have been paired.

**The [usage guide](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md) covers each command's output and options, the JSON format,
the Python API, tie-breaks and the pairing-engine example.**

## From Python

```python
from chess_results import ChessResults

event = ChessResults().tournament(1452107)           # 2026 British Championship
mcshane = event.players["Mcshane, Luke J"]

mcshane.score(after=6)                              # 5.0
"".join(c.value for c in mcshane.colours(after=6))  # 'bwbwbw'
mcshane.colour_preference(after=6)                  # (Colour.BLACK, Preference.MILD)
```

Player names are keyed exactly as chess-results.com spells them. The
[usage guide](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#from-python) also covers searching, congresses, flat rows for a
DataFrame, tie-breaks and the pairing-sheet functions.

## Predicting the next round

This tool can write your tournament as
[TRF(x)](https://handbook.fide.com/files/handbook/C04Annex2_TRF16.pdf), the file
format FIDE pairing engines read, so that a program such as
[bbpPairings](https://github.com/BieremaBoyzProgramming/bbpPairings) can work out what
the next round's pairings ought to be. **The engine is not included**: you build or
download it separately, and the example script is in the repository, not the pip
package. Given the right list of players it reproduced rounds 7 to 9 of the 2026
British Championship exactly. Without knowing who had withdrawn it got 37 of 51, 44 of
51 and 42 of 50 boards right, so treat a prediction as a good guess, not an
announcement. See [the guide](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#predicting-the-next-round) for how to run it.

## Terms

- **Starting number** (`No`). The number each entrant gets before round 1, usually
  by rating. This tool joins the round pages to the crosstable through it.
- **Scoregroup.** The players on the same score.
- **Float.** A player paired against someone from a different scoregroup is said to
  float: *up* if the opponent is higher, *down* if lower. `U` and `D` in the output.
- **Pairing-allocated bye.** The bye the pairing program gives the odd player out
  in a round with an odd number of players. Usually a full point.
- **Requested bye.** A bye a player asks for in advance, commonly worth half a
  point. Shown by chess-results.com as `not paired` with a score.
- **Crosstable.** The page that lists every player's every round. It is the one view
  that keeps byes after their round is superseded.
- **Colour preference.** Which colour a player is due. Absolute, strong or mild, as
  defined by [FIDE C.04.3](https://handbook.fide.com/chapter/C0403).
- **TRF(x).** The file format for a tournament report that FIDE pairing engines read.

## A note on byes

chess-results.com removes the bye and "not paired" rows from a round's page as soon
as the next round is published. Anything reading only those pages will miss the byes
taken in earlier rounds, and score those players short of the points they were
awarded. This tool reads the crosstable as well and puts the missing byes and
absences back, so the scores it reports agree with the tournament's published
totals.

## What it does not do

**Team tournaments and round robins.** chess-results.com publishes both in formats
this tool does not read. A team round pairs teams rather than players, and a round
robin puts every round on one page with a crosstable of opponents rather than of
rounds. Point it at either and it says so and stops, rather than reporting an empty
tournament.

**Tournaments that have not started.** They get the same treatment. An entry list
often appears months ahead of the first game, and "this has not started yet" is more
use than a table of zeroes.

**Most of the tournament's own metadata.** Every command reads the name; `players`
also prints the dates and time control, but only when the organiser published them
and only before the event has been paired. That header disappears from the same page
once a round exists. Nothing here reads the organiser, the chief arbiter, the
playing schedule, or the tie-break columns of the final ranking. Everything is built
around who played whom, so that is what it collects.

## Related projects

[**chessResults**](https://codeberg.org/SirfHaru/chessresults) is an R package that
also scrapes chess-results.com, returning a tidy tibble of tournament information,
starting rank, playing schedule, round results and closing rank. If you work in R, or
you want the site's tables as published, including the fuller tournament metadata and
the tie-breaks this tool skips, it is the better fit. This tool does a narrower and
different job: it corrects the per-player history and can write it as TRF(x).

[`trf`](https://pypi.org/project/trf/) reads and writes the FIDE tournament report
format. This tool only ever *writes* TRF, and writes it directly, so it takes no
dependency. If you need to read a TRF file that something else produced, that package
is where to look.

## Being a good guest

chess-results.com is a free service run for the chess community. This tool pauses
between requests, remembers pages it has already fetched so it does not ask twice,
and identifies itself. Please leave those defaults alone unless you have a reason,
and do not point it at large numbers of tournaments at once. `search` is never cached,
so each call goes to the site: go easy with it, and prefer `sections` over looping
through searches.

## How it works

[DESIGN.md](https://github.com/markjonleonard/chess-results/blob/main/DESIGN.md)
covers the internals: how the pages are parsed, how caching decides what to keep,
how byes are recovered, and how the pairing predictions were tested.

## Getting help

If something looks wrong, please
[open an issue](https://github.com/markjonleonard/chess-results/issues) and include
the tournament number and the command you ran. That is usually enough to reproduce
it. Tournaments vary more than you would expect in which columns they publish, so the
most likely cause is a column layout this tool has not seen before.

Bug reports and pull requests are both welcome.

## Licence

MIT (see [LICENSE](https://github.com/markjonleonard/chess-results/blob/main/LICENSE)).
That covers this code only. It says nothing about chess-results.com's data or its
terms of use, which are the site's to set. Check them before you use that data.
Not affiliated with chess-results.com.
