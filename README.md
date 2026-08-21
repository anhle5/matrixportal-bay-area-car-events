# MatrixPortal Bay Area car events feed

Daily-scraped JSON of Bay Area / Monterey car meets from
[bayareamotorevents.com](https://bayareamotorevents.com/) for an Adafruit MatrixPortal.

## Files

- `scrape_events.py` — builds `events.json` from the site sitemap
- `events.json` — feed the MatrixPortal downloads
- `.github/workflows/daily-scrape.yml` — refreshes the feed every day

## Run locally

```bash
python3 scrape_events.py
```

## MatrixPortal

In `settings.toml` on the CIRCUITPY drive:

```toml
EVENTS_JSON_URL = "https://raw.githubusercontent.com/<you>/matrixportal-car-events/main/events.json"
```

`code.py` fetches that URL over WiFi and rotates upcoming events.
