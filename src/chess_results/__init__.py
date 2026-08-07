"""Scrape tournament data from chess-results.com.

>>> from chess_results import ChessResults
>>> event = ChessResults().tournament(1452107)
>>> event.players["Mcshane, Luke J"].colours()
[Colour.BLACK, Colour.WHITE, ...]
"""

from .client import ChessResults
from .models import (
    Colour,
    CrosstableEntry,
    Pairing,
    Play,
    Player,
    PlayerRef,
    PlayKind,
    Preference,
    StartingRankEntry,
)
from .parse import parse_crosstable, parse_pairings, parse_starting_rank
from .tournament import Tournament

__all__ = [
    "ChessResults",
    "Colour",
    "CrosstableEntry",
    "Pairing",
    "Play",
    "PlayKind",
    "Player",
    "PlayerRef",
    "Preference",
    "StartingRankEntry",
    "Tournament",
    "parse_crosstable",
    "parse_pairings",
    "parse_starting_rank",
]

__version__ = "0.1.0"
