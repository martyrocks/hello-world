import unittest
from datetime import date

from flightfinder.alerts import AlertRules, Notifier, pick_alerts, process_alerts
from flightfinder.config import Settings
from flightfinder.models import Itinerary, Query, SearchRequest
from flightfinder.providers.base import Provider, ProviderError
from flightfinder.scoring import deal_score, label_for, score_all, sort_itineraries
from flightfinder.search import candidate_combos, choose_live_combos, dedupe, scan, spread
from flightfinder.store import PriceStore


def fare(price, day=4, ret=None, stops=1, provider="x", airlines=("QR",), minutes=1400, live=True):
    return Itinerary(
        provider=provider, origin="PER", destination="DUB",
        departure_date=date(2026, 11, day), return_date=ret, price=price, currency="AUD",
        airlines=airlines, stops=stops, duration_minutes=minutes, is_live=live,
    )


class FakeCached(Provider):
    name = "cached"
    is_live = False

    def search(self, query):
        return []

    def scout(self, origin, destination, month, one_way, currency):
        outside_window = Itinerary(
            provider="cached", origin="PER", destination="DUB",
            departure_date=date(2026, 12, 25), price=500, currency="AUD", is_live=False,
        )
        return [fare(900, day=20, live=False), fare(950, day=7, live=False), outside_window]


class FakeLive(Provider):
    name = "live"

    def __init__(self):
        super().__init__()
        self.calls: list[Query] = []

    def search(self, query):
        self.calls.append(query)
        return [fare(1000 + query.departure_date.day, day=query.departure_date.day, provider="live")]


class Broken(Provider):
    name = "broken"

    def search(self, query):
        raise ProviderError("broken: boom")


class ScoringTests(unittest.TestCase):
    def test_score_shape(self):
        self.assertEqual(deal_score(1000, 1000, 2000), 80)
        self.assertEqual(deal_score(2000, 1000, 2000), 20)
        self.assertEqual(deal_score(700, 1000, 2000), 100)
        self.assertEqual(deal_score(3000, 1000, 2000), 0)
        scores = [deal_score(p, 1000, 2000) for p in range(500, 3500, 100)]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_labels(self):
        self.assertEqual(label_for(95), "Exceptional")
        self.assertEqual(label_for(60), "Good")
        self.assertEqual(label_for(3), "Poor")

    def test_error_fare_flag_and_default_baseline(self):
        cheap, normal = fare(500), fare(1500)
        score_all([cheap, normal], {})
        self.assertIn("possible error fare", cheap.flags)
        self.assertNotIn("possible error fare", normal.flags)
        self.assertGreater(cheap.deal_score, normal.deal_score)

    def test_sorting(self):
        slow_cheap = fare(1000, minutes=40 * 60, stops=3)
        fast = fare(1100, minutes=20 * 60, stops=1)
        self.assertIs(sort_itineraries([fast, slow_cheap], "price")[0], slow_cheap)
        self.assertIs(sort_itineraries([slow_cheap, fast], "best")[0], fast)
        self.assertIs(sort_itineraries([slow_cheap, fast], "duration")[0], fast)
        with self.assertRaises(ValueError):
            sort_itineraries([fast], "nope")


class ScanTests(unittest.TestCase):
    def req(self, **kw):
        base = dict(origins=["PER"], destinations=["DUB"],
                    depart_from=date(2026, 11, 1), depart_to=date(2026, 11, 30))
        base.update(kw)
        return SearchRequest(**base)

    def test_candidates_and_spread(self):
        r = self.req(depart_to=date(2026, 11, 3), stays=[14, 21])
        combos = candidate_combos(r)
        self.assertEqual(len(combos), 6)
        self.assertEqual(combos[1], ("PER", "DUB", date(2026, 11, 1), date(2026, 11, 22)))
        self.assertEqual(spread(list(range(10)), 3), [0, 4, 9])
        self.assertEqual(spread([1, 2], 5), [1, 2])

    def test_scouted_dates_are_priced_first(self):
        r = self.req()
        scouted = [fare(900, day=20), fare(950, day=7)]
        chosen = choose_live_combos(candidate_combos(r), scouted, 4)
        self.assertEqual([c[2].day for c in chosen[:2]], [20, 7])
        self.assertEqual(len(chosen), 4)

    def test_scan_end_to_end(self):
        live, store = FakeLive(), PriceStore(":memory:")
        result = scan(self.req(max_live_queries=5), [FakeCached(), live, Broken()], store)
        self.assertEqual(len(live.calls), 5)
        self.assertEqual(result.live_queries, 10)  # 5 combos x 2 metered live providers
        self.assertEqual(result.errors, ["broken: boom"])
        self.assertEqual(result.cheapest.price, 900)  # cached scout fare, in window
        self.assertNotIn(date(2026, 12, 25), [i.departure_date for i in result.itineraries])
        self.assertTrue(all(i.deal_score is not None for i in result.itineraries))
        self.assertEqual(store.lowest_seen("PER", "DUB", "one_way", "AUD"), 900)

    def test_filters(self):
        result = scan(self.req(max_stops=0), [FakeLive()], None)
        self.assertEqual(result.itineraries, [])

    def test_dedupe_keeps_cheapest(self):
        a, b, c = fare(1000), fare(990), fare(990, live=False)
        self.assertEqual([i.price for i in dedupe([a, b])], [990])
        [kept] = dedupe([c, b])
        self.assertTrue(kept.is_live)


class AlertTests(unittest.TestCase):
    def test_rules(self):
        items = [fare(1500), fare(1200, day=5), fare(900, day=6)]
        score_all(items, {})
        hits = pick_alerts(items, AlertRules(below_price=1000, min_score=None), {})
        self.assertEqual([h[0].price for h in hits], [900])
        hits = pick_alerts(items, AlertRules(min_score=None), {("PER", "DUB", "one_way"): 1300})
        self.assertEqual([h[0].price for h in hits], [900])  # one new-low alert per route
        self.assertIn("new lowest price", hits[0][1])

    def test_no_repeat_alerts(self):
        store, sent = PriceStore(":memory:"), []
        settings = Settings.from_env()
        settings.webhook_url = settings.smtp_host = None
        notifier = Notifier(settings, console=sent.append)
        items = [fare(800)]
        score_all(items, {})
        rules = AlertRules(min_score=50)
        self.assertEqual(len(process_alerts(items, rules, store, notifier, {})), 1)
        self.assertEqual(len(process_alerts(items, rules, store, notifier, {})), 0)
        items[0].price = 750  # cheaper again -> alert again
        self.assertEqual(len(process_alerts(items, rules, store, notifier, {})), 1)


if __name__ == "__main__":
    unittest.main()
