"""Transport policy. Nothing here touches the network — it inspects the session
the client builds, and drives the adapter against a stubbed connection pool."""

import requests

from chess_results.client import RETRY_STATUSES, ChessResults, retrying_adapter


def _retry(session: requests.Session, scheme: str = "https://") -> object:
    return session.get_adapter(scheme + "chess-results.com").max_retries


class TestARetryPolicyIsMountedOnSessionsWeBuild:
    """One 503 out of a dozen requests would otherwise lose a whole scrape."""

    def test_both_schemes_carry_it(self):
        session = ChessResults().session
        for scheme in ("https://", "http://"):
            assert _retry(session, scheme).total == 3

    def test_it_retries_the_transient_statuses_and_nothing_else(self):
        retry = _retry(ChessResults().session)
        assert tuple(retry.status_forcelist) == RETRY_STATUSES
        # A 404 is chess-results answering, not failing: no tournament by that id.
        assert 404 not in retry.status_forcelist

    def test_only_idempotent_methods_are_replayed(self):
        assert set(_retry(ChessResults().session).allowed_methods) == {"GET", "HEAD"}

    def test_it_waits_longer_between_attempts(self):
        assert _retry(ChessResults().session).backoff_factor == 0.5

    def test_a_retry_after_header_is_honoured(self):
        assert _retry(ChessResults().session).respect_retry_after_header is True

    def test_retries_zero_turns_it_off(self):
        # requests' own default adapter, whose max_retries is a bare Retry(0).
        assert _retry(ChessResults(retries=0).session).total == 0

    def test_the_counts_are_configurable(self):
        retry = _retry(ChessResults(retries=7, backoff_factor=0.1).session)
        assert (retry.total, retry.backoff_factor) == (7, 0.1)


class TestASuppliedSessionIsLeftAlone:
    """Its transport policy belongs to whoever built it."""

    def test_no_adapter_is_mounted_over_the_caller_s_own(self):
        session = requests.Session()
        mine = requests.adapters.HTTPAdapter(max_retries=99)
        session.mount("https://", mine)
        assert ChessResults(session).session.get_adapter("https://chess-results.com") is mine

    def test_the_user_agent_is_still_set_politely(self):
        session = requests.Session()
        session.headers["User-Agent"] = "mine"
        assert ChessResults(session).session.headers["User-Agent"] == "mine"


def test_the_adapter_is_usable_on_its_own():
    """It is exported so a caller can mount it on a session of their own."""
    assert retrying_adapter(retries=1).max_retries.total == 1
