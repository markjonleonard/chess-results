from pathlib import Path

import pytest

from chess_results.congress import Congress
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
BRITISH_PLAYED_ROUNDS = 8

#: Rounds 6 and 7 were each saved twice, and which capture you want is the whole
#: point of the pair: `_midround` still shows its bye and "not paired" rows,
#: `_finished` is the same round after a later one was paired and those rows were
#: deleted. Neither is "the" round 6 fixture, so neither carries the plain name.
_CAPTURE = {6: "midround", 7: "midround"}
_PLAYED_CAPTURE = {6: "finished", 7: "finished"}


def _round_fixture(rnd: int, played_out: bool) -> str:
    captures = _PLAYED_CAPTURE if played_out else _CAPTURE
    suffix = captures.get(rnd)
    return f"british2026_champ_r{rnd}" + (f"_{suffix}" if suffix else "")


def _british(crosstable: bool, rounds: int = BRITISH_ROUNDS, played_out: bool = False) -> Tournament:
    event = Tournament(id="1452107", name="2026 British Chess Championships: Championship")
    event.add_starting_rank(parse_starting_rank(fixture("british2026_champ_startingrank.html")))
    for rnd in range(1, rounds + 1):
        event.add_round(parse_pairings(fixture(f"{_round_fixture(rnd, played_out)}.html"), rnd))
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


def _frome_section(name: str, fixture_stem: str) -> Tournament:
    event = Tournament(id=fixture_stem, name=f"Frome Chess Congress 2026 - {name}")
    event.add_round(parse_pairings(fixture(f"{fixture_stem}_r1.html"), 1))
    return event


@pytest.fixture(scope="session")
def frome_congress() -> Congress:
    """Two sections of one congress, which is the shape `Congress` exists for.

    Round 1 of the Open and the Standard. Two sections is enough to show
    everything that distinguishes a congress from a tournament -- the section
    tag, the per-section lookup, the merged export -- and Frome is the event
    the rest of the congress fixtures come from.

    Round pages alone, as `frome_round_one` is and for the same reason: Frome
    publishes no starting-rank list this suite has, and its crosstable prints
    names without the comma, so joining the two doubles the field.
    """
    return Congress(
        name="Frome Chess Congress 2026",
        sections={
            "Open": _frome_section("Open", "frome2026_open"),
            "Standard": _frome_section("Standard", "frome2026_standard"),
        },
    )


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
