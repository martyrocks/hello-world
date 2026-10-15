import io
import json
import os
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stdout
from datetime import date
from http.server import ThreadingHTTPServer

from flightfinder.cli import main, parse_date_range, parse_interval, parse_stays
from flightfinder.config import Settings
from flightfinder.providers.demo import DemoProvider
from flightfinder.store import PriceStore
from flightfinder.web import make_handler

TODAY = date(2026, 10, 15)


class ParsingTests(unittest.TestCase):
    def test_date_ranges(self):
        self.assertEqual(parse_date_range("2026-11", TODAY), (date(2026, 11, 1), date(2026, 11, 30)))
        self.assertEqual(
            parse_date_range("2026-11-10:2026-12", TODAY), (date(2026, 11, 10), date(2026, 12, 31))
        )
        self.assertEqual(parse_date_range("2026-10", TODAY), (TODAY, date(2026, 10, 31)))
        self.assertEqual(parse_date_range(None, TODAY)[0], date(2026, 11, 5))
        with self.assertRaises(Exception):
            parse_date_range("2026-01", TODAY)

    def test_stays_and_intervals(self):
        self.assertIsNone(parse_stays(None))
        self.assertEqual(parse_stays("21"), [21])
        self.assertEqual(parse_stays("14-28"), [14, 21, 28])
        self.assertEqual(parse_stays("14-30"), [14, 21, 28, 30])
        self.assertEqual(parse_interval("6h"), 21600)
        self.assertEqual(parse_interval("30m"), 1800)


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "h.db")
        for k in ("TRAVELPAYOUTS_TOKEN", "DUFFEL_ACCESS_TOKEN", "SERPAPI_KEY"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_cli_search_json(self):
        nxt = date.today().replace(day=1)
        month = f"{nxt.year + (nxt.month // 12)}-{nxt.month % 12 + 1:02d}"
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["search", "--depart", month, "--json", "--db", self.db, "--limit", "5"])
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["providers"], ["demo"])
        prices = [r["price"] for r in data["results"]]
        self.assertEqual(prices, sorted(prices))
        self.assertEqual(len(prices), 5)

    def test_web_api(self):
        store = PriceStore(self.db)
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(Settings.from_env(), [DemoProvider()], store)
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            html = urllib.request.urlopen(base + "/").read().decode()
            self.assertIn("Perth", html)
            data = json.load(urllib.request.urlopen(base + "/api/search?stay=21&sort=best"))
            self.assertTrue(data["demo"])
            self.assertTrue(data["results"])
            self.assertTrue(all(r["return_date"] for r in data["results"]))
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(base + "/api/search?from=PERTH")
            self.assertEqual(ctx.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
