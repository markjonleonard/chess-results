"""Caching policy.

The point of the policy is that a finished round is never refetched. These
tests drive the client with a fake session so nothing reaches the network, and
assert on the lifetimes it asks for.
"""

import pytest
from tests.conftest import _round_fixture, fixture

from chess_results.cache import LIVE_TTL, SETTLED_TTL, STARTING_RANK_TTL, SettledRounds
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
        self.calls.append({"params": params, "expire_after": kwargs.get("expire_after")})
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
