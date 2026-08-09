"""Command line interface: ``chess-results <command> <tournament-id>``."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from . import __version__
from .cache import DEFAULT_CACHE_DIR, LIVE_TTL
from .client import ChessResults
from .models import Play, PlayKind
from .tournament import Tournament

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
  chess-results colours 1452107               colour and float history, and who is due what
  chess-results unfinished 1452107            games in the latest round with no result yet
  chess-results dump 1452107 -o event.json    the whole tournament as JSON

Run "chess-results <command> --help" for a command's own options.
"""


def _fetch(args: argparse.Namespace) -> Tournament:
    client = ChessResults(
        delay=args.delay,
        cache=not args.no_cache,
        cache_dir=args.cache_dir,
        live_ttl=args.cache_ttl,
    )
    return client.tournament(
        args.tournament_id,
        rounds=args.rounds,
        bye_value=args.bye_value,
        crosstable=not args.no_crosstable,
    )


def _round(args: argparse.Namespace, event: Tournament) -> int:
    """The round to report on, clamped to the rounds the tournament actually has.

    ``--after 123`` on a seven-round event means "as it stands now", not a round
    that does not exist, so it must not reach the heading or the scoring.
    """
    if args.after is None:
        return event.last_round
    return max(1, min(args.after, event.last_round))


def _points(value: float | None) -> str:
    if value is None:
        return "-"
    whole, half = divmod(value * 2, 2)
    return f"{int(whole) if whole or not half else ''}{'½' if half else ''}" or "0"


def _how_far(event: Tournament, after: int) -> str:
    """How far the tournament has got, for the heading.

    A round is not simply over or not: it is paired before anyone sits down, then
    live while results come in, and only then settled. "After round 9" is a lie
    for the first two, and it is the state a live tournament is usually in.
    """
    games, unfinished = event.games(after), event.unfinished(after)
    if not games or not unfinished:
        return f"after round {after}"
    if len(unfinished) == len(games):
        return f"round {after} paired, no results yet"
    return f"during round {after}: {len(games) - len(unfinished)} of {len(games)} results in"


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
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


def cmd_standings(args: argparse.Namespace) -> int:
    event = _fetch(args)
    after = _round(args, event)
    print(f"{event.name or event.id} — {_how_far(event, after)}")
    # Mid-round the scores are not comparable -- some include this round, some do
    # not -- so say outright what each player is doing. A settled round needs no
    # such column, every score being complete.
    live = bool(event.unfinished(after))
    for rank, player in enumerate(event.ranking_order(after), start=1):
        line = (
            f"{rank:>4} {_points(player.score(after)):>4} "
            f"{player.start_no or '':>4}  {player.title or '':<3} {player.name}"
        )
        print(f"{line:<52} {_state(player.play(after))}" if live else line)
    return 0


def cmd_colours(args: argparse.Namespace) -> int:
    """Print the colour and float history that drives the next round's pairings."""
    event = _fetch(args)
    after = _round(args, event)
    print(f"{event.name or event.id} — colour and float history after round {after}")
    print(f"{'Pts':>4} {'No':>4}  {'Name':<32} {'Colours':<10} {'Floats':<10} Due")
    for player in event.ranking_order(after):
        colours = "".join(c.value.upper() for c in player.colours(after))
        floats = "".join((p.float_direction or "-") for p in player.plays if p.round <= after)
        due, strength = player.colour_preference(after)
        due_text = f"{due.value.upper()} ({strength.value})" if due else "-"
        print(
            f"{_points(player.score(after)):>4} {player.start_no or '':>4}  "
            f"{player.name:<32} {colours:<10} {floats:<10} {due_text}"
        )
    return 0


def cmd_unfinished(args: argparse.Namespace) -> int:
    event = _fetch(args)
    games = event.unfinished()
    if not games:
        print(f"round {event.last_round}: all results in")
        return 0
    print(f"round {event.last_round}: {len(games)} game(s) still unfinished")
    for game in games:
        print(
            f"  bd{game.board:<4} {game.white.name} ({_points(game.white_points_before)}) "
            f"vs {game.black.name if game.black else '?'} ({_points(game.black_points_before)})"
        )
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
        help="report the position after this round rather than the latest; "
        "clamped to the rounds played (standings and colours only)",
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
        extra = " [-o FILE]" if name == "dump" else ""
        child = sub.add_parser(
            name,
            aliases=list(aliases),
            help=help_text,
            usage=f"chess-results [options] {name}{extra} <tournament-id>",
            description=description,
            parents=[_shared(defaults=False)],
        )
        child.add_argument(
            "tournament_id", metavar="<tournament-id>", help="chess-results tournament id, e.g. 1452107"
        )
        if name == "dump":
            child.add_argument("-o", "--output", metavar="FILE", help="write JSON here instead of stdout")
        child.set_defaults(func=handler)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if not (sys.argv[1:] if argv is None else argv):
        # A bare "chess-results" is a request for help, not a usage error.
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    if not hasattr(args, "output"):
        args.output = None
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
