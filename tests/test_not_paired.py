"""The "not paired" page (art=40).

Both fixtures are final captures: the British after all 9 rounds, Frome after
all 5. The page ignores ``&rd=``, so a mid-event capture of it cannot be made
after the fact -- there is only ever the current one.

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
