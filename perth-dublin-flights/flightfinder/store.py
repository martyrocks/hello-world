"""SQLite price history: powers deal scoring, "new low" alerts and trend charts."""

from __future__ import annotations

import sqlite3
import statistics
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Itinerary

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    observed_at TEXT NOT NULL,
    provider TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    trip TEXT NOT NULL,              -- 'one_way' | 'return'
    departure_date TEXT NOT NULL,
    return_date TEXT,
    price REAL NOT NULL,
    currency TEXT NOT NULL,
    airlines TEXT,
    stops INTEGER,
    is_demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_obs_route
    ON observations (origin, destination, trip, currency, observed_at);
CREATE TABLE IF NOT EXISTS alerts_sent (
    key TEXT PRIMARY KEY,
    price REAL NOT NULL,
    sent_at TEXT NOT NULL
);
"""


def trip_kind(it: Itinerary) -> str:
    return "return" if it.return_date else "one_way"


class PriceStore:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(Path(path).expanduser()), check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self._lock = threading.Lock()

    def record(self, itineraries: list[Itinerary]) -> None:
        rows = [
            (
                it.found_at.isoformat(),
                it.provider,
                it.origin,
                it.destination,
                trip_kind(it),
                it.departure_date.isoformat(),
                it.return_date.isoformat() if it.return_date else None,
                it.price,
                it.currency,
                ",".join(it.airlines),
                it.stops,
                int(it.provider == "demo"),
            )
            for it in itineraries
        ]
        with self._lock, self.conn:
            self.conn.executemany(
                "INSERT INTO observations (observed_at, provider, origin, destination, trip,"
                " departure_date, return_date, price, currency, airlines, stops, is_demo)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )

    def _prices(self, origin, destination, trip, currency, days, demo) -> list[float]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            cur = self.conn.execute(
                "SELECT price FROM observations WHERE origin=? AND destination=? AND trip=?"
                " AND currency=? AND observed_at>=? AND is_demo=?",
                (origin, destination, trip, currency, since, int(demo)),
            )
            return [r[0] for r in cur.fetchall()]

    def typical_range(
        self, origin, destination, trip, currency, *, demo=False, days=120, min_samples=30
    ) -> tuple[float, float] | None:
        """Inter-quartile range of recently seen prices, if there is enough history."""
        prices = self._prices(origin, destination, trip, currency, days, demo)
        if len(prices) < min_samples:
            return None
        q = statistics.quantiles(prices, n=4)
        return q[0], q[2]

    def lowest_seen(self, origin, destination, trip, currency, *, demo=False, days=365):
        prices = self._prices(origin, destination, trip, currency, days, demo)
        return min(prices) if prices else None

    def daily_lows(self, origin, destination, trip, currency, *, demo=False, days=90):
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            cur = self.conn.execute(
                "SELECT substr(observed_at,1,10) AS day, MIN(price) FROM observations"
                " WHERE origin=? AND destination=? AND trip=? AND currency=?"
                " AND observed_at>=? AND is_demo=? GROUP BY day ORDER BY day",
                (origin, destination, trip, currency, since, int(demo)),
            )
            return [(day, price) for day, price in cur.fetchall()]

    def should_alert(self, key: str, price: float) -> bool:
        """True unless we've already alerted on this fare at the same or a lower price."""
        with self._lock:
            row = self.conn.execute(
                "SELECT price FROM alerts_sent WHERE key=?", (key,)
            ).fetchone()
        return row is None or price < row[0] - 0.5

    def mark_alerted(self, key: str, price: float) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT INTO alerts_sent (key, price, sent_at) VALUES (?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET price=excluded.price, sent_at=excluded.sent_at",
                (key, price, datetime.now(timezone.utc).isoformat()),
            )
