"""Deal scoring (0-100) and sorting, modelled on Ratepunk's "AI deal score".

A fare is graded against the route's *typical* price range. The range comes
from, in order of preference:
  1. Google's own typical range for the route (SerpApi price_insights),
  2. this app's price history once it has enough observations,
  3. a built-in baseline for Perth -> Dublin.
"""

from __future__ import annotations

from .config import default_baseline
from .models import Itinerary

LABELS = [(90, "Exceptional"), (75, "Great"), (55, "Good"), (35, "Fair"), (0, "Poor")]
ERROR_FARE_RATIO = 0.55  # below 55% of the typical low => possibly a mistake fare


def deal_score(price: float, low: float, high: float) -> int:
    """80 at the bottom of the typical range, 20 at the top, 100 when ~30% under it."""
    if high <= low:
        high = low * 1.01
    if price <= low:
        score = 80 + 20 * min(1.0, (low - price) / (0.3 * low))
    elif price <= high:
        score = 80 - 60 * (price - low) / (high - low)
    else:
        score = max(0.0, 20 - 20 * (price - high) / (0.5 * high))
    return round(score)


def label_for(score: int) -> str:
    return next(name for floor, name in LABELS if score >= floor)


def score_all(
    itineraries: list[Itinerary],
    typical: dict[tuple[str, str, str, str], tuple[float, float]],
) -> None:
    """Annotate itineraries in place. `typical` maps (origin, dest, trip, currency) -> range."""
    for it in itineraries:
        trip = "return" if it.return_date else "one_way"
        rng = typical.get((it.origin, it.destination, trip, it.currency))
        if rng is None:
            rng = default_baseline(trip == "one_way", it.currency)
        if rng is None:
            continue
        low, high = rng
        it.deal_score = deal_score(it.price, low, high)
        it.deal_label = label_for(it.deal_score)
        if it.price < ERROR_FARE_RATIO * low and "possible error fare" not in it.flags:
            it.flags.append("possible error fare")


def best_value(it: Itinerary, value_of_time: float, stop_penalty: float) -> float:
    """Price plus a cost for travel time and stops; lower is better."""
    hours = it.duration_hours if it.duration_hours is not None else 30.0
    return it.price + value_of_time * hours + stop_penalty * it.total_stops


def sort_itineraries(
    itineraries: list[Itinerary], by: str, value_of_time: float = 25, stop_penalty: float = 60
) -> list[Itinerary]:
    keys = {
        "price": lambda i: (i.price, i.duration_minutes or 10**6),
        "duration": lambda i: (i.duration_minutes or 10**6, i.price),
        "stops": lambda i: (i.total_stops, i.price),
        "score": lambda i: (-(i.deal_score or 0), i.price),
        "best": lambda i: best_value(i, value_of_time, stop_penalty),
        "date": lambda i: (i.departure_date, i.price),
    }
    if by not in keys:
        raise ValueError(f"sort must be one of: {', '.join(keys)}")
    return sorted(itineraries, key=keys[by])
