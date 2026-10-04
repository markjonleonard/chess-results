# chess-results usage guide

Every command, every option, JSON output and the Python API. The
[README](https://github.com/markjonleonard/chess-results) has the overview, how to install, and
[Terms](https://github.com/markjonleonard/chess-results#terms) for words such as *float* and *pairing-allocated bye*.

**Contents:** [players](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#players) · [standings](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#standings) · [pairings](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#pairings) · [pairing-sheet](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#pairing-sheet) · [colours](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#colours) · [history](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#history) · [unfinished](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#unfinished) · [dump](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#dump) · [sections](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#sections) · [search](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#search) · [JSON output](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#json-output) · [Options](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#options)

**Also:** [From Python](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#from-python) · [Predicting the next round](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#predicting-the-next-round) · [Terms](https://github.com/markjonleonard/chess-results#terms)

## Command line

Ten commands. Each takes a tournament number, except `search`, which takes a name.
`history` takes a player's name as well. `colors` is accepted as a synonym for
`colours`.

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

`players` is the one command that works before the tournament has started. Every
other command that reads a tournament needs at least one round to have been paired, and fails
with a clear error on an event that has not begun. `players` reads the
starting-rank list alone, which chess-results.com publishes as soon as the field
is entered.

The outputs below were captured during the 2026 British Championship, at different
moments. Running them now, on a finished event, will not reproduce the live ones.
Options such as `--after`, `--limit` and `--json` are described under
[Options](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#options) once you have seen what the commands print.

### players

Starting number, title, name, rating and federation for every entrant: the field,
straight off the starting-rank list. When the organiser filled in Swiss-Manager's
or ChessManager's tournament parameters, this is also the one place the event's
name, dates and time control get printed. That header disappears from the same page
once the event is under way.

```bash
chess-results players 1489496
```

```
Trowbridge Rapidplay 2026-2027
18 player(s)
  No      Name                          Rtg  Fed
   1      Dave Elkin                   1900
   2      Mark J Leonard               1829
   3      Tim Kirkman                  1743
   …
```

```bash
chess-results players 1449763   # before the event starts
```

This second event is a round robin, which every other command refuses. `players` only
reads the field, so it works on any event. Names appear as each event publishes them:
some organisers write "Surname, Forename" and some do not.

```
MEGA BIG NORMS WARSAW SUMMER ‘26 IM ROUND-ROBIN - B — 2026/08/27 to 2026/08/31
Time control: Standard: 90min +30sec increment per move starting from move 1
10 player(s)
  No      Name                          Rtg  Fed
   1  IM  Miś, Mieszko                 2401
   2  IM  Gnojek, Petr                 2399
   3  CM  Terkiewicz, Bruno            2369
   …
```

### standings

Rank, score, starting number, title and name.

```bash
chess-results standings 1452107 --after 6
```

```
2026 British Chess Championships: Championship — after round 6
  Rk  Pts   No      Name
   1    5    1  GM  Mcshane, Luke J
   2    5    2  GM  Adams, Michael
   3    5    3  GM  Royal, Shreyas
   4    5    4  IM  Grieve, Harry
   5    5    6  IM  Bazakutsa, Svyatoslav
   6   4½    7  IM  Harvey, Marcus R
   …
```

Mid-round, scores are not comparable: a player whose game has finished counts this
round, and one still at the board does not. So the heading says how far the round
has got, and an extra column says what each player is doing.

```bash
chess-results standings 1452107
```

```
2026 British Chess Championships: Championship — during round 9: 4 of 50 results in
  Rk  Pts   No      Name                         This round
   1   6½    3  GM  Royal, Shreyas               playing
   2   6½    4  IM  Grieve, Harry                playing
   …
  98    2   62  CM  Stubbs, Oliver               0F
 101    2   95      Jermy, Jaden                 not paired
```

`--women` lists only the players the starting-rank list marks as women, ranked
among themselves for a women's prize table. It is an error, not an empty table, on an
event that publishes no such column.

That column holds `playing`, the result of a finished game (`1`, `½`, `0`), `bye`,
or `not paired`. An `F` after a result marks a forfeit, so `0F` is a game lost by
default. The column appears only while a round is live. A round paired but not yet
started says so in the heading instead: `round 9 paired, no results yet`.

### pairings

One round's table: board, both players with the score each carried into the round,
and the result. The latest round unless you name one: `pairings 1452107 6`, or
`--after 6` if you prefer the flag the other commands take.

```bash
chess-results pairings 1452107 6
```

```
2026 British Chess Championships: Championship — round 6 pairings
  Bd  Pts   No      White                        Res    Pts   No      Black
   1   4½    6  IM  Bazakutsa, Svyatoslav        ½-½     4½    4  IM  Grieve, Harry
   2    4    1  GM  Mcshane, Luke J              1-0      4   10  IM  Waldhausen Gordon, Frederick
   3    4   15  IM  Han, Yichen                  0-1      4    2  GM  Adams, Michael
   …
```

The starting numbers are joined in from the starting-rank list, because most events
leave the `No.` columns off their pairing pages.

**`pairings` does not recover byes.** chess-results.com deletes the `bye` and
`not paired` rows from a round's page once the next round is paired, and this
command shows the page as published. Round 6 above has 52 rows for a field of 108:
the byes and absences are gone. `standings`, `colours` and `history` still count
them, because they read the crosstable too. See [A note on byes](https://github.com/markjonleonard/chess-results#a-note-on-byes).
A round that is still the current one keeps those rows, shown as `bye` or
`not paired` in the black column. [`pairing-sheet`](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#pairing-sheet) does rebuild
them from the crosstable, because a sheet on a wall has to account for every player,
whereas `pairings` prints the page as published.

### pairing-sheet

The pairings as a page to print and put on a noticeboard, rather than a table to
read on screen: a repeated heading, form-feed page breaks so a long field prints as
whole sheets, and a result column to pencil into as games finish.

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

Name the round positionally, with `--round N`, or with `--after N`; all three mean
the same thing here. Do not reach for `--rounds`, which is unrelated (see
[Options](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#options)). The other options are `--subtitle TEXT` for a line under the
heading, `--no-results`, `--lines-per-page N`, `--no-pages`, `-o FILE` to write the
sheet to a file, and `--pairs FILE`, described below.

A decided game prints its result, a forfeit keeping its `F` so a default does not
read as an ordinary win. A game still to be played leaves the box empty, which is
what makes the sheet something an arbiter can write on. `--no-results` drops the
column and gives its four characters back to names.

Everyone who is not playing keeps a row, with the reason: `bye`, `half-point bye`
or `not paired`. They score differently, so the sheet does not run them together.
They are rebuilt from the crosstable, because chess-results.com deletes them from a
round's page once the next round is paired (unlike `pairings`, which prints the page
as published). See
[A note on byes](https://github.com/markjonleonard/chess-results#a-note-on-byes).

#### Printing a round nobody has played yet

With `--pairs`, the sheet is built from a pairing engine's output instead of a
published round. This is the case it exists for: the pairing computer has died and
the wall still needs a sheet.

The first command below needs the example script, which is in the repository and not
in the pip package, and bbpPairings, which is installed separately. See
[Predicting the next round](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#predicting-the-next-round).

```bash
# pair the next round and print it, in one go
python examples/predict_next_round.py 1452107 --engine ~/bbpPairings/bbpPairings.exe \
    --sheet round8.txt --subtitle "Starts 14:15 — Great Hall"

# or from an engine output file you already have
chess-results pairing-sheet 1452107 --pairs next.txt | lpr
```

An engine emits a set of pairs and no ordering, so board numbers have to be chosen
rather than read off. This chooses them the way arbiter software does: strongest
pair on board 1, working down the scoregroups. A player with a fixed board is
*placed* on it and marked, since a fixed board is usually an access requirement and a
footnote nobody transcribes is no use on a wall:

```
 14  GM Hebden, Mark L          4          CM Lishoy Gengis Parataz   4  *
 ...
  -  WFM Cooke, Suzy G          1          bye

* board fixed for this player
```

Anything that cannot be honoured, such as two fixed boards wanting one table or a
fixed board outside the round, is printed on the sheet rather than raised as an error. A sheet
the arbiter corrects by hand beats no sheet five minutes before a round.

chess-results.com marks a fixed-board player with a footnote on their name but never
says which board. This tool takes it to be the board number the player held longest in
an unbroken run, which can be wrong, since two rounds on the same board by coincidence
look like a fixed board. It never changes who plays whom, only where.

A published round, by contrast, keeps its **published board numbers**, which are the
arbiter's own and beat any convention this could apply. No board is moved and
nothing is starred.

**These board numbers are a convention, not a ruling**, and the pairings are only as
good as the results they were computed from. Read
[Predicting the next round](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#predicting-the-next-round)
before putting one on the wall.

`--lines-per-page N` sets how many lines a page holds. The default of 66 is a full US
Letter page at six lines per inch, and fits A4 with room to spare. `--no-pages` gives one
continuous sheet with no breaks or page numbers, for reading on screen.

### colours

What the next round's pairing turns on: the colours each player has had, whether
they floated up or down in each round, and which colour they are due next.

```bash
chess-results colours 1452107 --after 6
```

```
2026 British Chess Championships: Championship — colour and float history after round 6
 Pts   No  Name                         Colours    Floats     Due
   5    1  Mcshane, Luke J              BWBWBW     ------     B (mild)
   5    2  Adams, Michael               WBWBWB     ------     W (mild)
   5    3  Royal, Shreyas               BWBWWB     ----U-     W (mild)
   5    4  Grieve, Harry                WBWBWB     ------     W (mild)
   5    6  Bazakutsa, Svyatoslav        WBWWBW     ----D-     B (absolute)
  4½    7  Harvey, Marcus R             BWBWBW     ------     B (mild)
   …
```

- **Colours** are `W` and `B` in the order played. A bye or an unplayed round adds
  no letter, so a player with a bye has fewer letters than rounds.
- **Floats** have one character per round: `U` for paired against a higher
  scoregroup, `D` for a lower one, `-` for neither. A pairing-allocated bye counts
  as `D`.
- **Due** is the colour the player should get next, and how strongly, using
  FIDE's three levels ([C.04.3](https://handbook.fide.com/chapter/C0403)). *Absolute*
  means a colour difference of two or more, or the same colour in the last two
  games. *Strong* means a difference of one. *Mild* means the player is level and
  would simply like to alternate.

Absolute is the strongest claim, not a guarantee: the rules relax it for top scorers
in the final round, so an arbiter may see an absolute preference unmet.

### history

One player's colour, board, opponent and result for every round, with their total
and FIDE-standard performance rating. The player is matched by exact name or any
case-insensitive part of it. `mcshane` finds `Mcshane, Luke J`, but a part that
matches more than one player is an error rather than a guess.

```bash
chess-results history 1452107 mcshane --after 6
```

```
Mcshane, Luke J — round-by-round history, after round 6
 Rd  Cl   Bd  Opponent                     Result
  1  B     1  Bowcott-Terry, Finlay        1
  2  W     1  Wells, Peter K               ½
  3  B     7  Ledger, Andrew J             ½
  4  W    10  Turner, Max N                1
  5  B     4  Pert, Richard G              1
  6  W     2  Waldhausen Gordon, Frederick 1
Total: 5
Performance: 2606
```

### unfinished

The games in the current round that have no result yet, with the scores each player
brought into the round. This output was captured during round 6, so on the finished
event it now prints `round 9: all results in`.

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

### dump

The whole tournament as one JSON document, for a script or another program to read.
It is always JSON, so `--json` is accepted and changes nothing.

```bash
chess-results dump 1452107 -o event.json
```

The document has four keys: `id`, `name`, `rounds` and `players`.

- `rounds` maps each round number to its pairings, one object per board, exactly as
  chess-results.com published that round. Earlier rounds therefore lack their byes,
  as with `pairings`.
- `players` lists every player in ranking order. Each has their starting number,
  rating, title, federation and a `plays` list with one entry per round: colour,
  opponent, board, score and float. The byes are back in here.

`-o FILE` writes the document to a file instead of printing it.

### sections

Every section of a congress, with the number who entered each and the total, from
the number of any one section:

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

`--summary` prints the same on one line, `Open 31; Major 28; Intermediate 40;
Minor 31; Foundation 19 (2024)`, and `--json` prints it as data. Counts come from the
search, so no tournament page is read. Sections are listed in tournament number
order.

chess-results.com does not link the sections of a congress, so they are found by
what they share: the same organiser, and the same start date or the same end date.
That is an inference. A section that shares neither date is not found, and two
unrelated events from one organiser starting or ending the same day would be merged.
If it matters, check the list against the congress's own page. Section labels are
the words in each name that the others lack, so they are only as clean as the
organiser's naming: "FIDE Open" rather than "Open" when only some titles say "FIDE".

### search

Finds tournaments in chess-results.com's own database, newest first. Every filter
is a case-insensitive substring match on the site's side, and they combine:

```bash
chess-results search "Derbyshire Congress" --limit 3
```

```
15 tournament(s) found, showing 3
 1256721  2025-09-20 to 2025-09-21    24  3rd Derbyshire Congress FOUNDATION
 1256715  2025-09-20 to 2025-09-21    25  3rd Derbyshire Congress MAJOR
 1256719  2025-09-20 to 2025-09-21    26  3rd Derbyshire Congress MINOR
```

The columns are the tournament number, its dates, the number of entrants and its
name. `--organiser` (or `--organizer`), `--director`, `--arbiter` (the chief
arbiter), `--location`, `--ends-from`, `--ends-to` and `--finished-only` (or
`--finished`) narrow it further, and `--limit` caps the list (default 100). The
heading always gives the full count, so a cut-off list says so.

The site cuts names at 50 characters in these results, and can drop the space where
a name had a line break ("2024Under 1500"). A name that may be affected is marked
with `*`. `players` shows a tournament's own name in full, and `sections` reads it
for you. Searches are never cached.

### JSON output

Every command takes `--json`, before or after the command name, and prints one JSON
document on standard output in place of the table. Warnings and errors still go to
stderr, so `chess-results standings 1452107 --json | jq` is safe.

```bash
chess-results standings 1452107 --limit 3 --json
```

```json
{
  "id": "1452107",
  "name": "2026 British Chess Championships: Championship",
  "after": 9,
  "results_in": 50,
  "games": 50,
  "settled": true,
  "live": false,
  "total": 108,
  "truncated": true,
  "players": [
    {"rank": 1, "score": 7.5, "start_no": 3, "title": "GM", "name": "Royal, Shreyas", "state": null},
    {"rank": 2, "score": 7.0, "start_no": 1, "title": "GM", "name": "Mcshane, Luke J", "state": null},
    {"rank": 3, "score": 7.0, "start_no": 2, "title": "GM", "name": "Adams, Michael", "state": null}
  ]
}
```

What each command's document holds:

| Command | Top-level keys |
| --- | --- |
| `players` | `id`, `name`, `dates`, `time_control`, `total`, `truncated`, `players` |
| `standings` | `id`, `name`, `after`, progress, `live`, `total`, `truncated`, `players` (`rank`, `score`, `start_no`, `title`, `name`, `state`) |
| `pairings` | `id`, `name`, `round`, progress, `total`, `truncated`, `boards` |
| `colours` | `id`, `name`, `after`, `total`, `truncated`, `players` (`colours`, `floats`, `due`, `strength`) |
| `history` | `id`, `name`, `player`, `after`, progress, `rounds`, `score`, `performance` |
| `unfinished` | `id`, `name`, `round`, `total`, `truncated`, `games` |
| `pairing-sheet` | `id`, `name`, `round`, `after`, `boards`, `warnings`, `rows` (`board`, `white`, `black`, `fixed_board`, `bye`, `note`, `result`) |
| `sections` | `name`, `start_date`, `end_date`, `total`, `sections` |
| `search` | `total`, `truncated`, `results` |
| `dump` | `id`, `name`, `rounds`, `players` |

*Progress* is three keys, `results_in`, `games` and `settled`, which say how far the
round has got. Dates are ISO strings, colours are `"w"` and `"b"`, and a missing
value is `null`. The one exception to the dates is `dates` in `players`, which is the
organiser's own free text, such as "2026/08/27 to 2026/08/31".

JSON never clips a name, so `--name-width` has no effect on it. `--limit` still
applies to a list, and `total` and `truncated` say what it left out, so a cut list
is never mistaken for the whole. A command that fails still prints its one-line
error on stderr and prints nothing on standard output. The exit code is 0 on success,
2 when the request cannot be answered (a tournament it cannot read or that has not started, an
ambiguous or unknown player, a missing file) and 1 when chess-results.com did not
return a usable search page.

### Options

`chess-results <command> --help` prints a command's own options. The options in this
table are shared, and every one can go before or after the command name. An option for
one command alone, such as `--pairs` or `--women`, is described under that command.

| Option | What it does | Taken by |
| --- | --- | --- |
| `--after N` | Report the tournament as it stood after round N. A round it has not reached gives the latest. | `standings`, `colours`, `history`, `pairings`, `pairing-sheet` |
| `--limit N` | Print the first N rows, then say how many were left out. | `players`, `standings`, `colours`, `pairings`, `unfinished`, `search` |
| `--name-width N` | Room for a player's name before it is clipped and ends in `…`. Default 28, narrowed to fit a small terminal; anything under 8 counts as 8. | `players`, `standings`, `colours`, `pairings`, `history`, `pairing-sheet` |
| `--json` | Print JSON instead of a table. See [JSON output](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#json-output). | every command |
| `--rounds N` | Stop reading after round N. | the round-reading commands; ignored by `players` |
| `--bye-value P` | What a pairing-allocated bye is worth, in points (default 1.0). | the round-reading commands; ignored by `players` |
| `--no-crosstable` | Skip the crosstable request. **Scores will be wrong** for anyone whose bye has been deleted from the round's own page. | the round-reading commands; ignored by `players` |
| `--delay S` | Seconds to wait between requests (default 1.0). | every command |
| `--no-cache` | Always refetch, ignoring the cache. | every command |
| `--cache-ttl S` | Seconds to reuse a live round's page (default 300). Finished rounds are cached far longer. | the round-reading commands; ignored by `players` |
| `--cache-dir D` | Where to keep cached pages (default `~/.cache/chess-results`). | every command |

"The round-reading commands" are `standings`, `pairings`, `pairing-sheet`, `colours`,
`history`, `unfinished` and `dump`. `players` reads the starting-rank page alone, never
a round or the crosstable, so the options marked ignored have nothing to act on
there. `sections` and `search` read the tournament search instead of a tournament, so
they too ignore those options.

**`--after` and `--rounds` are different.** `--after N` changes what is *reported*:
the figures as they stood after round N, from rounds already read. `--rounds N`
changes what is *read*: it stops fetching after round N, so nothing later exists at
all. To look at a past round, you want `--after`.

**`--limit`** counts rows of data rather than lines, so the heading is never counted
against it, whereas `| head -10` counts every line it prints. It saves no time, since
the fetching is done before anything is printed. It is refused on two commands:
`dump`, because a cut-off export would corrupt the data, and `pairing-sheet`,
because a sheet missing its last boards sends players looking for a board that is
not there.

**`--name-width`** is not offered on `dump`, since clipping a name would corrupt
data rather than tidy a table. `pairing-sheet` has a `--name-width` of its own that
is sized for paper, so it is never narrowed to your terminal window. Widen it
when an event has long names you want in full:

```bash
chess-results pairings 1452107 6 --name-width 40
```

**`--bye-value`** matters if your event scores the pairing-allocated bye at less
than a point. A *pairing-allocated bye* is the one the pairing program gives the
odd player out; it is not the bye a player asks for. The crosstable prints every
pairing-allocated bye as a full point whatever the event actually awards, so this
option tells the tool what the real value is, and it rescores those byes to match.
Requested byes, which are commonly half a point, are read as published and are not
affected.

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

Player names are keyed exactly as chess-results.com spells them, which is why the
key is `"Mcshane, Luke J"` and not `"McShane"`. A wrong spelling is a `KeyError`.
Colour values are lower-case `"w"` and `"b"` in Python, whereas the command line
prints them upper-case. As on the command line, `after=N` pins a figure to a round;
leave it off and you get everything read so far.

The standings, a round's pairings, the games still to play and the TRF(x) file are
each one call:

```python
[p.name for p in event.ranking_order(after=6)][:3]   # standings order after round 6
event.rounds[6][0]                                   # a Pairing: board 1 of round 6
event.unfinished()                                   # games in the latest round with no result
event.last_round                                     # 9

from chess_results.trf import to_trf
trf = to_trf(event, after=8)    # FIDE TRF(x) through round 8; raises TrfError if a game has no result
```

No separate API reference exists. The classes and their fields are documented in
the source, and [DESIGN.md](https://github.com/markjonleonard/chess-results/blob/main/DESIGN.md)
explains the model.

### A pairing sheet

`pairing-sheet` is a thin wrapper over functions you can call directly, which take
an assembled tournament and touch neither the network nor an engine:

```python
from pathlib import Path

from chess_results import sheet

made = sheet.sheet_from_round(event, 8)          # a published round
print(sheet.render(made, results=True))

pairs = sheet.read_engine_pairs(Path("next.txt").read_text())
made = sheet.sheet_from_pairs(event, pairs)      # an engine's output
made.warnings                                    # what the arbiter must fix by hand
```

`render` leaves the result column off unless asked, whereas the command turns it on.
It is a primitive and holds no opinion about what your sheet is for.

### Finding sections and tournaments

```python
from chess_results import ChessResults

client = ChessResults()

listing = client.sections(823027)
listing.summary()   # 'Open 30; Major 25; Intermediate 45; Minor 19; Foundation 25 (2023)'
listing.total       # 144
for section in listing.sections:
    print(section.id, section.label, section.players)   # 823027 Open 30, ...

found = client.search("Derbyshire Congress", ends_from="2024-01-01")
found.total         # how many matched, which can exceed len(found)
found.truncated     # True when `limit` cut the list short
found[0].name, found[0].id, found[0].players
```

`search` takes `name`, `tournament_id` (the command line has no flag for it, since
`sections` is how you start from a number), `organizer` (spelled as the site spells
it), `director`, `arbiter`, `location`, `ends_from`, `ends_to` (a `date` or
`"YYYY-MM-DD"`), `finished_only` and `limit`, and needs at least one criterion. A response that is not a list of
tournaments is retried once and then raised as `SearchError`.
`SearchResult.name_inexact` is set for a name the site may have cut at 50 characters
or run two words together in.

### A congress of several sections

A weekend congress runs as several graded sections, and chess-results.com gives
each one its own tournament number with nothing linking them. Name them yourself and
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

The section names are yours, since nothing on the site groups a congress. To have
them suggested, `sections` finds them from any one section's number (see
[Finding sections and tournaments](https://github.com/markjonleonard/chess-results/blob/main/USAGE.md#finding-sections-and-tournaments)):

```python
client = ChessResults()
listing = client.sections(1346570)
milton_keynes = client.congress({s.label: s.id for s in listing.sections}, name=listing.name)
```

Pass `skip_unreadable=True` to record a section this tool refuses (a round-robin
top section, or one that has not started) in `congress.unreadable` and carry on with
the rest, instead of losing the lot.

### Flat rows

Either a tournament or a congress will give you one record per player per round,
which is the shape to hand to a DataFrame, a CSV writer or `json.dump`:

```python
frome.rows()[0]
# {'round': 1, 'board': 1, 'section': 'Open', 'name': 'Jones, Steven A',
#  'colour': 'b', 'score': 1.0, 'kind': 'game', ...}
```

Two things to know before summing anything in there. `score` scores an unpaired
round 0, which is not the same as a round lost, so read `kind` alongside it, or a
player who went home after round 2 looks present and beaten in every round after.
And `rating` is the rating the player was paired on, estimates included, which is
not always what the rating list says today.

### Tie-breaks

`chess_results.tiebreaks` has the usual Swiss tie-breaks (progressive score,
Buchholz, Sonneborn-Berger, black count, head-to-head) as plain functions over a
`Player` and, when a tie-break needs one, the owning `Tournament`:

```python
from chess_results.tiebreaks import buchholz, progressive_score

mcshane = event.players["Mcshane, Luke J"]
progressive_score(mcshane, after=6)      # rewards a fast start
buchholz(mcshane, event, after=6)        # sum of opponents' scores
```

Buchholz here is the plain sum of the player's opponents' scores. A bye or an
unplayed round has no opponent and adds nothing, so this does not apply FIDE's
virtual-opponent rule from its tie-break regulations. Where those rules matter, as
at a FIDE-rated event, check the figures against your arbiter's software.

This is the arithmetic only. It is not a policy for which tie-breaks apply, in what
order, or to which prize; that is usually specific to the event and belongs in the
caller.

## Predicting the next round

This tool can write your tournament out as
[TRF(x)](https://handbook.fide.com/files/handbook/C04Annex2_TRF16.pdf), the file
format that FIDE pairing engines read, so that a program such as
[bbpPairings](https://github.com/BieremaBoyzProgramming/bbpPairings) can work out
what the next round's pairings ought to be.

**The engine is not included.** This tool writes the file and hands it over; the
pairing itself is done by bbpPairings, which you build or download separately and
point at with `--engine`. The example script lives in the
[repository](https://github.com/markjonleonard/chess-results/blob/main/examples/predict_next_round.py)
rather than in the pip package, so clone it first. It checks the engine path before
it fetches anything, so a wrong one costs you a message rather than a scrape:

```bash
python examples/predict_next_round.py 1452107 --engine ~/bbpPairings/bbpPairings.exe
```

How good is a prediction? Given the correct list of players, bbpPairings reproduced
rounds 7, 8 and 9 of the 2026 British Championship exactly: every board, every
colour, the right player on the bye. A live prediction cannot know who has quietly
withdrawn, and one player leaving changes the pairings for everyone below them.
Without that knowledge the same three rounds came out at 37 of 51, 44 of 51 and 42
of 50 boards right. Round 2 does not reproduce even with the right players: a large group on the same
score admits many legal pairings, and bbpPairings and the arbiter's software choose
differently among them. The
method and the figures are in
[DESIGN.md](https://github.com/markjonleonard/chess-results/blob/main/DESIGN.md#predicting-the-next-round).
Treat a prediction as a good guess, not an announcement.
