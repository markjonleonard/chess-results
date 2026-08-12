"""Assemble per-round pairing tables into per-player tournament histories."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .models import (
    Absence,
    Colour,
    CrosstableEntry,
    Disagreement,
    NotPairedEntry,
    Pairing,
    Play,
    Player,
    PlayKind,
    StartingRankEntry,
)


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
    #: What a pairing-allocated bye is worth here. FIDE-rated Swisses award a
    #: full point; some congresses award a half. The crosstable always prints a
    #: PAB as 1, so a round recovered from it has to be rescored by this.
    bye_value: float = 1.0
    #: Where a round page and the crosstable contradicted each other. Filled by
    #: :meth:`add_crosstable`; empty on every fixture in the suite.
    disagreements: list[Disagreement] = field(default_factory=list)

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

        Where both views do have the round, they are compared and any
        contradiction is recorded in :attr:`disagreements`. The two come from the
        same upload and agree on every fixture in the suite, so a disagreement
        means one of the two parsers has misread something.
        """
        by_number = {p.start_no: p for p in self.players.values() if p.start_no is not None}
        names = {no: player.name for no, player in by_number.items()}
        added: list[Play] = []

        for start_no, entries in crosstable.items():
            player = by_number.get(start_no)
            if player is None:
                continue
            for entry in entries:
                if entry.round not in self.rounds:
                    continue
                existing = player.play(entry.round)
                if existing is not None:
                    self.disagreements.extend(_compare(player.name, existing, entry, names))
                    continue
                play = Play(
                    round=entry.round,
                    kind=entry.kind,
                    colour=entry.colour,
                    opponent=names.get(entry.opponent_no) if entry.opponent_no else None,
                    # The crosstable prints every pairing-allocated bye as a full
                    # point, whatever the tournament actually awards for one.
                    score=self.bye_value if entry.kind is PlayKind.PAIRING_BYE else entry.score,
                    forfeit=entry.forfeit,
                    # A player given a bye is treated as a downfloater, as in add_round.
                    float_direction="D" if entry.kind is PlayKind.PAIRING_BYE else None,
                    from_crosstable=True,
                )
                player.plays.append(play)
                added.append(play)
            player.plays.sort(key=lambda p: p.round)
        return added

    def check_published_totals(
        self,
        crosstable: dict[int, list[CrosstableEntry]],
        totals: dict[int, float],
    ) -> list[Disagreement]:
        """Check our reading of the crosstable against the total it publishes.

        The ``TB1`` column is the arbiter's own arithmetic, so the round-by-round
        cells we parsed out of the same row must sum to it. That makes this the
        strongest check available on the scoring: every other one compares two of
        our own parsers against each other.

        It deliberately compares the crosstable against *itself* rather than
        against the assembled history. A player's assembled score is only
        comparable to a published total when both cover exactly the same rounds,
        and they routinely do not -- the crosstable is often the fresher capture,
        and it may run to rounds we have not fetched. Comparing those produced 75
        false alarms on the mid-event fixture alone.

        Published scores are used as printed: a pairing-allocated bye counts 1
        here whatever :attr:`bye_value` says, that being the crosstable's own
        convention.
        """
        names = {p.start_no: name for name, p in self.players.items() if p.start_no is not None}
        found: list[Disagreement] = []
        for start_no, published in totals.items():
            entries = crosstable.get(start_no)
            if entries is None:
                continue
            ours = sum(e.score for e in entries if e.score is not None)
            if abs(ours - published) > 1e-9:
                found.append(
                    Disagreement(
                        player=names.get(start_no, f"#{start_no}"),
                        round=0,  # a total belongs to no single round
                        field="total",
                        from_round_page=ours,
                        from_crosstable=published,
                    )
                )
        self.disagreements.extend(found)
        return found

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

    def rows(self) -> list[dict[str, object]]:
        """The whole event as flat records, one per player per round.

        A shape for handing to a DataFrame, a CSV writer or ``json.dump``,
        where the assembled :class:`Player` objects are awkward and the nested
        ``dataclasses.asdict`` output more awkward still. Rounds sort first,
        then boards, with byes and recovered rounds last within a round --
        those carry no board number.

        Two things to know before summing anything here.

        ``score`` is what the library holds, which scores an ``UNPAIRED`` round
        0. That is not the same as a round drawn nil, and for most purposes a
        round the player was neither paired for nor awarded anything wants to
        read as "no result" rather than as zero -- otherwise a player who
        withdrew after round 2 looks present, and beaten, in every round after
        it. The distinction is left to the caller because both readings are
        wanted in practice: pair ``score`` with ``kind`` and decide.

        ``rating`` is the rating the player was paired on, estimates included,
        and ``None`` where the event published no rating column at all.
        """
        return sorted(
            (
                {
                    "round": play.round,
                    "board": play.board,
                    "name": player.name,
                    "start_no": player.start_no,
                    "fide_id": player.fide_id,
                    "federation": player.federation,
                    "title": player.title,
                    "rating": player.rating,
                    "opponent": play.opponent,
                    "colour": play.colour.value if play.colour else None,
                    "score": play.score,
                    "kind": play.kind.value,
                    "forfeit": play.forfeit,
                    "points_before": play.points_before,
                    "float_direction": play.float_direction,
                    "from_crosstable": play.from_crosstable,
                }
                for player in self.players.values()
                for play in player.plays
            ),
            key=_row_order,
        )

    def games(self, rnd: int | None = None) -> list[Pairing]:
        """The actual games of a round: byes and "not paired" rows are not games."""
        rnd = rnd or self.last_round
        return [p for p in self.rounds.get(rnd, []) if p.kind is PlayKind.GAME]

    def unfinished(self, rnd: int | None = None) -> list[Pairing]:
        """Games with no result yet, for the given round or the latest one."""
        return [p for p in self.games(rnd) if p.white_score is None]

    def _unoccupied_rounds(self, entries: Iterable[NotPairedEntry], after: int) -> dict[str, set[int]]:
        """Rounds each player did not occupy, per the "not paired" page.

        Joined through the starting number where the tournament publishes one,
        as the crosstable is, and by name otherwise. Rounds after ``after`` are
        dropped: that page is always current, so using a later capture of it to
        reason about an earlier round would be reading the future.
        """
        by_no = {p.start_no: name for name, p in self.players.items() if p.start_no}
        unoccupied: dict[str, set[int]] = {}
        for entry in entries:
            name = by_no.get(entry.start_no, entry.name)
            if name in self.players:
                unoccupied[name] = {r for r in entry.rounds(Absence.UNPLAYED) if r <= after}
        return unoccupied

    def likely_withdrawn(
        self,
        after: int | None = None,
        consecutive: int = 1,
        not_paired: Iterable[NotPairedEntry] | None = None,
    ) -> set[str]:
        """Players who look to have left the event, for ``to_trf(withdrawn=...)``.

        Withdrawals are the entire error term in pairing prediction: given the
        right field bbpPairings reproduces a round exactly, and every miss without
        it is a player who had stopped playing. chess-results never says who has
        withdrawn, and the round pages delete their "not paired" rows as soon as a
        later round is paired -- so this reads the crosstable-reconciled histories
        instead, where the record survives.

        A player is flagged when their last ``consecutive`` rounds are all
        ``UNPAIRED``, or when they never occupied a round at all (an entrant who
        never turned up). A *requested* bye is deliberately not a signal: a player
        sitting out one round on a half point is still in the tournament.

        This is a heuristic and cannot be otherwise. A player who withdraws after
        the last round we can see leaves no trace to find -- three of the eight
        absent from round 9 of the 2026 British played round 8 -- and one who is
        unpaired for a round and returns is a false positive. ``consecutive=1``
        measured best on rounds 7-9 of that event: 12 of 18 found, 1 false alarm.
        Raising it trades recall for precision.

        ``not_paired`` supplies the "not paired" page (``art=40``) as a second
        source of absences, for a history that has no crosstable behind it. It
        is one request against one page where the crosstable is a whole table to
        mine, and on round pages alone it is the difference between finding the
        withdrawals and finding nobody. It buys nothing on a crosstable-reconciled
        history, which already holds everything it says.

        It carries one hazard, and it is exactly the distinction this method
        cares about: ``art=40`` prints ``*`` for a requested half-point bye as
        well as for a real absence. The marker is therefore consulted *only* for
        a round the player has no play for at all -- wherever a round page or the
        crosstable has said anything, that wins. So the hazard needs all three of
        a half-point bye, a round page that has since dropped the row, and no
        crosstable: Frome's twelve round 1 half-point byes produce no false alarm
        at all, because their round page still lists them. Reconcile against the
        crosstable for an event that awards half-point byes and the question does
        not arise, since it keeps ``-½`` apart from ``-0``.
        """
        after = after if after is not None else self.last_round
        if after < 1:
            return set()
        window = range(max(1, after - consecutive + 1), after + 1)
        unoccupied = self._unoccupied_rounds(not_paired, after) if not_paired is not None else {}
        withdrawn = set()
        for name, player in self.players.items():
            missed = unoccupied.get(name, set())

            def absent(rnd: int, play: Play | None, missed: set[int] = missed) -> bool:
                # A round with no play at all is only evidence when art=40 says so;
                # on round pages alone it usually means the row has been deleted.
                return play.kind is PlayKind.UNPAIRED if play is not None else rnd in missed

            plays = [(rnd, player.play(rnd)) for rnd in window]
            # The two signals the docstring describes, named so they stay distinguishable.
            trailing_unpaired = all(absent(rnd, p) for rnd, p in plays)
            never_played = not any(p.kind is not PlayKind.UNPAIRED for p in player.plays)
            if trailing_unpaired or never_played:
                withdrawn.add(name)
        return withdrawn


def _row_order(row: dict[str, object]) -> tuple[object, ...]:
    """Round, then board, then name -- with the boardless rounds last.

    A bye and a round recovered from the crosstable both have ``board`` None,
    which no comparison against an int survives, so the sort key carries an
    explicit "has no board" flag ahead of the number itself.
    """
    board = row["board"]
    return (row["round"], board is None, board if isinstance(board, int) else 0, row["name"])


def _compare(
    name: str,
    play: Play,
    entry: CrosstableEntry,
    names: dict[int, str],
) -> list[Disagreement]:
    """Fields on which a round page and the crosstable contradict each other.

    Only where *both* have something to say. One view holding a value the other
    lacks is not a contradiction: the crosstable is often the fresher capture,
    and a round page carries no result at all until the game finishes.
    """
    opponent = names.get(entry.opponent_no) if entry.opponent_no else None
    pairs: list[tuple[str, object, object]] = [
        ("kind", play.kind, entry.kind),
        ("colour", play.colour, entry.colour),
        ("opponent", play.opponent, opponent),
        # Not the bye: the crosstable prints a pairing-allocated bye as a full
        # point even where the tournament awards a half, which is a difference of
        # convention, not a contradiction.
        *([] if play.kind is PlayKind.PAIRING_BYE else [("score", play.score, entry.score)]),
        # Booleans are never absent, so these always compare.
        ("forfeit", play.forfeit, entry.forfeit),
    ]
    return [
        Disagreement(player=name, round=play.round, field=field_name, from_round_page=a, from_crosstable=b)
        for field_name, a, b in pairs
        if a is not None and b is not None and a != b
    ]


def _floats(white_before: float | None, black_before: float | None) -> tuple[str | None, str | None]:
    if white_before is None or black_before is None or white_before == black_before:
        return None, None
    if white_before > black_before:
        return "D", "U"
    return "U", "D"
