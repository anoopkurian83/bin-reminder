# Bin day reminder for Echo Show

Every evening an AWS Lambda function checks `bins.csv`. If tomorrow is a bin
collection day it fires a Voice Monkey announcement on the Echo Show — speech,
a chime, and a picture of the bin.

```
EventBridge (7 PM + 9 PM)
        │
        ▼
  AWS Lambda  ──►  Cloudflare Worker  ──►  Voice Monkey  ──►  Echo Show
```

## Files

| File | Purpose |
|---|---|
| `bin_reminder.py` | Lambda handler — reads `bins.csv`, calls Voice Monkey |
| `fetch_dates.py` | Run locally once a year to regenerate `bins.csv` from the Kirklees API |
| `bins.csv` | Collection schedule (one row per collection day) |
| `deploy.sh` | Packages and deploys Lambda + EventBridge rules from scratch |
| `cloudflare-worker/worker.js` | Cloudflare Worker that proxies requests to Voice Monkey |
| `images/` | Bin images served from S3 (`grey.png`, `green.png`, `brown.png`, `food.png`) |
| `make_images.py` | Regenerate the images (needs Pillow) |

## One-time setup

### 1. Voice Monkey
1. Enable the **Voice Monkey** skill in the Alexa app and link your Amazon account.
2. Sign in at voicemonkey.io → Devices → create a **Speaker** device for your Echo Show. Copy its **device ID**.
3. Settings → API → copy your **API token**.

### 2. Cloudflare Worker (proxy)
Voice Monkey blocks AWS Lambda IP ranges. A Cloudflare Worker forwards requests
from Lambda to Voice Monkey.

1. Sign up free at cloudflare.com.
2. Workers & Pages → Create → Create Worker.
3. Paste the contents of `cloudflare-worker/worker.js` and click **Deploy**.
4. Copy the Worker URL (e.g. `https://your-worker.workers.dev/`).

### 3. Deploy Lambda
```bash
KIRKLEES_UPRN=your_uprn python3 fetch_dates.py   # generate bins.csv first
./deploy.sh
```

`deploy.sh` will prompt for:
- AWS region (e.g. `eu-west-2`)
- `VM_TOKEN` — Voice Monkey API token
- `VM_DEVICE` — Voice Monkey device ID
- `VM_PROXY_URL` — your Cloudflare Worker URL
- `IMAGE_BASE_URL` — public HTTPS folder holding the bin images

It creates the Lambda function, IAM role, and two EventBridge rules (7 PM and
9 PM UK time).

## Annual refresh

The Kirklees API returns ~12 months of upcoming dates. Run this each year when
the new collection calendar starts (usually October):

```bash
KIRKLEES_UPRN=your_uprn python3 fetch_dates.py
./deploy.sh
```

`fetch_dates.py` writes a fresh `bins.csv`; `deploy.sh` bundles it into the
Lambda zip and redeployes.

## Local test

```bash
VM_TOKEN=... VM_DEVICE=... IMAGE_BASE_URL=... \
  FORCE_DATE=2026-10-25 python3 bin_reminder.py
```

Set `DRY_RUN=1` to print the payload without calling Voice Monkey.

## Schedule

Two EventBridge rules fire daily in UTC:

| Rule | UTC | UK time (GMT) |
|---|---|---|
| `bin-reminder-schedule` | 19:00 | 7:00 PM |
| `bin-reminder-schedule-9pm` | 21:00 | 9:00 PM |

When the clocks spring forward (BST, UTC+1) these shift to 8 PM / 10 PM.
Update the cron expressions in `deploy.sh` to 18:00 / 20:00 UTC if you want
them back on the hour in summer.

## bins.csv format

```csv
date,bins
2026-10-26,grey
2026-10-27,brown
2026-11-02,green
```

Use `;` to separate multiple bins on the same day: `2026-10-26,grey;brown`.
Valid bin types: `grey`, `green`, `brown`, `food`.
