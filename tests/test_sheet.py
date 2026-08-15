"""The printable pairing sheet: board assignment, fixed boards, pagination."""

from __future__ import annotations

import pytest

from chess_results import sheet
from chess_results.models import Colour, Play, Player, PlayKind
from chess_results.sheet import PairingSheet, SheetError, SheetRow
from chess_results.tournament import Tournament


def _pairs(event: Tournament, rnd: int) -> list[tuple[int, int]]:
    """A round's published pairings in a pairing engine's own output shape."""
    numbers = {p.name: p.start_no for p in event.players.values()}
    out = []
    for pairing in event.rounds[rnd]:
        if pairing.kind is PlayKind.GAME and pairing.black is not None:
            out.append((numbers[pairing.white.name], numbers[pairing.black.name]))
        elif pairing.kind is PlayKind.PAIRING_BYE:
            out.append((numbers[pairing.white.name], 0))
    return out


def _round_eight(event: Tournament) -> sheet.PairingSheet:
    """Round 8 of the British, re-paired from its own published pairs."""
    return sheet.sheet_from_pairs(event, _pairs(event, 8), round_number=8, after=7)


class TestReadEnginePairs:
    def test_reads_a_count_then_pairs(self):
        assert sheet.read_engine_pairs("3\n1 2\n3 4\n5 0\n") == [(1, 2), (3, 4), (5, 0)]

    def test_blank_lines_are_ignored(self):
        assert sheet.read_engine_pairs("1\n\n 7 8 \n\n") == [(7, 8)]

    def test_a_truncated_file_is_refused_not_shortened(self):
        # A short sheet is indistinguishable from a small round, so the count
        # is checked rather than skipped.
        with pytest.raises(SheetError, match="says 3 pairings but lists 2"):
            sheet.read_engine_pairs("3\n1 2\n3 4\n")

    def test_an_empty_file_is_refused(self):
        with pytest.raises(SheetError, match="empty file"):
            sheet.read_engine_pairs("")

    def test_a_missing_count_is_refused(self):
        with pytest.raises(SheetError, match="pair count"):
            sheet.read_engine_pairs("1 2\n3 4\n")

    def test_a_malformed_pair_names_its_line(self):
        with pytest.raises(SheetError, match="pair 2 is not two starting numbers"):
            sheet.read_engine_pairs("2\n1 2\nMcshane v Adams\n")


class TestBoardAssignment:
    def test_board_one_holds_the_leaders(self, british_played_out):
        made = _round_eight(british_played_out)
        leaders = british_played_out.ranking_order(7)[:2]
        assert made.rows[0].white in leaders or made.rows[0].black in leaders

    def test_boards_descend_by_score(self, british_played_out):
        made = _round_eight(british_played_out)
        tops = [
            max(row.white.score(7), row.black.score(7))
            for row in made.rows
            if row.board is not None and not row.pinned
        ]
        assert tops == sorted(tops, reverse=True)

    def test_boards_are_numbered_from_one_without_gaps(self, british_played_out):
        made = _round_eight(british_played_out)
        boards = [row.board for row in made.rows if row.board is not None]
        assert boards == list(range(1, len(boards) + 1))

    def test_every_pair_survives_exactly_once(self, british_played_out):
        pairs = _pairs(british_played_out, 8)
        made = sheet.sheet_from_pairs(british_played_out, pairs, round_number=8, after=7)
        got = {frozenset(p.name for p in (row.white, row.black) if p is not None) for row in made.rows}
        assert len(got) == len(pairs)
        assert len(made.rows) == len(pairs)

    def test_a_bye_takes_no_board_and_sorts_last(self, british_played_out):
        # Cooke took the round 8 bye, so this is a real bye player rather than
        # an invented one -- and one the round page itself has since dropped.
        cooke = british_played_out.players["Cooke, Suzy G"]
        pairs = [*_pairs(british_played_out, 8), (cooke.start_no, 0)]
        made = sheet.sheet_from_pairs(british_played_out, pairs, round_number=9, after=8)
        assert made.rows[-1].board is None
        assert made.rows[-1].is_bye
        assert made.boards == len(made.rows) - 1

    def test_an_unknown_starting_number_is_refused(self, british_played_out):
        with pytest.raises(SheetError, match="no player has starting number 9999"):
            sheet.sheet_from_pairs(british_played_out, [(1, 9999)])


class TestFixedBoards:
    """A pin beats the ranking: it is why the pin exists."""

    @staticmethod
    def _pin(player: Player, board: int) -> None:
        """Give a player a board a run long enough for fixed_board_number to see.

        The colour matters: fixed_board_number reads boards off plays that
        `counts_for_colour`, which a colourless play does not.
        """
        player.fixed_board = True
        player.plays = [
            Play(round=rnd, kind=PlayKind.GAME, colour=Colour.WHITE, score=0.5, board=board) for rnd in (1, 2)
        ]

    def _event(self, pinned_board: int) -> tuple[Tournament, list[tuple[int, int]]]:
        event = Tournament(id="x", name="Test Open")
        for number in range(1, 9):
            player = Player(name=f"P{number}", start_no=number, rating=2000 + number)
            player.plays.append(
                Play(
                    round=1,
                    kind=PlayKind.GAME,
                    colour=Colour.WHITE,
                    score=1.0 if number <= 4 else 0.0,
                    board=number,
                )
            )
            event.players[player.name] = player
        # P7 lost round 1, so by ranking it would be on one of the lower boards.
        self._pin(event.players["P7"], pinned_board)
        event.rounds[1] = []
        pairs = [(1, 5), (2, 6), (3, 7), (4, 8)]
        return event, pairs

    def test_a_pinned_player_gets_their_board(self):
        event, pairs = self._event(pinned_board=4)
        rows, warnings = sheet.assign_boards(
            event, [(event.players[f"P{w}"], event.players[f"P{b}"]) for w, b in pairs], after=1
        )
        assert warnings == []
        pinned = next(row for row in rows if row.pinned)
        assert pinned.board == 4
        assert "P7" in (pinned.white.name, pinned.black.name)

    def test_the_rest_still_fill_every_other_board(self):
        event, pairs = self._event(pinned_board=1)
        rows, _ = sheet.assign_boards(
            event, [(event.players[f"P{w}"], event.players[f"P{b}"]) for w, b in pairs], after=1
        )
        assert [row.board for row in rows] == [1, 2, 3, 4]
        assert len({row.white.name for row in rows}) == 4

    def test_a_pin_outside_the_round_warns_rather_than_vanishing(self):
        event, pairs = self._event(pinned_board=40)
        rows, warnings = sheet.assign_boards(
            event, [(event.players[f"P{w}"], event.players[f"P{b}"]) for w, b in pairs], after=1
        )
        assert len(rows) == 4
        assert any("does not have" in w for w in warnings)

    def test_two_pins_on_one_board_warn_and_neither_is_dropped(self):
        event, pairs = self._event(pinned_board=2)
        # P8 wants board 2 as well, and is in a different pair.
        self._pin(event.players["P8"], 2)
        rows, warnings = sheet.assign_boards(
            event, [(event.players[f"P{w}"], event.players[f"P{b}"]) for w, b in pairs], after=1
        )
        assert any("wanted by two pinned players" in w for w in warnings)
        assert len(rows) == 4
        assert [row.board for row in rows] == [1, 2, 3, 4]


class TestHebdensRealPin:
    """The one fixed board in the fixtures, so the pin is exercised for real.

    Hebden played boards 23, 18 and 1 before settling on 14 from round 4, which
    is what `Player.fixed_board_number` reads back.
    """

    def test_he_is_placed_on_his_own_board(self, british_played_out):
        made = _round_eight(british_played_out)
        row = next(r for r in made.rows if "Hebden, Mark L" in (r.white.name, r.black.name))
        assert row.board == british_played_out.players["Hebden, Mark L"].fixed_board_number == 14
        assert row.pinned

    def test_the_pin_is_what_puts_him_there(self, british_played_out):
        """Board 14 must be the pin's doing, not a coincidence of the ranking.

        Without this the test above would pass on an event where the pinned
        board happened to be where ranking put the pair anyway.
        """
        pairs = _pairs(british_played_out, 8)
        by_no = {p.start_no: p for p in british_played_out.players.values()}
        resolved = [(by_no[w], by_no[b]) for w, b in pairs]
        rows, _ = sheet.assign_boards(british_played_out, resolved, after=7)
        placed = next(r for r in rows if "Hebden, Mark L" in (r.white.name, r.black.name))

        hebden = british_played_out.players["Hebden, Mark L"]
        hebden.fixed_board = False
        try:
            unpinned, _ = sheet.assign_boards(british_played_out, resolved, after=7)
        finally:
            hebden.fixed_board = True
        natural = next(r for r in unpinned if "Hebden, Mark L" in (r.white.name, r.black.name))

        assert placed.board == 14
        assert not natural.pinned
        # If these ever coincide the assertion above proves nothing; the point
        # of this test is that they do not.
        assert natural.board != placed.board

    def test_no_other_pair_is_displaced_off_the_sheet(self, british_played_out):
        pairs = _pairs(british_played_out, 8)
        made = sheet.sheet_from_pairs(british_played_out, pairs, round_number=8, after=7)
        assert len(made.rows) == len(pairs)
        boards = sorted(r.board for r in made.rows if r.board is not None)
        assert boards == list(range(1, len(pairs) + 1))


class TestPublishedRound:
    def test_it_keeps_the_arbiters_own_board_numbers(self, british_played_out):
        made = sheet.sheet_from_round(british_played_out, 8)
        published = [p.board for p in british_played_out.rounds[8] if p.kind is PlayKind.GAME]
        assert [row.board for row in made.rows if row.board is not None] == published

    def test_a_bye_deleted_from_a_superseded_round_page_is_put_back(self, british_played_out):
        """Round 6's page has lost its bye row, and the sheet must not.

        chess-results deletes bye and "not paired" rows once a later round is
        paired, so round 6 lists 52 games for a field of 108. Chapman took the
        full-point bye that round; a sheet without him tells the hall no bye was
        given. The row is recovered from `Player.plays`, which the crosstable
        filled in.
        """
        made = sheet.sheet_from_round(british_played_out, 6)
        on_page = {p.white.name for p in british_played_out.rounds[6]}
        assert "Chapman, Luke" not in on_page  # gone from the page itself

        byes = {row.white.name: row.note for row in made.rows if row.is_bye}
        assert byes["Chapman, Luke"] == "bye"
        assert byes["Mannion, Steve R"] == "not paired"

    def test_the_sheet_accounts_for_every_player_in_the_event(self, british_played_out):
        """No player may be missing: each one either plays, or is told why not."""
        for rnd in sorted(british_played_out.rounds):
            made = sheet.sheet_from_round(british_played_out, rnd)
            named = {row.white.name for row in made.rows}
            named |= {row.black.name for row in made.rows if row.black is not None}
            expected = {p.name for p in british_played_out.players.values() if p.play(rnd)}
            assert named == expected, rnd

    def test_a_round_that_does_not_exist_is_refused(self, british_played_out):
        with pytest.raises(SheetError, match="round 99 has no pairings"):
            sheet.sheet_from_round(british_played_out, 99)


class TestRender:
    def _sheet(self, boards: int) -> PairingSheet:
        rows = []
        for board in range(1, boards + 1):
            white = Player(name=f"White {board}", start_no=board * 2 - 1)
            black = Player(name=f"Black {board}", start_no=board * 2)
            white.plays.append(Play(round=1, kind=PlayKind.GAME, score=1.0))
            black.plays.append(Play(round=1, kind=PlayKind.GAME, score=0.5))
            rows.append(SheetRow(board, white, black))
        return PairingSheet("Test Open", 2, rows)

    def test_the_heading_names_the_event_and_round(self):
        text = sheet.render(self._sheet(3), after=1)
        assert text.splitlines()[0] == "Test Open"
        assert "Round 2 pairings" in text

    def test_scores_print_as_halves_not_decimals(self):
        text = sheet.render(self._sheet(1), after=1)
        assert "½" in text
        assert "0.5" not in text

    def test_a_subtitle_reaches_the_page(self):
        text = sheet.render(self._sheet(1), after=1, subtitle="Starts 14:00 — Great Hall")
        assert "Starts 14:00 — Great Hall" in text

    def test_every_page_repeats_the_heading(self):
        text = sheet.render(self._sheet(120), after=1, lines_per_page=30)
        pages = text.split(sheet.FORM_FEED)
        assert len(pages) > 1
        assert all("Round 2 pairings" in page for page in pages)
        assert all("Bd " in page for page in pages)

    def test_no_page_overflows_its_length(self):
        for boards in range(1, 90):
            text = sheet.render(self._sheet(boards), after=1, lines_per_page=24)
            for page in text.split(sheet.FORM_FEED):
                assert len(page.strip("\n").splitlines()) <= 24, boards

    def test_pages_are_numbered_out_of_the_total(self):
        text = sheet.render(self._sheet(120), after=1, lines_per_page=30)
        pages = text.split(sheet.FORM_FEED)
        assert f"page 1 of {len(pages)}" in pages[0]
        assert f"page {len(pages)} of {len(pages)}" in pages[-1]

    def test_no_pages_means_no_form_feed(self):
        text = sheet.render(self._sheet(120), after=1, lines_per_page=0)
        assert sheet.FORM_FEED not in text
        assert "page 1 of" not in text

    def test_every_board_appears_exactly_once_across_the_pages(self):
        text = sheet.render(self._sheet(120), after=1, lines_per_page=30)
        for board in range(1, 121):
            assert sum(1 for line in text.splitlines() if line.startswith(f"{board:>3}  ")) == 1

    def test_a_bye_row_prints_the_word_and_no_board(self):
        base = self._sheet(2)
        lone = Player(name="Alone, A", start_no=99)
        lone.plays.append(Play(round=1, kind=PlayKind.GAME, score=1.0))
        made = PairingSheet(base.event, base.round, [*base.rows, SheetRow(None, lone, None)])
        line = next(line for line in sheet.render(made, after=1).splitlines() if "Alone, A" in line)
        assert line.startswith("  -")
        assert sheet.BYE_TEXT in line

    def test_warnings_are_printed_on_the_sheet_itself(self):
        base = self._sheet(2)
        made = PairingSheet(base.event, base.round, base.rows, ["board 1 is contested"])
        assert "! board 1 is contested" in sheet.render(made, after=1)

    def test_a_pinned_board_is_marked_and_explained(self):
        base = self._sheet(2)
        rows = [SheetRow(1, base.rows[0].white, base.rows[0].black, pinned=True), base.rows[1]]
        text = sheet.render(PairingSheet(base.event, base.round, rows), after=1)
        assert "* board fixed for this player" in text
        assert text.splitlines()[5].endswith("  *")

    def test_a_page_with_no_room_for_a_pairing_is_refused(self):
        with pytest.raises(SheetError, match="no room"):
            sheet.render(self._sheet(3), after=1, lines_per_page=4)


class TestResultColumn:
    """Swiss-Manager's pairing chart has a middle column for the result."""

    def test_a_decided_game_prints_its_result(self, british_played_out):
        made = sheet.sheet_from_round(british_played_out, 6)
        text = sheet.render(made, after=5, results=True)
        assert "Result" in text
        assert "½-½" in text
        assert "1-0" in text

    def test_an_unplayed_game_leaves_the_box_empty(self, british):
        """Empty, not a dash: the arbiter writes into it.

        Round 7 of the mid-event capture is paired with results still to come,
        which is the state a chart is printed in.
        """
        made = sheet.sheet_from_round(british, 7)
        assert all(row.result == "" for row in made.rows if row.board is not None)
        line = next(
            line
            for line in sheet.render(made, after=6, results=True).splitlines()
            if line.startswith("  1  ")
        )
        assert "-" not in line

    def test_a_bye_gets_no_result_box_content(self, british_played_out):
        made = sheet.sheet_from_round(british_played_out, 6)
        assert all(row.result == "" for row in made.rows if row.is_bye)

    def test_render_leaves_it_off_unless_asked(self, british_played_out):
        """`render` is a primitive and takes no view; the CLI is what has one.

        `chess-results pairing-sheet` turns the column on by default, since a
        sheet on a wall is written on as games finish. Keeping the two apart
        means a caller composing their own sheet is not surprised by a column
        they did not ask for.
        """
        made = sheet.sheet_from_round(british_played_out, 6)
        assert "Result" not in sheet.render(made, after=5)

    def test_it_still_fits_eighty_columns(self, british_played_out):
        made = sheet.sheet_from_round(british_played_out, 6)
        text = sheet.render(made, after=5, results=True)
        assert max(len(line) for line in text.splitlines()) <= 80

    def test_a_forfeit_is_marked(self, british_played_out):
        """Round 8's two defaults must not read as ordinary wins."""
        made = sheet.sheet_from_round(british_played_out, 8)
        assert any(row.result.endswith("F") for row in made.rows)


class TestAgainstRealPairings:
    def test_a_whole_british_round_renders_inside_eighty_columns(self, british_played_out):
        made = _round_eight(british_played_out)
        text = sheet.render(made, after=7)
        assert max(len(line) for line in text.splitlines()) <= 80

    def test_a_requested_bye_is_not_called_a_bye(self, frome_round_one):
        """Frome's round 1 has twelve half-point byes and no full-point ones.

        Flattening the three to "bye" tells a player who requested a half point
        that they were given a whole one, and tells an unpaired player nothing
        is wrong. The screen table already distinguishes them; so must the wall.
        """
        made = sheet.sheet_from_round(frome_round_one, 1)
        notes = {row.note for row in made.rows if row.is_bye}
        assert notes == {"half-point bye"}
        assert "half-point bye" in sheet.render(made, after=0)

    def test_both_kinds_of_bye_can_share_one_sheet(self, frome_congress):
        """Frome's Standard section has a full-point bye among half-point ones.

        The two are a point apart, so a sheet that prints them alike is wrong
        about somebody's score in front of the whole hall.
        """
        made = sheet.sheet_from_round(frome_congress.sections["Standard"], 1)
        assert {row.note for row in made.rows if row.is_bye} == {"bye", "half-point bye"}

    def test_a_congress_section_renders_too(self, frome_round_one):
        made = sheet.sheet_from_round(frome_round_one, 1)
        text = sheet.render(made, after=0)
        assert "Round 1 pairings" in text
        assert made.boards == len(frome_round_one.games(1))
