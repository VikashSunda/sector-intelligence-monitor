"""
Probe Screener.in to understand available Paytm quarterly data.
"""
import requests, re, json

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

url = "https://www.screener.in/company/PAYTM/consolidated/"
r = requests.get(url, headers=headers, timeout=20)
print(f"Status: {r.status_code}  Len: {len(r.text)}")

content = r.text

# Find quarters section
qmatch = re.search(r'<section[^>]*id=["\']quarters["\'][^>]*>(.*?)</section>', content, re.DOTALL | re.IGNORECASE)
if qmatch:
    raw = qmatch.group(1)
    # Find all th headers (periods)
    headers_found = re.findall(r'<th[^>]*>(.*?)</th>', raw, re.DOTALL)
    headers_clean = [re.sub(r'<[^>]+>', '', h).strip() for h in headers_found]
    print("\nColumn headers (periods):")
    print(headers_clean)

    # Find all rows
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', raw, re.DOTALL)
    print(f"\nRows found: {len(rows)}")
    for row in rows[:20]:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
        cells_clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if cells_clean and cells_clean[0]:
            print(" | ".join(cells_clean[:12]))
else:
    print("No quarters section found")
    # Check what sections exist
    sections = re.findall(r'id=["\']([^"\']+)["\']', content)
    print("All section IDs:", sections[:30])

# Try the Screener API directly
print("\n\nTrying Screener API...")
api_url = "https://www.screener.in/api/company/PAYTM/?format=json"
ra = requests.get(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
print(f"API Status: {ra.status_code}")
if ra.status_code == 200:
    data = ra.json()
    print("Keys:", list(data.keys())[:20])
