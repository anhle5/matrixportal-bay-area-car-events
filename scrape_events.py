#!/usr/bin/env python3
"""
Scrape upcoming Bay Area / Monterey car events from bayareamotorevents.com.

The site is a JS SPA, so we use the public sitemap event URLs (slugs encode
dates / recurrence) and expand them into a simple JSON feed for MatrixPortal.
"""

from __future__ import annotations

import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from calendar import monthcalendar
from datetime import date, timedelta
from pathlib import Path

SITEMAP_URL = "https://bayareamotorevents.com/sitemap.xml"
OUT_PATH = Path(__file__).resolve().parent / "events.json"
USER_AGENT = "matrixportal-car-events/1.0 (+local scraper)"

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

PLACE_HINTS = [
    ("san-francisco", "SF"),
    ("san-jose", "San Jose"),
    ("monterey", "Monterey"),
    ("pebble-beach", "Pebble Beach"),
    ("laguna-seca", "Laguna Seca"),
    ("pleasanton", "Pleasanton"),
    ("menlo-park", "Menlo Park"),
    ("redwood-city", "Redwood City"),
    ("portola-valley", "Portola Valley"),
    ("san-rafael", "San Rafael"),
    ("san-carlos", "San Carlos"),
    ("morgan-hill", "Morgan Hill"),
    ("willow-glen", "San Jose"),
    ("aptos", "Aptos"),
    ("seaside", "Seaside"),
    ("carmel", "Carmel"),
    ("pacific-grove", "Pacific Grove"),
    ("livermore", "Livermore"),
    ("fremont", "Fremont"),
    ("gilroy", "Gilroy"),
    ("martinez", "Martinez"),
    ("marin", "Marin"),
    ("napa", "Napa"),
    ("sonoma", "Sonoma"),
    ("oakland", "Oakland"),
    ("berkeley", "Berkeley"),
    ("palo-alto", "Palo Alto"),
    ("mountain-view", "Mountain View"),
    ("santa-clara", "Santa Clara"),
    ("santa-cruz", "Santa Cruz"),
    ("salinas", "Salinas"),
    ("milpitas", "Milpitas"),
    ("concord", "Concord"),
    ("walnut-creek", "Walnut Creek"),
    ("blackhawk", "Danville"),
    ("pier-32", "SF"),
    ("fort-mason", "SF"),
    ("peninsula", "Peninsula"),
    ("east-bay", "East Bay"),
    ("south-bay", "South Bay"),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def title_from_slug(slug: str) -> str:
    # Drop trailing date / recurrence tokens for a readable name.
    s = slug
    s = re.sub(
        r"-(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|"
        r"aug|august|sep|sept|september|oct|october|nov|november|dec|december)"
        r"(?:-\d{1,2}(?:-\d{1,2})?)?-20\d{2}$",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"-(1st|2nd|3rd|4th|first|second|third|fourth|last|every)-"
        r"(sunday|saturday|thursday|monday|tuesday|wednesday|friday)"
        r"(-monthly|-of-the-mo|-of-ev|-of-every|-monthl)?$",
        "",
        s,
        flags=re.I,
    )
    s = s.replace("-", " ").strip()
    s = re.sub(r"\s+", " ", s)
    titled = s.title()
    titled = re.sub(r"\b(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), titled)
    return (
        titled.replace(" And ", " & ")
        .replace(" Cnc", " C&C")
        .replace("Pcnc", "PCNC")
        .replace("Sf ", "SF ")
    )


def place_from_slug(slug: str) -> str:
    for key, place in PLACE_HINTS:
        if key in slug:
            return place
    return "Bay Area"


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date | None:
    """weekday: Mon=0 .. Sun=6. n: 1..4 or -1 for last."""
    cal = monthcalendar(year, month)
    days = [week[weekday] for week in cal if week[weekday] != 0]
    if not days:
        return None
    if n == -1:
        return date(year, month, days[-1])
    if 1 <= n <= len(days):
        return date(year, month, days[n - 1])
    return None


def expand_recurring(slug: str, today: date, until: date) -> list[date]:
    rules = [
        (r"1st-sunday|first-sunday", 6, 1),
        (r"2nd-sunday|second-sunday", 6, 2),
        (r"3rd-sunday|third-sunday", 6, 3),
        (r"4th-sunday|fourth-sunday", 6, 4),
        (r"last-sunday", 6, -1),
        (r"1st-saturday|first-saturday", 5, 1),
        (r"2nd-saturday|second-saturday", 5, 2),
        (r"3rd-saturday|third-saturday", 5, 3),
        (r"4th-saturday|fourth-saturday", 5, 4),
        (r"last-saturday", 5, -1),
        (r"last-thursday", 3, -1),
        (r"every-sunday", 6, 0),  # special: weekly
    ]
    for pat, weekday, n in rules:
        if re.search(pat, slug, re.I):
            out = []
            if n == 0:  # weekly
                d = today
                while d.weekday() != weekday:
                    d += timedelta(days=1)
                while d <= until:
                    out.append(d)
                    d += timedelta(days=7)
                return out
            y, m = today.year, today.month
            while date(y, m, 1) <= until:
                d = nth_weekday(y, m, weekday, n)
                if d and d >= today:
                    out.append(d)
                if m == 12:
                    y, m = y + 1, 1
                else:
                    m += 1
            return out
    return []


def parse_dated_slug(slug: str) -> list[date]:
    """Parse ...-aug-21-2026 or ...-aug-21-23-2026 into date list."""
    m = re.search(
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|"
        r"aug|august|sep|sept|september|oct|october|nov|november|dec|december)"
        r"-(\d{1,2})(?:-(\d{1,2}))?-?(20\d{2})$",
        slug,
        re.I,
    )
    if not m:
        # multi-month oddballs like sept-5-oct-3-nov-7 — skip for now
        return []
    month = MONTHS[m.group(1).lower()]
    d1 = int(m.group(2))
    d2 = int(m.group(3)) if m.group(3) else None
    year = int(m.group(4))
    if d2 and d2 > d1:
        return [date(year, month, d) for d in range(d1, d2 + 1)]
    return [date(year, month, d1)]


def event_urls_from_sitemap() -> list[str]:
    xml = fetch(SITEMAP_URL)
    root = ET.fromstring(xml)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [el.text for el in root.findall(".//s:loc", ns) if el.text]
    return [u for u in locs if "/events/" in u]


def build_events(today: date | None = None) -> list[dict]:
    today = today or date.today()
    until = today + timedelta(days=120)
    events: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for url in event_urls_from_sitemap():
        slug = url.rstrip("/").split("/")[-1]
        name = title_from_slug(slug)
        place = place_from_slug(slug)

        dates = parse_dated_slug(slug)
        if not dates:
            dates = expand_recurring(slug, today, until)
        dates = [d for d in dates if today <= d <= until]
        for d in dates:
            key = (d.isoformat(), name.lower())
            if key in seen:
                continue
            seen.add(key)
            events.append(
                {
                    "date": d.isoformat(),
                    "name": name[:48],
                    "place": place,
                    "source": "bayareamotorevents",
                    "url": url,
                }
            )

    events.sort(key=lambda e: (e["date"], e["name"]))
    return events


def main() -> None:
    events = build_events()
    payload = {
        "updated": date.today().isoformat(),
        "source": SITEMAP_URL,
        "count": len(events),
        "events": events,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {len(events)} events -> {OUT_PATH}")


if __name__ == "__main__":
    main()
