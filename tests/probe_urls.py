"""
Follow Google grounding redirects + probe paytm.com/document/ir/ filename variants
to discover real, downloadable Paytm earnings PDFs.
"""

import requests
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/pdf,text/html,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def follow_and_probe(url, label):
    """Follow redirects, return final URL + content-type."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        final = r.url
        ct = r.headers.get("Content-Type", "")
        cl = r.headers.get("Content-Length", str(len(r.content)))
        # PDF magic bytes
        is_pdf = r.content[:4] == b"%PDF" or "pdf" in ct.lower()
        return r.status_code, ct, cl, final, is_pdf
    except Exception as e:
        return 0, str(e)[:60], "?", url, False


print("\n=== Step 1: Follow Google grounding redirect links ===")
# From the earlier web search result for "Paytm investor presentation quarterly PDF 2024"
google_redirects = [
    ("https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGw9KMAf6-Xh8PFB-p3fnVA65MJ5UNq_1H0T3qJ5a9HTSCkiEfLzWfjAK7mcwFM305-GFhiH8JB-IVVAEbVf9rsTJUNnygIgn7IjpJa8vIh9Y_mCpV63NyRfmMSrFcQdIYOyotqGQbjgCsFwFq7Tq1kqZLkot6LNMF1zmZl1fGerFajwG7P_AvxGGGnkUfq7Pw=", "Q4 FY2024 presentation"),
    ("https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGwtHx_Dme9-IaCAc87zGhuZhwD4z9rz12-U-3FgyLRiUQ-7ZrfxogURPV5PBK9gbbVEJ08Z4BFrcZjorij8flekdhnWU86-8gH7rpVNirQ7Se_y9aapspkrWHC-3DcAWIbIFbGHersexLTX7BjxsexTKynMfTU_35racaMNhxkBqHsXXBZV5E8u53mlZ6QPnv0Ohb8dUeVTD0=", "Q3 FY2024 presentation"),
    ("https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGeis4uhX1sKZ1WltJF_yD3ziBdkXCYEe_RrJRn3jmYgjPn2-SVmLMmKouTLOxLuJJaquJH-2qhmQ4dNiQaE0qQC7Ie6NUDGAD92j0ErMxFt138HSRoAtRFfz5FvOG2eNXq0zh0nlr5QcSgM5ReqvHkUAVoQfy9_UjvSZmGq2r8s-RO0cU7ikJxVmjoARfLUk3ugVXOlLBPSD0=", "Q1 FY2024 presentation"),
    ("https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFbaPOkKhNwzo9z9RrmvrsCWgDtYoZZf9h-4rV4zVX04erEVFz2bLk7Rl6jRIQG2T5y2AB37dOmtQeF_3DubeHIHICpoHIcggPJUyDOXO3Asi0TyERctwGiSRSNALaohBVcchf7xRqxYduGOrC0IVDcuqojZ4S0UsZjSMv3BUW8__4QaK7QFk8b4MqgFB2a1fEAGj1TvyYebTI9", "Q1 FY2025 presentation"),
    ("https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFM0QsGQ1UjWUUfFIm3QMVG6d2L277iQVxUtmCX-1fUsJXXl5USTUT4jL0uwHp_wGKXJTJ2YKBfBeQfSRJTUbcyA517RDVTcZmnFprQ0Ib-0hb8QpQUmJo3XuNhAMbdCNSc1If6FvHGPAol7Z4BwtteOFUXQ1RWVIwlt13UiDbaR6SA9n22BHQCLRYp9Y2I1LkJvZKgmVeo1adqRKCL0YYgR4yrblJEuA==", "Q3 FY2025 presentation"),
]

confirmed_urls = []

for redirect_url, label in google_redirects:
    status, ct, cl, final_url, is_pdf = follow_and_probe(redirect_url, label)
    print(f"\n  [{label}]")
    print(f"    Final URL:    {final_url}")
    print(f"    HTTP {status}  |  {ct[:50]}  |  size={cl}")
    print(f"    Is PDF:       {is_pdf}")
    if is_pdf and status == 200:
        confirmed_urls.append((final_url, label, is_pdf))
    time.sleep(1)

print("\n=== Step 2: Probe paytm.com/document/ir/ filename variants ===")
filename_variants = [
    "EarningsPresentation.pdf",
    "earnings-presentation.pdf",
    "Earnings-Presentation.pdf",
    "earnings_presentation.pdf",
    "investor-presentation.pdf",
    "InvestorPresentation.pdf",
    "Paytm-Earnings-Presentation.pdf",
    "Paytm-Investor-Presentation.pdf",
]
quarters = ["q3fy25", "q4fy24", "q3fy24", "q2fy25", "q1fy25"]
BASE = "https://paytm.com/document/ir/"

print("  (checking filename variants for q3fy25 first)")
for fn in filename_variants:
    url = f"{BASE}q3fy25/{fn}"
    try:
        r = requests.head(url, headers={**HEADERS, "Accept": "application/pdf,*/*"},
                         timeout=10, allow_redirects=True)
        ct = r.headers.get("Content-Type", "")
        cl = r.headers.get("Content-Length", "?")
        is_pdf = r.status_code == 200 and "pdf" in ct.lower()
        status_str = "YES" if is_pdf else f"HTTP {r.status_code}"
        print(f"  {status_str:<8}  {fn}  (ct={ct[:40]}, size={cl})")
        if is_pdf:
            confirmed_urls.append((url, f"Q3FY25 {fn}", True))
    except Exception as e:
        print(f"  ERR       {fn}  ({e!s:.40})")
    time.sleep(0.2)

print("\n=== Step 3: Try ir.paytm.com data API ===")
api_candidates = [
    "https://pwebassets.paytm.com/investorrelations/data/financial-results.json",
    "https://pwebassets.paytm.com/investorrelations/data/home.json",
    "https://ir.paytm.com/api/financial-results",
    "https://ir.paytm.com/api/v1/financial-results",
]
for url in api_candidates:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        ct = r.headers.get("Content-Type", "")
        print(f"  HTTP {r.status_code}  {ct[:50]}  {url[-60:]}")
        if r.status_code == 200 and "json" in ct.lower():
            # Try to extract PDF URLs from JSON
            import json
            try:
                data = r.json()
                text = json.dumps(data)
                pdf_urls = [w for w in text.split('"') if ".pdf" in w.lower() and "paytm" in w.lower()]
                if pdf_urls:
                    print(f"    Found {len(pdf_urls)} PDF URLs in JSON!")
                    for u in pdf_urls[:10]:
                        print(f"      {u}")
            except Exception:
                pass
    except Exception as e:
        print(f"  ERR  {url[-60:]}  ({e!s:.60})")
    time.sleep(0.3)

print("\n=== CONFIRMED VALID PDFs ===")
if confirmed_urls:
    for url, label, valid in confirmed_urls:
        print(f"  [OK] {label}")
        print(f"       {url}")
else:
    print("  None confirmed yet — need further investigation")
