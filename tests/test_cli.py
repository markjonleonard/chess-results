import argparse
import re

import pytest

from chess_results.cli import _how_far, _round, _state, build_parser, cmd_colours, cmd_standings, main
from chess_results.models import Play, PlayKind


def test_shared_options_parse_before_the_subcommand():
    args = build_parser().parse_args(["--after", "6", "colours", "1452107"])
    assert (args.after, args.tournament_id) == (6, "1452107")


def test_shared_options_parse_after_the_subcommand():
    args = build_parser().parse_args(["colours", "1452107", "--after", "6"])
    assert (args.after, args.tournament_id) == (6, "1452107")


def test_bye_value_defaults_to_a_full_point():
    assert build_parser().parse_args(["standings", "1"]).bye_value == 1.0


def test_colors_is_accepted_as_a_synonym_for_colours():
    args = build_parser().parse_args(["colors", "1452107"])
    assert args.func is cmd_colours
    assert args.tournament_id == "1452107"


class TestBareInvocation:
    """``chess-results`` on its own asks for help; it is not a usage error."""

    def test_prints_the_full_help_and_succeeds(self, capsys):
        assert main([]) == 0
        out = capsys.readouterr().out
        assert "usage: chess-results [options] <command> <tournament-id>" in out
        assert "print the cross-round standings" in out
        assert "examples:" in out

    def test_a_bad_command_is_still_an_error(self):
        with pytest.raises(SystemExit) as exit_info:
            main(["wibble"])
        assert exit_info.value.code == 2


def test_subcommand_usage_does_not_inherit_the_top_level_usage_line(capsys):
    """The custom top-level usage would otherwise become each child's prog."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["standings", "--help"])
    assert capsys.readouterr().out.startswith("usage: chess-results [options] standings <tournament-id>")


class TestStandingsDistinguishALiveRoundFromASettledOne:
    """Mid-round the scores are not comparable, and the heading must not pretend they are."""

    def test_heading_tells_the_three_states_apart(self, british):
        assert _how_far(british, 5) == "after round 5"
        assert _how_far(british, 6) == "during round 6: 46 of 52 results in"
        assert _how_far(british, 7) == "round 7 paired, no results yet"

    @pytest.mark.parametrize(
        ("play", "expected"),
        [
            (None, "-"),
            (Play(round=6, kind=PlayKind.GAME), "playing"),
            (Play(round=6, kind=PlayKind.GAME, score=1.0), "1"),
            (Play(round=6, kind=PlayKind.GAME, score=0.5), "½"),
            (Play(round=6, kind=PlayKind.GAME, score=0.0), "0"),
            (Play(round=6, kind=PlayKind.GAME, score=0.0, forfeit=True), "0F"),
            (Play(round=6, kind=PlayKind.PAIRING_BYE, score=1.0), "bye"),
            (Play(round=6, kind=PlayKind.REQUESTED_BYE, score=0.5), "bye"),
            (Play(round=6, kind=PlayKind.UNPAIRED), "not paired"),
        ],
    )
    def test_every_way_a_round_can_be_occupied_reads_plainly(self, play, expected):
        assert _state(play) == expected

    def test_a_live_round_says_who_is_still_playing(self, british, capsys, monkeypatch):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: british)
        cmd_standings(argparse.Namespace(after=6))
        lines = capsys.readouterr().out.splitlines()
        assert lines[0].endswith("during round 6: 46 of 52 results in")
        states = {re.split(r"\s{2,}", line)[-1] for line in lines[1:]}
        assert {"playing", "bye"} <= states
        assert states & {"1", "½", "0"}

    def test_a_settled_round_needs_no_such_column(self, british, capsys, monkeypatch):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: british)
        cmd_standings(argparse.Namespace(after=5))
        lines = capsys.readouterr().out.splitlines()
        assert lines[0].endswith("after round 5")
        assert not any(line.endswith("playing") for line in lines[1:])


class TestRoundIsClamped:
    """``--after`` must never name a round the tournament does not have."""

    @pytest.mark.parametrize(
        ("given", "expected"),
        [(None, 7), (6, 6), (7, 7), (8, 7), (123, 7), (0, 1), (-4, 1)],
    )
    def test_clamped_to_the_rounds_played(self, british, given, expected):
        assert _round(argparse.Namespace(after=given), british) == expected

    def test_heading_reports_the_last_round_not_the_request(self, british, capsys, monkeypatch):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: british)
        cmd_colours(argparse.Namespace(after=123))
        assert "after round 7" in capsys.readouterr().out.splitlines()[0]
