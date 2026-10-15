# Qatar Airways, Perth → Doha → Dublin, Thursday 21 January 2027

*Researched 15 October 2026. The next Thursday that falls on the 21st is
21 January 2027 (21 October 2026 is a Wednesday). Qatar has not reliably
published its January 2027 timetable yet. The times below come from
third-party flight trackers covering Qatar's winter 2026/27 schedule, and
those sources don't all agree. **Confirm the times on qatarairways.com
before booking.***

## The connection at a glance

| Leg | Flight | Departs | Arrives | Flight time | Aircraft (usual) |
|---|---|---|---|---|---|
| 1 | **QR901** Perth → Doha | Thu 21 Jan, **22:45** AWST | Fri 22 Jan, **~05:10** AST | ~11h 25m (overnight) | Boeing 777-300ER (A350-900 on some dates) |
| — | Connection at Hamad International (DOH) | | | **~2h 55m** | |
| 2 | **QR19** Doha → Dublin | Fri 22 Jan, **~08:05** AST | Fri 22 Jan, **~12:50** GMT | ~7h 45m | Varies; check the seat map |

**Total journey: about 22 hours.** Time zones: Perth UTC+8, Doha UTC+3,
Dublin UTC+0 in January. You leave Thursday night and land in Dublin Friday
lunchtime.

### Other Doha → Dublin departures that day, and why QR19 is the one to pick

| Flight | Departs DOH | Wait at Doha | Verdict |
|---|---|---|---|
| **QR19** | ~08:05 | ~2h 55m | **Best.** Enough time to connect, without a long wait. |
| QR45 | ~15:20 | ~10h | Only worth it if you want a day in Doha. Book this one as a single ticket so the connection stays protected. |
| QR17 | ~01:30 (Sat) | ~20h | It left before you landed. The next one is effectively a stopover. |

Sources disagree on DOH–DUB times. One listing shows QR17 at 05:00 on a
787-9, another at 08:00, and they differ by season. Whichever flight leaves
Doha about 2½–4 hours after QR901 lands is the one you want.

### Connection risk

- QR901's actual departures in recent weeks ranged from about 7 minutes
  early to about 25 minutes late. Against a ~3-hour connection, that's
  comfortable.
- Book both legs on **one Qatar ticket**. Then if QR901 is late and you miss
  QR19, Qatar has to rebook you. Booking the two legs separately loses that
  protection.
- At Hamad, transfer passengers go through transfer security only, with no
  immigration. Under 3 hours is plenty of time.

## Price

- Typical Perth→Dublin fares are about **A$1,100–1,800 one-way** and
  **A$1,600–2,700 return**. Qatar's one-stop itinerary usually sits in the
  middle to upper part of that range. Slower two-stop routings via Asia are
  usually cheaper.
- 21 January falls in the WA school holidays, but it's after the Christmas
  peak. Expect mid-season prices, not the very cheapest (November and
  February are usually lower).
- To check real Qatar-only prices for that date and the days around it
  (needs an API key in `.env`, see the README):

  ```bash
  python3 -m flightfinder search --depart 2027-01-21 --airline QR --max-stops 1
  python3 -m flightfinder search --depart 2027-01-18:2027-01-24 --airline QR --calendar
  python3 -m flightfinder watch  --depart 2027-01-21 --airline QR --below 1300 --every 6h
  ```

## Getting an upgrade

**What to expect:** no email or script reliably gets a free upgrade on
Qatar. Free ("operational") upgrades happen mainly when economy is
overbooked, and they go first to Privilege Club Gold/Platinum members and
passengers on full-fare tickets. You can still improve your odds a lot, and
cheap paid or bid upgrades are far more common than free ones.

### Steps that actually move the odds (in order of impact)

1. **Join Privilege Club** (free) and put your number on the booking before
   check-in. Airlines rarely upgrade someone with no loyalty profile.
2. **Book directly with Qatar**, not through a travel agent or booking
   website. Avoid the very cheapest economy fare type, because the lowest
   booking classes are often excluded from upgrade and bid offers.
3. **Watch Manage Booking for an upgrade offer or bid.** Travel blogs report
   that bids usually open about 5 days before departure and close about 48
   hours before (not confirmed by Qatar). Bid on the **Perth → Doha** leg
   first: it's the 11-hour overnight flight, where a flat bed matters most.
4. **Check the Avios upgrade price.** Avios are Privilege Club's points, and
   buying them during a promotion can make an upgrade much cheaper than
   paying cash.
5. **At the airport:** check in early, travel solo if you can, dress smart
   casual, and be friendly. Ask whether there's an **airport upgrade price**.
   Last-minute fixed-price offers at the desk can be good value.
6. **If the flight is overbooked,** offer to be flexible. Volunteering
   sometimes gets you compensation, and occasionally a better seat.
7. **Mention a special occasion only if it's real.** Staff can see booking
   notes, and a made-up story can backfire.

### Email to send (Qatar Airways "Contact us" / Privilege Club form)

Fill in the brackets. Keep it short, warm and truthful.

> **Subject:** Upgrade request – booking [BOOKING REF], QR901/QR19, 21–22 January 2027
>
> Dear Qatar Airways team,
>
> I'm flying with you from Perth to Dublin on Thursday 21 January 2027, on
> QR901 to Doha and connecting to QR19 to Dublin (booking [BOOKING REF],
> Privilege Club [NUMBER]). I chose Qatar Airways for this trip because
> [your real reason, e.g. the reputation of your service / the smooth
> connection through Hamad].
>
> [Optional, only if true: The trip is for [special occasion, e.g. my
> 40th birthday / to see family I haven't seen in X years].]
>
> I'd be very grateful to be considered for an upgrade on the overnight
> Perth–Doha sector if there's availability. If a complimentary upgrade isn't
> possible, I'd also welcome details of any upgrade offer, bid or Avios
> option for the booking.
>
> Thank you for your time, and I'm looking forward to flying with you.
>
> Kind regards,
> [Name]
> [Phone] · [Email]

### What to say at check-in (Perth)

> "Hi! I'm flying through to Dublin tonight via Doha. Just wondering, is the
> flight full? If there's any chance of an upgrade on this leg, or an airport
> upgrade price, I'd love to hear it. No worries at all if not."

Then accept the answer graciously either way. Staff remember who was
pleasant, and that sometimes pays off on the next leg.

## Sources

- [QR901 on Trip.com (AU)](https://au.trip.com/flights/status-qr901/) · [FlightMapper QR901](https://info.flightmapper.net/flight/Qatar_Airways_QR_901) · [flight.info QR901](https://www.flight.info/QR901) · [FlightStats QR901](https://www.flightstats.com/v2/flight-tracker/QR/901)
- [Directflights DOH–DUB](https://www.directflights.com/DOH-DUB) · [Flightradar24 QR17](https://www.flightradar24.com/data/flights/qr17) · [Airportia QR17](https://www.airportia.com/flights/qr17/doha/dublin/) · [FlightsFrom DOH–DUB](https://www.flightsfrom.com/DOH-DUB)
- [Qatar Airways upgrade offer FAQs](https://www.qatarairways.com/en-kw/offers/offers/upgrade-offer-faqs.html) · [The Points Guy: Privilege Club](https://thepointsguy.com/loyalty-programs/qatar-airways-privilege-club/) · [Simple Flying: Privilege Club](https://simpleflying.com/how-most-qatar-airways-privilege-club/) · [Last-minute upgrade guide (blog)](https://tours-n-travel-pro.odoo.com/blog/news-2/qatar-airways-business-class-upgrade-18) · [LoyaltyLobby: 2026 policy changes](https://loyaltylobby.com/2026/05/22/qatar-airways-privilege-club-reduced-tier-retention-upgrade-policy-june-1-november-30-2026/)
