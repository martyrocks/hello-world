"""Provider interface. Each provider turns a Query into a list of Itineraries."""

from __future__ import annotations

import re
import urllib.parse
import threading
from abc import ABC, abstractmethod
from datetime import date

from ..models import Itinerary, Query


class ProviderError(RuntimeError):
    pass


class Provider(ABC):
    name: str = "provider"
    #: Live providers price a specific date on demand (and usually cost money per
    #: call); cached providers return recently-seen fares and are cheap to call.
    is_live: bool = True
    #: Unmetered providers (demo data) are called for every candidate date
    #: instead of being capped by SearchRequest.max_live_queries.
    unmetered: bool = False

    def __init__(self) -> None:
        self._lock = threading.Lock()
        #: Typical (low, high) price ranges reported by the source itself, keyed by
        #: (origin, destination, "one_way"|"return", currency). Used by the scorer.
        self.typical_ranges: dict[tuple[str, str, str, str], list[tuple[float, float]]] = {}

    @abstractmethod
    def search(self, query: Query) -> list[Itinerary]:
        """Return fares for exactly the query's route and dates."""

    def scout(
        self, origin: str, destination: str, month: str, one_way: bool, currency: str
    ) -> list[Itinerary]:
        """Cheap month-wide lookup used to pick dates worth pricing live.

        Only cached providers implement this; live providers return nothing.
        """
        return []

    def _add_typical_range(self, query: Query, low: float, high: float) -> None:
        key = (
            query.origin,
            query.destination,
            "return" if query.return_date else "one_way",
            query.currency.upper(),
        )
        with self._lock:
            self.typical_ranges.setdefault(key, []).append((low, high))


_ISO_DURATION = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?")


def parse_iso_duration(value: str | None) -> int | None:
    """'PT26H30M' / 'P1DT2H5M' -> minutes."""
    if not value:
        return None
    m = _ISO_DURATION.fullmatch(value)
    if not m:
        return None
    days, hours, minutes = (int(x or 0) for x in m.groups())
    return days * 1440 + hours * 60 + minutes


def parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def google_flights_link(origin: str, destination: str, depart: date, ret: date | None) -> str:
    """A Google Flights search URL, used as a booking link when a source has none."""
    q = f"Flights from {origin} to {destination} on {depart.isoformat()}"
    if ret:
        q += f" returning {ret.isoformat()}"
    return "https://www.google.com/travel/flights?" + urllib.parse.urlencode({"q": q})
