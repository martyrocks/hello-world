"""Command line interface: search, watch, serve, history, providers."""

from __future__ import annotations

import argparse
import calendar as cal_mod
import json
import re
import sys
import time
from datetime import date, datetime, timedelta

from .alerts import AlertRules, Notifier, process_alerts
from .config import (
    DEFAULT_DESTINATIONS,
    DEFAULT_ORIGINS,
    NEARBY_DESTINATIONS,
    Settings,
    load_dotenv,
)
from .models import Itinerary, SearchRequest
from .providers import ALL, configured_providers
from .scoring import sort_itineraries
from .search import ScanResult, scan
from .store import PriceStore

SORTS = ["price", "best", "duration", "stops", "score", "date"]


# --------------------------------------------------------------------------- parsing


def parse_date_range(value: str | None, today: date | None = None) -> tuple[date, date]:
    """'2026-11' | '2026-11-05' | '2026-11-01:2026-12-15' | None (=> 3-13 weeks out)."""
    today = today or date.today()
    if not value:
        return today + timedelta(days=21), today + timedelta(days=90)
    if ":" in value:
        a, b = value.split(":", 1)
        start, end = parse_date_range(a, today)[0], parse_date_range(b, today)[1]
    elif re.fullmatch(r"\d{4}-\d{2}", value):
        y, m = map(int, value.split("-"))
        start, end = date(y, m, 1), date(y, m, cal_mod.monthrange(y, m)[1])
    else:
        start = end = date.fromisoformat(value)
    if end < start:
        raise argparse.ArgumentTypeError(f"date range ends before it starts: {value}")
    if end < today:
        raise argparse.ArgumentTypeError(f"date range is in the past: {value}")
    return max(start, today), end


def parse_stays(value: str | None, step: int = 7) -> list[int] | None:
    """'21' -> [21]; '14-28' -> [14, 21, 28]; None -> one-way."""
    if not value:
        return None
    if "-" in value:
        lo, hi = (int(x) for x in value.split("-", 1))
        if hi < lo:
            lo, hi = hi, lo
        stays = list(range(lo, hi + 1, max(1, step)))
        if stays[-1] != hi:
            stays.append(hi)
        return stays
    return [int(value)]


def parse_interval(value: str) -> int:
    """'6h' / '30m' / '1d' / '3600' -> seconds."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([smhd]?)", value.strip().lower())
    if not m:
        raise argparse.ArgumentTypeError(f"bad interval: {value}")
    n, unit = float(m.group(1)), m.group(2) or "s"
    return int(n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit])


def codes(value: str) -> list[str]:
    out = [c.strip().upper() for c in value.split(",") if c.strip()]
    for c in out:
        if not re.fullmatch(r"[A-Z]{3}", c):
            raise argparse.ArgumentTypeError(f"not an IATA airport code: {c}")
    return out


def build_request(args: argparse.Namespace) -> SearchRequest:
    start, end = parse_date_range(args.depart)
    destinations = list(args.to)
    if args.nearby:
        destinations += [d for d in NEARBY_DESTINATIONS if d not in destinations]
    return SearchRequest(
        origins=args.origin,
        destinations=destinations,
        depart_from=start,
        depart_to=end,
        stays=parse_stays(args.stay, args.stay_step),
        adults=args.adults,
        cabin=args.cabin,
        currency=args.currency.upper(),
        max_stops=args.max_stops,
        max_duration_hours=args.max_hours,
        airlines=args.airline,
        max_live_queries=args.max_queries,
        date_step=args.date_step,
    )


# --------------------------------------------------------------------------- output


def _money(v: float, cur: str) -> str:
    return f"{v:,.0f} {cur}"


def format_table(items: list[Itinerary]) -> str:
    headers = ["#", "Price", "Deal", "Depart", "Return", "Airlines", "Stops", "Time", "Source"]
    rows = []
    for n, it in enumerate(items, 1):
        stops = str(it.stops) + (f" ({','.join(it.via)})" if it.via else "")
        if it.return_stops is not None:
            stops += f" / {it.return_stops}"
        rows.append(
            [
                str(n),
                _money(it.price, it.currency),
                f"{it.deal_score} {it.deal_label}" if it.deal_score is not None else "-",
                it.departure_date.strftime("%a %d %b"),
                it.return_date.strftime("%a %d %b") if it.return_date else "-",
                "/".join(it.airlines)[:22] or "-",
                stops,
                f"{it.duration_hours:.1f}h" if it.duration_minutes else "-",
                it.provider + ("" if it.is_live else " (cached)"),
            ]
        )
    widths = [max(len(r[i]) for r in [headers, *rows]) for i in range(len(headers))]
    line = lambda r: "  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip()
    out = [line(headers), line(["-" * w for w in widths])]
    for r, it in zip(rows, items):
        out.append(line(r))
        if it.flags:
            out.append(" " * (widths[0] + 2) + "↳ " + ", ".join(it.flags))
    return "\n".join(out)


def format_calendar(result: ScanResult) -> str:
    cal = result.calendar()
    if not cal:
        return ""
    prices = [it.price for it in cal.values()]
    lo, hi = min(prices), max(prices)
    out = ["Cheapest fare by departure date:"]
    for day, it in cal.items():
        width = 1 + int(29 * (it.price - lo) / (hi - lo)) if hi > lo else 1
        mark = "  ◀ cheapest" if it.price == lo else ""
        out.append(
            f"  {day.strftime('%a %d %b')}  {_money(it.price, it.currency):>11}  {'█' * width}{mark}"
        )
    return "\n".join(out)


def print_result(result: ScanResult, req: SearchRequest, args, settings: Settings) -> None:
    items = sort_itineraries(
        result.itineraries, args.sort, settings.value_of_time, settings.stop_penalty
    )
    if args.json:
        print(
            json.dumps(
                {
                    "request": {
                        "origins": req.origins,
                        "destinations": req.destinations,
                        "depart_from": req.depart_from.isoformat(),
                        "depart_to": req.depart_to.isoformat(),
                        "stays": req.stays,
                        "currency": req.currency,
                    },
                    "providers": result.providers,
                    "errors": result.errors,
                    "results": [it.to_dict() for it in items[: args.limit]],
                },
                indent=2,
            )
        )
        return
    trip = "one-way" if req.one_way else f"return, {'/'.join(map(str, req.stays))} nights"
    print(
        f"\n{'/'.join(req.origins)} → {'/'.join(req.destinations)}  |  "
        f"departing {req.depart_from:%d %b %Y} – {req.depart_to:%d %b %Y}  |  {trip}  |  "
        f"{req.adults} adult(s), {req.cabin}"
    )
    print(f"Sources: {', '.join(result.providers)}  |  live queries: {result.live_queries}")
    if "demo" in result.providers:
        print("NOTE: showing DEMO data. Add an API key (see README) for real fares.")
    for err in result.errors:
        print(f"warning: {err}", file=sys.stderr)
    if not items:
        print("\nNo fares found for those dates/filters.")
        return
    best = result.cheapest
    print(
        f"\nCheapest: {_money(best.price, best.currency)} on "
        f"{best.departure_date:%a %d %b %Y} with {'/'.join(best.airlines) or 'n/a'}"
        f" ({best.deal_label or 'unscored'})"
    )
    if args.calendar:
        print("\n" + format_calendar(result))
    print(f"\nTop {min(args.limit, len(items))} sorted by {args.sort}:\n")
    print(format_table(items[: args.limit]))
    print("\nBooking links:")
    for n, it in enumerate(items[: min(3, args.limit)], 1):
        print(f"  {n}. {it.booking_url or 'n/a'}")


# --------------------------------------------------------------------------- commands


def _setup(args):
    settings = Settings.from_env()
    if getattr(args, "db", None):
        settings.db_path = args.db
    providers = configured_providers(settings, args.providers)
    store = None if getattr(args, "no_history", False) else PriceStore(settings.db_path)
    return settings, providers, store


def _progress(args):
    if args.json or args.quiet:
        return None
    return lambda msg: print(f"  … {msg}", file=sys.stderr)


def cmd_search(args) -> int:
    settings, providers, store = _setup(args)
    req = build_request(args)
    result = scan(req, providers, store, progress=_progress(args))
    print_result(result, req, args, settings)
    return 0 if result.itineraries else 1


def cmd_watch(args) -> int:
    settings, providers, store = _setup(args)
    if store is None:
        print("watch needs price history; drop --no-history", file=sys.stderr)
        return 2
    rules = AlertRules(
        below_price=args.below,
        min_score=args.min_score,
        new_low=not args.no_new_low,
        max_alerts=args.max_alerts,
    )
    notifier = Notifier(settings)
    demo = all(p.name == "demo" for p in providers)
    while True:
        req = build_request(args)  # re-evaluated so relative dates roll forward
        trip = "one_way" if req.one_way else "return"
        previous_low = {
            (o, d, trip): store.lowest_seen(o, d, trip, req.currency, demo=demo)
            for o in req.origins
            for d in req.destinations
        }
        started = datetime.now()
        result = scan(req, providers, store, progress=_progress(args))
        for err in result.errors:
            print(f"warning: {err}", file=sys.stderr)
        hits = process_alerts(result.itineraries, rules, store, notifier, previous_low)
        best = result.cheapest
        print(
            f"[{started:%Y-%m-%d %H:%M}] scanned {len(result.itineraries)} fares; cheapest "
            + (f"{_money(best.price, best.currency)} on {best.departure_date}" if best else "n/a")
            + f"; {len(hits)} alert(s)"
        )
        if args.once:
            return 0
        next_run = datetime.now() + timedelta(seconds=args.every)
        print(f"next scan at {next_run:%Y-%m-%d %H:%M} (Ctrl+C to stop)")
        try:
            time.sleep(args.every)
        except KeyboardInterrupt:
            return 0


def cmd_history(args) -> int:
    settings = Settings.from_env()
    if args.db:
        settings.db_path = args.db
    store = PriceStore(settings.db_path)
    trip = "return" if args.trip == "return" else "one_way"
    rows = store.daily_lows(
        args.origin[0], args.to[0], trip, args.currency.upper(), demo=args.demo, days=args.days
    )
    if not rows:
        print("No history yet. Run `search` or `watch` first.")
        return 1
    lo, hi = min(p for _, p in rows), max(p for _, p in rows)
    print(f"Daily lowest {trip.replace('_', '-')} fare seen, {args.origin[0]} → {args.to[0]}:")
    for day, price in rows:
        width = 1 + int(29 * (price - lo) / (hi - lo)) if hi > lo else 1
        print(f"  {day}  {_money(price, args.currency.upper()):>11}  {'█' * width}")
    return 0


def cmd_providers(args) -> int:
    settings = Settings.from_env()
    active = {p.name for p in configured_providers(settings)}
    info = {
        "travelpayouts": ("TRAVELPAYOUTS_TOKEN", "cached fares, whole-month scouting (free)"),
        "duffel": ("DUFFEL_ACCESS_TOKEN", "live airline offers (pay per booking)"),
        "serpapi": ("SERPAPI_KEY", "live Google Flights results + typical prices"),
        "demo": ("-", "synthetic offline data, used when nothing else is set up"),
    }
    for name in ALL:
        env, desc = info[name]
        print(f"  [{'x' if name in active else ' '}] {name:<14} {env:<22} {desc}")
    return 0


def cmd_serve(args) -> int:
    from .web import serve

    settings, providers, store = _setup(args)
    serve(settings, providers, store, args.host, args.port)
    return 0


# --------------------------------------------------------------------------- argparse


def _add_search_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("route & dates")
    g.add_argument("--from", dest="origin", type=codes, default=DEFAULT_ORIGINS,
                   help="origin airport(s), comma separated (default PER)")
    g.add_argument("--to", type=codes, default=DEFAULT_DESTINATIONS,
                   help="destination airport(s), comma separated (default DUB)")
    g.add_argument("--nearby", action="store_true",
                   help="also check Cork, Shannon and Belfast")
    g.add_argument("--depart", metavar="WHEN",
                   help="YYYY-MM, YYYY-MM-DD or START:END (default: 3 to 13 weeks from today)")
    g.add_argument("--stay", metavar="NIGHTS",
                   help="search return trips of N nights, or a range like 14-28 (default one-way)")
    g.add_argument("--stay-step", type=int, default=7, help="step for a --stay range (default 7)")
    g.add_argument("--date-step", type=int, default=1,
                   help="check every Nth departure day (default 1)")
    f = p.add_argument_group("filters")
    f.add_argument("--max-stops", type=int)
    f.add_argument("--max-hours", type=float, help="maximum outbound journey time")
    f.add_argument("--airline", type=lambda v: [c.strip().upper() for c in v.split(",")],
                   help="only fares flown entirely by these airlines, e.g. QR or QR,EK")
    f.add_argument("--adults", type=int, default=1)
    f.add_argument("--cabin", default="economy",
                   choices=["economy", "premium_economy", "business", "first"])
    f.add_argument("--currency", default="AUD")
    s = p.add_argument_group("sources")
    s.add_argument("--providers", type=lambda v: v.split(","),
                   help=f"limit to these providers: {', '.join(ALL)}")
    s.add_argument("--max-queries", type=int, default=12,
                   help="date combinations to price with paid live providers (default 12)")
    s.add_argument("--db", help="price history database path")
    s.add_argument("--no-history", action="store_true", help="don't read or write price history")
    o = p.add_argument_group("output")
    o.add_argument("--sort", choices=SORTS, default="price")
    o.add_argument("--limit", type=int, default=15)
    o.add_argument("--calendar", action="store_true", help="show cheapest fare per day")
    o.add_argument("--json", action="store_true")
    o.add_argument("-q", "--quiet", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flightfinder",
        description="Find the cheapest flights from Perth to Dublin.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="search once and print the cheapest fares")
    _add_search_args(p)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("watch", help="re-scan on a schedule and alert on deals")
    _add_search_args(p)
    p.add_argument("--every", type=parse_interval, default=parse_interval("6h"),
                   help="time between scans, e.g. 30m, 6h, 1d (default 6h)")
    p.add_argument("--once", action="store_true", help="scan once and exit (for cron)")
    p.add_argument("--below", type=float, help="alert when a fare is at or under this price")
    p.add_argument("--min-score", type=int, default=85, help="alert at this deal score (default 85)")
    p.add_argument("--no-new-low", action="store_true", help="don't alert on new lowest prices")
    p.add_argument("--max-alerts", type=int, default=5)
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("serve", help="run the web dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--providers", type=lambda v: v.split(","))
    p.add_argument("--db")
    p.add_argument("--no-history", action="store_true")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("history", help="show the daily lowest fare seen so far")
    p.add_argument("--from", dest="origin", type=codes, default=DEFAULT_ORIGINS)
    p.add_argument("--to", type=codes, default=DEFAULT_DESTINATIONS)
    p.add_argument("--trip", choices=["one-way", "return"], default="one-way")
    p.add_argument("--currency", default="AUD")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--demo", action="store_true", help="show history recorded from demo data")
    p.add_argument("--db")
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("providers", help="list data sources and which are configured")
    p.set_defaults(func=cmd_providers)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, argparse.ArgumentTypeError) as e:
        parser.error(str(e))
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:  # e.g. piped into `head`
        sys.stderr.close()
        return 0
