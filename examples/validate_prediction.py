#!/usr/bin/env python3
"""Check a predicted round against the one the arbiter actually published.

Predicts round N from rounds 1..N-1 and diffs the result against the published
round N, comparing as *sets* — a pairing engine emits a set of pairs, not an
ordering, so comparing board by board understates the match badly.

    python validate_prediction.py 1452107 --round 8 \
        --engine ~/repos/other/bbpPairings/bbpPairings.exe

Each round is scored twice: once with no withdrawal information, which is what a
genuine live prediction has to work with, and once with the absent players read
back out of the published round. The second figure uses hindsight and is an upper
bound, not a live result. The gap between the two is the cost of not knowing who
has withdrawn.

Two traps this script exists to avoid, both of which produce plausible but wrong
numbers:

- The field must come from the crosstable-reconciled player histories, never from
  the round's own pairing page. Once a later round is paired, a round page loses
  its bye and "not paired" rows, so deriving the field from it silently
  reclassifies that round's bye recipient as a withdrawal.
- A ``Play`` recovered from the crosstable exists even for a round the player took
  no part in (``PlayKind.UNPAIRED``), so "has a play in round N" is not the same
  as "was paired in round N".
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
    parser.add_argument("--round", type=int, required=True, help="the round to reproduce")
    parser.add_argument("--engine", required=True, help="path to bbpPairings.exe")
    parser.add_argument("--total-rounds", type=int, help="rounds in the tournament (XXR)")
    parser.add_argument("--bye-value", type=float, default=1.0)
    parser.add_argument(
        "--consecutive",
        type=int,
        default=1,
        help="unpaired rounds needed before inferring a withdrawal (default 1)",
    )
    return parser.parse_args(argv)


def field(event, rnd: int) -> set[str]:
    """Who actually occupied round ``rnd``, byes included.

    Taken from the reconciled histories rather than the round page, which may
    have had its bye rows deleted by a later pairing.
    """
    return {
        name
        for name, player in event.players.items()
        if any(p.round == rnd and p.kind is not PlayKind.UNPAIRED for p in player.plays)
    }


def published(event, rnd: int) -> tuple[set[tuple[str, str]], str | None]:
    """The (white, black) pairs and bye recipient as the arbiter published them."""
    pairs: set[tuple[str, str]] = set()
    bye = None
    for player in event.players.values():
        for p in player.plays:
            if p.round == rnd and p.kind is PlayKind.PAIRING_BYE:
                bye = player.name
    for pairing in event.rounds[rnd]:
        if pairing.kind is PlayKind.GAME:
            pairs.add((pairing.white.name, pairing.black.name))
    return pairs, bye


def predict(
    event, after: int, engine: str, total_rounds: int | None, withdrawn: set[str]
) -> tuple[set[tuple[str, str]], str | None]:
    trf = to_trf(event, after=after, total_rounds=total_rounds, withdrawn=withdrawn)
    trf_path = Path(tempfile.mkstemp(suffix=".trf")[1])
    trf_path.write_text(trf)
    out_path = trf_path.with_suffix(".pairings")
    result = subprocess.run(
        [engine, "--dutch", str(trf_path), "-p", str(out_path)],
        capture_output=True,
        text=True,
        check=False,  # the engine's own message beats a traceback
    )
    if result.returncode:
        print(result.stdout + result.stderr, file=sys.stderr)
        raise SystemExit(f"bbpPairings exited {result.returncode}")

    by_no = {p.start_no: p.name for p in event.players.values() if p.start_no}
    pairs: set[tuple[str, str]] = set()
    bye = None
    for line in out_path.read_text().splitlines()[1:]:
        white_no, black_no = (int(x) for x in line.split())
        if black_no:
            pairs.add((by_no[white_no], by_no[black_no]))
        else:
            bye = by_no[white_no]
    return pairs, bye


def report(label, predicted, predicted_bye, actual, actual_bye) -> int:
    exact = predicted & actual
    as_sets_pred = {frozenset(p) for p in predicted}
    as_sets_actual = {frozenset(p) for p in actual}
    both = as_sets_pred & as_sets_actual
    print(f"\n{label}")
    print(f"  boards published        : {len(actual)}")
    print(f"  boards predicted        : {len(predicted)}")
    print(f"  exact (pair and colour) : {len(exact)}")
    print(f"  right pair, wrong colour: {len(both) - len(exact)}")
    print(f"  not predicted at all    : {len(actual) - len(both)}")
    verdict = "match" if actual_bye == predicted_bye else "DIFFER"
    print(f"  bye: published {actual_bye!r}, predicted {predicted_bye!r} — {verdict}")
    for missed in sorted(as_sets_actual - as_sets_pred):
        a, b = sorted(missed)
        print(f"    missed: {a} vs {b}")
    return len(exact)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rnd = args.round
    client = ChessResults(cache=True)

    event = client.tournament(args.tournament_id, bye_value=args.bye_value)
    if rnd not in event.rounds:
        raise SystemExit(f"round {rnd} is not published; rounds are {sorted(event.rounds)}")

    actual, actual_bye = published(event, rnd)
    before = client.tournament(args.tournament_id, rounds=rnd - 1, bye_value=args.bye_value)

    stalled = [p for p in before.rounds[rnd - 1] if p.kind is PlayKind.GAME and p.white_score is None]
    if stalled:
        print(
            f"warning: {len(stalled)} game(s) in round {rnd - 1} have no result; "
            "the engine reads scores as fact",
            file=sys.stderr,
        )

    present = field(event, rnd)
    absent = set(event.players) - present
    print(
        f"{event.name}\n{len(event.players)} players scraped, "
        f"{len(field(before, rnd - 1))} played round {rnd - 1}, {len(present)} in round {rnd}"
    )

    blind = report(
        f"round {rnd} from rounds 1-{rnd - 1}, no withdrawal information:",
        *predict(before, rnd - 1, args.engine, args.total_rounds, set()),
        actual,
        actual_bye,
    )
    if not absent:
        print(f"\nEveryone is still in; {blind}/{len(actual)} exact.")
        return 0

    print(f"\n{len(absent)} player(s) absent from round {rnd}:")
    for name in sorted(absent):
        print(f"    {name}")

    guessed = before.likely_withdrawn(after=rnd - 1, consecutive=args.consecutive)
    print(
        f"\ninferred from rounds 1-{rnd - 1} alone: {len(guessed)} flagged, "
        f"{len(guessed & absent)} correct, {len(guessed - absent)} false, {len(absent - guessed)} missed"
    )
    for name in sorted(guessed - absent):
        print(f"    false alarm: {name} (played round {rnd} after all)")
    for name in sorted(absent - guessed):
        print(f"    missed: {name}")
    inferred = report(
        f"round {rnd} with inferred withdrawals -- no hindsight:",
        *predict(before, rnd - 1, args.engine, args.total_rounds, guessed),
        actual,
        actual_bye,
    )

    informed = report(
        f"round {rnd} with the true withdrawals supplied:",
        *predict(before, rnd - 1, args.engine, args.total_rounds, absent),
        actual,
        actual_bye,
    )
    print(
        f"\n{blind}/{len(actual)} exact blind, {inferred}/{len(actual)} inferred, "
        f"{informed}/{len(actual)} once withdrawals are known. Only the last uses hindsight; "
        "the inferred figure is what a live prediction can actually achieve."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
