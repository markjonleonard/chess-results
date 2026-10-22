"""Reading what a pairing-allocated bye is worth, rather than asking.

A round page prints each player's score going into the round, and that score
includes whatever the arbiter gave for a bye in an earlier one. The British
awards a full point, which is the one real event here that can be checked; the
half-point case is built by hand, since no fixture comes from an event that
awards less.
"""

import copy

import pytest
from tests.conftest import _british, fixture
from tests.test_cache import FakeSession, pages

from chess_results.cli import _note_inferred_bye_value, build_parser
from chess_results.client import ChessResults
from chess_results.models import Pairing, PlayerRef, PlayKind
from chess_results.parse import parse_crosstable, parse_pairings, parse_starting_rank
from chess_results.tournament import Tournament


def _game(rnd, board, white, black, result, before):
    """A decided game; ``before`` is the (white, black) pre-round scores."""
    white_score, black_score = result
    return Pairing(
        round=rnd,
        board=board,
        white=PlayerRef(white),
        black=PlayerRef(black),
        kind=PlayKind.GAME,
        white_points_before=before[0],
        black_points_before=before[1],
        white_score=white_score,
        black_score=black_score,
    )


def _bye(rnd, board, player, before, value):
    return Pairing(
        round=rnd,
        board=board,
        white=PlayerRef(player),
        black=None,
        kind=PlayKind.PAIRING_BYE,
        white_points_before=before,
        white_score=value,
    )


def _event(value=0.5, extra_bye=None):
    """Five players, E out in round 1 and, optionally, another player in round 2."""
    event = Tournament(id="x", bye_value=1.0)
    event.add_round(
        [
            _game(1, 1, "A", "B", (1.0, 0.0), (0.0, 0.0)),
            _game(1, 2, "C", "D", (0.5, 0.5), (0.0, 0.0)),
            _bye(1, 3, "E", 0.0, 1.0),
        ]
    )
    # Round 2: E is back, having been given ``value`` for the bye.
    second = [
        _game(2, 1, "A", "E", (1.0, 0.0), (1.0, value)),
        _game(2, 2, "C", "B", (0.5, 0.5), (0.5, 0.0)),
    ]
    second.append(_bye(2, 3, "D", 0.5, 1.0))
    event.add_round(second)
    if extra_bye is not None:
        event.add_round(
            [
                _game(3, 1, "A", "C", (1.0, 0.0), (2.0, 1.0)),
                _game(3, 2, "D", "E", (0.5, 0.5), (0.5 + extra_bye, value)),
                _bye(3, 3, "B", 0.5, 1.0),
            ]
        )
    return event


class TestTheEvidence:
    def test_a_half_point_bye_is_read_from_the_next_pre_round_score(self):
        assert _event(0.5).bye_value_evidence()["E"] == 0.5

    def test_a_full_point_bye_is_read_the_same_way(self):
        assert _event(1.0).bye_value_evidence()["E"] == 1.0

    def test_other_results_are_taken_off_first(self):
        # D's bye is in round 2; their round 3 score is 0.5 (round 1 draw) + the bye.
        event = _event(0.5, extra_bye=0.5)
        assert event.bye_value_evidence()["D"] == 0.5

    def test_a_player_with_no_bye_gives_none(self):
        assert set(_event(0.5).bye_value_evidence()) <= {"D", "E"}

    def test_a_missing_round_is_not_mistaken_for_a_bye(self):
        event = _event(0.5)
        event.players["E"].plays = [p for p in event.players["E"].plays if p.round != 1]
        assert "E" not in event.bye_value_evidence()

    def test_an_unfinished_round_before_it_is_not_evidence(self):
        event = _event(0.5)
        for play in event.players["E"].plays:
            if play.kind is PlayKind.GAME:
                continue
            play.score = None
        assert "E" not in event.bye_value_evidence()

    def test_a_figure_outside_nought_to_one_is_not_a_bye_value(self):
        assert "E" not in _event(4.0).bye_value_evidence()


class TestInferring:
    def test_unanimous_evidence_gives_the_value(self):
        assert _event(0.5).infer_bye_value() == 0.5

    def test_no_evidence_gives_none(self):
        event = Tournament(id="x")
        event.add_round([_game(1, 1, "A", "B", (1.0, 0.0), (0.0, 0.0))])
        assert event.infer_bye_value() is None

    def test_conflicting_evidence_guesses_nothing_and_says_so(self):
        # E says a half; D, given a bye in round 2, says a full point.
        event = _event(0.5, extra_bye=1.0)
        assert event.infer_bye_value() is None
        assert [d.field for d in event.disagreements] == ["bye_value"]
        assert "pairing-allocated bye worth" in str(event.disagreements[0])

    def test_the_british_awards_a_full_point(self):
        event = _british(crosstable=True, rounds=8, played_out=True)
        evidence = event.bye_value_evidence()
        assert len(evidence) >= 3
        assert set(evidence.values()) == {1.0}
        assert event.infer_bye_value() == 1.0
        assert event.disagreements == []


class TestRescoring:
    def test_set_bye_value_rescores_the_rounds_and_the_players(self):
        event = _event(0.5)
        event.set_bye_value(0.5)
        assert event.bye_value == 0.5
        assert {
            p.white_score for r in event.rounds.values() for p in r if p.kind is PlayKind.PAIRING_BYE
        } == {0.5}
        assert {
            play.score
            for pl in event.players.values()
            for play in pl.plays
            if play.kind is PlayKind.PAIRING_BYE
        } == {0.5}

    def test_games_and_requested_byes_are_left_alone(self):
        event = _event(0.5)
        before = copy.deepcopy(event.players["A"].plays)
        event.set_bye_value(0.5)
        assert event.players["A"].plays == before


class TestTheClient:
    @pytest.fixture
    def cache_dir(self, tmp_path):
        return str(tmp_path)

    def test_the_value_is_read_when_not_given(self, cache_dir):
        event = ChessResults(FakeSession(pages), delay=0, cache_dir=cache_dir).tournament(1452107)
        assert event.bye_value == 1.0
        assert event.bye_value_inferred is True

    def test_a_value_given_is_used_as_it_stands(self, cache_dir):
        event = ChessResults(FakeSession(pages), delay=0, cache_dir=cache_dir).tournament(
            1452107, bye_value=0.5
        )
        assert event.bye_value == 0.5
        assert event.bye_value_inferred is False
        scores = {
            p.score for pl in event.players.values() for p in pl.plays if p.kind is PlayKind.PAIRING_BYE
        }
        assert scores == {0.5}

    def test_an_inferred_value_rescores_what_the_crosstable_recovers(self, cache_dir, monkeypatch):
        monkeypatch.setattr(Tournament, "infer_bye_value", lambda self: 0.5)
        event = ChessResults(FakeSession(pages), delay=0, cache_dir=cache_dir).tournament(1452107)
        assert event.bye_value == 0.5 and event.bye_value_inferred is True
        scores = {
            p.score for pl in event.players.values() for p in pl.plays if p.kind is PlayKind.PAIRING_BYE
        }
        assert scores == {0.5}


class TestTheCommandLine:
    def test_the_value_is_not_assumed(self):
        assert build_parser().parse_args(["standings", "1"]).bye_value is None

    def test_a_value_given_is_a_float(self):
        assert build_parser().parse_args(["standings", "1", "--bye-value", "0.5"]).bye_value == 0.5

    def test_a_worked_out_value_below_a_point_is_mentioned(self, capsys):
        event = Tournament(id="x", bye_value=0.5, bye_value_inferred=True)
        _note_inferred_bye_value(event)
        assert "worth ½" in capsys.readouterr().err

    def test_the_usual_full_point_is_not(self, capsys):
        _note_inferred_bye_value(Tournament(id="x", bye_value=1.0, bye_value_inferred=True))
        assert capsys.readouterr().err == ""

    def test_a_value_the_user_gave_is_not(self, capsys):
        _note_inferred_bye_value(Tournament(id="x", bye_value=0.5))
        assert capsys.readouterr().err == ""


def _wells(crosstable=True):
    """The 2024 Wells Congress Minor section: a half-point bye the page calls ``bye``.

    Round 2 lists Chris Whitehead against ``bye`` with ``½`` in the Result cell;
    rounds 4 and 5 list Glasbey and Moseley against ``bye`` with ``1``. The
    crosstable calls the first a requested bye and the other two pairing-allocated.
    """
    event = Tournament(id="895964", name="Wells Minor")
    event.add_starting_rank(parse_starting_rank(fixture("wells2024_minor_startingrank.html")))
    for rnd in range(1, 6):
        event.add_round(parse_pairings(fixture(f"wells2024_minor_r{rnd}.html"), rnd))
    if crosstable:
        event.add_crosstable(parse_crosstable(fixture("wells2024_minor_crosstable.html")))
    return event


class TestAPageThatPrintsTheByesValue:
    def test_the_result_cell_scores_the_bye(self):
        scores = {
            p.white.name: p.white_score
            for rnd in range(1, 6)
            for p in parse_pairings(fixture(f"wells2024_minor_r{rnd}.html"), rnd)
            if p.kind is PlayKind.PAIRING_BYE
        }
        assert scores == {"Chris Whitehead": 0.5, "Billy Glasbey": 1.0, "Marlowe Moseley": 1.0}

    def test_an_empty_cell_falls_back_to_a_full_point(self):
        byes = [
            p for p in parse_pairings(fixture("british2026_champ_r7_midround.html"), 7) if p.black is None
        ]
        assert {p.white_score for p in byes if p.kind is PlayKind.PAIRING_BYE} == {1.0}

    def test_a_value_given_wins_over_the_page(self):
        pairings = parse_pairings(fixture("wells2024_minor_r4.html"), 4, bye_value=0.25)
        assert [p.white_score for p in pairings if p.kind is PlayKind.PAIRING_BYE] == [0.25]

    def test_the_crosstable_says_the_half_point_one_was_requested(self):
        event = _wells()
        play = event.players["Chris Whitehead"].play(2)
        assert (play.kind, play.score, play.float_direction) == (PlayKind.REQUESTED_BYE, 0.5, None)
        assert [p.kind for p in event.rounds[2] if p.black is None and p.white.name == "Chris Whitehead"] == [
            PlayKind.REQUESTED_BYE
        ]

    def test_that_is_no_disagreement_and_the_total_is_the_published_one(self):
        event = _wells()
        assert event.disagreements == []
        assert event.players["Chris Whitehead"].score(5) == 0.5

    def test_the_real_pairing_byes_stay_pairing_byes(self):
        event = _wells()
        assert event.players["Billy Glasbey"].play(4).kind is PlayKind.PAIRING_BYE
        assert event.players["Marlowe Moseley"].play(5).kind is PlayKind.PAIRING_BYE

    def test_without_the_crosstable_the_printed_score_is_still_right(self):
        event = _wells(crosstable=False)
        assert event.players["Chris Whitehead"].play(2).score == 0.5

    def test_only_the_pairing_allocated_byes_are_evidence(self):
        event = _wells()
        assert event.bye_value_evidence() == {"Billy Glasbey": 1.0}
        assert event.infer_bye_value() == 1.0
