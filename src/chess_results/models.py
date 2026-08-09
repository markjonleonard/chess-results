"""Data model for chess-results.com tournament data."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum


class Colour(str, Enum):
    WHITE = "w"
    BLACK = "b"

    @property
    def other(self) -> Colour:
        return Colour.BLACK if self is Colour.WHITE else Colour.WHITE


class PlayKind(str, Enum):
    """How a player occupied a round."""

    GAME = "game"
    #: Pairing-allocated bye: shown by chess-results as an opponent named "bye".
    PAIRING_BYE = "pairing_bye"
    #: Requested (usually half-point) bye: "not paired" with a result value.
    REQUESTED_BYE = "requested_bye"
    #: Present in the list but neither paired nor awarded anything.
    UNPAIRED = "unpaired"


class Preference(str, Enum):
    """Strength of a colour preference (FIDE C.04.2.D)."""

    ABSOLUTE = "absolute"
    STRONG = "strong"
    MILD = "mild"
    NONE = "none"


@dataclass(frozen=True)
class PlayerRef:
    """A player as named on a pairing row."""

    name: str
    rating: int | None = None
    title: str | None = None
    start_no: int | None = None
    #: Footnote marker chess-results appended to the name, e.g. ``*)``.
    marker: str | None = None
    #: True when the page's legend explains the marker as a fixed board
    #: assignment -- a player who plays at one board number every round,
    #: usually on access or health grounds. It constrains where the game is
    #: played, not who plays whom.
    fixed_board: bool = False


@dataclass
class Pairing:
    """One row of a round's pairing table."""

    round: int
    board: int
    white: PlayerRef
    black: PlayerRef | None
    kind: PlayKind
    #: Points each player held *before* this round, as displayed.
    white_points_before: float | None = None
    black_points_before: float | None = None
    #: Result of the game, or the value awarded for a bye. None = not yet played.
    white_score: float | None = None
    black_score: float | None = None
    #: Raw contents of the Result cell, kept for debugging and round-tripping.
    raw_result: str = ""
    forfeit: bool = False

    @property
    def played(self) -> bool:
        return self.kind is PlayKind.GAME and self.white_score is not None


@dataclass(frozen=True)
class StartingRankEntry:
    """One row of the starting-rank list (art=0)."""

    start_no: int
    name: str
    rating: int | None = None
    title: str | None = None
    fide_id: str | None = None
    federation: str | None = None
    local_id: str | None = None
    sex: str | None = None
    type: str | None = None


@dataclass(frozen=True)
class CrosstableEntry:
    """One player's round as shown in a crosstable (``art=5``).

    The crosstable is the only view that keeps byes and skipped rounds after
    the round has been superseded, so it is the authority for those.
    """

    round: int
    kind: PlayKind
    #: Starting number of the opponent, for a game.
    opponent_no: int | None = None
    colour: Colour | None = None
    score: float | None = None
    forfeit: bool = False


class Absence(str, Enum):
    """A marker printed in a round column of the "not paired" page (``art=40``).

    Deliberately *not* a :class:`PlayKind`. ``UNPLAYED`` covers both a genuine
    absence and a requested half-point bye, which the page renders identically --
    see :func:`chess_results.parse.parse_not_paired`.
    """

    #: The player did not occupy the round: withdrawn, a late entry, or a
    #: requested bye. The page does not say which.
    UNPLAYED = "*"
    #: A pairing-allocated bye, worth a full point.
    BYE = "bye"
    #: The player forfeited: a game they were paired for but did not play.
    FORFEIT = "0F"


@dataclass(frozen=True)
class NotPairedEntry:
    """One player's row on the "not paired" page (``art=40``).

    A single page listing everyone who missed at least one round, as a grid of
    one column per round. Unlike the crosstable it names the player as well as
    numbering them, so it joins to a name-keyed field without the starting-rank
    list.
    """

    start_no: int
    name: str
    rating: int | None = None
    title: str | None = None
    federation: str | None = None
    #: Round number to the marker printed for it. Rounds the player played are
    #: simply absent.
    markers: dict[int, Absence] = field(default_factory=dict)

    def rounds(self, marker: Absence) -> set[int]:
        """The rounds carrying one particular marker."""
        return {rnd for rnd, value in self.markers.items() if value is marker}

    @property
    def missed(self) -> set[int]:
        """Every round the player did not play, whatever the reason."""
        return set(self.markers)


@dataclass
class Play:
    """What one player did in one round."""

    round: int
    kind: PlayKind
    colour: Colour | None = None
    opponent: str | None = None
    score: float | None = None
    points_before: float | None = None
    board: int | None = None
    forfeit: bool = False
    #: "D" if the player was paired down a scoregroup, "U" if paired up, else None.
    #: Inferred by comparing the two players' displayed pre-round scores.
    float_direction: str | None = None
    #: True when this round was recovered from the crosstable because the
    #: pairing page no longer lists it. Such a play has no board number and no
    #: pre-round score, since the crosstable does not publish them.
    from_crosstable: bool = False

    @property
    def counts_for_colour(self) -> bool:
        """Byes and unplayed games do not contribute to colour history."""
        return self.kind is PlayKind.GAME and self.colour is not None


@dataclass
class Player:
    """A player's whole tournament, assembled across rounds."""

    name: str
    start_no: int | None = None
    rating: int | None = None
    title: str | None = None
    federation: str | None = None
    fide_id: str | None = None
    #: Assigned to a fixed board number for the whole event.
    fixed_board: bool = False
    plays: list[Play] = field(default_factory=list)

    def play(self, rnd: int) -> Play | None:
        return next((p for p in self.plays if p.round == rnd), None)

    @property
    def fixed_board_number(self) -> int | None:
        """The board this player is pinned to, if any.

        chess-results flags *that* a player has a fixed board but never says
        which, so it is read back from the boards they actually played on.
        """
        if not self.fixed_board:
            return None
        boards = [p.board for p in self.plays if p.counts_for_colour and p.board]
        return Counter(boards).most_common(1)[0][0] if boards else None

    def score(self, after: int | None = None) -> float:
        """Points scored, counting only rounds with a known result."""
        return sum(p.score for p in self.plays if p.score is not None and (after is None or p.round <= after))

    def opponents(self, after: int | None = None) -> list[str]:
        return [p.opponent for p in self.plays if p.opponent and (after is None or p.round <= after)]

    def colours(self, after: int | None = None) -> list[Colour]:
        """Colour history, oldest first, skipping byes and unplayed rounds."""
        # The `is not None` is what `counts_for_colour` already guarantees, spelled
        # out again so the element type is Colour rather than Colour | None.
        return [
            p.colour
            for p in self.plays
            if p.colour is not None and p.counts_for_colour and (after is None or p.round <= after)
        ]

    def colour_difference(self, after: int | None = None) -> int:
        """Whites minus blacks."""
        cols = self.colours(after)
        return sum(1 for c in cols if c is Colour.WHITE) - sum(1 for c in cols if c is Colour.BLACK)

    def colour_preference(self, after: int | None = None) -> tuple[Colour | None, Preference]:
        """The player's due colour and how strongly it is due (FIDE C.04.2.D).

        Absolute when the colour difference is +/-2 or more, or when the two most
        recent games were the same colour. Strong at +/-1. Mild at 0, being the
        opposite of the most recent colour. None for a player yet to play.
        """
        cols = self.colours(after)
        if not cols:
            return None, Preference.NONE
        diff = self.colour_difference(after)
        if abs(diff) >= 2:
            return (Colour.BLACK if diff > 0 else Colour.WHITE), Preference.ABSOLUTE
        if len(cols) >= 2 and cols[-1] is cols[-2]:
            return cols[-1].other, Preference.ABSOLUTE
        if diff != 0:
            return (Colour.BLACK if diff > 0 else Colour.WHITE), Preference.STRONG
        return cols[-1].other, Preference.MILD
