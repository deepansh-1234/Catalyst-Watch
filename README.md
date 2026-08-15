# SEC 8-K Catalyst Tracker

A Python web app that monitors SEC EDGAR for 8-K filings across a 30-company large-cap tech universe, classifies them by event type, and serves them through a clean dashboard. Built with FastAPI, SQLite, and the `edgartools` library.

<img width="175" height="259" alt="dashboard" src="https://github.com/user-attachments/assets/99395eff-761e-4666-9962-6c3699413aac" />

---

## What it does

8-K filings are the "unscheduled material events" companies are required to report to the SEC — earnings releases, executive changes, cybersecurity incidents, major transactions. For anyone following equities, these are often the most time-sensitive documents a company produces.

This app polls EDGAR every 15 minutes in the background, writes each company's latest filing to a local SQLite cache, and classifies the event type using the SEC item code system (2.02 = earnings, 5.02 = leadership change, 1.05 = cybersecurity incident, etc.). The dashboard reads from the cache, so page loads are instant with no live API calls on the request path.

---

## Architecture

```
startup
  └── init_db()          — creates SQLite table if it doesn't exist
  └── sync_sec_data()    — initial data pull so the dashboard isn't empty on first load
  └── cron_loop()        — async background task, runs sync every 15 minutes

GET /
  └── reads from SQLite cache
  └── returns rendered HTML — no live network calls on the request path
```

The background worker runs as an asyncio task inside the FastAPI lifespan, so it doesn't block incoming requests and doesn't need a separate process or celery worker.

---

## Tracked universe

30 large-cap tech names across semiconductors, software, cloud, and cybersecurity:

`AAPL MSFT GOOGL META AMZN NFLX NVDA AMD INTC AVGO QCOM TSM MU CRM ORCL PLTR SNOW NOW WDAY ADBE SAP PANW CRWD FTNT NET CSCO HPE DELL ANET SMCI`

---

## Setup

**1. Install dependencies**
```bash
pip install fastapi uvicorn edgartools
```

**2. Set your EDGAR identity**

SEC EDGAR requires a name and email in the user-agent header for all programmatic requests. The app reads these from environment variables — it won't start without them.

```bash
export EDGAR_NAME="Your Name"
export EDGAR_EMAIL="your@email.com"
```

These are passed directly to `edgartools` and go into the HTTP header on every EDGAR request. Use a real email — the SEC uses this to contact you if your access patterns look unusual.

**3. Run**
```bash
python app.py
```

Then open `http://127.0.0.1:8000` in your browser. The first sync runs on startup so the dashboard populates immediately.

---

## Event classification

The app maps SEC item codes to readable event types and attaches a short impact note to each:

| SEC Item Code | Event Type | Impact Label |
|---|---|---|
| 2.02 | Earnings Release | Immediate — near-term price volatility likely |
| 5.02 | Executive / Board Change | Medium-term — monitor strategic continuity |
| 1.01 | Material Definitive Agreement | Strategic — long-term capital allocation shift |
| 1.05 | Cybersecurity Incident | Critical — assess regulatory and operational risk |
| 8.01 | Other Material Disclosure | Review filing for context |

If a filing contains an item code not in the above list, the raw SEC code is surfaced directly rather than guessing at a label.

---

## A few things worth knowing

The 15-minute polling interval is intentional — EDGAR's fair-use guidelines ask for no more than 10 requests per second and reasonable overall volume. The background worker requests one filing per company per cycle, well within limits.

The SQLite `INSERT OR REPLACE` on the `id` (filing URL) field means re-running the sync never creates duplicate rows. If a company files a second 8-K within the 90-day window, only the most recent one is stored. This is a deliberate design choice to keep the dashboard focused — if you want full filing history, the `get_filings()` call already returns all filings and you'd just remove the `filings[0]` slice.

The dashboard currently filters to filings from the last 90 days. This is a rolling window that auto-updates, as opposed to a hardcoded date that would require manual updates over time.

---

## Stack

Python · FastAPI · Uvicorn · SQLite · edgartools
