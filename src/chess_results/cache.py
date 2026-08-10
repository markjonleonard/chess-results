"""Response caching.

Round pages divide into two kinds. A round that is still being played changes
every few minutes; a round that is finished and has been superseded by a later
one never changes again. Caching both for the same short window means refetching
settled rounds forever, which is the bulk of the traffic when a tool is run
repeatedly against a live tournament.

So this module tracks which rounds have settled, in a small JSON file beside the
cache, and the client uses it to ask for a long lifetime on those pages and a
short one on everything else.

The crosstable needs the same treatment for a different reason. Most of it is
settled history -- the byes and absences that round pages delete once a later
round is paired, which is the only thing we take from it. Its volatile part is
the current round's results, which we never read from it, the round page being
the authority there. So caching it as though the whole page were live meant
refetching a mostly-frozen page every five minutes forever. What actually
matters is that the cached copy covers every round we have assembled, so
:class:`CrosstableCoverage` records how many rounds it covered when it was
fetched, and the client replaces it when that falls behind.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from requests_cache import CachedSession

#: A round still in play, or the most recent one: expect it to change.
LIVE_TTL = 300
#: A finished round with a later round already paired: it will not change again.
SETTLED_TTL = 60 * 60 * 24 * 30
#: The starting rank list is fixed once the tournament begins.
STARTING_RANK_TTL = 60 * 60 * 24

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "chess-results"


def cached_session(directory: str | Path | None = None, **kwargs: Any) -> CachedSession:
    """A ``requests_cache.CachedSession`` writing to ``directory``.

    Raises ImportError with a usable message if requests-cache is missing.

    ``kwargs`` are forwarded verbatim to ``CachedSession``, whose settings are a
    couple of dozen unrelated types, so ``Any`` is as precise as a pass-through
    can be. The import is deferred because requests-cache is optional at runtime.
    """
    try:
        from requests_cache import CachedSession
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError("caching needs requests-cache: pip install requests-cache") from exc

    path = Path(directory or DEFAULT_CACHE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return CachedSession(str(path / "http"), backend="sqlite", **kwargs)


class SettledRounds:
    """Remembers which rounds of which tournaments have finished for good.

    A round counts as settled once every game in it has a result *and* a later
    round has been paired, because chess-results can still amend a result while
    the round is the newest one.
    """

    def __init__(self, directory: str | Path | None = None) -> None:
        self.path = Path(directory or DEFAULT_CACHE_DIR) / "settled.json"
        try:
            self._data: dict[str, list[int]] = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self._data = {}

    def rounds(self, tournament_id: str | int) -> set[int]:
        return set(self._data.get(str(tournament_id), []))

    def is_settled(self, tournament_id: str | int, rnd: int) -> bool:
        return rnd in self.rounds(tournament_id)

    def record(self, tournament_id: str | int, rounds: set[int]) -> None:
        key = str(tournament_id)
        merged = sorted(self.rounds(key) | rounds)
        if merged == self._data.get(key):
            return
        self._data[key] = merged
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=0, sort_keys=True))
        except OSError:  # a cache that cannot be written is not an error
            pass


class CrosstableCoverage:
    """How many rounds the cached crosstable was known to cover, per tournament.

    Kept beside the settled-round record and for the same reason: requests-cache
    fixes a response's expiry when it is written, so a lifetime chosen once
    cannot later be shortened. Knowing what the cached copy covers lets the
    client decide to replace it instead.
    """

    def __init__(self, directory: str | Path | None = None) -> None:
        self.path = Path(directory or DEFAULT_CACHE_DIR) / "crosstable.json"
        try:
            self._data: dict[str, int] = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self._data = {}

    def rounds(self, tournament_id: str | int) -> int:
        """Rounds the cached crosstable covers; 0 when we have never fetched one."""
        value = self._data.get(str(tournament_id), 0)
        return value if isinstance(value, int) else 0

    def record(self, tournament_id: str | int, rounds: int) -> None:
        key = str(tournament_id)
        if self._data.get(key) == rounds:
            return
        self._data[key] = rounds
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=0, sort_keys=True))
        except OSError:  # a cache that cannot be written is not an error
            pass
