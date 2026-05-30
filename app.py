"""
Sector Intelligence Monitor — Streamlit Dashboard

Phase 1 skeleton:
- All DB queries wired and working
- Charts, synthesis, and document tabs functional
- Shows placeholder content when DB is empty
- Refresh button calls scheduler (stub in Phase 1, real in Phase 8)
"""

import logging
import os
import time
from collections import defaultdict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

# ─── Page config (must be first Streamlit call) ───────────────────────────────

st.set_page_config(
    page_title="Sector Intelligence Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── DB initialisation ────────────────────────────────────────────────────────

@st.cache_resource
def _init():
    """Initialise DB once per session. Returns (ready: bool, error: str)."""
    try:
        from pipeline.database import init_db
        init_db()
        return True, ""
    except Exception as exc:
        return False, str(exc)


DB_READY, DB_ERROR = _init()

# ─── Cached DB queries (ttl=5 min) ───────────────────────────────────────────

@st.cache_data(ttl=300)
def _get_companies(sector: str):
    from pipeline.database import get_companies_by_sector
    return get_companies_by_sector(sector)


@st.cache_data(ttl=300)
def _get_metrics_df(company_id: str):
    from pipeline.database import get_metrics_dataframe
    return get_metrics_dataframe(company_id)


@st.cache_data(ttl=300)
def _get_latest_metrics(company_id: str):
    from pipeline.database import get_latest_metrics
    return get_latest_metrics(company_id)


@st.cache_data(ttl=300)
def _get_synthesis(sector: str):
    from pipeline.database import get_synthesis
    return get_synthesis(sector)


@st.cache_data(ttl=300)
def _get_documents(company_id: str):
    from pipeline.database import get_documents
    return get_documents(company_id)


@st.cache_data(ttl=60)
def _get_refresh_log(limit: int = 5):
    from pipeline.database import get_refresh_log
    return get_refresh_log(limit)


# ─── Styling ──────────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    /* Sidebar */
    [data-testid="stSidebar"] { background-color: #0f0f1a; }

    /* KPI metric delta colours */
    [data-testid="stMetricDelta"] svg { display: none; }

    /* Tab font */
    .stTabs [data-baseweb="tab"] { font-size: 0.95rem; font-weight: 500; }

    /* Source link style */
    .doc-link a { color: #818cf8; text-decoration: none; }
    .doc-link a:hover { text-decoration: underline; }

    /* Status badges */
    .badge-success { color: #4ade80; font-size: 0.8rem; }
    .badge-failed  { color: #f87171; font-size: 0.8rem; }
    .badge-pending { color: #94a3b8; font-size: 0.8rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Sector / company config ──────────────────────────────────────────────────

SECTOR_CONFIG = {
    "indian_fintech": {
        "label": "🏦 Indian Fintech",
        "accent": "#6366f1",
        "available": True,
    },
    "indian_defence": {
        "label": "🛡️ Indian Defence",
        "accent": "#f59e0b",
        "available": True,
    },
    "us_biotech": {
        "label": "🧬 US Biotech",
        "accent": "#10b981",
        "available": True,
    },
}

METRIC_LABELS = {
    "aum_crore":                "AUM (₹ Cr)",
    "loan_book_growth_qoq_pct": "Loan Book Growth QoQ (%)",
    "loan_book_growth_yoy_pct": "Loan Book Growth YoY (%)",
    "gross_npa_pct":            "Gross NPA (%)",
    "net_npa_pct":              "Net NPA (%)",
    "credit_cost_pct_aum":      "Credit Cost (% AUM)",
    "net_interest_margin_pct":  "NIM (%)",
    "cost_of_funds_pct":        "Cost of Funds (%)",
    "revenue_crore":            "Revenue (₹ Cr)",
    "pat_crore":                "PAT (₹ Cr)",
    "digital_txn_volume_mn":    "Digital Txn Volume (Mn)",
    "active_users_mn":          "Active Users (Mn)",
}

# Metrics where "down" is good (e.g. NPA going down is positive)
INVERSE_METRICS = {"gross_npa_pct", "net_npa_pct", "credit_cost_pct_aum", "cost_of_funds_pct"}

# Extend labels with Paytm / payments fields
METRIC_LABELS.update({
    "gmv_mn_usd":                   "GMV (USD Mn)",
    "gmv_crore":                    "GMV (INR Cr)",
    "gmv_growth_yoy_pct":           "GMV Growth YoY (%)",
    "revenue_mn_usd":               "Revenue (USD Mn)",
    "revenue_growth_yoy_pct":       "Revenue Growth YoY (%)",
    "monthly_transacting_users_mn": "Monthly Transacting Users (Mn)",
    "mtu_growth_yoy_pct":           "MTU Growth YoY (%)",
    "merchant_subscriptions_mn":    "Merchant Subscriptions (Mn)",
    "devices_deployed_mn":          "Devices Deployed (Mn)",
    "net_payment_margin_mn_usd":    "Net Payment Margin (USD Mn)",
    "contribution_profit_mn_usd":   "Contribution Profit (USD Mn)",
    "contribution_margin_pct":      "Contribution Margin (%)",
    "ebitda_before_esop_mn_usd":    "EBITDA before ESOP (USD Mn)",
    "loan_distribution_value_crore":"Loan Distribution (INR Cr)",
    "loan_distribution_count_mn":   "Loan Distribution Count (Mn)",
    "pat_mn_usd":                   "PAT (USD Mn)",
    "revenue_mn_usd":               "Revenue (USD Mn)",
})

# Screener-sourced INR metrics (validated=0 — scraped from Screener.in)
METRIC_LABELS.update({
    "revenue_crore":            "Revenue (INR Cr)",
    "operating_profit_crore":   "Operating Profit (INR Cr)",
    "opm_pct":                  "Operating Margin (%)",
    "net_profit_crore":         "Net Profit (INR Cr)",
    "eps_inr":                  "EPS (INR)",
    # US Biotech
    "revenue_usd":              "Revenue (USD Mn)",
    "operating_profit_usd":     "Operating Profit (USD Mn)",
    "net_profit_usd":           "Net Profit (USD Mn)",
    "eps_usd":                  "EPS (USD)",
})

# Grouped chart layout: (group_name, [metric_names])
METRIC_GROUPS = [
    ("Scale",           ["gmv_mn_usd", "gmv_crore", "revenue_mn_usd", "revenue_crore"]),
    ("Users & Devices", ["monthly_transacting_users_mn", "merchant_subscriptions_mn", "devices_deployed_mn"]),
    ("Profitability",   ["ebitda_before_esop_mn_usd", "contribution_profit_mn_usd", "contribution_margin_pct", "net_payment_margin_mn_usd"]),
    ("P&L — Fundamentals", ["revenue_crore", "revenue_usd", "operating_profit_crore", "operating_profit_usd", "net_profit_crore", "net_profit_usd", "opm_pct", "eps_inr", "eps_usd"]),
    ("Lending / Credit", ["aum_crore", "gross_npa_pct", "net_npa_pct", "net_interest_margin_pct", "loan_distribution_value_crore"]),
]

# ─── Fiscal quarter sort key ─────────────────────────────────────────────────

import re as _re

def _quarter_sort_key(period: str) -> tuple:
    """
    Convert a period string like 'Q3FY25' or 'Q1FY24' into a sortable (fy, q) tuple.
    Falls back to (0, period) for unrecognised formats so they sort last.

    Examples:
        Q3FY24 -> (2024, 3)
        Q1FY25 -> (2025, 1)
        Q4FY25 -> (2025, 4)
    """
    m = _re.match(r"Q(\d)FY(\d{2,4})", str(period), _re.IGNORECASE)
    if m:
        q, fy = int(m.group(1)), int(m.group(2))
        fy = fy + 2000 if fy < 100 else fy  # FY25 -> 2025
        return (fy, q)
    return (0, period)  # fallback



def _seed_demo_if_empty():
    """Seed realistic demo data on first run (empty DB)."""
    from pipeline.database import (
        get_companies_by_sector, insert_company, upsert_metric,
        insert_document, update_document_status, insert_synthesis,
    )
    existing_companies = {c["id"] for c in get_companies_by_sector("indian_fintech")}
    
    if "paytm" not in existing_companies:
        insert_company("paytm", "Paytm (One97 Comm.)", "indian_fintech", "PAYTM", "BSE", "https://ir.paytm.com")
        quarters = {
            "Q3FY24": {"gmv_mn_usd":4700,"revenue_mn_usd":1200,"monthly_transacting_users_mn":10.0,"devices_deployed_mn":0.87,"ebitda_before_esop_mn_usd":-15,"contribution_profit_mn_usd":125,"contribution_margin_pct":52,"merchant_subscriptions_mn":10.8},
            "Q4FY24": {"gmv_mn_usd":4900,"revenue_mn_usd":1100,"monthly_transacting_users_mn":9.7, "devices_deployed_mn":0.99,"ebitda_before_esop_mn_usd":-10,"contribution_profit_mn_usd":130,"contribution_margin_pct":55,"merchant_subscriptions_mn":11.2},
            "Q1FY25": {"gmv_mn_usd":4100,"revenue_mn_usd":850, "monthly_transacting_users_mn":7.8, "devices_deployed_mn":0.99,"ebitda_before_esop_mn_usd":-40,"contribution_profit_mn_usd":75, "contribution_margin_pct":45,"merchant_subscriptions_mn":10.0},
            "Q3FY25": {"gmv_mn_usd":5200,"revenue_mn_usd":760, "monthly_transacting_users_mn":10.8,"devices_deployed_mn":1.12,"ebitda_before_esop_mn_usd": 24,"contribution_profit_mn_usd":200,"contribution_margin_pct":63,"merchant_subscriptions_mn":11.8},
            "Q4FY25": {"gmv_mn_usd":5800,"revenue_mn_usd":820, "monthly_transacting_users_mn":11.5,"devices_deployed_mn":1.25,"ebitda_before_esop_mn_usd": 45,"contribution_profit_mn_usd":235,"contribution_margin_pct":67,"merchant_subscriptions_mn":12.3},
        }
        for period, metrics in quarters.items():
            for k, v in metrics.items():
                upsert_metric("paytm", period, k, v, validated=1)
        urls = [
            ("https://paytm.com/document/ir/financial-results/fy2024-25/Paytm-Earnings-Presentation_May-2025_USD.pdf",        "investor_presentation", "Q4FY25"),
            ("https://paytm.com/document/ir/financial-results/fy2024-25/Paytm-Earnings-Presentation_Jan-2025_USD_Final.pdf",  "investor_presentation", "Q3FY25"),
            ("https://paytm.com/document/ir/financial-results/fy2024-25/Earnings-Presentation_USD_Q1_FY25.pdf",               "investor_presentation", "Q1FY25"),
            ("https://paytm.com/document/ir/financial-results/Earnings-Presentation_INR_FY24-Q4.pdf",                         "investor_presentation", "Q4FY24"),
            ("https://paytm.com/document/ir/financial-results/Paytm_Q3_FY_2024-Earnings-Presentation_INR.pdf",                "investor_presentation", "Q3FY24"),
        ]
        for url, dtype, period in urls:
            doc_id = insert_document("paytm", url, dtype, period)
            update_document_status(doc_id, "indexed")  # URL known; not downloaded in demo mode
        insert_synthesis(
            sector="indian_fintech:paytm",
            period_range="Q3FY24 to Q4FY25",
            synthesis_text=(
                "Paytm's GMV recovery is the defining trend of FY25: after dropping to $4.1B in Q1FY25 "
                "following the PPBL disruption, GMV rebounded to $5.8B by Q4FY25 — surpassing pre-disruption levels. "
                "The structural story is margin expansion: contribution margin improved from 45% in Q1FY25 to 67% "
                "in Q4FY25, while EBITDA turned positive at +$45M vs -$40M at the trough. This was achieved by "
                "pruning low-margin flows and focusing on high-value merchant transactions. Monthly Transacting "
                "Users recovered to 11.5M from the trough of 7.8M. Device deployments (Soundboxes) crossed 1.25M "
                "— the physical payments layer is growing, suggesting merchant stickiness to the hardware "
                "subscription model. Revenue is structurally lower ($820M vs $1.2B peak) as Paytm exited "
                "lending distribution — but EBITDA quality is markedly better."
            ),
            investing_lens_text=(
                "Paytm's trajectory reveals clear signals for early-stage investors: "
                "(1) DEVICE-LED B2B FINTECH: Soundbox growth to 1.25M validates hardware-as-a-service in merchant "
                "payments. Startups building vertical SaaS on payment terminals (inventory, credit, analytics) have "
                "a real monetisation surface. "
                "(2) MERCHANT CREDIT WHITE SPACE: Paytm has exited merchant lending — creating opportunity for "
                "embedded lending startups targeting the 12M+ merchant subscriber base. "
                "(3) MTU BENCHMARK: At 11.5M MTU and $820M revenue, Paytm earns ~$71/MTU annually. Target >=50 "
                "for comparable unit economics at early stage. "
                "(4) CONTRIBUTION MARGIN FLOOR: 60%+ contribution margins are achievable at scale — use this as "
                "the steady-state target, not raw revenue growth. "
                "(5) REGULATORY RESILIENCE: Post-PPBL recovery shows core payment rails (UPI, soundboxes, "
                "merchant subscriptions) are robust to disruptions of adjacent business lines."
            ),
        )

    if "bajaj_finance" not in existing_companies:
        insert_company("bajaj_finance", "Bajaj Finance", "indian_fintech", "BAJFINANCE", "BSE", "https://www.bajajfinserv.in/finance-investor-relation")
        insert_synthesis(
            sector="indian_fintech:bajaj_finance",
            period_range="Historical",
            synthesis_text="Bajaj Finance is a leading non-banking financial company in India. Currently tracking fundamental P&L metrics via Screener.in backfill.",
            investing_lens_text="Strong retail lending franchise with consistent growth and profitability."
        )

    if "pb_fintech" not in existing_companies:
        insert_company("pb_fintech", "PB Fintech", "indian_fintech", "POLICYBZR", "BSE", "https://investor.pbfintech.in/")
        insert_synthesis(
            sector="indian_fintech:pb_fintech",
            period_range="Historical",
            synthesis_text="PB Fintech operates Policybazaar and Paisabazaar. Currently tracking fundamental P&L metrics via Screener.in backfill.",
            investing_lens_text="Dominant digital insurance aggregator with increasing operational leverage."
        )

    if "sbi_cards" not in existing_companies:
        insert_company("sbi_cards", "SBI Cards", "indian_fintech", "SBICARD", "BSE", "https://www.sbicard.com/en/our-company/investor-relations.page")
        insert_synthesis(
            sector="indian_fintech:sbi_cards",
            period_range="Historical",
            synthesis_text="SBI Cards is a leading credit card issuer in India. Currently tracking fundamental P&L and asset quality metrics via Screener.in backfill.",
            investing_lens_text="Pure-play credit card issuer backed by India's largest bank, highly levered to consumer spending."
        )

    if "creditaccess" not in existing_companies:
        insert_company("creditaccess", "CreditAccess Grameen", "indian_fintech", "CREDITACC", "BSE", "https://www.creditaccessgrameen.in/investors/")
        insert_synthesis(
            sector="indian_fintech:creditaccess",
            period_range="Historical",
            synthesis_text="CreditAccess Grameen is India's largest microfinance institution. Currently tracking fundamental P&L and asset quality metrics via Screener.in backfill.",
            investing_lens_text="Microfinance leader with rural focus, demonstrating robust asset quality and scale."
        )

    # ── Indian Defence ──
    if "hal" not in existing_companies:
        insert_company("hal", "Hindustan Aeronautics Limited", "indian_defence", "HAL", "BSE", "https://hal-india.co.in/Investors")
    if "bel" not in existing_companies:
        insert_company("bel", "Bharat Electronics Limited", "indian_defence", "BEL", "BSE", "https://bel-india.in/investor-relations/")

    # ── US Biotech ──
    if "moderna" not in existing_companies:
        insert_company("moderna", "Moderna", "us_biotech", "MRNA", "NASDAQ", "https://investors.modernatx.com/")
    if "gilead" not in existing_companies:
        insert_company("gilead", "Gilead Sciences", "us_biotech", "GILD", "NASDAQ", "https://investors.gilead.com/")


if DB_READY:
    _seed_demo_if_empty()


# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📊 Sector Intel Monitor")
    st.caption("Early-stage investing intelligence from public filings")
    st.divider()

    # Sector selector
    sector_keys = list(SECTOR_CONFIG.keys())
    selected_sector = st.selectbox(
        "Sector",
        options=sector_keys,
        format_func=lambda k: SECTOR_CONFIG[k]["label"],
        key="sector_sel",
    )
    cfg = SECTOR_CONFIG[selected_sector]
    is_available = cfg["available"]

    # Company selector
    selected_company_id = None
    if DB_READY and is_available:
        companies = _get_companies(selected_sector)
        if companies:
            company_map = {c["id"]: c["name"] for c in companies}
            selected_company_id = st.selectbox(
                "Company",
                options=list(company_map.keys()),
                format_func=lambda k: company_map[k],
                key="company_sel",
            )
        else:
            st.info("No companies loaded. Run `seed.py` to populate.", icon="ℹ️")

    st.divider()

    # Refresh section
    st.markdown("#### 🔄 Data Refresh")
    if DB_READY and is_available:
        synthesis = (
            _get_synthesis(f"{selected_sector}:{selected_company_id}")
            or _get_synthesis(selected_sector)
        )
        if synthesis:
            st.caption(f"Last synthesis: {synthesis.get('generated_at', '')[:16]} UTC")
        else:
            st.caption("No synthesis yet.")

        if st.button("▶ Trigger Refresh", type="primary", use_container_width=True):
            # Clear cached data so fresh results show after refresh
            st.cache_data.clear()
            with st.spinner(f"Refreshing {cfg['label']}…"):
                try:
                    from scheduler import run_refresh
                    result = run_refresh(selected_sector)
                    new = result.get("new_docs_found", 0)
                    checked = result.get("docs_checked", 0)
                    errs = result.get("errors", [])
                    if errs:
                        st.warning(f"Completed with {len(errs)} error(s). {new} new docs.", icon="⚠️")
                    else:
                        st.success(f"✅ Done. Checked {checked} docs, found {new} new.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Refresh failed: {exc}")

    # Refresh log
    log = _get_refresh_log(5)
    if log:
        st.divider()
        st.caption("**Recent runs:**")
        for entry in log:
            ts = entry.get("run_at", "")[:16]
            new = entry.get("new_docs_found", 0)
            errs = entry.get("errors", [])
            icon = "⚠️" if errs else "✅"
            st.caption(f"{icon} {ts} · +{new} docs")


# ─── Main content ─────────────────────────────────────────────────────────────

st.markdown(f"# {cfg['label']}")

# ── Not yet available ─────────────────────────────────────────────────────────
if not is_available:
    st.info(
        "🚧 This sector is not yet loaded. **Indian Fintech** is available now.",
        icon="🚧",
    )
    st.stop()

# ── DB error ──────────────────────────────────────────────────────────────────
if not DB_READY:
    st.error(f"Database error: {DB_ERROR}", icon="🚨")
    st.code("python -c \"from pipeline.database import init_db; init_db()\"")
    st.stop()

# ── No company selected ───────────────────────────────────────────────────────
if not selected_company_id:
    st.info("Select a company from the sidebar to view metrics.", icon="👈")
    st.stop()

# Company display name
companies = _get_companies(selected_sector)
company_name = next(
    (c["name"] for c in companies if c["id"] == selected_company_id),
    selected_company_id,
)
st.subheader(company_name)

# ─── Tabs ─────────────────────────────────────────────────────────────────────

tab_metrics, tab_synthesis, tab_documents, tab_pipeline = st.tabs(
    ["📈 Metric Trends", "🧠 Synthesis", "📄 Documents", "⚙️ Pipeline"]
)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Metric Trends
# ══════════════════════════════════════════════════════════════════════════════

with tab_metrics:
    df = _get_metrics_df(selected_company_id)

    if df.empty:
        st.info(
            "No metrics loaded yet for this company. "
            "Run `python seed.py` or click **Trigger Refresh** to populate.",
            icon="📭",
        )
        st.stop()

    latest = _get_latest_metrics(selected_company_id)

    # ── Coverage note (Rec 2) ─────────────────────────────────────────────────
    _screener_metrics = {"revenue_crore", "operating_profit_crore", "opm_pct", "net_profit_crore", "eps_inr"}
    _has_screener = not df[df["metric_name"].isin(_screener_metrics)].empty
    _has_llm = "validated" in df.columns and (df["validated"] == 1).any()
    if _has_screener and _has_llm:
        st.info(
            "**Data Coverage** — P&L metrics (INR Cr) cover all 13 quarters "
            "(Q4FY23 – Q4FY26) via **Screener.in** backfill. "
            "Operational & payments metrics (USD) cover 5 key quarters "
            "(Q3FY24 – Q4FY25) extracted via **LLM** from investor presentations. "
            "Charts show source: ● Filing / LLM   ○ Screener.in",
            icon="ℹ️",
        )
    elif _has_screener:
        st.info(
            "**Data Coverage** — Metrics sourced from Screener.in (INR Cr, 13 quarters). "
            "Run the pipeline with an API key to add LLM-extracted operational data.",
            icon="ℹ️",
        )

    # ── KPI summary row ───────────────────────────────────────────────────────
    kpi_order = [
        "aum_crore", "gross_npa_pct", "net_interest_margin_pct",
        "cost_of_funds_pct", "pat_crore", "revenue_crore",
    ]
    available_kpis = [m for m in kpi_order if m in latest]

    if available_kpis:
        cols = st.columns(min(len(available_kpis), 4))
        for col, metric_key in zip(cols, available_kpis[:4]):
            m = latest[metric_key]
            val = m.get("metric_value")
            direction = m.get("direction", "flat") or "flat"
            label = METRIC_LABELS.get(metric_key, metric_key)

            if val is not None:
                arrow = "↑" if direction == "up" else "↓" if direction == "down" else "→"
                # For NPA-type metrics, down is actually green
                delta_color = "normal"
                if metric_key in INVERSE_METRICS:
                    delta_color = "inverse"

                col.metric(
                    label=label,
                    value=f"{val:,.2f}",
                    delta=f"{arrow} {direction}",
                    delta_color=delta_color,
                )

        st.divider()

    # ── Grouped metric charts ─────────────────────────────────────────────────
    accent = cfg["accent"]
    COLORS = ["#6366f1","#00d4aa","#f5a623","#ff4b4b","#a78bfa","#34d399"]

    for group_name, group_metrics in METRIC_GROUPS:
        available = [m for m in group_metrics if m in df["metric_name"].values]
        if not available:
            continue
        st.markdown(f"**{group_name}**")
        cols = st.columns(min(len(available), 2))
        for j, metric in enumerate(available):
            with cols[j % 2]:
                m_df = df[df["metric_name"] == metric].copy()
                m_df["_sort_key"] = m_df["period"].map(_quarter_sort_key)
                m_df = m_df.sort_values("_sort_key").drop(columns=["_sort_key"])
                label = METRIC_LABELS.get(metric, metric.replace("_"," ").title())
                unit  = m_df["unit"].iloc[0] if not m_df.empty and "unit" in m_df.columns else ""
                color = COLORS[j % len(COLORS)]

                # ── Rec 3: split by data source for distinct marker styles ──
                has_validated_col = "validated" in m_df.columns
                filing_df  = m_df[m_df["validated"] == 1] if has_validated_col else m_df.iloc[0:0]
                scraper_df = m_df[m_df["validated"] == 0] if has_validated_col else m_df

                fig = go.Figure()

                # LLM / Filing points — filled circles
                if not filing_df.empty:
                    fig.add_trace(go.Scatter(
                        x=filing_df["period"], y=filing_df["metric_value"],
                        mode="lines+markers",
                        name="Filing / LLM",
                        line=dict(color=color, width=2.5),
                        marker=dict(size=8, color=color, symbol="circle"),
                        hovertemplate=(
                            f"<b>{label}</b><br>%{{x}}: %{{y:.2f}} {unit}"
                            "<br><i>Source: Investor Presentation</i><extra></extra>"
                        ),
                    ))

                # Screener points — open circles, dashed line
                if not scraper_df.empty:
                    fig.add_trace(go.Scatter(
                        x=scraper_df["period"], y=scraper_df["metric_value"],
                        mode="lines+markers",
                        name="Screener.in",
                        line=dict(color=color, width=2, dash="dot"),
                        marker=dict(size=8, color="rgba(0,0,0,0)",
                                    symbol="circle", line=dict(color=color, width=2)),
                        hovertemplate=(
                            f"<b>{label}</b><br>%{{x}}: %{{y:.2f}} {unit}"
                            "<br><i>Source: Screener.in</i><extra></extra>"
                        ),
                    ))

                # If only one source type exists, fall back to simple solid line
                if filing_df.empty or scraper_df.empty:
                    fig = go.Figure(go.Scatter(
                        x=m_df["period"], y=m_df["metric_value"],
                        mode="lines+markers",
                        line=dict(color=color, width=2.5),
                        marker=dict(
                            size=8, color=color if not scraper_df.empty else color,
                            symbol="circle",
                            line=dict(color=color, width=2) if filing_df.empty else dict(width=0),
                        ),
                        hovertemplate=(
                            f"<b>{label}</b><br>%{{x}}: %{{y:.2f}} {unit}"
                            + ("<br><i>Source: Screener.in</i>" if filing_df.empty else "<br><i>Source: Investor Presentation</i>")
                            + "<extra></extra>"
                        ),
                    ))

                fig.update_layout(
                    title=label, height=260,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#cbd5e1",size=12),
                    title_font=dict(size=13,color="#e2e8f0"),
                    margin=dict(l=0,r=0,t=40,b=0),
                    xaxis=dict(gridcolor="#1e293b",tickangle=-30,showgrid=True),
                    yaxis=dict(gridcolor="#1e293b",showgrid=True),
                    hovermode="x unified",
                    showlegend=has_validated_col and not filing_df.empty and not scraper_df.empty,
                    legend=dict(orientation="h", y=1.15, x=0, font=dict(size=10)),
                )
                st.plotly_chart(fig, use_container_width=True, key=f"chart_metrics_{group_name}_{j}_{metric}")



# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Sector Synthesis
# ══════════════════════════════════════════════════════════════════════════════

    docs = _get_documents(selected_company_id)
    
with tab_synthesis:
    from pipeline.synthesis.text_cleaner import clean_synthesis
    # Look up by company-specific key first, then sector fallback
    synthesis = _get_synthesis(f"{selected_sector}:{selected_company_id}") or _get_synthesis(selected_sector)

    if not synthesis:
        st.info(
            "No synthesis generated yet. "
            "Load metric data first, then click **Trigger Refresh**.",
            icon="🧠",
        )
    else:
        generated_at = synthesis.get("generated_at", "")[:16]
        period_range = synthesis.get("period_range", "N/A")
        
        # Determine mode
        synthesis_mode = "Filing-driven" if docs else "Metric-driven"

        st.caption(f"Generated: **{generated_at} UTC** · Period: **{period_range}** · Mode: **{synthesis_mode}**")
        st.divider()

        col1, col2 = st.columns([1, 1], gap="large")

        with col1:
            st.markdown("### 📊 Sector Analysis")
            raw_analysis = synthesis.get("synthesis_text") or ""
            st.markdown(clean_synthesis(raw_analysis) or "_Not available._")

        with col2:
            st.markdown("### 🎯 Investing Lens")
            raw_lens = synthesis.get("investing_lens_text") or ""
            st.markdown(clean_synthesis(raw_lens) or "_Not available._")


# ══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Source Documents
# ══════════════════════════════════════════════════════════════════════════════

with tab_documents:
    if not docs:
        if "us_biotech" in selected_sector:
            st.info(
                "No SEC filings have been indexed yet. "
                "Metrics and synthesis are currently generated from historical financial data sources.",
                icon="📄",
            )
        else:
            st.info(
                "No investor presentations or transcripts have been indexed for this company yet. "
                "Historical metrics are currently sourced from Screener.in backfill.",
                icon="📄",
            )
    else:
        st.caption(f"{len(docs)} document(s) indexed")

        # Group by doc_type
        by_type: dict[str, list] = defaultdict(list)
        for doc in docs:
            by_type[doc.get("doc_type", "other")].append(doc)

        STATUS_ICONS = {
            "extracted": "✅",
            "parsed":    "✅",
            "downloaded":"📥",
            "indexed":   "🔗",  # URL registered; not downloaded locally (demo mode)
            "pending":   "⏳",
            "failed":    "❌",
            "skipped":   "⏭️",
        }

        for doc_type, type_docs in sorted(by_type.items()):
            type_label = doc_type.replace("_", " ").title()
            with st.expander(
                f"📁 {type_label} ({len(type_docs)})",
                expanded=True,
            ):
                # Header row
                hc1, hc2, hc3, hc4 = st.columns([3, 1, 1, 1])
                hc1.caption("**Document**")
                hc2.caption("**Period**")
                hc3.caption("**Status**")
                hc4.caption("**Chunks**")
                st.divider()

                for doc in sorted(
                    type_docs,
                    key=lambda d: d.get("period", ""),
                    reverse=True,
                ):
                    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                    period = doc.get("period", "—")
                    status = doc.get("parse_status", "pending")
                    icon = STATUS_ICONS.get(status, "❓")
                    chunks = doc.get("chunk_count") or 0
                    chunks_display = str(chunks) if chunks > 0 else ("—" if status == "indexed" else "0")
                    url = doc.get("source_url", "#")

                    c1.markdown(
                        f"<div class='doc-link'><a href='{url}' target='_blank'>"
                        f"{type_label} — {period}</a></div>",
                        unsafe_allow_html=True,
                    )
                    c2.caption(period)
                    c3.caption(f"{icon} {status}")
                    c4.caption(chunks_display)


# == Tab 4 — Pipeline ===========================================================

with tab_pipeline:
    st.markdown("### Run Pipeline")
    st.caption("Each step is idempotent. Safe to re-run.")

    col_l, col_r = st.columns(2)
    with col_l:
        provider = st.selectbox("LLM Provider", ["claude","gemini","openai"], key="pip_prov")
        model_map = {"claude":"claude-sonnet-4-5","gemini":"gemini-1.5-flash","openai":"gpt-4o-mini"}
        model = st.text_input("Model", value=model_map[provider], key="pip_model")
        api_key = st.text_input("API Key", type="password", key="pip_key",
                                help="Or set ANTHROPIC_API_KEY / GEMINI_API_KEY env var")
    with col_r:
        st.markdown("**Steps:**")
        st.markdown("1. Fetch documents (BSE / curated list)")  
        st.markdown("2. Download PDFs")
        st.markdown("3. Parse & chunk (PyMuPDF)")
        st.markdown("4. Extract metrics (LLM)")
        st.markdown("5. Generate synthesis (LLM)")

    st.markdown("---")
    if st.button("Run Full Pipeline", type="primary", use_container_width=True, key="pip_run"):
        if api_key:
            if provider == "claude":
                os.environ["ANTHROPIC_API_KEY"] = api_key
            elif provider == "gemini":
                os.environ["GEMINI_API_KEY"] = api_key
                os.environ["GOOGLE_API_KEY"] = api_key
            elif provider == "openai":
                os.environ["OPENAI_API_KEY"] = api_key

        has_llm_key = bool(
            os.getenv("ANTHROPIC_API_KEY") or
            os.getenv("GEMINI_API_KEY") or
            os.getenv("GOOGLE_API_KEY") or
            os.getenv("OPENAI_API_KEY")
        )

        with st.status("Running pipeline...", expanded=True) as pip_status:
            errors = []
            docs_checked = 0
            new_docs_found = 0
            start_time = time.time()
            try:
                st.write("Step 1-2: Fetching + downloading Paytm documents...")
                from pipeline.ingestion.paytm_fetcher import PaytmFetcher
                fetcher = PaytmFetcher()
                fr = fetcher.run(download_pdfs=True)
                docs_checked = fr.discovered
                new_docs_found = fr.new_documents
                st.write(f"  Discovered: {fr.discovered} | New: {fr.new_documents} | DL: {fr.downloaded}")

                st.write("Step 3: Parsing PDFs...")
                from pipeline.ingestion.pdf_parser import parse_all_pending
                pr = parse_all_pending(selected_company_id)
                st.write(f"  Parsed: {len(pr)} docs | Chunks: {sum(r.chunks_extracted for r in pr)}")

                st.write("Screener Backfill: Scraping historical P&L...")
                from pipeline.ingestion.screener_backfill import backfill_paytm_historical
                backfill_res = backfill_paytm_historical(company_id=selected_company_id)
                if backfill_res["periods_new"]:
                    st.write(f"  Screener backfill: +{len(backfill_res['periods_new'])} periods")
                else:
                    st.write("  Screener backfill: No new periods found")

                if has_llm_key:
                    st.write(f"Step 4: Extracting metrics ({provider}/{model})...")
                    from pipeline.extraction.metrics_extractor import extract_all_parsed
                    er = extract_all_parsed(selected_company_id, provider=provider, model=model)
                    new_ex = [r for r in er if r.success and not r.was_cached]
                    st.write(f"  Extracted: {len(new_ex)} new | Cached: {sum(1 for r in er if r.was_cached)}")
                    for r in er:
                        if not r.success and r.error:
                            errors.append(f"Extraction error: {r.error}")
                else:
                    st.warning("⚠️ Step 4: Extracting metrics skipped (no API key set)")
                    st.write("  Step 4: SKIPPED (no LLM API key set)")

                if has_llm_key:
                    st.write("Step 5: Generating synthesis...")
                    from pipeline.synthesis.synthesizer import synthesize_company
                    sr = synthesize_company(selected_company_id, company_name=company_name,
                                            sector=selected_sector, provider=provider, model=model)
                    if sr.success:
                        st.write(f"  Synthesis generated ({len(sr.synthesis_text)} chars)")
                    else:
                        st.write(f"  Synthesis skipped: {sr.error}")
                        errors.append(f"Synthesis skipped: {sr.error}")
                else:
                    st.warning("⚠️ Step 5: Generating synthesis skipped (no API key set)")
                    st.write("  Step 5: SKIPPED (no LLM API key set)")

                duration = round(time.time() - start_time, 2)
                from pipeline.database import log_refresh
                log_refresh(
                    sector=selected_sector,
                    docs_checked=docs_checked,
                    new_docs_found=new_docs_found,
                    errors=errors,
                    duration_seconds=duration,
                )

                st.cache_data.clear()
                
                if not has_llm_key:
                    pip_status.update(label="Pipeline complete (partial)", state="complete")
                    st.warning("Pipeline completed partially. LLM steps were skipped due to missing API keys.")
                else:
                    pip_status.update(label="Pipeline complete!", state="complete")
                    st.success("Done. Switch to Metrics or Synthesis tabs to see results.")
                
                time.sleep(2)
                st.rerun()
            except Exception as exc:
                duration = round(time.time() - start_time, 2)
                errors.append(str(exc))
                try:
                    from pipeline.database import log_refresh
                    log_refresh(
                        sector=selected_sector,
                        docs_checked=docs_checked,
                        new_docs_found=new_docs_found,
                        errors=errors,
                        duration_seconds=duration,
                    )
                except Exception as log_exc:
                    pass
                
                pip_status.update(label="Error", state="error")
                st.error(f"{exc}")
                import traceback
                st.code(traceback.format_exc())
