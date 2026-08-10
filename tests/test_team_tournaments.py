"""Team events, which this library does not read -- and says so.

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
from chess_results.client import TeamTournamentError
from chess_results.parse import has_pairings, is_team_pairings, parse_pairings, parse_starting_rank


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
