"""Parsers for chess-results.com HTML pages.

All parsing is driven by the table's header row rather than by fixed column
offsets. chess-results renders a single header row that mixes ``<th>`` (for
labelled columns) with ``<td>`` (for the two player-name columns), and it omits
columns a tournament has switched off -- the starting-rank ``No.`` columns in
particular. Reading ``th`` and ``td`` together yields a header that aligns one
to one with the data rows, whatever the tournament's display settings.

Pages must be requested with ``lan=1`` (English); the parsers key off English
column labels and the words "bye" / "not paired".
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from .models import Colour, CrosstableEntry, Pairing, PlayerRef, PlayKind, StartingRankEntry

#: chess-results marks its data tables with this class.
TABLE_CLASS = "CRs1"

#: Values that appear in the Black name column instead of a real opponent.
BYE_LABEL = "bye"
UNPAIRED_LABEL = "not paired"

#: Trailing annotations chess-results appends to names, e.g. "Hebden, Mark L *)".
_NAME_SUFFIX = re.compile(r"\s*(\*+\)?)\s*$")

#: A marker and the sentence explaining it, printed below the pairing table.
_LEGEND = re.compile(r"(\*+\))\s*([A-Z][^.]{3,200}\.)")

#: Wording chess-results uses for a player pinned to one board all event.
_FIXED_BOARD = "fixed board"


def clean_name(text: str) -> str:
    """Strip footnote markers and collapse whitespace in a player name."""
    return _NAME_SUFFIX.sub("", " ".join(text.split()))


def split_name_marker(text: str) -> tuple[str, str | None]:
    """Split a name cell into its name and any footnote marker."""
    text = " ".join(text.split())
    match = _NAME_SUFFIX.search(text)
    return (text[: match.start()], match.group(1)) if match else (text, None)


def parse_legend(html: str) -> dict[str, str]:
    """Read the footnote legend printed below a pairing table.

    Returns marker to explanation, e.g. ``{"*)": "This player is assigned to a
    fixed board."}``. Empty when the tournament has no annotated players.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.get_text().split())
    return {marker: explanation.strip() for marker, explanation in _LEGEND.findall(text)}


def parse_points(text: str) -> float | None:
    """Parse a points cell such as ``4½``, ``½`` or ``0``."""
    text = text.strip().replace("½", ".5")
    if not text:
        return None
    if text.startswith("."):
        text = "0" + text
    try:
        return float(text)
    except ValueError:
        return None


def parse_result(text: str) -> tuple[float | None, float | None, bool]:
    """Parse a Result cell into ``(white_score, black_score, forfeit)``.

    Handles ``1 - 0``, ``0 - 1``, ``½ - ½``, forfeits rendered with ``+``/``-``,
    a single value (byes) and the empty string (not yet played).
    """
    text = text.strip()
    if not text:
        return None, None, False
    if text.startswith("+"):
        return 1.0, 0.0, True
    if text.endswith("+"):
        return 0.0, 1.0, True
    tokens = re.findall(r"½|\d+(?:\.\d+)?", text)
    values = [0.5 if t == "½" else float(t) for t in tokens]
    if len(values) >= 2:
        return values[0], values[1], False
    if len(values) == 1:
        return values[0], None, False
    return None, None, False


def _cells(row: Tag) -> list[Tag]:
    return row.find_all(["th", "td"])


def _text(cell: Tag) -> str:
    return " ".join(cell.get_text().split())


def _int(text: str) -> int | None:
    text = text.strip()
    return int(text) if text.isdigit() else None


def _data_tables(html: str) -> list[Tag]:
    soup = BeautifulSoup(html, "html.parser")
    return soup.find_all("table", {"class": TABLE_CLASS})


class _Columns:
    """Maps header labels to column indices for one table."""

    def __init__(self, header: list[str]) -> None:
        self.header = header

    def index(self, label: str, after: int | None = None, before: int | None = None) -> int | None:
        for i, text in enumerate(self.header):
            if text != label:
                continue
            if after is not None and i <= after:
                continue
            if before is not None and i >= before:
                continue
            return i
        return None

    def value(self, cells: list[str], idx: int | None) -> str:
        return cells[idx] if idx is not None and idx < len(cells) else ""


def _header_row(table: Tag, first_label: str) -> tuple[list[str], int] | None:
    """Find the header row and its position within the table."""
    for i, row in enumerate(table.select("tr")):
        header = [_text(c) for c in _cells(row)]
        if header and header[0] == first_label:
            return header, i
    return None


def parse_pairings(html: str, rnd: int, *, bye_value: float = 1.0) -> list[Pairing]:
    """Parse a round's pairing table (``art=2``).

    ``bye_value`` is what a pairing-allocated bye is worth in this tournament.
    FIDE-rated Swisses award a full point; some congresses award a half. The
    value chess-results shows for a *requested* bye is read from the page and is
    not affected by this setting.
    """
    legend = parse_legend(html)
    fixed_board_markers = {marker for marker, text in legend.items() if _FIXED_BOARD in text.lower()}

    def player_ref(cells: list[str], cols: _Columns, i_name, i_rtg, i_title, i_no) -> PlayerRef:
        name, marker = split_name_marker(cols.value(cells, i_name))
        return PlayerRef(
            name=name,
            rating=_int(cols.value(cells, i_rtg)),
            title=cols.value(cells, i_title) or None,
            start_no=_int(cols.value(cells, i_no)),
            marker=marker,
            fixed_board=marker in fixed_board_markers,
        )

    pairings: list[Pairing] = []
    for table in _data_tables(html):
        found = _header_row(table, "Bo.")
        if not found:
            continue
        header, header_idx = found
        cols = _Columns(header)

        i_board = cols.index("Bo.")
        i_result = cols.index("Result")
        i_white = cols.index("White")
        i_black = cols.index("Black")
        if None in (i_board, i_result, i_white, i_black):
            continue

        i_w_rtg = cols.index("Rtg", before=i_result)
        i_w_pts = cols.index("Pts.", before=i_result)
        i_w_no = cols.index("No.", before=i_result)
        i_b_rtg = cols.index("Rtg", after=i_result)
        i_b_pts = cols.index("Pts.", after=i_result)
        i_b_no = cols.index("No.", after=i_result)
        # The unlabelled column immediately before a name column holds the title.
        i_w_title = i_white - 1 if i_white and not header[i_white - 1] else None
        i_b_title = i_black - 1 if i_black and not header[i_black - 1] else None

        for row in table.select("tr")[header_idx + 1 :]:
            cells = [_text(c) for c in _cells(row)]
            if len(cells) != len(header):
                continue
            board = _int(cols.value(cells, i_board))
            if board is None:
                continue

            white = player_ref(cells, cols, i_white, i_w_rtg, i_w_title, i_w_no)
            raw_result = cols.value(cells, i_result)
            white_score, black_score, forfeit = parse_result(raw_result)
            black_name = cols.value(cells, i_black)
            label = black_name.strip().lower()

            if label == BYE_LABEL:
                kind, black = PlayKind.PAIRING_BYE, None
                white_score, black_score = bye_value, None
            elif label == UNPAIRED_LABEL or not black_name:
                black = None
                if white_score:
                    kind = PlayKind.REQUESTED_BYE
                else:
                    kind, white_score = PlayKind.UNPAIRED, white_score or 0.0
                black_score = None
            else:
                kind = PlayKind.GAME
                black = player_ref(cells, cols, i_black, i_b_rtg, i_b_title, i_b_no)

            pairings.append(
                Pairing(
                    round=rnd,
                    board=board,
                    white=white,
                    black=black,
                    kind=kind,
                    white_points_before=parse_points(cols.value(cells, i_w_pts)),
                    black_points_before=parse_points(cols.value(cells, i_b_pts)),
                    white_score=white_score,
                    black_score=black_score,
                    raw_result=raw_result,
                    forfeit=forfeit,
                )
            )
    return pairings


def parse_starting_rank(html: str) -> list[StartingRankEntry]:
    """Parse the starting-rank list (``art=0``)."""
    entries: list[StartingRankEntry] = []
    for table in _data_tables(html):
        found = _header_row(table, "No.")
        if not found:
            continue
        header, header_idx = found
        cols = _Columns(header)
        i_no = cols.index("No.")
        i_name = cols.index("Name")
        if i_name is None:
            continue
        i_title = i_name - 1 if i_name and not header[i_name - 1] else None

        for row in table.select("tr")[header_idx + 1 :]:
            cells = [_text(c) for c in _cells(row)]
            if len(cells) != len(header):
                continue
            start_no = _int(cols.value(cells, i_no))
            if start_no is None:
                continue
            entries.append(
                StartingRankEntry(
                    start_no=start_no,
                    name=clean_name(cols.value(cells, i_name)),
                    rating=_int(cols.value(cells, cols.index("Rtg"))),
                    title=cols.value(cells, i_title) or None,
                    fide_id=cols.value(cells, cols.index("FideID")) or None,
                    federation=cols.value(cells, cols.index("FED")) or None,
                    local_id=cols.value(cells, cols.index("ID")) or None,
                    sex=cols.value(cells, cols.index("sex")) or None,
                    type=cols.value(cells, cols.index("Typ")) or None,
                )
            )
    return entries


#: A crosstable round column, e.g. "3.Rd".
_ROUND_COLUMN = re.compile(r"(\d+)\.Rd")

#: A played game in a crosstable cell: opponent's number, colour, result.
_CROSSTABLE_GAME = re.compile(r"^(\d+)([bw])([01½+-])$")

#: A round with no opponent: just the value awarded, e.g. "-1", "-½", "-0".
_CROSSTABLE_NO_GAME = re.compile(r"^-\s*([01½])$")

#: What each no-opponent value means. A full point is a pairing-allocated bye,
#: a half is a requested bye, and nothing at all is an unpaired round -- a
#: withdrawal, a late entry, or a zero-point bye.
_NO_GAME_KINDS = {
    1.0: PlayKind.PAIRING_BYE,
    0.5: PlayKind.REQUESTED_BYE,
    0.0: PlayKind.UNPAIRED,
}


def _crosstable_cell(text: str, rnd: int) -> CrosstableEntry | None:
    text = text.strip()

    game = _CROSSTABLE_GAME.match(text)
    if game:
        opponent, colour, result = game.groups()
        forfeit = result in "+-"
        score = {"½": 0.5, "+": 1.0, "-": 0.0}.get(result)
        return CrosstableEntry(
            round=rnd,
            kind=PlayKind.GAME,
            opponent_no=int(opponent),
            colour=Colour(colour),
            score=float(result) if score is None else score,
            forfeit=forfeit,
        )

    no_game = _CROSSTABLE_NO_GAME.match(text)
    if no_game:
        value = 0.5 if no_game.group(1) == "½" else float(no_game.group(1))
        return CrosstableEntry(round=rnd, kind=_NO_GAME_KINDS[value], score=value)

    return None


def parse_crosstable(html: str) -> dict[int, list[CrosstableEntry]]:
    """Parse the starting-rank crosstable (``art=5``), keyed by starting number.

    This is the only view that records what a player did in a round they were
    not paired in. chess-results prints "bye" and "not paired" rows on a round's
    pairing page only while that round is the current one; once a later round is
    paired they are dropped, and a full-point bye disappears with them.

    Rounds not yet played are simply absent from a player's list.
    """
    for table in _data_tables(html):
        found = _header_row(table, "No.")
        if found and any(_ROUND_COLUMN.fullmatch(h) for h in found[0]):
            break
    else:
        return {}

    header, header_idx = found
    cols = _Columns(header)
    i_no = cols.index("No.")
    if i_no is None:
        return {}
    rounds = {i: int(match.group(1)) for i, h in enumerate(header) if (match := _ROUND_COLUMN.fullmatch(h))}

    crosstable: dict[int, list[CrosstableEntry]] = {}
    for row in table.select("tr")[header_idx + 1 :]:
        cells = [_text(c) for c in _cells(row)]
        if len(cells) != len(header):
            continue
        start_no = _int(cols.value(cells, i_no))
        if start_no is None:
            continue
        entries = [_crosstable_cell(cells[i], rnd) for i, rnd in rounds.items()]
        crosstable[start_no] = [e for e in entries if e is not None]
    return crosstable


def parse_tournament_name(html: str) -> str | None:
    """Best-effort extraction of the tournament name from any page."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = _text(tag)
        if text:
            return text
    return None


def has_pairings(html: str) -> bool:
    """True if the page contains a pairing table (used to detect the last round)."""
    return any(_header_row(t, "Bo.") for t in _data_tables(html))
