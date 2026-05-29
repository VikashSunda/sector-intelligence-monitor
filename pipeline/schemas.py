"""
Pydantic schemas for:
  1. LLM extraction outputs (one per sector)
  2. Synthesis engine output
  3. FastAPI response models

All extraction fields are Optional — extraction is best-effort.
None means the metric was not mentioned in the source text, not that it is zero.
"""

from typing import Optional
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# LLM Extraction Schemas
# ═══════════════════════════════════════════════════════════════════════════════

class FintechMetrics(BaseModel):
    """
    Metrics extracted from one quarter's Indian Fintech earnings call / filing.
    Used for: Bajaj Finance, SBI Cards, Paytm, PB Fintech, CAMS, CDSL,
              Zaggle, CreditAccess Grameen, Five Star Business Finance.

    Fields cover two sub-types:
      (A) Payments / super-app companies (Paytm): GMV, MTU, devices, net payment margin
      (B) Lending / NBFC companies (Bajaj Finance, SBI Cards): AUM, NPA, NIM
    All fields are Optional — use only the ones relevant to the company.
    """
    # ── Payments / super-app (Paytm-specific) ─────────────────────────────────
    gmv_mn_usd: Optional[float] = Field(
        None,
        description="Gross Merchandise Value in USD millions for the quarter."
    )
    gmv_crore: Optional[float] = Field(
        None,
        description="Gross Merchandise Value in INR crores for the quarter."
    )
    gmv_growth_yoy_pct: Optional[float] = Field(
        None,
        description="GMV year-on-year growth as a percentage."
    )
    monthly_transacting_users_mn: Optional[float] = Field(
        None,
        description="Monthly Transacting Users (MTU) in millions."
    )
    mtu_growth_yoy_pct: Optional[float] = Field(
        None,
        description="MTU year-on-year growth as a percentage."
    )
    merchant_subscriptions_mn: Optional[float] = Field(
        None,
        description="Number of merchant subscriptions in millions."
    )
    devices_deployed_mn: Optional[float] = Field(
        None,
        description="Payment devices (Soundboxes, PoS, etc.) deployed in millions."
    )
    net_payment_margin_mn_usd: Optional[float] = Field(
        None,
        description="Net Payment Margin in USD millions for the quarter."
    )
    contribution_profit_mn_usd: Optional[float] = Field(
        None,
        description="Contribution Profit in USD millions."
    )
    contribution_margin_pct: Optional[float] = Field(
        None,
        description="Contribution Margin as a percentage of revenue."
    )
    ebitda_before_esop_mn_usd: Optional[float] = Field(
        None,
        description="Adjusted EBITDA (before ESOP costs) in USD millions."
    )
    loan_distribution_value_crore: Optional[float] = Field(
        None,
        description="Value of loans distributed through the platform in INR crores."
    )
    loan_distribution_count_mn: Optional[float] = Field(
        None,
        description="Number of loans distributed in millions."
    )

    # ── Revenue (shared — all fintech) ────────────────────────────────────────
    revenue_mn_usd: Optional[float] = Field(
        None,
        description="Total revenue from operations in USD millions."
    )
    revenue_crore: Optional[float] = Field(
        None,
        description="Total revenue or Net Interest Income in crores."
    )
    revenue_growth_yoy_pct: Optional[float] = Field(
        None,
        description="Revenue year-on-year growth as a percentage."
    )
    pat_crore: Optional[float] = Field(
        None,
        description="Profit After Tax in crores."
    )
    pat_mn_usd: Optional[float] = Field(
        None,
        description="Profit After Tax in USD millions."
    )

    # ── Loan book / AUM (Bajaj Finance, SBI Cards, etc.) ─────────────────────
    aum_crore: Optional[float] = Field(
        None,
        description="Total AUM or loan book in Indian Rupee crores. Numeric value only."
    )
    loan_book_growth_qoq_pct: Optional[float] = Field(
        None,
        description="Loan book quarter-on-quarter growth as a percentage. E.g. 5.2 means 5.2%."
    )
    loan_book_growth_yoy_pct: Optional[float] = Field(
        None,
        description="Loan book year-on-year growth as a percentage."
    )

    # ── Asset quality ─────────────────────────────────────────────────────────
    gross_npa_pct: Optional[float] = Field(
        None,
        description="Gross NPA (non-performing assets) as a percentage of total loans."
    )
    net_npa_pct: Optional[float] = Field(
        None,
        description="Net NPA as a percentage of net loans."
    )
    credit_cost_pct_aum: Optional[float] = Field(
        None,
        description="Credit cost as a percentage of AUM. Annualised if stated so."
    )

    # ── Profitability (lending) ────────────────────────────────────────────────
    net_interest_margin_pct: Optional[float] = Field(
        None,
        description="Net Interest Margin (NIM) as a percentage."
    )
    cost_of_funds_pct: Optional[float] = Field(
        None,
        description="Cost of funds / borrowings as a percentage."
    )

    # ── Digital / operational ─────────────────────────────────────────────────

    digital_txn_volume_mn: Optional[float] = Field(
        None,
        description="Digital transaction volume in millions for the quarter."
    )
    active_users_mn: Optional[float] = Field(
        None,
        description="Monthly or quarterly active users in millions."
    )


class DefenceMetrics(BaseModel):
    """
    Metrics for Indian Defence companies.
    Phase 2 extensibility — not used in Phase 1 MVP.
    Used for: HAL, BEL, MTAR, Paras Defence, Astra Microwave,
              Data Patterns, Zen Technologies, Bharat Forge.
    """
    order_book_value_crore: Optional[float] = Field(
        None, description="Total order book value in crores."
    )
    domestic_order_pct: Optional[float] = Field(
        None, description="Domestic orders as percentage of total order book."
    )
    export_order_pct: Optional[float] = Field(
        None, description="Export orders as percentage of total order book."
    )
    revenue_growth_qoq_pct: Optional[float] = Field(
        None, description="Revenue QoQ growth percentage."
    )
    revenue_growth_yoy_pct: Optional[float] = Field(
        None, description="Revenue YoY growth percentage."
    )
    ebitda_margin_pct: Optional[float] = Field(
        None, description="EBITDA margin as percentage."
    )
    rd_spend_pct_revenue: Optional[float] = Field(
        None, description="R&D spend as percentage of revenue."
    )
    new_order_wins_crore: Optional[float] = Field(
        None, description="New order wins value in crores this quarter."
    )
    new_order_geography: Optional[str] = Field(
        None, description="Geography of major new orders (e.g. domestic, Middle East, SEA)."
    )
    new_order_category: Optional[str] = Field(
        None, description="Product category of major new orders (e.g. radar, ammunition, avionics)."
    )


class BiotechMetrics(BaseModel):
    """
    Metrics for US Biotech companies.
    Phase 2 extensibility — not used in Phase 1 MVP.
    Used for: Moderna, Regeneron, Vertex, Biogen, Illumina,
              10x Genomics, PacBio, Recursion.
    """
    pipeline_phase1: Optional[int] = Field(
        None, description="Number of drug candidates in Phase 1 clinical trials."
    )
    pipeline_phase2: Optional[int] = Field(
        None, description="Number of drug candidates in Phase 2 clinical trials."
    )
    pipeline_phase3: Optional[int] = Field(
        None, description="Number of drug candidates in Phase 3 clinical trials."
    )
    pipeline_nda_bla: Optional[int] = Field(
        None, description="Number of NDA or BLA submissions pending FDA review."
    )
    cash_equivalents_mn: Optional[float] = Field(
        None, description="Cash and cash equivalents in millions USD."
    )
    cash_runway_quarters: Optional[float] = Field(
        None, description="Estimated cash runway in quarters at current burn rate."
    )
    product_revenue_mn: Optional[float] = Field(
        None, description="Product sales revenue in millions USD."
    )
    royalty_revenue_mn: Optional[float] = Field(
        None, description="Royalty revenue in millions USD."
    )
    collaboration_revenue_mn: Optional[float] = Field(
        None, description="Collaboration or milestone revenue in millions USD."
    )
    trial_readout_outcome: Optional[str] = Field(
        None, description="Outcome of key trial readout this quarter: positive / negative / mixed."
    )
    trial_readout_indication: Optional[str] = Field(
        None, description="Disease indication for the key trial readout."
    )
    ai_ml_investment_note: Optional[str] = Field(
        None, description="Notable AI/ML investment, partnership, or platform callout."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Synthesis Schema
# ═══════════════════════════════════════════════════════════════════════════════

class SynthesisOutput(BaseModel):
    """Output from the two-call synthesis engine."""
    synthesis_text: str = Field(
        ...,
        description=(
            "Sector-level trend analysis: which metrics are improving/deteriorating, "
            "what product bets multiple companies are making, structural vs cyclical signals."
        )
    )
    investing_lens_text: str = Field(
        ...,
        description=(
            "Early-stage investing lens: where incumbents are investing (validates startup market), "
            "where they are struggling (white space), what they are partnering vs building, "
            "benchmark metrics for evaluating early-stage companies in this space."
        )
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI / API Response Models
# ═══════════════════════════════════════════════════════════════════════════════

class CompanyResponse(BaseModel):
    id: str
    name: str
    sector: str
    ticker: Optional[str] = None
    exchange: Optional[str] = None
    ir_url: Optional[str] = None


class MetricPoint(BaseModel):
    period: str
    metric_name: str
    metric_value: Optional[float] = None
    unit: Optional[str] = None
    direction: Optional[str] = None


class DocumentResponse(BaseModel):
    id: int
    company_id: str
    source_url: str
    doc_type: Optional[str] = None
    period: Optional[str] = None
    parse_status: str
    chunk_count: int


class SynthesisResponse(BaseModel):
    sector: str
    period_range: Optional[str] = None
    synthesis_text: Optional[str] = None
    investing_lens_text: Optional[str] = None
    generated_at: Optional[str] = None


class RefreshResult(BaseModel):
    status: str
    sector: str
    docs_checked: int
    new_docs_found: int
    errors: list[str]
    duration_seconds: float


class RefreshLogEntry(BaseModel):
    id: int
    run_at: str
    sector: Optional[str] = None
    docs_checked: int
    new_docs_found: int
    errors: list[str]
    duration_seconds: Optional[float] = None
