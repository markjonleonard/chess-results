"""Scrape tournament data from chess-results.com.

>>> from chess_results import ChessResults
>>> event = ChessResults().tournament(1452107)
>>> event.players["Mcshane, Luke J"].colours()
[Colour.BLACK, Colour.WHITE, ...]
"""

from .client import (
    ChessResults,
    RoundRobinError,
    TeamTournamentError,
    TournamentError,
    TournamentNotStartedError,
)
from .congress import Congress
from .models import (
    Absence,
    Colour,
    CrosstableEntry,
    Disagreement,
    NotPairedEntry,
    Pairing,
    Play,
    Player,
    PlayerRef,
    PlayKind,
    Preference,
    StartingRankEntry,
)
from .parse import (
    parse_crosstable,
    parse_not_paired,
    parse_pairings,
    parse_published_totals,
    parse_starting_rank,
)
from .tournament import Tournament

__all__ = [
    "Absence",
    "ChessResults",
    "Colour",
    "Congress",
    "CrosstableEntry",
    "Disagreement",
    "NotPairedEntry",
    "Pairing",
    "Play",
    "PlayKind",
    "Player",
    "PlayerRef",
    "Preference",
    "RoundRobinError",
    "StartingRankEntry",
    "TeamTournamentError",
    "Tournament",
    "TournamentError",
    "TournamentNotStartedError",
    "parse_crosstable",
    "parse_not_paired",
    "parse_pairings",
    "parse_published_totals",
    "parse_starting_rank",
]

# The release workflow requires its tag to match this exactly, so the two
# cannot drift: tagging v0.1.0 with this saying anything else fails the build
# before it can upload. Rehearsals on TestPyPI use a throwaway .devN, since a
# version uploads once and deleting it does not free the filename.
__version__ = "0.1.0"
