"""HTTP client for chess-results.com.

chess-results serves tournaments from numbered mirrors and redirects the bare
domain to whichever one holds the tournament, so redirects must be followed.
Pages are always requested in English (``lan=1``) because the parsers key off
English column labels, and always with every row (``zeilen``) because the
default is a truncated page that says nothing about being truncated.
"""

from __future__ import annotations

import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .cache import LIVE_TTL, SETTLED_TTL, STARTING_RANK_TTL, SettledRounds, cached_session
from .models import CrosstableEntry, NotPairedEntry, Pairing, PlayKind, StartingRankEntry
from .parse import (
    has_pairings,
    is_team_pairings,
    parse_crosstable,
    parse_not_paired,
    parse_pairings,
    parse_published_totals,
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
#: "not paired": one row per player who has missed a round. Linked in the nav
#: bar, undocumented, and it ignores ``rd`` -- there is only ever the current one.
ART_NOT_PAIRED = 40

#: Rows to ask a list view for. chess-results paginates at 150 and offers
#: ``zeilen=99999`` as its own "show all" link, so this is the site's number
#: rather than one we chose; no chess tournament comes near it.
ALL_ROWS = 99999

#: Safety net for round auto-detection.
MAX_ROUNDS = 30


class TeamTournamentError(ValueError):
    """The tournament pairs teams, which this library does not read.

    Raised rather than returned empty. A team event's round page names no
    players, so the scrape would otherwise succeed into a tournament with no
    rounds and no field -- indistinguishable, to anyone reading the output,
    from an event that has not started yet.
    """


#: Transient conditions worth retrying: rate limiting, and the 5xx family a busy
#: chess-results returns under load. 404 and the rest of 4xx are answers, not faults.
RETRY_STATUSES = (429, 500, 502, 503, 504)
#: Attempts after the first, and the urllib3 backoff factor between them. Three
#: retries at 0.5 waits about 0.5s, 1s then 2s -- long enough to outlast a blip,
#: short enough that a genuinely dead server fails the scrape promptly.
RETRIES = 3
BACKOFF_FACTOR = 0.5


def retrying_adapter(retries: int = RETRIES, backoff_factor: float = BACKOFF_FACTOR) -> HTTPAdapter:
    """An ``HTTPAdapter`` that retries idempotent requests on transient failures.

    A scrape is one request per round plus the crosstable and the starting rank,
    so a single 503 on a twelve-round event would otherwise lose the whole run.
    ``Retry`` honours a ``Retry-After`` header when the server sends one.
    """
    return HTTPAdapter(
        max_retries=Retry(
            total=retries,
            status_forcelist=RETRY_STATUSES,
            allowed_methods=frozenset(["GET", "HEAD"]),
            backoff_factor=backoff_factor,
            respect_retry_after_header=True,
        )
    )


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

    Sessions built here retry transient failures; ``retries=0`` turns that off.
    A session passed in as ``session`` is left alone — its transport policy
    belongs to whoever made it.
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
        retries: int = RETRIES,
        backoff_factor: float = BACKOFF_FACTOR,
    ) -> None:
        supplied = session is not None
        if session is None and cache:
            session = cached_session(cache_dir)
        self.session = session or requests.Session()
        if not supplied and retries:
            adapter = retrying_adapter(retries, backoff_factor)
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)
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

    def _query(self, art: int, params: dict[str, str | int]) -> dict[str, str | int]:
        """The query string for one view, English and unpaginated.

        Both must be on every request, and ``zeilen`` is the one that bites:
        chess-results shows a long list 150 rows at a time and the truncated
        page announces itself nowhere a parser can see. A 209-player open read
        as 150 players produces no error at all — just an event missing a
        third of its field, and every score and prediction drawn from it.
        """
        return {"lan": 1, "art": art, "zeilen": ALL_ROWS, **params}

    def fetch(
        self,
        tournament_id: str | int,
        art: int,
        *,
        expire_after: int | None = None,
        **params: str | int,
    ) -> str:
        """Fetch one view of a tournament and return its HTML.

        ``expire_after`` is how long the response may be reused, in seconds.
        It is ignored by sessions that do not cache.
        """
        # expire_after is requests-cache's extension, absent from requests.Session.get,
        # so this cannot be typed more tightly than Any without lying about the session.
        options: dict[str, Any] = {}
        if self.caching and expire_after is not None:
            options["expire_after"] = expire_after

        # Pace only requests that actually reach the server.
        served_from_cache = False
        if not (self.caching and options.get("expire_after") == 0):
            wait = self.delay - (time.monotonic() - self._last_request)
            if wait > 0 and not self._is_cached(tournament_id, art, params):
                time.sleep(wait)

        response = self.session.get(
            f"{self.base_url}/tnr{tournament_id}.aspx",
            params=self._query(art, params),
            timeout=self.timeout,
            allow_redirects=True,
            **options,
        )
        served_from_cache = getattr(response, "from_cache", False)
        if not served_from_cache:
            self._last_request = time.monotonic()
        response.raise_for_status()
        return response.text

    def _is_cached(self, tournament_id: str | int, art: int, params: dict[str, str | int]) -> bool:
        # The backing store lives on CachedSession, not on requests.Session.
        cache = getattr(self.session, "cache", None)
        if cache is None:
            return False
        try:
            request = requests.Request(
                "GET",
                f"{self.base_url}/tnr{tournament_id}.aspx",
                params=self._query(art, params),
            ).prepare()
            return bool(cache.contains(request=request))
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

    def not_paired(self, tournament_id: str | int) -> list[NotPairedEntry]:
        """Everyone who has missed a round, from the "not paired" page.

        One request against one page, where the same facts otherwise mean mining
        the whole crosstable. It cannot tell a requested bye from an absence,
        though, so the crosstable stays the authority on what a missed round was
        worth: see :func:`chess_results.parse.parse_not_paired`.

        Given the live lifetime because a marker appears as soon as its round is
        paired.
        """
        return parse_not_paired(self.fetch(tournament_id, ART_NOT_PAIRED, expire_after=self.live_ttl))

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
        event = Tournament(id=str(tournament_id), name=parse_tournament_name(html), bye_value=bye_value)
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
            if is_team_pairings(page):
                raise TeamTournamentError(
                    f"tournament {tournament_id} pairs teams, not players; "
                    "chess-results reports team events in a different format "
                    "that this library does not read"
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
            # Fetched once and parsed twice: the round-by-round cells, and the
            # totals the page publishes, which are the check on our reading of them.
            html = self.fetch(tournament_id, ART_CROSSTABLE, expire_after=self.live_ttl)
            parsed = parse_crosstable(html)
            event.add_crosstable(parsed)
            event.check_published_totals(parsed, parse_published_totals(html))

        self.settled.record(tournament_id, settled_rounds(event))
        return event
