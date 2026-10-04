"""Scrape tournament data from chess-results.com.

>>> from chess_results import ChessResults
>>> event = ChessResults().tournament(1452107)
>>> event.players["Mcshane, Luke J"].colours()
[Colour.BLACK, Colour.WHITE, ...]
"""

from .client import (
    ChessResults,
    RoundRobinError,
    SearchError,
    TeamTournamentError,
    TournamentError,
    TournamentNotFoundError,
    TournamentNotStartedError,
)
from .congress import Congress
from .models import (
    Absence,
    Colour,
    CrosstableEntry,
    Disagreement,
    Entrants,
    EventSections,
    NotPairedEntry,
    Pairing,
    Play,
    Player,
    PlayerRef,
    PlayKind,
    Preference,
    SearchResult,
    SearchResults,
    Section,
    StartingRankEntry,
)
from .parse import (
    parse_crosstable,
    parse_not_paired,
    parse_pairings,
    parse_published_totals,
    parse_search_results,
    parse_starting_rank,
)
from .sheet import PairingSheet, SheetError, SheetRow, sheet_from_pairs, sheet_from_round
from .tournament import Tournament

__all__ = [
    "Absence",
    "ChessResults",
    "Colour",
    "Congress",
    "CrosstableEntry",
    "Disagreement",
    "Entrants",
    "EventSections",
    "NotPairedEntry",
    "Pairing",
    "PairingSheet",
    "Play",
    "PlayKind",
    "Player",
    "PlayerRef",
    "Preference",
    "RoundRobinError",
    "SearchError",
    "SearchResult",
    "SearchResults",
    "Section",
    "SheetError",
    "SheetRow",
    "StartingRankEntry",
    "TeamTournamentError",
    "Tournament",
    "TournamentError",
    "TournamentNotFoundError",
    "TournamentNotStartedError",
    "parse_crosstable",
    "parse_not_paired",
    "parse_pairings",
    "parse_published_totals",
    "parse_search_results",
    "parse_starting_rank",
    "sheet_from_pairs",
    "sheet_from_round",
]

# The release workflow requires its tag to match this exactly, so the two
# cannot drift: tagging vX.Y.Z with this saying anything else fails the build
# before it can upload. Rehearsals on TestPyPI use a throwaway .devN, since a
# version uploads once and deleting it does not free the filename.
__version__ = "0.2.0"
