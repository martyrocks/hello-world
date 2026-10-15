"""Deal alerts: console, webhook (Slack/Discord/ntfy-style JSON) and email."""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from .config import Settings
from .http import request_json
from .models import Itinerary
from .store import PriceStore, trip_kind


@dataclass
class AlertRules:
    below_price: float | None = None  # alert when a fare is under this price
    min_score: int | None = 85  # alert on "Exceptional"-ish deals
    new_low: bool = True  # alert when a fare beats everything seen before
    max_alerts: int = 5  # per run, cheapest first


def pick_alerts(
    itineraries: list[Itinerary],
    rules: AlertRules,
    previous_low: dict[tuple[str, str, str], float | None],
) -> list[tuple[Itinerary, str]]:
    """Return (itinerary, reason) pairs that deserve an alert, cheapest first."""
    hits: list[tuple[Itinerary, str]] = []
    lows_flagged: set[tuple[str, str, str]] = set()
    for it in sorted(itineraries, key=lambda i: i.price):
        route = (it.origin, it.destination, trip_kind(it))
        reason = None
        if rules.below_price is not None and it.price <= rules.below_price:
            reason = f"under your target of {rules.below_price:,.0f} {it.currency}"
        elif rules.min_score is not None and (it.deal_score or 0) >= rules.min_score:
            reason = f"{it.deal_label} deal (score {it.deal_score})"
        elif rules.new_low and route not in lows_flagged:
            prev = previous_low.get(route)
            if prev is not None and it.price < prev:
                reason = f"new lowest price (previous low {prev:,.0f} {it.currency})"
        if "possible error fare" in it.flags:
            reason = (reason + "; " if reason else "") + "possible error fare - book fast"
        if reason:
            hits.append((it, reason))
            lows_flagged.add(route)
        if len(hits) >= rules.max_alerts:
            break
    return hits


def alert_key(it: Itinerary) -> str:
    return "|".join(
        [
            it.origin,
            it.destination,
            it.departure_date.isoformat(),
            it.return_date.isoformat() if it.return_date else "-",
            "+".join(it.airlines),
            str(it.stops),
        ]
    )


def format_alert(it: Itinerary, reason: str) -> str:
    dates = it.departure_date.strftime("%a %d %b %Y")
    if it.return_date:
        dates += " -> " + it.return_date.strftime("%a %d %b %Y")
    via = f" via {', '.join(it.via)}" if it.via else ""
    dur = f", {it.duration_hours:.1f}h" if it.duration_minutes else ""
    lines = [
        f"✈️  {it.origin} → {it.destination}: {it.price:,.0f} {it.currency} ({reason})",
        f"    {dates} | {'/'.join(it.airlines) or 'airline n/a'} | "
        f"{it.stops} stop{'s' if it.stops != 1 else ''}{via}{dur} | source: {it.provider}",
    ]
    if it.flags:
        lines.append(f"    notes: {', '.join(it.flags)}")
    if it.booking_url:
        lines.append(f"    book: {it.booking_url}")
    return "\n".join(lines)


class Notifier:
    def __init__(self, settings: Settings, console=print):
        self.settings = settings
        self.console = console

    def send(self, hits: list[tuple[Itinerary, str]]) -> list[str]:
        """Deliver alerts on every configured channel. Returns delivery errors."""
        if not hits:
            return []
        body = "\n\n".join(format_alert(it, why) for it, why in hits)
        subject = (
            f"Flight deal: {hits[0][0].origin}→{hits[0][0].destination} "
            f"{hits[0][0].price:,.0f} {hits[0][0].currency}"
        )
        self.console(f"\n=== {subject} ===\n{body}\n")
        errors = []
        s = self.settings
        if s.webhook_url:
            try:
                # "text" for Slack/Mattermost, "content" for Discord.
                request_json("POST", s.webhook_url, body={"text": body, "content": body[:1900]})
            except Exception as e:
                errors.append(f"webhook: {e}")
        if s.smtp_host and s.email_to:
            try:
                msg = EmailMessage()
                msg["Subject"] = subject
                msg["From"] = s.email_from or s.email_to
                msg["To"] = s.email_to
                msg.set_content(body)
                with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
                    smtp.starttls()
                    if s.smtp_user:
                        smtp.login(s.smtp_user, s.smtp_password or "")
                    smtp.send_message(msg)
            except Exception as e:
                errors.append(f"email: {e}")
        return errors


def process_alerts(
    itineraries: list[Itinerary],
    rules: AlertRules,
    store: PriceStore,
    notifier: Notifier,
    previous_low: dict[tuple[str, str, str], float | None],
) -> list[tuple[Itinerary, str]]:
    hits = [
        (it, why)
        for it, why in pick_alerts(itineraries, rules, previous_low)
        if store.should_alert(alert_key(it), it.price)
    ]
    for err in notifier.send(hits):
        notifier.console(f"warning: alert delivery failed: {err}")
    for it, _ in hits:
        store.mark_alerted(alert_key(it), it.price)
    return hits
