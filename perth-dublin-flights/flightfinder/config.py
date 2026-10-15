"""Settings come from environment variables, optionally loaded from a .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ORIGINS = ["PER"]
DEFAULT_DESTINATIONS = ["DUB"]
# Irish/Northern Irish alternatives worth checking when Dublin itself is pricey.
NEARBY_DESTINATIONS = ["ORK", "SNN", "BFS"]

# Typical economy fares for Perth -> Dublin in AUD, used to grade deals until the
# local price history has enough observations of its own. Derived from the
# public route summaries on Skyscanner / Cheapflights / Ratepunk in 2026
# (one-way roughly A$1,100-1,800, return roughly A$1,600-2,700).
DEFAULT_BASELINES_AUD = {
    "one_way": (1100.0, 1800.0),
    "return": (1600.0, 2700.0),
}
# Rough conversion so the default baseline still works when searching in
# another currency. Only used for the fallback baseline, never for prices.
APPROX_FX_FROM_AUD = {"AUD": 1.0, "EUR": 0.60, "USD": 0.66, "GBP": 0.51, "NZD": 1.10, "SGD": 0.86}


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    travelpayouts_token: str | None
    duffel_token: str | None
    serpapi_key: str | None
    db_path: str
    webhook_url: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    email_from: str | None
    email_to: str | None
    value_of_time: float  # currency units per hour of travel, used by "best" sort
    stop_penalty: float  # currency units per extra stop, used by "best" sort

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(
            travelpayouts_token=env("TRAVELPAYOUTS_TOKEN") or None,
            duffel_token=env("DUFFEL_ACCESS_TOKEN") or None,
            serpapi_key=env("SERPAPI_KEY") or None,
            db_path=env("FLIGHTFINDER_DB", str(Path.home() / ".flightfinder" / "history.db")),
            webhook_url=env("ALERT_WEBHOOK_URL") or None,
            smtp_host=env("SMTP_HOST") or None,
            smtp_port=int(env("SMTP_PORT", "587")),
            smtp_user=env("SMTP_USER") or None,
            smtp_password=env("SMTP_PASSWORD") or None,
            email_from=env("ALERT_EMAIL_FROM") or env("SMTP_USER") or None,
            email_to=env("ALERT_EMAIL_TO") or None,
            value_of_time=float(env("VALUE_OF_TIME", "25")),
            stop_penalty=float(env("STOP_PENALTY", "60")),
        )


def default_baseline(one_way: bool, currency: str) -> tuple[float, float] | None:
    rate = APPROX_FX_FROM_AUD.get(currency.upper())
    if rate is None:
        return None
    low, high = DEFAULT_BASELINES_AUD["one_way" if one_way else "return"]
    return low * rate, high * rate
