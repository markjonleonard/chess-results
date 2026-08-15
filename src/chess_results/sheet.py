"""Render a round's pairings as a sheet to print and pin to a noticeboard.

The audience is a player walking up to a wall, not a terminal. So this module
is fixed-width text with a repeated heading and form-feed page breaks, and it
takes the two things a printed sheet must get right and a screen one need not:

**Board numbers are assigned, not enumerated.** A pairing engine emits a set of
pairs and no ordering (see :mod:`chess_results.trf`), so numbering them in the
order they came out sends players to arbitrary tables. :func:`assign_boards`
orders them the way arbiter software does -- by the higher-ranked player in each
pair, top scoregroup first -- and then honours fixed boards.

**Fixed boards are placed, not footnoted.** A player pinned to one board is
usually pinned on access grounds, so a note at the bottom of the sheet that
nobody transcribes is not good enough: the pair goes on that board, and if two
pins collide the sheet says so rather than quietly dropping one.

Nothing here touches the network or an engine. It takes an assembled
:class:`~chess_results.tournament.Tournament` and a list of pairs, so it can be
tested offline against the fixtures like every other layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Pairing, Player, PlayKind
from .tournament import Tournament

#: What a bye row prints where the opponent's name would go. The three are not
#: interchangeable on a wall: a player who asked for a half-point bye is being
#: told their request was granted, a player who is "not paired" is being told
#: something they may need to query with the arbiter, and only the first is a
#: full point. `cmd_pairings` draws the same distinction on screen.
BYE_TEXT = "bye"
NOT_PLAYING_TEXT = {
    PlayKind.PAIRING_BYE: BYE_TEXT,
    PlayKind.REQUESTED_BYE: "half-point bye",
    PlayKind.UNPAIRED: "not paired",
}

#: Room a name gets before it is clipped. 28 keeps the two name columns inside
#: 80, which is what a printer fed plain text gives you before it wraps -- and a
#: wrapped pairing row is far worse on a wall than a clipped name.
NAME_WIDTH = 28

#: Width of the result column. 6 holds the widest thing that goes in it,
#: "1-0F", with room either side to write "1/2" by hand in a box that is not
#: already full.
RESULT_WIDTH = 6

#: Lines on a printed page. 66 is the line-printer default at 6 lines per inch
#: on both A4 and US Letter, which is what an office printer fed plain text
#: will use.
LINES_PER_PAGE = 66

#: Separates pages. A printer treats it as "eject and start the next sheet";
#: `less` and most terminals show it as ^L.
FORM_FEED = "\f"


class SheetError(ValueError):
    """The pairings cannot be made into a sheet."""


@dataclass(frozen=True)
class SheetRow:
    """One line of the sheet: a board, or a bye."""

    #: None on a bye row -- a player who is not playing has no table to go to.
    board: int | None
    white: Player
    black: Player | None
    #: This board was chosen to honour a player's fixed board, not by ranking.
    pinned: bool = False
    #: What a row with no opponent says instead of a name. A pairing engine only
    #: ever means a full-point bye, so that is the default; a published round
    #: distinguishes the three (see :data:`NOT_PLAYING_TEXT`).
    note: str = BYE_TEXT
    #: The game's result, where one is known: "1-0", "½-½", "0-1", "1-0F". Empty
    #: for a game not yet played, which is what leaves the arbiter room to write
    #: it in by hand.
    result: str = ""

    @property
    def is_bye(self) -> bool:
        return self.black is None


@dataclass(frozen=True)
class PairingSheet:
    """A round's pairings, ordered and numbered, ready to render."""

    event: str
    round: int
    rows: list[SheetRow]
    #: Anything the arbiter must resolve by hand before pinning this up, such as
    #: two fixed boards wanting the same table. Rendered on the sheet itself.
    warnings: list[str] = field(default_factory=list)

    @property
    def boards(self) -> int:
        return sum(1 for row in self.rows if not row.is_bye)


def _rank_index(event: Tournament, after: int | None) -> dict[str, int]:
    """Each player's position in ranking order, for sorting pairs by strength."""
    return {player.name: i for i, player in enumerate(event.ranking_order(after))}


def assign_boards(
    event: Tournament,
    pairs: list[tuple[Player, Player | None]],
    *,
    after: int | None = None,
) -> tuple[list[SheetRow], list[str]]:
    """Number a round's pairs the way an arbiter would, and honour fixed boards.

    ``pairs`` is white and black for each board, black ``None`` for a bye.
    ``after`` is the round the standings are taken from -- the round *before*
    the one being paired.

    Boards run from the strongest pair down: each pair is ranked by its better
    player's position in :meth:`Tournament.ranking_order`, which puts the top
    scoregroup on board 1 and keeps a scoregroup's boards together. That is a
    convention rather than a rule, and an arbiter may renumber; it is chosen
    because it is what players expect to find on the wall.

    Byes take no board and sort last, since there is no table to send the player
    to.

    Fixed boards are then placed on top of that ordering, and a pin wins over
    the ranking -- that is the whole point of one. Returns the rows and any
    warnings, which are *not* raised: a sheet an arbiter must correct by hand is
    far more use at five minutes to the round than an exception.
    """
    rank = _rank_index(event, after)
    last = len(rank)

    def strength(pair: tuple[Player, Player | None]) -> tuple[int, int]:
        white, black = pair
        sides = [rank.get(white.name, last)]
        if black is not None:
            sides.append(rank.get(black.name, last))
        return min(sides), max(sides)

    games = sorted((p for p in pairs if p[1] is not None), key=strength)
    byes = sorted((p for p in pairs if p[1] is None), key=strength)

    placed: dict[int, tuple[Player, Player | None]] = {}
    warnings: list[str] = []
    unplaced = list(games)

    for pair in games:
        pins = {
            player.fixed_board_number
            for player in (pair[0], pair[1])
            if player is not None and player.fixed_board_number is not None
        }
        if not pins:
            continue
        names = " and ".join(p.name for p in (pair[0], pair[1]) if p is not None and p.fixed_board)
        if len(pins) > 1:
            warnings.append(
                f"{names} are pinned to different boards ({', '.join(str(b) for b in sorted(pins))}) "
                "and are playing each other; this sheet uses the lower one"
            )
        board = min(pins)
        if not 1 <= board <= len(games):
            warnings.append(
                f"{names} is pinned to board {board}, which this round does not have "
                f"({len(games)} boards); placed by ranking instead"
            )
            continue
        if board in placed:
            other = placed[board]
            held = " v ".join(p.name for p in other if p is not None)
            warnings.append(
                f"board {board} is wanted by two pinned players: {held} has it, "
                f"so {names} is placed by ranking instead"
            )
            continue
        placed[board] = pair
        unplaced.remove(pair)

    rows: list[SheetRow] = []
    spare = iter(unplaced)
    for board in range(1, len(games) + 1):
        if board in placed:
            white, black = placed[board]
            rows.append(SheetRow(board, white, black, pinned=True))
        else:
            white, black = next(spare)
            rows.append(SheetRow(board, white, black))
    rows.extend(SheetRow(None, white, None) for white, _ in byes)
    return rows, warnings


def sheet_from_pairs(
    event: Tournament,
    pairs: list[tuple[int, int]],
    *,
    round_number: int | None = None,
    after: int | None = None,
) -> PairingSheet:
    """Build a sheet from a pairing engine's output.

    ``pairs`` is bbpPairings' own shape: starting numbers, black ``0`` for a
    bye. See :func:`read_engine_pairs` for turning its file into that.

    Defaults describe the round being predicted: the pairs are for the round
    after the last one scraped, and the scores they were computed from are the
    ones as of that last round.
    """
    after = event.last_round if after is None else after
    round_number = after + 1 if round_number is None else round_number
    by_no = {p.start_no: p for p in event.players.values() if p.start_no is not None}

    resolved: list[tuple[Player, Player | None]] = []
    for white_no, black_no in pairs:
        if white_no not in by_no:
            raise SheetError(f"no player has starting number {white_no}")
        if black_no and black_no not in by_no:
            raise SheetError(f"no player has starting number {black_no}")
        resolved.append((by_no[white_no], by_no[black_no] if black_no else None))

    rows, warnings = assign_boards(event, resolved, after=after)
    return PairingSheet(event.name or str(event.id), round_number, rows, warnings)


def sheet_from_round(event: Tournament, rnd: int) -> PairingSheet:
    """Build a sheet from a round chess-results has already published.

    Unlike :func:`sheet_from_pairs` this keeps the *published* board numbers,
    which are the arbiter's own and beat any convention we could apply. Useful
    for reprinting a sheet that came off the wall, or for the round that has
    just been paired and uploaded.

    **The round page alone is not the round.** Once a later round is paired,
    chess-results deletes that round's bye and "not paired" rows, so a superseded
    round page lists only its games -- round 6 of the 2026 British has 52 rows
    for a field of 108, missing a full-point bye and three absentees. Those
    players are still in `Player.plays`, recovered from the crosstable, so they
    are added back here. Leaving them off would print a sheet that silently drops
    whoever is not playing, which on a wall reads as "no bye was given".
    """
    pairings = event.rounds.get(rnd)
    if not pairings:
        raise SheetError(f"round {rnd} has no pairings")
    rows = [
        SheetRow(
            p.board if p.kind is PlayKind.GAME else None,
            event.player(p.white.name),
            event.player(p.black.name) if p.black is not None else None,
            note=NOT_PLAYING_TEXT.get(p.kind, BYE_TEXT),
            result=_result(p),
        )
        for p in pairings
    ]

    on_page = {p.white.name for p in pairings} | {p.black.name for p in pairings if p.black}
    recovered = [
        (player, play)
        for player, play in ((p, p.play(rnd)) for p in event.players.values() if p.name not in on_page)
        if play is not None
    ]
    # By starting number, the only ordering these have: a recovered play carries
    # no board and no pre-round score, the crosstable publishing neither.
    recovered.sort(key=lambda item: item[0].start_no or 0)
    rows.extend(
        SheetRow(None, player, None, note=NOT_PLAYING_TEXT.get(play.kind, BYE_TEXT))
        for player, play in recovered
    )
    return PairingSheet(event.name or str(event.id), rnd, rows)


def read_engine_pairs(text: str) -> list[tuple[int, int]]:
    """Parse bbpPairings' ``-p`` output: a count, then one pair per line.

    A pair is two starting numbers, ``0`` for the bye's non-existent opponent.
    The count is checked rather than skipped, because a truncated file otherwise
    prints a short sheet that looks like a small round.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise SheetError("no pairings: the engine wrote an empty file")
    try:
        expected = int(lines[0].strip())
    except ValueError as exc:
        raise SheetError(f"expected a pair count on the first line, got {lines[0].strip()!r}") from exc

    pairs: list[tuple[int, int]] = []
    for number, line in enumerate(lines[1:], start=1):
        fields = line.split()
        if len(fields) != 2 or not all(f.lstrip("-").isdigit() for f in fields):
            raise SheetError(f"pair {number} is not two starting numbers: {line.strip()!r}")
        pairs.append((int(fields[0]), int(fields[1])))
    if len(pairs) != expected:
        raise SheetError(f"the file says {expected} pairings but lists {len(pairs)}")
    return pairs


def _points(value: float) -> str:
    """Scores as an arbiter writes them: 2½, not 2.5."""
    whole, half = divmod(round(value * 2), 2)
    return f"{whole if whole or not half else ''}{'½' if half else ''}" or "0"


def _result(pairing: Pairing) -> str:
    """A finished game's result, or empty for one still to be played.

    Empty rather than a dash: on a results chart the column is what the arbiter
    writes into, and a dash in the box is something to cross out first.
    """
    if pairing.kind is not PlayKind.GAME or pairing.white_score is None:
        return ""
    forfeit = "F" if pairing.forfeit else ""
    return f"{_points(pairing.white_score)}-{_points(pairing.black_score or 0)}{forfeit}"


def _describe(player: Player, after: int | None) -> tuple[str, str]:
    """A player's name and carried-in score, as the two columns want them."""
    title = f"{player.title} " if player.title else ""
    return f"{title}{player.name}", _points(player.score(after))


def render(
    sheet: PairingSheet,
    *,
    after: int | None = None,
    name_width: int = NAME_WIDTH,
    lines_per_page: int = LINES_PER_PAGE,
    subtitle: str | None = None,
    results: bool = False,
) -> str:
    """Render the sheet as fixed-width text, paginated with form feeds.

    ``after`` is the round whose scores are shown beside each name; it defaults
    to the round before this one. ``subtitle`` is a free line under the heading
    for whatever the hall needs that no page publishes -- start time, venue,
    "round 8 pairings, provisional".

    ``results`` adds the result column between the two players, where
    Swiss-Manager's own pairing chart puts it. A game already decided prints its
    result; one still to be played leaves the box empty for the arbiter to write
    into. Names lose four characters to it, the whole row having to stay inside
    the 80 columns a printer gives plain text.

    Every page repeats the heading, because a sheet pinned up as several pages
    is read as several sheets. ``lines_per_page`` of 0 turns pagination off, for
    piping somewhere that is not a printer.
    """
    after = sheet.round - 1 if after is None else after
    heading = [
        f"{sheet.event}",
        f"Round {sheet.round} pairings",
    ]
    if subtitle:
        heading.append(subtitle)

    if results:
        name_width = max(1, name_width - RESULT_WIDTH // 2 - 1)
        middle = f"  {'Result':^{RESULT_WIDTH}}  "
    else:
        middle = "   "
    columns = f"{'Bd':>3}  {'White':<{name_width}} {'Pts':>3}{middle}{'Black':<{name_width}} {'Pts':>3}"
    rule = "-" * len(columns)

    body: list[str] = []
    for row in sheet.rows:
        white, white_pts = _describe(row.white, after)
        board = "-" if row.board is None else str(row.board)
        if row.black is None:
            black, black_pts = row.note, ""
        else:
            black, black_pts = _describe(row.black, after)
        if results:
            # A bye has no result to write in, so its box stays blank rather
            # than being ruled off -- nothing is owed for a game not played.
            cell = "" if row.is_bye else row.result
            gap = f"  {cell:^{RESULT_WIDTH}}  "
        else:
            gap = "   "
        line = (
            f"{board:>3}  {white[:name_width]:<{name_width}} {white_pts:>3}{gap}"
            f"{black[:name_width]:<{name_width}} {black_pts:>3}"
        )
        body.append(line.rstrip() + ("  *" if row.pinned else ""))

    footer: list[str] = []
    if any(row.pinned for row in sheet.rows):
        footer.append("* board fixed for this player")
    footer.extend(f"! {text}" for text in sheet.warnings)

    return _paginate(heading, columns, rule, body, footer, lines_per_page)


def _paginate(
    heading: list[str],
    columns: str,
    rule: str,
    body: list[str],
    footer: list[str],
    lines_per_page: int,
) -> str:
    """Break the body across pages, repeating the heading on each.

    The footer goes on the last page only -- it is a note about the sheet, not
    about the page -- and takes its own room out of that page's rows.
    """
    top = [*heading, "", columns, rule]
    tail = ["", *footer] if footer else []

    if lines_per_page <= 0:
        return "\n".join([*top, *body, *tail]) + "\n"

    room = lines_per_page - len(top) - 1  # 1 for the page number line
    if room < 1:
        raise SheetError(f"lines_per_page={lines_per_page} leaves no room for a single pairing")

    # The footer competes with rows for space on the final page, so that page
    # holds fewer. Rows are then spread evenly rather than packed from the
    # front: packing can fill the early pages so completely that the last one
    # has no room left for the footer, or nothing on it but the footer.
    last_room = max(1, room - len(tail))
    total = 1
    while True:
        base, extra = divmod(len(body), total)
        # Larger pages first, so the smallest is last and meets the tighter limit.
        sizes = [base + 1] * extra + [base] * (total - extra)
        if max(sizes) <= room and sizes[-1] <= last_room:
            break
        total += 1

    chunks: list[list[str]] = []
    taken = 0
    for size in sizes:
        chunks.append(body[taken : taken + size])
        taken += size

    rendered = []
    for number, chunk in enumerate(chunks, start=1):
        page = [*top, *chunk]
        if number == len(chunks):
            page.extend(tail)
        page.append(f"page {number} of {len(chunks)}")
        rendered.append("\n".join(page))
    return (FORM_FEED + "\n").join(rendered) + "\n"
