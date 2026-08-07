"""HTTP client for chess-results.com.

chess-results serves tournaments from numbered mirrors and redirects the bare
domain to whichever one holds the tournament, so redirects must be followed.
Pages are always requested in English (``lan=1``) because the parsers key off
English column labels.
"""

from __future__ import annotations

import time

import requests

from .cache import LIVE_TTL, SETTLED_TTL, STARTING_RANK_TTL, SettledRounds, cached_session
from .models import CrosstableEntry, Pairing, PlayKind, StartingRankEntry
from .parse import (
    has_pairings,
    parse_crosstable,
    parse_pairings,
    parse_starting_rank,
    parse_tournament_name,
)
from .tournament import Tournament

BASE_URL = "https://chess-results.com"
USER_AGENT = "chess-results (+https://github.com/markjonleonard/chess-results)"

#: chess-results "art" view identifiers.
ART_STARTING_RANK = 0
ART_ROUND_PAIRINGS = 2
#: Starting-rank crosstable: every player's every round, keyed by starting
#: number. The only view that keeps byes after the round has been superseded.
ART_CROSSTABLE = 5

#: Safety net for round auto-detection.
MAX_ROUNDS = 30


def settled_rounds(event: Tournament) -> set[int]:
    """Rounds that will not change again, so their pages can be cached hard.

    A round qualifies once every game in it has a result and a later round has
    been paired. The newest round is excluded even when it looks complete: a
    result can still be corrected before the next pairing is published.
    """
    last = event.last_round
    return {
        rnd
        for rnd, pairings in event.rounds.items()
        if rnd < last and not any(p.kind is PlayKind.GAME and p.white_score is None for p in pairings)
    }


class ChessResults:
    """Fetches and parses chess-results.com pages.

    Uncached by default, so a caller decides its own policy. Pass ``cache=True``
    (or a ``requests_cache.CachedSession`` as ``session``) to cache responses.
    With caching on, pages are given lifetimes according to how volatile they
    are: see :mod:`chess_results.cache`.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        base_url: str = BASE_URL,
        delay: float = 1.0,
        timeout: float = 30.0,
        cache: bool = False,
        cache_dir: str | None = None,
        live_ttl: int = LIVE_TTL,
    ) -> None:
        if session is None and cache:
            session = cached_session(cache_dir)
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.base_url = base_url.rstrip("/")
        self.delay = delay
        self.timeout = timeout
        self.live_ttl = live_ttl
        self.settled = SettledRounds(cache_dir)
        self._last_request = 0.0

    @property
    def caching(self) -> bool:
        """True when the session stores responses."""
        return hasattr(self.session, "cache")

    def fetch(
        self,
        tournament_id: str | int,
        art: int,
        *,
        expire_after: int | None = None,
        **params: object,
    ) -> str:
        """Fetch one view of a tournament and return its HTML.

        ``expire_after`` is how long the response may be reused, in seconds.
        It is ignored by sessions that do not cache.
        """
        options: dict[str, object] = {}
        if self.caching and expire_after is not None:
            options["expire_after"] = expire_after

        # Pace only requests that actually reach the server.
        served_from_cache = False
        if not (self.caching and options.get("expire_after") == 0):
            wait = self.delay - (time.monotonic() - self._last_request)
            if wait > 0 and not self._is_cached(tournament_id, art, params):
                time.sleep(wait)

        query = {"lan": 1, "art": art, **params}
        response = self.session.get(
            f"{self.base_url}/tnr{tournament_id}.aspx",
            params=query,
            timeout=self.timeout,
            allow_redirects=True,
            **options,
        )
        served_from_cache = getattr(response, "from_cache", False)
        if not served_from_cache:
            self._last_request = time.monotonic()
        response.raise_for_status()
        return response.text

    def _is_cached(self, tournament_id: str | int, art: int, params: dict) -> bool:
        if not self.caching:
            return False
        try:
            request = requests.Request(
                "GET",
                f"{self.base_url}/tnr{tournament_id}.aspx",
                params={"lan": 1, "art": art, **params},
            ).prepare()
            return self.session.cache.contains(request=request)
        except Exception:  # cache introspection is a nicety, never a blocker
            return False

    def starting_rank(self, tournament_id: str | int) -> list[StartingRankEntry]:
        return parse_starting_rank(
            self.fetch(tournament_id, ART_STARTING_RANK, expire_after=STARTING_RANK_TTL)
        )

    def round_ttl(self, tournament_id: str | int, rnd: int) -> int:
        """How long this round's page may be reused."""
        return SETTLED_TTL if self.settled.is_settled(tournament_id, rnd) else self.live_ttl

    def pairings(self, tournament_id: str | int, rnd: int, *, bye_value: float = 1.0) -> list[Pairing]:
        html = self.fetch(
            tournament_id,
            ART_ROUND_PAIRINGS,
            rd=rnd,
            expire_after=self.round_ttl(tournament_id, rnd),
        )
        return parse_pairings(html, rnd, bye_value=bye_value)

    def crosstable(self, tournament_id: str | int) -> dict[int, list[CrosstableEntry]]:
        """The starting-rank crosstable, keyed by starting number."""
        return parse_crosstable(self.fetch(tournament_id, ART_CROSSTABLE, expire_after=self.live_ttl))

    def tournament(
        self,
        tournament_id: str | int,
        *,
        rounds: int | range | None = None,
        bye_value: float = 1.0,
        crosstable: bool = True,
    ) -> Tournament:
        """Fetch a whole tournament.

        ``rounds`` may be a count, a range, or None to fetch until the rounds run
        out. Rounds that have been paired but not yet played are included, with
        results left as None.

        ``crosstable`` adds one request for the crosstable, which is the only
        view that still records a bye once its round has been superseded. Leave
        it on unless you are certain the tournament has none, or scores will be
        wrong for anyone who took one.
        """
        html = self.fetch(tournament_id, ART_STARTING_RANK, expire_after=STARTING_RANK_TTL)
        event = Tournament(id=str(tournament_id), name=parse_tournament_name(html))
        event.add_starting_rank(parse_starting_rank(html))

        wanted = range(1, rounds + 1) if isinstance(rounds, int) else rounds
        previous: object = None
        for rnd in wanted or range(1, MAX_ROUNDS + 1):
            page = self.fetch(
                tournament_id,
                ART_ROUND_PAIRINGS,
                rd=rnd,
                expire_after=self.round_ttl(tournament_id, rnd),
            )
            if not has_pairings(page):
                break
            pairings = parse_pairings(page, rnd, bye_value=bye_value)
            # A round that has not been paired yet still renders a table, holding
            # only the withdrawn players' "not paired" rows. No games means the
            # tournament has not reached this round.
            if not any(p.kind is PlayKind.GAME for p in pairings):
                break
            # Out-of-range rounds can echo an earlier round's table.
            signature = [(p.board, p.white.name, p.black.name if p.black else None) for p in pairings]
            if signature == previous:
                break
            previous = signature
            event.add_round(pairings)

        if crosstable and event.rounds:
            event.add_crosstable(self.crosstable(tournament_id))

        self.settled.record(tournament_id, settled_rounds(event))
        return event
