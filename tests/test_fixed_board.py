"""Players assigned to a fixed board.

Swiss-Manager lets an arbiter pin a player to one board number for the whole
event, usually on access or health grounds. chess-results marks them with a
footnote against the name and explains it in a legend under the table. It
constrains where a game is played, never who plays whom -- but it does mean
board numbers cannot be derived from scores.
"""

import pytest
from tests.conftest import fixture

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
