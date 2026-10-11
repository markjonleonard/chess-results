"""The tournament-details table: organiser, arbiters, time control and dates.

The starting-rank page prints it when asked with ``turdet``, and an event more
than five days over prints a "Show tournament details" button in its place, which
has to be posted back. Frome 2026's Major (tnr1393522, ended 2026-05-17) is that
case, captured on 2026-10-11 before and after the postback; Rosario's Torneo
Mayor (tnr1502126) is a live event with an arbiter list long enough to be cut.
"""

from tests.conftest import fixture

from chess_results.client import ALL_DETAILS, ART_STARTING_RANK, ChessResults
from chess_results.parse import has_details_button, parse_starting_rank, parse_tournament_details

GATED = "frome2026_major_startingrank_gated.html"
POSTED = "frome2026_major_startingrank_details.html"
LIVE = "rosario2026_mayor_startingrank_details.html"
LIVE_CUT = "rosario2026_mayor_startingrank_details_cut.html"

#: The mirror the bare domain redirected to, which the postback must go back to.
MIRROR = "https://s2.chess-results.com/tnr1393522.aspx?lan=1&art=0&zeilen=99999&turdet=ALL&SNode=S0"


class TestTheDetailsTable:
    def test_an_old_event_hides_it_behind_a_button(self):
        page = fixture(GATED)
        assert has_details_button(page)
        assert parse_tournament_details(page) == {}

    def test_the_postback_prints_it(self):
        page = fixture(POSTED)
        assert not has_details_button(page)
        details = parse_tournament_details(page)
        assert details["Chief Arbiter"] == "Constable, John 415855"
        assert details["Deputy Chief Arbiter"] == "FA Walker, Derrick 343417094"
        assert details["Arbiter"] == "Leonard, Mark 343404405"

    def test_both_pages_carry_the_whole_field(self):
        assert parse_starting_rank(fixture(GATED)) == parse_starting_rank(fixture(POSTED))
        assert len(parse_starting_rank(fixture(POSTED))) == 50

    def test_a_live_event_prints_it_unasked_for_a_postback(self):
        page = fixture(LIVE)
        assert not has_details_button(page)
        assert parse_tournament_details(page)["Chief Arbiter"] == "AN Jeremias Marcopulo (ID FIDE 173908)"

    def test_turdet_all_lists_every_arbiter_where_yes_cuts_them_short(self):
        cut = parse_tournament_details(fixture(LIVE_CUT))["Arbiter"]
        whole = parse_tournament_details(fixture(LIVE))["Arbiter"]
        assert cut.endswith("All arbiters")
        assert whole == "AR Gimenez Benjamin (ID FIDE 168530) - Valentina Espinosa (ID FIDE 20000650)"


class _Page:
    def __init__(self, text, url):
        self.text, self.url = text, url

    def raise_for_status(self):
        pass


class _Session:
    """Serves the starting-rank page on every GET and ``posted`` on a POST."""

    def __init__(self, page, posted=None):
        self.page, self.posted = page, posted
        self.gets = []
        self.posts = []

    @property
    def headers(self):
        return {}

    def get(self, url, params=None, **kwargs):
        self.gets.append(params)
        return _Page(fixture(self.page), MIRROR)

    def post(self, url, data=None, **kwargs):
        self.posts.append((url, data))
        return _Page(fixture(self.posted), url)


class TestEntrants:
    def test_a_live_event_costs_one_request(self):
        session = _Session(LIVE)
        entrants = ChessResults(session, delay=0).entrants(1502126)
        assert len(session.gets) == 1 and session.posts == []
        assert session.gets[0]["art"] == ART_STARTING_RANK
        assert session.gets[0]["turdet"] == ALL_DETAILS
        assert entrants.chief_arbiter == "AN Jeremias Marcopulo (ID FIDE 173908)"
        assert entrants.deputy_chief_arbiter.startswith("AN Gimenez Julieta (ID FIDE 168548) - AR Sofia")
        assert entrants.organizer == "ARA / Club Cuatro Caballos"
        assert entrants.director == "David Simbler"

    def test_a_time_control_labelled_with_its_rate_is_still_read(self):
        """Rosario labels it "Time control (Standard)"; Warsaw plain "Time control"."""
        entrants = ChessResults(_Session(LIVE), delay=0).entrants(1502126)
        assert entrants.time_control == "90 minutos más 30 segundos de incremento"
        assert entrants.dates == "2026/10/02 to 2026/10/12"

    def test_an_old_event_presses_the_button(self):
        session = _Session(GATED, posted=POSTED)
        entrants = ChessResults(session, delay=0).entrants(1393522)
        assert entrants.director == "Chris Lamming and Sally Hunt"
        assert entrants.chief_arbiter == "Constable, John 415855"
        assert entrants.deputy_chief_arbiter == "FA Walker, Derrick 343417094"
        assert entrants.arbiters == "Leonard, Mark 343404405"
        assert entrants.organizer is None  # Frome does not fill it in
        assert entrants.time_control == "90 minutes + 30s from move 1"
        assert len(entrants.players) == 50

    def test_the_postback_goes_to_the_mirror_with_the_view_state(self):
        """Posted to the bare domain it is redirected, and the redirect makes it a GET."""
        session = _Session(GATED, posted=POSTED)
        ChessResults(session, delay=0).entrants(1393522)
        assert len(session.gets) == 2  # the page, then a fresh copy for its view state
        [(url, data)] = session.posts
        assert url == MIRROR
        assert data["__VIEWSTATE"]
        assert data["cb_alleDetails"] == "Show tournament details"

    def test_a_caller_wanting_only_the_field_skips_the_postback(self):
        session = _Session(GATED)
        entrants = ChessResults(session, delay=0).entrants(1393522, details=False)
        assert len(session.gets) == 1 and session.posts == []
        assert len(entrants.players) == 50
        assert entrants.chief_arbiter is None

    def test_a_postback_that_shows_nothing_leaves_the_details_empty(self):
        """What the organiser never filled in is a normal answer, not an error."""
        session = _Session(GATED, posted=GATED)
        entrants = ChessResults(session, delay=0).entrants(1393522)
        assert len(session.posts) == 1
        assert (entrants.chief_arbiter, entrants.time_control) == (None, None)
        assert len(entrants.players) == 50

    def test_starting_rank_skips_it_too(self):
        session = _Session(GATED)
        assert len(ChessResults(session, delay=0).starting_rank(1393522)) == 50
        assert session.posts == []


class _CachingSession(_Session):
    """Enough of a ``CachedSession`` for the client to treat itself as caching."""

    cache = None


def _press_once(tmp_path):
    """A caching run that presses Frome Major's button and records what it found."""
    session = _CachingSession(GATED, posted=POSTED)
    ChessResults(session, delay=0, cache_dir=str(tmp_path)).entrants(1393522)


class TestAPressIsRemembered:
    """The button only appears once an event is over, so what it reveals is final."""

    def test_the_second_run_presses_nothing(self, tmp_path):
        first = _CachingSession(GATED, posted=POSTED)
        ChessResults(first, delay=0, cache_dir=str(tmp_path)).entrants(1393522)
        assert len(first.posts) == 1

        second = _CachingSession(GATED, posted=POSTED)
        entrants = ChessResults(second, delay=0, cache_dir=str(tmp_path)).entrants(1393522)
        assert second.posts == [] and len(second.gets) == 1
        assert entrants.chief_arbiter == "Constable, John 415855"
        assert entrants.time_control == "90 minutes + 30s from move 1"

    def test_an_event_with_nothing_filled_in_is_remembered_as_such(self, tmp_path):
        page = fixture(POSTED)
        empty = page.replace('class="CR"', 'class="CRx"')  # no details table left to read
        first = _CachingSession(GATED, posted=POSTED)
        first.post = lambda url, data=None, **kwargs: _Page(empty, url)
        assert ChessResults(first, delay=0, cache_dir=str(tmp_path)).entrants(1393522).chief_arbiter is None

        second = _CachingSession(GATED, posted=POSTED)
        assert ChessResults(second, delay=0, cache_dir=str(tmp_path)).entrants(1393522).chief_arbiter is None
        assert second.posts == []

    def test_a_press_that_did_not_take_is_not_remembered(self, tmp_path):
        """Its answer still shows the button; an empty record would hide the details for good."""
        ChessResults(_CachingSession(GATED, posted=GATED), delay=0, cache_dir=str(tmp_path)).entrants(1393522)
        retry = _CachingSession(GATED, posted=POSTED)
        entrants = ChessResults(retry, delay=0, cache_dir=str(tmp_path)).entrants(1393522)
        assert len(retry.posts) == 1
        assert entrants.chief_arbiter == "Constable, John 415855"

    def test_an_uncached_client_does_not_read_the_record(self, tmp_path):
        _press_once(tmp_path)
        uncached = _Session(GATED, posted=POSTED)
        ChessResults(uncached, delay=0, cache_dir=str(tmp_path)).entrants(1393522)
        assert len(uncached.posts) == 1

    def test_details_false_never_consults_it(self, tmp_path):
        _press_once(tmp_path)
        entrants = ChessResults(_CachingSession(GATED), delay=0, cache_dir=str(tmp_path)).entrants(
            1393522, details=False
        )
        assert entrants.chief_arbiter is None
