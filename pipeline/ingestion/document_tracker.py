"""
Document tracking layer for the ingestion pipeline.

Wraps pipeline.database CRUD with:
  - DocumentRecord  dataclass — the canonical structured return type for all fetchers
  - DocumentTracker class    — register/update/mark_failed with deduplication

Usage:
    tracker = DocumentTracker("paytm")

    record = tracker.register(
        source_url="https://bse.../doc.pdf",
        doc_type="concall_transcript",
        period="Q3FY25",
        headline="Transcript of Q3 FY2025 Earnings Call",
    )

    if record.is_new:
        file_path = download_pdf(record.source_url)
        tracker.update_file_path(record.doc_id, file_path)
    else:
        print("Already in DB — skipping")
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from pipeline.database import (
    document_exists,
    get_documents,
    insert_document,
    update_document_status,
    update_file_path,
)

logger = logging.getLogger(__name__)


# ─── Structured return type ───────────────────────────────────────────────────

@dataclass
class DocumentRecord:
    """
    Canonical representation of a discovered document.
    Returned by DocumentTracker.register() and get_all_documents().

    Fields:
        company_id    — e.g. "paytm"
        source_url    — canonical BSE PDF URL
        doc_type      — "concall_transcript" | "investor_presentation" | "quarterly_results" | ...
        period        — Indian FY quarter label, e.g. "Q3FY25"
        headline      — raw announcement title from BSE
        doc_id        — SQLite row id in documents table (None if not yet persisted)
        file_path     — absolute or relative path to downloaded PDF (None if not downloaded)
        parse_status  — "pending" | "downloaded" | "parsed" | "failed" | "skipped"
        chunk_count   — number of text chunks after parsing (0 until Phase 3)
        is_new        — True if this URL was newly inserted; False if it was already in DB
    """
    company_id: str
    source_url: str
    doc_type: str
    period: str
    headline: str = ""
    doc_id: Optional[int] = None
    file_path: Optional[str] = None
    parse_status: str = "pending"
    chunk_count: int = 0
    is_new: bool = True

    def __repr__(self) -> str:
        status = "NEW" if self.is_new else "DUP"
        return (
            f"DocumentRecord({status} | {self.period} | {self.doc_type} | "
            f"id={self.doc_id} | {self.parse_status})"
        )


# ─── Tracker ──────────────────────────────────────────────────────────────────

class DocumentTracker:
    """
    Manages document metadata persistence for one company.
    All methods are safe to call multiple times — idempotent through UNIQUE constraint.

    Args:
        company_id: Company slug, e.g. "paytm". Must already exist in companies table.
    """

    def __init__(self, company_id: str):
        self.company_id = company_id

    def is_new(self, source_url: str) -> bool:
        """Return True if this URL has NOT been seen before for this company."""
        return not document_exists(self.company_id, source_url)

    def register(
        self,
        source_url: str,
        doc_type: str,
        period: str,
        headline: str = "",
    ) -> DocumentRecord:
        """
        Register a discovered document URL.

        If the URL is new: inserts a row, returns record with is_new=True.
        If the URL exists: returns existing record with is_new=False.

        The UNIQUE(company_id, source_url) constraint enforces deduplication
        at the DB level, so this is safe to call concurrently or repeatedly.

        Returns:
            DocumentRecord with doc_id populated from DB.
        """
        already_exists = document_exists(self.company_id, source_url)

        doc_id = insert_document(
            company_id=self.company_id,
            source_url=source_url,
            doc_type=doc_type,
            period=period,
            parse_status="pending",
            headline=headline,
        )

        record = DocumentRecord(
            company_id=self.company_id,
            source_url=source_url,
            doc_type=doc_type,
            period=period,
            headline=headline,
            doc_id=doc_id,
            parse_status="pending",
            is_new=not already_exists,
        )

        if not already_exists:
            logger.debug(f"Registered new document: {record}")
        else:
            logger.debug(f"Duplicate skipped: {source_url}")

        return record

    def update_file_path(self, doc_id: int, file_path: str) -> None:
        """
        Store local file path after successful download.
        Also marks parse_status as 'downloaded'.
        """
        update_file_path(doc_id, file_path)
        logger.debug(f"File path updated: doc_id={doc_id} → {file_path}")

    def mark_failed(self, doc_id: int, reason: str = "") -> None:
        """Mark a document as failed to download or parse."""
        update_document_status(doc_id, "failed", chunk_count=0)
        logger.warning(f"Document marked failed: doc_id={doc_id} reason={reason!r}")

    def mark_skipped(self, doc_id: int, reason: str = "") -> None:
        """Mark a document as intentionally skipped (e.g. encrypted PDF)."""
        update_document_status(doc_id, "skipped", chunk_count=0)
        logger.info(f"Document skipped: doc_id={doc_id} reason={reason!r}")

    def get_all_documents(self) -> list[DocumentRecord]:
        """
        Return all documents for this company from the DB as DocumentRecord objects.
        Useful for inspecting current state.
        """
        rows = get_documents(self.company_id)
        return [
            DocumentRecord(
                company_id=row["company_id"],
                source_url=row["source_url"],
                doc_type=row.get("doc_type") or "unknown",
                period=row.get("period") or "",
                headline=row.get("headline") or "",
                doc_id=row["id"],
                file_path=row.get("file_path"),
                parse_status=row.get("parse_status", "pending"),
                chunk_count=row.get("chunk_count", 0),
                is_new=False,   # Already in DB by definition
            )
            for row in rows
        ]

    def count(self) -> int:
        """Return total document count for this company."""
        return len(get_documents(self.company_id))
