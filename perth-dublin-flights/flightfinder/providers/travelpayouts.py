"""Travelpayouts / Aviasales Data API (free, cached fares from the last ~48h).

Docs: https://support.travelpayouts.com/hc/en-us/articles/203956163
This is the "scout": one call covers a whole month, so it is used to find which
dates are cheap before spending live-search calls on them.
"""

from __future__ import annotations

from datetime import date

from ..http import HTTPError, request_json
from ..models import Itinerary, Query
from .base import Provider, ProviderError, parse_date

URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
AVIASALES = "https://www.aviasales.com"


class TravelpayoutsProvider(Provider):
    name = "travelpayouts"
    is_live = False

    def __init__(self, token: str, marker: str | None = None):
        super().__init__()
        self.token = token
        self.marker = marker

    def _fetch(self, params: dict) -> dict:
        try:
            payload = request_json(
                "GET", URL, params=params, headers={"X-Access-Token": self.token}
            )
        except HTTPError as e:
            raise ProviderError(f"travelpayouts: {e}") from None
        if not payload.get("success", False):
            raise ProviderError(f"travelpayouts: {payload.get('error', 'request failed')}")
        return payload

    def search(self, query: Query) -> list[Itinerary]:
        params = {
            "origin": query.origin,
            "destination": query.destination,
            "departure_at": query.departure_date.isoformat(),
            "return_at": query.return_date.isoformat() if query.return_date else None,
            "one_way": "false" if query.return_date else "true",
            "direct": "false",
            "sorting": "price",
            "unique": "false",
            "currency": query.currency.lower(),
            "limit": 30,
        }
        return self.parse(self._fetch(params), query.currency)

    def scout(self, origin, destination, month, one_way, currency) -> list[Itinerary]:
        params = {
            "origin": origin,
            "destination": destination,
            "departure_at": month,  # YYYY-MM
            "one_way": "true" if one_way else "false",
            "direct": "false",
            "sorting": "price",
            "unique": "false",
            "currency": currency.lower(),
            "limit": 1000,
        }
        return self.parse(self._fetch(params), currency)

    def parse(self, payload: dict, currency: str) -> list[Itinerary]:
        cur = (payload.get("currency") or currency).upper()
        out = []
        for row in payload.get("data") or []:
            try:
                dep = parse_date(row["departure_at"])
                ret = parse_date(row["return_at"]) if row.get("return_at") else None
                link = row.get("link")
                url = f"{AVIASALES}{link}" if link and link.startswith("/") else link
                if url and self.marker:
                    url += f"{'&' if '?' in url else '?'}marker={self.marker}"
                out.append(
                    Itinerary(
                        provider=self.name,
                        origin=row.get("origin_airport") or row["origin"],
                        destination=row.get("destination_airport") or row["destination"],
                        departure_date=dep,
                        return_date=ret,
                        price=float(row["price"]),
                        currency=cur,
                        airlines=(row["airline"],) if row.get("airline") else (),
                        stops=int(row.get("transfers") or 0),
                        return_stops=(
                            int(row["return_transfers"])
                            if ret and row.get("return_transfers") is not None
                            else None
                        ),
                        duration_minutes=row.get("duration_to") or row.get("duration"),
                        booking_url=url,
                        is_live=False,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue  # skip malformed rows rather than failing the whole scan
        return out


def months_between(start: date, end: date) -> list[str]:
    months, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months
