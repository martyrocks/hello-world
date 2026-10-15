"""Small web dashboard (stdlib only): search form, price calendar, sortable results."""

from __future__ import annotations

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import NEARBY_DESTINATIONS, Settings
from .models import SearchRequest
from .providers.base import Provider
from .scoring import sort_itineraries
from .search import scan
from .store import PriceStore

STATIC = Path(__file__).with_name("static")


def request_from_params(q: dict[str, str]) -> SearchRequest:
    from .cli import codes, parse_date_range, parse_stays

    start, end = parse_date_range(q.get("depart") or None)
    destinations = codes(q.get("to") or "DUB")
    if q.get("nearby") in ("1", "true", "on"):
        destinations += [d for d in NEARBY_DESTINATIONS if d not in destinations]
    max_stops = q.get("max_stops")
    max_hours = q.get("max_hours")
    return SearchRequest(
        origins=codes(q.get("from") or "PER"),
        destinations=destinations,
        depart_from=start,
        depart_to=end,
        stays=parse_stays(q.get("stay") or None),
        adults=max(1, int(q.get("adults") or 1)),
        currency=(q.get("currency") or "AUD").upper(),
        max_stops=int(max_stops) if max_stops not in (None, "", "any") else None,
        max_duration_hours=float(max_hours) if max_hours else None,
        airlines=[c.strip().upper() for c in q["airline"].split(",")] if q.get("airline") else None,
        max_live_queries=min(40, int(q.get("max_queries") or 12)),
    )


def make_handler(settings: Settings, providers: list[Provider], store: PriceStore | None):
    scan_lock = threading.Lock()  # providers keep per-run state; one scan at a time

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter console
            pass

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload) -> None:
            self._send(status, json.dumps(payload).encode(), "application/json")

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            q = {k: v[-1] for k, v in parse_qs(url.query).items()}
            if url.path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/search":
                self._search(q)
            elif url.path == "/api/history":
                self._history(q)
            elif url.path == "/api/providers":
                self._json(200, {"providers": [p.name for p in providers]})
            else:
                self._send(404, b"not found", "text/plain")

        def _search(self, q):
            try:
                req = request_from_params(q)
            except Exception as e:
                return self._json(400, {"error": str(e)})
            try:
                with scan_lock:
                    result = scan(req, providers, store)
            except Exception as e:
                traceback.print_exc()
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})
            try:
                items = sort_itineraries(
                    result.itineraries,
                    q.get("sort") or "price",
                    settings.value_of_time,
                    settings.stop_penalty,
                )
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            limit = min(200, int(q.get("limit") or 50))
            self._json(
                200,
                {
                    "providers": result.providers,
                    "errors": result.errors,
                    "live_queries": result.live_queries,
                    "demo": "demo" in result.providers,
                    "cheapest": result.cheapest.to_dict() if result.cheapest else None,
                    "calendar": [
                        {"date": d.isoformat(), "price": it.price, "currency": it.currency}
                        for d, it in result.calendar().items()
                    ],
                    "results": [it.to_dict() for it in items[:limit]],
                    "count": len(items),
                },
            )

        def _history(self, q):
            if store is None:
                return self._json(200, {"history": []})
            demo = all(p.name == "demo" for p in providers)
            rows = store.daily_lows(
                (q.get("from") or "PER").upper(),
                (q.get("to") or "DUB").upper(),
                "return" if q.get("trip") == "return" else "one_way",
                (q.get("currency") or "AUD").upper(),
                demo=demo,
            )
            self._json(200, {"history": [{"day": d, "price": p} for d, p in rows]})

    return Handler


def serve(settings, providers, store, host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(settings, providers, store))
    names = ", ".join(p.name for p in providers)
    print(f"Flight finder dashboard on http://{host}:{port}  (sources: {names})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
