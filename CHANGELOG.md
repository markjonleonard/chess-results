# Changelog

## Unreleased

### New

- `players -v` (`--verbose`) prints the organiser, tournament director, chief arbiter,
  deputy chief arbiter and arbiters where the event publishes them, and its JSON
  carries them as `organizer`, `director`, `chief_arbiter`, `deputy_chief_arbiter` and
  `arbiters`. For an event that ended more than five days ago this costs two requests
  more the first time, because chess-results hides the details behind a button, and
  the answer is cached for good, since the event is over. `-v` also brings
  back that event's dates and time control. They are fields of `Entrants` too;
  `entrants(id, details=False)` skips the button.
- The time control is read where the page labels it with its rate, such as
  "Time control (Standard)", and a live event's dates and time control are read
  wherever its page publishes them, not only on the few pages that printed them
  unasked.

### Changed

- `--bye-value` is no longer needed. What a pairing-allocated bye is worth is read from
  the round pages' pre-round scores once a player has had one, at no cost in requests,
  and a value other than a full point is reported on stderr. Without evidence it is a
  full point as before, and a value you give still wins. `tournament()` and
  `congress()` take `bye_value=None` for this; `Tournament.bye_value_inferred` says
  whether it was read.

### Fixes

- **A requested half-point bye that a round page calls `bye` is read as one.** Both the
  score and the kind were wrong: it counted a full point and was reported as a pairing
  bye, disagreeing with the crosstable. The Result cell's printed value is now used for a
  `bye` row where there is one, and the crosstable's `-½` marks the bye as requested.
- **A refetched starting rank updates ratings.** While an event is live the starting rank
  is fetched again, and a rating an arbiter had corrected was ignored in favour of the
  first one read.

## 0.2.0 (2026-10-04)

### Fixes worth upgrading for

- **Bye and "not paired" rows are read on every round page.** Once a round's games are
  published, its page gains a `PGN` column that those rows have no cell for, and 0.1.0
  skipped them. With the crosstable, the default, scores were still right, because it
  filled the rounds in. With `--no-crosstable` or `crosstable=False`, everyone who took
  a full-point bye scored a point short: four players in the 2026 British Championship.
- **Starting numbers are refetched while a tournament is live.** An arbiter can renumber
  the field mid-event, and a cached starting-rank list then matched crosstable rows to
  the wrong players.

### Changes a script may notice

- A round robin, or a tournament that has not started, now exits 2 with a one-line
  message where 0.1.0 printed an empty report; from Python it raises `RoundRobinError`
  or `TournamentNotStartedError`. A number with no tournament behind it does the same,
  with `TournamentNotFoundError`. All three are `TournamentError`s.
- A network failure prints one line on stderr and exits 1, not a traceback.
- `--limit` and `--name-width` are common options, accepted either side of the command.
  A command that cannot use one refuses it rather than ignoring it.
- The usage line and help say "tournament number", as the README does.
- `dump`'s JSON is unchanged apart from a new `sex` key on each player.

### New

- Commands: `players` (the field, before round 1 too, team events included), `history`,
  `pairing-sheet`, `search` and `sections`.
- `--json` on every command, `--after` on `pairing-sheet` and `history`, and
  `standings --women`.
- From Python: `ChessResults.entrants`, `.search` and `.sections`; `Congress` for the
  sections of one event; `Tournament.rows()` for a DataFrame; the usual Swiss tie-breaks
  in `chess_results.tiebreaks`; `Tournament.performance_rating`; and every exception
  importable from `chess_results`.
- Examples: `validate_prediction.py` points out a likely substitution made after
  pairing; `predict_next_round.py` predicts round 1 of an event that has not started;
  and two new scripts predict several rounds ahead and a player's next ECF rating.

The full guide is [USAGE.md](USAGE.md).

## 0.1.0 (2026-08-10)

First release.
