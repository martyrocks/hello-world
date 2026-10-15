"""Duffel Flights API (live, bookable airline offers).

Docs: https://duffel.com/docs/api/v2/offer-requests
A test token (duffel_test_...) returns sandbox data; a live token returns real
fares. Each call prices one specific set of dates.
"""

from __future__ import annotations

from ..http import HTTPError, request_json
from ..models import Itinerary, Query, Segment
from .base import (
    Provider,
    ProviderError,
    google_flights_link,
    parse_date,
    parse_iso_duration,
)

URL = "https://api.duffel.com/air/offer_requests"


class DuffelProvider(Provider):
    name = "duffel"
    is_live = True

    def __init__(self, token: str):
        super().__init__()
        self.token = token

    def search(self, query: Query) -> list[Itinerary]:
        slices = [
            {
                "origin": query.origin,
                "destination": query.destination,
                "departure_date": query.departure_date.isoformat(),
            }
        ]
        if query.return_date:
            slices.append(
                {
                    "origin": query.destination,
                    "destination": query.origin,
                    "departure_date": query.return_date.isoformat(),
                }
            )
        body = {
            "data": {
                "slices": slices,
                "passengers": [{"type": "adult"} for _ in range(query.adults)],
                "cabin_class": query.cabin,
            }
        }
        if query.max_stops is not None:
            body["data"]["max_connections"] = query.max_stops
        try:
            payload = request_json(
                "POST",
                URL,
                params={"return_offers": "true", "supplier_timeout": 20000},
                headers={"Authorization": f"Bearer {self.token}", "Duffel-Version": "v2"},
                body=body,
                timeout=60,
            )
        except HTTPError as e:
            raise ProviderError(f"duffel: {e}") from None
        return self.parse(payload, query)

    def parse(self, payload: dict, query: Query) -> list[Itinerary]:
        out = []
        for offer in (payload.get("data") or {}).get("offers") or []:
            try:
                slices = offer["slices"]
                outbound = slices[0]
                segs = tuple(_segment(s) for s in outbound["segments"])
                ret_stops = len(slices[1]["segments"]) - 1 if len(slices) > 1 else None
                ret_date = (
                    parse_date(slices[1]["segments"][0]["departing_at"])
                    if len(slices) > 1
                    else None
                )
                carriers = []
                for sl in slices:
                    for s in sl["segments"]:
                        name = s["marketing_carrier"]["iata_code"]
                        if name not in carriers:
                            carriers.append(name)
                out.append(
                    Itinerary(
                        provider=self.name,
                        origin=segs[0].origin,
                        destination=segs[-1].destination,
                        departure_date=parse_date(segs[0].departure),
                        return_date=ret_date,
                        price=float(offer["total_amount"]),
                        currency=offer["total_currency"],
                        airlines=tuple(carriers),
                        stops=len(segs) - 1,
                        return_stops=ret_stops,
                        duration_minutes=parse_iso_duration(outbound.get("duration")),
                        via=tuple(s.destination for s in segs[:-1]),
                        segments=segs,
                        # Duffel offers are booked through its API; link to a
                        # public search for the same dates instead.
                        booking_url=google_flights_link(
                            segs[0].origin,
                            segs[-1].destination,
                            parse_date(segs[0].departure),
                            ret_date,
                        ),
                    )
                )
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        if query.currency and out and any(i.currency != query.currency for i in out):
            # Duffel prices in the airline's currency; flag it so the user isn't misled.
            for i in out:
                if i.currency != query.currency:
                    i.flags.append(f"priced in {i.currency}")
        return out


def _segment(s: dict) -> Segment:
    return Segment(
        origin=s["origin"]["iata_code"],
        destination=s["destination"]["iata_code"],
        departure=s["departing_at"],
        arrival=s["arriving_at"],
        carrier=s["marketing_carrier"]["iata_code"],
        flight_number=str(s.get("marketing_carrier_flight_number") or ""),
    )
