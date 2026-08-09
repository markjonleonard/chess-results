"""Assembling rounds into player histories.

The fixtures are the 2026 British Championship caught mid-event, which is a
useful test case: round 6 has unfinished games, round 7 is paired but unplayed,
the field contains byes and unpaired players, and the tournament publishes no
starting-rank columns on its pairing pages.
"""

from chess_results.models import Colour, PlayKind, Preference


class TestPlayerHistories:
    def test_starting_numbers_come_from_the_starting_rank_list(self, british):
        assert british.players["Mcshane, Luke J"].start_no == 1
        assert british.players["Bazakutsa, Svyatoslav"].start_no == 6

    def test_colour_history(self, british):
        mcshane = british.players["Mcshane, Luke J"]
        assert "".join(c.value for c in mcshane.colours(after=6)) == "bwbwbw"
        assert mcshane.colour_difference(after=6) == 0

    def test_opponents(self, british):
        bazakutsa = british.players["Bazakutsa, Svyatoslav"]
        assert bazakutsa.opponents(after=6)[3:] == [
            "Adams, Michael",
            "Royal, Shreyas",
            "Grieve, Harry",
        ]

    def test_mild_preference_alternates_from_the_last_colour(self, british):
        mcshane = british.players["Mcshane, Luke J"]
        assert mcshane.colour_preference(after=6) == (Colour.BLACK, Preference.MILD)

    def test_absolute_preference_at_two_colours_apart(self, british):
        bazakutsa = british.players["Bazakutsa, Svyatoslav"]
        assert bazakutsa.colour_difference(after=6) == 2
        assert bazakutsa.colour_preference(after=6) == (Colour.BLACK, Preference.ABSOLUTE)

    def test_scores_ignore_unfinished_games(self, british):
        # McShane's round 6 game had not finished when these pages were captured.
        assert british.players["Mcshane, Luke J"].score(after=6) == 4.0
        assert british.players["Grieve, Harry"].score(after=6) == 5.0

    def test_floats_are_inferred_from_pre_round_scores(self, british):
        bazakutsa = british.players["Bazakutsa, Svyatoslav"]
        royal = british.players["Royal, Shreyas"]
        assert bazakutsa.play(5).float_direction == "D"
        assert royal.play(5).float_direction == "U"
        assert bazakutsa.play(6).float_direction is None, "both were on 4½"

    def test_a_bye_counts_as_a_downfloat(self, british):
        chapman = british.players["Chapman, Luke"]
        assert chapman.play(6).kind is PlayKind.PAIRING_BYE
        assert chapman.play(6).float_direction == "D"

    def test_byes_do_not_enter_the_colour_history(self, british):
        chapman = british.players["Chapman, Luke"]
        assert chapman.play(6).colour is None
        assert len(chapman.colours(after=6)) < 6


class TestStandings:
    def test_ranking_order_is_score_then_starting_number(self, british):
        top = british.ranking_order(after=5)[:4]
        # Grieve is seeded 4 and Bazakutsa 6, so Grieve leads the 4½ group even
        # though Bazakutsa had White on board 1 of round 6.
        assert [p.name for p in top] == [
            "Grieve, Harry",
            "Bazakutsa, Svyatoslav",
            "Mcshane, Luke J",
            "Adams, Michael",
        ]

    def test_scoregroups_are_ordered_high_to_low(self, british):
        groups = british.scoregroups(after=5)
        assert list(groups)[:3] == [4.5, 4.0, 3.5]
        assert [p.name for p in groups[4.5]] == ["Grieve, Harry", "Bazakutsa, Svyatoslav"]

    def test_everyone_is_accounted_for(self, british):
        assert len(british.players) == 108
        assert sum(len(g) for g in british.scoregroups(after=5).values()) == 108


class TestUnfinished:
    def test_round_six_games_still_in_progress(self, british):
        games = british.unfinished(rnd=6)
        assert [g.board for g in games] == [2, 18, 20, 25, 44, 50]
        assert games[0].white.name == "Mcshane, Luke J"

    def test_a_paired_but_unplayed_round_is_entirely_unfinished(self, british):
        assert len(british.unfinished(rnd=7)) == 51


class TestLikelyWithdrawn:
    """Guessing who has left, since chess-results never says.

    The evidence only survives in the crosstable: a round page deletes its "not
    paired" rows as soon as a later round is paired, so the signal these read is
    exactly what ``add_crosstable`` restores.
    """

    def test_players_unpaired_in_the_latest_round_are_flagged(self, british):
        assert british.likely_withdrawn(after=6) == {
            "Badacsonyi, Frankie",
            "Brown, Stephanie",
            "Mannion, Steve R",
        }

    def test_it_defaults_to_the_last_round_scraped(self, british):
        assert british.likely_withdrawn() == british.likely_withdrawn(after=british.last_round)

    def test_requiring_more_rounds_trades_recall_for_precision(self, british):
        """Badacsonyi played round 4, so a three-round window no longer flags them."""
        loose = british.likely_withdrawn(after=6, consecutive=1)
        strict = british.likely_withdrawn(after=6, consecutive=3)
        assert strict < loose
        assert "Badacsonyi, Frankie" in loose - strict

    def test_the_window_cannot_run_off_the_front_of_the_event(self, british):
        """consecutive=9 at round 6 must not silently flag the whole field."""
        assert british.likely_withdrawn(after=6, consecutive=9) == british.likely_withdrawn(
            after=6, consecutive=6
        )

    def test_before_any_round_nobody_is_withdrawn(self, british):
        assert british.likely_withdrawn(after=0) == set()

    def test_the_signal_is_lost_without_the_crosstable(self, british, british_rounds_only):
        """Round pages alone find nobody once the round has been superseded.

        Round 5's "not paired" rows were deleted when round 6 was paired, so the
        round pages carry no trace of three players who had already stopped. The
        crosstable is the only reason this works at all.
        """
        assert british_rounds_only.likely_withdrawn(after=5) == set()
        assert len(british.likely_withdrawn(after=5)) == 3

    def test_a_current_round_still_shows_its_own_unpaired_rows(self, british, british_rounds_only):
        """The mid-round round-6 capture keeps them, so both views agree there."""
        assert british_rounds_only.likely_withdrawn(after=6) == british.likely_withdrawn(after=6)

    def test_a_requested_bye_is_not_a_withdrawal(self, frome_round_one):
        """A half-point bye is a player sitting out one round, not leaving."""
        assert frome_round_one.likely_withdrawn(after=1) == set()
        assert any(
            p.kind is PlayKind.REQUESTED_BYE for pl in frome_round_one.players.values() for p in pl.plays
        )
