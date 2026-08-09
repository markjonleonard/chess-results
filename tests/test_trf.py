"""TRF(x) export.

Column positions are checked directly, because a pairing engine reads this
format by column and misplaced fields fail silently or produce wrong pairings.
"""

import pytest
from tests.conftest import fixture

from chess_results.parse import parse_pairings, parse_starting_rank
from chess_results.tournament import Tournament
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


@pytest.fixture(scope="module")
def five_rounds():
    """Rounds 1-5, every game resulted, so the file can actually be written."""
    event = Tournament(id="1452107", name="five")
    event.add_starting_rank(parse_starting_rank(fixture("british2026_champ_startingrank.html")))
    for rnd in range(1, 6):
        event.add_round(parse_pairings(fixture(f"british2026_champ_r{rnd}.html"), rnd))
    return event


class TestRoundIsClamped:
    """A round beyond the last one played must not widen the file.

    Unclamped, ``after=99`` padded every player line with empty round columns
    and wrote ``XXR 100``, which a pairing engine reads as a 100-round event.
    """

    def test_out_of_range_matches_the_last_round(self, five_rounds):
        assert to_trf(five_rounds, after=99, total_rounds=9) == to_trf(five_rounds, after=5, total_rounds=9)

    def test_player_lines_do_not_grow(self, five_rounds):
        widest = max(
            len(ln)
            for ln in to_trf(five_rounds, after=99, total_rounds=9).splitlines()
            if ln.startswith("001")
        )
        assert widest == 139

    def test_xxr_is_not_inflated(self, five_rounds):
        assert "XXR 6" in to_trf(five_rounds, after=99)

    def test_the_clamp_is_reported_in_errors_too(self, played):
        """The complaint names the real last round, not the one asked for."""
        with pytest.raises(TrfError, match=r"rounds 1-7"):
            to_trf(played, after=99)


class TestNonStandardByeValues:
    """bbpPairings recomputes every score from the results and refuses a file
    whose totals disagree, so what a bye is worth has to be stated."""

    def _event(self, bye_value):
        from tests.conftest import _round_fixture

        from chess_results.parse import parse_crosstable

        event = Tournament(id="1452107", name="British", bye_value=bye_value)
        event.add_starting_rank(parse_starting_rank(fixture("british2026_champ_startingrank.html")))
        for rnd in range(1, 9):
            name = _round_fixture(rnd, played_out=True)
            event.add_round(parse_pairings(fixture(f"{name}.html"), rnd, bye_value=bye_value))
        event.add_crosstable(parse_crosstable(fixture("british2026_champ_crosstable_final.html")))
        return event

    def test_a_bye_recovered_from_the_crosstable_takes_the_tournament_value(self):
        """The crosstable prints every pairing-allocated bye as 1, whatever is awarded.

        All four of the British byes reach the history this way -- their round
        pages had been superseded -- so before this was honoured the bye value
        had no effect on that event at all.
        """
        half = self._event(0.5)
        cooke = half.players["Cooke, Suzy G"]
        assert cooke.play(8).score == 0.5
        assert cooke.play(8).from_crosstable

    def test_the_full_point_case_is_unchanged(self):
        assert self._event(1.0).players["Cooke, Suzy G"].play(8).score == 1.0

    def test_the_score_moves_with_it(self):
        full = self._event(1.0).players["Cooke, Suzy G"].score(8)
        assert self._event(0.5).players["Cooke, Suzy G"].score(8) == full - 0.5

    def test_bbu_declares_a_half_point_bye(self):
        lines = to_trf(self._event(0.5), after=8, total_rounds=9).splitlines()
        assert "BBU  0.5" in lines

    def test_a_full_point_bye_needs_no_declaration(self):
        """It is the default, and a redundant line is one more thing to get wrong."""
        lines = to_trf(self._event(1.0), after=8).splitlines()
        assert not [line for line in lines if line.startswith("BBU")]

    def test_an_explicit_argument_still_wins(self):
        lines = to_trf(self._event(1.0), after=8, bye_value=0.5).splitlines()
        assert "BBU  0.5" in lines

    def test_the_convention_difference_is_not_reported_as_a_disagreement(self):
        """The crosstable's 1.0 against the tournament's 0.5 is convention, not conflict."""
        assert self._event(0.5).disagreements == []
