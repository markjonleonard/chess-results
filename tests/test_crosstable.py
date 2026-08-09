"""Recovering rounds the pairing pages have dropped.

A round's pairing page lists byes and unpaired players only while that round is
the current one. Once a later round is paired those rows are deleted, so a
full-point bye vanishes and the player's score comes out a point light. The
crosstable keeps the whole record.
"""

import pytest
from tests.conftest import _british, fixture

from chess_results.models import Colour, PlayKind
from chess_results.parse import parse_crosstable


@pytest.fixture(scope="module")
def british_crosstable():
    return parse_crosstable(fixture("british2026_champ_crosstable.html"))


@pytest.fixture(scope="module")
def frome_crosstable():
    return parse_crosstable(fixture("frome2026_open_crosstable.html"))


class TestParsing:
    def test_every_player_has_a_row(self, british_crosstable):
        assert len(british_crosstable) == 108
        assert set(british_crosstable) == set(range(1, 109))

    def test_a_game_gives_opponent_colour_and_result(self, british_crosstable):
        # "54b1": beat starting number 54 with Black.
        first = british_crosstable[1][0]
        assert (first.kind, first.opponent_no) == (PlayKind.GAME, 54)
        assert (first.colour, first.score) == (Colour.BLACK, 1.0)

    def test_a_full_point_is_a_pairing_allocated_bye(self, british_crosstable):
        # Chapman is seed 106; his round 6 reads "-1".
        round6 = british_crosstable[106][5]
        assert (round6.round, round6.kind, round6.score) == (6, PlayKind.PAIRING_BYE, 1.0)
        assert round6.opponent_no is None and round6.colour is None

    def test_no_points_at_all_is_an_unpaired_round(self, british_crosstable):
        # Kothari, seed 69, entered late: rounds 1-2 read "-0".
        assert [e.kind for e in british_crosstable[69][:2]] == [PlayKind.UNPAIRED] * 2

    def test_a_half_point_is_a_requested_bye(self, frome_crosstable):
        # A congress where many players take a half-point bye in round 1.
        halves = [
            e for entries in frome_crosstable.values() for e in entries if e.kind is PlayKind.REQUESTED_BYE
        ]
        assert len(halves) == 14
        assert {e.score for e in halves} == {0.5}

    def test_a_page_without_round_columns_yields_nothing(self):
        assert parse_crosstable(fixture("british2026_champ_startingrank.html")) == {}


class TestReconciliation:
    def test_the_round_pages_alone_lose_a_bye(self, british_rounds_only):
        """Ruddy's round 5 bye is gone: round 7 was current when this was scraped."""
        ruddy = british_rounds_only.players["Ruddy, Rachel"]
        assert ruddy.play(5) is None
        assert ruddy.score() == 0.5

    def test_the_crosstable_puts_it_back(self, british):
        ruddy = british.players["Ruddy, Rachel"]
        assert ruddy.play(5).kind is PlayKind.PAIRING_BYE
        assert ruddy.play(5).score == 1.0
        assert ruddy.score() == 1.5

    def test_every_player_has_every_round(self, british):
        for player in british.players.values():
            rounds = {p.round for p in player.plays}
            assert rounds == set(range(1, british.last_round + 1)), player.name

    def test_recovered_plays_are_marked(self, british):
        recovered = [p for pl in british.players.values() for p in pl.plays if p.from_crosstable]
        assert recovered, "the fixtures do need reconciling"
        # The crosstable publishes no board numbers or pre-round scores.
        assert all(p.board is None and p.points_before is None for p in recovered)

    def test_results_from_the_pairing_pages_are_left_alone(self, british):
        """Round 6 was still current when captured, so its bye survived there."""
        chapman = british.players["Chapman, Luke"]
        assert chapman.play(6).kind is PlayKind.PAIRING_BYE
        assert chapman.play(6).from_crosstable is False
        assert chapman.play(6).board == 53, "read from the pairing page"

    def test_a_recovered_bye_still_counts_as_a_downfloat(self, british):
        assert british.players["Ruddy, Rachel"].play(5).float_direction == "D"

    def test_rounds_not_fetched_are_not_invented(self, british):
        limited = british.rounds.keys()
        assert max(limited) == 7, "the crosstable must not add rounds of its own"

    def test_reconciling_twice_changes_nothing(self, british):
        before = {n: len(p.plays) for n, p in british.players.items()}
        added = british.add_crosstable(parse_crosstable(fixture("british2026_champ_crosstable.html")))
        assert added == []
        assert {n: len(p.plays) for n, p in british.players.items()} == before


class TestCrossCheckingTheTwoViews:
    """The round pages and the crosstable come from the same upload, so they
    ought to agree. Where both have a round, `add_crosstable` compares them."""

    def test_the_real_fixtures_never_disagree(self, british, british_played_out):
        """Both directions of the British, mid-event and played out."""
        assert british.disagreements == []
        assert british_played_out.disagreements == []

    def test_frome_agrees_too(self, frome_round_one):
        assert frome_round_one.disagreements == []

    def test_a_capture_taken_later_is_not_a_disagreement(self, british):
        """The mid-event crosstable holds 114 results the round pages had not caught.

        A round page carries no result until the game finishes, and the crosstable
        fixture was saved later than the round 6 and 7 pages. One view having a
        value the other lacks is a difference in freshness, not a contradiction.
        """
        assert not [d for d in british.disagreements if d.field == "score"]

    def _corrupt(self, crosstable, start_no, rnd, **changes):
        import dataclasses

        return {
            no: [
                dataclasses.replace(e, **changes) if no == start_no and e.round == rnd else e for e in entries
            ]
            for no, entries in crosstable.items()
        }

    def test_a_flipped_colour_is_caught(self):
        event = _british_rounds_only()
        crosstable = self._corrupt(
            parse_crosstable(fixture("british2026_champ_crosstable.html")),
            start_no=1,
            rnd=1,
            colour=Colour.WHITE,  # McShane had black on board 1
        )
        event.add_crosstable(crosstable)
        assert [(d.field, d.round) for d in event.disagreements] == [("colour", 1)]

    def test_a_changed_score_is_caught_and_reads_clearly(self):
        event = _british_rounds_only()
        crosstable = self._corrupt(
            parse_crosstable(fixture("british2026_champ_crosstable.html")),
            start_no=1,
            rnd=1,
            score=0.0,
        )
        event.add_crosstable(crosstable)
        assert len(event.disagreements) == 1
        assert "round 1" in str(event.disagreements[0])
        assert "score is 1.0 on the round page but 0.0 in the crosstable" in str(event.disagreements[0])

    def test_the_pairing_page_still_wins(self):
        """A disagreement is reported, never silently resolved."""
        event = _british_rounds_only()
        name = next(p.name for p in event.players.values() if p.start_no == 1)
        before = event.players[name].play(1).score
        event.add_crosstable(
            self._corrupt(
                parse_crosstable(fixture("british2026_champ_crosstable.html")),
                start_no=1,
                rnd=1,
                score=0.0,
            )
        )
        assert event.players[name].play(1).score == before


def _british_rounds_only():
    """A fresh, unreconciled event -- the session fixtures must not be mutated."""
    return _british(crosstable=False)
