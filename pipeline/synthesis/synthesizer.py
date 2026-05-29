"""
Phase 6: Synthesis generation.

Takes extracted metrics from SQLite and generates two pieces of analysis via LLM:

  1. synthesis_text   — Trend analysis across quarters:
                        which metrics are improving/deteriorating, what structural
                        vs cyclical signals exist, what product bets are getting traction.

  2. investing_lens_text — Early-stage investing lens:
                        where incumbents are investing (validates startup market),
                        where they are struggling (white space),
                        what they are partnering vs building,
                        benchmark metrics for evaluating early-stage companies.

Flow:
  1. Query metrics table for company (or sector)
  2. Pivot into a period × metric table (wide format)
  3. Build structured prompt with the data table + context
  4. Call LLM → raw JSON → validate with SynthesisOutput
  5. Store via insert_synthesis (sector, period_range, texts)

Idempotency: insert_synthesis uses INSERT OR REPLACE, always updates.

Usage:
    from pipeline.synthesis.synthesizer import synthesize_company, synthesize_sector

    result = synthesize_company("paytm", "Paytm")
    print(result.synthesis_text[:500])

    result = synthesize_sector("indian_fintech")
    print(result.investing_lens_text[:500])
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from pipeline.database import (
    get_companies_by_sector,
    get_metrics_dataframe,
    get_metrics_summary_for_sector,
    insert_synthesis,
)
from pipeline.extraction.llm_client import LLMClient
from pipeline.schemas import SynthesisOutput

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "claude")
DEFAULT_MODEL    = os.getenv("LLM_MODEL", "claude-sonnet-4-5")


# ─── Return type ──────────────────────────────────────────────────────────────

@dataclass
class SynthesisResult:
    sector: str
    period_range: str
    synthesis_text: str = ""
    investing_lens_text: str = ""
    success: bool = False
    error: Optional[str] = None
    companies_covered: list[str] = field(default_factory=list)
    metrics_rows: int = 0

    def __str__(self) -> str:
        status = "OK" if self.success else "FAIL"
        return (
            f"SynthesisResult({status} sector={self.sector} "
            f"period_range={self.period_range} "
            f"companies={self.companies_covered})"
        )


# ─── Prompt builder ───────────────────────────────────────────────────────────

def _format_metrics_table(df: pd.DataFrame) -> str:
    """
    Convert long-format metrics DataFrame into a readable markdown table.
    Pivots to: period (rows) × metric_name (columns).
    """
    if df.empty:
        return "(no metrics data available)"

    # Pivot: index=period, columns=metric_name, values=metric_value
    pivot = df.pivot_table(
        index="period",
        columns="metric_name",
        values="metric_value",
        aggfunc="first",
    )
    pivot.index.name = "Period"
    pivot = pivot.sort_index()

    # Format as readable text table
    lines = []
    cols = list(pivot.columns)
    lines.append("Period       | " + " | ".join(f"{c:<20}" for c in cols))
    lines.append("-" * (14 + 23 * len(cols)))
    for period, row in pivot.iterrows():
        vals = []
        for c in cols:
            v = row.get(c)
            vals.append(f"{v:<20.2f}" if pd.notna(v) else f"{'N/A':<20}")
        lines.append(f"{period:<12} | " + " | ".join(vals))
    return "\n".join(lines)


def _build_synthesis_prompt(
    company_or_sector: str,
    period_range: str,
    metrics_table: str,
    context_note: str = "",
) -> str:
    """Build a two-part synthesis prompt returning JSON with synthesis_text and investing_lens_text."""
    return f"""You are a senior investment analyst specializing in Indian fintech and payments.

You have been given {period_range} of quarterly metrics for {company_or_sector}.
{context_note}

METRICS DATA:
{metrics_table}

Your task is to produce TWO pieces of analysis. Return ONLY valid JSON — no markdown, no explanation.

JSON SCHEMA:
{{
  "synthesis_text": "<string: 300-500 words>",
  "investing_lens_text": "<string: 300-500 words>"
}}

INSTRUCTIONS:

1. synthesis_text — Write a factual trend analysis:
   - Which metrics are improving quarter-over-quarter and year-over-year?
   - Which metrics are deteriorating or showing stress?
   - What are the 2-3 most important structural trends visible in the data?
   - What product bets appear to be getting traction (based on metric growth)?
   - Keep it data-driven: cite specific numbers and percentage changes.

2. investing_lens_text — Write an early-stage investing analysis:
   - Where is this incumbent investing heavily? (This validates the startup opportunity)
   - Where is the incumbent struggling? (This is the white space for startups)
   - What are the key operating benchmarks a startup in this space should aim for?
   - What does the incumbent's trajectory suggest about the next 2-3 years of the market?
   - Which adjacent markets or customer segments appear underserved?

Be specific, direct, and data-grounded. Avoid generic statements.

Return ONLY the JSON object:"""


def _build_company_context(company_id: str, df: pd.DataFrame) -> str:
    """Build context note describing the company and data coverage."""
    periods = sorted(df["period"].unique().tolist())
    metrics = sorted(df["metric_name"].unique().tolist())
    return (
        f"Company: {company_id.title()} (Indian Fintech / Payments sector)\n"
        f"Periods covered: {', '.join(periods)}\n"
        f"Metrics available: {', '.join(metrics)}"
    )


# ─── Core synthesis ───────────────────────────────────────────────────────────

def _call_llm_and_validate(
    prompt: str,
    provider: str,
    model: str,
) -> tuple[str, str, Optional[str]]:
    """
    Call LLM, parse JSON, validate with SynthesisOutput.
    Returns (synthesis_text, investing_lens_text, error_or_None).
    """
    try:
        client = LLMClient(provider=provider, model=model)
        raw = client.complete(prompt, max_tokens=2048, temperature=0.3)
    except Exception as e:
        return "", "", f"LLM call failed: {e}"

    try:
        json_str = client._extract_json(raw)
        if not json_str:
            raise ValueError("No JSON found in response")
        data = json.loads(json_str)
    except Exception as e:
        return "", "", f"JSON parse failed: {e} | Raw: {raw[:300]}"

    try:
        validated = SynthesisOutput(**data)
        return validated.synthesis_text, validated.investing_lens_text, None
    except Exception as e:
        # Try extracting text fields directly even if validation fails
        s = data.get("synthesis_text", "")
        i = data.get("investing_lens_text", "")
        if s and i:
            return s, i, None
        return "", "", f"Validation failed: {e}"


def synthesize_company(
    company_id: str,
    company_name: str = "",
    sector: str = "indian_fintech",
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    last_n_quarters: int = 8,
) -> SynthesisResult:
    """
    Generate synthesis for a single company based on stored metrics.

    Args:
        company_id:     e.g. "paytm"
        company_name:   Display name (defaults to company_id.title())
        sector:         Sector this company belongs to (for DB storage key)
        provider:       LLM provider
        model:          LLM model
        last_n_quarters: How many most-recent quarters to include

    Returns:
        SynthesisResult
    """
    name = company_name or company_id.title()
    result = SynthesisResult(sector=f"{sector}:{company_id}", period_range="")

    # ── Load metrics ───────────────────────────────────────────────────────────
    df = get_metrics_dataframe(company_id)
    if df is None or df.empty:
        result.error = f"No metrics found for {company_id}. Run Phase 4 first."
        logger.warning(result.error)
        return result

    # Limit to last N quarters
    periods = sorted(df["period"].unique())[-last_n_quarters:]
    df = df[df["period"].isin(periods)]
    period_range = f"{periods[0]} to {periods[-1]}" if len(periods) > 1 else periods[0]

    result.period_range = period_range
    result.metrics_rows = len(df)
    result.companies_covered = [company_id]

    logger.info(
        f"Synthesizing {name}: {len(periods)} quarters, "
        f"{df['metric_name'].nunique()} unique metrics | {provider}/{model}"
    )

    # ── Format data ───────────────────────────────────────────────────────────
    metrics_table = _format_metrics_table(df)
    context = _build_company_context(company_id, df)
    prompt = _build_synthesis_prompt(name, period_range, metrics_table, context)

    # ── LLM call ──────────────────────────────────────────────────────────────
    synthesis_text, investing_lens_text, error = _call_llm_and_validate(
        prompt, provider, model
    )
    if error:
        result.error = error
        logger.error(f"Synthesis failed for {company_id}: {error}")
        return result

    result.synthesis_text = synthesis_text
    result.investing_lens_text = investing_lens_text
    result.success = True

    # ── Store ──────────────────────────────────────────────────────────────────
    insert_synthesis(
        sector=f"{sector}:{company_id}",
        period_range=period_range,
        synthesis_text=synthesis_text,
        investing_lens_text=investing_lens_text,
    )
    logger.info(f"Synthesis stored: {name} | {period_range}")
    return result


def synthesize_sector(
    sector: str,
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    last_n_quarters: int = 4,
) -> SynthesisResult:
    """
    Generate cross-company sector synthesis using aggregated metrics.

    Args:
        sector:          e.g. "indian_fintech"
        provider / model: LLM config
        last_n_quarters: Number of recent quarters to include

    Returns:
        SynthesisResult
    """
    result = SynthesisResult(sector=sector, period_range="")

    # ── Load sector-wide metrics ───────────────────────────────────────────────
    rows = get_metrics_summary_for_sector(sector, last_n_quarters)
    if not rows:
        result.error = f"No metrics found for sector '{sector}'. Run extraction first."
        logger.warning(result.error)
        return result

    df = pd.DataFrame(rows)
    companies = sorted(df["company_id"].unique().tolist())
    periods = sorted(df["period"].unique().tolist())
    period_range = f"{periods[0]} to {periods[-1]}" if len(periods) > 1 else periods[0]

    result.period_range = period_range
    result.companies_covered = companies
    result.metrics_rows = len(df)

    logger.info(
        f"Sector synthesis: {sector} | {len(companies)} companies | "
        f"{len(periods)} quarters | {len(df)} metric rows"
    )

    # ── Format: one table per company ─────────────────────────────────────────
    table_sections = []
    for company in companies:
        company_df = df[df["company_id"] == company].copy()
        company_name = company_df["company_name"].iloc[0] if "company_name" in company_df else company
        table = _format_metrics_table(
            company_df[["period", "metric_name", "metric_value"]]
        )
        table_sections.append(f"### {company_name}\n{table}")
    metrics_table = "\n\n".join(table_sections)

    context = (
        f"Sector: {sector}\n"
        f"Companies: {', '.join(companies)}\n"
        f"Periods: {period_range}"
    )
    prompt = _build_synthesis_prompt(
        f"the {sector} sector ({', '.join(companies)})",
        period_range,
        metrics_table,
        context,
    )

    # ── LLM call ──────────────────────────────────────────────────────────────
    synthesis_text, investing_lens_text, error = _call_llm_and_validate(
        prompt, provider, model
    )
    if error:
        result.error = error
        logger.error(f"Sector synthesis failed: {error}")
        return result

    result.synthesis_text = synthesis_text
    result.investing_lens_text = investing_lens_text
    result.success = True

    insert_synthesis(
        sector=sector,
        period_range=period_range,
        synthesis_text=synthesis_text,
        investing_lens_text=investing_lens_text,
    )
    logger.info(f"Sector synthesis stored: {sector} | {period_range}")
    return result


def get_latest_synthesis(sector_or_key: str) -> Optional[dict]:
    """Retrieve the most recent stored synthesis for a sector or company key."""
    from pipeline.database import get_synthesis
    return get_synthesis(sector_or_key)
