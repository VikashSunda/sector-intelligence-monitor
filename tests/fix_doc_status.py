import sys, os
sys.path.insert(0, '.')
os.environ['DATABASE_PATH'] = 'data/sector_intel.db'
from pipeline.database import get_connection

with get_connection() as conn:
    sql = "UPDATE documents SET parse_status='indexed' WHERE parse_status='pending' AND file_path IS NULL"
    n = conn.execute(sql).rowcount
    print(f'Updated {n} documents: pending -> indexed')
    rows = conn.execute('SELECT id, period, parse_status, chunk_count FROM documents').fetchall()
    for r in rows:
        print(dict(r))
