"""
Historical backfill from Screener.in — Paytm (INR Crore).

Scraped from: https://www.screener.in/company/PAYTM/consolidated/
Section: Quarterly Results
Data confirmed: 2026-05-29

Screener uses calendar quarters (Mar/Jun/Sep/Dec ending).
Mapping to Indian Fiscal Year quarters:
  Jan-Mar (Q4): Mar ending  → Q4FYxx   (e.g. Mar 2023 → Q4FY23)
  Apr-Jun (Q1): Jun ending  → Q1FYxx+1 (e.g. Jun 2023 → Q1FY24)
  Jul-Sep (Q2): Sep ending  → Q2FYxx+1 (e.g. Sep 2023 → Q2FY24)
  Oct-Dec (Q3): Dec ending  → Q3FYxx+1 (e.g. Dec 2023 → Q3FY24)

Adds these metrics (all INR Crore unless noted):
  revenue_crore         — "Sales" from Screener quarterly P&L
  operating_profit_crore — "Operating Profit" (EBIT-like; before other income)
  opm_pct               — "OPM %" operating profit margin
  net_profit_crore      — "Net Profit"
  eps_inr               — "EPS in Rs"

Source attribution stored via upsert_metric source_doc_id=None, validated=0
(validated=0 marks scraped/aggregated data vs LLM-extracted from filings)
"""

import logging
import os
import re
import sys
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── Screener period → fiscal quarter mapping ──────────────────────────────────

_MONTH_MAP = {
    "Mar": (4, 0),   # Q4 of current FY  (Mar 2023 → Q4FY23)
    "Jun": (1, 1),   # Q1 of next FY     (Jun 2023 → Q1FY24)
    "Sep": (2, 1),   # Q2 of next FY     (Sep 2023 → Q2FY24)
    "Dec": (3, 1),   # Q3 of next FY     (Dec 2023 → Q3FY24)
}

def _screener_to_fiscal(label: str) -> Optional[str]:
    """
    Convert 'Mar 2023' → 'Q4FY23', 'Jun 2023' → 'Q1FY24', etc.
    Returns None for unrecognised labels.
    """
    m = re.match(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})", label)
    if not m:
        return None
    month_abbr, year_str = m.group(1), int(m.group(2))
    if month_abbr not in _MONTH_MAP:
        return None
    q_num, fy_offset = _MONTH_MAP[month_abbr]
    fy = (year_str + fy_offset) % 100          # last 2 digits of fiscal year
    return f"Q{q_num}FY{fy:02d}"


def _parse_crore(val: str) -> Optional[float]:
    """Parse '2,334' or '-131' or '-6%' into float. Returns None for empty/dash."""
    val = val.strip().replace(",", "").replace("\xa0", "").replace("&nbsp;", "")
    val = val.rstrip("%").strip()
    if not val or val in ("-", ""):
        return None
    try:
        return float(val)
    except ValueError:
        return None


# ── Screener scraper ──────────────────────────────────────────────────────────

SCREENER_URL = "https://www.screener.in/company/PAYTM/consolidated/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "https://www.screener.in/",
}

# Row label → (metric_name, unit, direction)
ROW_MAP = {
    "Sales":            ("revenue_crore",          "INR Cr", "up"),
    "Operating Profit": ("operating_profit_crore",  "INR Cr", "up"),
    "OPM %":            ("opm_pct",                "%",      "up"),
    "Net Profit":       ("net_profit_crore",        "INR Cr", "up"),
    "EPS in Rs":        ("eps_inr",                "INR",    "up"),
}

# Normalise row label for matching
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[+\xa0&;nbsp]+", "", s)).strip()


def fetch_screener_quarterly(url: str = SCREENER_URL) -> dict[str, dict[str, float]]:
    """
    Scrape Screener.in quarterly P&L for Paytm.

    Returns:
        {
          "Q4FY23": {"revenue_crore": 2334.0, "net_profit_crore": -168.0, ...},
          "Q1FY24": {...},
          ...
        }
    """
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    content = r.text

    # Extract quarters section
    qmatch = re.search(
        r'<section[^>]*id=["\']quarters["\'][^>]*>(.*?)</section>',
        content, re.DOTALL | re.IGNORECASE
    )
    if not qmatch:
        raise ValueError("No #quarters section found on Screener page")

    raw = qmatch.group(1)

    # Parse header row → fiscal period labels
    header_row = re.search(r'<thead[^>]*>(.*?)</thead>', raw, re.DOTALL)
    if not header_row:
        raise ValueError("No <thead> in quarters section")

    th_cells = re.findall(r'<th[^>]*>(.*?)</th>', header_row.group(1), re.DOTALL)
    periods: list[str] = []
    for cell in th_cells:
        text = re.sub(r'<[^>]+>', '', cell).strip()
        fiscal = _screener_to_fiscal(text)
        periods.append(fiscal)   # None for the first (row label) column

    # Parse data rows
    tbody = re.search(r'<tbody[^>]*>(.*?)</tbody>', raw, re.DOTALL)
    if not tbody:
        raise ValueError("No <tbody> in quarters section")

    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody.group(1), re.DOTALL)

    result: dict[str, dict[str, float]] = {}

    for row_html in rows:
        cells_html = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.DOTALL)
        if not cells_html:
            continue

        # Row label (first cell)
        label_raw = re.sub(r'<[^>]+>', '', cells_html[0]).strip()
        label_raw = _norm(label_raw)

        # Find matching metric
        matched_metric = None
        for key, metric_info in ROW_MAP.items():
            if _norm(key) in label_raw or label_raw in _norm(key):
                matched_metric = metric_info
                break
        if matched_metric is None:
            continue

        metric_name, unit, direction = matched_metric

        # Data cells (columns 1..N, matching periods[1..N])
        for col_idx, cell_html in enumerate(cells_html[1:], start=1):
            if col_idx >= len(periods):
                break
            period = periods[col_idx]
            if not period:
                continue

            cell_text = re.sub(r'<[^>]+>', '', cell_html).strip()
            value = _parse_crore(cell_text)
            if value is None:
                continue

            if period not in result:
                result[period] = {}
            result[period][metric_name] = (value, unit, direction)

    return result


def backfill_paytm_historical(
    company_id: str = "paytm",
    dry_run: bool = False,
) -> dict:
    """
    Fetch Screener.in quarterly data and write missing periods to the metrics table.

    Args:
        company_id: Target company
        dry_run:    If True, print what would be written but don't write

    Returns:
        Summary dict with keys: periods_found, periods_new, metrics_written, skipped
    """
    from pipeline.database import upsert_metric, get_metrics_dataframe

    logger.info(f"Fetching Screener.in quarterly data for {company_id}...")
    scraped = fetch_screener_quarterly()
    logger.info(f"  Scraped {len(scraped)} quarters from Screener.in")

    # What periods already have data?
    existing_df = get_metrics_dataframe(company_id)
    existing_periods = set(existing_df["period"].unique()) if not existing_df.empty else set()
    logger.info(f"  Existing periods in DB: {sorted(existing_periods)}")

    summary = {
        "periods_found": sorted(scraped.keys()),
        "periods_new": [],
        "periods_existing": sorted(existing_periods),
        "metrics_written": 0,
        "skipped": 0,
    }

    for period, metrics in sorted(scraped.items()):
        is_new = period not in existing_periods
        if not is_new:
            summary["skipped"] += 1
            logger.info(f"  SKIP {period} — already in DB")
            continue

        summary["periods_new"].append(period)
        for metric_name, (value, unit, direction) in metrics.items():
            if dry_run:
                logger.info(f"  [DRY] {period} {metric_name} = {value} {unit}")
            else:
                upsert_metric(
                    company_id=company_id,
                    period=period,
                    metric_name=metric_name,
                    metric_value=value,
                    unit=unit,
                    direction=direction,
                    source_doc_id=None,
                    validated=0,   # 0 = scraped/aggregated, not LLM-extracted from filing
                )
                summary["metrics_written"] += 1
                logger.info(f"  WRITE {period} {metric_name} = {value} {unit}")

    return summary


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault("DATABASE_PATH", "data/sector_intel.db")

    dry = "--dry-run" in sys.argv
    from pipeline.database import init_db
    init_db()
    result = backfill_paytm_historical(dry_run=dry)
    print(f"\nScraped periods: {result['periods_found']}")
    print(f"New periods: {result['periods_new']}")
    print(f"Metrics written: {result['metrics_written']}")
    print(f"Periods skipped (already in DB): {result['skipped']}")
