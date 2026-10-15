"""Offline demo data so the app runs without any API keys.

Fares are synthetic but deterministic and shaped like the real Perth -> Dublin
market: no nonstop service, one-stop options through the Gulf hubs or London,
cheaper two-stop options through Asia, seasonal peaks around Christmas and the
European summer, and the occasional flash sale. Every result is flagged
"demo data" so it can never be mistaken for a real fare.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

from ..models import Itinerary, Query, Segment
from .base import Provider, google_flights_link

# (carriers, via, base one-way AUD, journey hours, local departure time from PER)
ROUTES = [
    (("QR",), ("DOH",), 1610, 22.5, "22:45"),
    (("EK",), ("DXB",), 1680, 23.5, "21:55"),
    (("EY",), ("AUH",), 1560, 24.0, "00:30"),
    (("QF", "EI"), ("LHR",), 2150, 20.5, "18:30"),
    (("SQ", "EI"), ("SIN", "LHR"), 1480, 28.0, "13:05"),
    (("CX", "EI"), ("HKG", "LHR"), 1440, 30.5, "00:05"),
    (("MH", "EI"), ("KUL", "LHR"), 1360, 31.0, "15:10"),
    (("TK",), ("SIN", "IST"), 1310, 29.0, "08:25"),
]
SEASON = {1: 1.12, 2: 0.95, 3: 0.97, 4: 1.0, 5: 1.02, 6: 1.2, 7: 1.25,
          8: 1.12, 9: 0.96, 10: 0.94, 11: 0.9, 12: 1.35}
WEEKDAY = {0: 1.0, 1: 0.93, 2: 0.93, 3: 0.98, 4: 1.06, 5: 1.0, 6: 1.07}
DEST_FACTOR = {"DUB": 1.0, "ORK": 1.06, "SNN": 1.08, "BFS": 1.03}
FX = {"AUD": 1.0, "EUR": 0.60, "USD": 0.66, "GBP": 0.51, "NZD": 1.10, "SGD": 0.86}


def _noise(*parts: object) -> float:
    """Deterministic value in [0, 1) derived from the inputs."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


class DemoProvider(Provider):
    name = "demo"
    is_live = True
    unmetered = True

    def search(self, query: Query) -> list[Itinerary]:
        if query.origin != "PER" and query.destination != "PER":
            return []
        fx = FX.get(query.currency.upper(), 1.0)
        currency = query.currency.upper() if query.currency.upper() in FX else "AUD"
        out = []
        for carriers, via, base, hours, dep_time in ROUTES:
            stops = len(via)
            if query.max_stops is not None and stops > query.max_stops:
                continue
            price = self._one_way(base, query.departure_date, query.destination, carriers)
            ret_stops = None
            if query.return_date:
                price += 0.6 * self._one_way(base, query.return_date, query.destination, carriers)
                ret_stops = stops
            # Rare flash sale / mistake fare so alerts have something to fire on.
            sale = _noise("sale", carriers, query.departure_date, query.return_date) < 0.004
            if sale:
                price *= 0.55
            it = Itinerary(
                provider=self.name,
                origin=query.origin,
                destination=query.destination,
                departure_date=query.departure_date,
                return_date=query.return_date,
                price=round(price * fx * query.adults),
                currency=currency,
                airlines=carriers,
                stops=stops,
                return_stops=ret_stops,
                duration_minutes=int(hours * 60 + 90 * _noise("dur", carriers, query.departure_date)),
                via=via,
                segments=_segments(query, carriers, via, dep_time, hours),
                booking_url=google_flights_link(
                    query.origin, query.destination, query.departure_date, query.return_date
                ),
                flags=["demo data"] + (["flash sale"] if sale else []),
            )
            out.append(it)
        return out

    @staticmethod
    def _one_way(base: float, day: date, dest: str, carriers: tuple) -> float:
        noise = 0.88 + 0.24 * _noise(carriers, day, dest)
        return base * SEASON[day.month] * WEEKDAY[day.weekday()] * DEST_FACTOR.get(dest, 1.1) * noise


def _segments(query: Query, carriers, via, dep_time: str, hours: float) -> tuple[Segment, ...]:
    points = [query.origin, *via, query.destination]
    legs = len(points) - 1
    start = datetime.combine(query.departure_date, datetime.strptime(dep_time, "%H:%M").time())
    leg_span = timedelta(hours=hours / legs)
    segs = []
    for i in range(legs):
        carrier = carriers[min(i, len(carriers) - 1)]
        dep = start + leg_span * i
        arr = dep + leg_span * 0.75  # the rest is layover
        segs.append(
            Segment(
                origin=points[i],
                destination=points[i + 1],
                departure=dep.isoformat(timespec="minutes"),
                arrival=arr.isoformat(timespec="minutes"),
                carrier=carrier,
                flight_number=str(100 + int(900 * _noise(carrier, points[i], points[i + 1]))),
            )
        )
    return tuple(segs)
