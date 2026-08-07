"""TRF(x) export.

Column positions are checked directly, because a pairing engine reads this
format by column and misplaced fields fail silently or produce wrong pairings.
"""

import pytest

from chess_results.trf import TrfError, to_trf


@pytest.fixture(scope="module")
def played(british):
    """Rounds 1-6 with the six unfinished games decided as they actually went."""
    round7 = british.rounds[7]
    after6 = {}
    for p in round7:
        if p.white_points_before is not None:
            after6[p.white.name] = p.white_points_before
        if p.black and p.black_points_before is not None:
            after6[p.black.name] = p.black_points_before
    for pairing in british.rounds[6]:
        if pairing.white_score is not None or pairing.black is None:
            continue
        white, black = british.players[pairing.white.name], british.players[pairing.black.name]
        w = after6[white.name] - white.score(after=5)
        pairing.white_score = white.play(6).score = w
        pairing.black_score = black.play(6).score = 1.0 - w
    return british


class TestPlayerLine:
    @pytest.fixture(scope="class")
    def line(self, played):
        text = to_trf(played, after=6, total_rounds=9)
        return next(line for line in text.splitlines() if "Mcshane" in line)

    def test_identifier_and_starting_number(self, line):
        assert line[0:3] == "001"
        assert line[4:8] == "   1"

    def test_title_name_and_rating(self, line):
        assert line[10:13] == "GM "
        assert line[14:47].strip() == "Mcshane, Luke J"
        assert line[48:52] == "2597"

    def test_federation_and_fide_id(self, line):
        assert line[53:56] == "ENG"
        assert line[57:68].strip() == "404853"

    def test_points_and_rank(self, line):
        assert line[80:84] == " 5.0"
        assert line[85:89].strip() == "1"

    def test_round_fields_repeat_every_ten_columns(self, line):
        # Round 1: black against seed 54; round 6: white against seed 10, won.
        assert (line[91:95].strip(), line[96], line[98]) == ("54", "b", "1")
        assert (line[141:145].strip(), line[146], line[148]) == ("10", "w", "1")

    def test_a_draw_is_an_equals_sign(self, line):
        assert line[106] == "w" and line[108] == "="


class TestTournamentFile:
    def test_header_and_round_count(self, played):
        text = to_trf(played, after=6, total_rounds=9)
        assert text.splitlines()[0].startswith("012 ")
        assert "XXR 9" in text

    def test_one_record_per_player(self, played):
        text = to_trf(played, after=6, total_rounds=9)
        assert sum(1 for line in text.splitlines() if line.startswith("001")) == 108

    def test_withdrawn_players_get_a_zero_point_bye_next_round(self, played):
        text = to_trf(played, after=6, total_rounds=9, withdrawn={"Mannion, Steve R"})
        line = next(line for line in text.splitlines() if "Mannion" in line)
        # Round 7 begins at column 92 + 6*10 = 152.
        assert (line[151:155], line[156], line[158]) == ("0000", "-", "Z")

    def test_unfinished_games_are_refused(self, british):
        with pytest.raises(TrfError, match="have no result"):
            to_trf(british, after=7)
