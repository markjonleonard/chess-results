"""HTTP client for chess-results.com.

chess-results serves tournaments from numbered mirrors and redirects the bare
domain to whichever one holds the tournament, so redirects must be followed.
Pages are always requested in English (``lan=1``) because the parsers key off
English column labels, and always with every row (``zeilen``) because the
default is a truncated page that says nothing about being truncated.
"""

from __future__ import annotations

import dataclasses
import datetime
import time
from collections.abc import Callable, Mapping
from typing import Any

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .cache import (
    LIVE_TTL,
    SETTLED_TTL,
    STARTING_RANK_TTL,
    CrosstableCoverage,
    SettledRounds,
    cached_session,
)
from .congress import Congress
from .models import (
    CrosstableEntry,
    Entrants,
    EventSections,
    NotPairedEntry,
    Pairing,
    PlayKind,
    SearchResult,
    SearchResults,
    StartingRankEntry,
)
from .parse import (
    has_pairings,
    is_combined_pairings,
    is_team_pairings,
    parse_crosstable,
    parse_not_paired,
    parse_pairings,
    parse_published_totals,
    parse_search_form,
    parse_search_results,
    parse_starting_rank,
    parse_tournament_details,
    parse_tournament_name,
)
from .sections import group_sections, is_sibling, sibling_query, sibling_window
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

#: The title chess-results gives the page for a number with no tournament behind
#: it. A real event carries its own name even before anyone has entered, so this
#: name with an empty field means there is nothing there, not an empty event.
NO_TOURNAMENT_TITLE = "Tournament-Database"

#: The tournament search form, and the page sizes it offers (its "Maximum number
#: of lines" select, in the order of its option values).
SEARCH_PAGE = "TurnierSuche.aspx"
SEARCH_PAGE_SIZES = (100, 250, 500, 1000, 1500, 2000)

#: Safety net for round auto-detection.
MAX_ROUNDS = 30


class TournamentError(ValueError):
    """This tournament cannot be assembled into a per-player history.

    Raised rather than returned empty, which is the whole point. Each case below
    produces a page this library reads *nothing* from, and an empty tournament
    is indistinguishable from a real one that has yet to be played: the caller
    gets a confident report of zero rounds and no warning that anything is
    wrong. Naming the reason is the difference between a tool that is honest
    about its limits and one that quietly answers the wrong question.
    """


class SearchError(RuntimeError):
    """The search answered with something that is not a list of tournaments.

    A fault in the service rather than an answer, so it is not a
    `TournamentError`: an error page sent with a success status, which
    chess-results does now and then and which went away on a second try.
    """


class TournamentNotFoundError(TournamentError):
    """chess-results has no tournament by that number.

    Raised before any round is fetched: the site answers such a number with a
    placeholder page, not an error, so it is recognised by that page.
    """


class TeamTournamentError(TournamentError):
    """The tournament pairs teams rather than players.

    A team event's round page carries teams and match points and names no player
    at all; the individual boards live on a second view this library does not
    read either.
    """


class RoundRobinError(TournamentError):
    """The tournament is a round robin, published in a shape this cannot read.

    Two views differ from the Swiss equivalents. The pairings page holds every
    round at once under repeated headings and ignores ``rd``, so each round
    would be read as whichever was asked for; and the crosstable is a grid of
    opponents rather than of rounds, which `parse_crosstable` reads nothing
    from while `parse_published_totals` still finds the totals beside it --
    leaving the usual cross-check with nothing to compare and nothing to say.
    """


class TournamentNotStartedError(TournamentError):
    """No round has been played, so there is no history to assemble.

    Not a limitation but a state, and a common one: chess-results publishes an
    entry list as soon as registration opens, often months ahead, and such a
    page carries a field and no games.
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


def _iso(day: datetime.date | str | None) -> str:
    return day.isoformat() if isinstance(day, datetime.date) else (day or "")


def _no_such_tournament(name: str | None, players: list[StartingRankEntry]) -> bool:
    return name == NO_TOURNAMENT_TITLE and not players


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
        self.coverage = CrosstableCoverage(cache_dir)
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
        refresh: bool = False,
        **params: str | int,
    ) -> str:
        """Fetch one view of a tournament and return its HTML.

        ``expire_after`` is how long the response may be reused, in seconds.
        ``refresh`` replaces any cached copy rather than reusing it, which is
        the only way to shorten a lifetime after the fact -- requests-cache
        fixes expiry when the response is written. Both are ignored by sessions
        that do not cache.
        """
        # expire_after is requests-cache's extension, absent from requests.Session.get,
        # so this cannot be typed more tightly than Any without lying about the session.
        options: dict[str, Any] = {}
        if self.caching and expire_after is not None:
            options["expire_after"] = expire_after
        if self.caching and refresh:
            options["force_refresh"] = True

        # Pace only requests that actually reach the server. A forced refresh
        # always reaches it, cached or not, so it must not take the shortcut.
        served_from_cache = False
        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0 and (refresh or not self._is_cached(tournament_id, art, params)):
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

    def _extend_cached_lifetime(
        self,
        tournament_id: str | int,
        art: int,
        params: dict[str, str | int],
        expire_after: int,
    ) -> bool:
        """Give an already-cached page a longer life, without refetching it.

        requests-cache fixes a response's expiry when it writes it, so a round
        cached while it was live keeps the short lifetime even after it settles
        and `round_ttl` starts asking for the long one. Left alone it expires on
        the old schedule and is fetched a second time to say nothing new.

        Rewriting the stored entry avoids that request entirely, which is the
        point: forcing a refresh would also fix the expiry but would spend the
        very request this is trying not to spend.

        Returns True when an entry was extended. False covers every ordinary
        reason there was nothing to do -- no cache, never fetched, already
        expired -- none of which is a fault: the page is simply fetched again
        as it would have been.
        """
        cache = getattr(self.session, "cache", None)
        if cache is None:
            return False
        try:
            request = requests.Request(
                "GET",
                f"{self.base_url}/tnr{tournament_id}.aspx",
                params=self._query(art, params),
            ).prepare()
            response = cache.get_response(cache.create_key(request=request))
            if response is None:
                return False
            response.reset_expiration(expire_after)
            cache.responses[response.cache_key] = response
            return True
        except Exception:  # cache surgery is an optimisation, never a blocker
            return False

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

    def _pace(self) -> None:
        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)

    def search(
        self,
        name: str | None = None,
        *,
        tournament_id: str | int | None = None,
        organizer: str | None = None,
        director: str | None = None,
        arbiter: str | None = None,
        location: str | None = None,
        ends_from: datetime.date | str | None = None,
        ends_to: datetime.date | str | None = None,
        finished_only: bool = False,
        limit: int = SEARCH_PAGE_SIZES[0],
    ) -> SearchResults:
        """Search chess-results' tournament database.

        Every text criterion is a case-insensitive substring match on the site's
        side, and they combine with AND. ``ends_from`` and ``ends_to`` bound the
        date a tournament *ended* (a ``date`` or ``"YYYY-MM-DD"``).

        At least one criterion is required: the alternative is the whole
        database, which is never what was meant. Rows come back most recently
        updated first, and ``limit`` caps them -- the result's ``total`` is how
        many matched, so a cut-off list says so rather than reading as a small
        answer. Names can be cut or have spaces
        dropped by the site; see :attr:`SearchResult.name_inexact`.

        Never cached. The search is a form post, which a cache does not store,
        and its entrant counts move while an event is live.
        """
        fields = {
            "ctl00$P1$txt_tnr": "" if tournament_id is None else str(tournament_id),
            "ctl00$P1$txt_bez": name or "",
            "ctl00$P1$txt_veranstalter": organizer or "",
            "ctl00$P1$txt_leiter": director or "",
            "ctl00$P1$txt_Hauptschiedsrichter": arbiter or "",
            "ctl00$P1$txt_ort": location or "",
            "ctl00$P1$txt_von_tag": _iso(ends_from),
            "ctl00$P1$txt_bis_tag": _iso(ends_to),
        }
        if not any(fields.values()) and not finished_only:
            raise ValueError("search needs at least one criterion")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        page_size = next((i for i, size in enumerate(SEARCH_PAGE_SIZES) if size >= limit), None)
        if page_size is None:
            page_size = len(SEARCH_PAGE_SIZES) - 1
        fields["ctl00$P1$combo_anzahl_zeilen"] = str(page_size)
        if finished_only:
            fields["ctl00$P1$cbox_zuEnde"] = "on"

        # The form has to be fetched first: ASP.NET refuses a postback that does
        # not carry the view state it issued. Not from the cache, for the same reason.
        options: dict[str, Any] = {"expire_after": 0} if self.caching else {}
        self._pace()
        form = self.session.get(
            f"{self.base_url}/{SEARCH_PAGE}",
            params={"lan": 1},
            timeout=self.timeout,
            allow_redirects=True,
            **options,
        )
        self._last_request = time.monotonic()
        form.raise_for_status()
        data = {
            **parse_search_form(form.text),
            # The selects the form posts back as they stand: everything, by last update.
            "ctl00$P1$combo_art": "5",
            "ctl00$P1$combo_sort": "1",
            "ctl00$P1$combo_land": "-",
            "ctl00$P1$combo_bedenkzeit": "0",
            "ctl00$P1$cb_suchen": "Search",
            **fields,
        }
        # A search changes nothing, so a page that is not a result page is worth
        # exactly one more try before it is reported.
        for attempt in (1, 2):
            self._pace()
            response = self.session.post(form.url, data=data, timeout=self.timeout)
            self._last_request = time.monotonic()
            response.raise_for_status()
            try:
                found = parse_search_results(response.text)
            except ValueError:
                if attempt == 2:
                    seen = " ".join(BeautifulSoup(response.text, "html.parser").get_text().split())[:100]
                    raise SearchError(f"chess-results returned no search results (got: {seen!r})") from None
                continue
            return SearchResults(results=found.results[:limit], total=found.total)
        raise AssertionError("unreachable")  # pragma: no cover

    def sections(self, tournament_id: str | int) -> EventSections:
        """Every section of the event ``tournament_id`` belongs to, with entrant counts.

        Two searches and no tournament pages: the first finds the tournament, the
        second finds what shares its organiser and dates -- see
        :mod:`chess_results.sections` for why that is an inference. The one
        exception is a name the search cut short, which is read in full off its
        own page so that its section label survives.
        """
        found = self.search(tournament_id=tournament_id, limit=1)
        if not found:
            raise TournamentNotFoundError(f"chess-results has no tournament {tournament_id}")
        target = found[0]
        candidates = [target]
        window = sibling_window(target)
        if window is not None:
            nearby = self.search(
                **sibling_query(target),
                ends_from=window[0],
                ends_to=window[1],
                limit=SEARCH_PAGE_SIZES[-1],
            )
            candidates += [c for c in nearby if is_sibling(target, c)]
        full = {c.id: self._full_name(c) for c in {c.id: c for c in candidates}.values()}
        return group_sections(
            dataclasses.replace(target, name=full[target.id]),
            (dataclasses.replace(c, name=full[c.id]) for c in candidates),
        )

    def _full_name(self, result: SearchResult) -> str:
        """The tournament's own name: the search's may have been cut or lost its spaces."""
        if not result.name_inexact:
            return result.name
        return self.entrants(result.id).name or result.name

    def starting_rank(self, tournament_id: str | int) -> list[StartingRankEntry]:
        return self.entrants(tournament_id).players

    def entrants(self, tournament_id: str | int) -> Entrants:
        """The field and tournament header, from the starting-rank page alone.

        One fetch serves all of it, rather than a separate request per piece
        of the same page.
        """
        html = self.fetch(tournament_id, ART_STARTING_RANK, expire_after=STARTING_RANK_TTL)
        name, players = parse_tournament_name(html), parse_starting_rank(html)
        if _no_such_tournament(name, players):
            raise TournamentNotFoundError(f"chess-results has no tournament {tournament_id}")
        details = parse_tournament_details(html)
        return Entrants(
            id=str(tournament_id),
            name=name,
            time_control=details.get("Time control"),
            dates=details.get("Date"),
            players=players,
        )

    def round_ttl(self, tournament_id: str | int, rnd: int) -> int:
        """How long this round's page may be reused."""
        return SETTLED_TTL if self.settled.is_settled(tournament_id, rnd) else self.live_ttl

    def crosstable_is_stale(self, tournament_id: str | int, event: Tournament) -> bool:
        """Whether a cached crosstable must be replaced rather than reused.

        The crosstable is cached hard, because the only thing we take from it --
        byes and absences deleted from superseded round pages -- never changes
        once written. Two things make a cached copy insufficient:

        - **It covers fewer rounds than we hold.** A crosstable fetched before
          round 8 existed cannot supply round 8's bye, and `add_crosstable`
          fills only rounds we already have. This is the case that matters.
        - **The newest round is still being played.** Nothing we *need* changes
          while results arrive, since the round page carries them, but
          `add_crosstable` also compares the two views and reports any
          contradiction. Against a stale copy that comparison would report
          results the crosstable simply had not caught yet, turning a tripwire
          into noise.

        So a settled tournament is fetched once and then never again, and a live
        one behaves as it always has.
        """
        return self.coverage.rounds(tournament_id) < event.last_round or bool(event.unfinished())

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
        name, players = parse_tournament_name(html), parse_starting_rank(html)
        if _no_such_tournament(name, players):
            # Before any round page: there are none to fetch, and probing thirty
            # of them would end in "not started", which is the wrong answer.
            raise TournamentNotFoundError(f"chess-results has no tournament {tournament_id}")
        event = Tournament(id=str(tournament_id), name=name, bye_value=bye_value)
        event.add_starting_rank(players)

        wanted = range(1, rounds + 1) if isinstance(rounds, int) else rounds
        previous: object = None
        truncated = False
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
            if is_combined_pairings(page):
                raise RoundRobinError(
                    f"tournament {tournament_id} publishes every round on one "
                    "page, as chess-results does for a round robin; this "
                    "library reads only the round-by-round format of a Swiss"
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
        else:
            # The loop ran out of ``wanted`` without chess-results itself ever
            # saying "no more rounds" -- i.e. ``rounds=`` (an int or a range,
            # either one a caller-chosen bound) cut this scrape off, not the
            # real tournament. event.unfinished() only sees what we fetched,
            # so on its own it would call a tournament "settled" that is
            # still live past the point we stopped looking.
            truncated = rounds is not None

        if event.rounds and (truncated or event.unfinished()):
            # Starting numbers are supposed to be fixed once an event begins,
            # but a live one can still have them corrected -- an arbiter
            # moving a misplaced entry, say, which renumbers everyone below
            # it. add_crosstable joins entirely by starting number, so a stale
            # cached copy of this page then attributes a shifted player's
            # crosstable row to whoever now holds their *old* number, and
            # ranking_order, the pairing sheet's board assignment and the TRF
            # export all inherit the wrong number too. Refetched whenever the
            # real tournament might still be live -- its own latest round is
            # unfinished, or ``rounds=`` means we cannot tell -- for the same
            # reason the crosstable is: nothing here can drift once an event
            # has settled, only while it has not.
            html = self.fetch(tournament_id, ART_STARTING_RANK, expire_after=STARTING_RANK_TTL, refresh=True)
            event.add_starting_rank(parse_starting_rank(html))

        if crosstable and event.rounds:
            # Fetched once and parsed twice: the round-by-round cells, and the
            # totals the page publishes, which are the check on our reading of them.
            html = self.fetch(
                tournament_id,
                ART_CROSSTABLE,
                # Cached hard and replaced on demand rather than expired on a
                # timer: what we take from this page is settled history, and a
                # short lifetime meant refetching it forever.
                expire_after=SETTLED_TTL,
                refresh=self.crosstable_is_stale(tournament_id, event),
            )
            parsed = parse_crosstable(html)
            event.add_crosstable(parsed)
            event.check_published_totals(parsed, parse_published_totals(html))
            self.coverage.record(tournament_id, event.last_round)

        if not event.rounds:
            # Every reason for this is the same to a reader: a field, and no
            # games. Saying so beats reporting a tournament of zero rounds.
            raise TournamentNotStartedError(
                f"tournament {tournament_id} has no played rounds; it has probably not started yet"
            )

        # A round that settled during this run was cached with the short
        # lifetime, and requests-cache cannot be told otherwise after the fact.
        # Extend the stored entries in place rather than spending a request each
        # to fetch pages that have not changed and never will again.
        now_settled = settled_rounds(event)
        for rnd in sorted(now_settled - self.settled.rounds(tournament_id)):
            self._extend_cached_lifetime(tournament_id, ART_ROUND_PAIRINGS, {"rd": rnd}, SETTLED_TTL)
        self.settled.record(tournament_id, now_settled)
        return event

    def congress(
        self,
        sections: Mapping[str, str | int],
        *,
        name: str | None = None,
        rounds: int | range | None = None,
        bye_value: float = 1.0,
        crosstable: bool = True,
        skip_unreadable: bool = False,
        progress: Callable[[str, str], None] | None = None,
    ) -> Congress:
        """Fetch several tournaments as one event.

        ``sections`` maps the name you call each section to its tournament
        number -- ``{"Open": 1393521, "Major": 1393522}``. The names are yours:
        chess-results publishes nothing that groups the sections of a congress,
        so nothing can be inferred here. Insertion order is kept, which is
        usually strongest first and is the order everything reports in.

        Every other argument is passed to :meth:`tournament` unchanged and
        applies to all sections. ``bye_value`` in particular is a property of
        the congress rather than of a section -- one set of conditions of entry
        governs the lot -- so a single value is the right shape. Check it
        against the crosstable's published totals before trusting it.

        ``skip_unreadable`` records a section that raises
        :class:`TournamentError` in :attr:`Congress.unreadable` and carries on,
        rather than losing the whole congress to one section. This is worth
        having because the shapes the library refuses are shapes a congress
        really contains: a top section run as an all-play-all raises
        :class:`RoundRobinError`, and a section that has not started yet raises
        :class:`TournamentNotStartedError` on the morning of the event. Off by
        default, so the quiet loss of a section has to be asked for.

        ``progress`` is called with ``(section, tournament_id)`` before each
        section is fetched. A congress is the one call in this library long
        enough to need it: five sections at roughly seven requests each, paced a
        second apart, is minutes of silence otherwise.
        """
        event = Congress(name=name)
        for section, tournament_id in sections.items():
            if progress is not None:
                progress(section, str(tournament_id))
            try:
                event.sections[section] = self.tournament(
                    tournament_id,
                    rounds=rounds,
                    bye_value=bye_value,
                    crosstable=crosstable,
                )
            except TournamentError as error:
                if not skip_unreadable:
                    raise
                event.unreadable[section] = error
        return event
