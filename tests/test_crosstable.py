"""Recovering rounds the pairing pages have dropped.

A round's pairing page lists byes and unpaired players only while that round is
the current one. Once a later round is paired those rows are deleted, so a
full-point bye vanishes and the player's score comes out a point light. The
crosstable keeps the whole record.
"""

import pytest
from tests.conftest import _british, fixture

from chess_results.models import Colour, PlayKind
from chess_results.parse import parse_crosstable, parse_published_totals


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


class TestPublishedTotals:
    """The TB1 column is the arbiter's own arithmetic, so the round-by-round
    cells we read out of the same row must sum to it."""

    @pytest.mark.parametrize(
        ("name", "players"),
        [
            ("british2026_champ_crosstable", 108),
            ("british2026_champ_crosstable_final", 108),
            ("frome2026_open_crosstable", 38),
        ],
    )
    def test_every_published_total_is_read(self, name, players):
        totals = parse_published_totals(fixture(f"{name}.html"))
        assert len(totals) == players

    def test_a_half_point_total_survives_the_decimal_comma(self):
        """5,5 in the source; the whole point of reading this column."""
        totals = parse_published_totals(fixture("british2026_champ_crosstable_final.html"))
        assert 5.5 in totals.values()
        assert all(t % 0.5 == 0 for t in totals.values())

    @pytest.mark.parametrize(
        "name",
        [
            "british2026_champ_crosstable",
            "british2026_champ_crosstable_final",
            "frome2026_open_crosstable",
        ],
    )
    def test_our_cells_sum_to_the_published_total_for_every_player(self, name):
        """254 player-rows across three captures, and all of them agree."""
        event = _british(crosstable=False)
        html = fixture(f"{name}.html")
        assert event.check_published_totals(parse_crosstable(html), parse_published_totals(html)) == []

    def test_a_page_without_the_column_yields_nothing(self):
        assert parse_published_totals(fixture("british2026_champ_r5.html")) == {}

    def test_a_wrong_total_is_caught_and_named(self):
        event = _british(crosstable=False)
        html = fixture("british2026_champ_crosstable.html")
        totals = parse_published_totals(html)
        totals[1] = totals[1] + 1
        found = event.check_published_totals(parse_crosstable(html), totals)
        assert len(found) == 1
        assert found[0].field == "total"
        assert found[0].player == "Mcshane, Luke J"
        assert "sum to 5.0 but it publishes 6.0" in str(found[0])

    def test_it_is_not_compared_against_the_assembled_history(self):
        """A published total and an assembled score cover the same rounds only by luck.

        The mid-event crosstable is a later capture than the round pages, so
        comparing the two produces 75 mismatches on a healthy tournament.
        """
        html = fixture("british2026_champ_crosstable.html")
        totals = parse_published_totals(html)
        event = _british(crosstable=True)
        by_no = {p.start_no: p for p in event.players.values() if p.start_no}
        differing = [no for no, total in totals.items() if by_no[no].score(7) != total]
        assert len(differing) == 75
        assert [d for d in event.disagreements if d.field == "total"] == []


class TestTheScoreColumnIsNotAlwaysTB1:
    """TB1 holds the score on some events and a tiebreak on others.

    The 2026 British and Frome both print TB1 and no Pts. column, and their TB1
    *is* the score -- which is what made it look like a rule. Arad 2026 prints
    both: Pts. is the score and TB1 is a rating tiebreak, so reading TB1 gave
    the top seed a total of 2369 and reported 208 of 209 players as disagreeing
    with themselves. A wrong column is worse than no column, because it buries
    a real disagreement in a page of false ones.
    """

    @staticmethod
    def _header(name):
        from chess_results.parse import _data_tables, _header_row

        for table in _data_tables(fixture(name)):
            found = _header_row(table, "No.")
            if found:
                return found[0]
        raise AssertionError("no crosstable header")

    def test_arad_publishes_both_columns(self):
        """Guarding the premise: if this event stopped printing Pts. the test
        below would pass for the wrong reason."""
        header = self._header("arad2026_a_crosstable.html")
        assert "Pts." in header
        assert "TB1" in header

    def test_the_score_is_read_from_points_not_the_tiebreak(self):
        totals = parse_published_totals(fixture("arad2026_a_crosstable.html"))
        # Kovalenko is seed 1 and scored 6 of 9. TB1 on his row is 2369.
        assert totals[1] == 6.0
        assert max(totals.values()) <= 9

    def test_the_whole_event_then_agrees_with_itself(self):
        from chess_results.tournament import Tournament

        html = fixture("arad2026_a_crosstable.html")
        event = Tournament(id="1342553")
        cross = parse_crosstable(html)
        event.add_crosstable(cross)
        assert len(cross) == 209
        assert event.check_published_totals(cross, parse_published_totals(html)) == []

    def test_tb1_is_still_used_where_it_is_the_only_candidate(self):
        """The British prints no Pts. column, and its TB1 is the score."""
        assert "Pts." not in self._header("british2026_champ_crosstable_final.html")
        totals = parse_published_totals(fixture("british2026_champ_crosstable_final.html"))
        assert totals and max(totals.values()) <= 9

    def test_an_implausible_column_is_refused_rather_than_believed(self):
        """No score can exceed the rounds played, so a rating in that column is
        rejected outright. Returning nothing reads as "no totals to check
        against"; returning ratings would fail every player in the event."""
        html = fixture("arad2026_a_crosstable.html").replace(">Pts.<", ">Xx.<")
        assert parse_published_totals(html) == {}


class TestRecoveredPlaysAreNeverGames:
    """Why a recovered play needing no float direction costs nothing.

    A Play restored from the crosstable has no ``points_before`` -- the
    crosstable prints no pre-round score -- so ``_floats`` cannot run on it and
    only the bye-is-a-downfloat rule applies. That looks like a gap and is not
    one: ``add_crosstable`` fills only rounds already fetched, and the only
    rows chess-results deletes from a round page are byes and "not paired". A
    game row is never removed, so a recovered game does not arise.

    These pin that, because the reasoning above is what makes the missing
    float safe to leave alone.
    """

    @pytest.mark.parametrize("played_out", [False, True])
    def test_every_recovered_play_is_a_bye_or_an_absence(self, played_out, request):
        event = request.getfixturevalue("british_played_out" if played_out else "british")
        recovered = [p for pl in event.players.values() for p in pl.plays if p.from_crosstable]
        assert recovered, "fixture no longer exercises recovery at all"
        assert all(p.kind is not PlayKind.GAME for p in recovered)

    def test_a_recovered_bye_still_counts_as_a_downfloat(self, british_played_out):
        byes = [
            p
            for pl in british_played_out.players.values()
            for p in pl.plays
            if p.from_crosstable and p.kind is PlayKind.PAIRING_BYE
        ]
        assert byes
        assert all(p.float_direction == "D" for p in byes)

    def test_a_recovered_absence_floats_nowhere(self, british_played_out):
        """Correct rather than missing: an unpaired player did not float."""
        absences = [
            p
            for pl in british_played_out.players.values()
            for p in pl.plays
            if p.from_crosstable and p.kind is PlayKind.UNPAIRED
        ]
        assert absences
        assert all(p.float_direction is None for p in absences)
