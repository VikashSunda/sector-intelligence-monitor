"""
Refresh orchestrator + APScheduler background job.

Entry points:
  1. Direct call:         from scheduler import run_refresh; run_refresh("indian_fintech")
  2. Streamlit button:   same — called from app.py
  3. CLI (manual):       python scheduler.py --sector indian_fintech
  4. Daemon (cron):      python scheduler.py --daemon   (runs every Sunday 02:00 IST)

Pipeline order per refresh:
  Phase 2: Discover new Paytm IR documents (fetcher)
  Phase 3: Parse & chunk any downloaded PDFs
  Phase 4: Extract metrics from parsed chunks (LLM) — skips if no API key
  Phase 6: Regenerate synthesis (LLM) — skips if no API key
  Screener: Backfill any missing historical quarters from Screener.in

All steps are idempotent — safe to re-run without duplicating data.
"""

import argparse
import logging
import os
import time

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Sector → company config ───────────────────────────────────────────────────
SECTOR_COMPANIES = {
    "indian_fintech": [
        {
            "company_id": "paytm",
            "company_name": "Paytm (One97 Communications)",
            "screener_slug": "PAYTM",
        },
        {
            "company_id": "bajaj_finance",
            "company_name": "Bajaj Finance",
            "screener_slug": "BAJFINANCE",
        },
        {
            "company_id": "pb_fintech",
            "company_name": "PB Fintech",
            "screener_slug": "POLICYBZR",
        },
        {
            "company_id": "sbi_cards",
            "company_name": "SBI Cards",
            "screener_slug": "SBICARD",
        },
        {
            "company_id": "creditaccess",
            "company_name": "CreditAccess Grameen",
            "screener_slug": "CREDITACC",
        },
    ],
    # extensibility: add indian_defence, us_biotech here without redesign
}


def run_refresh(sector: str = "indian_fintech") -> dict:
    """
    Run the full data refresh pipeline for a sector.

    Returns a summary dict with keys:
        status, sector, docs_checked, new_docs_found, errors, duration_seconds
    """
    from pipeline.database import init_db, log_refresh

    start = time.time()
    logger.info(f"Starting refresh for sector: {sector}")

    init_db()

    companies = SECTOR_COMPANIES.get(sector, [])
    if not companies:
        logger.warning(f"No companies configured for sector: {sector}")
        return {
            "status": "skipped",
            "sector": sector,
            "docs_checked": 0,
            "new_docs_found": 0,
            "errors": [f"No companies for sector {sector}"],
            "duration_seconds": 0.0,
        }

    docs_checked = 0
    new_docs_found = 0
    errors: list[str] = []

    llm_provider = os.getenv("LLM_PROVIDER", "claude")
    llm_model = os.getenv("LLM_MODEL", "") or (
        "claude-sonnet-4-5" if llm_provider == "claude"
        else "gemini-1.5-flash" if llm_provider == "gemini"
        else "gpt-4o-mini"
    )
    has_llm_key = bool(
        os.getenv("ANTHROPIC_API_KEY") or
        os.getenv("GEMINI_API_KEY") or
        os.getenv("GOOGLE_API_KEY") or
        os.getenv("OPENAI_API_KEY")
    )

    for company in companies:
        cid = company["company_id"]
        cname = company["company_name"]

        # ── Phase 2: Discover + download new documents ────────────────────────
        try:
            from pipeline.ingestion.paytm_fetcher import PaytmFetcher
            fetcher = PaytmFetcher()
            fetch_result = fetcher.run(download_pdfs=True)
            docs_checked += fetch_result.discovered
            new_docs_found += fetch_result.new_documents
            logger.info(
                f"  [{cid}] Fetch: discovered={fetch_result.discovered} "
                f"new={fetch_result.new_documents} dl={fetch_result.downloaded} "
                f"bse={'OK' if fetch_result.bse_api_success else 'FALLBACK'}"
            )
        except Exception as exc:
            msg = f"[{cid}] Fetch error: {exc}"
            logger.error(msg)
            errors.append(msg)

        # ── Phase 3: Parse all downloaded PDFs ────────────────────────────────
        try:
            from pipeline.ingestion.pdf_parser import parse_all_pending
            parse_results = parse_all_pending(cid)
            total_chunks = sum(r.chunks_extracted for r in parse_results)
            logger.info(f"  [{cid}] Parse: {len(parse_results)} docs, {total_chunks} chunks")
        except Exception as exc:
            msg = f"[{cid}] Parse error: {exc}"
            logger.error(msg)
            errors.append(msg)

        # ── Phase 4: Extract metrics via LLM (skipped if no key) ─────────────
        if has_llm_key:
            try:
                from pipeline.extraction.metrics_extractor import extract_all_parsed
                extract_results = extract_all_parsed(
                    cid,
                    company_name=cname,
                    provider=llm_provider,
                    model=llm_model,
                    force=False,
                )
                newly_extracted = [r for r in extract_results if r.success and not r.was_cached]
                logger.info(
                    f"  [{cid}] Extract: {len(newly_extracted)} new, "
                    f"{sum(1 for r in extract_results if r.was_cached)} cached"
                )
            except Exception as exc:
                msg = f"[{cid}] Extract error: {exc}"
                logger.error(msg)
                errors.append(msg)
        else:
            logger.info(f"  [{cid}] Extract: SKIPPED (no LLM API key set)")

        # ── Screener backfill: fill missing historical quarters ───────────────
        screener_slug = company.get("screener_slug", cid.upper())
        try:
            from pipeline.ingestion.screener_backfill import backfill_company_historical
            backfill = backfill_company_historical(
                company_id=cid,
                screener_slug=screener_slug,
            )
            if backfill["periods_new"]:
                logger.info(f"  [{cid}] Screener backfill: +{len(backfill['periods_new'])} periods")
        except Exception as exc:
            msg = f"[{cid}] Screener backfill error: {exc}"
            logger.warning(msg)
            # Non-fatal: Screener may be unreachable

        # ── Phase 6: Regenerate synthesis (skipped if no key) ─────────────────
        if has_llm_key:
            try:
                from pipeline.synthesis.synthesizer import synthesize_company
                synth = synthesize_company(
                    cid,
                    company_name=cname,
                    sector=sector,
                    provider=llm_provider,
                    model=llm_model,
                )
                if synth.success:
                    logger.info(f"  [{cid}] Synthesis: OK ({len(synth.synthesis_text)} chars)")
                else:
                    logger.warning(f"  [{cid}] Synthesis: {synth.error}")
            except Exception as exc:
                msg = f"[{cid}] Synthesis error: {exc}"
                logger.error(msg)
                errors.append(msg)
        else:
            logger.info(f"  [{cid}] Synthesis: SKIPPED (no LLM API key set)")

    duration = round(time.time() - start, 2)
    status = "ok" if not errors else "partial"
    logger.info(
        f"Refresh complete: sector={sector} docs_checked={docs_checked} "
        f"new={new_docs_found} errors={len(errors)} duration={duration}s"
    )

    # ── Write refresh log ──────────────────────────────────────────────────────
    try:
        log_refresh(
            sector=sector,
            docs_checked=docs_checked,
            new_docs_found=new_docs_found,
            errors=errors,
            duration_seconds=duration,
        )
    except Exception as exc:
        logger.error(f"Failed to write refresh_log: {exc}")

    return {
        "status": status,
        "sector": sector,
        "docs_checked": docs_checked,
        "new_docs_found": new_docs_found,
        "errors": errors,
        "duration_seconds": duration,
    }


# ── APScheduler daemon ────────────────────────────────────────────────────────

def start_scheduler():
    """
    Start a background APScheduler job.
    Runs every Sunday at 02:00 IST (UTC+05:30 = 20:30 UTC Saturday).
    """
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        func=lambda: run_refresh("indian_fintech"),
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="Asia/Kolkata"),
        id="weekly_refresh_indian_fintech",
        name="Weekly Indian Fintech Refresh",
        replace_existing=True,
        misfire_grace_time=3600,  # allow up to 1hr late if server was down
    )
    scheduler.start()
    logger.info("APScheduler started — weekly refresh scheduled for Sunday 02:00 IST")
    return scheduler


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sector Intelligence Monitor — Refresh Scheduler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scheduler.py                            # one-shot refresh, indian_fintech
  python scheduler.py --sector indian_fintech    # explicit sector
  python scheduler.py --daemon                   # start cron daemon (blocks)
        """,
    )
    parser.add_argument(
        "--sector",
        default="indian_fintech",
        choices=list(SECTOR_COMPANIES.keys()),
        help="Sector to refresh (default: indian_fintech)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as a background cron daemon (weekly on Sunday 02:00 IST)",
    )
    args = parser.parse_args()

    if args.daemon:
        import signal
        sched = start_scheduler()
        logger.info("Daemon running. Press Ctrl+C to stop.")
        try:
            signal.pause()
        except (AttributeError, KeyboardInterrupt):
            # signal.pause() not on Windows — use sleep loop
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                pass
        finally:
            sched.shutdown()
            logger.info("Scheduler stopped.")
    else:
        result = run_refresh(args.sector)
        print(f"\nRefresh result:")
        for k, v in result.items():
            print(f"  {k}: {v}")
