# Sector Intelligence Monitor

Early-stage investing signals extracted automatically from public company filings.

**Live demo:** [Streamlit Cloud URL]  
**Loom demo:** [Loom URL]  
**GitHub:** [repo URL]

---

## What it does

Ingests 3+ years of Indian Fintech (Paytm) investor presentations and quarterly P&L data, extracts structured financial metrics via LLM, and surfaces two outputs:

1. **Trend analysis** — which metrics are improving, which are deteriorating, what product bets are gaining traction
2. **Investing lens** — where the incumbent is investing (validates the startup market), where it is struggling (white space), and operating benchmarks for evaluating early-stage companies

---

## Architecture

```
Public Sources
  ├── Paytm IR page (investor presentations PDF)
  └── Screener.in (quarterly P&L — 13 quarters)
         │
         ▼
  Ingestion Layer
  ├── paytm_fetcher.py      discover + download PDFs
  ├── pdf_parser.py         PyMuPDF text extraction + chunking
  └── screener_backfill.py  historical P&L scraper
         │
         ▼
  Extraction Layer
  └── metrics_extractor.py  LLM → FintechMetrics (Pydantic) → SQLite
         │
         ▼
  SQLite (data/sector_intel.db)
  ├── companies
  ├── documents
  ├── chunks
  ├── metrics             ← 13 quarters, 13 metric types, 80 rows
  ├── synthesis
  └── refresh_log
         │
         ▼
  Synthesis Layer
  └── synthesizer.py      metrics table → LLM → trend analysis + investing lens
         │
         ▼
  Streamlit Dashboard (app.py)
  ├── Metrics tab         — grouped Plotly charts (fiscal chronological order)
  ├── Synthesis tab       — trend analysis + investing lens
  ├── Documents tab       — indexed filings with status + source links
  └── Pipeline tab        — run full pipeline from browser
         │
         ▼
  Scheduler (scheduler.py)
  └── APScheduler weekly cron — Sunday 02:00 IST
```

---

## Current data coverage

| Company | Earliest | Latest | Quarters | Source |
|---------|----------|--------|----------|--------|
| Paytm (One97 Comm.) | Q4FY23 | Q4FY26 | 13 | Screener.in + IR PDFs |

Metrics tracked:
- **Payments:** GMV, Monthly Transacting Users, Merchant Subscriptions, Devices Deployed
- **Profitability:** EBITDA before ESOP, Contribution Profit, Contribution Margin
- **P&L (INR Cr):** Revenue, Operating Profit, OPM%, Net Profit, EPS

---

## Stack

| Layer | Technology |
|-------|-----------|
| Dashboard | Streamlit + Plotly |
| Database | SQLite (file-based, zero config) |
| PDF parsing | PyMuPDF (fitz) |
| LLM extraction | Claude / Gemini / OpenAI (provider-agnostic) |
| Validation | Pydantic v2 |
| Scheduler | APScheduler |
| Historical data | Screener.in (HTML scraping) |

---

## Quickstart

### 1. Clone and install

```bash
git clone <repo>
cd sector-intelligence-monitor
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set LLM_PROVIDER and the corresponding API key
```

### 3. Run

```bash
# Launch dashboard (demo data auto-seeded on first run)
streamlit run app.py

# Run full pipeline manually (requires API key for LLM steps)
python scheduler.py --sector indian_fintech

# Start weekly auto-refresh daemon
python scheduler.py --daemon
```

---

## Deployment (Streamlit Cloud)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app → select `app.py`
3. Add secrets in the Streamlit Cloud UI (Settings → Secrets):

```toml
LLM_PROVIDER = "claude"
ANTHROPIC_API_KEY = "sk-ant-..."
DATABASE_PATH = "/tmp/sector_intel.db"
```

4. The app seeds demo data automatically on first launch — no manual setup required.

> **Note on persistence:** Streamlit Cloud's filesystem is ephemeral. The SQLite DB is recreated with demo data on each cold start. For persistent storage, configure `DATABASE_PATH` to point to a mounted volume or use the Pipeline tab to re-run extraction after each deployment.

---

## Running the pipeline manually

```bash
# One-shot refresh (fetch → parse → extract → synthesize → Screener backfill)
python scheduler.py

# Dry-run the Screener backfill only
python -m pipeline.ingestion.screener_backfill --dry-run

# Check current coverage
python tests/coverage_report.py
```

---

## Adding a new sector

The architecture is modular. To add Indian Defence or US Biotech:

1. Add a `DefenceMetrics` or `BiotechMetrics` Pydantic model to `pipeline/schemas.py`
2. Create `pipeline/ingestion/<company>_fetcher.py` following the `PaytmFetcher` pattern
3. Register the company in `scheduler.py → SECTOR_COMPANIES`
4. Add the sector to `SECTOR_CONFIG` in `app.py`

No other changes required.

---

## Project structure

```
.
├── app.py                          # Streamlit dashboard
├── scheduler.py                    # Refresh orchestrator + APScheduler cron
├── requirements.txt
├── .env.example
├── packages.txt                    # Streamlit Cloud system packages
├── .streamlit/
│   └── config.toml
├── pipeline/
│   ├── database.py                 # All SQLite CRUD
│   ├── schemas.py                  # FintechMetrics, SynthesisOutput (Pydantic)
│   ├── config.py
│   ├── ingestion/
│   │   ├── paytm_fetcher.py        # Phase 2: document discovery
│   │   ├── document_tracker.py     # Phase 2: DB tracking + dedup
│   │   ├── pdf_parser.py           # Phase 3: text extraction + chunking
│   │   └── screener_backfill.py    # Historical P&L backfill
│   ├── extraction/
│   │   ├── metrics_extractor.py    # Phase 4: LLM → FintechMetrics
│   │   └── llm_client.py           # Provider-agnostic LLM client
│   └── synthesis/
│       └── synthesizer.py          # Phase 6: trend analysis + investing lens
├── data/
│   ├── sector_intel.db             # SQLite database
│   └── pdfs/paytm/                 # Downloaded PDFs
└── tests/
    ├── test_phase1.py  through test_phase6.py
    └── coverage_report.py
```

---

## Test suite

```bash
python tests/test_phase1.py   # DB schema + init
python tests/test_phase2.py   # Paytm document fetcher
python tests/test_phase3.py   # PDF parsing + chunking
python tests/test_phase4.py   # LLM extraction (live tests require API key)
python tests/test_phase6.py   # Synthesis (live tests require API key)
python tests/coverage_report.py  # Historical coverage audit
```

---

## Assignment requirements checklist

| Requirement | Status |
|-------------|--------|
| 3 years of public company data | ✅ Q4FY23–Q4FY26 (13 quarters) |
| Structured database | ✅ SQLite with 6 normalised tables |
| Key metrics extracted | ✅ GMV, MTU, Devices, Revenue, EBITDA, Contribution Margin, Net Profit, EPS, OPM% |
| Trend identification | ✅ LLM synthesis with trend analysis |
| Investing lens | ✅ Synthesis tab: white space, benchmarks, incumbent signals |
| Auto-refresh scheduler | ✅ APScheduler weekly cron + manual trigger |
| Streamlit dashboard | ✅ 4 tabs: Metrics, Synthesis, Documents, Pipeline |
| Source document links | ✅ Documents tab with IR page links |
| Indian Fintech sector | ✅ Paytm (extensible to Bajaj Finance, SBI Cards) |
| Modular for new sectors | ✅ Defence + Biotech schemas stubbed, add fetcher to extend |
