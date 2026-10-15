# Perth → Dublin flight finder

Searches for the cheapest flights from **Perth (PER) to Dublin (DUB)**. It takes
the useful ideas from [Ratepunk Flights](docs/RATEPUNK_ANALYSIS.md) (scanning
around the clock, a deal score, mistake-fare detection and price alerts) and
points them at the one route you care about, on the dates you choose.

- **Searches many dates at once.** Give it a month or a date range, one-way or
  return with a range of trip lengths.
- **Combines several fare sources.** It uses Travelpayouts/Aviasales (free,
  cached fares), Duffel (live airline offers) and Google Flights through
  SerpApi, and removes duplicate fares.
- **Scouts first, then checks.** Free month-wide lookups find the cheap dates;
  paid live searches are spent only on those dates (`--max-queries`).
- **Gives each fare a deal score (0–100).** It compares the fare with the
  route's typical price and flags possible mistake fares.
- **Sorts several ways:** cheapest, best value (price vs. travel time and
  stops), fastest, fewest stops, deal score or date.
- **Watches prices and sends alerts.** Alerts go to the console, email or a
  Slack/Discord webhook, and the same deal is never alerted twice.
- **Keeps a price history** in a local SQLite database and charts the
  cheapest fare per day.
- **Has a web dashboard** with a price calendar and a sortable results table.
- **Needs no third-party packages,** only Python 3.10+.

## Quick start

```bash
cd perth-dublin-flights
python3 -m flightfinder search --depart 2026-11 --calendar
```

With no API keys set, it uses **demo data**: synthetic fares shaped like the
real route, clearly labelled as demo. To get real fares, add at least one key:

```bash
cp .env.example .env      # then fill in one or more keys
python3 -m flightfinder providers
```

| Source | Key | What it gives you | Cost |
|---|---|---|---|
| [Travelpayouts](https://www.travelpayouts.com/) (Aviasales Data API) | `TRAVELPAYOUTS_TOKEN` | Cached fares from the last ~48h for a whole month in one call. Used as the scout | Free |
| [SerpApi](https://serpapi.com/google-flights-api) Google Flights | `SERPAPI_KEY` | Live Google Flights results plus Google's typical price range for the route | Free tier, then paid per search |
| [Duffel](https://duffel.com/) | `DUFFEL_ACCESS_TOKEN` | Live, bookable airline offers. `duffel_test_` tokens return sandbox data | Free to search; paid per booking |

Recommended setup: **Travelpayouts plus SerpApi**. Travelpayouts finds the
cheap dates for free, and SerpApi checks those dates with live Google Flights
prices.

## Usage

```bash
# Cheapest one-way fares in November, with a price-per-day chart
python3 -m flightfinder search --depart 2026-11 --calendar

# Return trips of 14–28 nights leaving between 10 Nov and 15 Dec, best value first
python3 -m flightfinder search --depart 2026-11-10:2026-12-15 --stay 14-28 --sort best

# Max 1 stop, max 26 hours, also try Cork, Shannon and Belfast, show prices in euros
python3 -m flightfinder search --depart 2027-02 --max-stops 1 --max-hours 26 --nearby --currency EUR

# JSON output (for scripts)
python3 -m flightfinder search --depart 2026-11 --json

# Re-scan every 6 hours. Alert below A$1,000, on deals scoring 85+, or on a new lowest price
python3 -m flightfinder watch --depart 2026-11-01:2027-02-28 --below 1000 --every 6h

# ...or let cron run it (every 6 hours)
# 0 */6 * * *  cd /path/to/perth-dublin-flights && python3 -m flightfinder watch --once -q

# Web dashboard at http://127.0.0.1:8000
python3 -m flightfinder serve

# Daily lowest fare seen so far
python3 -m flightfinder history --trip one-way
```

Run `python3 -m flightfinder <command> --help` to see every option. Useful ones:

| Option | Meaning |
|---|---|
| `--from PER` / `--to DUB` | Airports; comma-separate several, e.g. `--to DUB,ORK` |
| `--depart` | `YYYY-MM`, `YYYY-MM-DD` or `START:END` (default: 3 to 13 weeks from today) |
| `--stay` | Return trip length in nights, e.g. `21` or `14-28` (left out = one-way) |
| `--max-queries` | How many date combinations to price with paid live sources (default 12) |
| `--sort` | `price`, `best`, `duration`, `stops`, `score`, `date` |
| `--providers` | Use only some sources, e.g. `--providers serpapi` |
| `--airline` | Only fares flown entirely by these airlines, e.g. `--airline QR` |

## How it works

```
SearchRequest ──► scout (cached, whole months) ──► choose dates ──► live providers (parallel)
                                                                       │
     alerts ◄── price history (SQLite) ◄── deal score ◄── filter + dedupe
```

1. **Scout.** Cached sources return the cheapest recently seen fares for each
   month in your range.
2. **Pick dates.** The cheapest dates the scout found come first. The rest of
   the `--max-queries` budget goes on dates spread evenly across your range,
   so a live-only fare isn't missed.
3. **Price live.** Duffel and Google Flights are queried in parallel. If one
   source fails, you get a warning, but the scan still finishes.
4. **Filter, remove duplicates, score.** Each fare's deal score compares it
   with the route's typical range. The range comes from Google's own figure if
   available, otherwise from the price history (once it has 30+ prices),
   otherwise from a built-in Perth→Dublin baseline (about A$1,100–1,800
   one-way, A$1,600–2,700 return).

   | Score | Label | Meaning |
   |---|---|---|
   | 90–100 | Exceptional | Well below the typical low |
   | 75–89 | Great | Around the bottom of the typical range |
   | 55–74 | Good | Lower half of the typical range |
   | 35–54 | Fair | Upper half |
   | 0–34 | Poor | At or above the typical high |

   Fares below 55% of the typical low get a **possible error fare** flag.
5. **Record and alert.** Every fare is saved to the price history, and `watch`
   applies your alert rules.

## Project layout

```
flightfinder/
  cli.py            command line (search / watch / serve / history / providers)
  search.py         scanner: scout → choose dates → live search → merge
  scoring.py        deal score, labels, sort orders
  store.py          SQLite price history and alert de-duplication
  alerts.py         alert rules, console / webhook / email delivery
  web.py, static/   dashboard
  providers/        travelpayouts.py, duffel.py, serpapi.py, demo.py
docs/RATEPUNK_ANALYSIS.md   what Ratepunk does and how this app compares
docs/QATAR_QR901_PER_DOH_DUB_2027-01-21.md   Qatar PER-DOH-DUB connection analysis + upgrade tips
tests/              unit and end-to-end tests (python3 -m unittest discover -s tests)
```

To add a new fare source, subclass `providers.base.Provider`, implement
`search(query)`, and register it in `providers/__init__.py`.

## Notes

- Prices from cached sources (marked *cached*) can be up to about 48 hours
  old. Always confirm the price on the booking site.
- Duffel prices offers in the airline's currency. If that differs from the
  currency you asked for, the fare is flagged.
- No public API covers every airline. Running more than one source gives the
  best coverage.
