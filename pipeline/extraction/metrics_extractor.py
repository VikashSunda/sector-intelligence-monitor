"""
Phase 4: LLM metrics extraction.

Strategy:
- One LLM call per document (not per chunk): concatenate all chunk texts into
  a single document, send to Claude Sonnet, extract FintechMetrics JSON.
- This is cost-efficient (~2000-3000 input tokens per presentation) and gives
  the LLM full context to resolve cross-slide references (e.g. YoY changes
  mentioned on a different slide from the raw numbers).

Flow per document:
  1. Load chunks from DB (already parsed in Phase 3)
  2. Build extraction prompt with full document text
  3. Call LLMClient → raw JSON
  4. Validate with FintechMetrics Pydantic model
  5. Store each non-null field as a row in metrics via upsert_metric
  6. Update document parse_status → 'extracted'

Idempotency:
  - Check if metrics already exist for (company_id, period) before calling LLM
  - force=True to re-extract

Usage:
    from pipeline.extraction.metrics_extractor import extract_metrics, extract_all_parsed

    result = extract_metrics(doc_id=1, company_id="paytm", period="Q3FY25")
    print(result.metrics_stored)  # e.g. 8

    results = extract_all_parsed("paytm")
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from pydantic import ValidationError

from pipeline.database import get_chunks, get_documents, upsert_metric, update_document_status, get_metrics_dataframe
from pipeline.extraction.llm_client import LLMClient
from pipeline.schemas import FintechMetrics

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "claude")
DEFAULT_MODEL    = os.getenv("LLM_MODEL", "claude-sonnet-4-5")

# Fields with non-numeric types (str) — stored separately
_STR_FIELDS = {
    "new_order_geography",
    "new_order_category",
    "trial_readout_outcome",
    "trial_readout_indication",
    "ai_ml_investment_note",
}

# Unit mapping: field_name → (unit_str, direction_hint)
_FIELD_META: dict[str, tuple[str, str]] = {
    # Payments
    "gmv_mn_usd":                  ("USD Mn",  "up"),
    "gmv_crore":                   ("INR Cr",  "up"),
    "gmv_growth_yoy_pct":          ("%",       "up"),
    "monthly_transacting_users_mn":("Mn",      "up"),
    "mtu_growth_yoy_pct":          ("%",       "up"),
    "merchant_subscriptions_mn":   ("Mn",      "up"),
    "devices_deployed_mn":         ("Mn",      "up"),
    "net_payment_margin_mn_usd":   ("USD Mn",  "up"),
    "contribution_profit_mn_usd":  ("USD Mn",  "up"),
    "contribution_margin_pct":     ("%",       "up"),
    "ebitda_before_esop_mn_usd":   ("USD Mn",  "up"),
    "loan_distribution_value_crore":("INR Cr", "up"),
    "loan_distribution_count_mn":  ("Mn",      "up"),
    # Revenue / profitability
    "revenue_mn_usd":              ("USD Mn",  "up"),
    "revenue_crore":               ("INR Cr",  "up"),
    "revenue_growth_yoy_pct":      ("%",       "up"),
    "pat_crore":                   ("INR Cr",  "up"),
    "pat_mn_usd":                  ("USD Mn",  "up"),
    # Lending
    "aum_crore":                   ("INR Cr",  "up"),
    "loan_book_growth_qoq_pct":    ("%",       "up"),
    "loan_book_growth_yoy_pct":    ("%",       "up"),
    "gross_npa_pct":               ("%",       "down"),
    "net_npa_pct":                 ("%",       "down"),
    "credit_cost_pct_aum":         ("%",       "down"),
    "net_interest_margin_pct":     ("%",       "up"),
    "cost_of_funds_pct":           ("%",       "down"),
    # Generic
    "digital_txn_volume_mn":       ("Mn",      "up"),
    "active_users_mn":             ("Mn",      "up"),
}


# ─── Return type ──────────────────────────────────────────────────────────────

@dataclass
class ExtractionResult:
    doc_id: int
    company_id: str
    period: str
    success: bool = False
    was_cached: bool = False
    metrics_extracted: int = 0   # non-null fields in parsed response
    metrics_stored: int = 0      # rows written to DB
    validation_errors: list[str] = field(default_factory=list)
    error: Optional[str] = None
    raw_response: Optional[str] = None

    def __str__(self) -> str:
        if self.was_cached:
            return f"ExtractionResult(CACHED doc_id={self.doc_id})"
        status = "OK" if self.success else "FAIL"
        return (
            f"ExtractionResult({status} doc_id={self.doc_id} "
            f"period={self.period} metrics={self.metrics_stored})"
        )


# ─── Prompt builder ───────────────────────────────────────────────────────────

def _build_extraction_prompt(
    company_name: str,
    period: str,
    doc_type: str,
    document_text: str,
    schema: type[FintechMetrics],
) -> str:
    """Build the LLM extraction prompt."""

    # Build field list from Pydantic schema
    field_lines = []
    for name, fld in schema.model_fields.items():
        desc = fld.description or ""
        field_lines.append(f"  - {name}: {desc}")
    field_list = "\n".join(field_lines)

    # Build JSON template (all nulls)
    json_template = json.dumps(
        {name: None for name in schema.model_fields},
        indent=2
    )

    return f"""You are a financial analyst extracting structured metrics from an investor presentation.

TASK: Extract ALL financial metrics you can find in the document below.
Return ONLY a valid JSON object. No explanation, no markdown, no code block — just raw JSON.
Use null for any metric not found in the document.
All numeric values must be plain numbers (no commas, no % signs, no currency symbols).

Company: {company_name}
Period: {period}
Document type: {doc_type}

FIELDS TO EXTRACT:
{field_list}

IMPORTANT RULES:
1. Extract ONLY what is explicitly stated in the document — do not infer or estimate.
2. For percentage fields (ending in _pct), store the number only (e.g. 15.3 for 15.3%).
3. For USD fields (ending in _mn_usd), convert from USD millions to the numeric value.
4. For INR fields (ending in _crore), use INR crore values.
5. If a metric appears with YoY or QoQ growth mentioned, extract both the absolute value AND the growth rate.
6. Return EXACTLY this JSON structure (fill in values or keep null):

{json_template}

DOCUMENT:
{document_text}

Return ONLY the JSON object:"""


# ─── Core extraction ──────────────────────────────────────────────────────────

def _metrics_exist(company_id: str, period: str) -> bool:
    """Return True if any metrics are already stored for (company_id, period)."""
    df = get_metrics_dataframe(company_id)
    if df is None or df.empty:
        return False
    return period in df["period"].unique().tolist()


def _store_metrics(
    metrics: FintechMetrics,
    company_id: str,
    period: str,
    source_doc_id: int,
) -> int:
    """Iterate non-null FintechMetrics fields and write to DB. Returns count stored."""
    stored = 0
    for field_name, value in metrics.model_dump().items():
        if value is None:
            continue
        if field_name in _STR_FIELDS:
            # String metrics: store as 0 numeric + unit as the string value (best-effort)
            continue
        if not isinstance(value, (int, float)):
            continue
        unit, direction = _FIELD_META.get(field_name, ("", "neutral"))
        upsert_metric(
            company_id=company_id,
            period=period,
            metric_name=field_name,
            metric_value=float(value),
            unit=unit,
            direction=direction,
            source_doc_id=source_doc_id,
            validated=1,
        )
        stored += 1
    return stored


def extract_metrics(
    doc_id: int,
    company_id: str,
    period: str,
    company_name: str = "",
    doc_type: str = "investor_presentation",
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    force: bool = False,
) -> ExtractionResult:
    """
    Extract financial metrics from a parsed document via LLM.

    Args:
        doc_id:       Document ID in the documents table (must be parsed).
        company_id:   e.g. "paytm"
        period:       e.g. "Q3FY25"
        company_name: Display name for prompt (e.g. "Paytm")
        doc_type:     e.g. "investor_presentation"
        provider:     LLM provider: "claude" | "gemini" | "openai"
        model:        Model name.
        force:        Re-extract even if metrics already exist.

    Returns:
        ExtractionResult
    """
    result = ExtractionResult(doc_id=doc_id, company_id=company_id, period=period)

    # ── Load chunks ────────────────────────────────────────────────────────────
    chunks = get_chunks(doc_id)
    if not chunks:
        result.error = f"No chunks found for doc_id={doc_id}. Run Phase 3 first."
        logger.error(result.error)
        return result

    # ── Idempotency check ─────────────────────────────────────────────────────
    if not force:
        from pipeline.database import get_connection
        with get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM metrics WHERE company_id=? AND period=? AND source_doc_id=?",
                (company_id, period, doc_id),
            ).fetchone()[0]
        if count > 0:
            result.was_cached = True
            result.success = True
            result.metrics_stored = count
            logger.info(f"Metrics already exist for {company_id} {period} (doc_id={doc_id}): {count} rows")
            return result

    # ── Build document text ────────────────────────────────────────────────────
    document_text = "\n\n---\n\n".join(
        f"[Page {ch['page_num']+1}]\n{ch['text']}" for ch in chunks
    )
    logger.info(
        f"Extracting: {company_id} {period} (doc_id={doc_id}) "
        f"| {len(chunks)} chunks | {len(document_text)} chars | {provider}/{model}"
    )

    # ── Build prompt ──────────────────────────────────────────────────────────
    prompt = _build_extraction_prompt(
        company_name=company_name or company_id.title(),
        period=period,
        doc_type=doc_type,
        document_text=document_text,
        schema=FintechMetrics,
    )

    # ── Call LLM ──────────────────────────────────────────────────────────────
    try:
        client = LLMClient(provider=provider, model=model)
        raw = client.complete(prompt, max_tokens=2048, temperature=0.0)
        result.raw_response = raw
    except Exception as e:
        result.error = f"LLM call failed: {e}"
        logger.error(f"  LLM error for doc_id={doc_id}: {e}")
        update_document_status(doc_id, "extraction_failed")
        return result

    # ── Parse JSON ────────────────────────────────────────────────────────────
    try:
        json_data = client._extract_json(raw)
        if not json_data:
            raise ValueError("Empty JSON extracted from response")
        parsed = json.loads(json_data)
    except Exception as e:
        result.error = f"JSON parse failed: {e}"
        logger.error(f"  JSON parse error: {e}\n  Raw: {raw[:200]}")
        update_document_status(doc_id, "extraction_failed")
        return result

    # ── Validate with Pydantic ────────────────────────────────────────────────
    try:
        metrics = FintechMetrics(**parsed)
    except ValidationError as e:
        # Partial success: filter out invalid fields and retry
        logger.warning(f"  Pydantic validation errors: {e.error_count()} fields")
        result.validation_errors = [str(err) for err in e.errors()]
        clean = {k: v for k, v in parsed.items() if k in FintechMetrics.model_fields}
        try:
            metrics = FintechMetrics(**clean)
        except ValidationError as e2:
            result.error = f"Pydantic validation failed: {e2}"
            update_document_status(doc_id, "extraction_failed")
            return result

    # ── Count non-null extracted metrics ─────────────────────────────────────
    non_null = {k: v for k, v in metrics.model_dump().items() if v is not None}
    result.metrics_extracted = len(non_null)
    logger.info(f"  Extracted {len(non_null)} non-null metrics: {list(non_null.keys())}")

    # ── Store to DB ───────────────────────────────────────────────────────────
    stored = _store_metrics(metrics, company_id, period, doc_id)
    result.metrics_stored = stored
    result.success = stored > 0

    # ── Update document status ────────────────────────────────────────────────
    update_document_status(doc_id, "extracted")
    logger.info(f"  Stored {stored} metrics to DB. Status: extracted")

    return result


def extract_all_parsed(
    company_id: str,
    company_name: str = "",
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    force: bool = False,
) -> list[ExtractionResult]:
    """
    Extract metrics for all 'parsed' or 'downloaded' documents of a company.

    Args:
        company_id:   e.g. "paytm"
        company_name: Display name for the LLM prompt.
        provider:     LLM provider.
        model:        Model name.
        force:        Re-extract even if metrics already stored.

    Returns:
        List of ExtractionResult.
    """
    docs = get_documents(company_id)
    target_statuses = {"parsed", "extracted"} if force else {"parsed"}
    pending = [
        d for d in docs
        if d.get("parse_status") in target_statuses
    ]
    logger.info(
        f"extract_all_parsed: {len(pending)} documents for '{company_id}' "
        f"(force={force})"
    )
    results = []
    for doc in pending:
        result = extract_metrics(
            doc_id=doc["id"],
            company_id=company_id,
            period=doc.get("period", "unknown"),
            company_name=company_name or company_id.title(),
            doc_type=doc.get("doc_type", "investor_presentation"),
            provider=provider,
            model=model,
            force=force,
        )
        results.append(result)
    return results
