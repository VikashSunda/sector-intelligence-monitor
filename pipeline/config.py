"""
Company registry and sector definitions.
Fixed — do not make dynamic. All 25 companies defined here.
Sector modules reference this dict directly.
"""

from datetime import datetime
from typing import Optional


# ─── Full company registry ────────────────────────────────────────────────────

COMPANIES: dict[str, dict] = {

    # ── Indian Fintech ────────────────────────────────────────────────────────
    "bajaj_finance": {
        "name": "Bajaj Finance",
        "sector": "indian_fintech",
        "ticker": "BAJFINANCE",
        "bse_scrip": "532648",
        "screener_slug": "BAJFINANCE",
        "exchange": "BSE",
        "ir_url": "https://www.bajajfinserv.in/bajaj-finance-limited-investor-relations",
    },
    "sbi_cards": {
        "name": "SBI Cards",
        "sector": "indian_fintech",
        "ticker": "SBICARD",
        "bse_scrip": "543066",
        "screener_slug": "SBICARD",
        "exchange": "BSE",
        "ir_url": "https://www.sbicard.com/en/personal/investor-relations.page",
    },
    "paytm": {
        "name": "Paytm",
        "sector": "indian_fintech",
        "ticker": "PAYTM",
        "bse_scrip": "543396",
        "screener_slug": "PAYTM",
        "exchange": "BSE",
        "ir_url": "https://investor.paytm.com",
    },
    "pb_fintech": {
        "name": "PB Fintech (PolicyBazaar)",
        "sector": "indian_fintech",
        "ticker": "POLICYBZR",
        "bse_scrip": "543390",
        "screener_slug": "POLICYBZR",
        "exchange": "BSE",
        "ir_url": "https://ir.pbfintech.com",
    },
    "cams": {
        "name": "CAMS",
        "sector": "indian_fintech",
        "ticker": "CAMS",
        "bse_scrip": "543232",
        "screener_slug": "CAMS",
        "exchange": "BSE",
        "ir_url": "https://www.cams.io/investor-relations",
    },
    "cdsl": {
        "name": "CDSL",
        "sector": "indian_fintech",
        "ticker": "CDSL",
        "bse_scrip": "543219",
        "screener_slug": "CDSL",
        "exchange": "BSE",
        "ir_url": "https://www.cdslindia.com/investor-relations",
    },
    "zaggle": {
        "name": "Zaggle",
        "sector": "indian_fintech",
        "ticker": "ZAGGLE",
        "bse_scrip": "543977",
        "screener_slug": "ZAGGLE",
        "exchange": "BSE",
        "ir_url": "https://www.zaggle.in/investors",
    },
    "creditaccess_grameen": {
        "name": "CreditAccess Grameen",
        "sector": "indian_fintech",
        "ticker": "CREDITACC",
        "bse_scrip": "541770",
        "screener_slug": "CREDITACC",
        "exchange": "BSE",
        "ir_url": "https://www.creditaccessgrameen.in/investor-relations",
    },
    "five_star_finance": {
        "name": "Five Star Business Finance",
        "sector": "indian_fintech",
        "ticker": "FIVESTAR",
        "bse_scrip": "543663",
        "screener_slug": "FIVESTAR",
        "exchange": "BSE",
        "ir_url": "https://www.fivestarbusiness.in/investors",
    },

    # ── Indian Defence ────────────────────────────────────────────────────────
    "hal": {
        "name": "HAL",
        "sector": "indian_defence",
        "ticker": "HAL",
        "bse_scrip": "541154",
        "screener_slug": "HAL",
        "exchange": "BSE",
        "ir_url": "https://hal-india.co.in/investors",
    },
    "bel": {
        "name": "BEL",
        "sector": "indian_defence",
        "ticker": "BEL",
        "bse_scrip": "500049",
        "screener_slug": "BEL",
        "exchange": "BSE",
        "ir_url": "https://bel-india.in/investors",
    },
    "mtar_technologies": {
        "name": "MTAR Technologies",
        "sector": "indian_defence",
        "ticker": "MTAR",
        "bse_scrip": "543270",
        "screener_slug": "MTAR",
        "exchange": "BSE",
        "ir_url": "https://mtartech.com/investor-relations",
    },
    "paras_defence": {
        "name": "Paras Defence",
        "sector": "indian_defence",
        "ticker": "PARAS",
        "bse_scrip": "543809",
        "screener_slug": "PARAS",
        "exchange": "BSE",
        "ir_url": "https://parasdefence.com/investors",
    },
    "astra_microwave": {
        "name": "Astra Microwave",
        "sector": "indian_defence",
        "ticker": "ASTRAMICRO",
        "bse_scrip": "532493",
        "screener_slug": "ASTRAMICRO",
        "exchange": "BSE",
        "ir_url": "https://www.astramicrowaveproducts.com/investors",
    },
    "data_patterns": {
        "name": "Data Patterns",
        "sector": "indian_defence",
        "ticker": "DATAPATTNS",
        "bse_scrip": "543428",
        "screener_slug": "DATAPATTNS",
        "exchange": "BSE",
        "ir_url": "https://www.datapatternsindia.com/investor-relations",
    },
    "zen_technologies": {
        "name": "Zen Technologies",
        "sector": "indian_defence",
        "ticker": "ZENTEC",
        "bse_scrip": "533287",
        "screener_slug": "ZENTEC",
        "exchange": "BSE",
        "ir_url": "https://www.zentechnologies.com/investors",
    },
    "bharat_forge": {
        "name": "Bharat Forge (Defence Segment)",
        "sector": "indian_defence",
        "ticker": "BHARATFORG",
        "bse_scrip": "500493",
        "screener_slug": "BHARATFORG",
        "exchange": "BSE",
        "ir_url": "https://bharatforge.com/investors",
    },

    # ── US Biotech ────────────────────────────────────────────────────────────
    "moderna": {
        "name": "Moderna",
        "sector": "us_biotech",
        "ticker": "MRNA",
        "cik": "0001682852",
        "exchange": "NASDAQ",
        "ir_url": "https://investors.modernatx.com",
    },
    "regeneron": {
        "name": "Regeneron",
        "sector": "us_biotech",
        "ticker": "REGN",
        "cik": "0000872589",
        "exchange": "NASDAQ",
        "ir_url": "https://investor.regeneron.com",
    },
    "vertex_pharma": {
        "name": "Vertex Pharmaceuticals",
        "sector": "us_biotech",
        "ticker": "VRTX",
        "cik": "0000875320",
        "exchange": "NASDAQ",
        "ir_url": "https://investors.vrtx.com",
    },
    "biogen": {
        "name": "Biogen",
        "sector": "us_biotech",
        "ticker": "BIIB",
        "cik": "0000875045",
        "exchange": "NASDAQ",
        "ir_url": "https://investors.biogen.com",
    },
    "illumina": {
        "name": "Illumina",
        "sector": "us_biotech",
        "ticker": "ILMN",
        "cik": "0001110803",
        "exchange": "NASDAQ",
        "ir_url": "https://investor.illumina.com",
    },
    "10x_genomics": {
        "name": "10x Genomics",
        "sector": "us_biotech",
        "ticker": "TXG",
        "cik": "0001770605",
        "exchange": "NASDAQ",
        "ir_url": "https://investor.10xgenomics.com",
    },
    "pacbio": {
        "name": "Pacific Biosciences",
        "sector": "us_biotech",
        "ticker": "PACB",
        "cik": "0001372514",
        "exchange": "NASDAQ",
        "ir_url": "https://investor.pacb.com",
    },
    "recursion_pharma": {
        "name": "Recursion Pharmaceuticals",
        "sector": "us_biotech",
        "ticker": "RXRX",
        "cik": "0001601712",
        "exchange": "NASDAQ",
        "ir_url": "https://ir.recursion.com",
    },
}

SECTORS: dict[str, str] = {
    "indian_fintech": "Indian Fintech",
    "indian_defence": "Indian Defence",
    "us_biotech": "US Biotech",
}

# MVP phase 1 scope — expanded in Phase 8
MVP_COMPANIES = ["paytm", "bajaj_finance", "sbi_cards"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_companies_for_sector(sector: str) -> dict[str, dict]:
    """Return all companies belonging to a sector."""
    return {k: v for k, v in COMPANIES.items() if v.get("sector") == sector}


def date_to_quarter(date_str: str) -> str:
    """
    Convert a date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS) to Indian financial
    quarter label: Q1FY22, Q2FY22, ..., Q4FY25.

    Indian FY runs April–March:
      Apr–Jun  → Q1FY{Y+1}  e.g. Apr 2024 → Q1FY25
      Jul–Sep  → Q2FY{Y+1}  e.g. Jul 2024 → Q2FY25
      Oct–Dec  → Q3FY{Y+1}  e.g. Oct 2024 → Q3FY25
      Jan–Mar  → Q4FY{Y}    e.g. Jan 2024 → Q4FY24
    """
    date_str = date_str[:10]  # Trim to YYYY-MM-DD
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    month, year = dt.month, dt.year

    if month >= 4:
        # Apr-Jun-Jul-Sep-Oct-Dec: FY ends next calendar year
        fy = year + 1
        quarter = (month - 4) // 3 + 1   # 4→1, 7→2, 10→3
    else:
        # Jan-Feb-Mar: FY ends this calendar year
        fy = year
        quarter = 4   # Always Q4 for Jan/Feb/Mar

    return f"Q{quarter}FY{str(fy)[2:]}"


def get_quarter_range(from_fy_year: int = 2022) -> list[str]:
    """
    Return all quarter labels from Q1FY{from_fy_year} to the current quarter.
    Used to build the expected quarter list for coverage checks.
    """
    quarters = []
    # Start of FY: April 1 of (from_fy_year - 1)
    dt = datetime(from_fy_year - 1, 4, 1)
    now = datetime.now()

    while dt <= now:
        quarters.append(date_to_quarter(dt.strftime("%Y-%m-%d")))
        month = dt.month + 3
        year = dt.year + (1 if month > 12 else 0)
        month = month - 12 if month > 12 else month
        dt = datetime(year, month, 1)

    return quarters
