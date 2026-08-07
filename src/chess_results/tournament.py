"""Assemble per-round pairing tables into per-player tournament histories."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Colour, CrosstableEntry, Pairing, Play, Player, PlayKind, StartingRankEntry


@dataclass
class Tournament:
    """A tournament's players and rounds, keyed by player name.

    chess-results identifies players by name on pairing pages, so names are the
    join key here. Where the tournament publishes starting numbers they are
    carried through and are the correct thing to sort on.
    """

    id: str | None = None
    name: str | None = None
    players: dict[str, Player] = field(default_factory=dict)
    rounds: dict[int, list[Pairing]] = field(default_factory=dict)

    @property
    def last_round(self) -> int:
        return max(self.rounds, default=0)

    def player(self, name: str) -> Player:
        if name not in self.players:
            self.players[name] = Player(name=name)
        return self.players[name]

    def add_starting_rank(self, entries: list[StartingRankEntry]) -> None:
        for e in entries:
            p = self.player(e.name)
            p.start_no = e.start_no
            p.rating = p.rating or e.rating
            p.title = p.title or e.title
            p.federation = e.federation
            p.fide_id = e.fide_id

    def add_round(self, pairings: list[Pairing]) -> None:
        if not pairings:
            return
        rnd = pairings[0].round
        self.rounds[rnd] = pairings
        for pr in pairings:
            white = self.player(pr.white.name)
            white.rating = white.rating or pr.white.rating
            white.title = white.title or pr.white.title
            white.fixed_board = white.fixed_board or pr.white.fixed_board
            if white.start_no is None:
                white.start_no = pr.white.start_no

            if pr.kind is not PlayKind.GAME or pr.black is None:
                white.plays.append(
                    Play(
                        round=rnd,
                        kind=pr.kind,
                        score=pr.white_score,
                        points_before=pr.white_points_before,
                        board=pr.board,
                        # A player receiving a bye is treated as a downfloater.
                        float_direction="D" if pr.kind is PlayKind.PAIRING_BYE else None,
                    )
                )
                continue

            black = self.player(pr.black.name)
            black.rating = black.rating or pr.black.rating
            black.title = black.title or pr.black.title
            black.fixed_board = black.fixed_board or pr.black.fixed_board
            if black.start_no is None:
                black.start_no = pr.black.start_no

            w_float, b_float = _floats(pr.white_points_before, pr.black_points_before)
            white.plays.append(
                Play(
                    round=rnd,
                    kind=PlayKind.GAME,
                    colour=Colour.WHITE,
                    opponent=black.name,
                    score=pr.white_score,
                    points_before=pr.white_points_before,
                    board=pr.board,
                    forfeit=pr.forfeit,
                    float_direction=w_float,
                )
            )
            black.plays.append(
                Play(
                    round=rnd,
                    kind=PlayKind.GAME,
                    colour=Colour.BLACK,
                    opponent=white.name,
                    score=pr.black_score,
                    points_before=pr.black_points_before,
                    board=pr.board,
                    forfeit=pr.forfeit,
                    float_direction=b_float,
                )
            )

    def add_crosstable(self, crosstable: dict[int, list[CrosstableEntry]]) -> list[Play]:
        """Restore rounds the pairing pages have dropped, and return what was added.

        A round's pairing page lists byes and unpaired players only while that
        round is the current one. Once a later round is paired those rows are
        removed, so a player who took a full-point bye in round 6 simply has no
        round 6 anywhere on the round pages, and their score comes out a point
        light. The crosstable keeps the whole record, so it is the authority for
        any round a player is missing.

        Only rounds already fetched are filled, and only where the player has
        nothing for that round; results read from the pairing pages are left
        alone, since those carry board numbers and pre-round scores too.
        """
        by_number = {p.start_no: p for p in self.players.values() if p.start_no is not None}
        names = {no: player.name for no, player in by_number.items()}
        added: list[Play] = []

        for start_no, entries in crosstable.items():
            player = by_number.get(start_no)
            if player is None:
                continue
            for entry in entries:
                if entry.round not in self.rounds or player.play(entry.round) is not None:
                    continue
                play = Play(
                    round=entry.round,
                    kind=entry.kind,
                    colour=entry.colour,
                    opponent=names.get(entry.opponent_no) if entry.opponent_no else None,
                    score=entry.score,
                    forfeit=entry.forfeit,
                    # A player given a bye is treated as a downfloater, as in add_round.
                    float_direction="D" if entry.kind is PlayKind.PAIRING_BYE else None,
                    from_crosstable=True,
                )
                player.plays.append(play)
                added.append(play)
            player.plays.sort(key=lambda p: p.round)
        return added

    def ranking_order(self, after: int | None = None) -> list[Player]:
        """Players in FIDE ranking order: score descending, then starting number."""
        return sorted(
            self.players.values(),
            key=lambda p: (
                -p.score(after),
                p.start_no if p.start_no is not None else 10**6,
                -(p.rating or 0),
                p.name,
            ),
        )

    def scoregroups(self, after: int | None = None) -> dict[float, list[Player]]:
        """Players grouped by score, highest first, each group in ranking order."""
        groups: dict[float, list[Player]] = {}
        for p in self.ranking_order(after):
            groups.setdefault(p.score(after), []).append(p)
        return dict(sorted(groups.items(), key=lambda kv: -kv[0]))

    def unfinished(self, rnd: int | None = None) -> list[Pairing]:
        """Games with no result yet, for the given round or the latest one."""
        rnd = rnd or self.last_round
        return [p for p in self.rounds.get(rnd, []) if p.kind is PlayKind.GAME and p.white_score is None]


def _floats(white_before: float | None, black_before: float | None) -> tuple[str | None, str | None]:
    if white_before is None or black_before is None or white_before == black_before:
        return None, None
    if white_before > black_before:
        return "D", "U"
    return "U", "D"
