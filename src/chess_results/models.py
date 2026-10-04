"""Data model for chess-results.com tournament data."""

from __future__ import annotations

import datetime
from collections.abc import Iterator
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
    """Strength of a colour preference (FIDE Dutch system, C.04.3 article 1.7)."""

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
    #: The player's team, on a team event's player list (``art=16``).
    team: str | None = None


@dataclass(frozen=True)
class Entrants:
    """The starting-rank page (art=0), read once.

    Works before round 1 is paired, unlike `Tournament`, which needs at least
    one round assembled. ``time_control`` and ``dates`` are only ever set when
    the organiser filled in Swiss-Manager's or ChessManager's tournament
    parameters -- many events, the 2026 British Championship among them,
    publish neither.
    """

    id: str
    name: str | None
    time_control: str | None
    dates: str | None
    players: list[StartingRankEntry]


@dataclass(frozen=True)
class SearchResult:
    """One row of chess-results' tournament search.

    ``players`` is the site's own entrant count, so a search answers "how big is
    it" without a request per tournament. It is as fresh as the search index,
    which a live event updates as it goes.

    The search page's names are not always the tournament's own. It cuts them at
    50 characters, silently -- the section label of a long congress title is
    exactly the part lost -- and it can drop the space where the name had a line
    break, so "2024 Under 1500" arrives as "2024Under 1500". ``name_inexact`` is
    set when ``name`` may be either; the real name is on the tournament's own page.
    """

    id: str
    name: str
    name_inexact: bool = False
    federation: str | None = None
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    director: str | None = None
    organizer: str | None = None
    chief_arbiter: str | None = None
    location: str | None = None
    time_control: str | None = None
    rounds: int | None = None
    players: int | None = None


@dataclass(frozen=True)
class SearchResults:
    """The rows a search returned, and how many matched in all.

    The two differ when the page size cut the list short, and a short list reads
    as a small answer -- so ``total`` is carried rather than discarded, and
    ``truncated`` says so.
    """

    results: list[SearchResult]
    total: int

    @property
    def truncated(self) -> bool:
        return self.total > len(self.results)

    def __iter__(self) -> Iterator[SearchResult]:
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)

    def __getitem__(self, index: int) -> SearchResult:
        return self.results[index]


@dataclass(frozen=True)
class Section:
    """One section of an event: the tournament and what tells it from its siblings."""

    label: str
    result: SearchResult

    @property
    def id(self) -> str:
        return self.result.id

    @property
    def players(self) -> int | None:
        return self.result.players


@dataclass(frozen=True)
class EventSections:
    """The sections of one event, and the headcount of each.

    Grouped by inference, not by anything the site publishes -- see
    :mod:`chess_results.sections`.
    """

    name: str
    sections: list[Section]

    @property
    def start_date(self) -> datetime.date | None:
        return self.sections[0].result.start_date

    @property
    def end_date(self) -> datetime.date | None:
        return self.sections[0].result.end_date

    @property
    def total(self) -> int:
        """Entries across every section; a player in two sections counts twice."""
        return sum(s.players or 0 for s in self.sections)

    def summary(self) -> str:
        """``Open 45; Major 27; Intermediate 44 (2023)``"""
        counts = "; ".join(f"{s.label} {'?' if s.players is None else s.players}" for s in self.sections)
        year = self.start_date.year if self.start_date else None
        return f"{counts} ({year})" if year else counts


@dataclass(frozen=True)
class CrosstableEntry:
    """One player's round as shown in a crosstable (``art=5``).

    The crosstable records byes and skipped rounds as well as games, so it is
    the authority for any round a player's round pages say nothing about.
    """

    round: int
    kind: PlayKind
    #: Starting number of the opponent, for a game.
    opponent_no: int | None = None
    colour: Colour | None = None
    score: float | None = None
    forfeit: bool = False


@dataclass(frozen=True)
class Disagreement:
    """One field where a round's pairing page and the crosstable differ.

    The two views come from the same upload and have always agreed on every
    fixture in the suite, so this is a tripwire rather than a routine event: a
    disagreement means one of the two parsers has misread something.
    """

    player: str
    round: int
    #: The attribute that differs: "kind", "colour", "opponent", "score",
    #: "forfeit", or "total" for a published total that our cells do not sum to.
    field: str
    from_round_page: object = None
    from_crosstable: object = None

    def __str__(self) -> str:
        def show(value: object) -> str:
            return value.value if isinstance(value, Enum) else repr(value)

        if self.field == "total":
            # Both sides come from the crosstable here: our sum of its cells
            # against the total it prints, so the usual wording would mislead.
            return (
                f"{self.player}: the crosstable's rounds sum to "
                f"{show(self.from_round_page)} but it publishes {show(self.from_crosstable)}"
            )
        return (
            f"round {self.round}: {self.player}: {self.field} is "
            f"{show(self.from_round_page)} on the round page "
            f"but {show(self.from_crosstable)} in the crosstable"
        )


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
    #: The starting-rank list's own marker for a woman, when it publishes one
    #: at all -- ``"w"`` on most events, but Warsaw marks men as ``"M"`` instead
    #: and may capitalise the other way too, so callers should compare
    #: case-insensitively rather than against a single literal.
    sex: str | None = None
    #: Assigned to a fixed board number for the whole event.
    fixed_board: bool = False
    plays: list[Play] = field(default_factory=list)

    def play(self, rnd: int) -> Play | None:
        return next((p for p in self.plays if p.round == rnd), None)

    @property
    def fixed_board_number(self) -> int | None:
        """The board this player is currently pinned to, if any.

        chess-results flags *that* a player has a fixed board but never says
        which, so it has to be read back from the boards they actually played
        on, and it is a guess however it is done.

        The guess is the longest unbroken run of one board number, most recent
        run winning a tie. A pin does not necessarily start at round 1 -- Hebden
        played boards 23, 18 and 1 in the 2026 British before settling on 14 from
        round 4 -- so the run is what identifies it. Taking the *modal* board
        instead, as this used to, gets that case wrong for exactly as long as it
        matters: after round 4, when the pin has just begun and every board has
        been played once, the mode is 23.

        A round with no board of its own, a bye, is skipped rather than treated
        as breaking the run.

        It cannot be made exact. Two rounds on the same board by coincidence look
        just like a pin, and a pin the arbiter could not honour one round looks
        like two shorter ones. Treat it as presentational, which is all a fixed
        board ever is: it constrains where a game is played, never who plays whom.
        """
        if not self.fixed_board:
            return None
        played = sorted(self.plays, key=lambda p: p.round)
        boards = [p.board for p in played if p.counts_for_colour and p.board]

        best: int | None = None
        best_length = 0
        run_board: int | None = None
        run_length = 0
        for board in boards:
            run_length = run_length + 1 if board == run_board else 1
            run_board = board
            # >= so that the most recent of equally long runs wins.
            if run_length >= best_length:
                best, best_length = board, run_length
        return best

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
        """The player's due colour and how strongly it is due (FIDE C.04.3, art. 1.7).

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
