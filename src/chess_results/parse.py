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

from .models import (
    Absence,
    Colour,
    CrosstableEntry,
    NotPairedEntry,
    Pairing,
    PlayerRef,
    PlayKind,
    StartingRankEntry,
)

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

#: The site's own name, which every page title is prefixed with.
_TITLE_PREFIX = re.compile(r"^Chess-Results Server\s+Chess-results\.com\s*-\s*", re.IGNORECASE)

#: Where a rating may be found, best first. An event rated on one list prints a
#: plain ``Rtg``; one rated nationally and internationally at once prints
#: ``RtgI`` and ``RtgN`` and no ``Rtg`` at all, which used to leave every rating
#: None. International first, that being what a FIDE pairing engine wants.
_RATING_LABELS = ("Rtg", "RtgI", "RtgN")


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
    """Parse a points cell such as ``4½``, ``½``, ``0`` or ``4,5``.

    chess-results writes points two different ways in the same tournament. The
    round-by-round cells use ``½``, but a total is rendered in the server's
    locale and comes back with a decimal comma -- the crosstable's ``TB1``
    column prints 4½ as ``4,5``. A comma here is always a decimal separator: no
    points value is ever large enough to need a thousands separator.

    Returns None for anything unparseable, which includes the empty cell of a
    round not yet played.
    """
    text = text.strip().replace("½", ".5").replace(",", ".")
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

    Decimal commas are normalised first, as in :func:`parse_points`. Left alone,
    ``0,5 - 0,5`` tokenises as four separate numbers and the first two -- 0 and
    5 -- would be read as the two players' scores.
    """
    text = text.strip().replace(",", ".")
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

    def index_any(
        self, labels: tuple[str, ...], after: int | None = None, before: int | None = None
    ) -> int | None:
        """The first of ``labels`` this header carries, in the order given."""
        for label in labels:
            found = self.index(label, after=after, before=before)
            if found is not None:
                return found
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

    def player_ref(
        cells: list[str],
        cols: _Columns,
        i_name: int | None,
        i_rtg: int | None,
        i_title: int | None,
        i_no: int | None,
    ) -> PlayerRef:
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

        i_w_rtg = cols.index_any(_RATING_LABELS, before=i_result)
        i_w_pts = cols.index("Pts.", before=i_result)
        i_w_no = cols.index("No.", before=i_result)
        i_b_rtg = cols.index_any(_RATING_LABELS, after=i_result)
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
                    rating=_int(cols.value(cells, cols.index_any(_RATING_LABELS))),
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
    """The tournament's name, as printed above the table.

    Every view heads the page with the tournament name in the first ``h2``, and
    names the view itself in a second one ("Starting rank", "Pairings/Results").
    Reading the first heading of *any* level instead picks up the ``h3``
    server-load banner that chess-results prints above the name on tournaments
    more than five days old, and a round page's ``h3`` date line below it.

    Falls back to the page title, which carries the same name behind the site's
    own prefix -- but truncated, so it is a fallback and not the first choice.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("h2"):
        text = _text(tag)
        if text:
            return text
    if soup.title:
        return _TITLE_PREFIX.sub("", _text(soup.title)) or None
    return None


def has_pairings(html: str) -> bool:
    """True if the page contains a pairing table (used to detect the last round)."""
    return any(_header_row(t, "Bo.") for t in _data_tables(html))


#: What a team match table pairs on: a team against a team, carrying match
#: points. No player is named anywhere on it.
_TEAM_COLUMNS = ("Team", "MP")

#: The heading row chess-results puts above each round's boards, as
#: "Round 3 on 2026/08/09 at 14.00".
_ROUND_HEADING = re.compile(r"^Round\s+\d+\s+on\b")


def is_combined_pairings(html: str) -> bool:
    """True if one pairing table holds every round at once (``art=2``).

    A Swiss publishes one page per round and ``&rd=`` selects it. A round robin
    publishes all of its rounds together, under repeated "Round N on ..."
    headings inside a single table, and ignores ``&rd=`` -- so every round of a
    round robin would otherwise be read as the round that was asked for.

    Detected by the headings rather than by the tournament type, which is not on
    the page: one heading is what a Swiss round page has, more than one means
    the rounds have been combined.
    """
    for table in _data_tables(html):
        if not _header_row(table, "Bo."):
            continue
        headings = sum(
            1
            for row in table.select("tr")
            if (cells := [_text(c) for c in _cells(row)]) and _ROUND_HEADING.match(cells[0])
        )
        if headings > 1:
            return True
    return False


def is_team_pairings(html: str) -> bool:
    """True if a round page pairs teams rather than players (``art=2``).

    A team event's round page is a different table entirely -- ``No. | SNo |
    Team | MP | Res. | : | Res. | MP | Team | SNo`` -- naming no players at
    all, so :func:`parse_pairings` reads nothing from it. That is the safe
    failure, but on its own it is indistinguishable from an event that has not
    started, and the caller would report an empty tournament with every
    appearance of confidence. Detecting it lets the caller say so instead.

    The individual boards live on ``art=3``, laid out as one sub-table per
    match with the two team names in its header, which this library also does
    not read.
    """
    for table in _data_tables(html):
        found = _header_row(table, "No.")
        if found and all(label in found[0] for label in _TEAM_COLUMNS):
            return True
    return False


#: Where a crosstable's score column may be found, best first. ``Pts.`` says
#: what it is; ``TB1`` merely often happens to hold the score, on events whose
#: first tiebreak is the score itself and which print no ``Pts.`` column at all
#: (the 2026 British and Frome are both like this). Where a tournament
#: publishes both, ``TB1`` is a genuine tiebreak and nothing to do with points
#: -- Arad 2026's is a rating, so reading it gave Kovalenko a total of 2369.
_TOTAL_LABELS = ("Pts.", "TB1")


def parse_published_totals(html: str) -> dict[int, float]:
    """The tournament's own total for each player, from the crosstable.

    Keyed by starting number, as the crosstable is. This is the arbiter's
    arithmetic rather than ours, which makes it the one figure on the page that
    can check our reading of the round-by-round cells: they must sum to it.

    Read from ``Pts.`` where the event publishes one and ``TB1`` otherwise, and
    **the result is checked before being believed**: no player can score more
    than there are rounds, so a column that breaks that is not the score
    however it is labelled. A wrong column here is worse than none, since it
    would report every player in the event as a disagreement and bury a real
    one. Returns ``{}`` when no column survives, which reads downstream as
    "this crosstable publishes no totals to check against".

    Printed in the server's locale, so ``4½`` arrives as ``4,5`` -- see
    :func:`parse_points`. Players whose total will not parse are left out.
    """
    for table in _data_tables(html):
        found = _header_row(table, "No.")
        if found and any(label in found[0] for label in _TOTAL_LABELS):
            break
    else:
        return {}

    header, header_idx = found
    cols = _Columns(header)
    i_no = cols.index("No.")
    if i_no is None:
        return {}
    # Counting the round columns bounds what a total can legitimately be.
    rounds = sum(1 for cell in header if _ROUND_COLUMN.fullmatch(cell.strip()))

    for label in _TOTAL_LABELS:
        i_total = cols.index(label)
        if i_total is None:
            continue
        totals: dict[int, float] = {}
        for row in table.select("tr")[header_idx + 1 :]:
            cells = [_text(c) for c in _cells(row)]
            if len(cells) != len(header):
                continue
            start_no = _int(cols.value(cells, i_no))
            total = parse_points(cols.value(cells, i_total))
            if start_no is not None and total is not None:
                totals[start_no] = total
        # A score cannot exceed the rounds played. Anything that does is a
        # tiebreak wearing the wrong name, so try the next candidate.
        if totals and (not rounds or max(totals.values()) <= rounds):
            return totals
    return {}


def parse_not_paired(html: str) -> list[NotPairedEntry]:
    """Parse the "not paired" page (``art=40``).

    One row per player who has missed at least one round, one column per round,
    marked ``*`` not paired, ``bye`` a bye and ``0F`` a forfeit. It is the most
    direct statement chess-results makes of who was absent when: a single page,
    where the same facts otherwise have to be mined out of the whole crosstable.

    Two things it does *not* tell you, both verified against the crosstables for
    the 2026 British Championship and the 2026 Frome Open:

    - **A requested bye is indistinguishable from an absence.** Only a
      pairing-allocated (full-point) bye prints ``bye``. A requested half-point
      bye prints ``*``, exactly as a withdrawal does -- every one of Frome's
      round 1 half-point byes appears here as ``*``. The crosstable keeps the
      distinction (``-½`` against ``-1``), so it remains the authority for
      *what* a missed round was worth; this page is the authority for *which*
      rounds were missed. Withdrawal inference cares about the difference: a
      player sitting out on a half point has not withdrawn.
    - **Only the defaulting player is listed for a forfeit.** Their opponent
      collects the point without appearing here at all.

    It also ignores ``&rd=``: there is one page, always current, so a past
    round's view of it cannot be recovered afterwards.
    """
    for table in _data_tables(html):
        found = _header_row(table, "SNo")
        if found and any(_ROUND_COLUMN.fullmatch(h) for h in found[0]):
            break
    else:
        return []

    header, header_idx = found
    cols = _Columns(header)
    i_no = cols.index("SNo")
    i_name = cols.index("Name")
    if i_no is None or i_name is None:
        return []
    # The title is the unlabelled column immediately before the name.
    i_title = i_name - 1 if i_name and not header[i_name - 1] else None
    rounds = {i: int(match.group(1)) for i, h in enumerate(header) if (match := _ROUND_COLUMN.fullmatch(h))}

    entries: list[NotPairedEntry] = []
    for row in table.select("tr")[header_idx + 1 :]:
        cells = [_text(c) for c in _cells(row)]
        if len(cells) != len(header):
            continue
        start_no = _int(cols.value(cells, i_no))
        if start_no is None:
            continue
        markers: dict[int, Absence] = {}
        for i, rnd in rounds.items():
            try:
                markers[rnd] = Absence(cells[i].strip())
            except ValueError:  # blank, or a marker this page has not shown before
                continue
        entries.append(
            NotPairedEntry(
                start_no=start_no,
                name=clean_name(cols.value(cells, i_name)),
                rating=_int(cols.value(cells, cols.index_any(_RATING_LABELS))),
                title=cols.value(cells, i_title) or None,
                federation=cols.value(cells, cols.index("FED")) or None,
                markers=markers,
            )
        )
    return entries
