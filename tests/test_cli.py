import argparse
import json
import re

import pytest

from chess_results.cli import (
    _how_far,
    _limited,
    _round,
    _state,
    build_parser,
    cmd_colours,
    cmd_dump,
    cmd_pairings,
    cmd_standings,
    cmd_unfinished,
    main,
)
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
        cmd_standings(argparse.Namespace(after=6, limit=None))
        lines = capsys.readouterr().out.splitlines()
        assert lines[0].endswith("during round 6: 46 of 52 results in")
        states = {re.split(r"\s{2,}", line)[-1] for line in lines[1:]}
        assert {"playing", "bye"} <= states
        assert states & {"1", "½", "0"}

    def test_a_settled_round_needs_no_such_column(self, british, capsys, monkeypatch):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: british)
        cmd_standings(argparse.Namespace(after=5, limit=None))
        lines = capsys.readouterr().out.splitlines()
        assert lines[0].endswith("after round 5")
        assert not any(line.endswith("playing") for line in lines[1:])


class TestPairings:
    """One round's board-by-board table."""

    @staticmethod
    def _run(event, monkeypatch, capsys, **kwargs):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: event)
        cmd_pairings(argparse.Namespace(**{"round": None, "after": None, "limit": None, **kwargs}))
        return capsys.readouterr().out.splitlines()

    def test_a_settled_round_shows_boards_players_and_results(self, british, monkeypatch, capsys):
        lines = self._run(british, monkeypatch, capsys, round=5)
        assert lines[0].endswith("round 5 pairings")
        assert lines[1].split() == ["Bd", "Pts", "No", "White", "Res", "Pts", "No", "Black"]
        assert lines[2] == (
            "   1   3½    3  GM  Royal, Shreyas            ½-½      4    6  IM  Bazakutsa, Svyatoslav"
        )

    def test_starting_numbers_are_joined_in_from_the_starting_rank(self, british, monkeypatch, capsys):
        """This event's pairing pages carry no No. columns, so the rows have none."""
        assert british.rounds[5][0].white.start_no is None
        assert "  3  GM  Royal, Shreyas" in self._run(british, monkeypatch, capsys, round=5)[2]

    def test_the_heading_counts_the_results_of_a_live_round(self, british, monkeypatch, capsys):
        assert self._run(british, monkeypatch, capsys, round=6)[0].endswith(
            "round 6 pairings, 46 of 52 results in"
        )

    def test_a_paired_but_unplayed_round_says_so_and_shows_no_results(self, british, monkeypatch, capsys):
        lines = self._run(british, monkeypatch, capsys, round=7)
        assert lines[0].endswith("round 7 pairings, no results yet")
        assert "-" in lines[2].split()
        assert not any(re.search(r"[\d½]-[\d½]", line) for line in lines[2:])

    def test_rows_with_no_opponent_keep_their_board_and_say_what_happened(self, british, monkeypatch, capsys):
        """Byes and withdrawals are rows on the page too, and round 6 still has them."""
        tails = {re.split(r"\s{2,}", line)[-1] for line in self._run(british, monkeypatch, capsys, round=6)}
        assert {"bye", "not paired"} <= tails

    def test_the_round_defaults_to_the_latest(self, british, monkeypatch, capsys):
        assert self._run(british, monkeypatch, capsys)[0].endswith("round 7 pairings, no results yet")

    def test_after_names_a_round_too_and_the_positional_wins(self, british, monkeypatch, capsys):
        assert self._run(british, monkeypatch, capsys, after=5)[0].endswith("round 5 pairings")
        assert self._run(british, monkeypatch, capsys, round=4, after=5)[0].endswith("round 4 pairings")

    def test_a_round_the_event_has_not_reached_is_clamped(self, british, monkeypatch, capsys):
        assert self._run(british, monkeypatch, capsys, round=99)[0].endswith(
            "round 7 pairings, no results yet"
        )


class TestLimit:
    """``--limit`` counts rows of data, which ``| head`` cannot do."""

    @pytest.mark.parametrize(
        ("limit", "kept", "dropped"),
        [(None, 4, 0), (10, 4, 0), (4, 4, 0), (3, 3, 1), (1, 1, 3), (0, 0, 4), (-2, 0, 4)],
    )
    def test_rows_are_taken_from_the_front(self, limit, kept, dropped):
        rows, left_out = _limited(["a", "b", "c", "d"], limit)
        assert (len(rows), left_out) == (kept, dropped)

    def test_the_heading_is_not_one_of_the_rows(self, british, monkeypatch, capsys):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: british)
        cmd_standings(argparse.Namespace(after=5, limit=3))
        lines = capsys.readouterr().out.splitlines()
        assert lines[0].endswith("after round 5")
        assert len(lines) == 5  # heading, three players, and the tally
        assert lines[-1] == "… and 105 more"

    def test_nothing_is_said_when_nothing_is_left_out(self, british, monkeypatch, capsys):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: british)
        cmd_standings(argparse.Namespace(after=5, limit=500))
        assert "more" not in capsys.readouterr().out.splitlines()[-1]

    def test_dump_refuses_it_rather_than_ignoring_it(self):
        """Truncated JSON is not JSON, so the flag is not on dump at all."""
        with pytest.raises(SystemExit) as exit_info:
            build_parser().parse_args(["dump", "1452107", "--limit", "3"])
        assert exit_info.value.code == 2


class TestBrokenPipe:
    """`chess-results dump ... | head` must not look like a crash."""

    def test_a_closed_pipe_is_not_an_error_report(self, monkeypatch):
        silenced = []
        monkeypatch.setattr("chess_results.cli._silence_stdout", lambda: silenced.append(True))
        monkeypatch.setattr("chess_results.cli._fetch", _raise_broken_pipe)
        assert main(["standings", "1452107"]) == 141
        assert silenced == [True]


def _raise_broken_pipe(args):
    raise BrokenPipeError


class TestRoundIsClamped:
    """``--after`` must never name a round the tournament does not have."""

    @pytest.mark.parametrize(
        ("given", "expected"),
        [(None, 7), (6, 6), (7, 7), (8, 7), (123, 7), (0, 1), (-4, 1)],
    )
    def test_clamped_to_the_rounds_played(self, british, given, expected):
        assert _round(given, british) == expected

    def test_heading_reports_the_last_round_not_the_request(self, british, capsys, monkeypatch):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: british)
        cmd_colours(argparse.Namespace(after=123, limit=None))
        assert "after round 7" in capsys.readouterr().out.splitlines()[0]


class TestDump:
    """``dump`` is the one command that writes a file rather than printing."""

    def _run(self, event, monkeypatch, output):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: event)
        return cmd_dump(argparse.Namespace(output=output))

    def test_without_an_output_the_json_goes_to_stdout(self, british, monkeypatch, capsys):
        assert self._run(british, monkeypatch, None) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["id"] == "1452107"
        assert len(payload["players"]) == 108
        assert sorted(payload["rounds"]) == [str(rnd) for rnd in range(1, 8)]

    def test_with_an_output_it_writes_the_file_and_says_so_on_stderr(
        self, british, monkeypatch, capsys, tmp_path
    ):
        path = tmp_path / "event.json"
        assert self._run(british, monkeypatch, str(path)) == 0
        captured = capsys.readouterr()
        # The path goes to stderr so that stdout stays pipeable when it is used.
        assert captured.out == ""
        assert captured.err.strip() == f"wrote {path}"
        assert json.loads(path.read_text(encoding="utf-8"))["id"] == "1452107"

    def test_names_survive_the_round_trip_unescaped(self, british, monkeypatch, tmp_path):
        """ensure_ascii=False, so accented names stay readable in the file."""
        path = tmp_path / "event.json"
        self._run(british, monkeypatch, str(path))
        assert "\\u" not in path.read_text(encoding="utf-8")


class TestUnfinished:
    """What is still being played in the latest round."""

    def _run(self, event, monkeypatch, capsys, limit=None):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: event)
        assert cmd_unfinished(argparse.Namespace(limit=limit)) == 0
        return capsys.readouterr().out.splitlines()

    def test_a_paired_round_with_no_results_lists_every_board(self, british, monkeypatch, capsys):
        lines = self._run(british, monkeypatch, capsys)
        assert lines[0] == "round 7: 51 game(s) still unfinished"
        assert len(lines) == 52
        assert lines[1].startswith("  bd1   ")

    def test_each_row_names_both_players_and_their_scores(self, british, monkeypatch, capsys):
        assert re.fullmatch(r"  bd1\s+\S.*\(\S+\) vs .*\(\S+\)", self._run(british, monkeypatch, capsys)[1])

    def test_a_settled_round_says_so_instead(self, british_played_out, monkeypatch, capsys):
        assert self._run(british_played_out, monkeypatch, capsys) == ["round 8: all results in"]

    def test_limit_truncates_and_says_how_many_are_left(self, british, monkeypatch, capsys):
        lines = self._run(british, monkeypatch, capsys, limit=3)
        assert len(lines) == 5
        assert lines[-1] == "… and 48 more"
