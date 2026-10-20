#!/usr/bin/env python3
"""Fetch next bin collection dates from Kirklees API and write a year's schedule to bins.csv.

Run this locally (not from Lambda) once a year when the new collection calendar starts.

Usage:
  KIRKLEES_UPRN=your_uprn python fetch_dates.py

After running, redeploy Lambda so the updated bins.csv is bundled in:
  ./deploy.sh
"""

import csv
import http.cookiejar
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

KIRKLEES_SESSION_URL = (
    "https://my.kirklees.gov.uk/authapi/isauthenticated"
    "?uri=https%3A%2F%2Fmy.kirklees.gov.uk%2Fservice%2FBins_and_recycling___Manage_your_bins"
    "&hostname=my.kirklees.gov.uk&withCredentials=true"
)
KIRKLEES_API_URL = "https://my.kirklees.gov.uk/apibroker/runLookup"
KIRKLEES_LOOKUP_ID = "65e08e60b299d"

CSV_PATH = Path(__file__).with_name("bins.csv")
COLLECTION_INTERVAL = timedelta(weeks=2)
HORIZON_DAYS = 365


def _label_to_bin_type(label: str) -> str | None:
    label = label.lower()
    if "grey" in label or "general" in label:
        return "grey"
    if "green" in label or "recycl" in label:
        return "green"
    if "brown" in label or "garden" in label:
        return "brown"
    if "food" in label:
        return "food"
    return None


def fetch_next_dates(uprn: str) -> dict[str, date]:
    """Return {bin_type: next_collection_date} from the Kirklees API."""
    session_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-GB,en;q=0.9",
        "Referer": "https://my.kirklees.gov.uk/service/Bins_and_recycling___Manage_your_bins",
        "Origin": "https://my.kirklees.gov.uk",
    }
    # Use a cookie-aware opener so the session cookie set in step 1
    # is automatically sent with the step 2 POST (same as requests.Session()).
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        urllib.request.HTTPSHandler(context=_SSL_CONTEXT),
    )

    req = urllib.request.Request(KIRKLEES_SESSION_URL, headers=session_headers)
    with opener.open(req, timeout=30) as resp:
        sid = json.loads(resp.read())["auth-session"]

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-GB,en;q=0.9",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://my.kirklees.gov.uk",
        "Referer": "https://my.kirklees.gov.uk/fillform/?iframe_id=fillform-frame-1&db_id=",
    }
    params = urllib.parse.urlencode({
        "id": KIRKLEES_LOOKUP_ID,
        "repeat_against": "",
        "noRetry": "false",
        "getOnlyTokens": "undefined",
        "log_id": "",
        "app_name": "AF-Renderer::Self",
        "_": str(int(time.time() * 1000)),
        "sid": sid,
    })
    payload = {"formValues": {"Search": {"validatedUPRN": {"value": uprn}}}}
    req = urllib.request.Request(
        f"{KIRKLEES_API_URL}?{params}",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    with opener.open(req, timeout=30) as resp:
        data = json.loads(resp.read())

    rows_data = data["integration"]["transformed"]["rows_data"]
    if not isinstance(rows_data, dict):
        raise ValueError("Unexpected response format from Kirklees API")

    result: dict[str, date] = {}
    for _, bin_info in rows_data.items():
        bin_type = _label_to_bin_type(bin_info.get("label", ""))
        if not bin_type:
            continue
        raw = bin_info.get("NextCollectionDate", "")
        try:
            result[bin_type] = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S").date()
        except ValueError:
            continue
    return result


def generate_schedule(next_dates: dict[str, date]) -> dict[date, list[str]]:
    """Extrapolate fortnightly collections for each bin type for HORIZON_DAYS days."""
    end = date.today() + timedelta(days=HORIZON_DAYS)
    schedule: dict[date, list[str]] = {}
    for bin_type, start in next_dates.items():
        d = start
        while d <= end:
            schedule.setdefault(d, []).append(bin_type)
            d += COLLECTION_INTERVAL
    return schedule


def write_csv(schedule: dict[date, list[str]]) -> None:
    rows = sorted(schedule.items())
    with CSV_PATH.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "bins"])
        for day, bins in rows:
            writer.writerow([day, ";".join(bins)])
    print(f"Wrote {len(rows)} collection days to {CSV_PATH}")
    print("Next step: run ./deploy.sh to bundle the updated bins.csv into Lambda.")


def main() -> None:
    uprn = os.environ.get("KIRKLEES_UPRN")
    if not uprn:
        sys.exit("Set KIRKLEES_UPRN=<your uprn> before running")

    print("Fetching next collection dates from Kirklees API...")
    next_dates = fetch_next_dates(uprn)
    if not next_dates:
        sys.exit("No bin dates returned — check your UPRN")

    print("Seed dates from API:")
    for bin_type, d in sorted(next_dates.items()):
        print(f"  {bin_type:6s}: {d}")

    schedule = generate_schedule(next_dates)
    write_csv(schedule)


if __name__ == "__main__":
    main()
