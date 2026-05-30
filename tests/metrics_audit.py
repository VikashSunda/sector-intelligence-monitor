import sys, os
sys.path.insert(0, '.')
os.environ['DATABASE_PATH'] = 'data/sector_intel.db'
from pipeline.database import get_connection

with get_connection() as conn:
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='metrics'"
    ).fetchone()
    print('=== metrics table schema ===')
    print(schema[0])
    print()

    metrics = conn.execute(
        'SELECT DISTINCT metric_name FROM metrics ORDER BY metric_name'
    ).fetchall()
    print('=== Metric types stored ===')
    for m in metrics:
        cnt = conn.execute(
            'SELECT COUNT(*) FROM metrics WHERE metric_name=?', (m[0],)
        ).fetchone()[0]
        print(f'  {m[0]:<35} {cnt:2} quarters')

    print()
    docs = conn.execute('SELECT period, doc_type, parse_status FROM documents').fetchall()
    print('=== Indexed IR documents ===')
    for d in docs:
        print(f'  {d[0]:<8} {d[1]:<25} {d[2]}')
