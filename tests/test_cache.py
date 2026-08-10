"""Caching policy.

The point of the policy is that a finished round is never refetched. These
tests drive the client with a fake session so nothing reaches the network, and
assert on the lifetimes it asks for.
"""

import pytest
from tests.conftest import _round_fixture, fixture

from chess_results.cache import LIVE_TTL, SETTLED_TTL, STARTING_RANK_TTL, CrosstableCoverage, SettledRounds
from chess_results.client import ChessResults, settled_rounds
from chess_results.parse import parse_pairings
from chess_results.tournament import Tournament


class FakeResponse:
    from_cache = False
    status_code = 200

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeCache:
    def contains(self, request=None, **kwargs):
        return False


class FakeSession:
    """Stands in for a requests_cache.CachedSession."""

    cache = FakeCache()

    def __init__(self, pages):
        self.pages = pages
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, **kwargs):
        self.calls.append(
            {
                "params": params,
                "expire_after": kwargs.get("expire_after"),
                "force_refresh": kwargs.get("force_refresh", False),
            }
        )
        art, rnd = params["art"], params.get("rd")
        return FakeResponse(self.pages(art, rnd))


def pages(art, rnd):
    if art == 0:
        return fixture("british2026_champ_startingrank.html")
    if art == 5:
        return fixture("british2026_champ_crosstable.html")
    if rnd and rnd <= 7:
        # The mid-round captures for 6 and 7: this fake serves a live tournament.
        return fixture(f"{_round_fixture(rnd, played_out=False)}.html")
    return fixture("british2026_champ_r8_unpaired_only.html")


@pytest.fixture
def cache_dir(tmp_path):
    return str(tmp_path)


class TestLifetimes:
    def test_starting_rank_is_cached_for_a_day(self, cache_dir):
        session = FakeSession(pages)
        ChessResults(session, delay=0, cache_dir=cache_dir).tournament(1452107)
        assert session.calls[0]["expire_after"] == STARTING_RANK_TTL

    def test_a_round_is_live_until_it_is_known_to_have_settled(self, cache_dir):
        session = FakeSession(pages)
        ChessResults(session, delay=0, cache_dir=cache_dir).tournament(1452107)
        rounds = [c for c in session.calls if c["params"].get("rd")]
        assert {c["expire_after"] for c in rounds} == {LIVE_TTL}

    def test_settled_rounds_are_cached_hard_on_the_next_run(self, cache_dir):
        first = FakeSession(pages)
        ChessResults(first, delay=0, cache_dir=cache_dir).tournament(1452107)

        second = FakeSession(pages)
        ChessResults(second, delay=0, cache_dir=cache_dir).tournament(1452107)
        by_round = {c["params"]["rd"]: c["expire_after"] for c in second.calls if c["params"].get("rd")}
        # Rounds 1-5 finished and were superseded; round 6 had games in progress
        # when these pages were captured, and round 7 is the newest.
        assert [by_round[r] for r in (1, 2, 3, 4, 5)] == [SETTLED_TTL] * 5
        assert by_round[6] == LIVE_TTL
        assert by_round[7] == LIVE_TTL

    def test_no_cache_means_no_lifetime_is_requested(self, cache_dir):
        class PlainSession(FakeSession):
            """A session with no .cache attribute, like requests.Session."""

            cache = None
            __slots__ = ()

            def __getattribute__(self, name):
                if name == "cache":
                    raise AttributeError(name)
                return super().__getattribute__(name)

        session = PlainSession(pages)
        client = ChessResults(session, delay=0, cache_dir=cache_dir)
        assert client.caching is False
        client.tournament(1452107)
        assert {c["expire_after"] for c in session.calls} == {None}


class TestSettledRounds:
    def test_a_finished_superseded_round_has_settled(self):
        event = Tournament(id="x")
        for rnd in (1, 2):
            event.add_round(parse_pairings(fixture(f"british2026_champ_r{rnd}.html"), rnd))
        assert settled_rounds(event) == {1}

    def test_the_newest_round_never_counts_as_settled(self):
        event = Tournament(id="x")
        event.add_round(parse_pairings(fixture("british2026_champ_r1.html"), 1))
        assert settled_rounds(event) == set()

    def test_a_round_with_games_in_progress_has_not_settled(self):
        event = Tournament(id="x")
        for rnd in (6, 7):
            event.add_round(parse_pairings(fixture(f"{_round_fixture(rnd, played_out=False)}.html"), rnd))
        assert 6 not in settled_rounds(event), "round 6 had six games unfinished"

    def test_records_survive_between_instances(self, tmp_path):
        SettledRounds(tmp_path).record(1452107, {1, 2, 3})
        assert SettledRounds(tmp_path).rounds(1452107) == {1, 2, 3}
        assert SettledRounds(tmp_path).is_settled(1452107, 2)

    def test_records_accumulate_rather_than_replace(self, tmp_path):
        SettledRounds(tmp_path).record(1452107, {1, 2})
        SettledRounds(tmp_path).record(1452107, {3})
        assert SettledRounds(tmp_path).rounds(1452107) == {1, 2, 3}

    def test_missing_file_is_not_an_error(self, tmp_path):
        assert SettledRounds(tmp_path / "nope").rounds(1452107) == set()


def played_out_pages(art, rnd):
    """A finished tournament: rounds 1-8 all decided, nothing in progress."""
    if art == 0:
        return fixture("british2026_champ_startingrank.html")
    if art == 5:
        return fixture("british2026_champ_crosstable_final.html")
    if rnd and rnd <= 8:
        return fixture(f"{_round_fixture(rnd, played_out=True)}.html")
    return fixture("british2026_champ_r8_unpaired_only.html")


class TestTheCrosstableIsNotTreatedAsLive:
    """Most of the crosstable is settled history, and that is all we read.

    It used to be fetched on the live lifetime -- five minutes, flat, forever,
    including for an event that finished last year. But its volatile part is
    the current round's results, which we never take from it; the round page is
    the authority there. What we do take is the byes and absences that round
    pages delete once a later round is paired, and those never change again.

    So it is cached hard and *replaced* when it stops covering what we hold,
    which is the only way round requests-cache fixing expiry at write time.
    """

    @staticmethod
    def _crosstable(session):
        return [c for c in session.calls if c["params"]["art"] == 5]

    def test_it_is_cached_hard_rather_than_briefly(self, cache_dir):
        session = FakeSession(played_out_pages)
        ChessResults(session, delay=0, cache_dir=cache_dir).tournament(1452107)
        assert self._crosstable(session)[0]["expire_after"] == SETTLED_TTL

    def test_a_settled_tournament_is_not_refetched_on_the_next_run(self, cache_dir):
        """The win: run it twice against a finished event and the second run
        reuses the cached copy instead of asking again."""
        first = FakeSession(played_out_pages)
        ChessResults(first, delay=0, cache_dir=cache_dir).tournament(1452107)
        assert self._crosstable(first)[0]["force_refresh"] is True  # nothing cached yet

        second = FakeSession(played_out_pages)
        ChessResults(second, delay=0, cache_dir=cache_dir).tournament(1452107)
        assert self._crosstable(second)[0]["force_refresh"] is False

    def test_a_live_round_still_forces_a_fresh_copy(self, cache_dir):
        """While results are arriving, add_crosstable's comparison would
        otherwise report them as contradictions rather than as a stale page."""
        first = FakeSession(pages)
        ChessResults(first, delay=0, cache_dir=cache_dir).tournament(1452107)
        second = FakeSession(pages)
        ChessResults(second, delay=0, cache_dir=cache_dir).tournament(1452107)
        assert self._crosstable(second)[0]["force_refresh"] is True

    def test_a_new_round_forces_a_fresh_copy(self, cache_dir):
        """The case that matters. A crosstable fetched when the event had 8
        rounds cannot supply round 9's bye, and add_crosstable fills only rounds
        we already hold -- so a stale copy would lose a bye silently."""
        first = FakeSession(played_out_pages)
        client = ChessResults(first, delay=0, cache_dir=cache_dir)
        client.tournament(1452107)
        assert client.coverage.rounds(1452107) == 8

        # The same event a round later.
        def with_round_nine(art, rnd):
            if art == 2 and rnd == 9:
                return fixture("british2026_champ_r9.html")
            return played_out_pages(art, rnd)

        second = FakeSession(with_round_nine)
        later = ChessResults(second, delay=0, cache_dir=cache_dir)
        later.tournament(1452107)
        assert self._crosstable(second)[0]["force_refresh"] is True
        assert later.coverage.rounds(1452107) == 9


class TestCrosstableCoverageRecord:
    def test_it_starts_empty(self, cache_dir):
        assert CrosstableCoverage(cache_dir).rounds(1452107) == 0

    def test_it_survives_between_runs(self, cache_dir):
        CrosstableCoverage(cache_dir).record(1452107, 8)
        assert CrosstableCoverage(cache_dir).rounds(1452107) == 8

    def test_a_corrupt_file_is_treated_as_empty(self, cache_dir, tmp_path):
        (tmp_path / "crosstable.json").write_text("{not json")
        assert CrosstableCoverage(cache_dir).rounds(1452107) == 0

    def test_an_unreadable_value_is_treated_as_never_fetched(self, cache_dir, tmp_path):
        """Rather than trusting whatever the file happens to hold."""
        (tmp_path / "crosstable.json").write_text('{"1452107": "eight"}')
        assert CrosstableCoverage(cache_dir).rounds(1452107) == 0
