"""Players assigned to a fixed board.

Swiss-Manager lets an arbiter pin a player to one board number for the whole
event, usually on access or health grounds. chess-results marks them with a
footnote against the name and explains it in a legend under the table. It
constrains where a game is played, never who plays whom -- but it does mean
board numbers cannot be derived from scores.
"""

import pytest
from tests.conftest import _british, fixture

from chess_results.models import Colour, Play, Player, PlayKind
from chess_results.parse import parse_legend, parse_pairings, split_name_marker


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hebden, Mark L *)", ("Hebden, Mark L", "*)")),
        ("Mcshane, Luke J", ("Mcshane, Luke J", None)),
        ("Someone  **)", ("Someone", "**)")),
    ],
)
def test_split_name_marker(text, expected):
    assert split_name_marker(text) == expected


def test_legend_is_read_from_the_page():
    legend = parse_legend(fixture("british2026_champ_r6_midround.html"))
    assert legend == {"*)": "This player is assigned to a fixed board."}


def test_no_legend_when_nobody_is_annotated():
    assert parse_legend(fixture("frome2026_open_r1.html")) == {}


class TestPairingRows:
    @pytest.fixture(scope="class")
    def round6(self):
        return parse_pairings(fixture("british2026_champ_r6_midround.html"), 6)

    def test_marked_player_is_flagged(self, round6):
        hebden = next(p for p in round6 if p.white.name == "Hebden, Mark L").white
        assert (hebden.marker, hebden.fixed_board) == ("*)", True)

    def test_marker_is_not_part_of_the_name(self, round6):
        assert all("*" not in p.white.name for p in round6)

    def test_unmarked_players_are_not_flagged(self, round6):
        adams = next(p for p in round6 if p.black and p.black.name == "Adams, Michael").black
        assert (adams.marker, adams.fixed_board) == (None, False)


class TestPlayer:
    def test_flag_survives_assembly(self, british):
        assert british.players["Hebden, Mark L"].fixed_board is True
        assert british.players["Adams, Michael"].fixed_board is False

    def test_board_number_is_read_back_from_the_games_played(self, british):
        # chess-results says a player has a fixed board but never which one.
        assert british.players["Hebden, Mark L"].fixed_board_number == 14

    def test_players_without_a_fixed_board_have_no_number(self, british):
        assert british.players["Adams, Michael"].fixed_board_number is None


class TestWhichBoardTheyArePinnedTo:
    """chess-results says a player has a fixed board and never which one, so it
    is read back from the boards they played. Hebden's pin starts at round 4:
    boards 23, 18, 1, then 14 for the rest of the event."""

    def _hebden(self, upto):
        event = _british(crosstable=True, rounds=upto)
        return event.players["Hebden, Mark L"]

    @pytest.mark.parametrize("upto", [4, 5, 6, 7])
    def test_the_pin_is_found_from_the_round_it_starts(self, upto):
        """The modal board answered 23 at round 4 and only came right at round 5.

        That is precisely when the answer matters -- a live prediction of the
        next round -- so the run, not the count, is what identifies the pin.
        """
        assert self._hebden(upto).fixed_board_number == 14

    def test_before_the_pin_begins_there_is_nothing_better_than_the_last_board(self):
        """Rounds 1-3 are 23, 18, 1: no run, and no way to know 14 is coming."""
        assert self._hebden(3).fixed_board_number == 1

    def test_a_long_run_beats_a_more_recent_short_one(self):
        player = Player(name="x", fixed_board=True)
        for rnd, board in enumerate([7, 7, 7, 7, 9], start=1):
            player.plays.append(
                Play(round=rnd, kind=PlayKind.GAME, colour=Colour.WHITE, board=board, opponent="y")
            )
        assert player.fixed_board_number == 7

    def test_the_most_recent_wins_a_tie(self):
        player = Player(name="x", fixed_board=True)
        for rnd, board in enumerate([3, 3, 8, 8], start=1):
            player.plays.append(
                Play(round=rnd, kind=PlayKind.GAME, colour=Colour.WHITE, board=board, opponent="y")
            )
        assert player.fixed_board_number == 8

    def test_a_bye_does_not_break_the_run(self):
        """A round with no board of its own says nothing about the pin."""
        player = Player(name="x", fixed_board=True)
        for rnd, board in enumerate([5, 5], start=1):
            player.plays.append(
                Play(round=rnd, kind=PlayKind.GAME, colour=Colour.WHITE, board=board, opponent="y")
            )
        player.plays.append(Play(round=3, kind=PlayKind.PAIRING_BYE, score=1.0))
        player.plays.append(Play(round=4, kind=PlayKind.GAME, colour=Colour.WHITE, board=5, opponent="y"))
        assert player.fixed_board_number == 5

    def test_a_player_who_has_played_nothing_yet_has_no_number(self):
        assert Player(name="x", fixed_board=True).fixed_board_number is None
