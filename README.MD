# ⚡ Corporate Catalyst Intelligence Engine

An institutional-grade regulatory data pipeline that tracks, caches, and categorizes unscheduled material events (8-K filings) across a 30-company large-cap technology universe. Built using Python, FastAPI, and SQLite.

## 🏗️ Architecture Overview
- **Data Ingestion:** Asynchronous handshakes with federal SEC EDGAR servers via programmatic user-agent indexing.
- **Background Worker:** Runs an independent daemon process loop that updates the database cache every 15 minutes, preventing federal connection throttling.
- **Caching Engine:** Low-latency SQLite database layer running `INSERT OR REPLACE` data-integrity rules to completely eliminate redundant network overhead.
- **Backend Controller:** Modern FastAPI routing architecture running a Uvicorn ASGI server framework delivering sub-10ms response times.
- **Frontend Presentation:** Dynamic HTML5/CSS3 template client styled with high-contrast, professional SaaS metrics.

## 🛠️ Tech Stack
- **Language:** Python
- **Framework:** FastAPI
- **Server Engine:** Uvicorn
- **Database Architecture:** SQLite3
- **Data Layer:** Edgartools core bindings

## 🏃‍♂️ How to Run Locally
1. Clone this repository to your desktop environment.
2. Install the necessary system packages:
   ```bash
   pip install fastapi uvicorn edgartools