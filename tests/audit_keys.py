import re
from collections import Counter

with open('app.py', encoding='utf-8') as f:
    lines = f.readlines()

print('=== All plotly_chart calls ===')
for i, line in enumerate(lines, 1):
    if 'plotly_chart' in line:
        print(f'L{i:4}: {line.rstrip()}')

print()
print('=== All widget key= values ===')
keys = []
for i, line in enumerate(lines, 1):
    m = re.search(r'key=([^\s,\)]+)', line)
    if m:
        raw = m.group(1).strip('"').strip("'")
        keys.append((i, raw))

# Static (non-f-string) keys are the only ones that can duplicate at definition time
static = [(ln, k) for ln, k in keys if not k.startswith('f"') and not k.startswith("f'")]
dupes = {k: v for k, v in Counter(k for _, k in static).items() if v > 1}

print(f'Total widget keys found: {len(keys)}')
if dupes:
    print(f'DUPLICATE STATIC KEYS: {dupes}')
else:
    print('No duplicate static keys')

print()
for ln, k in keys:
    print(f'  L{ln:4}: {k}')
