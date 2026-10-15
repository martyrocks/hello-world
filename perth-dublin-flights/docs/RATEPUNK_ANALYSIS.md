# Ratepunk: what it does and what this app borrows

*Researched October 2026. Most of the public information about Ratepunk comes
from Ratepunk's own website and blog, so the feature list and the savings
figures below are the company's own claims, not independently tested ones.*

## What Ratepunk is

Ratepunk launched in 2021 as a **free browser extension for comparing hotel
prices** (Chrome, Safari, Firefox). While you look at a hotel on one booking
site, it checks the same room on Booking.com, Expedia, Priceline, Agoda and
others, and pops up the cheapest rate.

Its main product now is **Ratepunk Flights**, a subscription deal-alert service:

| Feature | How Ratepunk describes it |
|---|---|
| Home airports | You choose your departure airport(s) (reviews mention up to 4) |
| 24/7 scanning | An "AI-powered" system scans the internet for cheap and hidden fares |
| Deal alerts | Deals are sent by email, so you don't have to search yourself |
| AI deal score | Each deal is rated so you can judge how good it really is |
| Error / mistake fares | Mistake fares and flash sales are flagged quickly, before they disappear |
| Dashboard | A web/app dashboard with dynamic sorting (cheapest, best, …) |
| Route pages | SEO pages per route, e.g. *Perth → Dublin*, showing recent cheap fares |
| Extras | Price-drop and rebooking alerts for hotels, cashback (up to 7%) |
| Pricing | Freemium / subscription (one blog post says $49/year), 14-day money-back |

### How it most likely works

Ratepunk doesn't publish how it works. Judging from its features, it probably
does three things:

1. **Collects fares at scale** from flight data feeds or by scraping metasearch
   sites, for many destinations from each subscriber's home airport.
2. **Compares each fare with that route's normal price.** This is where the
   "deal score" comes from: a fare well below the route's usual range is a
   deal, and one far below it may be a mistake fare.
3. **Sends alerts**, giving each subscriber only the deals from the airports
   they chose.

### Limitations for *your* goal (Perth → Dublin)

- **Ratepunk alerts on deals *from* your airport to anywhere.** You can't point
  it at one route and dates and have it find the cheapest PER→DUB fare.
- You **can't see how it works**: the data sources, how often it scans and how
  the deal score is calculated are all hidden.
- It costs a subscription, and it's tuned mainly for US and European airports.
  Perth has far fewer flights, so fewer deals will turn up.

## How this app reproduces the useful parts, focused on PER → DUB

| Ratepunk idea | This app |
|---|---|
| Scan the internet 24/7 | `watch` re-scans on a schedule (`--every 6h`), or runs from cron with `--once` |
| Many fare sources | Plug-in providers: Travelpayouts/Aviasales (cached), Duffel (live airline offers), Google Flights via SerpApi (live) |
| Efficient scanning | **Scout, then verify**: cheap month-wide cached lookups find promising dates, then a capped number of paid live searches price them |
| Up to 4 home airports | `--from PER,…` takes any number of origins; `--nearby` adds Cork, Shannon and Belfast as destinations |
| AI deal score | Transparent 0–100 score against the route's typical price range (Google's own range → your price history → a built-in PER-DUB baseline) |
| Error-fare detection | Flags fares under 55% of the typical low as *possible error fare* |
| Email alerts | Email (SMTP), Slack/Discord webhooks and console; rules for target price, deal score and new lowest price; never sends the same alert twice |
| Dynamic sorting | `--sort price | best | duration | stops | score | date`. "Best" weighs price against travel time and stops |
| Route pages / dashboard | `serve` runs a web dashboard with a calendar of the cheapest fare per day and a sortable results table |
| Price-drop tracking | Every scan is saved to SQLite; `history` shows the daily lowest fare over time |

## Perth → Dublin market notes (useful for interpreting results)

- There are **no nonstop flights**. Every itinerary has at least one stop.
- One-stop options usually go through the Gulf hubs (Doha with Qatar, Dubai
  with Emirates, Abu Dhabi with Etihad), or through London (Qantas nonstop
  PER–LHR, then Aer Lingus). Two-stop options through Asia (Singapore, Kuala
  Lumpur, Hong Kong, Istanbul) are often cheaper but slower.
- Public route summaries in 2026 put typical fares at roughly **A$1,100–1,800
  one-way** and **A$1,600–2,700 return**. Skyscanner names **November** as
  usually the cheapest month. Mid-December and the European summer
  (June–August) are the peaks.

### Sources

- [Ratepunk review (Ratepunk blog)](https://www.ratepunk.com/blog/ratepunk-review-is-it-a-scam-or-legit)
- [Ratepunk Perth → Dublin route page](https://www.ratepunk.com/flights-from-to/PER/DUB/cheap-flights-from-perth-to-dublin)
- [Skyscanner vs RatePunk (Ratepunk blog)](https://www.ratepunk.com/blog/skyscanner-vs-rate-punk-which-finds-better-deals)
- [Best Google Flights alternative (Ratepunk blog)](https://www.ratepunk.com/blog/post/best-google-flights-alternative-to-find-cheap-flights)
- [Cheapflights: Perth → Dublin](https://www.cheapflights.com.au/flights-to-Dublin/Perth/)
- [Skyscanner: Perth → Dublin](https://www.skyscanner.ie/routes/per/dub/perth-to-dublin.html)
- [Travelpayouts Aviasales Data API](https://support.travelpayouts.com/hc/en-us/articles/203956163)
- [Top flight APIs in 2026 (ScrapingBee)](https://www.scrapingbee.com/blog/top-flights-apis-for-travel-apps/)
