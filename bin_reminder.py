"""Bin day reminder for an Echo Show via the Voice Monkey Announcement API.

Run once each evening. If tomorrow (UK time) has a collection in bins.csv,
it announces it on the Echo Show with speech, a bin image and large text.

Environment variables:
  VM_TOKEN        Voice Monkey API token (Console -> API Tokens)
  VM_DEVICE       Voice Monkey speaker device ID for the Echo Show
  IMAGE_BASE_URL  Public HTTPS folder holding grey.png, green.png ... (no trailing slash)
  VM_PROXY_URL    Cloudflare Worker URL (proxies to Voice Monkey to avoid IP blocks)
  DRY_RUN=1       Print the request instead of sending it
  FORCE_DATE      Pretend today is this date (YYYY-MM-DD), for testing
"""

import csv
import json
import os
import ssl
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

API_URL = os.environ.get("VM_PROXY_URL", "").rstrip("/") + "/announce" if os.environ.get("VM_PROXY_URL") else "https://api-v3.voicemonkey.io/announce"
UK = ZoneInfo("Europe/London")
CSV_PATH = Path(__file__).with_name("bins.csv")

BIN_LABELS = {
    "grey": "grey general waste bin",
    "green": "green recycling bin",
    "brown": "brown garden waste bin",
    "food": "food waste caddy",
}


def load_schedule(path: Path) -> dict[date, list[str]]:
    schedule: dict[date, list[str]] = {}
    with path.open(newline="") as f:
        rows = (line for line in f if line.strip() and not line.startswith("#"))
        for row in csv.DictReader(rows):
            day = date.fromisoformat(row["date"].strip())
            bins = [b.strip().lower() for b in row["bins"].split(";") if b.strip()]
            unknown = [b for b in bins if b not in BIN_LABELS]
            if unknown:
                sys.exit(f"Unknown bin type {unknown} on {day} in {path.name}")
            schedule.setdefault(day, []).extend(bins)
    return schedule


def build_message(bins: list[str]) -> tuple[str, str]:
    names = [BIN_LABELS[b] for b in bins]
    spoken = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    speech = f"Reminder: tomorrow is bin day. Please put out the {spoken} tonight."
    text = "BIN DAY TOMORROW\n" + " + ".join(b.upper() for b in bins)
    return speech, text


def announce(speech: str, text: str, image: str | None) -> None:
    payload = {
        "token": os.environ.get("VM_TOKEN", ""),
        "device": os.environ.get("VM_DEVICE", ""),
        "speech": speech,
        "chime": "soundbank://soundlibrary/alarms/beeps_and_bloops/bell_02",
    }
    if image:
        payload["background_image"] = image
    else:
        payload["no_bg"] = True
        payload["text_display"] = text

    if os.environ.get("DRY_RUN") == "1":
        safe = {**payload, "token": "***"}
        print("DRY RUN - would POST to", API_URL)
        print(json.dumps(safe, indent=2))
        return

    if not payload["token"] or not payload["device"]:
        sys.exit("VM_TOKEN and VM_DEVICE must be set")

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
        print("Voice Monkey responded:", resp.status, resp.read().decode()[:300])


def main() -> None:
    forced = os.environ.get("FORCE_DATE")
    today = date.fromisoformat(forced) if forced else datetime.now(UK).date()
    tomorrow = today + timedelta(days=1)

    schedule = load_schedule(CSV_PATH)
    bins = schedule.get(tomorrow)
    if not bins:
        print(f"{today}: no collection tomorrow ({tomorrow}). Nothing to do.")
        upcoming = sorted(d for d in schedule if d > today)
        if not upcoming:
            print("WARNING: bins.csv has no future dates — run fetch_dates.py to refresh.")
        return

    speech, text = build_message(bins)
    base = os.environ.get("IMAGE_BASE_URL", "").rstrip("/")
    image = f"{base}/{bins[0]}.png" if base else None
    print(f"{today}: collection tomorrow -> {bins}")
    announce(speech, text, image)


def lambda_handler(event, context):
    main()


if __name__ == "__main__":
    main()
