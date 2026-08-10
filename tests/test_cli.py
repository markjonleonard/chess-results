import argparse
import copy
import json
import os
import re

import pytest

from chess_results.cli import (
    _COLOURS_PREFIX,
    _SIDE_PREFIX,
    _STANDINGS_PREFIX,
    DEFAULT_NAME_WIDTH,
    MAX_WARNINGS,
    MIN_NAME_WIDTH,
    _fit,
    _how_far,
    _limited,
    _name_width,
    _round,
    _state,
    _warn_disagreements,
    build_parser,
    cmd_colours,
    cmd_dump,
    cmd_pairings,
    cmd_standings,
    cmd_unfinished,
    main,
)
from chess_results.models import Disagreement, Play, PlayKind


def _args(**kwargs):
    """The options a reporting command reads, defaulted as the parser defaults them.

    Collected here rather than spelled out at each call so that adding an
    option to the parser does not mean editing every construction in this file
    — which is exactly what --name-width would otherwise have cost.
    """
    return argparse.Namespace(**{"after": None, "limit": None, "name_width": None, **kwargs})


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
        cmd_standings(_args(after=6))
        lines = capsys.readouterr().out.splitlines()
        assert lines[0].endswith("during round 6: 46 of 52 results in")
        states = {re.split(r"\s{2,}", line)[-1] for line in lines[1:]}
        assert {"playing", "bye"} <= states
        assert states & {"1", "½", "0"}

    def test_a_settled_round_needs_no_such_column(self, british, capsys, monkeypatch):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: british)
        cmd_standings(_args(after=5))
        lines = capsys.readouterr().out.splitlines()
        assert lines[0].endswith("after round 5")
        assert not any(line.endswith("playing") for line in lines[1:])


class TestPairings:
    """One round's board-by-board table."""

    @staticmethod
    def _run(event, monkeypatch, capsys, **kwargs):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: event)
        cmd_pairings(_args(**{"round": None, **kwargs}))
        return capsys.readouterr().out.splitlines()

    def test_a_settled_round_shows_boards_players_and_results(self, british, monkeypatch, capsys):
        lines = self._run(british, monkeypatch, capsys, round=5)
        assert lines[0].endswith("round 5 pairings")
        assert lines[1].split() == ["Bd", "Pts", "No", "White", "Res", "Pts", "No", "Black"]
        assert lines[2] == (
            "   1   3½    3  GM  Royal, Shreyas               ½-½      4    6  IM  Bazakutsa, Svyatoslav"
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


class TestColumnsStayInLine:
    """A name longer than its column used to shift every column after it.

    ``f"{name:<25}"`` widens to the name rather than clipping it, so the four
    2026 British names over 25 characters each knocked their own row out of
    line while every other row stayed put. The fix clips instead, and these
    pin both halves: that long names are cut, and that the cut keeps the row
    the same shape as its neighbours.
    """

    @staticmethod
    def _pairings(event, monkeypatch, capsys, **kwargs):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: event)
        cmd_pairings(_args(**{"round": 6, **kwargs}))
        return capsys.readouterr().out.splitlines()

    def test_the_result_column_starts_at_one_place_on_every_row(self, british, monkeypatch, capsys):
        rows = self._pairings(british, monkeypatch, capsys)[2:]
        # Every row's result sits at the same offset, whatever the name did.
        assert len({len(row) - len(row[_SIDE_PREFIX + DEFAULT_NAME_WIDTH :]) for row in rows}) == 1

    def test_a_name_that_does_not_fit_is_clipped_with_an_ellipsis(self, british, monkeypatch, capsys):
        longest = max((p.name for p in british.players.values()), key=len)
        assert len(longest) > DEFAULT_NAME_WIDTH, "fixture no longer exercises clipping"
        rows = self._pairings(british, monkeypatch, capsys)
        assert not any(longest in row for row in rows)
        assert any("…" in row for row in rows)

    def test_a_name_that_fits_is_left_alone(self, british, monkeypatch, capsys):
        """The four that used to overrun are all inside the wider default now."""
        rows = "\n".join(self._pairings(british, monkeypatch, capsys))
        assert "Arakhamia-Grant, Ketevan E" in rows
        assert "Raju, Sooraj Menothuparambil" in rows

    def test_name_width_widens_the_column_to_show_a_clipped_name(self, british, monkeypatch, capsys):
        rows = self._pairings(british, monkeypatch, capsys, name_width=40)
        assert any("Lishoy Gengis Paratazham, Dildarav" in row for row in rows)

    def test_name_width_narrows_it_too(self, british, monkeypatch, capsys):
        rows = self._pairings(british, monkeypatch, capsys, name_width=10)[2:]
        assert all(len(row) - len(row[_SIDE_PREFIX + 10 :]) == _SIDE_PREFIX + 10 for row in rows)

    def test_no_row_is_left_with_trailing_whitespace(self, british, monkeypatch, capsys):
        rows = self._pairings(british, monkeypatch, capsys)
        assert not any(row != row.rstrip() for row in rows)

    def test_colours_clips_its_name_column_too(self, british, monkeypatch, capsys):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: british)
        cmd_colours(_args(after=6))
        rows = capsys.readouterr().out.splitlines()[2:]
        # Anchored on position rather than on finding a run of W/B: two players
        # have played one game apiece, so a single letter is a whole history.
        start = _COLOURS_PREFIX + DEFAULT_NAME_WIDTH + 1
        assert all(re.fullmatch(r"[WB]*\s*", row[start : start + 10]) for row in rows)

    def test_a_live_standings_state_column_lines_up(self, british, monkeypatch, capsys):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: british)
        cmd_standings(_args(after=6))
        rows = capsys.readouterr().out.splitlines()[1:]
        assert len({len(row) - len(row[_STANDINGS_PREFIX + DEFAULT_NAME_WIDTH :]) for row in rows}) == 1


class TestNameWidthIsChosen:
    """How wide the column gets when nothing asks for a particular width."""

    def test_an_explicit_width_wins(self):
        assert _name_width(40, fixed=0) == 40

    def test_piped_output_takes_the_default(self, monkeypatch):
        """Not a terminal, so there is no width to fit — be reproducible instead."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)
        assert _name_width(None, fixed=0) == DEFAULT_NAME_WIDTH

    def test_a_narrow_terminal_narrows_the_column(self, monkeypatch):
        monkeypatch.setattr("chess_results.cli.sys.stdout.isatty", lambda: True, raising=False)
        monkeypatch.setattr("shutil.get_terminal_size", lambda *a: os.terminal_size((60, 24)))
        assert _name_width(None, fixed=42, columns=2) == (60 - 42) // 2

    def test_a_wide_terminal_does_not_widen_it_past_the_default(self, monkeypatch):
        monkeypatch.setattr("chess_results.cli.sys.stdout.isatty", lambda: True, raising=False)
        monkeypatch.setattr("shutil.get_terminal_size", lambda *a: os.terminal_size((400, 24)))
        assert _name_width(None, fixed=42, columns=2) == DEFAULT_NAME_WIDTH

    def test_a_column_is_never_narrowed_into_uselessness(self, monkeypatch):
        monkeypatch.setattr("chess_results.cli.sys.stdout.isatty", lambda: True, raising=False)
        monkeypatch.setattr("shutil.get_terminal_size", lambda *a: os.terminal_size((20, 24)))
        assert _name_width(None, fixed=42, columns=2) == MIN_NAME_WIDTH
        assert _name_width(1, fixed=0) == MIN_NAME_WIDTH

    @pytest.mark.parametrize(
        ("text", "width", "expected"),
        [
            ("abc", 5, "abc  "),
            ("abcde", 5, "abcde"),
            ("abcdef", 5, "abcd…"),
            ("abc", 1, "…"),
            ("abc", 0, ""),
        ],
    )
    def test_fit_pads_or_clips(self, text, width, expected):
        """Never wider than asked for — the point is to hold a column, not fill it."""
        assert _fit(text, width) == expected
        assert len(_fit(text, width)) == width


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
        cmd_standings(_args(after=5, limit=3))
        lines = capsys.readouterr().out.splitlines()
        assert lines[0].endswith("after round 5")
        assert len(lines) == 5  # heading, three players, and the tally
        assert lines[-1] == "… and 105 more"

    def test_nothing_is_said_when_nothing_is_left_out(self, british, monkeypatch, capsys):
        monkeypatch.setattr("chess_results.cli._fetch", lambda args: british)
        cmd_standings(_args(after=5, limit=500))
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
        cmd_colours(_args(after=123))
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


class TestDisagreementsAreReported:
    """A contradiction between the two views means a parser has misread
    something, so it must not pass silently under a table of numbers."""

    def _event(self, british, count):
        event = copy.copy(british)
        event.disagreements = [
            Disagreement(
                player=f"Player {i}",
                round=1,
                field="score",
                from_round_page=1.0,
                from_crosstable=0.0,
            )
            for i in range(count)
        ]
        return event

    def test_nothing_is_said_when_the_views_agree(self, british, capsys):
        _warn_disagreements(british)
        assert capsys.readouterr().err == ""

    def test_each_one_is_spelled_out_on_stderr(self, british, capsys):
        _warn_disagreements(self._event(british, 2))
        err = capsys.readouterr().err.splitlines()
        assert err[0].startswith("warning: 2 disagreement(s)")
        assert err[1] == ("  round 1: Player 0: score is 1.0 on the round page but 0.0 in the crosstable")
        assert len(err) == 3

    def test_a_long_list_is_truncated_but_counted(self, british, capsys):
        _warn_disagreements(self._event(british, 25))
        err = capsys.readouterr().err.splitlines()
        assert len(err) == 1 + MAX_WARNINGS + 1
        assert err[-1] == f"  … and {25 - MAX_WARNINGS} more"

    def test_it_goes_to_stderr_so_piped_output_stays_clean(self, british, capsys):
        _warn_disagreements(self._event(british, 1))
        assert capsys.readouterr().out == ""
