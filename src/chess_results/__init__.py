"""Scrape tournament data from chess-results.com.

>>> from chess_results import ChessResults
>>> event = ChessResults().tournament(1452107)
>>> event.players["Mcshane, Luke J"].colours()
[Colour.BLACK, Colour.WHITE, ...]
"""

from .client import ChessResults
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
    "CrosstableEntry",
    "Disagreement",
    "NotPairedEntry",
    "Pairing",
    "Play",
    "PlayKind",
    "Player",
    "PlayerRef",
    "Preference",
    "StartingRankEntry",
    "Tournament",
    "parse_crosstable",
    "parse_not_paired",
    "parse_pairings",
    "parse_published_totals",
    "parse_starting_rank",
]

__version__ = "0.1.0"
