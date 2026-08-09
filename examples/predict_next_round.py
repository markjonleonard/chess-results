#!/usr/bin/env python3
"""Predict the next round's pairings for a live chess-results tournament.

Scrapes the tournament, lets you decide any games still in progress, writes a
TRF(x) file and hands it to bbpPairings.

    python predict_next_round.py 1452107 \
        --engine ~/repos/other/bbpPairings/bbpPairings.exe \
        --assume "Mcshane, Luke J=1"

Each --assume names a player in an unfinished game and the score they take
(1, 0.5 or 0); their opponent takes the rest. Every unfinished game must be
decided, because a pairing engine reads scores as fact.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from chess_results import ChessResults
from chess_results.models import PlayKind
from chess_results.trf import to_trf


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("tournament_id")
    parser.add_argument("--engine", required=True, help="path to bbpPairings.exe")
    parser.add_argument(
        "--assume",
        action="append",
        default=[],
        metavar="NAME=SCORE",
        help='decide an unfinished game, e.g. "Mcshane, Luke J=1"',
    )
    parser.add_argument(
        "--withdrawn",
        action="append",
        default=[],
        metavar="NAME",
        help="player who will not be paired next round",
    )
    parser.add_argument(
        "--no-infer-withdrawals",
        action="store_true",
        help="do not add players who look to have left the event (see Tournament.likely_withdrawn)",
    )
    parser.add_argument("--total-rounds", type=int, help="rounds in the tournament (XXR)")
    parser.add_argument("--bye-value", type=float, default=1.0)
    parser.add_argument("--trf", help="keep the generated TRF here")
    return parser.parse_args(argv)


def apply_assumptions(event, assumptions: dict[str, float]) -> None:
    """Fill in results for games still in progress."""
    for pairing in event.rounds[event.last_round]:
        if pairing.kind is not PlayKind.GAME or pairing.white_score is not None:
            continue
        white, black = pairing.white.name, pairing.black.name
        if white in assumptions:
            w = assumptions[white]
        elif black in assumptions:
            w = 1.0 - assumptions[black]
        else:
            raise SystemExit(
                f"round {event.last_round} board {pairing.board} is unfinished: "
                f"{white} vs {black}. Decide it with --assume."
            )
        pairing.white_score, pairing.black_score = w, 1.0 - w
        event.players[white].play(event.last_round).score = w
        event.players[black].play(event.last_round).score = 1.0 - w


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    assumptions = {}
    for item in args.assume:
        name, _, score = item.rpartition("=")
        assumptions[name.strip()] = float(score)

    event = ChessResults().tournament(args.tournament_id, bye_value=args.bye_value)
    print(f"{event.name} — {len(event.players)} players, {event.last_round} rounds scraped", file=sys.stderr)
    apply_assumptions(event, assumptions)

    withdrawn = set(args.withdrawn)
    if not args.no_infer_withdrawals:
        inferred = event.likely_withdrawn() - withdrawn
        if inferred:
            print(
                f"inferring {len(inferred)} withdrawal(s) from unpaired rounds: "
                f"{', '.join(sorted(inferred))}",
                file=sys.stderr,
            )
        withdrawn |= inferred

    trf = to_trf(
        event,
        total_rounds=args.total_rounds,
        withdrawn=withdrawn,
    )
    trf_path = Path(args.trf) if args.trf else Path(tempfile.mkstemp(suffix=".trf")[1])
    trf_path.write_text(trf)

    out_path = trf_path.with_suffix(".pairings")
    result = subprocess.run(
        [args.engine, "--dutch", str(trf_path), "-p", str(out_path)],
        capture_output=True,
        text=True,
        check=False,  # the engine's own message is more useful than a traceback
    )
    if result.returncode:
        print(result.stdout + result.stderr, file=sys.stderr)
        return result.returncode

    by_no = {p.start_no: p for p in event.players.values() if p.start_no}
    lines = out_path.read_text().splitlines()
    print(f"\nround {event.last_round + 1} — {lines[0].strip()} pairings")
    for board, line in enumerate(lines[1:], start=1):
        white_no, black_no = (int(x) for x in line.split())
        white = by_no[white_no]
        black = by_no[black_no].name if black_no else "bye"
        print(f"{board:>3}  {white.name:<32} {white.score():>4}  -  {black}")
    print(
        "\nBoard numbers are this script's, not the arbiter's: a pairing engine "
        "emits a set of pairs, not an ordering.",
        file=sys.stderr,
    )
    for player in event.players.values():
        if player.fixed_board:
            print(f"{player.name} plays on fixed board {player.fixed_board_number}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
