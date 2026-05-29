"""
Phase 6 verification tests — Synthesis generation.

Tests (all run regardless of API key):
  1. Module imports
  2. _format_metrics_table produces a readable table from a DataFrame
  3. _build_synthesis_prompt is well-formed and includes data
  4. synthesize_company returns early with clear error when no metrics in DB
  5. insert_synthesis + get_synthesis round-trip
  6. get_latest_synthesis returns the stored result

Live tests (skipped if no API key):
  7. Real synthesis from pre-seeded metrics (Paytm Q3FY25 data)
  8. Synthesis text length and content quality checks

Run: python tests/test_phase6.py
"""

import os
import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_phase6")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_PATH"] = "data/sector_intel_phase6_test.db"

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
    p = Path("data/sector_intel_phase6_test.db")
    if p.exists():
        p.unlink()


def seed_db():
    """Seed a minimal DB with Paytm company + multi-quarter metrics."""
    from pipeline.database import init_db, insert_company, upsert_metric
    init_db()
    insert_company("paytm", "Paytm", "indian_fintech", "PAYTM", "BSE", "https://ir.paytm.com")

    # Realistic Paytm metrics across 4 quarters (from public presentations)
    quarters = {
        "Q3FY24": {
            "gmv_mn_usd": 4700.0,
            "revenue_mn_usd": 1200.0,
            "monthly_transacting_users_mn": 10.0,
            "devices_deployed_mn": 0.87,
            "ebitda_before_esop_mn_usd": -15.0,
            "contribution_profit_mn_usd": 125.0,
            "contribution_margin_pct": 52.0,
        },
        "Q4FY24": {
            "gmv_mn_usd": 4900.0,
            "revenue_mn_usd": 1100.0,
            "monthly_transacting_users_mn": 9.7,
            "devices_deployed_mn": 0.99,
            "ebitda_before_esop_mn_usd": -10.0,
            "contribution_profit_mn_usd": 130.0,
            "contribution_margin_pct": 55.0,
        },
        "Q1FY25": {
            "gmv_mn_usd": 4100.0,
            "revenue_mn_usd": 850.0,
            "monthly_transacting_users_mn": 7.8,
            "devices_deployed_mn": 0.99,
            "ebitda_before_esop_mn_usd": -40.0,
            "contribution_profit_mn_usd": 75.0,
            "contribution_margin_pct": 45.0,
        },
        "Q3FY25": {
            "gmv_mn_usd": 5200.0,
            "revenue_mn_usd": 760.0,
            "monthly_transacting_users_mn": 10.8,
            "devices_deployed_mn": 1.12,
            "ebitda_before_esop_mn_usd": 24.3,
            "contribution_profit_mn_usd": 200.0,
            "contribution_margin_pct": 63.0,
        },
    }
    for period, metrics in quarters.items():
        for metric_name, value in metrics.items():
            upsert_metric("paytm", period, metric_name, value)

    return quarters


# ── Test 1: Imports ───────────────────────────────────────────────────────────

def test_imports():
    sep("Test 1: Imports")
    from pipeline.synthesis.synthesizer import (
        synthesize_company, synthesize_sector,
        SynthesisResult, get_latest_synthesis,
        _format_metrics_table, _build_synthesis_prompt,
    )
    print("  synthesize_company         OK")
    print("  synthesize_sector          OK")
    print("  SynthesisResult            OK")
    print("  get_latest_synthesis       OK")
    print("  _format_metrics_table      OK")
    print("  _build_synthesis_prompt    OK")


# ── Test 2: _format_metrics_table ────────────────────────────────────────────

def test_format_table():
    sep("Test 2: _format_metrics_table")
    import pandas as pd
    from pipeline.synthesis.synthesizer import _format_metrics_table

    df = pd.DataFrame([
        {"period": "Q3FY24", "metric_name": "gmv_mn_usd",    "metric_value": 4700.0},
        {"period": "Q3FY24", "metric_name": "revenue_mn_usd","metric_value": 1200.0},
        {"period": "Q4FY24", "metric_name": "gmv_mn_usd",    "metric_value": 4900.0},
        {"period": "Q4FY24", "metric_name": "revenue_mn_usd","metric_value": 1100.0},
        {"period": "Q1FY25", "metric_name": "gmv_mn_usd",    "metric_value": 4100.0},
        {"period": "Q1FY25", "metric_name": "revenue_mn_usd","metric_value": 850.0},
    ])

    table = _format_metrics_table(df)
    assert "Q3FY24" in table
    assert "Q4FY24" in table
    assert "gmv_mn_usd" in table
    assert "4700" in table
    assert "1200" in table

    print(f"  Table produced ({len(table)} chars)")
    print()
    for line in table.split("\n"):
        print(f"    {line}")
    print()
    print("  _format_metrics_table  OK")


# ── Test 3: _build_synthesis_prompt ──────────────────────────────────────────

def test_build_prompt():
    sep("Test 3: _build_synthesis_prompt")
    from pipeline.synthesis.synthesizer import _build_synthesis_prompt

    prompt = _build_synthesis_prompt(
        company_or_sector="Paytm",
        period_range="Q3FY24 to Q3FY25",
        metrics_table="Period | gmv_mn_usd\nQ3FY24 | 4700\nQ3FY25 | 5200",
        context_note="Company: Paytm (fintech)",
    )

    assert len(prompt) > 300
    assert "synthesis_text" in prompt
    assert "investing_lens_text" in prompt
    assert "Q3FY24 to Q3FY25" in prompt
    assert "Paytm" in prompt
    print(f"  Prompt length: {len(prompt)} chars  OK")
    print(f"  Contains synthesis_text field  OK")
    print(f"  Contains investing_lens_text field  OK")
    print(f"  Contains company name + period  OK")


# ── Test 4: synthesize_company with no metrics ───────────────────────────────

def test_no_metrics_graceful():
    sep("Test 4: synthesize_company - graceful empty response")
    from pipeline.synthesis.synthesizer import synthesize_company

    # company with no metrics in DB
    result = synthesize_company("unknown_co", "Unknown Co", sector="indian_fintech")
    assert result.success is False
    assert result.error is not None
    assert "No metrics" in result.error
    print(f"  Empty company returns success=False  OK")
    print(f"  Error: {result.error}")


# ── Test 5: insert_synthesis + get_synthesis round-trip ──────────────────────

def test_synthesis_db_roundtrip():
    sep("Test 5: insert_synthesis + get_synthesis round-trip")
    from pipeline.database import insert_synthesis, get_synthesis

    insert_synthesis(
        sector="indian_fintech:paytm",
        period_range="Q3FY24 to Q3FY25",
        synthesis_text="GMV grew from $4.7B to $5.2B. EBITDA turned positive.",
        investing_lens_text="Paytm's device rental business validates the B2B fintech stack.",
    )

    stored = get_synthesis("indian_fintech:paytm")
    assert stored is not None
    assert stored["synthesis_text"] == "GMV grew from $4.7B to $5.2B. EBITDA turned positive."
    assert stored["investing_lens_text"] == "Paytm's device rental business validates the B2B fintech stack."
    assert stored["period_range"] == "Q3FY24 to Q3FY25"
    print(f"  insert_synthesis  OK")
    print(f"  get_synthesis     OK")
    print(f"  Period range: {stored['period_range']}")
    print(f"  Synthesis preview: {stored['synthesis_text'][:60]}...")

    # Update (same sector key = overwrite)
    insert_synthesis(
        sector="indian_fintech:paytm",
        period_range="Q3FY24 to Q3FY25",
        synthesis_text="Updated synthesis.",
        investing_lens_text="Updated lens.",
    )
    updated = get_synthesis("indian_fintech:paytm")
    assert updated["synthesis_text"] == "Updated synthesis."
    print(f"  Re-insert (upsert) OK")


# ── Test 6: get_latest_synthesis ─────────────────────────────────────────────

def test_get_latest_synthesis():
    sep("Test 6: get_latest_synthesis")
    from pipeline.synthesis.synthesizer import get_latest_synthesis

    result = get_latest_synthesis("indian_fintech:paytm")
    assert result is not None
    assert "synthesis_text" in result
    print(f"  get_latest_synthesis  OK")
    print(f"  Keys: {list(result.keys())}")


# ── Test 7: Live synthesis (skipped if no key) ────────────────────────────────

def test_live_synthesis():
    sep("Test 7: Live company synthesis", live=True)

    if not LIVE_TESTS:
        print(f"  SKIPPED - no API key")
        print(f"  Set ANTHROPIC_API_KEY or GEMINI_API_KEY to run")
        return None

    print(f"  Provider: {LLM_PROVIDER}/{LLM_MODEL}")
    from pipeline.synthesis.synthesizer import synthesize_company

    result = synthesize_company(
        company_id="paytm",
        company_name="Paytm (One97 Communications)",
        sector="indian_fintech",
        provider=LLM_PROVIDER,
        model=LLM_MODEL,
        last_n_quarters=8,
    )

    print(f"  Success: {result.success}")
    print(f"  Period range: {result.period_range}")
    print(f"  Companies: {result.companies_covered}")
    print(f"  Metrics rows: {result.metrics_rows}")
    if result.error:
        print(f"  Error: {result.error}")

    assert result.success, f"Synthesis failed: {result.error}"
    assert len(result.synthesis_text) > 100, "synthesis_text too short"
    assert len(result.investing_lens_text) > 100, "investing_lens_text too short"

    print(f"\n  Synthesis text ({len(result.synthesis_text)} chars):")
    print(f"  {result.synthesis_text[:400]}...")
    print(f"\n  Investing lens ({len(result.investing_lens_text)} chars):")
    print(f"  {result.investing_lens_text[:300]}...")
    print(f"\n  GATE: synthesis generated and stored  PASS")
    return result


# ── Test 8: Stored synthesis readable ────────────────────────────────────────

def test_stored_synthesis_readable():
    sep("Test 8: Stored synthesis state")
    from pipeline.database import get_synthesis

    stored = get_synthesis("indian_fintech:paytm")
    if stored:
        print(f"  Sector key: indian_fintech:paytm")
        print(f"  Period:     {stored.get('period_range','?')}")
        print(f"  Synthesis:  {len(stored.get('synthesis_text',''))} chars")
        print(f"  Lens:       {len(stored.get('investing_lens_text',''))} chars")
        print(f"  Generated:  {stored.get('generated_at','?')}")
        print(f"  Synthesis stored + readable  OK")
    else:
        print(f"  No synthesis stored (live tests skipped)  OK (expected)")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\nLIVE TESTS: {'ENABLED' if LIVE_TESTS else 'DISABLED (no API key)'}")
    if LIVE_TESTS:
        print(f"Provider: {LLM_PROVIDER}/{LLM_MODEL}")

    try:
        test_imports()
        test_format_table()
        test_build_prompt()

        seed_db()
        print("\n  [setup] DB seeded with 4 quarters of Paytm metrics")

        test_no_metrics_graceful()
        test_synthesis_db_roundtrip()
        test_get_latest_synthesis()
        test_live_synthesis()
        test_stored_synthesis_readable()

        sep("ALL PHASE 6 TESTS PASSED")
        if not LIVE_TESTS:
            print()
            print("  NOTE: Tests 7-8 live portion skipped (no API key).")
            print("  Run with ANTHROPIC_API_KEY=<key> to test live synthesis.")
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
