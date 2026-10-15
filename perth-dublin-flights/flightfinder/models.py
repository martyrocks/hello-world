"""Core data types shared by providers, the scanner and the UIs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone


@dataclass(frozen=True)
class Segment:
    origin: str
    destination: str
    departure: str  # ISO-8601 local time as reported by the provider
    arrival: str
    carrier: str
    flight_number: str = ""


@dataclass
class Itinerary:
    """One bookable (or, for cached sources, recently seen) fare."""

    provider: str
    origin: str
    destination: str
    departure_date: date
    price: float
    currency: str
    return_date: date | None = None
    airlines: tuple[str, ...] = ()
    stops: int = 0
    return_stops: int | None = None
    duration_minutes: int | None = None  # outbound journey time
    via: tuple[str, ...] = ()
    booking_url: str | None = None
    segments: tuple[Segment, ...] = ()
    is_live: bool = True  # False for cached / historical fare sources
    found_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Filled in by the scorer.
    deal_score: int | None = None
    deal_label: str | None = None
    flags: list[str] = field(default_factory=list)

    @property
    def is_return(self) -> bool:
        return self.return_date is not None

    @property
    def total_stops(self) -> int:
        return self.stops + (self.return_stops or 0)

    def flown_only_by(self, codes: list[str]) -> bool:
        """True if every leg is on one of the given airlines (IATA codes).

        Segment flight numbers are checked first because some sources (Google
        Flights) give airline names rather than codes.
        """
        wanted = {c.upper() for c in codes}
        if self.segments:
            return all(
                s.carrier.upper() in wanted
                or s.flight_number.replace(" ", "")[:2].upper() in wanted
                for s in self.segments
            )
        return bool(self.airlines) and all(a.upper() in wanted for a in self.airlines)

    @property
    def duration_hours(self) -> float | None:
        return None if self.duration_minutes is None else self.duration_minutes / 60

    def dedupe_key(self) -> tuple:
        flights = tuple(f"{s.carrier}{s.flight_number}" for s in self.segments)
        return (
            self.origin,
            self.destination,
            self.departure_date,
            self.return_date,
            flights or (self.airlines, self.stops, self.via),
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["departure_date"] = self.departure_date.isoformat()
        d["return_date"] = self.return_date.isoformat() if self.return_date else None
        d["found_at"] = self.found_at.isoformat()
        d["duration_hours"] = round(self.duration_hours, 1) if self.duration_minutes else None
        return d


@dataclass(frozen=True)
class Query:
    """A single concrete provider query: one route, one set of dates."""

    origin: str
    destination: str
    departure_date: date
    return_date: date | None = None
    adults: int = 1
    cabin: str = "economy"
    currency: str = "AUD"
    max_stops: int | None = None


@dataclass
class SearchRequest:
    """What the user asked for; expanded into many Query objects by the scanner."""

    origins: list[str]
    destinations: list[str]
    depart_from: date
    depart_to: date
    stays: list[int] | None = None  # None => one-way; otherwise trip lengths in days
    adults: int = 1
    cabin: str = "economy"
    currency: str = "AUD"
    max_stops: int | None = None
    max_duration_hours: float | None = None
    airlines: list[str] | None = None  # IATA codes; keep fares flown only by these
    max_live_queries: int = 12
    date_step: int = 1

    @property
    def one_way(self) -> bool:
        return not self.stays
