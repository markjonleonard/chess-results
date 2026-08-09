"""Forfeits, against real pages at last.

Until 2026-08-09 no fixture in the repo contained one, so `_crosstable_cell`'s
forfeit branch had never run on anything but invented input. Rounds 8 and 9 of
the 2026 British supply two real ones, both involving Stubbs (starting number
62), who forfeited twice:

    round 8   board 45   Stubbs vs Gunatilake   "- - +"
    round 9   board 48   Cooke  vs Stubbs       "+ - -"

The pair is worth having because it covers both directions on both views: a
forfeit *loss* renders in the crosstable as `100w-` and the matching *win* on
the opponent's row as the same game seen from the other side. A forfeit is
still a game -- it has an opponent and a colour -- which is what separates it
from a bye, and what `Play.forfeit` records is that the *game* was decided by
default. Which player defaulted is carried by the score, not the flag.
"""

import pytest
from tests.conftest import fixture

from chess_results.models import Colour, PlayKind
from chess_results.parse import parse_crosstable, parse_pairings
from chess_results.trf import to_trf

STUBBS = 62
GUNATILAKE = 100
COOKE = 104


def _round_result(line: str, rnd: int) -> str:
    """The result character of one round in a TRF ``001`` record.

    Round fields start at column 92 and repeat every ten, the result being the
    seventh of them -- see TestPlayerLine in test_trf.py for the full layout.
    """
    at = 98 + (rnd - 1) * 10
    return line[at : at + 1]


@pytest.fixture(scope="module")
def round_eight():
    return parse_pairings(fixture("british2026_champ_r8.html"), 8)


@pytest.fixture(scope="module")
def round_nine():
    return parse_pairings(fixture("british2026_champ_r9.html"), 9)


@pytest.fixture(scope="module")
def final_crosstable():
    return parse_crosstable(fixture("british2026_champ_crosstable_final.html"))


def board(pairings, number):
    return next(p for p in pairings if p.board == number)


class TestOnAPairingPage:
    def test_a_forfeit_by_black_is_a_win_for_white(self, round_nine):
        pairing = board(round_nine, 48)
        assert (pairing.white.name, pairing.black.name) == ("Cooke, Suzy G", "Stubbs, Oliver")
        assert pairing.raw_result.startswith("+ -")
        assert (pairing.white_score, pairing.black_score) == (1.0, 0.0)
        assert pairing.forfeit

    def test_a_forfeit_by_white_is_a_win_for_black(self, round_eight):
        pairing = board(round_eight, 45)
        assert (pairing.white.name, pairing.black.name) == ("Stubbs, Oliver", "Gunatilake, Vinuda")
        assert pairing.raw_result.startswith("- -")
        assert (pairing.white_score, pairing.black_score) == (0.0, 1.0)
        assert pairing.forfeit

    def test_it_is_still_a_game_not_a_bye(self, round_nine):
        """Both players have an opponent and a colour; a bye has neither."""
        assert board(round_nine, 48).kind is PlayKind.GAME

    def test_only_the_defaulted_games_are_flagged(self, round_eight, round_nine):
        assert [p.board for p in round_eight if p.forfeit] == [45]
        assert [p.board for p in round_nine if p.forfeit] == [48]


class TestInTheCrosstable:
    """The branch that had no coverage at all: `54b+` / `54b-` shaped cells."""

    def test_a_forfeit_loss_keeps_opponent_and_colour(self, final_crosstable):
        entries = {e.round: e for e in final_crosstable[STUBBS]}
        assert (entries[8].opponent_no, entries[8].colour) == (GUNATILAKE, Colour.WHITE)
        assert (entries[9].opponent_no, entries[9].colour) == (COOKE, Colour.BLACK)
        assert [entries[r].score for r in (8, 9)] == [0.0, 0.0]
        assert all(entries[r].forfeit for r in (8, 9))
        assert all(entries[r].kind is PlayKind.GAME for r in (8, 9))

    def test_the_same_game_is_a_forfeit_win_on_the_other_row(self, final_crosstable):
        for start_no, rnd, colour in ((GUNATILAKE, 8, Colour.BLACK), (COOKE, 9, Colour.WHITE)):
            entry = next(e for e in final_crosstable[start_no] if e.round == rnd)
            assert (entry.opponent_no, entry.colour, entry.score) == (STUBBS, colour, 1.0)
            assert entry.forfeit

    def test_no_other_game_in_the_event_was_defaulted(self, final_crosstable):
        defaulted = {(no, e.round) for no, entries in final_crosstable.items() for e in entries if e.forfeit}
        assert defaulted == {(STUBBS, 8), (STUBBS, 9), (GUNATILAKE, 8), (COOKE, 9)}


class TestTrfEncoding:
    """A forfeit is not a normal result: FIDE writes `+` and `-`, not `1`/`0`.

    Read out of a real TRF file rather than by calling the private encoder, so
    the round columns have to line up as well as the character being right.
    """

    def test_the_defaulting_player_gets_a_minus_and_the_opponent_a_plus(self, british_played_out):
        lines = {
            line[14:47].strip(): line
            for line in to_trf(british_played_out).splitlines()
            if line.startswith("001")
        }
        assert _round_result(lines["Stubbs, Oliver"], 8) == "-"
        assert _round_result(lines["Gunatilake, Vinuda"], 8) == "+"

    def test_a_played_game_is_still_written_as_a_number(self, british_played_out):
        line = next(
            x
            for x in to_trf(british_played_out).splitlines()
            if x.startswith("001") and "Royal, Shreyas" in x
        )
        assert {_round_result(line, r) for r in range(1, 9)} <= {"1", "=", "0"}


class TestTheCurrentRoundKeepsItsUnpairedRows:
    """A round shows its "not paired" rows only until a later round is paired.

    Round 9 was the current round when this fixture was captured -- and being
    the last round of the event, nothing will ever supersede it, so these rows
    are permanent. Round 8 had already lost its own by then. That contrast is
    the vanishing-bye problem in a single test file, and the reason
    `add_crosstable` exists at all.
    """

    def test_round_nine_still_lists_the_players_who_were_not_paired(self, round_nine):
        unpaired = [p for p in round_nine if p.kind is PlayKind.UNPAIRED]
        assert len(unpaired) == 8
        assert "Mannion, Steve R" in {p.white.name for p in unpaired}

    def test_and_they_are_absent_from_the_superseded_round_eight(self, round_eight):
        assert not [p for p in round_eight if p.kind is PlayKind.UNPAIRED]
