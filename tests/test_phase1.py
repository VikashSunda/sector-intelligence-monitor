"""Phase 1 gate tests — run with: python tests/test_phase1.py"""

import sys
import os
import json
import re

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use a test DB so we don't pollute the real one
os.environ["DATABASE_PATH"] = "data/sector_intel_test.db"


def test_database():
    print("=== Gate 1: Database init ===")
    from pipeline.database import init_db, get_connection
    init_db()

    conn = get_connection()
    tables = sorted(
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        if r[0] != "sqlite_sequence"   # SQLite internal table for AUTOINCREMENT
    )
    conn.close()

    expected = ["chunks", "companies", "documents", "metrics", "refresh_log", "synthesis"]
    assert tables == expected, f"Expected {expected}, got {tables}"
    print(f"  Tables: {tables}  OK")


def test_crud():
    print("\n=== Gate 2: CRUD round-trip ===")
    from pipeline.database import (
        insert_company, document_exists, insert_document,
        update_document_status, upsert_metric, get_metrics_dataframe,
        insert_synthesis, get_synthesis, log_refresh, get_refresh_log,
        get_latest_metrics,
    )

    insert_company("test_co", "Test Company", "indian_fintech", "TEST", "BSE", "https://test.com")
    print("  insert_company   OK")

    assert not document_exists("test_co", "https://example.com/doc1.pdf")
    doc_id = insert_document("test_co", "https://example.com/doc1.pdf", "concall_transcript", "Q3FY24")
    assert document_exists("test_co", "https://example.com/doc1.pdf")
    # Second call must return existing id without error
    doc_id2 = insert_document("test_co", "https://example.com/doc1.pdf", "concall_transcript", "Q3FY24")
    assert doc_id == doc_id2
    print("  document_exists  OK  (dedup works)")

    update_document_status(doc_id, "success", chunk_count=12)
    print("  update_status    OK")

    upsert_metric("test_co", "Q3FY24", "aum_crore", 50000.0, unit="crore", direction="up", source_doc_id=doc_id)
    upsert_metric("test_co", "Q3FY24", "gross_npa_pct", 1.2, unit="%", direction="down", source_doc_id=doc_id)
    upsert_metric("test_co", "Q2FY24", "aum_crore", 45000.0, unit="crore", source_doc_id=doc_id)
    print("  upsert_metric    OK")

    df = get_metrics_dataframe("test_co")
    assert len(df) == 3, f"Expected 3 rows, got {len(df)}"
    print(f"  get_metrics_df   OK  ({len(df)} rows)")

    # Upsert idempotency
    upsert_metric("test_co", "Q3FY24", "aum_crore", 51000.0, unit="crore", direction="up")
    df2 = get_metrics_dataframe("test_co")
    val = df2[(df2["period"] == "Q3FY24") & (df2["metric_name"] == "aum_crore")]["metric_value"].iloc[0]
    assert val == 51000.0, f"UPSERT failed: got {val}"
    print("  upsert idempotency OK")

    latest = get_latest_metrics("test_co")
    assert "aum_crore" in latest
    print("  get_latest_metrics OK")

    insert_synthesis("indian_fintech", "Q1FY22-Q3FY24", "Sector is growing.", "Look at digital lending.")
    syn = get_synthesis("indian_fintech")
    assert syn is not None
    assert syn["synthesis_text"] == "Sector is growing."
    print("  synthesis        OK")

    log_refresh("indian_fintech", docs_checked=5, new_docs_found=2, errors=[], duration_seconds=3.14)
    rlog = get_refresh_log(limit=1)
    assert rlog[0]["new_docs_found"] == 2
    assert isinstance(rlog[0]["errors"], list)
    print("  refresh_log      OK")


def test_schemas():
    print("\n=== Gate 3: Pydantic schemas ===")
    from pipeline.schemas import (
        FintechMetrics, DefenceMetrics, BiotechMetrics, SynthesisOutput,
        CompanyResponse, RefreshResult,
    )

    m = FintechMetrics(aum_crore=50000.0, gross_npa_pct=1.2, net_interest_margin_pct=None)
    assert m.aum_crore == 50000.0
    assert m.net_interest_margin_pct is None
    j = json.loads(m.model_dump_json())
    assert j["aum_crore"] == 50000.0
    print("  FintechMetrics   OK")

    # All fields None — valid empty extraction
    empty = FintechMetrics()
    assert all(v is None for v in empty.model_dump().values())
    print("  FintechMetrics (empty) OK")

    s = SynthesisOutput(synthesis_text="test synthesis", investing_lens_text="test lens")
    assert s.synthesis_text == "test synthesis"
    print("  SynthesisOutput  OK")

    # Defence and Biotech schemas load (future use)
    DefenceMetrics()
    BiotechMetrics()
    print("  DefenceMetrics, BiotechMetrics  OK")


def test_llm_client():
    print("\n=== Gate 4: LLM client (no API key required) ===")
    from pipeline.extraction.llm_client import LLMClient

    c = LLMClient(provider="claude")
    assert c.provider == "claude"
    assert c.model == "claude-sonnet-4-5"
    print(f"  Claude default model: {c.model}  OK")

    c2 = LLMClient(provider="gemini")
    assert c2.model == "gemini-1.5-flash"
    print(f"  Gemini default model: {c2.model}  OK")

    c3 = LLMClient(provider="openai")
    assert c3.model == "gpt-4o-mini"
    print(f"  OpenAI default model: {c3.model}  OK")

    # JSON extraction — raw JSON
    raw = '{"aum_crore": 50000.0, "gross_npa_pct": null}'
    result = LLMClient._extract_json(raw)
    assert result == raw
    print("  _extract_json (raw) OK")

    # JSON extraction — markdown fenced
    fenced = "```json\n" + '{"aum_crore": 123}' + "\n```"
    result2 = LLMClient._extract_json(fenced)
    parsed = json.loads(result2)
    assert parsed["aum_crore"] == 123
    print("  _extract_json (fenced) OK")

    # JSON extraction — text with preamble
    preamble = 'Here is the JSON:\n{"gross_npa_pct": 1.5, "aum_crore": null}\nEnd.'
    result3 = LLMClient._extract_json(preamble)
    parsed3 = json.loads(result3)
    assert parsed3["gross_npa_pct"] == 1.5
    print("  _extract_json (preamble) OK")

    # Bad provider
    try:
        LLMClient(provider="unknown_provider")
        assert False, "Should have raised ValueError"
    except ValueError:
        print("  Bad provider raises ValueError  OK")


def test_config():
    print("\n=== Gate 5: Config helpers ===")
    from pipeline.config import (
        date_to_quarter, get_companies_for_sector, get_quarter_range, COMPANIES
    )

    cases = [
        ("2023-11-15", "Q3FY24"),
        ("2024-04-01", "Q1FY25"),
        ("2024-01-15", "Q4FY24"),
        ("2022-07-01", "Q2FY23"),
        ("2022-04-01", "Q1FY23"),
        ("2023-01-31", "Q4FY23"),
    ]
    for date_str, expected in cases:
        result = date_to_quarter(date_str)
        assert result == expected, f"date_to_quarter({date_str!r}) = {result!r}, expected {expected!r}"
    print(f"  date_to_quarter  OK  ({len(cases)} cases)")

    fintech = get_companies_for_sector("indian_fintech")
    assert "paytm" in fintech
    assert "bajaj_finance" in fintech
    assert "sbi_cards" in fintech
    assert len(fintech) == 9
    print(f"  Indian Fintech   OK  ({len(fintech)} companies)")

    defence = get_companies_for_sector("indian_defence")
    assert len(defence) == 8
    print(f"  Indian Defence   OK  ({len(defence)} companies)")

    biotech = get_companies_for_sector("us_biotech")
    assert len(biotech) == 8
    print(f"  US Biotech       OK  ({len(biotech)} companies)")

    quarters = get_quarter_range(2022)
    assert "Q1FY22" in quarters
    assert len(quarters) >= 13   # FY22 to present
    print(f"  get_quarter_range OK  ({len(quarters)} quarters since FY22)")


def cleanup():
    import pathlib
    test_db = pathlib.Path("data/sector_intel_test.db")
    if test_db.exists():
        test_db.unlink()


if __name__ == "__main__":
    try:
        test_database()
        test_crud()
        test_schemas()
        test_llm_client()
        test_config()
        cleanup()
        print("\n" + "=" * 50)
        print("  ALL PHASE 1 GATES PASSED [OK]")
        print("=" * 50)
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
