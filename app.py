from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from edgar import set_identity, Company
import sqlite3
import datetime
import uvicorn
import asyncio
import os
from contextlib import asynccontextmanager

# SEC EDGAR requires a name and email in the user-agent header for all requests.
# Set these as environment variables before running:
#   export EDGAR_NAME="Your Name"
#   export EDGAR_EMAIL="your@email.com"
# Docs: https://www.sec.gov/os/accessing-edgar-data
EDGAR_NAME  = os.environ.get("EDGAR_NAME",  "")
EDGAR_EMAIL = os.environ.get("EDGAR_EMAIL", "")
if not EDGAR_NAME or not EDGAR_EMAIL:
    raise EnvironmentError(
        "EDGAR_NAME and EDGAR_EMAIL environment variables must be set before running. "
        "SEC EDGAR requires a valid name and email in the request header."
    )

DB_FILE = "filings_cache.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT event_type FROM filings LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("DROP TABLE IF EXISTS filings")
        
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS filings (
            id TEXT PRIMARY KEY,
            ticker TEXT,
            filing_date TEXT,
            url TEXT,
            event_type TEXT,
            impact TEXT
        )
    ''')
    conn.commit()
    conn.close()

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

def sync_sec_data():
    """Pulls the latest 8-K filing for each tracked company and writes it to the local cache."""
    print("Syncing SEC EDGAR data...")
    set_identity(f"{EDGAR_NAME} {EDGAR_EMAIL}")

    tech_universe = {
        "AAPL": "0000320193", "MSFT": "0000789019", "GOOGL": "0001652044", 
        "META": "0001326801", "AMZN": "0001018724", "NFLX": "0001065280",
        "NVDA": "0001045810", "AMD": "0000002488", "INTC": "0000050863", 
        "AVGO": "0001730168", "QCOM": "0000804328", "TSM": "0001046179", "MU": "0000723125",
        "CRM": "0001108524", "ORCL": "0001341439", "PLTR": "0001321655", 
        "SNOW": "0001640147", "NOW": "0001373715", "WDAY": "0001347858", "ADBE": "0000796343", "SAP": "0001492674",
        "PANW": "0001327567", "CRWD": "0001535527", "FTNT": "0001262039", "NET": "0001624185",
        "CSCO": "0000858877", "HPE": "0001645590", "DELL": "0001571996", "ANET": "0001596532", "SMCI": "0001379521"
    }
    
    # only surface filings from the last 90 days — keeps the dashboard current
    # without hardcoding a calendar date that goes stale
    filter_date = datetime.date.today() - datetime.timedelta(days=90)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    for ticker, cik in tech_universe.items():
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
                    except (AttributeError, IndexError, TypeError):
                        pass  # item parsing is best-effort; fall back to generic event label
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO filings (id, ticker, filing_date, url, event_type, impact)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (latest.url, ticker, str(latest.filing_date), latest.url, detected_event, suggested_impact))
        except Exception as e:
            print(f"Sync error for {ticker}: {e}")
            
    conn.commit()
    conn.close()
    print("Sync complete.")

async def cron_loop():
    """Background task runner that updates the database every 15 minutes without blocking requests"""
    while True:
        try:
            sync_sec_data()
        except Exception as e:
            print(f"Background worker loop error: {e}")
        await asyncio.sleep(900) # 900 seconds = 15 minutes

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles background thread execution alongside web server lifespan"""
    init_db()
    # Run an initial data sync right on startup so the database isn't empty
    sync_sec_data()
    # Boot the background daemon loop task
    asyncio.create_task(cron_loop())
    yield

# Initialize Web App Engine with custom Lifespan Manager
app = FastAPI(lifespan=lifespan)

@app.get("/", response_class=HTMLResponse)
def home_page():
    """Renders instantly from the local cached database without hitting the internet"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, filing_date, url, event_type, impact FROM filings ORDER BY filing_date DESC")
    rows = cursor.fetchall()
    conn.close()
    
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Macro Catalyst Intelligence | SEC Tracker</title>
            <style>
                :root {
                    --bg-main: #0b0f19;
                    --bg-card: #131a2b;
                    --border-color: #1e2942;
                    --text-primary: #f1f5f9;
                    --text-secondary: #64748b;
                    --accent-blue: #38bdf8;
                    --accent-cyan: #06b6d4;
                }
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif; 
                    max-width: 1000px; 
                    margin: 0 auto; 
                    padding: 50px 24px; 
                    background-color: var(--bg-main); 
                    color: var(--text-primary);
                    line-height: 1.5;
                    -webkit-font-smoothing: antialiased;
                }
                header {
                    margin-bottom: 40px;
                    border-bottom: 1px solid var(--border-color);
                    padding-bottom: 24px;
                }
                h1 { 
                    font-size: 1.85rem; 
                    font-weight: 700; 
                    letter-spacing: -0.025em;
                    color: var(--text-primary);
                    margin: 0 0 6px 0;
                }
                .subtitle { 
                    color: var(--text-secondary); 
                    font-size: 0.95rem; 
                }
                .grid { display: grid; gap: 20px; }
                .card { 
                    background-color: var(--bg-card); 
                    padding: 24px; 
                    border-radius: 8px; 
                    border: 1px solid var(--border-color); 
                    transition: border-color 0.2s ease;
                }
                .card:hover { border-color: #2b3a5c; }
                .meta-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
                .ticker-badge { 
                    background-color: #1a253c; 
                    color: #93c5fd; 
                    padding: 4px 10px; 
                    border-radius: 4px; 
                    font-weight: 600; 
                    font-size: 0.8rem; 
                    letter-spacing: 0.05em;
                    border: 1px solid #253556;
                }
                .date-stamp { color: var(--text-secondary); font-size: 0.85rem; }
                .event-title { font-size: 1.15rem; font-weight: 600; margin-bottom: 14px; }
                .analysis-container { 
                    background-color: rgba(2, 6, 23, 0.4); 
                    padding: 14px 16px; 
                    border-radius: 6px; 
                    border-left: 3px solid var(--accent-blue); 
                    margin: 16px 0; 
                    font-size: 0.92rem; 
                    color: #cbd5e1; 
                }
                .analysis-container strong {
                    color: #94a3b8; font-weight: 600; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; display: block; margin-bottom: 4px;
                }
                .source-link { display: inline-flex; align-items: center; color: var(--accent-blue); text-decoration: none; font-weight: 500; font-size: 0.88rem; }
                .source-link:hover { color: #7dd3fc; }
                .source-link::after { content: " ↗"; font-size: 0.75rem; margin-left: 4px; }
                .empty-state { color: var(--text-secondary); text-align: center; padding: 40px; border: 1px dashed var(--border-color); border-radius: 8px; }
            </style>
        </head>
        <body>
            <header>
                <h1>Corporate Catalyst Intelligence Engine</h1>
                <div class="subtitle">Real-time surveillance infrastructure tracking material structural shifts across large-cap tech.</div>
            </header>
            <main class="grid">
    """
    
    if not rows:
        html_content += "<div class='empty-state'>No active infrastructure alerts cached for this tracking period.</div>"
    else:
        for row in rows:
            html_content += f"""
            <article class="card">
                <div class="meta-header">
                    <span class="ticker-badge">{row[0]}</span>
                    <span class="date-stamp">Filed {row[1]}</span>
                </div>
                <div class="event-title">{row[3]}</div>
                <div class="analysis-container">
                    <strong>Quantitative Impact Outlook</strong>
                    {row[4]}
                </div>
                <a href="{row[2]}" class="source-link" target="_blank">Access SEC Edgar Filing Archive</a>
            </article>
            """
            
    html_content += "</main></body></html>"
    return html_content

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)