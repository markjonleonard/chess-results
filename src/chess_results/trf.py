"""Export a scraped tournament to FIDE TRF(x), the format pairing engines read.

TRF is a fixed-column format. Field positions below are 1-based, matching the
FIDE Technical Commission's specification, and are what JaVaFo and bbpPairings
expect:

===========  ==========================================
Columns      Contents
===========  ==========================================
1-3          ``001`` (player record)
5-8          starting rank number
10           sex
11-13        title
15-47        name
49-52        rating
54-56        federation
58-68        FIDE ID
70-79        date of birth
81-84        points
86-89        rank
92-95        round 1 opponent's starting rank number
97           round 1 colour
99           round 1 result
===========  ==========================================

Each further round repeats the last three fields shifted ten columns right.
"""

from __future__ import annotations

from .models import Colour, Play, Player, PlayKind
from .tournament import Tournament

#: Result characters, as accepted by bbpPairings and JaVaFo.
RESULT_WIN = "1"
RESULT_DRAW = "="
RESULT_LOSS = "0"
RESULT_FORFEIT_WIN = "+"
RESULT_FORFEIT_LOSS = "-"
RESULT_PAIRING_BYE = "U"
RESULT_HALF_POINT_BYE = "H"
RESULT_ZERO_POINT_BYE = "Z"

_ROUND_START = 92
_ROUND_WIDTH = 10


class TrfError(ValueError):
    """The tournament cannot be represented as TRF."""


def _place(line: list[str], start: int, width: int, text: str, *, right: bool = False) -> None:
    text = text[:width]
    text = text.rjust(width) if right else text.ljust(width)
    end = start - 1 + width
    if len(line) < end:
        line.extend(" " * (end - len(line)))
    line[start - 1 : end] = list(text)


def _points(value: float) -> str:
    return f"{value:.1f}"


def _result_char(play: Play) -> str:
    if play.kind is PlayKind.PAIRING_BYE:
        return RESULT_PAIRING_BYE
    if play.kind is PlayKind.REQUESTED_BYE:
        return RESULT_HALF_POINT_BYE if play.score else RESULT_ZERO_POINT_BYE
    if play.kind is PlayKind.UNPAIRED:
        return RESULT_ZERO_POINT_BYE
    if play.forfeit:
        return RESULT_FORFEIT_WIN if play.score else RESULT_FORFEIT_LOSS
    if play.score == 1:
        return RESULT_WIN
    if play.score == 0.5:
        return RESULT_DRAW
    return RESULT_LOSS


def player_line(
    player: Player,
    rank: int,
    numbers: dict[str, int],
    after: int,
    *,
    withdrawn: bool = False,
) -> str:
    """Render one ``001`` record.

    ``withdrawn`` adds a zero-point-bye entry for the round after ``after``,
    which is how a pairing engine is told to leave a player out of it.
    """
    if player.start_no is None:
        raise TrfError(f"{player.name} has no starting rank number")

    line: list[str] = []
    _place(line, 1, 3, "001")
    _place(line, 5, 4, str(player.start_no), right=True)
    _place(line, 11, 3, player.title or "")
    _place(line, 15, 33, player.name)
    _place(line, 49, 4, str(player.rating or 0), right=True)
    _place(line, 54, 3, player.federation or "")
    _place(line, 58, 11, player.fide_id or "")
    _place(line, 81, 4, _points(player.score(after)), right=True)
    _place(line, 86, 4, str(rank), right=True)

    for rnd in range(1, after + 1):
        play = player.play(rnd)
        start = _ROUND_START + (rnd - 1) * _ROUND_WIDTH
        if play is None:
            # Absent from the round entirely: score nothing, stay pairable.
            _place(line, start, 4, "0000", right=True)
            _place(line, start + 5, 1, "-")
            _place(line, start + 7, 1, RESULT_ZERO_POINT_BYE)
            continue
        if play.opponent is None:
            opponent_no = "0000"
            colour = "-"
        else:
            if play.opponent not in numbers:
                raise TrfError(f"round {rnd}: unknown opponent {play.opponent!r}")
            opponent_no = str(numbers[play.opponent])
            colour = "w" if play.colour is Colour.WHITE else "b"
        _place(line, start, 4, opponent_no, right=True)
        _place(line, start + 5, 1, colour)
        _place(line, start + 7, 1, _result_char(play))

    if withdrawn:
        start = _ROUND_START + after * _ROUND_WIDTH
        _place(line, start, 4, "0000", right=True)
        _place(line, start + 5, 1, "-")
        _place(line, start + 7, 1, RESULT_ZERO_POINT_BYE)

    return "".join(line).rstrip()


def to_trf(
    event: Tournament,
    *,
    after: int | None = None,
    total_rounds: int | None = None,
    bye_value: float | None = None,
    withdrawn: set[str] | None = None,
) -> str:
    """Render a tournament as TRF(x), covering rounds 1..``after``.

    Every game in those rounds must have a result: a pairing engine reads scores
    as fact and bbpPairings rejects a file whose points do not match its results.
    Use ``Tournament.unfinished()`` to find gaps, and decide them before calling
    this (that is the "assume X wins" step of any prediction).

    ``total_rounds`` becomes the ``XXR`` line -- the engine needs it to know
    whether it is pairing the final round, which changes the colour rules.

    ``bye_value`` is written as a ``BBU`` line, bbpPairings' extension for what a
    pairing-allocated bye is worth. It defaults to the tournament's own value and
    is omitted for the standard full point, which needs no declaration. Getting
    this wrong is not cosmetic: bbpPairings recomputes every player's score from
    their results and refuses the file outright if the total disagrees.
    """
    # Clamped: a round beyond the last one played would pad every player line
    # with empty round columns and inflate XXR, which a pairing engine misreads.
    after = event.last_round if after is None else max(1, min(after, event.last_round))
    unfinished = [
        (rnd, p)
        for rnd in range(1, after + 1)
        for p in event.rounds.get(rnd, [])
        if p.kind is PlayKind.GAME and p.white_score is None
    ]
    if unfinished:
        rnd, first = unfinished[0]
        raise TrfError(
            f"{len(unfinished)} game(s) in rounds 1-{after} have no result, "
            f"e.g. round {rnd} board {first.board}: {first.white.name} vs "
            f"{first.black.name if first.black else '?'}"
        )

    ranking = event.ranking_order(after)
    numbers = {p.name: p.start_no for p in event.players.values() if p.start_no is not None}

    lines = []
    if event.name:
        lines.append(f"012 {event.name}")
    lines.extend(
        player_line(player, rank, numbers, after, withdrawn=player.name in (withdrawn or set()))
        for rank, player in enumerate(ranking, start=1)
    )
    lines.append(f"XXR {total_rounds or after + 1}")
    bye_value = event.bye_value if bye_value is None else bye_value
    if bye_value != 1.0:
        lines.append(f"BBU {bye_value:4.1f}")
    return "\n".join(lines) + "\n"
