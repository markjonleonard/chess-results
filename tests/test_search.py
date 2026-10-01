"""The tournament search and the sections inferred from it. Offline: the search
pages are saved fixtures and the session is a stub that replays them."""

import datetime

import pytest

from chess_results import ChessResults, TournamentNotFoundError
from chess_results.models import Entrants, SearchResult, SearchResults
from chess_results.parse import parse_search_form, parse_search_results
from chess_results.sections import (
    event_name,
    group_sections,
    is_sibling,
    section_labels,
    sibling_query,
)
from conftest import fixture


def _result(tid="1", name="Congress Open", **kwargs):
    fields = {
        "organizer": "Org",
        "director": "Dir",
        "start_date": datetime.date(2024, 11, 23),
        "end_date": datetime.date(2024, 11, 24),
        "players": 10,
        **kwargs,
    }
    return SearchResult(id=tid, name=name, **fields)


class TestParseSearchResults:
    def test_reads_every_row_once(self):
        # The results table sits inside layout tables whose rows would repeat it.
        found = parse_search_results(fixture("search_derbyshire_congress.html"))
        assert (len(found), found.total, found.truncated) == (15, 15, False)

    def test_a_row_is_read_by_header(self):
        found = parse_search_results(fixture("search_by_tnr_derbyshire2024_open.html"))
        assert found[0] == SearchResult(
            id="1063614",
            name="Derbyshire Congress Open",
            federation="ENG",
            start_date=datetime.date(2024, 11, 23),
            end_date=datetime.date(2024, 11, 24),
            director="David Woodhouse",
            organizer="David Woodhouse",
            chief_arbiter="John Shaw",
            location=None,
            time_control="90 minutes + 10 second increment from move 1",
            rounds=5,
            players=31,
        )

    def test_nothing_found_is_an_empty_answer(self):
        found = parse_search_results(fixture("search_no_results.html"))
        assert (len(found), found.total) == (0, 0)

    def test_a_page_it_does_not_understand_is_an_error_not_an_empty_answer(self):
        with pytest.raises(ValueError, match="not a chess-results search page"):
            parse_search_results("<html><body>Service unavailable</body></html>")

    def test_the_form_page_is_not_a_result_page(self):
        with pytest.raises(ValueError):
            parse_search_results(fixture("search_form.html"))

    def test_a_name_the_site_cut_is_flagged(self):
        """The search cuts names at 50 characters, and loses the section label with them."""
        found = parse_search_results(fixture("search_milton_keynes2026.html"))
        assert all(r.name_inexact for r in found)
        assert found[1].name == "Milton Keynes FIDE Chess Congress 28th-29th Mar 20"

    def test_a_short_name_is_not(self):
        found = parse_search_results(fixture("search_derbyshire_congress.html"))
        assert not any(r.name_inexact for r in found)

    def test_a_name_whose_space_the_site_dropped_is_flagged(self):
        """Hull 4NCL's search rows read "2024Under 1500" where the tournament says "2024 Under 1500"."""
        html = fixture("search_derbyshire_congress.html").replace(
            "3rd Derbyshire Congress MAJOR", "3rd Derbyshire Congress 2025Major"
        )
        found = parse_search_results(html)
        assert [r.name for r in found if r.name_inexact] == ["3rd Derbyshire Congress 2025Major"]

    @pytest.mark.parametrize("name", ["Hull Rapid 2024 - U1900", "Hull 4NCL Congress 2024 Open"])
    def test_ordinary_names_are_not(self, name):
        from chess_results.parse import _name_is_inexact

        assert not _name_is_inexact(name)


def test_the_form_is_posted_back_with_its_view_state():
    fields = parse_search_form(fixture("search_form.html"))
    assert set(fields) == {"__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"}


class TestSectionLabels:
    def test_the_words_not_common_to_every_name(self):
        names = [f"Derbyshire Congress {s}" for s in ("Open", "Major", "Minor")]
        assert section_labels(names) == ["Open", "Major", "Minor"]

    def test_punctuation_does_not_make_two_words_differ(self):
        names = ["2026 Shropshire Congress: Open", "2026 Shropshire Congress: Major"]
        assert section_labels(names) == ["Open", "Major"]

    def test_a_marker_standing_alone_is_not_a_word(self):
        names = ["Congress - U1600 @ MK4", "Congress - U1400 @MK4"]
        assert section_labels(names) == ["U1600", "U1400"]

    def test_a_label_may_be_several_words(self):
        assert section_labels(["Bristol Over 1799", "Bristol Under 1800"]) == ["Over 1799", "Under 1800"]

    def test_a_lone_tournament_keeps_its_name(self):
        assert section_labels(["Hastings Masters"]) == ["Hastings Masters"]

    def test_a_name_with_nothing_of_its_own_keeps_its_full_name(self):
        assert section_labels(["Congress", "Congress Open"]) == ["Congress", "Open"]

    def test_labels_that_collide_fall_back_to_full_names(self):
        names = ["Congress A Open", "Congress B Open"]
        # "A" and "B" differ, so they are fine; identical leftovers are not.
        assert section_labels(names) == ["A", "B"]
        assert section_labels(["Congress Open", "Congress Open"]) == ["Congress Open", "Congress Open"]


class TestEventName:
    def test_the_words_every_name_starts_with(self):
        names = [f"Derbyshire Congress {s}" for s in ("Open", "Major")]
        assert event_name(names) == "Derbyshire Congress"

    def test_none_in_common_is_empty(self):
        assert event_name(["Open Derbyshire", "Major Derbyshire"]) == ""


class TestIsSibling:
    def test_the_same_organiser_on_the_same_dates(self):
        assert is_sibling(_result("1"), _result("2", "Congress Major"))

    def test_other_dates_are_another_event(self):
        later = _result("2", start_date=datetime.date(2025, 11, 22), end_date=datetime.date(2025, 11, 23))
        assert not is_sibling(_result("1"), later)

    def test_another_organiser_is_another_event(self):
        assert not is_sibling(_result("1"), _result("2", organizer="Someone else"))

    def test_the_organiser_is_compared_without_regard_to_case_or_spacing(self):
        assert is_sibling(_result("1"), _result("2", organizer="  org "))

    def test_the_director_stands_in_for_a_missing_organiser(self):
        mine = _result("1", organizer=None)
        assert is_sibling(mine, _result("2", organizer=None))
        assert not is_sibling(mine, _result("3", organizer=None, director="Other"))

    def test_an_empty_organiser_does_not_match_everything_that_day(self):
        """With nobody named, the name's opening words are all that is left."""
        mine = _result("1", "Weekend Chess Open", organizer=None, director=None)
        assert is_sibling(mine, _result("2", "Weekend Chess Major", organizer=None, director=None))
        assert not is_sibling(mine, _result("3", "Quite Different Open", organizer=None, director=None))

    def test_no_dates_is_no_evidence(self):
        undated = _result("1", start_date=None, end_date=None)
        assert not is_sibling(undated, _result("2", start_date=None, end_date=None))


def test_the_siblings_are_searched_for_by_organiser_first():
    assert sibling_query(_result()) == {"organizer": "Org"}
    assert sibling_query(_result(organizer=None)) == {"director": "Dir"}
    assert sibling_query(_result("1", "Weekend Open Extra", organizer=None, director=None)) == {
        "name": "Weekend Open"
    }


def test_group_sections_orders_by_number_and_includes_the_target():
    target = _result("5", "Congress Minor")
    event = group_sections(target, [_result("9", "Congress Open"), _result("3", "Congress Major")])
    assert [(s.id, s.label) for s in event.sections] == [("3", "Major"), ("5", "Minor"), ("9", "Open")]


class _Page:
    def __init__(self, text, url="https://s2.chess-results.com/TurnierSuche.aspx?lan=1"):
        self.text, self.url = text, url

    def raise_for_status(self):
        pass


class _Session:
    """Replays saved search pages, one per post, and remembers what was posted."""

    def __init__(self, *posts):
        self.posts = list(posts)
        self.sent = []
        self.gets = 0

    def get(self, url, **kwargs):
        self.gets += 1
        return _Page(fixture("search_form.html"))

    def post(self, url, data=None, **kwargs):
        self.sent.append(data)
        return _Page(fixture(self.posts.pop(0)))

    @property
    def headers(self):
        return {}


def _client(*posts):
    session = _Session(*posts)
    return ChessResults(session, delay=0), session


class TestSearch:
    def test_it_posts_the_criteria_with_the_view_state(self):
        client, session = _client("search_derbyshire_congress.html")
        client.search("Derbyshire Congress", organizer="Woodhouse", ends_from=datetime.date(2024, 11, 24))
        sent = session.sent[0]
        assert sent["ctl00$P1$txt_bez"] == "Derbyshire Congress"
        assert sent["ctl00$P1$txt_veranstalter"] == "Woodhouse"
        assert sent["ctl00$P1$txt_von_tag"] == "2024-11-24"
        assert sent["ctl00$P1$txt_bis_tag"] == ""
        assert sent["__VIEWSTATE"]
        assert sent["ctl00$P1$cb_suchen"] == "Search"

    def test_it_looks_a_tournament_up_by_its_number(self):
        client, session = _client("search_by_tnr_derbyshire2024_open.html")
        client.search(tournament_id=1063614)
        assert session.sent[0]["ctl00$P1$txt_tnr"] == "1063614"

    def test_a_search_with_no_criterion_is_refused(self):
        client, session = _client()
        with pytest.raises(ValueError, match="at least one criterion"):
            client.search()
        assert session.gets == 0

    @pytest.mark.parametrize(
        ("limit", "option"), [(1, "0"), (100, "0"), (101, "1"), (600, "3"), (99999, "5")]
    )
    def test_the_smallest_page_that_holds_the_limit_is_asked_for(self, limit, option):
        client, session = _client("search_derbyshire_congress.html")
        client.search("x", limit=limit)
        assert session.sent[0]["ctl00$P1$combo_anzahl_zeilen"] == option

    def test_a_limit_below_the_matches_says_how_many_there_were(self):
        client, _ = _client("search_derbyshire_congress.html")
        found = client.search("Derbyshire", limit=4)
        assert (len(found), found.total, found.truncated) == (4, 15, True)

    def test_finished_only_ticks_the_box(self):
        client, session = _client("search_derbyshire_congress.html", "search_derbyshire_congress.html")
        client.search("x")
        client.search("x", finished_only=True)
        assert "ctl00$P1$cbox_zuEnde" not in session.sent[0]
        assert session.sent[1]["ctl00$P1$cbox_zuEnde"] == "on"


class TestSections:
    def test_the_sections_of_a_congress_with_their_counts(self):
        client, _ = _client(
            "search_by_tnr_derbyshire2024_open.html", "search_derbyshire2024_by_organizer.html"
        )
        event = client.sections(1063614)
        assert event.summary() == "Open 31; Major 28; Intermediate 40; Minor 31; Foundation 19 (2024)"
        assert event.name == "Derbyshire Congress"
        assert event.total == 149

    def test_it_takes_two_searches_and_no_tournament_page(self):
        client, session = _client(
            "search_by_tnr_derbyshire2024_open.html", "search_derbyshire2024_by_organizer.html"
        )
        client.sections(1063614)
        assert len(session.sent) == 2
        # The second narrows to the one organiser on the day the event ended.
        assert session.sent[1]["ctl00$P1$txt_veranstalter"] == "David Woodhouse"
        assert (
            session.sent[1]["ctl00$P1$txt_von_tag"] == session.sent[1]["ctl00$P1$txt_bis_tag"] == "2024-11-24"
        )

    def test_other_years_by_the_same_organiser_are_not_sections(self):
        """The whole name search finds three congresses; only the target's own dates count."""
        client, _ = _client("search_by_tnr_derbyshire2024_open.html", "search_derbyshire_congress.html")
        assert [s.label for s in client.sections(1063614).sections] == [
            "Open",
            "Major",
            "Intermediate",
            "Minor",
            "Foundation",
        ]

    def test_a_name_the_search_cut_is_read_in_full(self, monkeypatch):
        """Without this every Milton Keynes label would be lost off the end of the name."""
        by_id = {
            "1346566": "Milton Keynes FIDE Chess Congress 28th-29th Mar 2026 - OPEN @MK4 1NA",
            "1346568": "Milton Keynes FIDE Chess Congress 28th-29th Mar 2026 - U1900 @MK4 1NA",
            "1346570": "Milton Keynes FIDE Chess Congress 28th-29th Mar 2026 - U1600 @ MK4 1NA",
            "1346571": "Milton Keynes Chess Congress 28th-29th Mar 2026 - U1400 ECF @ MK4 1NA",
        }
        client, _ = _client("search_milton_keynes2026.html", "search_milton_keynes2026.html")
        monkeypatch.setattr(
            client,
            "entrants",
            lambda tid: Entrants(
                id=str(tid), name=by_id[str(tid)], time_control=None, dates=None, players=[]
            ),
        )
        event = client.sections(1346570)
        assert event.summary() == "FIDE OPEN 14; FIDE U1900 33; FIDE U1600 19; U1400 ECF 20 (2026)"
        assert event.total == 86

    def test_an_unknown_number_is_an_error(self):
        client, _ = _client("search_no_results.html")
        with pytest.raises(TournamentNotFoundError):
            client.sections(1)

    def test_an_undated_tournament_is_its_own_only_section(self, monkeypatch):
        undated = SearchResult(id="7", name="Mystery Open", players=3)
        client, _ = _client()
        calls = []

        def search(**kwargs):
            calls.append(kwargs)
            return SearchResults([undated], 1)

        monkeypatch.setattr(client, "search", search)
        event = client.sections(7)
        assert [s.id for s in event.sections] == ["7"]
        assert len(calls) == 1  # with no date there is nothing to narrow a second search by
