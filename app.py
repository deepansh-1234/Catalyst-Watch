from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from edgar import set_identity, Company
from bse import BSE
import sqlite3
import datetime
import uvicorn
import asyncio
import os
from contextlib import asynccontextmanager

# ── EDGAR Identity ────────────────────────────────────────────────────────────
# SEC EDGAR requires a name and email in the user-agent header for all requests.
# Set these as environment variables before running:
#   export EDGAR_NAME="Your Name"       (Windows: $env:EDGAR_NAME="Your Name")
#   export EDGAR_EMAIL="your@email.com"
EDGAR_NAME  = os.environ.get("EDGAR_NAME",  "")
EDGAR_EMAIL = os.environ.get("EDGAR_EMAIL", "")
if not EDGAR_NAME or not EDGAR_EMAIL:
    raise EnvironmentError(
        "EDGAR_NAME and EDGAR_EMAIL environment variables must be set before running. "
        "SEC EDGAR requires a valid name and email in the request header."
    )

DB_FILE = "filings_cache.db"

# ── Database ──────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # US filings (SEC EDGAR / 8-K)
    c.execute('''
        CREATE TABLE IF NOT EXISTS filings (
            id TEXT PRIMARY KEY,
            ticker TEXT,
            filing_date TEXT,
            url TEXT,
            event_type TEXT,
            impact TEXT
        )
    ''')

    # India filings (BSE corporate announcements)
    c.execute('''
        CREATE TABLE IF NOT EXISTS bse_filings (
            id TEXT PRIMARY KEY,
            ticker TEXT,
            company_name TEXT,
            filing_date TEXT,
            url TEXT,
            category TEXT,
            headline TEXT
        )
    ''')

    conn.commit()
    conn.close()

# ── SEC 8-K event classification ─────────────────────────────────────────────
ITEM_CODES = {
    "1": "Material Definitive Agreement",
    "1.01": "Material Definitive Agreement",
    "1.02": "Termination of Material Agreement",
    "1.03": "Bankruptcy or Receivership",
    "1.05": "Cybersecurity Incident",
    "2.01": "Acquisition or Disposal of Assets",
    "2.02": "Earnings Release / Financial Results",
    "2.03": "Off-Balance Sheet Obligation Created",
    "2.04": "Triggering of Accelerated Obligation",
    "2.06": "Material Impairment",
    "3": "Securities / Delisting Event",
    "3.01": "Notice of Delisting",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Shareholders",
    "4.01": "Change of Auditor",
    "4.02": "Non-Reliance on Prior Financial Statements",
    "5": "Executive / Board Leadership Change",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Executive / Board Leadership Change",
    "5.03": "Amendments to Articles or Bylaws",
    "5.07": "Shareholder Vote Results",
    "5.08": "Shareholder Director Nominations",
    "7.01": "Regulation FD Disclosure",
    "8": "Other Material Disclosure",
    "8.01": "Other Material Disclosure",
    "9.01": "Financial Statements and Exhibits",
}

# ── US universe (large-cap tech, 30 names) ────────────────────────────────────
US_UNIVERSE = {
    "AAPL": "0000320193", "MSFT": "0000789019", "GOOGL": "0001652044",
    "META": "0001326801", "AMZN": "0001018724", "NFLX": "0001065280",
    "NVDA": "0001045810", "AMD": "0000002488", "INTC": "0000050863",
    "AVGO": "0001730168", "QCOM": "0000804328", "TSM": "0001046179", "MU": "0000723125",
    "CRM": "0001108524", "ORCL": "0001341439", "PLTR": "0001321655",
    "SNOW": "0001640147", "NOW": "0001373715", "WDAY": "0001347858",
    "ADBE": "0000796343", "SAP": "0001492674",
    "PANW": "0001327567", "CRWD": "0001535527", "FTNT": "0001262039", "NET": "0001624185",
    "CSCO": "0000858877", "HPE": "0001645590", "DELL": "0001571996",
    "ANET": "0001596532", "SMCI": "0001379521",
}

# ── US company display names ──────────────────────────────────────────────────
US_NAMES = {
    "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
    "META": "Meta Platforms", "AMZN": "Amazon", "NFLX": "Netflix",
    "NVDA": "NVIDIA", "AMD": "Advanced Micro Devices", "INTC": "Intel",
    "AVGO": "Broadcom", "QCOM": "Qualcomm", "TSM": "TSMC", "MU": "Micron Technology",
    "CRM": "Salesforce", "ORCL": "Oracle", "PLTR": "Palantir",
    "SNOW": "Snowflake", "NOW": "ServiceNow", "WDAY": "Workday",
    "ADBE": "Adobe", "SAP": "SAP SE",
    "PANW": "Palo Alto Networks", "CRWD": "CrowdStrike", "FTNT": "Fortinet", "NET": "Cloudflare",
    "CSCO": "Cisco", "HPE": "Hewlett Packard Enterprise", "DELL": "Dell Technologies",
    "ANET": "Arista Networks", "SMCI": "Super Micro Computer",
}

# ── Nifty 50 universe (BSE scrip codes, full index as of mid-2026) ────────────
NIFTY_50 = {
    # Financial Services
    "HDFCBANK":   "500180",
    "ICICIBANK":  "532174",
    "KOTAKBANK":  "500247",
    "AXISBANK":   "532215",
    "SBIN":       "500112",
    "BAJFINANCE": "500034",
    "BAJAJFINSV": "532978",
    "HDFCLIFE":   "540777",
    "SBILIFE":    "540719",
    "ICICIPRULI": "540133",
    "JIOFIN":     "543969",
    # IT & Technology
    "TCS":        "532540",
    "INFY":       "500209",
    "WIPRO":      "507685",
    "HCLTECH":    "532281",
    "TECHM":      "532755",
    "LTIM":       "540005",
    # Energy & Oil & Gas
    "RELIANCE":   "500325",
    "ONGC":       "500312",
    "COALINDIA":  "533278",
    "NTPC":       "532555",
    "POWERGRID":  "532898",
    "BPCL":       "500547",
    "TATAPOWER":  "500400",
    # Industrials & Conglomerates
    "LT":         "500510",
    "ADANIPORTS": "532921",
    "ADANIENT":   "512599",
    "SIEMENS":    "500550",
    "ABB":        "500002",
    # Automobiles
    "TATAMOTORS": "500570",
    "MARUTI":     "532500",
    "M&M":        "500520",
    "BAJAJ-AUTO": "532977",
    "EICHERMOT":  "505200",
    "HEROMOTOCO": "500182",
    # Consumer & FMCG
    "HINDUNILVR": "500696",
    "ITC":        "500875",
    "NESTLEIND":  "500790",
    "BRITANNIA":  "500825",
    "TATACONSUM": "500800",
    # Pharma & Healthcare
    "SUNPHARMA":  "524715",
    "DRREDDY":    "500124",
    "CIPLA":      "500087",
    "DIVISLAB":   "532488",
    "APOLLOHOSP": "508869",
    "MAXHEALTH":  "543220",
    # Metals & Mining
    "TATASTEEL":  "500470",
    "JSWSTEEL":   "500228",
    "HINDALCO":   "500440",
    # Telecom
    "BHARTIARTL": "532454",
    # Cement
    "ULTRACEMCO": "532538",
    "SHREECEM":   "500387",
}

# ── BSE category classification ───────────────────────────────────────────────
BSE_CATEGORY_MAP = {
    "Result":                 "Financial Results",
    "Board Meeting":          "Board Meeting",
    "Corp. Action":           "Corporate Action",
    "AGM/EGM":                "AGM / EGM",
    "Company Update":         "Company Update",
    "Insider Trading / SAST": "Insider Trading / SAST",
    "New Listing":            "New Listing",
    "Others":                 "Other Disclosure",
}

def classify_bse_category(raw_category):
    if not raw_category:
        return "Other Disclosure"
    for key, label in BSE_CATEGORY_MAP.items():
        if key.lower() in raw_category.lower():
            return label
    return raw_category.strip()

# ── US sync (SEC EDGAR 8-K) ───────────────────────────────────────────────────
def sync_sec_data():
    print("Syncing SEC EDGAR data...")
    set_identity(f"{EDGAR_NAME} {EDGAR_EMAIL}")
    filter_date = datetime.date.today() - datetime.timedelta(days=90)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    for ticker, cik in US_UNIVERSE.items():
        try:
            company = Company(cik)
            filings = company.get_filings(form="8-K")
            if filings:
                latest = filings[0]
                if latest.filing_date >= filter_date:
                    detected_event = "Material Catalyst Event"
                    suggested_impact = "High: Review filing details to assess structural adjustments to investment thesis."
                    try:
                        items = latest.items if hasattr(latest, 'items') else []
                        if items:
                            primary_item = str(items[0]).strip()
                            detected_event = ITEM_CODES.get(primary_item, f"SEC Code: {primary_item}")
                            if primary_item in ["2.02", "2"]:
                                suggested_impact = "Immediate: Quarterly financial performance released. Anticipate near-term equity price volatility."
                            elif primary_item in ["5.02", "5"]:
                                suggested_impact = "Medium-Term: Core governance shift. Evaluate team alignment and strategic execution continuity."
                            elif primary_item in ["1.01", "1"]:
                                suggested_impact = "Strategic: Definitive transaction executed. Evaluates long-term capital allocation shifts."
                            elif primary_item in ["1.05"]:
                                suggested_impact = "Critical Risk: Material breach. Assess regulatory liability and prospective churn metrics."
                            elif primary_item in ["2.01"]:
                                suggested_impact = "Strategic: Asset acquisition or disposal. Review impact on balance sheet and capital allocation."
                            elif primary_item in ["4.01"]:
                                suggested_impact = "Governance: Auditor change. Monitor for implications on financial reporting quality."
                            elif primary_item in ["3.01", "3"]:
                                suggested_impact = "Regulatory: Delisting or securities event. Assess liquidity and investor implications."
                            elif primary_item in ["5.07"]:
                                suggested_impact = "Governance: Shareholder vote results filed. Review for board composition or policy changes."
                    except (AttributeError, IndexError, TypeError):
                        pass
                    c.execute('''
                        INSERT OR REPLACE INTO filings (id, ticker, filing_date, url, event_type, impact)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (latest.url, ticker, str(latest.filing_date), latest.url, detected_event, suggested_impact))
        except Exception as e:
            print(f"SEC sync error for {ticker}: {e}")

    conn.commit()
    conn.close()
    print("SEC sync complete.")

# ── India sync (BSE Nifty 50 announcements) ───────────────────────────────────
def sync_bse_data():
    print("Syncing BSE data...")
    from_date = datetime.datetime.now() - datetime.timedelta(days=90)
    to_date   = datetime.datetime.now()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    try:
        bse = BSE(download_folder='/tmp/')
        for ticker, scrip_code in NIFTY_50.items():
            try:
                data = bse.announcements(
                    scripcode=scrip_code,
                    from_date=from_date,
                    to_date=to_date,
                )
                rows = data.get("Table", [])
                if not rows:
                    continue

                latest       = rows[0]
                ann_id       = str(latest.get("NEWSID", f"{scrip_code}_latest"))
                company_name = str(latest.get("SLONGNAME", ticker))
                filing_date  = str(latest.get("NEWS_DT", ""))[:10]
                headline     = str(latest.get("HEADLINE", "Corporate Announcement"))
                category_raw = str(latest.get("CATEGORYNAME", ""))
                pdf_name     = str(latest.get("ATTACHMENTNAME", ""))

                url = (
                    f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{pdf_name}"
                    if pdf_name else
                    f"https://www.bseindia.com/corporates/ann.html?scripcd={scrip_code}"
                )
                category = classify_bse_category(category_raw)

                c.execute('''
                    INSERT OR REPLACE INTO bse_filings
                    (id, ticker, company_name, filing_date, url, category, headline)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (ann_id, ticker, company_name, filing_date, url, category, headline))

            except Exception as e:
                print(f"BSE sync error for {ticker}: {e}")

        bse.exit()
    except Exception as e:
        print(f"BSE session error: {e}")

    conn.commit()
    conn.close()
    print("BSE sync complete.")

# ── Background cron ───────────────────────────────────────────────────────────
async def cron_loop():
    while True:
        try:
            sync_sec_data()
        except Exception as e:
            print(f"SEC cron error: {e}")
        try:
            sync_bse_data()
        except Exception as e:
            print(f"BSE cron error: {e}")
        await asyncio.sleep(900)  # 15 minutes

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    sync_sec_data()
    sync_bse_data()
    asyncio.create_task(cron_loop())
    yield

app = FastAPI(lifespan=lifespan)

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home_page():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT ticker, filing_date, url, event_type, impact FROM filings ORDER BY filing_date DESC")
    us_rows = c.fetchall()
    c.execute("SELECT ticker, company_name, filing_date, url, category, headline FROM bse_filings ORDER BY filing_date DESC")
    in_rows = c.fetchall()
    conn.close()

    css = """
    <style>
        :root {
            --bg-main: #0b0f19; --bg-card: #131a2b; --border: #1e2942;
            --text-primary: #f1f5f9; --text-secondary: #64748b;
            --accent-blue: #38bdf8; --accent-green: #34d399;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 1060px; margin: 0 auto; padding: 50px 24px;
            background: var(--bg-main); color: var(--text-primary);
            line-height: 1.5; -webkit-font-smoothing: antialiased;
        }
        header { margin-bottom: 36px; border-bottom: 1px solid var(--border); padding-bottom: 20px; }
        h1 { font-size: 1.8rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 6px; }
        .subtitle { color: var(--text-secondary); font-size: 0.9rem; }
        .tabs { display: flex; gap: 8px; margin-bottom: 28px; }
        .tab {
            padding: 8px 20px; border-radius: 6px; border: 1px solid var(--border);
            background: transparent; color: var(--text-secondary);
            cursor: pointer; font-size: 0.88rem; font-weight: 500;
            transition: all 0.15s ease;
        }
        .tab.active { background: #1a253c; color: var(--accent-blue); border-color: #253556; }
        .tab.active.us-tab { background: #29230f; color: #fcd34d; border-color: #4a3a10; }
        .tab-content { display: none; }
        .tab-content.active { display: grid; gap: 18px; }
        .card {
            background: var(--bg-card); padding: 22px 24px;
            border-radius: 8px; border: 1px solid var(--border);
            transition: border-color 0.15s ease;
        }
        .card:hover { border-color: #2b3a5c; }
        .meta { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }
        .company-info { display: flex; flex-direction: column; gap: 4px; }
        .company-name { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }
        .badge {
            display: inline-block; padding: 2px 8px; border-radius: 4px; font-weight: 600;
            font-size: 0.72rem; letter-spacing: 0.05em; border: 1px solid; width: fit-content;
        }
        .badge-us { background: #29230f; color: #fcd34d; border-color: #4a3a10; }
        .badge-in { background: #14291e; color: #6ee7b7; border-color: #1a4a30; }
        .date { color: var(--text-secondary); font-size: 0.83rem; }
        .event-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 12px; }
        .analysis {
            background: rgba(2,6,23,0.4); padding: 12px 16px; border-radius: 6px;
            border-left: 3px solid var(--accent-blue); margin: 14px 0;
            font-size: 0.9rem; color: #cbd5e1;
        }
        .analysis strong {
            color: #94a3b8; font-weight: 600; font-size: 0.82rem;
            text-transform: uppercase; letter-spacing: 0.05em;
            display: block; margin-bottom: 4px;
        }
        .analysis.india { border-left-color: var(--accent-green); }
        .source-link {
            display: inline-flex; align-items: center; color: #fcd34d;
            text-decoration: none; font-weight: 500; font-size: 0.86rem;
        }
        .source-link.india { color: var(--accent-green); }
        .source-link:hover { opacity: 0.8; }
        .source-link::after { content: " ↗"; font-size: 0.74rem; margin-left: 3px; }
        .empty {
            color: var(--text-secondary); text-align: center; padding: 40px;
            border: 1px dashed var(--border); border-radius: 8px;
        }
    </style>
    <script>
        function showTab(id) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            const btn = document.getElementById('tab-' + id);
            btn.classList.add('active');
            document.getElementById('content-' + id).classList.add('active');
        }
    </script>
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Corporate Catalyst Tracker</title>
    {css}
</head>
<body>
    <header>
        <h1>Corporate Catalyst Tracker</h1>
        <div class="subtitle">
            Real-time surveillance across Nifty 50 (BSE announcements) and US large-cap tech (SEC 8-K). 
            Refreshes every 15 minutes.
        </div>
    </header>

    <div class="tabs">
        <button id="tab-in" class="tab active" onclick="showTab('in')">
            India Markets - Nifty 50 ({len(in_rows)} filings)
        </button>
        <button id="tab-us" class="tab us-tab" onclick="showTab('us')">
            US Markets - SEC 8-K ({len(us_rows)} filings)
        </button>
    </div>

    <div id="content-in" class="tab-content active">"""

    # ── India tab (first, active by default) ─────────────────────────────────
    if not in_rows:
        html += "\n        <div class='empty'>No BSE filings cached for this period.</div>"
    else:
        for row in in_rows:
            ticker       = row[0]
            company_name = row[1]
            filing_date  = row[2]
            url          = row[3]
            category     = row[4]
            headline     = row[5]
            html += f"""
        <article class="card">
            <div class="meta">
                <div class="company-info">
                    <span class="company-name">{company_name}</span>
                    <span class="badge badge-in">{ticker}</span>
                </div>
                <span class="date">Filed {filing_date}</span>
            </div>
            <div class="event-title">{headline}</div>
            <div class="analysis india">
                <strong>Category</strong>
                {category}
            </div>
            <a href="{url}" class="source-link india" target="_blank">View BSE Filing</a>
        </article>"""

    html += """
    </div>

    <div id="content-us" class="tab-content">"""

    # ── US tab ────────────────────────────────────────────────────────────────
    if not us_rows:
        html += "\n        <div class='empty'>No US filings cached for this period.</div>"
    else:
        for row in us_rows:
            ticker      = row[0]
            filing_date = row[1]
            url         = row[2]
            event_type  = row[3]
            impact      = row[4]
            company_name = US_NAMES.get(ticker, ticker)
            html += f"""
        <article class="card">
            <div class="meta">
                <div class="company-info">
                    <span class="company-name">{company_name}</span>
                    <span class="badge badge-us">{ticker}</span>
                </div>
                <span class="date">Filed {filing_date}</span>
            </div>
            <div class="event-title">{event_type}</div>
            <div class="analysis">
                <strong>Impact Outlook</strong>
                {impact}
            </div>
            <a href="{url}" class="source-link" target="_blank">View SEC EDGAR Filing</a>
        </article>"""

    html += """
    </div>
</body>
</html>"""

    return html


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
