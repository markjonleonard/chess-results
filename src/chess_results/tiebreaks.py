"""Generic Swiss tiebreak calculations over an assembled `Tournament`.

These are the calculations themselves, not a policy for when to apply them --
which tiebreaks to use, in what order, and how to handle a prize a congress
defines on its own eligibility rules are questions for the caller. Frome
Congress's Somerset Trophy, for instance, chains these in a specific order to
settle a specific prize; that cascade is its own rule, not a FIDE-mandated
sequence, and does not belong here.

Byes and unpaired rounds have no opponent, so they contribute nothing to any
of these -- `Player.opponents()` already excludes them. `after` selects a
round cutoff the way `Player.score` does, for a tiebreak taken mid-event.

FIDE's own tiebreak regulations (C.02) define edge cases these do not handle
-- a game not played through no fault of a player is scored as a draw against
a "virtual opponent" for Buchholz and Sonneborn-Berger purposes, for instance
-- so treat these as the calculations a congress actually uses in practice,
not a conformant implementation of the regulations.
"""

from __future__ import annotations

from .models import Colour, Player, PlayKind
from .tournament import Tournament


def _opponent_score(tournament: Tournament, name: str, *, after: int | None = None) -> float:
    opponent = tournament.players.get(name)
    return opponent.score(after) if opponent is not None else 0.0


def progressive_score(player: Player, *, after: int | None = None) -> float:
    """Sum of the running score after each round played so far -- rewards a fast start."""
    running = 0.0
    total = 0.0
    for play in sorted(player.plays, key=lambda p: p.round):
        if after is not None and play.round > after:
            break
        running += play.score or 0.0
        total += running
    return total


def buchholz(player: Player, tournament: Tournament, *, after: int | None = None) -> float:
    """Sum of the player's opponents' scores."""
    return sum(_opponent_score(tournament, name, after=after) for name in player.opponents(after))


def sonneborn_berger(player: Player, tournament: Tournament, *, after: int | None = None) -> float:
    """Like Buchholz, but an opponent's score counts only for a win (full) or a draw (half)."""
    total = 0.0
    for play in player.plays:
        if after is not None and play.round > after:
            continue
        if not play.opponent:
            continue
        opponent_score = _opponent_score(tournament, play.opponent, after=after)
        if play.score == 1.0:
            total += opponent_score
        elif play.score == 0.5:
            total += opponent_score / 2
    return total


def black_count(player: Player, *, after: int | None = None) -> int:
    """Number of games played with black -- FIDE's usual last-resort tiebreak."""
    return sum(1 for c in player.colours(after) if c is Colour.BLACK)


def head_to_head(player: Player, opponent_name: str, *, after: int | None = None) -> float | None:
    """The result of the game between this player and a named opponent.

    From this player's perspective: 1.0 a win, 0.5 a draw, 0.0 a loss. None if
    they never played each other (in or before `after`, if given).
    """
    for play in player.plays:
        if after is not None and play.round > after:
            continue
        if play.kind is PlayKind.GAME and play.opponent == opponent_name:
            return play.score
    return None
