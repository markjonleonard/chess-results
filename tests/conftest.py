from pathlib import Path

import pytest

from chess_results.parse import parse_crosstable, parse_pairings, parse_starting_rank
from chess_results.tournament import Tournament

FIXTURES = Path(__file__).parent / "fixtures"

#: The 2026 British Championship, scraped mid-tournament: rounds 1-6 played
#: (six games in round 6 still unfinished at the moment of capture) and round 7
#: paired but not started.
BRITISH_ROUNDS = 7


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


#: Rounds 1-8, every game of which has a result. Round 9 was still being played
#: when the fixtures were captured, so there is no complete-tournament fixture.
#: Rounds 6 and 7 have to come from their `_finished` captures: the plain ones
#: are mid-round snapshots kept deliberately, for the byes they still show.
BRITISH_PLAYED_ROUNDS = 8
_FINISHED = {6: "british2026_champ_r6_finished", 7: "british2026_champ_r7_finished"}


def _british(crosstable: bool, rounds: int = BRITISH_ROUNDS, played_out: bool = False) -> Tournament:
    event = Tournament(id="1452107", name="2026 British Chess Championships: Championship")
    event.add_starting_rank(parse_starting_rank(fixture("british2026_champ_startingrank.html")))
    for rnd in range(1, rounds + 1):
        name = _FINISHED.get(rnd, f"british2026_champ_r{rnd}") if played_out else f"british2026_champ_r{rnd}"
        event.add_round(parse_pairings(fixture(f"{name}.html"), rnd))
    if crosstable:
        name = "british2026_champ_crosstable_final" if played_out else "british2026_champ_crosstable"
        event.add_crosstable(parse_crosstable(fixture(f"{name}.html")))
    return event


@pytest.fixture(scope="session")
def british() -> Tournament:
    """The whole pipeline, crosstable reconciliation included."""
    return _british(crosstable=True)


@pytest.fixture(scope="session")
def british_rounds_only() -> Tournament:
    """Round pages alone, so tests can show what the crosstable adds."""
    return _british(crosstable=False)


@pytest.fixture(scope="session")
def british_played_out() -> Tournament:
    """Rounds 1-8 with every game decided, and the crosstable from the end.

    Distinct from `british`, the same tournament caught mid-event, which is what
    most tests want. Use this one where an unfinished game would get in the way:
    `to_trf` refuses a file with any, so anything asserting on real TRF output
    needs this. It includes the two games decided by default.
    """
    return _british(crosstable=True, rounds=BRITISH_PLAYED_ROUNDS, played_out=True)


@pytest.fixture(scope="session")
def frome_round_one() -> Tournament:
    """A congress section after one round, whose field took twelve half-point byes.

    The only fixture with requested byes. Built from the round page alone: there
    is no starting-rank fixture for Frome, and the crosstable is not a substitute
    -- its name column omits the comma ("Norris Zack" against the round page's
    "Norris, Zack"), so joining the two by name silently doubles the field.
    """
    event = Tournament(id="frome", name="Frome Chess Congress 2026 - Open")
    event.add_round(parse_pairings(fixture("frome2026_open_r1.html"), 1))
    return event
