"""Command line interface: ``chess-results <command> <tournament-id>``."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from .cache import DEFAULT_CACHE_DIR, LIVE_TTL
from .client import ChessResults
from .tournament import Tournament


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


def _points(value: float | None) -> str:
    if value is None:
        return "-"
    whole, half = divmod(value * 2, 2)
    return f"{int(whole) if whole or not half else ''}{'½' if half else ''}" or "0"


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
    after = args.after or event.last_round
    print(f"{event.name or event.id} — after round {after}")
    for rank, player in enumerate(event.ranking_order(after), start=1):
        print(
            f"{rank:>4} {_points(player.score(after)):>4} "
            f"{player.start_no or '':>4}  {player.title or '':<3} {player.name}"
        )
    return 0


def cmd_colours(args: argparse.Namespace) -> int:
    """Print the colour and float history that drives the next round's pairings."""
    event = _fetch(args)
    after = args.after or event.last_round
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

    def default(value: object) -> object:
        return value if defaults else argparse.SUPPRESS

    parser.add_argument("--delay", type=float, default=default(1.0), help="seconds between requests")
    parser.add_argument("--rounds", type=int, default=default(None), help="stop after this many rounds")
    parser.add_argument(
        "--bye-value",
        type=float,
        default=default(1.0),
        help="points a pairing-allocated bye is worth (default 1.0)",
    )
    parser.add_argument(
        "--after", type=int, default=default(None), help="report the position after this round"
    )
    parser.add_argument(
        "--no-crosstable",
        action="store_true",
        default=default(False),
        help="skip the crosstable request; scores will be wrong for "
        "anyone whose bye has been dropped from its round page",
    )
    parser.add_argument(
        "--no-cache", action="store_true", default=default(False), help="always refetch, ignoring the cache"
    )
    parser.add_argument(
        "--cache-ttl",
        type=int,
        default=default(LIVE_TTL),
        help=f"seconds to reuse a live round's page (default {LIVE_TTL}); "
        "finished rounds are cached for far longer",
    )
    parser.add_argument(
        "--cache-dir", default=default(None), help=f"where to keep cached pages (default {DEFAULT_CACHE_DIR})"
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chess-results", description=__doc__, parents=[_shared()])
    sub = parser.add_subparsers(dest="command", required=True)

    for name, handler, help_text in (
        ("dump", cmd_dump, "write the whole tournament as JSON"),
        ("standings", cmd_standings, "print the cross-round standings"),
        ("colours", cmd_colours, "print colour and float histories"),
        ("unfinished", cmd_unfinished, "list games without a result"),
    ):
        child = sub.add_parser(name, help=help_text, parents=[_shared(defaults=False)])
        child.add_argument("tournament_id", help="chess-results tournament id, e.g. 1452107")
        if name == "dump":
            child.add_argument("-o", "--output", help="write JSON here instead of stdout")
        child.set_defaults(func=handler)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "output"):
        args.output = None
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
