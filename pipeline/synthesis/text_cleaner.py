"""
Synthesis text post-processor.

Cleans common LLM output formatting artefacts before display in the dashboard.
All rules are pure whitespace/dash normalisation — meaning is never altered.

Patterns handled:
  1.  "$4.1BinQ1FY25"  ->  "$4.1B in Q1FY25"      (unit + period glued)
  2.  "+$45Mvs-$40M"  ->  "+$45M vs -$40M"         (vs comparison)
  3.  "$820Mrevenue"   ->  "$820M revenue"           (unit + word glued)
  4.  "45%inQ1FY25"   ->  "45% in Q1FY25"           (percent + word/period)
  5.  "11.5Mfrom"     ->  "11.5M from"              (Mn/M/B/K + word)
  6.  "Q1FY25following"-> "Q1FY25 following"         (period + word)
  7.  "inQ1FY25"      ->  "in Q1FY25"               (word + period)
  8.  "2,334Crrevenue"->  "2,334 Cr revenue"        (Crore amount)
  9.  em-dash variants ->  " — "                    (–, --, isolated -)
  10. double spaces    ->  single space
"""

import re

# Fiscal quarter pattern e.g. Q1FY25, Q4FY2024
_QTR = r"Q[1-4]FY\d{2,4}"

# Common connector words that follow a unit without a space
_CONNECTOR = (
    r"in|at|vs|by|of|to|from|for|the|a|an|and|but|or|with|on|per|as|"
    r"is|was|has|have|after|before|while|into|over|its|their|"
    r"revenue|GMV|MTU|users|devices|margins|growth|quarter|"
    r"annually|monthly|surpassing|showing|crossing|reaching|"
    r"suggesting|following|improving|recovering"
)


def _rules(text: str) -> str:

    # ── Rule 0 (priority): "Mn" two-char unit FIRST, before any M rules ─────
    # "10.8Mn merchants" -> "10.8 Mn merchants"
    # "4.5Mnfrom" -> "4.5 Mn from"
    text = re.sub(r"(\d)(Mn)([A-Za-z])", r"\1 \2 \3", text)

    # ── Rule 1: "vs" glued between values: "+$45Mvs-$40M" ───────────────────
    # Before: digit-or-unit char, then "vs", then sign/digit/$
    text = re.sub(r"([0-9MBKCr%\+\-])vs([+\-\$0-9])", r"\1 vs \2", text)

    # ── Rule 2: digit + unit + quarter glued: "4.1BinQ1FY25" ────────────────
    # Use [MBKCr%] but NOT Mn (already handled above)
    text = re.sub(
        r"(\d)([MBKCr%]+)\s*(" + _QTR + r")",
        r"\1\2 \3",
        text,
    )

    # ── Rule 3: "Cr" and remaining multi-char units + word glued ────────────
    text = re.sub(r"(\d)(Cr)([A-Za-z])", r"\1 \2 \3", text)

    # ── Rule 4: Single-char unit + connector word: "$820Mrevenue" ────────────
    text = re.sub(
        r"(\d)([MBK%])((?:" + _CONNECTOR + r")\b)",
        r"\1\2 \3",
        text,
    )

    # ── Rule 5: Percent + word/period glued: "45%in" ─────────────────────────
    text = re.sub(r"(\d%\+?)([A-Za-z])", r"\1 \2", text)

    # ── Rule 6: Period + word glued: "Q1FY25following" ───────────────────────
    text = re.sub(r"(" + _QTR + r")([A-Za-z])", r"\1 \2", text)

    # ── Rule 7: Word + period glued: "inQ1FY25" ──────────────────────────────
    text = re.sub(r"([a-z])(" + _QTR + r")", r"\1 \2", text)

    # ── Rule 8: Single-char unit + any word: "11.5Mfrom" ────────────────────
    text = re.sub(r"(\d)([MBK])([A-Za-z])", r"\1\2 \3", text)

    # ── Rule 9: Crore amounts: "2,334Crrevenue" ──────────────────────────────
    text = re.sub(r"([\d,]+)(Cr)([A-Za-z])", r"\1 \2 \3", text)

    # ── Rule 10: Normalise dashes to em-dash ────────────────────────────────
    en = "\u2013"
    em = "\u2014"
    text = re.sub(r"\s*" + re.escape(en) + r"\s*", " \u2014 ", text)
    text = re.sub(r"\s*" + re.escape(em) + r"\s*", " \u2014 ", text)
    text = re.sub(r"\s+--\s+", " \u2014 ", text)
    # Isolated single hyphen surrounded by spaces (not inside compound words)
    text = re.sub(r"(?<=[A-Za-z0-9])\s+-\s+(?=[A-Za-z0-9])", " \u2014 ", text)

    # ── Rule 11: Collapse double+ spaces ─────────────────────────────────────
    text = re.sub(r"  +", " ", text)

    return text.strip()


def clean_synthesis(text: str) -> str:
    """
    Clean synthesis or investing-lens text before dashboard display.
    Returns original (or empty string) if input is None/empty.
    Safe to call multiple times — idempotent.
    """
    if not text:
        return text or ""
    return _rules(text)


# ── Test suite ────────────────────────────────────────────────────────────────

_TESTS = [
    # (raw_input, expected_output, label)
    (
        "GMV dropped to $4.1BinQ1FY25 following disruption",
        "GMV dropped to $4.1B in Q1FY25 following disruption",
        "unit+period glued",
    ),
    (
        "EBITDA turned positive at +$45Mvs-$40M at the trough",
        "EBITDA turned positive at +$45M vs -$40M at the trough",
        "vs comparison glued",
    ),
    (
        "Revenue is $820Mrevenue vs $1.2Bpeak",
        "Revenue is $820M revenue vs $1.2B peak",
        "unit+word glued",
    ),
    (
        "contribution margin improved from 45%in Q1FY25 to 67%in Q4FY25",
        "contribution margin improved from 45% in Q1FY25 to 67% in Q4FY25",
        "percent+word glued",
    ),
    (
        "11.5Mfrom the trough of 7.8M",
        "11.5M from the trough of 7.8M",
        "M+word glued",
    ),
    (
        "GMV rebounded to $5.8Bby Q4FY25",
        "GMV rebounded to $5.8B by Q4FY25",
        "B+word glued",
    ),
    (
        "Q4FY25following the disruption",
        "Q4FY25 following the disruption",
        "period+word glued",
    ),
    (
        "recovered inQ3FY25 and grew",
        "recovered in Q3FY25 and grew",
        "word+period glued",
    ),
    (
        "Text with  double  spaces here",
        "Text with double spaces here",
        "double spaces",
    ),
    (
        "60%+contribution margins are achievable",
        "60%+ contribution margins are achievable",
        "percent+ glued",
    ),
    (
        "10.8Mnfrom the trough of 7.8M",
        "10.8 Mn from the trough of 7.8M",
        "Mn+word glued (no space)",
    ),
    (
        "revenue of 2,334Crrevenue in FY24",
        "revenue of 2,334 Cr revenue in FY24",
        "Crore amount",
    ),
    (
        "Clean text with no issues at all.",
        "Clean text with no issues at all.",
        "already clean — no change",
    ),
]


def run_tests(verbose: bool = True) -> bool:
    passed = failed = 0
    for raw, expected, label in _TESTS:
        result = clean_synthesis(raw)
        ok = result == expected
        if ok:
            passed += 1
            if verbose:
                print(f"  PASS {label}")
        else:
            failed += 1
            print(f"  FAIL {label}")
            print(f"     IN:   {raw!r}")
            print(f"     GOT:  {result!r}")
            print(f"     WANT: {expected!r}")
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{passed+failed} passed")
    return failed == 0


if __name__ == "__main__":
    import sys, os
    ok = run_tests(verbose=True)

    # Show before/after on the actual DB synthesis
    sys.path.insert(0, ".")
    os.environ.setdefault("DATABASE_PATH", "data/sector_intel.db")
    try:
        from pipeline.database import get_synthesis
        s = get_synthesis("indian_fintech:paytm")
        if s:
            print("\n=== REAL SYNTHESIS BEFORE/AFTER ===\n")
            for field in ("synthesis_text", "investing_lens_text"):
                raw = s.get(field, "") or ""
                cleaned = clean_synthesis(raw)
                status = "CHANGED" if raw != cleaned else "no change"
                print(f"[{field}] {status}")
                if raw != cleaned:
                    # Show first diff
                    for i, (a, b) in enumerate(zip(raw.split(), cleaned.split())):
                        if a != b:
                            ctx_r = " ".join(raw.split()[max(0,i-2):i+3])
                            ctx_c = " ".join(cleaned.split()[max(0,i-2):i+3])
                            print(f"  BEFORE: ...{ctx_r!r}...")
                            print(f"  AFTER:  ...{ctx_c!r}...")
                            break
    except Exception as e:
        print(f"DB read skipped: {e}")

    sys.exit(0 if ok else 1)
