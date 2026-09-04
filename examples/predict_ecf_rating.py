#!/usr/bin/env python3
"""Predict a chess-results.com player's next ECF standard rating.

Bridges two sibling packages that stay deliberately decoupled -- chess_results
reads the event, ecf_rating reads the players and applies the ECF's own
K-method Elo update -- without either gaining a dependency on the other. Needs
both importable, e.g.:

    pip install -e ~/repos/personal/ecf-rating

    python predict_ecf_rating.py 1452107 "Adams, Michael" --ecf-code 100026F

Once the player's own ECF code is known, their *own* submitted-games log
(``ecf.games``) already names every opponent by ECF number -- no per-opponent
name search needed, and no ambiguity to report, for any game the ECF has
already ingested. A round is matched against that log by (opponent name,
score); unmatched rounds -- the ECF has not yet seen them, typically a still-
live event -- fall back to a name search on the opponent, same as before.

A matched round can carry an already-published increment. That means the ECF
has already rated it, which means the player's current baseline rating
*already reflects it* -- confirmed live on the 2nd Swindon Congress Minor
section (tnr1484241), finished 2026-08-31 and fully rated by the 2026-09-01
list. Feeding such a round back into the K-method here would double-count it,
so it is excluded from the prediction and shown separately with the ECF's own
real number instead of a guess.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from ecf_rating import ECF, BudgetExhausted, expected_score, player_no, predict_rating
from ecf_rating.models import Game

from chess_results import ChessResults
from chess_results.cli import _find_player
from chess_results.models import PlayKind


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("tournament_id")
    parser.add_argument(
        "player",
        metavar="<player>",
        help='a chess-results.com name, or part of one, e.g. "Adams, Michael" or just "adams"',
    )
    parser.add_argument("--ecf-code", help="skip the name search; the player's ECF code, e.g. 100026F")
    parser.add_argument(
        "--domain", default="S", help="rating domain: S(tandard), R(apid) or B(litz) (default: S)"
    )
    parser.add_argument(
        "--k", type=int, default=20, help="K-factor (default: 20; the ECF uses 40 for juniors)"
    )
    parser.add_argument(
        "--rating-date",
        metavar="YYYY-MM-DD",
        help="look up ratings as published for this date rather than the most recent (default: today)",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=40,
        metavar="N",
        help="how far back into the player's own submitted-games log to look for this "
        "tournament's rounds (default: 40; raise it for a very active player)",
    )
    return parser.parse_args(argv)


def resolve_ecf_code(ecf: ECF, name: str, fide_id: str | None) -> str | None:
    """The ECF code for ``name``, or None if it can't be resolved with confidence.

    Zero or more than one match is reported and treated as unresolved, never
    guessed at. Only used for the player being predicted, and for an
    opponent's round the player's own submitted-games log has not caught yet.
    """
    found = ecf.search(name, fide_id=fide_id)
    if len(found) == 1:
        return found[0].code
    if not found:
        print(f"warning: no ECF match for {name!r}", file=sys.stderr)
    else:
        options = ", ".join(f"{p.full_name} ({p.code})" for p in found)
        print(f"warning: {name!r} matches more than one ECF player: {options}", file=sys.stderr)
    return None


def _name_key(name: str) -> tuple[str, str]:
    """(surname, first forename word), lower-cased -- enough to match names across sources.

    chess-results and the ECF's own membership record do not always agree on
    how much of a name to print: chess-results published a round as "Collins,
    Jonathan" while that player's own ECF game log has "Collins, Jonathan L"
    (tnr1484240, round 3, 2026-09-03) -- same game, same score, one source
    keeping his middle initial and the other dropping it. Comparing only the
    surname and the first forename word survives that without being so loose
    it would also equate two different people who merely share a surname.
    """
    surname, _, forename = name.partition(",")
    first_word = forename.strip().split()[0] if forename.strip() else ""
    return surname.strip().lower(), first_word.lower()


def match_own_game(own_games: list[Game], used: set[int], opponent_name: str, score: float) -> Game | None:
    """The one game in the player's own log this round is, if there's exactly one candidate.

    Matched by (opponent name, score) -- the two facts chess-results and the
    ECF's submitted result must agree on if they are the same game -- with
    names compared via :func:`_name_key` rather than exact equality, since the
    two sources do not always publish the same amount of a name. More than one
    candidate (the same opponent and score recur within the lookback window)
    is treated as unresolved rather than guessed at; ``used`` stops the same
    submitted game being claimed twice.
    """
    wanted = _name_key(opponent_name)
    candidates = [
        i
        for i, g in enumerate(own_games)
        if i not in used
        and g.opponent_name is not None
        and _name_key(g.opponent_name) == wanted
        and g.score == score
    ]
    if len(candidates) != 1:
        return None
    used.add(candidates[0])
    return own_games[candidates[0]]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rating_date = date.fromisoformat(args.rating_date) if args.rating_date else None

    event = ChessResults().tournament(args.tournament_id)
    matches = _find_player(event, args.player)
    if len(matches) != 1:
        if matches:
            names = ", ".join(sorted(p.name for p in matches))
            print(
                f"predict_ecf_rating: {args.player!r} matches more than one player: {names}",
                file=sys.stderr,
            )
        else:
            print(f"predict_ecf_rating: no player matching {args.player!r} in {event.name}", file=sys.stderr)
        return 2
    player = matches[0]

    ecf = ECF()
    try:
        code = args.ecf_code or resolve_ecf_code(ecf, player.name, player.fide_id)
        if code is None:
            print(
                f"predict_ecf_rating: no confident ECF match for {player.name!r}; pass --ecf-code",
                file=sys.stderr,
            )
            return 2

        baseline = ecf.last_known_rating(code, domain=args.domain, before=rating_date)
        if baseline is None or baseline.original is None:
            print(f"predict_ecf_rating: no {args.domain} rating found for ECF {code}", file=sys.stderr)
            return 2
        if baseline.category == "P":
            print(
                f"predict_ecf_rating: {player.name} is Category P (provisional) -- "
                "not computed by the K-method",
                file=sys.stderr,
            )
            return 1

        print(
            f"{player.name} -- ECF {code}, {args.domain} rating {baseline.original} "
            f"({baseline.category or '?'}) as of {baseline.effective_date}"
        )

        own_games = ecf.games(code, domain=args.domain, limit=args.history_limit)
        used: set[int] = set()

        games: list[tuple[int, float]] = []
        already_rated: list[tuple[int, str, float]] = []
        for play in player.plays:
            if play.kind is not PlayKind.GAME or play.opponent is None or play.forfeit or play.score is None:
                continue

            matched = match_own_game(own_games, used, play.opponent, play.score)
            if matched is not None and matched.opponent_rating is not None:
                opponent_rating = matched.opponent_rating
                source = "submitted"
            else:
                opponent = event.players.get(play.opponent)
                opponent_code = resolve_ecf_code(ecf, play.opponent, opponent.fide_id if opponent else None)
                if opponent_code is None:
                    print(
                        f"warning: skipping round {play.round} vs {play.opponent!r} -- opponent not resolved"
                    )
                    continue
                found_rating = ecf.last_known_rating(opponent_code, domain=args.domain, before=rating_date)
                if found_rating is None or found_rating.original is None:
                    print(
                        f"warning: skipping round {play.round} vs {play.opponent!r} -- "
                        f"no {args.domain} rating found"
                    )
                    continue
                opponent_rating = found_rating.original
                source = "search"

            if matched is not None and matched.rating_change is not None:
                already_rated.append((play.round, play.opponent, matched.rating_change))
                print(
                    f"  rd {play.round:>2}  {play.opponent:<32} {opponent_rating:>4}  "
                    f"{play.score:>4}  {matched.rating_change:>+6.2f}  (rated)"
                )
                continue

            games.append((opponent_rating, play.score))
            increment = args.k * (play.score - expected_score(baseline.original - opponent_rating))
            print(
                f"  rd {play.round:>2}  {play.opponent:<32} {opponent_rating:>4}  "
                f"{play.score:>4}  {increment:>+6.2f}  ({source})"
            )

        predicted = predict_rating(baseline.original, games, k=args.k, category=baseline.category)
    except BudgetExhausted as exc:
        print(f"predict_ecf_rating: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"predict_ecf_rating: {exc}", file=sys.stderr)
        return 1

    if already_rated:
        already_total = sum(change for _, _, change in already_rated)
        # The baseline above is the *current* published rating, not the rating
        # before this tournament -- it already has these games folded in.
        # Backing the published changes back out recovers the true "before".
        pre_tournament = round(baseline.original - already_total)
        print(
            f"\n{len(already_rated)} of {len(already_rated) + len(games)} game(s) are already ECF-rated "
            f"(published change {already_total:+.2f}): {player.name} was {pre_tournament} before this "
            f"tournament, and the baseline above ({baseline.original}) already reflects it."
        )
        if baseline.effective_date is not None:
            audit_year, audit_month = baseline.effective_date.year, baseline.effective_date.month - 1
            if audit_month == 0:
                audit_year, audit_month = audit_year - 1, 12
            print(
                "Cross-check the already-rated games against the ECF's own working: "
                f"https://rating.englishchess.org.uk/robo_audit?player_no={player_no(code)}"
                f"&year={audit_year}&month={audit_month}&domain={args.domain}"
            )
    print(f"\n{predicted.games_counted} unrated game(s) counted, change {predicted.change:+.2f}")
    print(f"predicted next {args.domain} rating: {predicted.new_rating} (current: {baseline.original})")
    if predicted.games_counted == 0 and already_rated:
        print("(nothing left to predict -- this tournament is already fully ECF-rated)")
    print(
        "\nThis covers only this tournament's games; any other games the player "
        "has in the same rating period are not reflected here.",
        file=sys.stderr,
    )

    if ecf.client.budget is not None:
        budget = ecf.client.budget
        print(
            f"ECF daily processing budget used: {budget.used_ms:.0f}ms / {budget.limit_ms:.0f}ms",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
