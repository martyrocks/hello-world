"""Google Flights results via SerpApi (live; Google has no public flights API).

Docs: https://serpapi.com/google-flights-api
Besides fares, Google returns "price_insights" with the typical price range
for the route, which the scorer uses to grade deals.
"""

from __future__ import annotations

from ..http import HTTPError, request_json
from ..models import Itinerary, Query, Segment
from .base import Provider, ProviderError, parse_date

URL = "https://serpapi.com/search.json"
CABINS = {"economy": 1, "premium_economy": 2, "business": 3, "first": 4}


class SerpApiProvider(Provider):
    name = "serpapi"
    is_live = True

    def __init__(self, api_key: str, gl: str = "au", hl: str = "en"):
        super().__init__()
        self.api_key = api_key
        self.gl = gl
        self.hl = hl

    def search(self, query: Query) -> list[Itinerary]:
        params = {
            "engine": "google_flights",
            "departure_id": query.origin,
            "arrival_id": query.destination,
            "outbound_date": query.departure_date.isoformat(),
            "return_date": query.return_date.isoformat() if query.return_date else None,
            "type": 1 if query.return_date else 2,
            "currency": query.currency.upper(),
            "adults": query.adults,
            "travel_class": CABINS.get(query.cabin, 1),
            # SerpApi: 1 = nonstop, 2 = up to 1 stop, 3 = up to 2 stops; omit for any.
            "stops": (
                query.max_stops + 1
                if query.max_stops is not None and query.max_stops < 3
                else None
            ),
            "hl": self.hl,
            "gl": self.gl,
            "api_key": self.api_key,
        }
        try:
            payload = request_json("GET", URL, params=params, timeout=60)
        except HTTPError as e:
            raise ProviderError(f"serpapi: {e}") from None
        if payload.get("error"):
            if "returned any results" in payload["error"]:
                return []
            raise ProviderError(f"serpapi: {payload['error']}")
        return self.parse(payload, query)

    def parse(self, payload: dict, query: Query) -> list[Itinerary]:
        insights = payload.get("price_insights") or {}
        rng = insights.get("typical_price_range")
        if isinstance(rng, list) and len(rng) == 2:
            self._add_typical_range(query, float(rng[0]), float(rng[1]))
        link = (payload.get("search_metadata") or {}).get("google_flights_url")
        out = []
        for option in (payload.get("best_flights") or []) + (payload.get("other_flights") or []):
            try:
                flights = option["flights"]
                segs = tuple(
                    Segment(
                        origin=f["departure_airport"]["id"],
                        destination=f["arrival_airport"]["id"],
                        departure=f["departure_airport"]["time"].replace(" ", "T"),
                        arrival=f["arrival_airport"]["time"].replace(" ", "T"),
                        carrier=f.get("airline", ""),
                        flight_number=f.get("flight_number", ""),
                    )
                    for f in flights
                )
                airlines = []
                for f in flights:
                    if f.get("airline") and f["airline"] not in airlines:
                        airlines.append(f["airline"])
                it = Itinerary(
                    provider=self.name,
                    origin=segs[0].origin,
                    destination=segs[-1].destination,
                    departure_date=parse_date(segs[0].departure),
                    return_date=query.return_date,
                    price=float(option["price"]),
                    currency=query.currency.upper(),
                    airlines=tuple(airlines),
                    stops=len(segs) - 1,
                    duration_minutes=option.get("total_duration"),
                    via=tuple(l["id"] for l in option.get("layovers") or [] if l.get("id")),
                    segments=segs,
                    booking_url=link,
                )
                if any(l.get("overnight") for l in option.get("layovers") or []):
                    it.flags.append("overnight layover")
                if any(f.get("often_delayed_by_over_30_min") for f in flights):
                    it.flags.append("often delayed")
                out.append(it)
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        return out
