import sys, os, re
sys.path.insert(0, '.')
os.environ['DATABASE_PATH'] = 'data/sector_intel.db'
from pipeline.database import get_metrics_dataframe

def qkey(p):
    m = re.match(r'Q(\d)FY(\d{2,4})', str(p))
    if m:
        q, fy = int(m.group(1)), int(m.group(2))
        return (fy+2000 if fy<100 else fy, q)
    return (0, p)

df = get_metrics_dataframe('paytm')
periods = sorted(df['period'].unique(), key=qkey)
print('=== COVERAGE REPORT ===')
print(f'Earliest:        {periods[0]}')
print(f'Latest:          {periods[-1]}')
print(f'Unique quarters: {len(periods)}')
print(f'3-year (12+):    {len(periods) >= 12}')
print(f'Periods: {periods}')
print()
print('=== METRICS PER PERIOD ===')
for p in periods:
    pdata = df[df['period']==p]
    names = sorted(pdata['metric_name'].tolist())
    print(f'  {p}: {len(names)} metrics  {names}')
print()
print(f'Total rows: {len(df)}')
print('All metric names:')
for n in sorted(df['metric_name'].unique()):
    print(f'  {n}')
