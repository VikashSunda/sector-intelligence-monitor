"""
Phase 4 verification tests — LLM metrics extraction.

Tests (all run regardless of API key availability):
  1. Module imports
  2. Prompt builder produces valid, non-empty prompt
  3. _store_metrics correctly maps FintechMetrics fields → DB rows
  4. Idempotency: second extract call for same doc returns was_cached=True

Live LLM tests (skipped if no API key is set):
  5. Real extraction from Q3FY25 Paytm presentation
  6. extract_all_parsed batch run
  7. Metrics stored in DB readable via get_metrics_df

Run: python tests/test_phase4.py
Set ANTHROPIC_API_KEY or GEMINI_API_KEY to enable live tests.
"""

import os
import sys
import json
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_phase4")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_PATH"] = "data/sector_intel_phase4_test.db"

PDF_DIR = Path("data/pdfs/paytm")

# ── Detect available API keys ─────────────────────────────────────────────────
_ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_GEMINI_KEY    = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")

if _ANTHROPIC_KEY:
    LLM_PROVIDER = "claude"
    LLM_MODEL    = "claude-sonnet-4-5"
    LIVE_TESTS   = True
elif _GEMINI_KEY:
    LLM_PROVIDER = "gemini"
    LLM_MODEL    = "gemini-1.5-flash"
    LIVE_TESTS   = True
else:
    LLM_PROVIDER = "claude"
    LLM_MODEL    = "claude-sonnet-4-5"
    LIVE_TESTS   = False


def sep(title, live=False):
    tag = " [LIVE]" if live else ""
    print(f"\n{'='*65}")
    print(f"  {title}{tag}")
    print("=" * 65)


def cleanup():
    p = Path("data/sector_intel_phase4_test.db")
    if p.exists():
        p.unlink()


# ── DB setup: parse all 3 PDFs into test DB ───────────────────────────────────

def setup_parsed_db():
    """Re-use Phase 3 parsing to populate the test DB with 3 parsed docs."""
    from pipeline.database import init_db, insert_company, insert_document, update_file_path
    from pipeline.ingestion.pdf_parser import parse_pdf

    init_db()
    insert_company("paytm", "Paytm", "indian_fintech", "PAYTM", "BSE", "https://ir.paytm.com")

    pdfs = sorted(PDF_DIR.glob("*.pdf"))[:3]
    periods = ["Q3FY25", "Q4FY25", "Q1FY25"]
    doc_ids = []
    for pdf_path, period in zip(pdfs, periods):
        doc_id = insert_document(
            company_id="paytm",
            source_url=f"https://paytm.com/document/ir/test/{pdf_path.name}",
            doc_type="investor_presentation",
            period=period,
            headline=f"Paytm {period} Earnings",
        )
        update_file_path(doc_id, str(pdf_path))
        parse_pdf(str(pdf_path), doc_id)
        doc_ids.append(doc_id)
    return doc_ids


# ── Test 1: Imports ───────────────────────────────────────────────────────────

def test_imports():
    sep("Test 1: Imports")
    from pipeline.extraction.metrics_extractor import (
        extract_metrics, extract_all_parsed, ExtractionResult,
        _build_extraction_prompt, _store_metrics, _FIELD_META,
    )
    from pipeline.schemas import FintechMetrics
    print("  extract_metrics       OK")
    print("  extract_all_parsed    OK")
    print("  ExtractionResult      OK")
    print("  _build_extraction_prompt OK")
    print("  _store_metrics        OK")
    print(f"  _FIELD_META entries:  {len(_FIELD_META)}")
    print(f"  FintechMetrics fields:{len(FintechMetrics.model_fields)}")


# ── Test 2: Prompt builder ─────────────────────────────────────────────────────

def test_prompt_builder():
    sep("Test 2: Prompt builder")
    from pipeline.extraction.metrics_extractor import _build_extraction_prompt
    from pipeline.schemas import FintechMetrics

    sample_text = "GMV: USD 5,200 million\nRevenue: USD 187 million\nMTU: 10.8 million"
    prompt = _build_extraction_prompt(
        company_name="Paytm",
        period="Q3FY25",
        doc_type="investor_presentation",
        document_text=sample_text,
        schema=FintechMetrics,
    )

    assert len(prompt) > 500, "Prompt too short"
    assert "gmv_mn_usd" in prompt
    assert "monthly_transacting_users_mn" in prompt
    assert "Q3FY25" in prompt
    assert sample_text in prompt
    # JSON template present
    assert '"gmv_mn_usd": null' in prompt

    print(f"  Prompt length: {len(prompt)} chars  OK")
    print(f"  Contains gmv_mn_usd field  OK")
    print(f"  Contains Q3FY25 period     OK")
    print(f"  JSON template embedded     OK")
    print(f"  Sample prompt (first 200 chars):")
    print(f"    {prompt[:200].replace(chr(10),' ')!r}")


# ── Test 3: _store_metrics DB write ───────────────────────────────────────────

def test_store_metrics(doc_ids):
    sep("Test 3: _store_metrics -> DB write")
    from pipeline.extraction.metrics_extractor import _store_metrics
    from pipeline.schemas import FintechMetrics
    from pipeline.database import get_metrics_dataframe

    # Create a synthetic FintechMetrics with known values
    metrics = FintechMetrics(
        gmv_mn_usd=5200.0,
        revenue_mn_usd=187.5,
        monthly_transacting_users_mn=10.8,
        devices_deployed_mn=1.12,
        ebitda_before_esop_mn_usd=24.3,
        contribution_profit_mn_usd=75.0,
        contribution_margin_pct=40.0,
    )

    stored = _store_metrics(metrics, "paytm", "Q3FY25_test", source_doc_id=doc_ids[0])
    assert stored == 7, f"Expected 7 stored, got {stored}"
    print(f"  _store_metrics wrote {stored} rows  OK")

    # Verify they're in the DB
    df = get_metrics_dataframe("paytm")
    assert df is not None and not df.empty
    print(f"  get_metrics_df returned {len(df)} rows  OK")

    # Check specific metric value
    gmv_rows = df[df["metric_name"] == "gmv_mn_usd"]
    assert len(gmv_rows) >= 1
    assert gmv_rows.iloc[0]["metric_value"] == 5200.0
    print(f"  gmv_mn_usd = {gmv_rows.iloc[0]['metric_value']}  OK")

    return stored


# ── Test 4: Idempotency check (no API call) ───────────────────────────────────

def test_idempotency(doc_ids):
    sep("Test 4: Idempotency (cached result on second call)")
    from pipeline.extraction.metrics_extractor import extract_metrics, _store_metrics
    from pipeline.schemas import FintechMetrics

    # Pre-seed a metric for doc_ids[1] period Q4FY25
    metrics = FintechMetrics(gmv_mn_usd=4800.0, revenue_mn_usd=165.0)
    _store_metrics(metrics, "paytm", "Q4FY25", source_doc_id=doc_ids[1])

    # Now call extract_metrics — should detect existing metrics and return cached
    result = extract_metrics(
        doc_id=doc_ids[1],
        company_id="paytm",
        period="Q4FY25",
        force=False,
    )
    assert result.was_cached is True, f"Expected cached=True, got {result.was_cached}"
    assert result.success is True
    print(f"  Second call returned was_cached=True  OK")
    print(f"  metrics_stored={result.metrics_stored}  OK")


# ── Test 5: Live LLM extraction (skipped if no key) ──────────────────────────

def test_live_extraction(doc_ids):
    sep("Test 5: Live LLM extraction", live=True)

    if not LIVE_TESTS:
        print(f"  SKIPPED — no API key found")
        print(f"  Set ANTHROPIC_API_KEY or GEMINI_API_KEY to run live tests")
        print(f"  Provider that would be used: {LLM_PROVIDER}/{LLM_MODEL}")
        return None

    print(f"  Using provider: {LLM_PROVIDER}/{LLM_MODEL}")

    from pipeline.extraction.metrics_extractor import extract_metrics

    # Use Q3FY25 doc (doc_ids[0]) — already parsed
    result = extract_metrics(
        doc_id=doc_ids[0],
        company_id="paytm",
        period="Q3FY25",
        company_name="Paytm (One97 Communications)",
        doc_type="investor_presentation",
        provider=LLM_PROVIDER,
        model=LLM_MODEL,
        force=True,
    )

    print(f"  Success:           {result.success}")
    print(f"  Metrics extracted: {result.metrics_extracted}")
    print(f"  Metrics stored:    {result.metrics_stored}")
    print(f"  Validation errors: {len(result.validation_errors)}")

    if result.error:
        print(f"  Error: {result.error}")

    if result.raw_response:
        preview = result.raw_response[:300].replace('\n', ' ')
        print(f"  LLM response preview: {preview!r}")

    assert result.success, f"Extraction failed: {result.error}"
    assert result.metrics_stored >= 3, f"Expected >=3 metrics stored, got {result.metrics_stored}"
    print(f"\n  GATE: metrics_stored >= 3  PASS ({result.metrics_stored})")

    return result


# ── Test 6: extract_all_parsed (live or skipped) ──────────────────────────────

def test_extract_all_parsed(doc_ids):
    sep("Test 6: extract_all_parsed batch run", live=True)

    if not LIVE_TESTS:
        print(f"  SKIPPED — no API key found")
        return

    from pipeline.extraction.metrics_extractor import extract_all_parsed
    from pipeline.database import get_documents

    # Mark doc_ids[2] (Q1FY25) as 'parsed' — doc_ids[0] (Q3FY25) now 'extracted'
    results = extract_all_parsed(
        company_id="paytm",
        company_name="Paytm (One97 Communications)",
        provider=LLM_PROVIDER,
        model=LLM_MODEL,
        force=False,
    )

    print(f"  extract_all_parsed returned {len(results)} results")
    for r in results:
        print(f"  {r}")

    successful = [r for r in results if r.success and not r.was_cached]
    print(f"  Newly extracted: {len(successful)}")
    total_metrics = sum(r.metrics_stored for r in results)
    print(f"  Total metrics stored this run: {total_metrics}")


# ── Test 7: DB metrics state ──────────────────────────────────────────────────

def test_db_metrics_state():
    sep("Test 7: Final DB metrics state")

    from pipeline.database import get_metrics_dataframe, get_documents
    df = get_metrics_dataframe("paytm")
    docs = get_documents("paytm")

    if df is None or df.empty:
        print("  No metrics in DB (expected if live tests skipped)")
        print("  DB state: OK (metrics table exists, just empty)")
        return

    print(f"  Total metric rows:  {len(df)}")
    print(f"  Unique metrics:     {df['metric_name'].nunique()}")
    print(f"  Periods with data:  {sorted(df['period'].unique())}")
    print()
    print(f"  {'Period':<10}  {'Metric':<35}  {'Value':>12}  {'Unit'}")
    print(f"  {'-'*10}  {'-'*35}  {'-'*12}  {'-'*10}")
    for _, row in df.sort_values(["period","metric_name"]).iterrows():
        if row.get("metric_name", "").endswith("_test"):
            continue
        print(f"  {row.get('period','?'):<10}  {row.get('metric_name','?'):<35}  "
              f"{row.get('metric_value',0):>12.2f}  {row.get('unit','')}")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\nLIVE TESTS: {'ENABLED' if LIVE_TESTS else 'DISABLED (no API key)'}")
    if LIVE_TESTS:
        print(f"Provider: {LLM_PROVIDER}/{LLM_MODEL}")
    else:
        print("To enable: set ANTHROPIC_API_KEY or GEMINI_API_KEY environment variable")

    try:
        test_imports()
        test_prompt_builder()
        doc_ids = setup_parsed_db()
        print(f"\n  [setup] Parsed {len(doc_ids)} docs into test DB")
        test_store_metrics(doc_ids)
        test_idempotency(doc_ids)
        test_live_extraction(doc_ids)
        test_extract_all_parsed(doc_ids)
        test_db_metrics_state()

        sep("ALL PHASE 4 TESTS PASSED")
        if not LIVE_TESTS:
            print()
            print("  NOTE: Tests 5-6 were skipped (no API key).")
            print("  Run with ANTHROPIC_API_KEY=<key> to enable live extraction.")
        print()
        cleanup()
        sys.exit(0)

    except AssertionError as e:
        print(f"\nFAILED: {e}")
        cleanup()
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\nERROR: {e}")
        traceback.print_exc()
        cleanup()
        sys.exit(1)
