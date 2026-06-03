# Sector Intelligence Monitor

A multi-sector intelligence platform that automatically collects company data, stores structured financial metrics, generates investment-oriented insights, and visualizes trends through an interactive dashboard.

## Live Links

* Live Demo: https://sector-intelligence-monitor.onrender.com
* Loom Demo: https://www.loom.com/share/01dc8f6abb014dcfb543c373ea1052ab
* GitHub Repository: https://github.com/VikashSunda/sector-intelligence-monitor

---

# Overview

Investors and analysts often spend significant time reading earnings presentations, financial reports, and company disclosures to understand industry trends.

This project automates that workflow by:

* Collecting company information from public sources
* Storing structured financial metrics
* Generating automated trend analysis and investing insights
* Providing an interactive dashboard for exploration

The platform is designed to be modular and extensible, allowing new sectors and companies to be added without redesigning the frontend.

---

# Current Coverage

## Indian Fintech

* Paytm (One97 Communications)
* Bajaj Finance
* PB Fintech
* SBI Cards
* CreditAccess Grameen

## Indian Defence

* Hindustan Aeronautics Limited (HAL)
* Bharat Electronics Limited (BEL)

## US Biotech

* Moderna (MRNA)
* Gilead Sciences (GILD)

Total Coverage:

* 3 sectors
* 9 companies
* Historical quarterly financial data
* Automated synthesis generation

---

# Key Features

### Multi-Sector Monitoring

Track companies across multiple industries using a common architecture.

### Historical Financial Tracking

Store and visualize quarterly financial performance across multiple years.

### Automated Synthesis

Generate:

* Trend Analysis
* Investing Lens
* Sector Insights

from structured company data.

### Document Tracking

Register and manage investor presentations and company documents where available.

### Interactive Dashboard

Explore:

* Financial metrics
* Historical trends
* Generated synthesis
* Source documents
* Pipeline operations

### Automated Refresh Pipeline

Support periodic updates through a scheduler-driven workflow.

---

# System Architecture

Public Data Sources
↓
Ingestion Layer
↓
Document Parsing
↓
Structured Metric Extraction
↓
SQLite Database
↓
Synthesis Generation
↓
Streamlit Dashboard

The platform separates data ingestion from visualization, making it easy to add new sectors while reusing the same database, synthesis engine, and frontend.

---

# Technology Stack

| Layer                     | Technology                  |
| ------------------------- | --------------------------- |
| Dashboard                 | Streamlit                   |
| Visualizations            | Plotly                      |
| Database                  | SQLite                      |
| PDF Parsing               | PyMuPDF                     |
| Data Validation           | Pydantic                    |
| Scheduling                | APScheduler                 |
| Historical Financial Data | Screener.in / Yahoo Finance |
| LLM Support               | Claude / Gemini / OpenAI    |

---

# Dashboard Modules

## Metrics Tab

Visualizes historical financial performance through interactive charts.

Examples include:

* Revenue
* Profitability
* Earnings Per Share
* Operating Margins
* Company-specific operational metrics

---

## Synthesis Tab

Generates:

### Trend Analysis

Highlights major financial and operational developments.

### Investing Lens

Identifies:

* Growth signals
* Operational strengths
* Strategic opportunities
* Potential risks

---

## Documents Tab

Displays available investor presentations and source documents.

When filings are unavailable, the platform falls back gracefully to historical financial data.

---

## Pipeline Tab

Allows users to:

* Run refresh workflows
* Update company information
* Regenerate synthesis
* Monitor pipeline execution

---

# Database Design

The platform uses SQLite for simplicity and portability.

Core tables:

* companies
* documents
* chunks
* metrics
* synthesis
* refresh_log

This structure supports both document-driven and metric-driven intelligence generation.

---

# Running Locally

## Clone Repository

```bash
git clone <repository-url>
cd sector-intelligence-monitor
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Configure Environment

```bash
cp .env.example .env
```

Add your preferred LLM provider credentials if you want to run extraction and synthesis generation.

## Start Dashboard

```bash
streamlit run app.py
```

---

# Pipeline Execution

Run a complete refresh:

```bash
python scheduler.py
```

Start scheduled updates:

```bash
python scheduler.py --daemon
```

---

# Extensibility

The system was designed to support new sectors with minimal changes.

Adding a new sector typically requires:

1. Registering companies
2. Adding an ingestion connector
3. Mapping metrics into the existing schema

The dashboard, database, and synthesis engine automatically reuse the new data without requiring frontend changes.

---

# Assignment Requirements Coverage

| Requirement                   | Status |
| ----------------------------- | ------ |
| Public company coverage       | ✅      |
| Historical financial tracking | ✅      |
| Structured database           | ✅      |
| Automated metric storage      | ✅      |
| Trend analysis                | ✅      |
| Investing lens generation     | ✅      |
| Dashboard visualization       | ✅      |
| Source document tracking      | ✅      |
| Scheduled refresh workflow    | ✅      |
| Multi-sector architecture     | ✅      |
| Public deployment             | ✅      |

---

# Future Improvements

* Additional sectors and geographies
* More document ingestion sources
* Advanced cross-sector comparison
* Automated notifications for new filings
* Enhanced analyst-style reporting

---
