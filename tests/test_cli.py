import argparse

import pytest

from chess_results.cli import _round, build_parser, cmd_colours


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
