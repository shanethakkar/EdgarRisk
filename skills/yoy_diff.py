"""
yoy_diff.py
Skill: Compute year-over-year diff of Risk Factors between two parsed 10-Ks.

Identifies:
  - NEW risks (present this year, not last year)
  - REMOVED risks (present last year, not this year)
  - MODIFIED risks (substantially changed wording)
  - UNCHANGED risks (essentially same)

Uses fuzzy matching on risk headings + body similarity since identical
risks are often reworded slightly year-over-year.

Usage:
    python3 yoy_diff.py --ticker BA --year_a 2024 --year_b 2023
"""

import argparse
import json
from difflib import SequenceMatcher
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def similarity(a: str, b: str) -> float:
    """Ratio of similarity between two strings, 0..1."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def best_match(target: dict, candidates: list, threshold: float = 0.5):
    """Find the best-matching risk in candidates for target risk."""
    best = None
    best_score = 0.0
    for c in candidates:
        # weighted score: heading match counts more than body
        h_score = similarity(target["heading"], c["heading"])
        b_score = similarity(target["body"][:1000], c["body"][:1000])
        score = 0.6 * h_score + 0.4 * b_score
        if score > best_score:
            best_score = score
            best = c
    if best_score >= threshold:
        return best, best_score
    return None, best_score


def diff_filings(year_a_data: dict, year_b_data: dict) -> dict:
    """Diff year_a (newer) against year_b (older)."""
    risks_a = year_a_data["risks"]
    risks_b = year_b_data["risks"]

    new_risks = []
    modified_risks = []
    unchanged_risks = []
    matched_b_indices = set()

    for ra in risks_a:
        match, score = best_match(ra, risks_b)
        if match is None:
            new_risks.append(ra)
        else:
            matched_b_indices.add(id(match))
            body_sim = similarity(ra["body"][:2000], match["body"][:2000])
            if body_sim < 0.85:
                modified_risks.append(
                    {
                        "heading_new": ra["heading"],
                        "heading_old": match["heading"],
                        "body_new": ra["body"],
                        "body_old": match["body"],
                        "similarity": round(body_sim, 3),
                    }
                )
            else:
                unchanged_risks.append({"heading": ra["heading"], "similarity": round(body_sim, 3)})

    removed_risks = [rb for rb in risks_b if id(rb) not in matched_b_indices]

    return {
        "ticker": year_a_data["ticker"],
        "year_new": year_a_data["fiscal_year"],
        "year_old": year_b_data["fiscal_year"],
        "counts": {
            "new": len(new_risks),
            "removed": len(removed_risks),
            "modified": len(modified_risks),
            "unchanged": len(unchanged_risks),
            "total_new_year": len(risks_a),
            "total_old_year": len(risks_b),
        },
        "new_risks": new_risks,
        "removed_risks": removed_risks,
        "modified_risks": modified_risks,
        "unchanged_risks": unchanged_risks,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--year_a", required=True, help="Newer fiscal year, e.g. 2024")
    parser.add_argument("--year_b", required=True, help="Older fiscal year, e.g. 2023")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    path_a = PROCESSED_DIR / f"{ticker}_FY{args.year_a}_parsed.json"
    path_b = PROCESSED_DIR / f"{ticker}_FY{args.year_b}_parsed.json"

    for p in (path_a, path_b):
        if not p.exists():
            raise FileNotFoundError(f"Missing parsed file: {p}. Run section_parser.py first.")

    data_a = json.loads(path_a.read_text())
    data_b = json.loads(path_b.read_text())

    diff = diff_filings(data_a, data_b)

    out_path = PROCESSED_DIR / f"{ticker}_diff_FY{args.year_a}_vs_FY{args.year_b}.json"
    out_path.write_text(json.dumps(diff, indent=2))

    c = diff["counts"]
    print(f"\n=== {ticker} FY{args.year_a} vs FY{args.year_b} ===")
    print(f"Risks this year: {c['total_new_year']}, last year: {c['total_old_year']}")
    print(f"  NEW:       {c['new']}")
    print(f"  REMOVED:   {c['removed']}")
    print(f"  MODIFIED:  {c['modified']}")
    print(f"  UNCHANGED: {c['unchanged']}")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
