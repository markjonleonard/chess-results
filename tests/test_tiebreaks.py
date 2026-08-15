"""Generic Swiss tiebreak calculations, pinned against a small hand-built event.

A four-player round-robin-shaped fixture, deliberately small enough to check
each sum by hand: A beats B, A draws C, B beats D, and A has a pairing bye in
round 3 that does not enter anyone's colour or opponent history.
"""

from __future__ import annotations

from chess_results.models import Colour, Play, PlayKind
from chess_results.tiebreaks import black_count, buchholz, head_to_head, progressive_score, sonneborn_berger
from chess_results.tournament import Tournament


def _event() -> Tournament:
    event = Tournament()
    a, b, c, d = (event.player(name) for name in ("A", "B", "C", "D"))

    a.plays = [
        Play(round=1, kind=PlayKind.GAME, colour=Colour.WHITE, opponent="B", score=1.0),
        Play(round=2, kind=PlayKind.GAME, colour=Colour.BLACK, opponent="C", score=0.5),
        Play(round=3, kind=PlayKind.PAIRING_BYE, score=1.0),
    ]
    b.plays = [
        Play(round=1, kind=PlayKind.GAME, colour=Colour.BLACK, opponent="A", score=0.0),
        Play(round=2, kind=PlayKind.GAME, colour=Colour.WHITE, opponent="D", score=1.0),
        Play(round=3, kind=PlayKind.UNPAIRED, score=None),
    ]
    c.plays = [
        Play(round=1, kind=PlayKind.UNPAIRED, score=None),
        Play(round=2, kind=PlayKind.GAME, colour=Colour.WHITE, opponent="A", score=0.5),
        Play(round=3, kind=PlayKind.UNPAIRED, score=None),
    ]
    d.plays = [
        Play(round=1, kind=PlayKind.UNPAIRED, score=None),
        Play(round=2, kind=PlayKind.GAME, colour=Colour.BLACK, opponent="B", score=0.0),
        Play(round=3, kind=PlayKind.UNPAIRED, score=None),
    ]
    return event


class TestProgressiveScore:
    def test_sums_the_running_score_after_each_round(self):
        # A: 1, 1.5, 2.5 -> 5.0
        assert progressive_score(_event().players["A"]) == 5.0

    def test_a_round_not_played_carries_the_running_score_forward(self):
        # B: 0, 1, 1 (unpaired round 3 adds nothing new) -> 2.0
        assert progressive_score(_event().players["B"]) == 2.0

    def test_respects_after(self):
        assert progressive_score(_event().players["A"], after=2) == 2.5


class TestBuchholz:
    def test_sums_opponents_final_scores(self):
        event = _event()
        # A played B (final score 1.0) and C (final score 0.5).
        assert buchholz(event.players["A"], event) == 1.5

    def test_a_bye_contributes_no_opponent(self):
        event = _event()
        # A's round-3 bye has no opponent, so only B and C count.
        assert buchholz(event.players["A"], event) == buchholz(event.players["A"], event, after=2)

    def test_respects_after(self):
        event = _event()
        # After round 1 only: A's sole opponent is B, on 0.0 at that point.
        assert buchholz(event.players["A"], event, after=1) == 0.0


class TestSonnebornBerger:
    def test_a_win_counts_the_opponents_score_in_full(self):
        event = _event()
        # A beat B (final score 1.0) for 1.0, drew C (final score 0.5) for 0.25.
        assert sonneborn_berger(event.players["A"], event) == 1.25

    def test_a_loss_counts_nothing(self):
        event = _event()
        # B lost to A (contributes 0) and beat D (D's final score 0.0, contributes 0).
        assert sonneborn_berger(event.players["B"], event) == 0.0


class TestBlackCount:
    def test_counts_games_played_with_black_only(self):
        # A played black once (round 2); the round-3 bye has no colour.
        assert black_count(_event().players["A"]) == 1

    def test_unpaired_rounds_do_not_count(self):
        assert black_count(_event().players["C"]) == 0


class TestHeadToHead:
    def test_returns_the_result_from_this_players_perspective(self):
        event = _event()
        assert head_to_head(event.players["A"], "B") == 1.0
        assert head_to_head(event.players["B"], "A") == 0.0

    def test_none_when_they_never_played(self):
        event = _event()
        assert head_to_head(event.players["A"], "D") is None

    def test_a_bye_or_unpaired_round_is_not_a_game_against_anyone(self):
        # C's round-1 and round-3 entries are UNPAIRED with no opponent name,
        # so a caller passing an empty name must not accidentally match them.
        event = _event()
        assert head_to_head(event.players["C"], "") is None
