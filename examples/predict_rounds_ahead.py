#!/usr/bin/env python3
"""Predict several rounds ahead by assuming the stronger player always wins.

Any game chess-results has not yet decided -- one still in progress in the
last scraped round, and every round beyond it -- is filled in by rating: the
higher-rated player wins, equal ratings draw, and a bye scores the
tournament's bye value. Each simulated round is paired for real by
bbpPairings before the next one is decided, so predictions compound the same
way an arbiter's actual field would, including the colour and floating rules.

    python predict_rounds_ahead.py 1489496 \
        --engine ~/repos/other/bbpPairings/bbpPairings.exe \
        --initial-color white1 \
        --rounds 3

Predicting from an unstarted tournament needs --initial-color, exactly as
predict_next_round.py does and for the same reason: bbpPairings cannot choose
round 1's colours on its own when there is no colour history yet to infer
them from.

This is a "what if" tool, not a live-prediction one: unlike
predict_next_round.py it does not try to infer real withdrawals, because a
field that exists only in simulation has none to infer. Running it against a
tournament already in progress decides the current round by rating rather
than asking --assume, on the same "stronger wins" premise as the rest of it.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from chess_results import ChessResults, TournamentNotStartedError
from chess_results.cache import STARTING_RANK_TTL
from chess_results.client import ART_STARTING_RANK
from chess_results.models import Pairing, PlayerRef, PlayKind
from chess_results.parse import parse_starting_rank, parse_tournament_name
from chess_results.sheet import render, sheet_from_round
from chess_results.tournament import Tournament
from chess_results.trf import to_trf


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("tournament_id")
    parser.add_argument("--engine", required=True, help="path to bbpPairings.exe")
    parser.add_argument("--rounds", type=int, default=1, help="how many rounds ahead to predict")
    parser.add_argument(
        "--initial-color",
        choices=["white1", "black1"],
        help="who gets white in round 1 (required when the tournament has not "
        "started; ignored otherwise, since a later round already has colours "
        "to infer from)",
    )
    parser.add_argument("--total-rounds", type=int, help="rounds in the tournament (XXR)")
    parser.add_argument("--bye-value", type=float, default=1.0)
    parser.add_argument("--trf", help="keep the final round's generated TRF here")
    parser.add_argument(
        "--sheet",
        nargs="?",
        const="-",
        metavar="FILE",
        help="also write a printable pairing sheet for the last predicted round ('-' or no value for stdout)",
    )
    parser.add_argument("--subtitle", metavar="TEXT", help="a line under the sheet's heading")
    return parser.parse_args(argv)


BBPPAIRINGS = "https://github.com/BieremaBoyzProgramming/bbpPairings"


def check_engine(path: str) -> None:
    """Fail before scraping if the engine is not where --engine says it is."""
    engine = Path(path).expanduser()
    if engine.is_file() and os.access(engine, os.X_OK):
        return
    if engine.is_dir():
        reason = "is a directory, not the executable inside it"
    elif engine.is_file():
        reason = "is not executable"
    else:
        reason = "does not exist"
    raise SystemExit(
        f"pairing engine {str(engine)!r} {reason}.\n"
        "\n"
        "This script does not pair; it writes FIDE TRF(x) and hands it to "
        "bbpPairings, which is a separate program you build or download "
        f"yourself:\n    {BBPPAIRINGS}\n"
        "\n"
        "Point --engine at the bbpPairings executable once you have one."
    )


def run_engine(engine: str, trf_text: str, *, keep: str | None = None) -> list[tuple[int, int]]:
    """Hand a TRF(x) file to bbpPairings and return its (white, black) pairs.

    ``black`` is 0 for a bye, matching bbpPairings' own output.
    """
    trf_path = Path(keep) if keep else Path(tempfile.mkstemp(suffix=".trf")[1])
    trf_path.write_text(trf_text)
    out_path = trf_path.with_suffix(".pairings")
    result = subprocess.run(
        [engine, "--dutch", str(trf_path), "-p", str(out_path)],
        capture_output=True,
        text=True,
        check=False,  # the engine's own message is more useful than a traceback
    )
    if result.returncode:
        raise SystemExit(result.stdout + result.stderr)
    lines = out_path.read_text().splitlines()[1:]
    pairs = []
    for line in lines:
        white_no, black_no = (int(x) for x in line.split())
        pairs.append((white_no, black_no))
    return pairs


def result_by_rating(white_rating: int | None, black_rating: int | None) -> tuple[float, float]:
    """The stronger player wins; equal ratings (0/unrated included) draw."""
    white, black = white_rating or 0, black_rating or 0
    if white > black:
        return 1.0, 0.0
    if black > white:
        return 0.0, 1.0
    return 0.5, 0.5


def decide_current_round(event: Tournament) -> None:
    """Fill in every unfinished game in the last scraped round, by rating."""
    for pairing in event.rounds.get(event.last_round, []):
        if pairing.kind is not PlayKind.GAME or pairing.white_score is not None:
            continue
        assert pairing.black is not None, "a GAME pairing always has a black player"
        white = event.players[pairing.white.name]
        black = event.players[pairing.black.name]
        w, b = result_by_rating(white.rating, black.rating)
        pairing.white_score, pairing.black_score = w, b
        white_play = white.play(event.last_round)
        black_play = black.play(event.last_round)
        assert white_play is not None and black_play is not None, "both just played this round"
        white_play.score, black_play.score = w, b


def simulate_next_round(
    event: Tournament, engine: str, total_rounds: int | None, initial_color: str | None
) -> list[Pairing]:
    """Pair the round after ``event.last_round`` and decide it by rating."""
    rnd = event.last_round + 1
    trf = to_trf(event, total_rounds=total_rounds, initial_color=initial_color)
    pairs = run_engine(engine, trf)
    by_no = {p.start_no: p for p in event.players.values() if p.start_no is not None}

    pairings = []
    for board, (white_no, black_no) in enumerate(pairs, start=1):
        white = by_no[white_no]
        white_ref = PlayerRef(white.name, rating=white.rating, start_no=white.start_no)
        if not black_no:
            pairings.append(
                Pairing(
                    round=rnd,
                    board=board,
                    white=white_ref,
                    black=None,
                    kind=PlayKind.PAIRING_BYE,
                    white_score=event.bye_value,
                )
            )
            continue
        black = by_no[black_no]
        black_ref = PlayerRef(black.name, rating=black.rating, start_no=black.start_no)
        w, b = result_by_rating(white.rating, black.rating)
        pairings.append(
            Pairing(
                round=rnd,
                board=board,
                white=white_ref,
                black=black_ref,
                kind=PlayKind.GAME,
                white_score=w,
                black_score=b,
            )
        )
    event.add_round(pairings)
    return pairings


def print_round(rnd: int, pairings: list[Pairing]) -> None:
    print(f"\nround {rnd} (assumed by rating):", file=sys.stderr)
    for pairing in pairings:
        if pairing.black is None:
            print(f"{pairing.board:>3}  {pairing.white.name:<28} bye", file=sys.stderr)
        else:
            score = f"{pairing.white_score:g}-{pairing.black_score:g}"
            line = f"{pairing.board:>3}  {pairing.white.name:<28} {score}  {pairing.black.name}"
            print(line, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # Before the scrape, so a mistyped path costs nothing and asks
    # chess-results for nothing.
    check_engine(args.engine)
    if args.rounds < 1:
        raise SystemExit("--rounds must be at least 1")

    client = ChessResults()
    try:
        event = client.tournament(args.tournament_id, bye_value=args.bye_value)
    except TournamentNotStartedError:
        if args.initial_color is None:
            raise SystemExit(
                f"tournament {args.tournament_id} has no played rounds; predicting "
                "from it needs --initial-color white1|black1, since bbpPairings has "
                "no colour history to infer round 1's colours from"
            ) from None
        html = client.fetch(args.tournament_id, ART_STARTING_RANK, expire_after=STARTING_RANK_TTL)
        event = Tournament(
            id=str(args.tournament_id), name=parse_tournament_name(html), bye_value=args.bye_value
        )
        event.add_starting_rank(parse_starting_rank(html))
    print(f"{event.name} — {len(event.players)} players, {event.last_round} rounds scraped", file=sys.stderr)

    if event.last_round:
        decide_current_round(event)

    for _ in range(args.rounds):
        rnd = event.last_round + 1
        color = args.initial_color if rnd == 1 else None
        pairings = simulate_next_round(event, args.engine, args.total_rounds, color)
        print_round(rnd, pairings)

    target = event.last_round
    print(f"\nround {target} prediction:")
    for pairing in event.rounds[target]:
        black = pairing.black.name if pairing.black is not None else "bye"
        print(f"{pairing.board:>3}  {pairing.white.name:<32} -  {black}")

    if args.trf:
        Path(args.trf).write_text(to_trf(event, total_rounds=args.total_rounds))

    if args.sheet:
        sheet = sheet_from_round(event, target)
        text = render(sheet, subtitle=args.subtitle)
        if args.sheet == "-":
            print(text, end="")
        else:
            Path(args.sheet).write_text(text)
            print(f"wrote {args.sheet}: {sheet.boards} boards", file=sys.stderr)
        for warning in sheet.warnings:
            print(f"warning: {warning}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
