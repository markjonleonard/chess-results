"""Command line interface: ``chess-results <command> <tournament-id>``."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shutil
import sys
from pathlib import Path
from typing import TypeVar

from . import __version__
from .cache import DEFAULT_CACHE_DIR, LIVE_TTL
from .client import ChessResults, TournamentError
from .models import Pairing, Play, PlayerRef, PlayKind
from .tournament import Tournament

T = TypeVar("T")

#: How many disagreements to spell out before summarising the rest.
MAX_WARNINGS = 10

DESCRIPTION = """\
Scrape a tournament from chess-results.com and report on it.

Every command takes a tournament id — the tnr number in a chess-results.com
URL, so 1452107 in https://chess-results.com/tnr1452107.aspx. Rounds are
discovered automatically; pages are cached, briefly for a live round and for
much longer once a round has settled.
"""

EPILOG = """\
examples:
  chess-results standings 1452107             the standings after the latest round
  chess-results standings 1452107 --after 6   the standings as they were after round 6
  chess-results pairings 1452107              the latest round's boards and results
  chess-results pairings 1452107 6            round 6's boards and results
  chess-results colours 1452107               colour and float history, and who is due what
  chess-results unfinished 1452107            games in the latest round with no result yet
  chess-results dump 1452107 -o event.json    the whole tournament as JSON
  chess-results standings 1452107 --limit 10  just the top ten, heading kept

Run "chess-results <command> --help" for a command's own options.
"""


def _fetch(args: argparse.Namespace) -> Tournament:
    client = ChessResults(
        delay=args.delay,
        cache=not args.no_cache,
        cache_dir=args.cache_dir,
        live_ttl=args.cache_ttl,
    )
    event = client.tournament(
        args.tournament_id,
        rounds=args.rounds,
        bye_value=args.bye_value,
        crosstable=not args.no_crosstable,
    )
    _warn_disagreements(event)
    return event


def _warn_disagreements(event: Tournament) -> None:
    """Say so when the round pages and the crosstable contradict each other.

    They never have on any page we have kept, so this means a parser has misread
    something and the numbers below it are suspect. On stderr, so it cannot
    corrupt piped output.
    """
    if not event.disagreements:
        return
    print(
        f"warning: {len(event.disagreements)} disagreement(s) between the round "
        "pages and the crosstable; the figures below may be wrong",
        file=sys.stderr,
    )
    for item in event.disagreements[:MAX_WARNINGS]:
        print(f"  {item}", file=sys.stderr)
    if len(event.disagreements) > MAX_WARNINGS:
        print(f"  … and {len(event.disagreements) - MAX_WARNINGS} more", file=sys.stderr)


def _round(requested: int | None, event: Tournament) -> int:
    """The round to report on, clamped to the rounds the tournament actually has.

    ``--after 123`` on a seven-round event means "as it stands now", not a round
    that does not exist, so it must not reach the heading or the scoring.
    """
    if requested is None:
        return event.last_round
    return max(1, min(requested, event.last_round))


def _points(value: float | None) -> str:
    if value is None:
        return "-"
    whole, half = divmod(value * 2, 2)
    return f"{int(whole) if whole or not half else ''}{'½' if half else ''}" or "0"


def _progress(event: Tournament, rnd: int) -> tuple[int, int]:
    """Games decided and games in the round; equal once the round has settled.

    A round is not simply over or not: it is paired before anyone sits down, then
    live while results come in, and only then settled. A live tournament spends
    most of its time in the middle state, so no heading may assume the last.
    """
    games = event.games(rnd)
    return len(games) - len(event.unfinished(rnd)), len(games)


def _how_far(event: Tournament, after: int) -> str:
    """How far the tournament has got, for the standings heading."""
    done, total = _progress(event, after)
    if done == total:
        return f"after round {after}"
    if not done:
        return f"round {after} paired, no results yet"
    return f"during round {after}: {done} of {total} results in"


def _limited(rows: list[T], limit: int | None) -> tuple[list[T], int]:
    """The rows to print, and how many were left out.

    Counted in rows of data, not lines of output: ``--limit 10`` is ten players,
    where ``| head -10`` is nine players and a heading.
    """
    if limit is None or limit >= len(rows):
        return rows, 0
    kept = max(0, limit)
    return rows[:kept], len(rows) - kept


def _and_the_rest(dropped: int) -> None:
    """Never truncate silently: a cut-off table looks like a short tournament."""
    if dropped:
        print(f"… and {dropped} more")


def _state(play: Play | None) -> str:
    """What a player is doing in the round being reported on."""
    if play is None:
        return "-"
    if play.kind is not PlayKind.GAME:
        return "not paired" if play.kind is PlayKind.UNPAIRED else "bye"
    if play.score is None:
        return "playing"
    return _points(play.score) + ("F" if play.forfeit else "")


def cmd_dump(args: argparse.Namespace) -> int:
    event = _fetch(args)
    payload = {
        "id": event.id,
        "name": event.name,
        "rounds": {
            str(rnd): [dataclasses.asdict(p) for p in pairings]
            for rnd, pairings in sorted(event.rounds.items())
        },
        "players": [dataclasses.asdict(p) for p in event.ranking_order()],
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


def cmd_standings(args: argparse.Namespace) -> int:
    event = _fetch(args)
    after = _round(args.after, event)
    print(f"{event.name or event.id} — {_how_far(event, after)}")
    # Mid-round the scores are not comparable -- some include this round, some do
    # not -- so say outright what each player is doing. A settled round needs no
    # such column, every score being complete.
    live = bool(event.unfinished(after))
    # Nothing follows the name unless the round is live, so a settled table has
    # nothing to knock out of line and its names are left whole.
    width = _STANDINGS_PREFIX + _name_width(args.name_width, _STANDINGS_FIXED)
    players, dropped = _limited(event.ranking_order(after), args.limit)
    for rank, player in enumerate(players, start=1):
        line = (
            f"{rank:>4} {_points(player.score(after)):>4} "
            f"{player.start_no or '':>4}  {player.title or '':<3} {player.name}"
        )
        print(f"{_fit(line, width)} {_state(player.play(after))}".rstrip() if live else line)
    _and_the_rest(dropped)
    return 0


#: How much room a name gets before it is clipped. 28 fits all but one of the
#: 2026 British's 108 names; 25, which the pairings table used to allow, broke
#: four of them — and a name that overran did not merely look untidy, it shifted
#: every column after it on that row.
DEFAULT_NAME_WIDTH = 28

#: Below this a name is more ellipsis than name, so a narrow terminal is
#: allowed to wrap instead.
MIN_NAME_WIDTH = 8


def _fit(text: str, width: int) -> str:
    """Pad ``text`` to ``width``, or clip it to fit, ending in an ellipsis.

    Padding alone was the bug: ``f"{name:<25}"`` widens to the name when the
    name is longer, so one long name pushed the rest of its row out of line
    while every other row stayed put.
    """
    if width <= 0:
        return ""
    if len(text) <= width:
        return f"{text:<{width}}"
    # width - 1, not max(1, width - 1): the latter returned "a…" for a column
    # one character wide, overrunning the very column it was asked to fit.
    return text[: width - 1] + "…"


def _name_width(requested: int | None, fixed: int, columns: int = 1) -> int:
    """How much room to give each name column.

    ``--name-width`` wins outright, so a wide terminal can be told to show
    names this clips. Otherwise the table is narrowed to fit the terminal, and
    when stdout is not one it takes the default: piped output has no width to
    speak of, and something reproducible beats something that depends on
    whichever terminal happened to run it.

    :param fixed: columns the row spends on everything that is not a name.
    :param columns: how many name columns share what is left.
    """
    if requested is not None:
        return max(MIN_NAME_WIDTH, requested)
    if not sys.stdout.isatty():
        return DEFAULT_NAME_WIDTH
    room = (shutil.get_terminal_size().columns - fixed) // columns
    return max(MIN_NAME_WIDTH, min(DEFAULT_NAME_WIDTH, room))


def _result(pairing: Pairing) -> str:
    """The score line of one game, as ``1-0``, ``½-½``, ``0-1``, ``1-0F`` or ``-``."""
    if pairing.white_score is None:
        return "-"
    return f"{_points(pairing.white_score)}-{_points(pairing.black_score)}{'F' if pairing.forfeit else ''}"


def _side(event: Tournament, player: PlayerRef, points: float | None) -> str:
    """One player's half of a pairing row: pre-round score, starting number, name.

    Most events leave the ``No.`` columns off their pairing pages, so the number
    comes from the assembled player, who has it from the starting-rank list.
    """
    known = event.players.get(player.name)
    start_no = player.start_no or (known.start_no if known else None)
    title = player.title or (known.title if known else None)
    return f"{_points(points):>4} {start_no or '':>4}  {title or '':<3} {player.name}"


def _side_heading(label: str) -> str:
    """The same shape as ``_side``, so the two line up. The title column has no name."""
    return f"{'Pts':>4} {'No':>4}  {'':<3} {label}"


#: What one side of a pairing row costs before the name starts. Measured off
#: ``_side_heading`` rather than counted by hand, so changing either side's
#: shape cannot leave this behind.
_SIDE_PREFIX = len(_side_heading(""))

#: A pairing row's fixed furniture: the board and result columns, both sides'
#: prefixes, and the three spaces between the four.
_PAIRINGS_FIXED = 4 + 5 + 2 * _SIDE_PREFIX + 3


def cmd_pairings(args: argparse.Namespace) -> int:
    """Print one round's pairing table: who is on which board, against whom."""
    event = _fetch(args)
    rnd = _round(args.round if args.round is not None else args.after, event)
    done, total = _progress(event, rnd)
    state = "" if done == total else (f", {done} of {total} results in" if done else ", no results yet")
    print(f"{event.name or event.id} — round {rnd} pairings{state}")
    side = _SIDE_PREFIX + _name_width(args.name_width, _PAIRINGS_FIXED, columns=2)
    print(
        f"{'Bd':>4} {_fit(_side_heading('White'), side)} "
        f"{'Res':<5} {_fit(_side_heading('Black'), side)}".rstrip()
    )
    boards, dropped = _limited(event.rounds.get(rnd, []), args.limit)
    for pairing in boards:
        white = _side(event, pairing.white, pairing.white_points_before)
        if pairing.black is not None:
            result, black = _result(pairing), _side(event, pairing.black, pairing.black_points_before)
        else:
            # A bye or a withdrawal: no opponent, so the result column carries
            # whatever the player was awarded for the round, if anything.
            result = "" if pairing.kind is PlayKind.UNPAIRED else _points(pairing.white_score)
            black = f"{'':>4} {'':>4}  {'':<3} {_STANDING_IN[pairing.kind]}"
        print(f"{pairing.board:>4} {_fit(white, side)} {result:<5} {_fit(black, side)}".rstrip())
    _and_the_rest(dropped)
    return 0


#: What fills the opponent's side of a row that has no opponent.
_STANDING_IN = {
    PlayKind.PAIRING_BYE: "bye",
    PlayKind.REQUESTED_BYE: "requested bye",
    PlayKind.UNPAIRED: "not paired",
}


#: A colours row before the name: score, starting number, and their separators.
_COLOURS_PREFIX = 4 + 1 + 4 + 2

#: The rest of a colours row: the two 10-wide history columns, the widest
#: "B (absolute)" due text, and the three spaces between them.
_COLOURS_FIXED = _COLOURS_PREFIX + 10 + 10 + len("B (absolute)") + 3

#: A standings row before the name: rank, score, starting number, title.
_STANDINGS_PREFIX = 4 + 4 + 4 + 3 + 5

#: Only a live round adds the state column, and "not paired" is its longest.
_STANDINGS_FIXED = _STANDINGS_PREFIX + len("not paired") + 1


def cmd_colours(args: argparse.Namespace) -> int:
    """Print the colour and float history that drives the next round's pairings."""
    event = _fetch(args)
    after = _round(args.after, event)
    print(f"{event.name or event.id} — colour and float history after round {after}")
    width = _name_width(args.name_width, _COLOURS_FIXED)
    print(f"{'Pts':>4} {'No':>4}  {_fit('Name', width)} {'Colours':<10} {'Floats':<10} Due")
    players, dropped = _limited(event.ranking_order(after), args.limit)
    for player in players:
        colours = "".join(c.value.upper() for c in player.colours(after))
        floats = "".join((p.float_direction or "-") for p in player.plays if p.round <= after)
        due, strength = player.colour_preference(after)
        due_text = f"{due.value.upper()} ({strength.value})" if due else "-"
        print(
            f"{_points(player.score(after)):>4} {player.start_no or '':>4}  "
            f"{_fit(player.name, width)} {colours:<10} {floats:<10} {due_text}"
        )
    _and_the_rest(dropped)
    return 0


def cmd_unfinished(args: argparse.Namespace) -> int:
    event = _fetch(args)
    games = event.unfinished()
    if not games:
        print(f"round {event.last_round}: all results in")
        return 0
    print(f"round {event.last_round}: {len(games)} game(s) still unfinished")
    shown, dropped = _limited(games, args.limit)
    for game in shown:
        print(
            f"  bd{game.board:<4} {game.white.name} ({_points(game.white_points_before)}) "
            f"vs {game.black.name if game.black else '?'} ({_points(game.black_points_before)})"
        )
    _and_the_rest(dropped)
    return 0


def _shared(defaults: bool = True) -> argparse.ArgumentParser:
    """Options accepted either side of the subcommand.

    The top-level parser carries the real defaults; the subcommand copies
    suppress theirs, so a value given before the subcommand is not overwritten
    by the subparser's default afterwards.
    """
    parser = argparse.ArgumentParser(add_help=False)
    group = parser.add_argument_group("common options (accepted before or after the command)")

    def default(value: object) -> object:
        return value if defaults else argparse.SUPPRESS

    group.add_argument(
        "--delay",
        type=float,
        default=default(1.0),
        metavar="SECONDS",
        help="wait between requests (default 1.0)",
    )
    group.add_argument(
        "--rounds", type=int, default=default(None), metavar="N", help="stop after this many rounds"
    )
    group.add_argument(
        "--bye-value",
        type=float,
        default=default(1.0),
        metavar="POINTS",
        help="points a pairing-allocated bye is worth (default 1.0)",
    )
    group.add_argument(
        "--after",
        type=int,
        default=default(None),
        metavar="ROUND",
        help="report on this round rather than the latest; clamped to the "
        "rounds played (standings, colours and pairings)",
    )
    group.add_argument(
        "--no-crosstable",
        action="store_true",
        default=default(False),
        help="skip the crosstable request; scores will be wrong for "
        "anyone whose bye has been dropped from its round page",
    )
    group.add_argument(
        "--no-cache", action="store_true", default=default(False), help="always refetch, ignoring the cache"
    )
    group.add_argument(
        "--cache-ttl",
        type=int,
        default=default(LIVE_TTL),
        metavar="SECONDS",
        help=f"how long to reuse a live round's page (default {LIVE_TTL}); "
        "finished rounds are cached for far longer",
    )
    group.add_argument(
        "--cache-dir",
        default=default(None),
        metavar="DIR",
        help=f"where to keep cached pages (default {DEFAULT_CACHE_DIR})",
    )
    return parser


COMMANDS = (
    (
        "dump",
        (),
        cmd_dump,
        "write the whole tournament as JSON",
        "Every round's pairings and every player's assembled history, as JSON.",
    ),
    (
        "standings",
        (),
        cmd_standings,
        "print the cross-round standings",
        "Players in ranking order with their scores, reconciled against the "
        "crosstable so that byes dropped from the round pages still count.",
    ),
    (
        "pairings",
        (),
        cmd_pairings,
        "print a round's board-by-board pairings",
        "One round's pairing table: board, both players with the score each "
        "carried into the round, and the result. The latest round unless a round "
        "number is given (--after names one too, for consistency with the other "
        "commands). Byes and withdrawals keep their row, as chess-results shows "
        "them — though only while the round is the current one.",
    ),
    (
        "colours",
        ("colors",),
        cmd_colours,
        "print colour and float histories",
        "Each player's colours so far, their up/down floats, and the colour they "
        "are due next — the history a Swiss pairing engine works from.",
    ),
    (
        "unfinished",
        (),
        cmd_unfinished,
        "list games without a result",
        "The games in the latest round still being played. Nothing to report once every result is in.",
    ),
)


#: Commands whose arguments are not simply a tournament id, for the usage line.
USAGE_ARGS = {
    "dump": "[-o FILE] <tournament-id>",
    "pairings": "<tournament-id> [<round>]",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chess-results",
        usage="chess-results [options] <command> <tournament-id>",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[_shared()],
    )
    parser.add_argument("--version", action="version", version=f"chess-results {__version__}")
    # prog is spelled out because the custom usage above would otherwise become
    # the children's prog, giving "chess-results [options] <command> ... standings".
    sub = parser.add_subparsers(
        dest="command", required=True, title="commands", metavar="<command>", prog="chess-results"
    )

    for name, aliases, handler, help_text, description in COMMANDS:
        child = sub.add_parser(
            name,
            aliases=list(aliases),
            help=help_text,
            usage=f"chess-results [options] {name} {USAGE_ARGS.get(name, '<tournament-id>')}",
            description=description,
            parents=[_shared(defaults=False)],
        )
        child.add_argument(
            "tournament_id", metavar="<tournament-id>", help="chess-results tournament id, e.g. 1452107"
        )
        if name == "dump":
            child.add_argument("-o", "--output", metavar="FILE", help="write JSON here instead of stdout")
        else:
            # Not on dump: truncated JSON is not JSON. Left off the top-level
            # parser for the same reason, so `dump --limit` is an error rather
            # than a flag that quietly does nothing.
            child.add_argument(
                "--limit",
                type=int,
                metavar="ROWS",
                help="print at most this many rows, then say how many were left out",
            )
            # Alongside --limit, and off dump for the same reason: JSON has no
            # columns to align, and clipping a name there would corrupt data
            # rather than tidy a table.
            child.add_argument(
                "--name-width",
                type=int,
                metavar="CHARS",
                help=f"room to give a player's name before clipping it "
                f"(default {DEFAULT_NAME_WIDTH}, narrowed to fit the terminal; "
                f"anything under {MIN_NAME_WIDTH} is treated as {MIN_NAME_WIDTH})",
            )
        if name == "pairings":
            child.add_argument(
                "round",
                nargs="?",
                type=int,
                metavar="<round>",
                help="which round to show (default the latest)",
            )
        child.set_defaults(func=handler)
    return parser


def _silence_stdout() -> None:
    """Point what is left of stdout at /dev/null, after the reader has gone away.

    ``dump ... | head`` closes the pipe long before we stop writing. Python's
    parting flush of a dead stdout prints "Exception ignored ... BrokenPipeError"
    over the user's prompt, which reads as a crash; this gives the flush somewhere
    harmless to go.
    """
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if not (sys.argv[1:] if argv is None else argv):
        # A bare "chess-results" is a request for help, not a usage error.
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    if not hasattr(args, "output"):
        args.output = None
    try:
        code: int = args.func(args)
        return code
    except BrokenPipeError:
        _silence_stdout()
        return 141  # what a shell reports for a process killed by SIGPIPE
    except TournamentError as exc:
        # A tournament this cannot read, or one with nothing to read yet.
        # Neither is a crash, so say so in one line rather than showing a
        # traceback for something the user can do nothing about.
        print(f"chess-results: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
