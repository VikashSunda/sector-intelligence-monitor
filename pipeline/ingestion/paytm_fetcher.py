"""
Paytm (One 97 Communications Ltd) document discovery and download.
BSE scrip code: 543396

Discovery flow:
  1. BSE Corporate Announcements API — primary source for concall transcripts
  2. Curated fallback list           — known public BSE filing URLs (guaranteed at least 1 doc)

Documents targeted:
  - Earnings call transcripts  (quarterly, from BSE)
  - Investor presentations     (ad-hoc, from BSE)
  - Quarterly financial results PDFs

All metadata stored in documents table via DocumentTracker (dedup via UNIQUE constraint).
PDFs downloaded to data/pdfs/paytm/.

Usage:
    from pipeline.ingestion.paytm_fetcher import fetch_paytm_documents

    result = fetch_paytm_documents(from_date="2022-04-01", download_pdfs=True)
    print(result)
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from pipeline.config import COMPANIES, date_to_quarter
from pipeline.ingestion.document_tracker import DocumentRecord, DocumentTracker

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

COMPANY_ID = "paytm"
SCRIP_CODE = "543396"
PDF_DIR = Path("data/pdfs/paytm")

BSE_API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnGetAnnouncementDtls/w"
BSE_PDF_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
BSE_CORP_FILING_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# Map of headline keyword → doc_type
DOC_TYPE_MAP = [
    ("transcript",            "concall_transcript"),
    ("earnings call",         "concall_transcript"),
    ("concall",               "concall_transcript"),
    ("investor presentation", "investor_presentation"),
    ("investor day",          "investor_presentation"),
    ("annual report",         "annual_report"),
    ("quarterly results",     "quarterly_results"),
    ("financial results",     "quarterly_results"),
    ("unaudited results",     "quarterly_results"),
]

# BSE search keywords — each is a separate API call
BSE_SEARCH_KEYWORDS = [
    "Transcript",
    "Investor Presentation",
    "",   # Empty = all announcements (catches financial results)
]

# ─── Curated fallback document list ──────────────────────────────────────────
# These are real Paytm filings on BSE, used if the API returns no results.
# Source: https://www.bseindia.com (category: Result → Transcript)
# Verified format: https://www.bseindia.com/xml-data/corpfiling/AttachLive/{name}

# ── Verified real Paytm investor presentations ────────────────────────────────
# All URLs below were confirmed HTTP 200 + application/pdf via HEAD request.
# Source: paytm.com/document/ir/financial-results/ (official IR portal)
# Confirmed: 2026-05-29
#
# URL pattern:
#   FY24:  paytm.com/document/ir/financial-results/{filename}.pdf
#   FY25:  paytm.com/document/ir/financial-results/fy2024-25/{filename}.pdf

FALLBACK_DOCUMENTS = [
    # ── FY25 (April 2024 – March 2025) ───────────────────────────────────────
    {
        "source_url": "https://paytm.com/document/ir/financial-results/fy2024-25/Paytm-Earnings-Presentation_Jan-2025_USD_Final.pdf",
        "doc_type": "investor_presentation",
        "period": "Q3FY25",
        "headline": "Paytm Earnings Presentation Q3 FY2025 (Jan 2025) - USD",
    },
    {
        "source_url": "https://paytm.com/document/ir/financial-results/fy2024-25/Paytm-Earnings-Presentation_May-2025_USD.pdf",
        "doc_type": "investor_presentation",
        "period": "Q4FY25",
        "headline": "Paytm Earnings Presentation Q4 FY2025 (May 2025) - USD",
    },
    {
        "source_url": "https://paytm.com/document/ir/financial-results/fy2024-25/Earnings-Presentation_USD_Q1_FY25.pdf",
        "doc_type": "investor_presentation",
        "period": "Q1FY25",
        "headline": "Paytm Earnings Presentation Q1 FY2025 - USD",
    },
    # ── FY24 (April 2023 – March 2024) ───────────────────────────────────────
    {
        "source_url": "https://paytm.com/document/ir/financial-results/Earnings-Presentation_INR_FY24-Q4.pdf",
        "doc_type": "investor_presentation",
        "period": "Q4FY24",
        "headline": "Paytm Earnings Presentation Q4 FY2024 - INR",
    },
    {
        "source_url": "https://paytm.com/document/ir/financial-results/Paytm_Q3_FY_2024-Earnings-Presentation_INR.pdf",
        "doc_type": "investor_presentation",
        "period": "Q3FY24",
        "headline": "Paytm Earnings Presentation Q3 FY2024 - INR",
    },
    {
        "source_url": "https://paytm.com/document/ir/financial-results/Paytm_Q2_FY_2024-Earnings-Presentation_INR.pdf",
        "doc_type": "investor_presentation",
        "period": "Q2FY24",
        "headline": "Paytm Earnings Presentation Q2 FY2024 - INR",
    },
    {
        "source_url": "https://paytm.com/document/ir/financial-results/Paytm_Q1_FY_2024_Earnings-Presentation_INR.pdf",
        "doc_type": "investor_presentation",
        "period": "Q1FY24",
        "headline": "Paytm Earnings Presentation Q1 FY2024 - INR",
    },
]


# ─── Fetch result ─────────────────────────────────────────────────────────────

@dataclass
class FetchResult:
    """Summary of a fetch_paytm_documents() run."""
    discovered: int = 0           # Total URLs found (BSE + fallback)
    new_documents: int = 0        # URLs newly inserted into DB
    skipped_duplicates: int = 0   # URLs already in DB (skipped)
    downloaded: int = 0           # PDFs successfully downloaded
    failed_downloads: int = 0     # PDFs that failed to download
    records: list[DocumentRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    bse_api_success: bool = False # Whether BSE API returned results

    def __str__(self) -> str:
        return (
            f"FetchResult("
            f"discovered={self.discovered}, "
            f"new={self.new_documents}, "
            f"duplicates={self.skipped_duplicates}, "
            f"downloaded={self.downloaded}, "
            f"failed={self.failed_downloads}, "
            f"bse_api={'OK' if self.bse_api_success else 'FALLBACK'}"
            f")"
        )


# ─── Main fetcher class ───────────────────────────────────────────────────────

class PaytmFetcher:
    """
    Discovers and downloads Paytm investor documents.

    Discovery order:
      1. BSE Corporate Announcements API (primary)
      2. Curated fallback URLs (if API returns 0 results)

    Deduplication is enforced by DocumentTracker via UNIQUE(company_id, source_url).
    """

    def __init__(self):
        self.tracker = DocumentTracker(COMPANY_ID)
        PDF_DIR.mkdir(parents=True, exist_ok=True)

    # ─── BSE discovery ────────────────────────────────────────────────────────

    def _query_bse_api(self, keyword: str, from_date: str, to_date: str) -> list[dict]:
        """Single BSE API request. Returns raw announcement list or []."""
        from_dt = datetime.strptime(from_date, "%Y-%m-%d")
        to_dt   = datetime.strptime(to_date, "%Y-%m-%d")

        params = {
            "scripcd":      SCRIP_CODE,
            "CategoryID":   "",
            "subcategoryid":"",
            "FromDate":     from_dt.strftime("%d/%m/%Y"),
            "ToDate":       to_dt.strftime("%d/%m/%Y"),
            "pageno":       "1",
            "strSearch":    keyword,
        }

        resp = requests.get(
            BSE_API_URL,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=20,
        )
        resp.raise_for_status()

        data = resp.json()
        rows = data.get("Table", [])
        if not isinstance(rows, list):
            return []
        return rows

    def discover_bse(self, from_date: str, to_date: str) -> list[dict]:
        """
        Query BSE API across all search keywords.
        Returns deduplicated list of announcement dicts.
        """
        all_rows: list[dict] = []

        for keyword in BSE_SEARCH_KEYWORDS:
            try:
                logger.info(f"BSE query: keyword={keyword!r} [{from_date} → {to_date}]")
                rows = self._query_bse_api(keyword, from_date, to_date)
                logger.info(f"  Got {len(rows)} rows")
                all_rows.extend(rows)
                time.sleep(1.5)   # Polite delay between BSE requests
            except requests.RequestException as e:
                logger.warning(f"BSE API failed for keyword={keyword!r}: {e}")
            except Exception as e:
                logger.warning(f"BSE parse error for keyword={keyword!r}: {e}")

        # Deduplicate by AttachmentName
        seen: set[str] = set()
        unique: list[dict] = []
        for row in all_rows:
            att = (row.get("AttachmentName") or row.get("ATTACHMENTNAME") or "").strip()
            if att and att not in seen:
                seen.add(att)
                unique.append(row)
            elif not att:
                # No attachment — skip
                pass

        logger.info(f"BSE: {len(all_rows)} total → {len(unique)} unique with attachments")
        return unique

    # ─── Classification ───────────────────────────────────────────────────────

    @staticmethod
    def _classify(headline: str) -> tuple[str, bool]:
        """
        Returns (doc_type, is_relevant).
        is_relevant=False → announcement is not a document we want to ingest.
        """
        h = headline.lower()
        for keyword, doc_type in DOC_TYPE_MAP:
            if keyword in h:
                return doc_type, True
        # Include standalone financial result PDFs
        if any(k in h for k in ("result", "financial", "quarter", "annual")):
            return "quarterly_results", True
        return "other", False

    @staticmethod
    def _parse_bse_date(date_str: str) -> str:
        """
        Parse BSE date formats to YYYY-MM-DD.
        Handles: "22/01/2025 03:31:00", "20250122", "2025-01-22 03:31:00"
        """
        if not date_str:
            return datetime.now().strftime("%Y-%m-%d")
        # Take only the date part
        date_str = date_str.strip()[:10]
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return datetime.now().strftime("%Y-%m-%d")

    # ─── PDF download ─────────────────────────────────────────────────────────

    def download_pdf(
        self,
        url: str,
        doc_id: int,
        period: str,
    ) -> Optional[str]:
        """
        Download PDF from URL to data/pdfs/paytm/.
        Returns local path on success, None on failure.
        Skips download if file already exists (idempotent).
        """
        # Build safe local filename from doc_id + period
        safe_period = period.replace("/", "_")
        # Infer extension from URL
        url_path = url.split("?")[0]
        ext = Path(url_path).suffix.lower() or ".pdf"
        local_filename = f"{doc_id}_{safe_period}{ext}"
        local_path = PDF_DIR / local_filename

        # Already downloaded?
        if local_path.exists() and local_path.stat().st_size > 1024:
            logger.info(f"  Already on disk: {local_path}")
            return str(local_path)

        try:
            logger.info(f"  Downloading: {url}")
            resp = requests.get(
                url,
                headers={**REQUEST_HEADERS, "Accept": "application/pdf,*/*"},
                timeout=45,
                stream=True,
            )
            resp.raise_for_status()

            # Verify it looks like a PDF or file (not an HTML error page)
            content_type = resp.headers.get("Content-Type", "")
            if "html" in content_type and resp.headers.get("Content-Length", "9999") == "0":
                logger.warning(f"  Got HTML response (likely 404 page): {url}")
                return None

            with open(local_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=16384):
                    if chunk:
                        fh.write(chunk)

            size_kb = local_path.stat().st_size // 1024
            if size_kb < 5:
                # Suspiciously small — probably an HTML error page saved as PDF
                logger.warning(f"  File too small ({size_kb}KB) — likely invalid: {url}")
                local_path.unlink()
                return None

            logger.info(f"  Saved: {local_path} ({size_kb} KB)")
            return str(local_path)

        except requests.RequestException as e:
            logger.warning(f"  Download failed: {url} — {e}")
            if local_path.exists():
                local_path.unlink()
            return None

    # ─── Process one announcement ─────────────────────────────────────────────

    def _process_announcement(
        self,
        source_url: str,
        doc_type: str,
        period: str,
        headline: str,
        result: FetchResult,
        download_pdfs: bool,
    ) -> None:
        """Register one URL, optionally download, update result in-place."""
        record = self.tracker.register(
            source_url=source_url,
            doc_type=doc_type,
            period=period,
            headline=headline,
        )

        if record.is_new:
            result.new_documents += 1
            logger.info(f"  NEW [{period}] {doc_type}: {headline[:70]}")

            if download_pdfs and record.doc_id:
                file_path = self.download_pdf(source_url, record.doc_id, period)
                if file_path:
                    self.tracker.update_file_path(record.doc_id, file_path)
                    record.file_path = file_path
                    record.parse_status = "downloaded"
                    result.downloaded += 1
                else:
                    self.tracker.mark_failed(record.doc_id, f"Download failed: {source_url}")
                    record.parse_status = "failed"
                    result.failed_downloads += 1
                    result.errors.append(f"Download failed [{period}]: {source_url}")
        else:
            result.skipped_duplicates += 1
            logger.debug(f"  DUP [{period}] {headline[:70]}")

        result.records.append(record)

    # ─── Main entry point ─────────────────────────────────────────────────────

    def run(
        self,
        from_date: str = "2022-04-01",
        download_pdfs: bool = True,
    ) -> FetchResult:
        """
        Discover and optionally download all Paytm IR documents.

        Strategy:
          1. Try BSE API for all announcements since from_date
          2. If BSE returns 0 useful results, use curated fallback list
          3. Process each: register in DB, download PDF if requested

        Args:
            from_date:    Earliest date to include (YYYY-MM-DD)
            download_pdfs: Whether to download PDF files to data/pdfs/paytm/

        Returns:
            FetchResult with counts and DocumentRecord list.
        """
        to_date = datetime.now().strftime("%Y-%m-%d")
        result = FetchResult()

        # ── Step 1: BSE API ───────────────────────────────────────────────────
        bse_announcements = self.discover_bse(from_date, to_date)
        result.bse_api_success = len(bse_announcements) > 0

        bse_processed = 0
        for ann in bse_announcements:
            attachment = (ann.get("AttachmentName") or ann.get("ATTACHMENTNAME") or "").strip()
            headline   = (
                ann.get("Headline") or ann.get("HEADLINE") or
                ann.get("NewsSub")  or ann.get("NEWSSUB")  or
                ann.get("NewsTitle") or ""
            ).strip()
            date_str   = (
                ann.get("News_submission_dt") or ann.get("DT_TM") or ""
            ).strip()

            if not attachment:
                continue

            doc_type, is_relevant = self._classify(headline)
            if not is_relevant:
                logger.debug(f"  Irrelevant: {headline[:60]}")
                continue

            source_url = f"{BSE_PDF_BASE}{attachment}"
            parsed_date = self._parse_bse_date(date_str)
            period = date_to_quarter(parsed_date)

            result.discovered += 1
            bse_processed += 1
            self._process_announcement(
                source_url, doc_type, period, headline, result, download_pdfs
            )

        logger.info(f"BSE: {bse_processed} relevant announcements processed")

        # ── Step 2: Fallback if BSE returned nothing ──────────────────────────
        if bse_processed == 0:
            logger.warning(
                "BSE API returned 0 relevant results. "
                "Using curated fallback document list."
            )
            for doc in FALLBACK_DOCUMENTS:
                result.discovered += 1
                self._process_announcement(
                    source_url=doc["source_url"],
                    doc_type=doc["doc_type"],
                    period=doc["period"],
                    headline=doc["headline"],
                    result=result,
                    download_pdfs=download_pdfs,
                )

        return result


# ─── Convenience function ─────────────────────────────────────────────────────

def fetch_paytm_documents(
    from_date: str = "2022-04-01",
    download_pdfs: bool = True,
) -> FetchResult:
    """
    Convenience function: ensures DB + company exist, then runs fetcher.

    Args:
        from_date:     Earliest date for document discovery
        download_pdfs: Whether to download PDFs locally

    Returns:
        FetchResult
    """
    from pipeline.database import init_db, insert_company

    init_db()

    co = COMPANIES.get("paytm", {})
    insert_company(
        company_id="paytm",
        name=co.get("name", "Paytm"),
        sector=co.get("sector", "indian_fintech"),
        ticker=co.get("ticker"),
        exchange=co.get("exchange"),
        ir_url=co.get("ir_url"),
    )

    fetcher = PaytmFetcher()
    return fetcher.run(from_date=from_date, download_pdfs=download_pdfs)


# ─── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Fetch Paytm investor documents")
    parser.add_argument("--from-date", default="2022-04-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--no-download", action="store_true", help="Skip PDF downloads")
    args = parser.parse_args()

    result = fetch_paytm_documents(
        from_date=args.from_date,
        download_pdfs=not args.no_download,
    )
    print(f"\nResult: {result}")
    print(f"Documents: {len(result.records)}")
