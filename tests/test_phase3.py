"""
Phase 3 verification tests — PDF parsing and chunking.

Tests:
  1. Import check
  2. Text extraction from all 3 downloaded PDFs
  3. Chunk count, content quality, minimum thresholds
  4. DB storage (insert_chunks, get_chunks, chunks_exist)
  5. Idempotency — parsing the same PDF twice does not duplicate chunks
  6. parse_all_pending integration

Run: python tests/test_phase3.py
"""

import os
import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_phase3")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_PATH"] = "data/sector_intel_phase3_test.db"

PDF_DIR = Path("data/pdfs/paytm")


def sep(title):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print("=" * 65)


def cleanup():
    p = Path("data/sector_intel_phase3_test.db")
    if p.exists():
        p.unlink()


# ── Test 1: Imports ───────────────────────────────────────────────────────────

def test_imports():
    sep("Test 1: Imports")
    from pipeline.ingestion.pdf_parser import (
        parse_pdf, parse_all_pending, ParseResult, ParsedChunk,
        _clean_text, _split_long_text,
    )
    from pipeline.database import (
        chunks_exist, insert_chunks, get_chunks, delete_chunks_for_doc
    )
    print("  parse_pdf          OK")
    print("  parse_all_pending  OK")
    print("  ParseResult        OK")
    print("  DB chunk functions OK")


# ── Test 2: Text cleaning helpers ────────────────────────────────────────────

def test_helpers():
    sep("Test 2: Text cleaning and splitting helpers")
    from pipeline.ingestion.pdf_parser import _clean_text, _split_long_text

    # Clean text
    raw = "Hello\r\nWorld\n\n\n\nFoo   Bar\f"
    cleaned = _clean_text(raw)
    assert "\r" not in cleaned
    assert "\f" not in cleaned
    assert "   " not in cleaned
    assert cleaned.count("\n") < 5  # blank lines collapsed
    print(f"  _clean_text        OK  ({len(raw)} -> {len(cleaned)} chars)")

    # Splitting — single chunk (short text)
    short = "A" * 100
    parts = _split_long_text(short, max_chars=4000, overlap=100)
    assert len(parts) == 1
    print(f"  _split_long_text (short)  OK  -> 1 chunk")

    # Splitting — paragraph split
    long = ("First paragraph.\n\nSecond paragraph that is quite long.\n\n" * 20)
    parts = _split_long_text(long, max_chars=500, overlap=50)
    assert len(parts) > 1
    # All parts should be <= max_chars
    assert all(len(p) <= 600 for p in parts)  # a bit of tolerance for split logic
    print(f"  _split_long_text (long)   OK  -> {len(parts)} chunks")


# ── Test 3: Parse all 3 downloaded PDFs ──────────────────────────────────────

def test_parse_pdfs():
    sep("Test 3: Parse 3 downloaded Paytm PDFs")

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    assert len(pdfs) >= 3, f"Need at least 3 PDFs in {PDF_DIR}, found {len(pdfs)}"

    from pipeline.database import init_db, insert_company, insert_document, update_file_path
    from pipeline.ingestion.pdf_parser import parse_pdf, ParseResult

    init_db()
    insert_company("paytm", "Paytm", "indian_fintech", "PAYTM", "BSE", "https://ir.paytm.com")

    results = []
    for i, pdf_path in enumerate(pdfs[:3]):
        # Register document
        doc_id = insert_document(
            company_id="paytm",
            source_url=f"https://paytm.com/document/ir/test/{pdf_path.name}",
            doc_type="investor_presentation",
            period=f"Q{i+1}FY25",
            headline=f"Test doc {i+1}",
        )
        update_file_path(doc_id, str(pdf_path))

        result = parse_pdf(str(pdf_path), doc_id)
        results.append(result)

        assert isinstance(result, ParseResult)
        assert result.total_pages > 0, f"Expected >0 pages, got {result.total_pages}"
        assert result.chunks_extracted >= 3, (
            f"Expected >=3 chunks, got {result.chunks_extracted} for {pdf_path.name}"
        )
        assert result.chunks_stored > 0, "Expected chunks to be stored"
        assert not result.was_cached, "First parse should not be cached"

        print(f"\n  [{i+1}] {pdf_path.name}")
        print(f"       Pages: {result.total_pages}  |  Skipped: {result.pages_skipped}")
        print(f"       Chunks extracted: {result.chunks_extracted}")
        print(f"       Chunks stored:    {result.chunks_stored}")
        print(f"       Errors:           {len(result.errors)}")

    return results


# ── Test 4: Chunk content quality ─────────────────────────────────────────────

def test_chunk_quality():
    sep("Test 4: Chunk content quality")

    from pipeline.database import get_documents, get_chunks

    docs = get_documents("paytm")
    assert len(docs) > 0

    total_chunks = 0
    for doc in docs:
        if doc.get("parse_status") != "parsed":
            continue
        chunks = get_chunks(doc["id"])
        total_chunks += len(chunks)

        for ch in chunks:
            # Each chunk has required fields
            assert ch.get("text"), f"Empty text in chunk {ch['id']}"
            assert ch.get("char_count", 0) > 0
            assert ch.get("page_num") is not None
            assert ch.get("chunk_index") is not None

        # Sample: print first chunk of first parsed doc
        if doc["id"] == docs[0]["id"] and chunks:
            print(f"\n  First chunk preview (doc_id={doc['id']}, page={chunks[0]['page_num']}):")
            preview = chunks[0]["text"][:300].replace("\n", " ")
            print(f"    {preview!r}")
            print(f"  All {len(chunks)} chunks valid (non-empty text, valid page/index)")

    print(f"\n  Total chunks across all docs: {total_chunks}")
    assert total_chunks >= 10, f"Expected at least 10 total chunks, got {total_chunks}"
    print(f"  GATE: total_chunks >= 10  PASS")


# ── Test 5: Idempotency — parsing twice ───────────────────────────────────────

def test_idempotency():
    sep("Test 5: Idempotency (parse twice = same chunk count)")

    from pipeline.database import get_documents, get_chunks
    from pipeline.ingestion.pdf_parser import parse_pdf

    docs = [d for d in get_documents("paytm") if d.get("parse_status") == "parsed"]
    assert len(docs) > 0

    doc = docs[0]
    chunks_before = get_chunks(doc["id"])
    count_before = len(chunks_before)

    # Parse again WITHOUT force — should be cached
    result2 = parse_pdf(doc["file_path"], doc["id"], force=False)
    assert result2.was_cached is True, "Second parse without force must be cached"
    assert result2.chunks_stored == 0, "No new chunks should be stored on cached run"
    chunks_after = get_chunks(doc["id"])
    assert len(chunks_after) == count_before, (
        f"Chunk count changed after 2nd parse: {count_before} -> {len(chunks_after)}"
    )
    print(f"  Second parse (force=False): was_cached=True, chunks unchanged={count_before}  OK")

    # Parse WITH force=True — should re-parse and same count
    result3 = parse_pdf(doc["file_path"], doc["id"], force=True)
    assert result3.was_cached is False
    chunks_force = get_chunks(doc["id"])
    assert len(chunks_force) == count_before, (
        f"Force re-parse changed chunk count: {count_before} -> {len(chunks_force)}"
    )
    print(f"  Third parse (force=True):  re-parsed, chunk count={len(chunks_force)} (same)  OK")


# ── Test 6: parse_all_pending integration ─────────────────────────────────────

def test_parse_all_pending():
    sep("Test 6: parse_all_pending integration")

    from pipeline.database import get_documents, insert_document, update_file_path
    from pipeline.ingestion.pdf_parser import parse_all_pending

    pdfs = sorted(PDF_DIR.glob("*.pdf"))

    # All 3 docs are already 'parsed' — pending count should be 0
    results = parse_all_pending("paytm", force=False)
    print(f"  parse_all_pending (no force) returned {len(results)} results (expected 0 — all parsed)")
    assert len(results) == 0, f"Expected 0 pending docs, got {len(results)}"

    # force=True re-parses all docs with a file_path
    results_forced = parse_all_pending("paytm", force=True)
    print(f"  parse_all_pending (force=True) returned {len(results_forced)} results")
    assert len(results_forced) >= 3, f"Expected >= 3 results on force, got {len(results_forced)}"
    assert all(not r.was_cached for r in results_forced), "Force=True should not be cached"
    assert all(r.chunks_stored > 0 for r in results_forced), "All forced results should store chunks"
    total_errors = sum(len(r.errors) for r in results_forced)
    print(f"  Force re-parsed: {len(results_forced)} docs, errors={total_errors}")
    print(f"  parse_all_pending  OK")


# ── Test 7: DB state ──────────────────────────────────────────────────────────

def test_db_state():
    sep("Test 7: Final Database State")

    from pipeline.database import get_documents, get_chunks

    docs = get_documents("paytm")
    print(f"\n  {'ID':>4}  {'Period':<10}  {'Status':<10}  {'Chunks':>6}  {'File'}")
    print(f"  {'-'*4}  {'-'*10}  {'-'*10}  {'-'*6}  {'-'*40}")
    for doc in sorted(docs, key=lambda d: d.get("period", "")):
        chunks = get_chunks(doc["id"])
        fp = doc.get("file_path") or "(none)"
        fp_short = Path(fp).name if fp != "(none)" else "(none)"
        print(f"  {doc['id']:>4}  {doc.get('period','?'):<10}  "
              f"{doc.get('parse_status','?'):<10}  {len(chunks):>6}  {fp_short}")

    parsed = [d for d in docs if d.get("parse_status") == "parsed"]
    assert len(parsed) >= 3, f"Need at least 3 parsed docs, got {len(parsed)}"
    print(f"\n  Parsed documents: {len(parsed)} >= 3  PASS")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        test_imports()
        test_helpers()
        test_parse_pdfs()
        test_chunk_quality()
        test_idempotency()
        test_parse_all_pending()
        test_db_state()

        sep("ALL PHASE 3 TESTS PASSED")
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
