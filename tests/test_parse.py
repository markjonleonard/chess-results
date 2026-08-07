import pytest
from tests.conftest import fixture

from chess_results.models import PlayKind
from chess_results.parse import clean_name, parse_pairings, parse_points, parse_result, parse_starting_rank


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1 - 0", (1.0, 0.0, False)),
        ("0 - 1", (0.0, 1.0, False)),
        ("½ - ½", (0.5, 0.5, False)),
        ("", (None, None, False)),
        ("½", (0.5, None, False)),
        ("0", (0.0, None, False)),
        ("+ -", (1.0, 0.0, True)),
        ("- +", (0.0, 1.0, True)),
    ],
)
def test_parse_result(text, expected):
    assert parse_result(text) == expected


@pytest.mark.parametrize("text,expected", [("4½", 4.5), ("½", 0.5), ("0", 0.0), ("3", 3.0), ("", None)])
def test_parse_points(text, expected):
    assert parse_points(text) == expected


def test_clean_name_strips_footnote_markers():
    assert clean_name("Hebden, Mark L *)") == "Hebden, Mark L"
    assert clean_name("Mcshane,  Luke J") == "Mcshane, Luke J"


class TestBritishPairings:
    """A tournament that publishes no starting-rank columns."""

    @pytest.fixture(scope="class")
    def round7(self):
        return parse_pairings(fixture("british2026_champ_r7.html"), 7)

    def test_board_one(self, round7):
        board = round7[0]
        assert board.white.name == "Royal, Shreyas"
        assert board.black.name == "Mcshane, Luke J"
        assert (board.white.rating, board.black.rating) == (2514, 2597)
        assert (board.white_points_before, board.black_points_before) == (5.0, 5.0)
        assert board.white_score is None, "round 7 has not been played"

    def test_titles_are_read_from_the_unlabelled_column(self, round7):
        assert (round7[0].white.title, round7[0].black.title) == ("GM", "GM")

    def test_absent_starting_numbers_are_none(self, round7):
        assert round7[0].white.start_no is None

    def test_pairing_allocated_bye(self, round7):
        byes = [p for p in round7 if p.kind is PlayKind.PAIRING_BYE]
        assert [p.white.name for p in byes] == ["Nevska, Gerda"]
        assert byes[0].white_score == 1.0, "defaults to a full point"

    def test_bye_value_is_configurable(self):
        half = parse_pairings(fixture("british2026_champ_r7.html"), 7, bye_value=0.5)
        assert [p.white_score for p in half if p.kind is PlayKind.PAIRING_BYE] == [0.5]

    def test_unpaired_players_score_nothing(self, round7):
        unpaired = [p for p in round7 if p.kind is PlayKind.UNPAIRED]
        assert "Mannion, Steve R" in [p.white.name for p in unpaired]
        assert all(p.white_score == 0.0 and p.black is None for p in unpaired)

    def test_round_six_results(self):
        round6 = parse_pairings(fixture("british2026_champ_r6.html"), 6)
        played = [p for p in round6 if p.played]
        assert len(played) == 46
        adams = next(p for p in round6 if p.black and p.black.name == "Adams, Michael")
        assert (adams.white.name, adams.raw_result) == ("Han, Yichen", "0 - 1")
        assert (adams.white_score, adams.black_score) == (0.0, 1.0)


class TestFromePairings:
    """A tournament that does publish starting-rank columns."""

    @pytest.fixture(scope="class")
    def round1(self):
        return parse_pairings(fixture("frome2026_open_r1.html"), 1)

    def test_starting_numbers_are_read(self, round1):
        board = round1[0]
        assert (board.white.name, board.white.start_no) == ("Rice, Sean", 19)
        assert (board.black.name, board.black.start_no) == ("Jones, Steven A", 2)

    def test_requested_byes_keep_their_published_value(self, round1):
        byes = [p for p in round1 if p.kind is PlayKind.REQUESTED_BYE]
        assert len(byes) == 12
        assert all(p.white_score == 0.5 for p in byes)

    def test_extra_columns_do_not_shift_the_others(self, round1):
        assert round1[0].white.rating == 2071
        assert round1[0].white_points_before == 0.0


class TestStartingRank:
    @pytest.fixture(scope="class")
    def entries(self):
        return parse_starting_rank(fixture("british2026_champ_startingrank.html"))

    def test_every_player_is_listed(self, entries):
        assert len(entries) == 108
        assert [e.start_no for e in entries] == list(range(1, 109))

    def test_top_seed(self, entries):
        top = entries[0]
        assert (top.start_no, top.name, top.rating, top.title) == (1, "Mcshane, Luke J", 2597, "GM")
        assert (top.fide_id, top.federation) == ("404853", "ENG")

    def test_footnote_markers_are_stripped(self, entries):
        assert any(e.name == "Hebden, Mark L" for e in entries)


class TestRoundNotYetPaired:
    """chess-results renders a table for a round that has not been paired.

    It holds only the withdrawn players' "not paired" rows. Treating it as a
    real round invents a round that does not exist, and makes every player who
    is still in the event look as though they had left it.
    """

    @pytest.fixture(scope="class")
    def rows(self):
        return parse_pairings(fixture("british2026_champ_r8_unpaired_only.html"), 8)

    def test_the_table_parses_but_holds_no_games(self, rows):
        assert rows, "the page does render a table"
        assert not [p for p in rows if p.kind is PlayKind.GAME]

    def test_every_row_is_an_unpaired_player(self, rows):
        assert {p.kind for p in rows} == {PlayKind.UNPAIRED}
        assert "Mannion, Steve R" in [p.white.name for p in rows]
