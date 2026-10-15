import unittest
from datetime import date

from flightfinder.models import Query
from flightfinder.providers.base import parse_iso_duration
from flightfinder.providers.demo import DemoProvider
from flightfinder.providers.duffel import DuffelProvider
from flightfinder.providers.serpapi import SerpApiProvider
from flightfinder.providers.travelpayouts import TravelpayoutsProvider, months_between

TRAVELPAYOUTS = {
    "success": True,
    "currency": "aud",
    "data": [
        {
            "origin": "PER", "destination": "DUB", "origin_airport": "PER",
            "destination_airport": "DUB", "price": 1187, "airline": "QR",
            "flight_number": "901", "departure_at": "2026-11-04T18:45:00+08:00",
            "return_at": "", "transfers": 1, "return_transfers": 0,
            "duration": 1390, "duration_to": 1390, "duration_back": 0,
            "link": "/search/PER0411DUB1?t=QR17782",
        },
        {"origin": "PER", "destination": "DUB", "price": "bad", "departure_at": "x"},
    ],
}

DUFFEL = {
    "data": {
        "offers": [
            {
                "total_amount": "1534.20",
                "total_currency": "AUD",
                "slices": [
                    {
                        "duration": "PT23H35M",
                        "segments": [
                            {
                                "origin": {"iata_code": "PER"},
                                "destination": {"iata_code": "DXB"},
                                "departing_at": "2026-11-04T21:55:00",
                                "arriving_at": "2026-11-05T04:50:00",
                                "marketing_carrier": {"iata_code": "EK"},
                                "marketing_carrier_flight_number": "421",
                            },
                            {
                                "origin": {"iata_code": "DXB"},
                                "destination": {"iata_code": "DUB"},
                                "departing_at": "2026-11-05T08:20:00",
                                "arriving_at": "2026-11-05T12:30:00",
                                "marketing_carrier": {"iata_code": "EK"},
                                "marketing_carrier_flight_number": "161",
                            },
                        ],
                    }
                ],
            }
        ]
    }
}

SERPAPI = {
    "search_metadata": {"google_flights_url": "https://www.google.com/travel/flights?x"},
    "price_insights": {"lowest_price": 1290, "price_level": "low",
                       "typical_price_range": [1350, 1900]},
    "best_flights": [
        {
            "flights": [
                {"departure_airport": {"id": "PER", "time": "2026-11-04 18:45"},
                 "arrival_airport": {"id": "DOH", "time": "2026-11-05 00:30"},
                 "airline": "Qatar Airways", "flight_number": "QR 901"},
                {"departure_airport": {"id": "DOH", "time": "2026-11-05 02:10"},
                 "arrival_airport": {"id": "DUB", "time": "2026-11-05 07:30"},
                 "airline": "Qatar Airways", "flight_number": "QR 17",
                 "often_delayed_by_over_30_min": True},
            ],
            "layovers": [{"id": "DOH", "duration": 100, "name": "Hamad", "overnight": True}],
            "total_duration": 1365,
            "price": 1290,
        }
    ],
    "other_flights": [{"flights": []}],
}

Q = Query(origin="PER", destination="DUB", departure_date=date(2026, 11, 4))


class ProviderParsingTests(unittest.TestCase):
    def test_iso_duration(self):
        self.assertEqual(parse_iso_duration("PT23H35M"), 23 * 60 + 35)
        self.assertEqual(parse_iso_duration("P1DT2H"), 26 * 60)
        self.assertIsNone(parse_iso_duration("nonsense"))
        self.assertIsNone(parse_iso_duration(None))

    def test_months_between(self):
        self.assertEqual(
            months_between(date(2026, 11, 20), date(2027, 1, 3)),
            ["2026-11", "2026-12", "2027-01"],
        )

    def test_travelpayouts(self):
        items = TravelpayoutsProvider("t", marker="123").parse(TRAVELPAYOUTS, "AUD")
        self.assertEqual(len(items), 1)  # malformed row skipped
        it = items[0]
        self.assertEqual((it.price, it.currency, it.stops), (1187.0, "AUD", 1))
        self.assertEqual(it.departure_date, date(2026, 11, 4))
        self.assertIsNone(it.return_date)
        self.assertFalse(it.is_live)
        self.assertEqual(
            it.booking_url, "https://www.aviasales.com/search/PER0411DUB1?t=QR17782&marker=123"
        )

    def test_duffel(self):
        [it] = DuffelProvider("t").parse(DUFFEL, Q)
        self.assertEqual(it.price, 1534.20)
        self.assertEqual(it.stops, 1)
        self.assertEqual(it.via, ("DXB",))
        self.assertEqual(it.airlines, ("EK",))
        self.assertEqual(it.duration_minutes, 23 * 60 + 35)
        self.assertEqual([s.flight_number for s in it.segments], ["421", "161"])
        self.assertIn("google.com/travel/flights", it.booking_url)

    def test_serpapi(self):
        p = SerpApiProvider("k")
        [it] = p.parse(SERPAPI, Q)
        self.assertEqual((it.price, it.stops, it.via), (1290.0, 1, ("DOH",)))
        self.assertEqual(it.airlines, ("Qatar Airways",))
        self.assertIn("overnight layover", it.flags)
        self.assertIn("often delayed", it.flags)
        self.assertEqual(p.typical_ranges[("PER", "DUB", "one_way", "AUD")], [(1350.0, 1900.0)])

    def test_demo_is_deterministic_and_flagged(self):
        a = DemoProvider().search(Q)
        b = DemoProvider().search(Q)
        self.assertEqual([i.price for i in a], [i.price for i in b])
        self.assertTrue(all("demo data" in i.flags for i in a))
        self.assertTrue(all(i.stops >= 1 for i in a))  # no nonstop PER-DUB exists

    def test_demo_respects_max_stops_and_return(self):
        q = Query("PER", "DUB", date(2026, 11, 4), date(2026, 11, 25), max_stops=1)
        items = DemoProvider().search(q)
        self.assertTrue(items)
        self.assertTrue(all(i.stops <= 1 and i.return_date == date(2026, 11, 25) for i in items))


if __name__ == "__main__":
    unittest.main()
