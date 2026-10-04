# chess-results

[![CI](https://github.com/markjonleonard/chess-results/actions/workflows/ci.yml/badge.svg)](https://github.com/markjonleonard/chess-results/actions/workflows/ci.yml)

Look up a chess tournament on [chess-results.com](https://chess-results.com) and
get the results back as text you can read, or as data you can work with.

For each player it collects who they played, which colour they had, whether they
floated up or down, and whether they took a bye: the things you need to follow a
Swiss tournament, or to work out what the next round's pairings should be.

What sets it apart from reading the site's tables is what happens after parsing.
It assembles the round pages into a per-player history and corrects it, recovering
the byes that chess-results.com deletes from earlier rounds' pages. It can then write
the tournament as FIDE [TRF(x)](https://handbook.fide.com/files/handbook/C04Annex2_TRF16.pdf)
for a pairing engine. Terms such as *float* and *pairing-allocated bye* are explained
in [Terms](https://github.com/markjonleonard/chess-results#terms).

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
are described under [Command line](https://github.com/markjonleonard/chess-results#command-line).

## Command line

Ten commands. Each takes a tournament number, except `search`, which takes a name.
`colors` is accepted as a synonym for `colours`.

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
other tournament command needs at least one round to have been paired, and fails
with a clear error on an event that has not begun. `players` reads the
starting-rank list alone, which chess-results.com publishes as soon as the field
is entered.

The outputs below were captured during the 2026 British Championship, at different
moments. Running them now, on a finished event, will not reproduce the live ones.
Options such as `--after`, `--limit` and `--json` are described under
[Options](https://github.com/markjonleonard/chess-results#options) once you have seen what the commands print.

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
`not paired` in the black column.

### pairing-sheet

The pairings as a page to print and pin to a noticeboard, rather than a table to
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
[Options](https://github.com/markjonleonard/chess-results#options)).

A decided game prints its result, a forfeit keeping its `F` so a default does not
read as an ordinary win. A game still to be played leaves the box empty, which is
what makes the sheet something an arbiter can write on. `--no-results` drops the
column and gives its four characters back to names.

Everyone who is not playing keeps a row, with the reason: `bye`, `half-point bye`
or `not paired`. Those are a point apart, so the sheet does not run them together.
They are rebuilt from the crosstable, because chess-results.com deletes them from a
round's page once the next round is paired. See
[A note on byes](https://github.com/markjonleonard/chess-results#a-note-on-byes).

#### Printing a round nobody has played yet

With `--pairs`, the sheet is built from a pairing engine's output instead of a
published round. This is the case it exists for: the pairing computer has died and
the wall still needs a sheet.

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
*placed* on it and marked, since a pin is usually an access requirement and a
footnote nobody transcribes is no use on a wall:

```
 14  GM Hebden, Mark L          4          CM Lishoy Gengis Parataz   4  *
 ...
  -  WFM Cooke, Suzy G          1          bye

* board fixed for this player
```

Anything that cannot be honoured, such as two pins wanting one board or a pin
outside the round, is printed on the sheet rather than raised as an error. A sheet
the arbiter corrects by hand beats no sheet five minutes before a round.

A published round, by contrast, keeps its **published board numbers**, which are the
arbiter's own and beat any convention this could apply. No board is moved and
nothing is starred.

**These board numbers are a convention, not a ruling**, and the pairings are only as
good as the results they were computed from. Read
[Predicting the next round](https://github.com/markjonleonard/chess-results#predicting-the-next-round)
before pinning one up.

`--lines-per-page N` sets how many lines a page holds (66 by default, which is what
a printer fed plain text uses on A4 and US Letter). `--no-pages` gives one
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

```
$ chess-results sections 1063614
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

```
$ chess-results search "Derbyshire Congress" --limit 3
15 tournament(s) found, showing 3
 1256721  2025-09-20 to 2025-09-21    24  3rd Derbyshire Congress FOUNDATION
 1256715  2025-09-20 to 2025-09-21    25  3rd Derbyshire Congress MAJOR
 1256719  2025-09-20 to 2025-09-21    26  3rd Derbyshire Congress MINOR
```

The columns are the tournament number, its dates, the number of entrants and its
name. `--organizer`, `--director`, `--location`, `--ends-from`, `--ends-to` and
`--finished` narrow it further, and `--limit` caps the list (default 100). The
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
    {"rank": 1, "score": 7.5, "start_no": 3, "title": "GM", "name": "Royal, Shreyas", "state": null}
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
| `pairing-sheet` | `event`, `round`, `after`, `boards`, `warnings`, `rows` |
| `sections` | `name`, `start_date`, `end_date`, `total`, `sections` |
| `search` | `total`, `truncated`, `results` |
| `dump` | `id`, `name`, `rounds`, `players` |

*Progress* is three keys, `results_in`, `games` and `settled`, which say how far the
round has got. Dates are ISO strings, colours are `"w"` and `"b"`, and a missing
value is `null`.

JSON never clips a name, so `--name-width` has no effect on it. `--limit` still
applies to a list, and `total` and `truncated` say what it left out, so a cut list
is never mistaken for the whole. A command that fails still prints its one-line
error on stderr and prints nothing on standard output.

### Options

`chess-results <command> --help` prints a command's own options. Every option can go
before or after the command name.

| Option | What it does | Taken by |
| --- | --- | --- |
| `--after N` | Report the tournament as it stood after round N. A round it has not reached gives the latest. | `standings`, `colours`, `history`, `pairings`, `pairing-sheet` |
| `--limit N` | Print the first N rows, then say how many were left out. | `players`, `standings`, `colours`, `pairings`, `unfinished`, `search` |
| `--name-width N` | Room for a player's name before it is clipped and ends in `…`. Default 28, narrowed to fit a small terminal; anything under 8 counts as 8. | `players`, `standings`, `colours`, `pairings`, `history`, `pairing-sheet` |
| `--json` | Print JSON instead of a table. See [JSON output](https://github.com/markjonleonard/chess-results#json-output). | every command |
| `--rounds N` | Stop reading after round N. | the tournament commands; ignored by `players` |
| `--bye-value P` | What a pairing-allocated bye is worth, in points (default 1.0). | the tournament commands; ignored by `players` |
| `--no-crosstable` | Skip the crosstable request. **Scores will be wrong** for anyone whose bye has been deleted from the round's own page. | the tournament commands; ignored by `players` |
| `--delay S` | Seconds to wait between requests (default 1.0). | every command |
| `--no-cache` | Always refetch, ignoring the cache. | every command |
| `--cache-ttl S` | Seconds to reuse a live round's page (default 300). Finished rounds are cached far longer. | the tournament commands; ignored by `players` |
| `--cache-dir D` | Where to keep cached pages (default `~/.cache/chess-results`). | every command |

"The tournament commands" are `standings`, `pairings`, `pairing-sheet`, `colours`,
`history`, `unfinished` and `dump`. `players` reads the starting-rank page alone,
never a round or the crosstable, so the options marked ignored have nothing to act
on there. `sections` and `search` read the tournament search instead of a
tournament, so they too ignore those options.

**`--after` and `--rounds` are different.** `--after N` changes what is *reported*:
the figures as they stood after round N, from rounds already read. `--rounds N`
changes what is *read*: it stops fetching after round N, so nothing later exists at
all. To look at a past round, you want `--after`.

**`--limit`** counts rows of data rather than lines, so the heading is never counted
against it, where `| head -10` counts every line it prints. It saves no time, since
the fetching is done before anything is printed. It is refused on two commands:
`dump`, because a cut-off export would corrupt the data, and `pairing-sheet`,
because a sheet missing its last boards sends players looking for a board that is
not there.

**`--name-width`** is not offered on `dump`, where clipping a name would corrupt
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
Colour values are lower-case `"w"` and `"b"` in Python, where the command line
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
trf = to_trf(event, after=8)    # FIDE TRF(x) through round 8; every game must have a result
```

No separate API reference exists. The classes and their fields are documented in
the source, and [DESIGN.md](https://github.com/markjonleonard/chess-results/blob/main/DESIGN.md)
explains the model.

### A pairing sheet

`pairing-sheet` is a thin wrapper over functions you can call directly, which take
an assembled tournament and touch neither the network nor an engine:

```python
from chess_results import sheet

made = sheet.sheet_from_round(event, 8)          # a published round
print(sheet.render(made, results=True))

pairs = sheet.read_engine_pairs(open("next.txt").read())
made = sheet.sheet_from_pairs(event, pairs)      # an engine's output
made.warnings                                    # what the arbiter must fix by hand
```

`render` leaves the result column off unless asked, where the command turns it on.
It is a primitive and holds no opinion about what your sheet is for.

### Finding sections and tournaments

```python
from chess_results import ChessResults

client = ChessResults()

event = client.sections(823027)
event.summary()     # 'Open 30; Major 25; Intermediate 45; Minor 19; Foundation 25 (2023)'
event.total         # 144
for section in event.sections:
    section.id, section.label, section.players   # ('823027', 'Open', 30), ...

found = client.search("Derbyshire Congress", ends_from="2024-01-01")
found.total         # how many matched, which can exceed len(found)
found.truncated     # True when `limit` cut the list short
found[0].name, found[0].id, found[0].players
```

`search` takes `name`, `tournament_id`, `organizer`, `director`, `arbiter`,
`location`, `ends_from`, `ends_to` (a `date` or `"YYYY-MM-DD"`), `finished_only`
and `limit`, and needs at least one criterion. A response that is not a list of
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
[Finding sections and tournaments](https://github.com/markjonleonard/chess-results#finding-sections-and-tournaments)):

```python
client = ChessResults()
found = client.sections(1346570)
milton_keynes = client.congress({s.label: s.id for s in found.sections}, name=found.name)
```

Pass `skip_unreadable=True` to record a section this tool refuses (an all-play-all
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
round 0, which is not the same as a round drawn nil, so read `kind` alongside it, or
a player who went home after round 2 looks present and beaten in every round after.
And `rating` is the rating the player was paired on, estimates included, which is
not always what the rating list says today.

### Tiebreaks

`chess_results.tiebreaks` has the calculations a Swiss standardly settles ties with
(progressive score, Buchholz, Sonneborn-Berger, black count, head-to-head) as plain
functions over a `Player` and, where a tiebreak needs one, the owning `Tournament`:

```python
from chess_results.tiebreaks import buchholz, progressive_score

mcshane = event.players["Mcshane, Luke J"]
progressive_score(mcshane, after=6)      # rewards a fast start
buchholz(mcshane, event, after=6)        # sum of opponents' scores
```

This is the arithmetic only. It is not a policy for which tiebreaks apply, in what
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
of 50 boards right. Round 2 does not reproduce even with the right players. The
method and the figures are in
[DESIGN.md](https://github.com/markjonleonard/chess-results/blob/main/DESIGN.md#predicting-the-next-round).
Treat a prediction as a good guess, not an announcement.

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
and do not point it at large numbers of tournaments at once.

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

MIT, see [LICENSE](https://github.com/markjonleonard/chess-results/blob/main/LICENSE).
That covers this code only. It says nothing about chess-results.com's data or its
terms of use, which are the site's to set. Check them before you use that data.
Not affiliated with chess-results.com.
