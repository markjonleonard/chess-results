"""Several tournaments that are really one event.

A UK congress runs as five or six graded sections over the same weekend, in the
same hall, under one set of prize rules -- and chess-results gives each of them
its own tournament number, with nothing on the site tying them together. There
is no congress page, no parent identifier, no link between the sections. The
grouping exists in the entry form and the prize list and nowhere in the data.

So the grouping has to come from the caller, which is what separates this from
everything else in the library: :class:`Congress` is the one type not read off
a page. What it saves is the loop and the section tag that every congress user
would otherwise write, plus the lookups that only make sense once the sections
are held together -- which section a player is in, and one flat export across
all of them.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

from .models import Disagreement, Player
from .tournament import Tournament


@dataclass
class Congress:
    """Sections that form one event, keyed by the name the caller gave them.

    Section names are the caller's own -- "Open", "Major", "U1750" -- because
    the site does not publish them. They are the key everywhere here, and they
    are what tags a row in :meth:`rows`.

    Deliberately *not* offered: a merged ``players`` dict across sections. The
    library keys players by name, so merging would silently drop one of two
    players sharing a name in different sections -- no error, and nothing left
    behind to detect it by.

    That is insurance against a rare event rather than a common one, and it is
    worth being accurate about which. Measured on Frome 2026, 191 players over
    five sections: *no* name appears twice. Ten surnames span sections,
    including four that look like families -- Archer-Lock, Kilambi, Stalidis,
    Walker -- and every one has a distinct first name. Names here are
    "Surname, Firstname", so relatives are the case that does **not** collide.
    What would is two unrelated people with the same full name, and the reason
    to guard it is only that merging five sections multiplies the field the
    coincidence has to miss. :meth:`find` returns every match with its section,
    which costs nothing when there is one.
    """

    name: str | None = None
    sections: dict[str, Tournament] = field(default_factory=dict)
    #: Sections asked for that could not be read, and why. Only ever filled
    #: when the fetch was told to skip them; otherwise the error is raised.
    #: A congress whose top section is an all-play-all is the usual cause.
    unreadable: dict[str, Exception] = field(default_factory=dict)

    def __getitem__(self, section: str) -> Tournament:
        return self.sections[section]

    def __contains__(self, section: str) -> bool:
        return section in self.sections

    def __iter__(self) -> Iterator[str]:
        return iter(self.sections)

    def __len__(self) -> int:
        return len(self.sections)

    def items(self) -> Iterator[tuple[str, Tournament]]:
        return iter(self.sections.items())

    @property
    def last_round(self) -> int:
        """The furthest round any section has reached.

        Sections of one congress usually run the same schedule, but not always
        -- a Minor may play five rounds over a weekend that the Open plays in
        six -- so this is a maximum rather than a shared fact.
        """
        return max((event.last_round for event in self.sections.values()), default=0)

    @property
    def player_count(self) -> int:
        """Entries across the whole congress.

        Entries rather than people: someone playing two sections, which a few
        congresses allow, counts twice. Named to avoid reading as a ``players``
        collection, which this deliberately does not offer.
        """
        return sum(len(event.players) for event in self.sections.values())

    @property
    def disagreements(self) -> list[Disagreement]:
        """Every section's contradictions, in section order.

        Same meaning as :attr:`Tournament.disagreements` -- a round page and the
        crosstable saying different things, which has never yet happened on real
        data and means a parser bug when it does.
        """
        return [d for event in self.sections.values() for d in event.disagreements]

    def find(self, name: str) -> dict[str, Player]:
        """Sections in which a player of this name appears, to their record.

        Usually one entry, and empty when nobody of that name played. It
        returns a mapping rather than a single player because a congress is
        precisely where one name can be two people -- a father and son entering
        different sections is an ordinary weekend -- and picking one of them
        silently is the failure this is shaped to avoid.
        """
        return {
            section: event.players[name] for section, event in self.sections.items() if name in event.players
        }

    def section_of(self, name: str) -> str | None:
        """The one section a player is in, or None if they are in none or several.

        A convenience over :meth:`find` for the common case. None covers both
        "did not play" and "played twice" on purpose: either way there is no
        single answer, and a caller that cares about the difference should ask
        :meth:`find` and look at what came back.
        """
        found = self.find(name)
        return next(iter(found)) if len(found) == 1 else None

    def rows(self) -> list[dict[str, object]]:
        """The whole congress flat, one record per player per round, section-tagged.

        :meth:`Tournament.rows` with a ``section`` key added and the sections
        merged. The sort puts a round together across all sections rather than
        finishing one section before starting the next, so the file reads the
        way the weekend ran: round, then section, then board.

        The caveats on :meth:`Tournament.rows` about ``score`` and ``rating``
        apply here unchanged.
        """
        rows = []
        for section, event in self.sections.items():
            for row in event.rows():
                rows.append({**row, "section": section})
        return sorted(
            rows,
            key=lambda r: (
                r["round"],
                str(r["section"]),
                r["board"] is None,
                r["board"] if isinstance(r["board"], int) else 0,
                str(r["name"]),
            ),
        )


def build(sections: Mapping[str, Tournament], name: str | None = None) -> Congress:
    """A congress from tournaments already in hand.

    For assembling one offline, from saved pages or from tournaments fetched
    separately. :meth:`chess_results.ChessResults.congress` is the way to fetch
    one.
    """
    return Congress(name=name, sections=dict(sections))
