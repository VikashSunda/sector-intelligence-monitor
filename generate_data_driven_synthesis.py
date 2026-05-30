import logging
from pipeline.database import get_metrics_dataframe, insert_synthesis, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_data_driven_synthesis(company_id: str, sector: str, company_name: str):
    df = get_metrics_dataframe(company_id)
    if df is None or df.empty:
        logger.warning(f"No metrics found for {company_id}")
        return

    periods = sorted(df["period"].unique())
    period_range = f"{periods[0]} to {periods[-1]}" if len(periods) > 1 else periods[0]
    
    # Very basic metric trend calculation
    def get_trend(metric_name):
        m_df = df[df["metric_name"] == metric_name].sort_values("period")
        if len(m_df) < 2: return "insufficient data"
        first = m_df.iloc[0]["metric_value"]
        last = m_df.iloc[-1]["metric_value"]
        if first == 0: return "increased"
        pct_change = ((last - first) / abs(first)) * 100
        if pct_change > 5: return f"grew by {pct_change:.1f}%"
        elif pct_change < -5: return f"declined by {abs(pct_change):.1f}%"
        return "remained stable"

    rev_trend = get_trend("revenue_crore") if "revenue_crore" in df["metric_name"].values else get_trend("revenue_usd")
    profit_trend = get_trend("net_profit_crore") if "net_profit_crore" in df["metric_name"].values else get_trend("net_profit_usd")
    
    synthesis_text = (
        f"{company_name} is a key player in the {sector} sector. "
        f"Over the period {period_range}, the company's revenue {rev_trend}, "
        f"while its net profit {profit_trend}. "
        "These metrics are sourced directly from historical financial backfills."
    )
    
    investing_lens_text = (
        f"The {sector} sector presents opportunities backed by solid fundamentals. "
        f"{company_name}'s trajectory validates steady scale and profitability. "
        "Startups looking to build in this space should target similar unit economics "
        "and growth patterns."
    )
    
    insert_synthesis(
        sector=f"{sector}:{company_id}",
        period_range=period_range,
        synthesis_text=synthesis_text,
        investing_lens_text=investing_lens_text
    )
    logger.info(f"Generated data-driven synthesis for {company_id}")

if __name__ == "__main__":
    init_db()
    for cid, sec, name in [
        ("hal", "indian_defence", "Hindustan Aeronautics Limited"),
        ("bel", "indian_defence", "Bharat Electronics Limited"),
        ("moderna", "us_biotech", "Moderna"),
        ("gilead", "us_biotech", "Gilead Sciences")
    ]:
        generate_data_driven_synthesis(cid, sec, name)
