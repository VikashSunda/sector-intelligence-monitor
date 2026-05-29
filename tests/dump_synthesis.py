import sys, os
sys.path.insert(0, '.')
os.environ['DATABASE_PATH'] = 'data/sector_intel.db'
from pipeline.database import get_synthesis

s = get_synthesis('indian_fintech:paytm')
print('=== SYNTHESIS TEXT (raw) ===')
print(repr(s['synthesis_text']))
print()
print('=== INVESTING LENS TEXT (raw) ===')
print(repr(s['investing_lens_text']))
