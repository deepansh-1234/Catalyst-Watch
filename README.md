# CatalystWatch

A real-time corporate filing surveillance dashboard covering two markets simultaneously - India's Nifty 50 via BSE corporate announcements and US large-cap tech via SEC EDGAR (8-K filings). Built with FastAPI, SQLite, and async Python.

<img width="354" height="289" alt="image" src="https://github.com/user-attachments/assets/5b132a7f-6d9b-4d8c-8363-fd435431a5a7" />

<img width="350" height="289" alt="image" src="https://github.com/user-attachments/assets/7d96b2dc-dc7d-44b5-ba78-dd3d16ffb42a" />


---

## What it does

Material corporate events like earnings releases, leadership changes, M&A transactions, cybersecurity incidents which are the most time-sensitive documents a company produces. Analysts and associates on equity desks monitor these continuously across both Indian and US names.

CatalystWatch polls both sources every 15 minutes in the background, classifies each filing by event type, and serves everything through a tabbed dashboard. The page reads from a local SQLite cache, so loads are instant with no live API calls on the request path.

**India tab:** tracks all the Nifty 50 companies across BSE corporate announcements. Filings are classified by BSE category (Financial Results, Board Meeting, Corporate Action, AGM/EGM, etc.) and link directly to the source PDF on BSE India.

**US tab:** tracks 30 large-cap tech names across SEC EDGAR. Each 8-K is classified using the SEC item code system (2.02 = earnings, 5.02 = leadership change, 1.05 = cybersecurity incident) with a short impact note attached.

---

## Architecture

```
startup
  └── init_db()          — initialises SQLite tables for US and India filings
  └── sync_sec_data()    — initial EDGAR pull (US)
  └── sync_bse_data()    — initial BSE pull (India)
  └── cron_loop()        — async background task, refreshes both feeds every 15 min

GET /
  └── reads from local SQLite cache
  └── returns rendered HTML — no live network calls on the request path
```

The background worker runs as an asyncio task inside the FastAPI lifespan manager - no separate process, no Celery, no Redis needed.

---

## Tracked universe

**India : Full Nifty 50 (BSE announcements)**

Financial services, IT, energy, industrials, automobiles, FMCG, pharma, metals, telecom, and cement - all 50 index constituents as of mid-2026.

**USA : 30 large-cap tech names (SEC 8-K)**

`AAPL MSFT GOOGL META AMZN NFLX NVDA AMD INTC AVGO QCOM TSM MU CRM ORCL PLTR SNOW NOW WDAY ADBE SAP PANW CRWD FTNT NET CSCO HPE DELL ANET SMCI`

---

## Setup

**1. Install dependencies**
```bash
pip install fastapi uvicorn edgartools bse
```

**2. Set your EDGAR identity**

SEC EDGAR requires a real name and email in every request header. The app reads these from environment variables and won't start without them.

```bash
# macOS / Linux
export EDGAR_NAME="Your Name"
export EDGAR_EMAIL="your@email.com"

# Windows (PowerShell)
$env:EDGAR_NAME="Your Name"
$env:EDGAR_EMAIL="your@email.com"
```

Use a real email as the SEC contacts you if your access patterns look unusual. No authentication is required beyond this.

**3. Run**
```bash
python app.py
```

Open `http://127.0.0.1:8000`. Both syncs run on startup so the dashboard populates immediately - the US sync takes 1–2 minutes, the India sync is faster.

---

## Event classification

**India (BSE categories)**

Financial Results · Board Meeting · Corporate Action · AGM / EGM · Company Update · Insider Trading / SAST · Other Disclosure

**US (SEC item codes)**

| Code | Event | Impact |
|---|---|---|
| 2.02 | Earnings Release | Immediate - near-term price volatility likely |
| 5.02 | Executive / Board Change | Medium-term - monitor strategic continuity |
| 1.01 | Material Definitive Agreement | Strategic - long-term capital allocation shift |
| 2.01 | Acquisition or Disposal of Assets | Strategic - review balance sheet impact |
| 1.05 | Cybersecurity Incident | Critical - assess regulatory and operational risk |
| 5.07 | Shareholder Vote Results | Governance - review for board or policy changes |
| 4.01 | Change of Auditor | Governance - monitor financial reporting implications |

---

## A few things worth knowing

The 15-minute polling interval is deliberate as EDGAR's fair-use guidelines recommend no more than 10 requests per second and reasonable aggregate volume. One filing request per company per cycle is well within limits. BSE has similar conventions around automated access.

`INSERT OR REPLACE` on the filing ID means re-running a sync never creates duplicate rows. Only the most recent filing per company within the 90-day window is stored which is a deliberate choice to keep the dashboard scannable rather than archival.

The 90-day window is a rolling calculation off today's date. It doesn't need manual updates and won't go stale.

---

## Stack

Python · FastAPI · Uvicorn · SQLite · edgartools · BseIndiaApi
