"""Several tournaments held together as one event.

A congress is the shape the site does not model: Frome 2026 is five tournament
numbers with nothing on chess-results.com linking them, so the grouping and the
section names both come from the caller. These cover what holding them together
buys -- a section-tagged flat export, and lookups that only mean anything once
the sections are in one place.

`Tournament.rows()` is tested here too rather than in test_tournament.py. It
exists to serve `Congress.rows()`, the two share their caveats about `score`
and `rating`, and splitting them would separate the caveat from the case that
motivates it.
"""

import pytest
from tests.conftest import fixture

from chess_results.client import ChessResults, RoundRobinError, TournamentNotStartedError
from chess_results.congress import Congress, build
from chess_results.models import Player, PlayKind
from chess_results.parse import parse_pairings
from chess_results.tournament import Tournament

OPEN_PLAYERS = 38
STANDARD_PLAYERS = 31


class TestHoldingSectionsTogether:
    def test_the_sections_keep_the_order_they_were_given(self, frome_congress):
        """Usually strongest first, and everything reports in this order."""
        assert list(frome_congress) == ["Open", "Standard"]
        assert len(frome_congress) == 2

    def test_a_section_is_reached_by_the_name_the_caller_chose(self, frome_congress):
        assert "Open" in frome_congress
        assert "U1750" not in frome_congress
        assert len(frome_congress["Open"].players) == OPEN_PLAYERS

    def test_entries_are_counted_across_the_whole_congress(self, frome_congress):
        assert frome_congress.player_count == OPEN_PLAYERS + STANDARD_PLAYERS

    def test_the_last_round_is_the_furthest_any_section_reached(self, frome_congress):
        """A maximum, not a shared fact -- sections need not run the same schedule."""
        assert frome_congress.last_round == 1

    def test_disagreements_gather_from_every_section(self, frome_congress):
        assert frome_congress.disagreements == []

    def test_build_takes_tournaments_already_in_hand(self):
        one = Tournament(id="a")
        assert build({"Major": one}, name="Somewhere Congress").sections == {"Major": one}


class TestFindingAPlayer:
    """Why there is no merged `players` dict.

    Merging name-keyed sections would drop one of two players sharing a name,
    silently. It is a rare case rather than a likely one -- Frome 2026's 191
    players over five sections contain no repeated name, and the ten surnames
    that do span sections all have distinct first names, families being exactly
    what "Surname, Firstname" keeps apart. `find` returns every match with its
    section because that costs nothing when there is one.
    """

    def test_a_player_is_found_with_their_section(self, frome_congress):
        found = frome_congress.find("Jones, Steven A")
        assert list(found) == ["Open"]
        assert found["Open"].name == "Jones, Steven A"

    def test_someone_who_did_not_play_is_simply_absent(self, frome_congress):
        assert frome_congress.find("Carlsen, Magnus") == {}
        assert frome_congress.section_of("Carlsen, Magnus") is None

    def test_section_of_answers_the_ordinary_case(self, frome_congress):
        assert frome_congress.section_of("Jones, Steven A") == "Open"

    #: Constructed, because no real congress to hand contains a collision --
    #: which is the point of the docstring above, not a gap in the fixtures.
    SHARED = "Smith, John"

    def _two_of_them(self):
        return Congress(
            sections={
                section: Tournament(id=section, players={self.SHARED: Player(name=self.SHARED)})
                for section in ("Major", "Minor")
            }
        )

    def test_the_real_sections_do_not_actually_collide(self, frome_congress):
        """The measurement behind the docstring, kept honest.

        Written down because the first version of this class justified itself
        with families entering different sections -- which is the one case that
        cannot collide, first names differing. If a fixture ever does contain a
        repeat, this fails and the prose needs revisiting rather than the code.
        """
        names = [name for event in frome_congress.sections.values() for name in event.players]
        assert len(names) == len(set(names))

    def test_a_shared_surname_across_sections_is_not_a_shared_name(self, frome_congress):
        """Hill plays the Open and the Standard, and they are two people.

        The case that looks like a collision and is not: the key is the whole
        "Surname, Firstname", so the two never meet. Everything a congress
        actually contains looks like this.
        """
        assert frome_congress.section_of("Hill, Andy") == "Open"
        assert frome_congress.section_of("Hill, Glyn") == "Standard"
        assert frome_congress.find("Hill") == {}, "a surname is not a key here"

    def test_one_name_in_two_sections_returns_both(self):
        assert list(self._two_of_them().find(self.SHARED)) == ["Major", "Minor"]

    def test_and_section_of_refuses_to_choose_between_them(self):
        assert self._two_of_them().section_of(self.SHARED) is None, "two answers is not one answer"


class TestTheFlatExport:
    def test_one_row_per_player_per_round(self, frome_congress):
        assert len(frome_congress.rows()) == OPEN_PLAYERS + STANDARD_PLAYERS

    def test_every_row_carries_its_section(self, frome_congress):
        sections = {row["section"] for row in frome_congress.rows()}
        assert sections == {"Open", "Standard"}

    def test_rounds_come_together_across_sections_rather_than_section_by_section(self, frome_congress):
        """The file reads the way the weekend ran: round, then section, then board."""
        keys = [(row["round"], row["section"], row["board"]) for row in frome_congress.rows()]
        assert keys == sorted(keys, key=lambda k: (k[0], k[1], k[2] is None, k[2] or 0))

    def test_a_row_says_what_the_player_did(self, frome_congress):
        row = next(r for r in frome_congress.rows() if r["name"] == "Jones, Steven A")
        assert row["section"] == "Open"
        assert (row["round"], row["board"], row["colour"]) == (1, 1, "b")
        assert (row["opponent"], row["score"]) == ("Rice, Sean", 1.0)
        assert row["kind"] == PlayKind.GAME.value

    def test_the_congress_row_is_the_tournament_row_plus_a_section(self, frome_congress):
        congress_row = next(r for r in frome_congress.rows() if r["name"] == "Jones, Steven A")
        section_row = next(r for r in frome_congress["Open"].rows() if r["name"] == "Jones, Steven A")
        assert congress_row == {**section_row, "section": "Open"}


class TestTournamentRows:
    def test_one_row_per_player_per_round(self, british_played_out):
        expected = sum(len(p.plays) for p in british_played_out.players.values())
        assert len(british_played_out.rows()) == expected

    def test_rounds_sort_first_then_boards(self, british_played_out):
        keys = [
            (r["round"], r["board"] is None, r["board"] or 0, r["name"]) for r in british_played_out.rows()
        ]
        assert keys == sorted(keys)

    def test_a_boardless_round_sorts_after_the_boards(self, british_played_out):
        """Byes and rounds recovered from the crosstable have no board number."""
        round_six = [r for r in british_played_out.rows() if r["round"] == 6]
        boardless = [i for i, r in enumerate(round_six) if r["board"] is None]
        assert boardless, "the fixture does need to exercise this"
        assert min(boardless) == len(round_six) - len(boardless)

    def test_an_unpaired_round_is_scored_zero_and_says_so(self, british_played_out):
        """The caveat the docstring carries, pinned.

        `score` is what the library holds, and it scores an unpaired round 0 --
        which is not the same as a round drawn nil. Anything summing this
        column has to read `kind` alongside it, or a player who withdrew looks
        present and beaten in every round after they went home.
        """
        unpaired = [r for r in british_played_out.rows() if r["kind"] == PlayKind.UNPAIRED.value]
        assert unpaired, "the fixture does need to exercise this"
        assert {r["score"] for r in unpaired} == {0.0}
        assert {r["opponent"] for r in unpaired} == {None}

    def test_a_recovered_round_is_marked_as_such(self, british_played_out):
        recovered = [r for r in british_played_out.rows() if r["from_crosstable"]]
        assert recovered
        assert all(r["board"] is None and r["points_before"] is None for r in recovered)

    def test_a_forfeit_keeps_its_opponent(self, british_played_out):
        """A forfeit is a game; only a bye has no opponent.

        Two rows, not four: this fixture stops after round 8, so it holds the
        Stubbs/Gunatilake default and not the Cooke/Stubbs one from round 9.
        """
        forfeits = [r for r in british_played_out.rows() if r["forfeit"]]
        assert {(r["round"], r["name"]) for r in forfeits} == {
            (8, "Stubbs, Oliver"),
            (8, "Gunatilake, Vinuda"),
        }
        assert all(r["kind"] == PlayKind.GAME.value and r["opponent"] for r in forfeits)


class _StubSections(ChessResults):
    """A client whose sections are decided in advance, so no page is fetched."""

    def __init__(self, outcomes):
        super().__init__()
        self.outcomes = outcomes
        self.asked = []

    def tournament(self, tournament_id, **kwargs):
        self.asked.append(str(tournament_id))
        outcome = self.outcomes[str(tournament_id)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class TestFetchingOne:
    def test_each_section_is_fetched_under_the_name_it_was_given(self):
        client = _StubSections({"1": Tournament(id="1"), "2": Tournament(id="2")})
        congress = client.congress({"Open": 1, "Major": 2}, name="Somewhere")

        assert client.asked == ["1", "2"], "in the order the caller listed them"
        assert list(congress) == ["Open", "Major"]
        assert congress.name == "Somewhere"
        assert congress["Open"].id == "1"

    def test_an_unreadable_section_loses_the_whole_congress_by_default(self):
        """Consistent with `tournament`, which raises rather than returning empty."""
        client = _StubSections({"1": Tournament(id="1"), "2": RoundRobinError("all-play-all")})
        with pytest.raises(RoundRobinError):
            client.congress({"Open": 1, "Major": 2})

    def test_or_is_recorded_and_stepped_over_when_asked(self):
        """The shapes the library refuses are shapes a congress really has: a
        top section run as an all-play-all, or one that has not started yet."""
        client = _StubSections(
            {
                "1": Tournament(id="1"),
                "2": RoundRobinError("all-play-all"),
                "3": TournamentNotStartedError("not yet"),
            }
        )
        congress = client.congress({"Open": 1, "Major": 2, "Minor": 3}, skip_unreadable=True)

        assert list(congress) == ["Open"]
        assert sorted(congress.unreadable) == ["Major", "Minor"]
        assert isinstance(congress.unreadable["Major"], RoundRobinError)

    def test_progress_is_reported_before_each_section_rather_than_after(self):
        """A congress is minutes of requests; silence for all of it is the thing
        this avoids, so the call has to come before the fetch, not after."""
        seen = []

        class Announcing(_StubSections):
            def tournament(self, tournament_id, **kwargs):
                seen.append(("fetched", str(tournament_id)))
                return Tournament(id=str(tournament_id))

        Announcing({}).congress(
            {"Open": 1, "Major": 2},
            progress=lambda section, tournament_id: seen.append(("announced", section)),
        )
        assert seen == [
            ("announced", "Open"),
            ("fetched", "1"),
            ("announced", "Major"),
            ("fetched", "2"),
        ]

    def test_the_bye_value_reaches_every_section(self):
        """One set of conditions of entry governs a congress, so one value does."""
        seen = {}

        class Recording(_StubSections):
            def tournament(self, tournament_id, **kwargs):
                seen[str(tournament_id)] = kwargs["bye_value"]
                return Tournament(id=str(tournament_id))

        Recording({}).congress({"Open": 1, "Major": 2}, bye_value=0.5)
        assert seen == {"1": 0.5, "2": 0.5}


def test_the_two_frome_sections_really_are_different_tournaments():
    """Guarding the fixture: if both stems ever pointed at one page, every test
    above would still pass and none of them would mean anything."""
    opening = parse_pairings(fixture("frome2026_open_r1.html"), 1)
    standard = parse_pairings(fixture("frome2026_standard_r1.html"), 1)
    assert {p.white.name for p in opening}.isdisjoint({p.white.name for p in standard})
