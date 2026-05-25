"""
redflag_detector.py
Skill: Scan parsed 10-K text for high-signal red-flag phrases.

These phrases historically correlate with serious trouble: going-concern
warnings, internal controls weaknesses, restatements, active SEC or
DOJ investigations, etc. Counts occurrences across multiple years so
the Analyst Agent can highlight YoY changes.

Usage:
    python3 redflag_detector.py --ticker BA
"""

import argparse
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

RED_FLAGS = {
    "going_concern": [
        r"going\s*concern",
        r"substantial\s*doubt",
        r"unable\s*to\s*continue",
    ],
    "internal_controls": [
        r"material\s*weakness",
        r"significant\s*deficiency",
        r"ineffective\s*internal\s*control",
    ],
    "restatement": [
        r"restate\w*\s*(of|our|the|prior)\s*financial",
        r"restated\s*financial\s*statements",
        r"prior\s*period\s*adjustment",
    ],
    "regulatory_investigation": [
        r"sec\s*investigation",
        r"department\s*of\s*justice\s*investigation",
        r"doj\s*investigation",
        r"subject\s*to\s*(an\s*)?investigation",
        r"grand\s*jury\s*subpoena",
        r"received\s*a\s*subpoena",
    ],
    "litigation_serious": [
        r"class\s*action",
        r"shareholder\s*derivative",
        r"criminal\s*investigation",
        r"criminal\s*charges",
        r"whistleblower",
    ],
    "covenant_breach": [
        r"covenant\s*violation",
        r"covenant\s*breach",
        r"event\s*of\s*default",
        r"acceleration\s*of\s*indebtedness",
    ],
    "auditor_concerns": [
        r"change\s*in\s*auditor",
        r"resignation\s*of\s*(the\s*)?auditor",
        r"qualified\s*opinion",
        r"adverse\s*opinion",
    ],
    "operational_crisis": [
        r"production\s*halt",
        r"plant\s*shutdown",
        r"recall\s*of\s*(our|the)",
        r"suspended\s*operations",
    ],
}


def scan_text(text: str) -> dict:
    text_lower = text.lower()
    findings = {}
    for category, patterns in RED_FLAGS.items():
        matches = []
        total = 0
        for pat in patterns:
            for m in re.finditer(pat, text_lower):
                total += 1
                # capture surrounding context
                start = max(0, m.start() - 100)
                end = min(len(text), m.end() + 200)
                snippet = text[start:end].replace("\n", " ").strip()
                matches.append({"phrase": m.group(0), "context": snippet})
                if len(matches) >= 5:
                    break
            if len(matches) >= 5:
                break
        if total > 0:
            findings[category] = {"count": total, "samples": matches[:5]}
    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args()

    ticker = args.ticker.upper()
    summary_path = PROCESSED_DIR / f"{ticker}_parsed_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing {summary_path}. Run section_parser.py first.")

    summary = json.loads(summary_path.read_text())

    all_findings = {}
    for entry in summary:
        fy = entry["fiscal_year"]
        parsed_path = PROCESSED_DIR / f"{ticker}_FY{fy}_parsed.json"
        parsed = json.loads(parsed_path.read_text())

        # Scan both Risk Factors and MD&A
        combined_text = parsed["risk_factors_text"] + "\n\n" + parsed["mdna_text"]
        findings = scan_text(combined_text)
        all_findings[fy] = findings

        print(f"\n=== FY{fy} Red Flags ===")
        if not findings:
            print("  (none detected)")
        for cat, data in findings.items():
            print(f"  {cat}: {data['count']} occurrence(s)")

    out_path = PROCESSED_DIR / f"{ticker}_redflags.json"
    out_path.write_text(json.dumps(all_findings, indent=2))

    # Year-over-year change summary
    years_sorted = sorted(all_findings.keys(), reverse=True)
    if len(years_sorted) >= 2:
        newest, prior = years_sorted[0], years_sorted[1]
        print(f"\n=== Red Flag Changes: FY{newest} vs FY{prior} ===")
        all_cats = set(all_findings[newest].keys()) | set(all_findings[prior].keys())
        for cat in sorted(all_cats):
            new_count = all_findings[newest].get(cat, {}).get("count", 0)
            old_count = all_findings[prior].get(cat, {}).get("count", 0)
            delta = new_count - old_count
            arrow = "^" if delta > 0 else ("v" if delta < 0 else "=")
            print(f"  {cat:30s}  FY{prior}: {old_count:2d} -> FY{newest}: {new_count:2d}  {arrow}")

    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
