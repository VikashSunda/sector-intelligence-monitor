"""
Phase 2 verification tests — Paytm ingestion.

Tests:
  1. Import check (no crashes)
  2. DocumentTracker unit tests (register, dedup, update_file_path, mark_failed)
  3. PaytmFetcher live run (BSE API or fallback)
  4. Duplicate prevention (second run adds 0 new rows)
  5. DB state inspection (show all inserted rows)

Run: python tests/test_phase2.py
"""

import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_phase2")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use isolated test DB
os.environ["DATABASE_PATH"] = "data/sector_intel_phase2_test.db"


def cleanup():
    import pathlib
    for f in ["data/sector_intel_phase2_test.db"]:
        p = pathlib.Path(f)
        if p.exists():
            p.unlink()


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print("="*60)


# ─── Test 1: Import check ─────────────────────────────────────────────────────

def test_imports():
    separator("Test 1: Import Check")

    from pipeline.ingestion.document_tracker import DocumentRecord, DocumentTracker
    from pipeline.ingestion.paytm_fetcher import PaytmFetcher, FetchResult, fetch_paytm_documents, FALLBACK_DOCUMENTS

    assert DocumentRecord is not None
    assert DocumentTracker is not None
    assert PaytmFetcher is not None
    assert len(FALLBACK_DOCUMENTS) > 0, "Fallback document list must not be empty"

    print(f"  DocumentRecord     OK")
    print(f"  DocumentTracker    OK")
    print(f"  PaytmFetcher       OK")
    print(f"  FALLBACK_DOCUMENTS OK  ({len(FALLBACK_DOCUMENTS)} entries)")


# ─── Test 2: DocumentTracker unit tests ───────────────────────────────────────

def test_document_tracker():
    separator("Test 2: DocumentTracker Unit Tests")

    from pipeline.database import init_db, insert_company
    from pipeline.ingestion.document_tracker import DocumentTracker, DocumentRecord

    init_db()
    insert_company("paytm", "Paytm", "indian_fintech", "PAYTM", "BSE", "https://investor.paytm.com")

    tracker = DocumentTracker("paytm")

    # 2a. is_new on unseen URL
    test_url = "https://bseindia.com/test/doc_tracker_test.pdf"
    assert tracker.is_new(test_url), "URL should be new"
    print("  is_new() on unseen URL     OK")

    # 2b. register() inserts and returns DocumentRecord
    record = tracker.register(test_url, "concall_transcript", "Q3FY25", "Test headline Q3FY25")
    assert isinstance(record, DocumentRecord)
    assert record.is_new is True
    assert record.doc_id is not None
    assert record.company_id == "paytm"
    assert record.period == "Q3FY25"
    print(f"  register() first call      OK  (doc_id={record.doc_id})")

    # 2c. register() same URL → is_new=False (deduplication)
    record2 = tracker.register(test_url, "concall_transcript", "Q3FY25", "Test headline Q3FY25")
    assert record2.is_new is False
    assert record2.doc_id == record.doc_id, "Doc ID must match existing row"
    print(f"  register() duplicate       OK  (is_new=False, same doc_id={record2.doc_id})")

    # 2d. is_new now returns False
    assert not tracker.is_new(test_url), "URL should no longer be new"
    print("  is_new() after register    OK  (returns False)")

    # 2e. update_file_path
    tracker.update_file_path(record.doc_id, "/fake/path/doc.pdf")
    from pipeline.database import get_documents
    rows = get_documents("paytm")
    updated = next((r for r in rows if r["id"] == record.doc_id), None)
    assert updated is not None
    assert updated["file_path"] == "/fake/path/doc.pdf"
    assert updated["parse_status"] == "downloaded"
    print("  update_file_path()         OK  (file_path + status stored)")

    # 2f. mark_failed
    failed_url = "https://bseindia.com/test/failed_doc.pdf"
    failed_record = tracker.register(failed_url, "concall_transcript", "Q2FY25", "Fail test")
    tracker.mark_failed(failed_record.doc_id, "404 Not Found")
    rows2 = get_documents("paytm")
    failed_row = next((r for r in rows2 if r["id"] == failed_record.doc_id), None)
    assert failed_row["parse_status"] == "failed"
    print("  mark_failed()              OK  (parse_status=failed)")

    # 2g. get_all_documents
    all_docs = tracker.get_all_documents()
    assert len(all_docs) >= 2
    assert all(isinstance(d, DocumentRecord) for d in all_docs)
    print(f"  get_all_documents()        OK  ({len(all_docs)} records)")


# ─── Test 3: Live BSE fetch (or fallback) ─────────────────────────────────────

def test_live_fetch():
    separator("Test 3: Live Fetch (BSE API or Fallback)")

    from pipeline.ingestion.paytm_fetcher import fetch_paytm_documents, FetchResult

    print("  Running fetch_paytm_documents(download_pdfs=False)...")
    result = fetch_paytm_documents(from_date="2023-04-01", download_pdfs=False)

    assert isinstance(result, FetchResult)

    print(f"\n  Result summary:")
    print(f"    BSE API success:     {result.bse_api_success}")
    print(f"    Documents discovered:{result.discovered}")
    print(f"    New (inserted):      {result.new_documents}")
    print(f"    Duplicates skipped:  {result.skipped_duplicates}")
    print(f"    Downloads:           {result.downloaded}")
    print(f"    Errors:              {len(result.errors)}")

    assert result.discovered > 0, (
        "Must discover at least 1 document. "
        "BSE API may be down but fallback list should always provide results."
    )
    assert result.new_documents > 0, "First run must insert at least 1 new document"

    print(f"\n  Discovered URLs ({result.discovered}):")
    for rec in result.records[:10]:  # Show first 10
        status = "NEW" if rec.is_new else "DUP"
        print(f"    [{status}] [{rec.period}] {rec.doc_type}")
        print(f"          {rec.source_url}")

    if len(result.records) > 10:
        print(f"    ... and {len(result.records) - 10} more")

    print(f"\n  GATE: discovered >= 1   {'PASS' if result.discovered >= 1 else 'FAIL'}")
    print(f"  GATE: new_documents >= 1 {'PASS' if result.new_documents >= 1 else 'FAIL'}")


# ─── Test 4: Duplicate prevention ─────────────────────────────────────────────

def test_duplicate_prevention():
    separator("Test 4: Duplicate Prevention (second run)")

    from pipeline.ingestion.paytm_fetcher import fetch_paytm_documents
    from pipeline.database import get_documents

    rows_before = get_documents("paytm")
    count_before = len(rows_before)
    print(f"  Documents in DB before second run: {count_before}")

    print("  Running fetch_paytm_documents() a SECOND time...")
    result2 = fetch_paytm_documents(from_date="2023-04-01", download_pdfs=False)

    rows_after = get_documents("paytm")
    count_after = len(rows_after)
    print(f"  Documents in DB after second run:  {count_after}")

    assert result2.new_documents == 0, (
        f"Second run must insert 0 new documents. Got {result2.new_documents}"
    )
    assert count_after == count_before, (
        f"Row count must not change. Before={count_before}, After={count_after}"
    )
    print(f"  New documents on 2nd run: {result2.new_documents}  (expected 0)")
    print(f"  DB row count unchanged:   {count_before} == {count_after}  PASS")
    print(f"  Duplicates skipped:       {result2.skipped_duplicates}")
    print("  GATE: duplicate prevention  PASS")


# ─── Test 5: DB state inspection ──────────────────────────────────────────────

def test_db_state():
    separator("Test 5: Database State Inspection")

    from pipeline.database import get_documents, get_connection

    rows = get_documents("paytm")
    print(f"  Total documents in DB: {len(rows)}")
    print()
    print(f"  {'ID':>4}  {'Period':<10}  {'Type':<25}  {'Status':<12}  {'file_path'}")
    print(f"  {'-'*4}  {'-'*10}  {'-'*25}  {'-'*12}  {'-'*30}")

    for row in sorted(rows, key=lambda r: (r.get("period") or "", r.get("id", 0))):
        doc_id = row.get("id", "?")
        period = row.get("period", "?")
        doc_type = (row.get("doc_type") or "unknown")[:25]
        status = (row.get("parse_status") or "?")[:12]
        fp = row.get("file_path") or "(not downloaded)"
        if fp != "(not downloaded)":
            fp = fp[-35:] if len(fp) > 35 else fp  # Truncate long paths
        print(f"  {doc_id:>4}  {period:<10}  {doc_type:<25}  {status:<12}  {fp}")

    # Verify each row has required fields
    for row in rows:
        assert row.get("company_id") == "paytm"
        assert row.get("source_url"), "source_url must not be empty"
        assert row.get("doc_type"),   "doc_type must not be empty"
        assert row.get("period"),     "period must not be empty"

    print(f"\n  All rows have required fields (company_id, source_url, doc_type, period)  PASS")


# ─── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        test_imports()
        test_document_tracker()
        test_live_fetch()
        test_duplicate_prevention()
        test_db_state()

        print()
        separator("ALL PHASE 2 TESTS PASSED")
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
