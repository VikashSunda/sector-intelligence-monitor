"""
PDF text extraction and chunking — Phase 3.

Uses PyMuPDF (fitz) to extract text page-by-page from downloaded PDFs.

Chunking strategy:
  - Primary unit: one chunk per PDF page (ideal for investor presentation slides)
  - If a page exceeds MAX_CHUNK_CHARS (4000): split into sub-chunks at sentence/paragraph boundaries
  - Skip pages with fewer than MIN_CHUNK_CHARS (50): blank slides or image-only pages
  - Each chunk stored in the `chunks` table (doc_id, chunk_index, page_num, text)

After parsing:
  - documents.parse_status  → 'parsed'
  - documents.chunk_count   → number of chunks stored

Idempotency:
  - If chunks already exist for a doc_id, parsing is skipped by default
  - Pass force=True to re-parse and replace existing chunks

Usage:
    from pipeline.ingestion.pdf_parser import parse_pdf, parse_all_pending

    result = parse_pdf(file_path="data/pdfs/paytm/doc.pdf", doc_id=5)
    print(result.chunks_stored)   # e.g. 16
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from pipeline.database import (
    chunks_exist,
    delete_chunks_for_doc,
    get_documents,
    insert_chunks,
    update_document_status,
)

logger = logging.getLogger(__name__)

# ─── Chunking parameters ─────────────────────────────────────────────────────

MAX_CHUNK_CHARS = 4000   # Max characters per chunk before splitting
MIN_CHUNK_CHARS = 50     # Skip pages shorter than this (blank / image-only)
OVERLAP_CHARS   = 100    # Character overlap between sub-chunks (for context continuity)


# ─── Return types ─────────────────────────────────────────────────────────────

@dataclass
class ParsedChunk:
    """A single text chunk extracted from a PDF."""
    doc_id: int
    chunk_index: int
    page_num: int       # 0-indexed PDF page number
    text: str
    char_count: int


@dataclass
class ParseResult:
    """Summary of a parse_pdf() call."""
    doc_id: int
    file_path: str
    total_pages: int = 0
    pages_skipped: int = 0     # blank / image-only
    chunks_extracted: int = 0  # from text extraction
    chunks_stored: int = 0     # actually written to DB (0 if already cached)
    was_cached: bool = False   # True if chunks already existed and force=False
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        if self.was_cached:
            return f"ParseResult(CACHED doc_id={self.doc_id}, chunks={self.chunks_extracted})"
        return (
            f"ParseResult(doc_id={self.doc_id}, "
            f"pages={self.total_pages}, "
            f"skipped={self.pages_skipped}, "
            f"chunks={self.chunks_stored}, "
            f"errors={len(self.errors)})"
        )


# ─── Text cleaning ────────────────────────────────────────────────────────────

def _clean_text(raw: str) -> str:
    """
    Clean raw PyMuPDF text:
    - Collapse runs of whitespace / blank lines
    - Remove form-feed characters
    - Normalise Unicode dashes and quotes
    """
    text = raw.replace("\f", "\n")                  # form-feed → newline
    text = re.sub(r"\r\n|\r", "\n", text)           # CRLF → LF
    text = re.sub(r"\n{3,}", "\n\n", text)          # squeeze blank lines
    text = re.sub(r" {2,}", " ", text)              # squeeze spaces
    text = text.strip()
    return text


# ─── Splitting ────────────────────────────────────────────────────────────────

def _split_long_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """
    Split text that exceeds max_chars into overlapping sub-chunks.
    Splits preferentially at paragraph boundaries (\n\n), then sentence ends.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + max_chars

        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # Try to split at paragraph boundary
        split_at = text.rfind("\n\n", start, end)
        if split_at == -1 or split_at <= start:
            # Try sentence end (. ! ?)
            for sentinel in (". ", "! ", "? ", ".\n"):
                pos = text.rfind(sentinel, start, end)
                if pos > start:
                    split_at = pos + len(sentinel)
                    break
        if split_at <= start:
            # Hard split
            split_at = end

        chunks.append(text[start:split_at].strip())
        start = max(start + 1, split_at - overlap)

    return [c for c in chunks if c]


# ─── Core extraction ──────────────────────────────────────────────────────────

def _extract_chunks_from_pdf(
    file_path: str,
    doc_id: int,
) -> tuple[list[dict], int, int, list[str]]:
    """
    Open PDF with fitz, extract text page by page, apply chunking.

    Returns:
        (chunks: list[dict], total_pages, pages_skipped, errors)
    """
    chunks: list[dict] = []
    errors: list[str] = []
    total_pages = 0
    pages_skipped = 0
    chunk_index = 0

    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)

        for page_num in range(total_pages):
            try:
                page = doc[page_num]
                raw_text = page.get_text("text")
                text = _clean_text(raw_text)

                if len(text) < MIN_CHUNK_CHARS:
                    pages_skipped += 1
                    logger.debug(f"  Page {page_num}: skipped (only {len(text)} chars)")
                    continue

                # Split if over limit
                sub_texts = _split_long_text(text, MAX_CHUNK_CHARS, OVERLAP_CHARS)

                for sub in sub_texts:
                    chunks.append({
                        "chunk_index": chunk_index,
                        "page_num":    page_num,
                        "text":        sub,
                        "char_count":  len(sub),
                    })
                    chunk_index += 1

            except Exception as e:
                err = f"Page {page_num} extraction error: {e}"
                logger.warning(f"  {err}")
                errors.append(err)

        doc.close()

    except Exception as e:
        err = f"Failed to open PDF {file_path}: {e}"
        logger.error(err)
        errors.append(err)

    return chunks, total_pages, pages_skipped, errors


# ─── Public API ───────────────────────────────────────────────────────────────

def parse_pdf(
    file_path: str,
    doc_id: int,
    force: bool = False,
) -> ParseResult:
    """
    Parse a PDF file, store chunks in DB, update document status.

    Args:
        file_path:  Absolute or relative path to the PDF file.
        doc_id:     Document row id in the documents table.
        force:      If True, re-parse even if chunks already exist.

    Returns:
        ParseResult with summary statistics.
    """
    result = ParseResult(doc_id=doc_id, file_path=file_path)

    # Idempotency check
    if not force and chunks_exist(doc_id):
        # Count existing chunks
        from pipeline.database import get_chunks
        existing = get_chunks(doc_id)
        result.chunks_extracted = len(existing)
        result.chunks_stored = 0
        result.was_cached = True
        logger.info(f"PDF already parsed: doc_id={doc_id}, {len(existing)} chunks cached")
        return result

    if not Path(file_path).exists():
        err = f"File not found: {file_path}"
        logger.error(err)
        result.errors.append(err)
        update_document_status(doc_id, "failed", 0)
        return result

    logger.info(f"Parsing: {Path(file_path).name} (doc_id={doc_id})")

    # Extract
    chunks, total_pages, pages_skipped, errors = _extract_chunks_from_pdf(file_path, doc_id)
    result.total_pages = total_pages
    result.pages_skipped = pages_skipped
    result.chunks_extracted = len(chunks)
    result.errors = errors

    if not chunks:
        logger.warning(f"  No text extracted from {file_path}")
        update_document_status(doc_id, "failed", 0)
        return result

    # Replace if forcing
    if force:
        deleted = delete_chunks_for_doc(doc_id)
        logger.info(f"  Force re-parse: deleted {deleted} existing chunks")

    # Store
    stored = insert_chunks(doc_id, chunks)
    result.chunks_stored = stored

    # Update document record
    update_document_status(doc_id, "parsed", chunk_count=len(chunks))

    logger.info(
        f"  Parsed: {total_pages} pages, "
        f"{pages_skipped} skipped, "
        f"{len(chunks)} chunks, "
        f"{stored} stored"
    )
    return result


def parse_all_pending(
    company_id: str,
    force: bool = False,
) -> list[ParseResult]:
    """
    Parse all documents for a company that have been downloaded but not yet parsed.
    Skips documents without a local file_path.

    Args:
        company_id: e.g. "paytm"
        force:      Re-parse even if already parsed.

    Returns:
        List of ParseResult objects.
    """
    docs = get_documents(company_id)
    results: list[ParseResult] = []

    pending = [
        d for d in docs
        if d.get("file_path")
        and (force or d.get("parse_status") in ("downloaded", "pending", "failed"))
    ]

    logger.info(f"parse_all_pending: {len(pending)} documents to process for '{company_id}'")

    for doc in pending:
        result = parse_pdf(
            file_path=doc["file_path"],
            doc_id=doc["id"],
            force=force,
        )
        results.append(result)

    return results
