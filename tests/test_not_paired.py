"""The "not paired" page (art=40).

Two of the fixtures are final captures: the British after all 9 rounds, Frome
after all 5. The page ignores ``&rd=``, so a mid-event capture of it cannot be
made after the fact -- there is only ever the current one, which is why the
Jeddah set below had to be caught live and cannot be regenerated.

The interesting tests are the ones that check it against the crosstable, which
is the view whose facts we already trust.
"""

import pytest
from tests.conftest import fixture

from chess_results.models import Absence, PlayKind
from chess_results.parse import parse_crosstable, parse_not_paired


@pytest.fixture(scope="module")
def british_not_paired():
    return parse_not_paired(fixture("british2026_champ_notpaired_final.html"))


@pytest.fixture(scope="module")
def frome_not_paired():
    return parse_not_paired(fixture("frome2026_open_notpaired.html"))


def by_number(entries):
    return {entry.start_no: entry for entry in entries}


class TestTheRowsAndTheirColumns:
    def test_only_players_who_missed_something_are_listed(self, british_not_paired):
        # 15 rows out of a field of 108.
        assert len(british_not_paired) == 15
        assert all(entry.markers for entry in british_not_paired)

    def test_a_player_is_named_as_well_as_numbered(self, british_not_paired):
        """Unlike the crosstable, so this joins to a name-keyed field unaided."""
        mannion = by_number(british_not_paired)[59]
        assert (mannion.name, mannion.title, mannion.rating) == ("Mannion, Steve R", "IM", 2206)
        assert mannion.federation == "SCO"

    def test_an_untitled_player_has_no_title(self, british_not_paired):
        assert by_number(british_not_paired)[54].title is None

    def test_the_three_markers_are_read(self, british_not_paired):
        entries = by_number(british_not_paired)
        assert entries[47].markers[9] is Absence.UNPLAYED
        assert entries[106].markers[6] is Absence.BYE
        assert entries[62].markers[8] is Absence.FORFEIT

    def test_rounds_the_player_played_are_absent_not_blank(self, british_not_paired):
        # Mannion played round 1 and nothing after it.
        assert by_number(british_not_paired)[59].missed == set(range(2, 10))

    def test_rounds_selects_by_marker(self, british_not_paired):
        ruddy = by_number(british_not_paired)[107]
        assert ruddy.rounds(Absence.BYE) == {5}
        assert ruddy.rounds(Absence.UNPLAYED) == {8, 9}
        assert ruddy.rounds(Absence.FORFEIT) == set()


class TestAgainstTheCrosstable:
    """The crosstable is the view we already trust, so agree with it or explain."""

    @pytest.fixture(scope="class")
    def crosstable(self):
        return parse_crosstable(fixture("british2026_champ_crosstable_final.html"))

    def test_every_bye_marker_is_a_pairing_bye_in_the_crosstable(self, british_not_paired, crosstable):
        for entry in british_not_paired:
            for rnd in entry.rounds(Absence.BYE):
                match = [e for e in crosstable[entry.start_no] if e.round == rnd]
                assert [e.kind for e in match] == [PlayKind.PAIRING_BYE]

    def test_a_forfeit_lists_only_the_player_who_defaulted(self, british_not_paired, crosstable):
        """Stubbs defaulted to Cooke in round 9; Cooke took the point and is not here for it."""
        entries = by_number(british_not_paired)
        assert entries[62].markers[9] is Absence.FORFEIT
        assert 9 not in entries[104].missed
        cooke_r9 = [e for e in crosstable[104] if e.round == 9]
        assert [(e.kind, e.score, e.forfeit) for e in cooke_r9] == [(PlayKind.GAME, 1.0, True)]


class TestARequestedByeIsIndistinguishableFromAnAbsence:
    """The limitation that stops this replacing the crosstable.

    Only a pairing-allocated (full-point) bye prints "bye". A requested
    half-point bye prints "*", exactly as a withdrawal does. Frome's round 1 is
    the proof: it has both, and they render identically.
    """

    @pytest.fixture(scope="class")
    def crosstable(self):
        return parse_crosstable(fixture("frome2026_open_crosstable.html"))

    def test_the_half_point_byes_are_marked_unplayed(self, frome_not_paired, crosstable):
        entries = by_number(frome_not_paired)
        for start_no in (8, 21, 29):
            assert entries[start_no].markers[1] is Absence.UNPLAYED
            round_one = [e for e in crosstable[start_no] if e.round == 1]
            assert [e.kind for e in round_one] == [PlayKind.REQUESTED_BYE]

    def test_a_real_absence_is_marked_the_same_way(self, frome_not_paired, crosstable):
        """Chua's round 1 was a half point and his round 5 was nothing. Same marker."""
        chua = by_number(frome_not_paired)[8]
        assert chua.markers[1] is chua.markers[5] is Absence.UNPLAYED
        kinds = {e.round: e.kind for e in crosstable[8]}
        assert (kinds[1], kinds[5]) == (PlayKind.REQUESTED_BYE, PlayKind.UNPAIRED)

    def test_full_point_byes_in_the_same_event_do_print_bye(self, frome_not_paired, crosstable):
        entries = by_number(frome_not_paired)
        assert entries[34].markers[3] is Absence.BYE
        assert [e.kind for e in crosstable[34] if e.round == 3] == [PlayKind.PAIRING_BYE]


class TestADifferentColumnLayout:
    """Frome publishes five rounds and no titles; nothing may be read by offset."""

    def test_the_round_columns_are_read_from_the_header(self, frome_not_paired):
        assert max(rnd for entry in frome_not_paired for rnd in entry.missed) == 5

    def test_it_parses_a_field_with_no_titled_players(self, frome_not_paired):
        assert len(frome_not_paired) == 18
        assert {entry.title for entry in frome_not_paired} == {None}


class TestPagesWithNothingToParse:
    def test_a_page_with_no_such_table_yields_nothing(self):
        assert parse_not_paired("<html><body><p>nothing here</p></body></html>") == []

    def test_a_crosstable_is_not_mistaken_for_one(self):
        """It has round columns too, but numbers its players "No." not "SNo"."""
        assert parse_not_paired(fixture("british2026_champ_crosstable.html")) == []


class TestFeedingItToWithdrawalInference:
    """What the page is actually worth, measured against the crosstable.

    `likely_withdrawn` reads trailing UNPAIRED rounds. Run against round pages
    alone it finds nobody for a superseded round, those being exactly the rows
    chess-results deletes. art=40 is the one-page source of the same facts.
    """

    @pytest.fixture(scope="class")
    def not_paired(self):
        return parse_not_paired(fixture("british2026_champ_notpaired_final.html"))

    def test_round_pages_alone_find_nobody_for_a_superseded_round(self, british_rounds_only):
        """Round 5 has been superseded, so its "not paired" rows are gone."""
        assert british_rounds_only.likely_withdrawn(after=5) == set()

    def test_the_page_recovers_exactly_what_the_crosstable_would_have(
        self, british_rounds_only, british, not_paired
    ):
        recovered = british_rounds_only.likely_withdrawn(after=5, not_paired=not_paired)
        assert recovered == british.likely_withdrawn(after=5)
        assert len(recovered) == 3

    def test_it_adds_nothing_to_a_reconciled_history(self, british, not_paired):
        """The crosstable already holds everything the page says."""
        for after in (5, 6):
            assert british.likely_withdrawn(after=after, not_paired=not_paired) == (
                british.likely_withdrawn(after=after)
            )

    @pytest.mark.parametrize("after", range(1, 8))
    def test_round_pages_plus_the_page_equal_the_crosstable_at_every_round(
        self, british_rounds_only, british, not_paired, after
    ):
        """The whole claim, in one assertion: one page buys what the crosstable does.

        Round pages alone find 0, 0, 0, 0, 0, 3, 5 across rounds 1-7; with the
        page they find 2, 2, 2, 2, 3, 3, 5, which is the crosstable's answer
        exactly.
        """
        assert british_rounds_only.likely_withdrawn(after=after, not_paired=not_paired) == (
            british.likely_withdrawn(after=after)
        )

    def test_the_future_is_not_read_back_into_an_earlier_round(self, british_rounds_only, not_paired):
        """The capture is post-event, so a marker for round 8 must not count at round 5.

        The page is always current and ignores &rd=, so a live prediction after
        round 5 could only ever have seen rounds 1-5 of it.
        """
        after_five = british_rounds_only.likely_withdrawn(after=5, not_paired=not_paired)
        # Badacsonyi stopped after round 4 and is findable; Golding's first missed
        # round is 7, so nothing at round 5 may know about him.
        assert "Badacsonyi, Frankie" in after_five
        assert "Golding, Alex" not in after_five

    def test_a_full_point_bye_is_not_mistaken_for_an_absence(self, british_rounds_only, not_paired):
        """Chapman took a round 6 bye; the page marks it "bye", not "*"."""
        assert "Chapman, Luke" not in british_rounds_only.likely_withdrawn(after=6, not_paired=not_paired)


class TestTheHalfPointByeHazard:
    """art=40 cannot tell a requested bye from an absence, so the marker is only
    consulted for a round nothing else has spoken about."""

    @pytest.fixture(scope="class")
    def frome(self):
        from chess_results.parse import parse_pairings
        from chess_results.tournament import Tournament

        event = Tournament(id="1393521")
        event.add_round(parse_pairings(fixture("frome2026_open_r1.html"), 1))
        event.add_crosstable(parse_crosstable(fixture("frome2026_open_crosstable.html")))
        return event

    def test_twelve_half_point_byes_produce_no_false_alarm(self, frome, frome_not_paired):
        """Their round page still lists them, and a round page beats the marker."""
        assert frome.likely_withdrawn(after=1, not_paired=frome_not_paired) == set()

    def test_the_marker_only_fills_a_round_with_no_play_at_all(self, frome, frome_not_paired):
        bye_takers = [e for e in frome_not_paired if e.markers.get(1) is Absence.UNPLAYED]
        assert len(bye_takers) >= 10  # all of them marked exactly as a withdrawal would be
        assert all(frome.players[e.name].play(1) is not None for e in bye_takers)


class TestItDoesNotWarnInAdvance:
    """Whether a marker can appear for a round that has not been paired yet.

    This is the question the withdrawal ceiling turned on, and until 2026-08-10
    it was answered by inference from the page's semantics rather than by
    observation -- because ``art=40`` ignores ``&rd=``, so the state of a
    half-finished event cannot be recovered afterwards.

    The Jeddah fixtures are that observation, caught live: a 32-player, 7-round
    Swiss with round 1 complete, round 2 paired and half played, and round 3 not
    yet paired. The page carries a column for every one of the seven rounds and
    a marker for round 1 only.
    """

    @pytest.fixture(scope="class")
    def jeddah(self):
        return parse_not_paired(fixture("jeddah2026_notpaired_midevent.html"))

    def test_round_one_is_marked(self, jeddah):
        """Absent, forfeited and bye all appear, so the page is working."""
        assert {e.markers[1] for e in jeddah} == {Absence.UNPLAYED, Absence.FORFEIT, Absence.BYE}

    def test_no_unpaired_round_carries_a_marker(self, jeddah):
        """Rounds 3-7 are unpaired, and none of them says anything about anyone.

        The finding: the page is contemporaneous, never predictive. It records
        a round once that round has been paired, so it cannot tell you who is
        about to be missing from the round you are trying to predict.
        """
        assert all(set(entry.markers) == {1} for entry in jeddah)

    def test_a_live_round_is_silent_here_only_because_nobody_missed_it(self, jeddah):
        """Guarding the reading: round 2 pairs the whole field, so its blankness
        is explained without appealing to how the page treats a live round.
        Rounds 3-7 carry the argument, being unpaired rather than unblemished."""
        from chess_results.parse import parse_pairings, parse_starting_rank

        field = {e.name for e in parse_starting_rank(fixture("jeddah2026_startingrank.html"))}
        round_two = parse_pairings(fixture("jeddah2026_r2_live.html"), 2)
        paired = {p.white.name for p in round_two} | {p.black.name for p in round_two if p.black}
        assert paired == field

    def test_an_unpaired_round_still_renders_an_empty_table(self):
        """Round 3 is not paired, so its page has no rows -- not even withdrawals."""
        from chess_results.parse import parse_pairings

        assert parse_pairings(fixture("jeddah2026_r3_unpaired.html"), 3) == []
