import sys, os
sys.path.insert(0, '.')
os.environ['DATABASE_PATH'] = 'data/sector_intel.db'
from pipeline.database import get_connection

with get_connection() as conn:
    # Documents table schema
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='documents'"
    ).fetchone()
    print('=== documents table DDL ===')
    print(schema[0])
    print()

    # Full documents rows
    print('=== documents rows ===')
    rows = conn.execute(
        'SELECT id, parse_status, file_path, chunk_count FROM documents'
    ).fetchall()
    for r in rows:
        print(dict(r))

    print()
    # Where does chunk_count get populated? Check if it's a column or computed
    # Also check what the seed function calls
    with open('app.py', encoding='utf-8') as f:
        content = f.read()
    # Find _seed_demo_if_empty definition
    start = content.find('def _seed_demo_if_empty')
    end = content.find('\ndef ', start + 1)
    print('=== _seed_demo_if_empty in app.py ===')
    print(content[start:end])
