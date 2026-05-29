import sys, os, re
sys.path.insert(0, '.')
os.environ['DATABASE_PATH'] = 'data/sector_intel.db'
from pipeline.database import get_connection

with get_connection() as conn:
    # 1. Table row counts
    tables = ['companies', 'documents', 'chunks', 'metrics', 'synthesis', 'refresh_log']
    print('=== TABLE ROW COUNTS ===')
    for t in tables:
        try:
            n = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
            print(f'  {t:<20}: {n}')
        except Exception as e:
            print(f'  {t:<20}: ERROR - {e}')

    print()

    # 2. Documents detail
    print('=== DOCUMENTS TABLE ===')
    docs = conn.execute('''
        SELECT id, company_id, period, doc_type, parse_status,
               file_path, source_url
        FROM documents ORDER BY id
    ''').fetchall()
    for d in docs:
        fp = d['file_path'] or ''
        file_exists = os.path.exists(fp) if fp else False
        print(f"  id={d['id']} period={d['period']:<8} status={d['parse_status']:<20} "
              f"file={'EXISTS' if file_exists else 'MISSING':7} url={d['source_url'][-50:]}")

    print()

    # 3. Chunks per document
    print('=== CHUNKS PER DOCUMENT ===')
    chunk_counts = conn.execute('''
        SELECT doc_id, COUNT(*) as cnt FROM chunks GROUP BY doc_id ORDER BY doc_id
    ''').fetchall()
    if chunk_counts:
        for row in chunk_counts:
            print(f'  doc_id={row["doc_id"]}: {row["cnt"]} chunks')
    else:
        print('  (no chunks)')

    # 4. Chunks total + sample
    total_chunks = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
    print(f'\n  Total chunks in DB: {total_chunks}')
    if total_chunks > 0:
        sample = conn.execute('SELECT doc_id, page_num, LEFT(text,60) as preview FROM chunks LIMIT 3').fetchall()
        for s in sample:
            print(f'  Sample: doc_id={s["doc_id"]} page={s["page_num"]} text={s["preview"]!r}')

    print()

    # 5. Metrics summary
    print('=== METRICS SUMMARY ===')
    periods = conn.execute('''
        SELECT period, COUNT(*) as cnt FROM metrics GROUP BY period ORDER BY period
    ''').fetchall()
    for p in periods:
        print(f'  {p["period"]:<10}: {p["cnt"]} metrics')

    print()

    # 6. Synthesis
    print('=== SYNTHESIS ===')
    synth = conn.execute('SELECT sector, period_range, generated_at FROM synthesis').fetchall()
    for s in synth:
        print(f'  sector={s["sector"]} | period={s["period_range"]} | at={s["generated_at"]}')

    print()

    # 7. Dashboard query diagnosis — what does app.py call for chunk_count?
    print('=== DASHBOARD QUERY DIAGNOSIS ===')
    # Check if get_documents returns chunk_count field
    from pipeline.database import get_documents
    docs_api = get_documents('paytm')
    if docs_api:
        sample_doc = docs_api[0]
        keys = list(sample_doc.keys())
        print(f'  get_documents() returns keys: {keys}')
        print(f'  chunk_count in response: {"chunk_count" in keys}')
        print(f'  parse_status sample: {[d.get("parse_status") for d in docs_api]}')
    else:
        print('  get_documents("paytm") returned empty')

    print()

    # 8. Check if app.py reads chunk_count from the right place
    print('=== APP.PY CHUNK_COUNT REFERENCE ===')
    with open('app.py', encoding='utf-8') as f:
        lines = f.readlines()
    for i, line in enumerate(lines, 1):
        if 'chunk' in line.lower() and ('count' in line.lower() or 'chunk_count' in line.lower()):
            print(f'  L{i:4}: {line.rstrip()}')
