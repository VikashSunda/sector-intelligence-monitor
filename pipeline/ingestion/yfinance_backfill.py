import logging
import math
import yfinance as yf
from datetime import datetime

from pipeline.database import get_metrics_dataframe, upsert_metric, init_db, get_connection

logger = logging.getLogger(__name__)

def date_to_quarter(dt: datetime) -> str:
    """Map a datetime to a fiscal quarter string e.g. Q4FY24.
    For simplicity, assume US companies align calendar year to FY."""
    q = (dt.month - 1) // 3 + 1
    fy = dt.year % 100
    return f"Q{q}FY{fy}"

def fetch_yfinance_quarterly(company_id: str, ticker: str):
    logger.info(f"Fetching yfinance quarterly data for {company_id} ({ticker})...")
    stock = yf.Ticker(ticker)
    df = stock.quarterly_income_stmt
    
    if df.empty:
        logger.warning(f"No yfinance data found for {ticker}")
        return

    # yfinance returns dates as columns
    dates = df.columns
    
    metrics_written = 0
    for dt in dates:
        period = date_to_quarter(dt)
        
        def get_val(row_name):
            if row_name in df.index:
                val = df.loc[row_name, dt]
                if not math.isnan(val):
                    return val
            return None

        rev = get_val("Total Revenue")
        op_inc = get_val("Operating Income")
        net_inc = get_val("Net Income")
        eps = get_val("Basic EPS")
        
        # yfinance reports in absolute USD, we want USD Millions
        if rev: rev = rev / 1_000_000
        if op_inc: op_inc = op_inc / 1_000_000
        if net_inc: net_inc = net_inc / 1_000_000
        
        writes = []
        if rev is not None:
            writes.append(("revenue_usd", rev, "USD Mn", "up"))
            if op_inc is not None:
                opm = (op_inc / rev) * 100 if rev else 0
                writes.append(("opm_pct", opm, "%", "up"))
        
        if op_inc is not None:
            writes.append(("operating_profit_usd", op_inc, "USD Mn", "up"))
        if net_inc is not None:
            writes.append(("net_profit_usd", net_inc, "USD Mn", "up"))
        if eps is not None:
            writes.append(("eps_usd", eps, "USD", "up"))
            
        for m_name, m_val, unit, direction in writes:
            upsert_metric(
                company_id=company_id,
                period=period,
                metric_name=m_name,
                metric_value=float(m_val),
                unit=unit,
                direction=direction,
                source_doc_id=None,
                validated=0
            )
            metrics_written += 1
            logger.info(f"  WRITE {period} {m_name} = {m_val} {unit}")
            
    logger.info(f"[{company_id}] yfinance backfill: +{len(dates)} periods, {metrics_written} metrics")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    fetch_yfinance_quarterly("moderna", "MRNA")
