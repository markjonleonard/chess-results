"""Working out which tournaments are sections of one event.

chess-results has no such thing as an event. A congress that runs an Open, a
Major and a Minor publishes three unrelated tournament numbers, and nothing on
the site links them -- see :mod:`chess_results.congress`, whose grouping has to
come from the caller. What the search *does* publish for every tournament is who
organised it and when, and sections of one congress agree on both. That is all
this goes on, so it is an inference and a good one, not a fact:

- **Same organiser, same start and end date.** A congress whose Open runs a day
  longer than its weekend sections is therefore missed, and an organiser who
  runs two unrelated events over the same dates would be merged. Neither has
  turned up in the congresses this was written against; both are possible.
- **No organiser is not a wildcard.** An empty organiser would match every
  tournament of the day, so the director stands in, and failing that the first
  two words of the name -- the least reliable of the three, used last.

Everything here is pure: the search itself is the client's business.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TypedDict

from .models import EventSections, SearchResult, Section

#: Leading and trailing punctuation is not part of a word: "Congress:" is "congress".
_EDGE = re.compile(r"^\W+|\W+$")

#: Words of a name to compare when nothing but the name is left to go on.
_NAME_PREFIX_WORDS = 2


def _words(name: str) -> list[tuple[str, str]]:
    """``(comparison key, word as written)`` for each word that has any letters or digits.

    ``"-"`` and ``"@"`` are punctuation standing alone and drop out, which is
    what lets "@MK4" and "@ MK4" be the same word.
    """
    out = []
    for raw in name.split():
        word = _EDGE.sub("", raw)
        if word:
            out.append((word.casefold(), word))
    return out


def _clean(text: str | None) -> str:
    return " ".join((text or "").split()).casefold()


def is_sibling(target: SearchResult, other: SearchResult) -> bool:
    """Whether ``other`` looks like a section of the same event as ``target``."""
    if (target.start_date, target.end_date) != (other.start_date, other.end_date):
        return False
    if target.start_date is None:
        return False  # no dates, so nothing to say the two overlap at all
    for field in ("organizer", "director"):
        mine = _clean(getattr(target, field))
        if mine:
            return mine == _clean(getattr(other, field))
    mine_words = [k for k, _ in _words(target.name)[:_NAME_PREFIX_WORDS]]
    return bool(mine_words) and mine_words == [k for k, _ in _words(other.name)[:_NAME_PREFIX_WORDS]]


class SiblingQuery(TypedDict, total=False):
    """The one criterion of :meth:`ChessResults.search` that finds siblings."""

    organizer: str
    director: str
    name: str


def sibling_query(target: SearchResult) -> SiblingQuery:
    """The search that would find ``target``'s siblings, mirroring :func:`is_sibling`.

    Narrow on purpose: the same one organiser on the day the event ended. The
    site's own match is a substring, so the result is still filtered with
    :func:`is_sibling` afterwards.
    """
    organizer, director = (
        " ".join((target.organizer or "").split()),
        " ".join((target.director or "").split()),
    )
    if organizer:
        return {"organizer": organizer}
    if director:
        return {"director": director}
    return {"name": " ".join(w for _, w in _words(target.name)[:_NAME_PREFIX_WORDS])}


def section_labels(names: list[str]) -> list[str]:
    """What tells each name from the others: the words not common to every one.

    "Derbyshire Congress Open" and "Derbyshire Congress Minor" give "Open" and
    "Minor". A name with nothing of its own left, or one that comes out the same
    as another's, keeps its full name instead -- a label that is empty or
    ambiguous is worse than a long one.
    """
    if len(names) == 1:
        return list(names)
    parsed = [_words(n) for n in names]
    common = set.intersection(*({k for k, _ in words} for words in parsed))
    labels = [" ".join(w for k, w in words if k not in common) for words in parsed]
    ambiguous = {label for label in labels if labels.count(label) > 1}
    return [
        name if not label or label in ambiguous else label for label, name in zip(labels, names, strict=True)
    ]


def event_name(names: list[str]) -> str:
    """The words every name starts with: "Derbyshire Congress" for its five sections."""
    parsed = [_words(n) for n in names]
    shared: list[str] = []
    for column in zip(*parsed, strict=False):
        if len({key for key, _ in column}) != 1:
            break
        shared.append(column[0][1])
    return " ".join(shared)


def group_sections(target: SearchResult, candidates: Iterable[SearchResult]) -> EventSections:
    """The sections of ``target``'s event, ``target`` included, by tournament number.

    Ordered by number, which is the order the organiser created them in and so
    usually the order they would print them: Open first.
    """
    found = {c.id: c for c in candidates if is_sibling(target, c)}
    found[target.id] = target
    ordered = [found[k] for k in sorted(found, key=int)]
    names = [r.name for r in ordered]
    labels = section_labels(names)
    return EventSections(
        name=event_name(names) or target.name,
        sections=[Section(label=label, result=r) for label, r in zip(labels, ordered, strict=True)],
    )
