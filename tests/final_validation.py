import sys, os, re
sys.path.insert(0, '.')
os.environ['DATABASE_PATH'] = 'data/sector_intel.db'

print('=== FINAL SUBMISSION VALIDATION ===\n')

# 1. Scheduler
from scheduler import run_refresh, SECTOR_COMPANIES, start_scheduler
companies = [c['company_id'] for c in SECTOR_COMPANIES['indian_fintech']]
print(f'[1] Scheduler OK — companies: {companies}')

# 2. APScheduler
from apscheduler.schedulers.background import BackgroundScheduler
print('[2] APScheduler import OK')

# 3. All pipeline modules
from pipeline.database import init_db, get_metrics_dataframe, get_synthesis
from pipeline.ingestion.paytm_fetcher import PaytmFetcher
from pipeline.ingestion.pdf_parser import parse_all_pending
from pipeline.ingestion.screener_backfill import backfill_paytm_historical
from pipeline.extraction.metrics_extractor import extract_all_parsed
from pipeline.synthesis.synthesizer import synthesize_company
print('[3] All pipeline modules import OK')

# 4. Coverage
def qkey(p):
    m = re.match(r'Q(\d)FY(\d{2,4})', str(p))
    if m:
        q, fy = int(m.group(1)), int(m.group(2))
        return (fy+2000 if fy<100 else fy, q)
    return (0, p)

df = get_metrics_dataframe('paytm')
periods = sorted(df['period'].unique(), key=qkey)
ok = len(periods) >= 12
print(f'[4] Coverage: {periods[0]} to {periods[-1]} | {len(periods)} quarters | 3yr: {ok}')
assert ok, 'Coverage below 12 quarters!'

# 5. Synthesis stored
s = get_synthesis('indian_fintech:paytm')
print(f'[5] Synthesis in DB: {bool(s)} | period: {s["period_range"] if s else "none"}')

# 6. Requirements
reqs = [l.strip() for l in open('requirements.txt') if l.strip() and not l.startswith('#')]
print(f'[6] requirements.txt: {len(reqs)} packages')

# 7. Streamlit config
cfg_text = open('.streamlit/config.toml').read()
headless = 'headless = true' in cfg_text
print(f'[7] Streamlit config: headless={headless}')

# 8. Files present
needed = ['README.md', 'LOOM_DEMO_CHECKLIST.md', 'scheduler.py', 'app.py', '.env.example', 'packages.txt']
for f in needed:
    assert os.path.exists(f), f'Missing: {f}'
print(f'[8] All submission files present: {needed}')

print('\n=== ALL CHECKS PASSED ===')
