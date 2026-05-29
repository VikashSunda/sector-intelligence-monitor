"""
FastAPI backend.
Provides the mandatory /api/refresh endpoint and read-only data API
for any consumers that prefer HTTP over direct DB access.

Phases:
  Phase 1 → skeleton with stubs (current)
  Phase 8 → scheduler.run_refresh() wired into /api/refresh

Run locally:
    uvicorn backend.main:app --reload --port 8000
"""

import logging
import os

from contextlib import asynccontextmanager
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from pipeline.config import SECTORS
from pipeline.database import (
    get_all_sectors,
    get_companies_by_sector,
    get_documents,
    get_metrics_dataframe,
    get_refresh_log,
    get_synthesis,
    init_db,
)
from pipeline.schemas import (
    CompanyResponse,
    DocumentResponse,
    RefreshLogEntry,
    RefreshResult,
    SynthesisResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialised.")
    yield


app = FastAPI(
    title="Sector Intelligence Monitor API",
    description=(
        "Ingests public company filings, extracts structured financial metrics "
        "via LLM, and serves an investing intelligence dashboard."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "version": "0.1.0"}


# ─── Sectors ──────────────────────────────────────────────────────────────────

@app.get("/api/sectors", tags=["data"])
def list_sectors():
    """Return all defined sectors with their display names."""
    return {"sectors": SECTORS}


# ─── Companies ────────────────────────────────────────────────────────────────

@app.get("/api/companies", response_model=list[CompanyResponse], tags=["data"])
def list_companies(sector: str = Query(None, description="Filter by sector key")):
    """Return companies, optionally filtered by sector."""
    if sector:
        return get_companies_by_sector(sector)
    all_companies = []
    for s in get_all_sectors():
        all_companies.extend(get_companies_by_sector(s))
    return all_companies


# ─── Metrics ──────────────────────────────────────────────────────────────────

@app.get("/api/metrics", tags=["data"])
def get_company_metrics(
    company_id: str = Query(..., description="Company slug, e.g. 'paytm'"),
    metric_names: str = Query(
        None, description="Comma-separated metric names to filter"
    ),
):
    """
    Return time-series metrics for a company in long format.
    Each row: {period, metric_name, metric_value, unit, direction}.
    """
    names = [n.strip() for n in metric_names.split(",")] if metric_names else None
    df = get_metrics_dataframe(company_id, names)
    if df.empty:
        return {"company_id": company_id, "metrics": []}
    return {"company_id": company_id, "metrics": df.to_dict(orient="records")}


# ─── Synthesis ────────────────────────────────────────────────────────────────

@app.get("/api/synthesis", response_model=SynthesisResponse, tags=["data"])
def get_sector_synthesis(sector: str = Query(...)):
    """Return the most recent synthesis + investing lens for a sector."""
    result = get_synthesis(sector)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No synthesis found for sector '{sector}'. Run a refresh first.",
        )
    return SynthesisResponse(**result)


# ─── Documents ────────────────────────────────────────────────────────────────

@app.get("/api/documents", response_model=list[DocumentResponse], tags=["data"])
def list_documents(company_id: str = Query(...)):
    """Return all source documents for a company with parse status."""
    docs = get_documents(company_id)
    return [DocumentResponse(**d) for d in docs]


# ─── Refresh ──────────────────────────────────────────────────────────────────

@app.post("/api/refresh", response_model=RefreshResult, tags=["pipeline"])
def trigger_refresh(
    sector: str = Query("indian_fintech", description="Sector to refresh"),
    background: bool = Query(
        False, description="Run asynchronously (returns immediately)"
    ),
    background_tasks: BackgroundTasks = None,
):
    """
    Trigger a full data refresh for a sector.
    Checks for new filings, ingests, extracts metrics, re-runs synthesis.

    - background=false (default): blocks until complete, returns summary
    - background=true: queues the job and returns immediately
    """
    try:
        from scheduler import run_refresh  # Wired in Phase 8
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Scheduler not yet implemented. Complete Phase 8 to enable.",
        )

    if background and background_tasks is not None:
        background_tasks.add_task(run_refresh, sector)
        return RefreshResult(
            status="queued",
            sector=sector,
            docs_checked=0,
            new_docs_found=0,
            errors=[],
            duration_seconds=0.0,
        )

    result = run_refresh(sector)
    return RefreshResult(**result)


# ─── Refresh log ──────────────────────────────────────────────────────────────

@app.get("/api/refresh-log", tags=["pipeline"])
def refresh_log(limit: int = Query(10, ge=1, le=100)):
    """Return the N most recent refresh log entries."""
    entries = get_refresh_log(limit)
    return {"entries": entries}


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
