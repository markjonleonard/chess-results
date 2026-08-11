"""Tournaments this cannot read, and the ones with nothing to read yet.

chess-results reports a team competition in a different shape entirely. The
round page (``art=2``) pairs *teams*: ``No. | SNo | Team | MP | Res. | : |
Res. | MP | Team | SNo``, naming no player anywhere on it. The individual
boards live on a second view (``art=3``), laid out as one sub-table per match
with the two team names in its header.

Neither is a pairing table in the sense the rest of the parsers mean, so both
read as nothing. That is the safe failure -- no team name is ever mistaken for
a player -- but on its own it is indistinguishable from a tournament that has
not started, so the scrape would report an empty event with every appearance of
confidence. `is_team_pairings` exists to tell those two apart.

The fixtures are the Chinese National Youth Chess Team Championship 2026 G14
(1472122), captured 2026-08-10 with round 1 paired and unplayed.
"""

import pytest
from tests.conftest import fixture

from chess_results.cli import main
from chess_results.client import (
    RoundRobinError,
    TeamTournamentError,
    TournamentError,
    TournamentNotStartedError,
)
from chess_results.parse import (
    has_pairings,
    is_combined_pairings,
    is_team_pairings,
    parse_crosstable,
    parse_pairings,
    parse_published_totals,
    parse_starting_rank,
)


class TestTheShapeOfThesePages:
    def test_the_round_page_pairs_teams(self):
        assert is_team_pairings(fixture("cnyt2026_g14_teams_r1.html"))

    def test_an_individual_event_is_not_mistaken_for_one(self):
        for name in ("british2026_champ_r5.html", "frome2026_open_r1.html", "jeddah2026_r1.html"):
            assert not is_team_pairings(fixture(name)), name

    def test_neither_team_view_yields_pairings(self):
        """The safe failure: nothing is read, so no team becomes a player."""
        assert parse_pairings(fixture("cnyt2026_g14_teams_r1.html"), 1) == []
        assert parse_pairings(fixture("cnyt2026_g14_boards_r1.html"), 1) == []

    def test_the_board_view_looks_like_pairings_but_is_not(self):
        """It opens with a "Bo." column, so the cheap check is fooled; only
        parsing it finds out. Recorded because it is the trap to avoid if this
        is ever taken further."""
        assert has_pairings(fixture("cnyt2026_g14_boards_r1.html"))
        assert parse_pairings(fixture("cnyt2026_g14_boards_r1.html"), 1) == []

    def test_the_player_list_does_parse(self):
        """A team event still publishes an ordinary list of players, so the
        players are reachable even though their games are not."""
        rank = parse_starting_rank(fixture("cnyt2026_g14_playerrank.html"))
        assert len(rank) == 32
        assert (rank[0].name, rank[0].title, rank[0].rating) == ("Xue, Tianhao", "WIM", 2218)


class TestTheScrapeRefusesRatherThanReturnsNothing:
    class _Client:
        """Serves the team round page for every round."""

        def __init__(self):
            self.calls = 0

        def fetch(self, tournament_id, art, **kwargs):
            self.calls += 1
            if art == 0:
                return fixture("cnyt2026_g14_playerrank.html")
            return fixture("cnyt2026_g14_teams_r1.html")

    def test_tournament_raises(self, monkeypatch):
        from chess_results.client import ChessResults

        client = ChessResults()
        monkeypatch.setattr(client, "fetch", self._Client().fetch)
        with pytest.raises(TeamTournamentError, match="pairs teams"):
            client.tournament(1472122, crosstable=False)

    def test_it_says_which_tournament_and_why(self, monkeypatch):
        from chess_results.client import ChessResults

        client = ChessResults()
        monkeypatch.setattr(client, "fetch", self._Client().fetch)
        with pytest.raises(TeamTournamentError) as info:
            client.tournament(1472122, crosstable=False)
        assert "1472122" in str(info.value)
        assert "does not read" in str(info.value)

    def test_it_stops_at_the_first_round_rather_than_probing_thirty(self, monkeypatch):
        """MAX_ROUNDS is 30; refusing early keeps it to one round request."""
        from chess_results.client import ChessResults

        stub = self._Client()
        client = ChessResults()
        monkeypatch.setattr(client, "fetch", stub.fetch)
        with pytest.raises(TeamTournamentError):
            client.tournament(1472122, crosstable=False)
        assert stub.calls == 2  # the starting rank, then one round


class TestTheCommandLineSaysSoPlainly:
    def test_it_reports_one_line_and_exits_two(self, monkeypatch, capsys):
        def explode(args):
            raise TeamTournamentError("tournament 1472122 pairs teams, not players")

        monkeypatch.setattr("chess_results.cli._fetch", explode)
        assert main(["standings", "1472122"]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.strip() == "chess-results: tournament 1472122 pairs teams, not players"


class TestARoundRobinIsRefusedRatherThanMisread:
    """chess-results publishes a round robin in two shapes this cannot read.

    The pairings page holds *every* round at once, under repeated "Round N on
    ..." headings in one table, and ignores `rd` -- so a parser that read it
    would assign all nine rounds' games to whichever round it asked for. The
    crosstable is a grid of opponents rather than of rounds, which
    `parse_crosstable` reads nothing from.

    The fixtures are the USSA Closed 2026 Open (1471902), nine players and nine
    rounds, finished.
    """

    def test_the_pairings_page_holds_every_round(self):
        assert is_combined_pairings(fixture("ussa2026_roundrobin_pairings.html"))

    def test_a_swiss_round_page_does_not(self):
        """One "Round N on" heading is what a Swiss round page has; the
        detector keys off more than one, not off the tournament type, which the
        page does not state."""
        for name in ("british2026_champ_r5.html", "frome2026_open_r1.html", "jeddah2026_r1.html"):
            assert not is_combined_pairings(fixture(name)), name

    def test_the_crosstable_reads_as_nothing(self):
        """Its columns are opponents, not rounds, so no `N.Rd` header matches."""
        assert parse_crosstable(fixture("ussa2026_roundrobin_crosstable.html")) == {}

    def test_but_the_totals_beside_it_still_read(self):
        """Which is why refusing matters. `check_published_totals` would compare
        nine published totals against nothing at all and report no
        disagreement -- the cross-check silent exactly when it should shout."""
        totals = parse_published_totals(fixture("ussa2026_roundrobin_crosstable.html"))
        assert len(totals) == 9

    def test_the_scrape_refuses(self, monkeypatch):
        from chess_results.client import ChessResults

        def serve(tournament_id, art, **kwargs):
            if art == 0:
                return fixture("ussa2026_roundrobin_startingrank.html")
            return fixture("ussa2026_roundrobin_pairings.html")

        client = ChessResults()
        monkeypatch.setattr(client, "fetch", serve)
        with pytest.raises(RoundRobinError, match="every round on one"):
            client.tournament(1471902, crosstable=False)


class TestATournamentThatHasNotStartedSaysSo:
    """The commonest of the three by far.

    chess-results publishes an entry list as soon as registration opens, often
    months ahead: a field, and no games. Six round-robin tournament numbers were
    tried while hunting for a played one and four had not started.

    The fixture is the Warsaw IM norm event (1449763), captured on 2026-08-10
    for an event beginning on the 27th.
    """

    @staticmethod
    def _client(monkeypatch):
        from chess_results.client import ChessResults

        def serve(tournament_id, art, **kwargs):
            if art == 0:
                return fixture("warsaw2026_notstarted_startingrank.html")
            return fixture("warsaw2026_notstarted_r1.html")

        client = ChessResults()
        monkeypatch.setattr(client, "fetch", serve)
        return client

    def test_the_field_is_published_but_no_round_is(self):
        rank = parse_starting_rank(fixture("warsaw2026_notstarted_startingrank.html"))
        assert len(rank) == 6
        assert not has_pairings(fixture("warsaw2026_notstarted_r1.html"))

    def test_the_scrape_refuses_rather_than_reporting_zero_rounds(self, monkeypatch):
        with pytest.raises(TournamentNotStartedError, match="not started"):
            self._client(monkeypatch).tournament(1449763, crosstable=False)


class TestAllThreeShareOneBaseClass:
    """So a caller catches one thing, and the CLI reports them alike."""

    def test_every_refusal_is_a_TournamentError(self):
        for cls in (TeamTournamentError, RoundRobinError, TournamentNotStartedError):
            assert issubclass(cls, TournamentError)
            assert issubclass(cls, ValueError)

    @pytest.mark.parametrize(
        "error",
        [TeamTournamentError, RoundRobinError, TournamentNotStartedError],
    )
    def test_the_command_line_reports_each_in_one_line(self, error, monkeypatch, capsys):
        def explode(args):
            raise error("tournament 1 cannot be read for a specific reason")

        monkeypatch.setattr("chess_results.cli._fetch", explode)
        assert main(["standings", "1"]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("chess-results: ")


class TestTheErrorsAreImportableFromTheTopLevel:
    """A caller catching these should not have to reach into a submodule.

    `ChessResults` was exported and the errors it raises were not, so a
    downstream consumer had to import from `chess_results.client` — a private
    path that a refactor would break.
    """

    def test_each_is_importable_from_the_package(self):
        import chess_results

        for name in (
            "TournamentError",
            "TeamTournamentError",
            "RoundRobinError",
            "TournamentNotStartedError",
        ):
            assert hasattr(chess_results, name), name
            assert name in chess_results.__all__, name

    def test_the_base_class_catches_all_three(self):
        from chess_results import TournamentError as Base

        for name in ("TeamTournamentError", "RoundRobinError", "TournamentNotStartedError"):
            import chess_results

            assert issubclass(getattr(chess_results, name), Base)

    def test_everything_named_in_all_actually_exists(self):
        """The drift that caused this, caught generally rather than by name."""
        import chess_results

        missing = [n for n in chess_results.__all__ if not hasattr(chess_results, n)]
        assert missing == []
