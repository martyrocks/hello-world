"""The scanner: expands a SearchRequest into provider calls and merges the results.

Strategy ("scout, then verify"):
  1. Cached providers (Travelpayouts) are asked for whole months at once. That's
     cheap and shows which departure dates are currently cheap.
  2. Live providers (Duffel, Google Flights via SerpApi) are expensive per call,
     so they only price the most promising date combinations: the scout's
     cheapest dates first, then an even spread over the rest of the window.
  3. Everything is filtered, de-duplicated, scored against the route's typical
     price and saved to the price history.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import Itinerary, Query, SearchRequest
from .providers.base import Provider, ProviderError
from .providers.travelpayouts import months_between
from .scoring import score_all
from .store import PriceStore

Combo = tuple[str, str, date, "date | None"]
UNMETERED_CAP = 500


@dataclass
class ScanResult:
    itineraries: list[Itinerary]
    errors: list[str] = field(default_factory=list)
    live_queries: int = 0
    providers: list[str] = field(default_factory=list)

    @property
    def cheapest(self) -> Itinerary | None:
        return min(self.itineraries, key=lambda i: i.price, default=None)

    def calendar(self) -> dict[date, Itinerary]:
        """Cheapest fare per departure date."""
        cal: dict[date, Itinerary] = {}
        for it in self.itineraries:
            cur = cal.get(it.departure_date)
            if cur is None or it.price < cur.price:
                cal[it.departure_date] = it
        return dict(sorted(cal.items()))


def candidate_combos(req: SearchRequest) -> list[Combo]:
    combos: list[Combo] = []
    day = req.depart_from
    while day <= req.depart_to:
        for o in req.origins:
            for d in req.destinations:
                if req.one_way:
                    combos.append((o, d, day, None))
                else:
                    for stay in req.stays or []:
                        combos.append((o, d, day, day + timedelta(days=stay)))
        day += timedelta(days=max(1, req.date_step))
    return combos


def spread(items: list, n: int) -> list:
    """Pick n items evenly spaced across the list (keeps first and last)."""
    if n <= 0:
        return []
    if len(items) <= n:
        return list(items)
    if n == 1:
        return [items[len(items) // 2]]
    step = (len(items) - 1) / (n - 1)
    return [items[round(i * step)] for i in range(n)]


def choose_live_combos(
    candidates: list[Combo], scouted: list[Itinerary], limit: int
) -> list[Combo]:
    allowed = set(candidates)
    chosen: list[Combo] = []
    for it in sorted(scouted, key=lambda i: i.price):
        combo = (it.origin, it.destination, it.departure_date, it.return_date)
        if combo in allowed and combo not in chosen:
            chosen.append(combo)
        if len(chosen) >= limit:
            return chosen
    rest = [c for c in candidates if c not in chosen]
    return chosen + spread(rest, limit - len(chosen))


def _in_window(it: Itinerary, req: SearchRequest) -> bool:
    if not (req.depart_from <= it.departure_date <= req.depart_to):
        return False
    if req.one_way:
        return it.return_date is None
    if it.return_date is None:
        return False
    stay = (it.return_date - it.departure_date).days
    return min(req.stays) <= stay <= max(req.stays)


def _passes_filters(it: Itinerary, req: SearchRequest) -> bool:
    if req.max_stops is not None and it.stops > req.max_stops:
        return False
    if (
        req.max_duration_hours is not None
        and it.duration_hours is not None
        and it.duration_hours > req.max_duration_hours
    ):
        return False
    return True


def dedupe(itineraries: list[Itinerary]) -> list[Itinerary]:
    """Keep the cheapest copy of each distinct itinerary; prefer live over cached on ties."""
    best: dict[tuple, Itinerary] = {}
    for it in itineraries:
        key = it.dedupe_key()
        cur = best.get(key)
        if cur is None or (it.price, not it.is_live) < (cur.price, not cur.is_live):
            best[key] = it
    return list(best.values())


def scan(
    req: SearchRequest,
    providers: list[Provider],
    store: PriceStore | None = None,
    progress: Callable[[str], None] | None = None,
    max_workers: int = 6,
) -> ScanResult:
    say = progress or (lambda _msg: None)
    result = ScanResult(itineraries=[], providers=[p.name for p in providers])
    found: list[Itinerary] = []
    for p in providers:
        p.typical_ranges.clear()  # ranges are per scan

    # 1. Scout with cached providers.
    scouted: list[Itinerary] = []
    cached = [p for p in providers if not p.is_live]
    months = months_between(req.depart_from, req.depart_to)
    for p in cached:
        for o in req.origins:
            for d in req.destinations:
                for month in months:
                    say(f"{p.name}: scouting {o}->{d} {month}")
                    try:
                        scouted += p.scout(o, d, month, req.one_way, req.currency)
                    except ProviderError as e:
                        result.errors.append(str(e))
    scouted = [it for it in scouted if _in_window(it, req)]
    found += scouted

    # 2. Price promising combinations with live providers.
    candidates = candidate_combos(req)
    metered = choose_live_combos(candidates, scouted, req.max_live_queries)
    unmetered = spread(candidates, UNMETERED_CAP)
    jobs: list[tuple[Provider, Query]] = []
    for p in (p for p in providers if p.is_live):
        for o, d, dep, ret in unmetered if p.unmetered else metered:
            jobs.append(
                (
                    p,
                    Query(
                        origin=o,
                        destination=d,
                        departure_date=dep,
                        return_date=ret,
                        adults=req.adults,
                        cabin=req.cabin,
                        currency=req.currency,
                        max_stops=req.max_stops,
                    ),
                )
            )
    result.live_queries = sum(1 for p, _ in jobs if not p.unmetered)
    if jobs:
        say(f"running {len(jobs)} provider queries")
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(p.search, q): (p, q) for p, q in jobs}
        errors: set[str] = set()
        for fut in as_completed(futures):
            try:
                found += fut.result()
            except ProviderError as e:
                errors.add(str(e))
            except Exception as e:  # network failures etc. shouldn't kill the scan
                errors.add(f"{futures[fut][0].name}: {type(e).__name__}: {e}")
        result.errors += sorted(errors)

    # 3. Filter, de-duplicate, score, record.
    found = [it for it in found if _in_window(it, req) and _passes_filters(it, req)]
    found = dedupe(found)

    typical: dict[tuple[str, str, str, str], tuple[float, float]] = {}
    for p in providers:
        for key, ranges in p.typical_ranges.items():
            typical[key] = (
                statistics.median(r[0] for r in ranges),
                statistics.median(r[1] for r in ranges),
            )
    if store is not None:
        demo = all(p.name == "demo" for p in providers)
        trip = "one_way" if req.one_way else "return"
        for o in req.origins:
            for d in req.destinations:
                key = (o, d, trip, req.currency.upper())
                if key not in typical:
                    rng = store.typical_range(o, d, trip, req.currency.upper(), demo=demo)
                    if rng:
                        typical[key] = rng
    score_all(found, typical)
    if store is not None and found:
        store.record(found)

    result.itineraries = sorted(found, key=lambda i: i.price)
    return result
