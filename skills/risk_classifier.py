"""
risk_classifier.py
Skill: Classify each new/modified risk into a category and assess severity.

Two-tier approach:
  1. Keyword-based first-pass classification into 8 standard buckets
     (financial, operational, regulatory, litigation, cyber, geopolitical,
      supply_chain, market). This runs immediately and is deterministic.
  2. Emits a structured JSON file of risks for the Analyst Agent (Claude
     Code itself) to refine with reasoning when it runs the Rule 2/3
     workflow described in CLAUDE.md.

Usage:
    python3 risk_classifier.py --ticker BA --year_a 2024 --year_b 2023
"""

import argparse
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

CATEGORIES = {
    "financial": [
        "liquidity", "debt", "credit rating", "covenant", "cash flow",
        "interest rate", "indebtedness", "going concern", "impairment",
        "goodwill", "pension", "tax", "currency",
    ],
    "operational": [
        "manufacturing", "production", "quality", "defect", "recall",
        "facility", "operations", "personnel", "labor", "workforce",
        "execution", "delivery", "capacity",
    ],
    "regulatory": [
        "regulation", "regulatory", "FAA", "FDA", "SEC", "compliance",
        "permit", "license", "certification", "approval", "law", "rule",
        "agency", "government", "investigation",
    ],
    "litigation": [
        "litigation", "lawsuit", "claim", "settlement", "court",
        "judgment", "plaintiff", "defendant", "damages", "class action",
        "whistleblower",
    ],
    "cyber": [
        "cyber", "data breach", "information security", "ransomware",
        "hack", "intrusion", "personally identifiable", "privacy",
        "GDPR", "CCPA",
    ],
    "geopolitical": [
        "war", "conflict", "sanctions", "geopolitical", "trade tension",
        "tariff", "export control", "China", "Russia", "Ukraine",
        "Middle East",
    ],
    "supply_chain": [
        "supplier", "supply chain", "raw material", "shortage",
        "component", "vendor", "logistics", "shipping",
    ],
    "market": [
        "competition", "competitor", "demand", "customer", "market share",
        "pricing pressure", "macroeconomic", "recession", "inflation",
    ],
}

SEVERITY_MARKERS_HIGH = [
    "material adverse", "going concern", "material weakness",
    "substantial doubt", "may be unable", "could result in significant",
    "loss of certification", "production halt", "criminal",
]
SEVERITY_MARKERS_MED = [
    "could harm", "may adversely affect", "could materially",
    "subject to investigation", "ongoing investigation",
]


def classify_text(text: str) -> dict:
    text_lower = text.lower()
    scores = {}
    for cat, keywords in CATEGORIES.items():
        hits = sum(1 for k in keywords if k in text_lower)
        if hits > 0:
            scores[cat] = hits

    if not scores:
        primary = "uncategorized"
        secondary = []
    else:
        sorted_cats = sorted(scores.items(), key=lambda x: -x[1])
        primary = sorted_cats[0][0]
        secondary = [c for c, _ in sorted_cats[1:3]]

    severity = "low"
    if any(m in text_lower for m in SEVERITY_MARKERS_HIGH):
        severity = "high"
    elif any(m in text_lower for m in SEVERITY_MARKERS_MED):
        severity = "medium"

    return {
        "primary_category": primary,
        "secondary_categories": secondary,
        "severity": severity,
        "category_scores": scores,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--year_a", required=True)
    parser.add_argument("--year_b", required=True)
    args = parser.parse_args()

    ticker = args.ticker.upper()
    diff_path = PROCESSED_DIR / f"{ticker}_diff_FY{args.year_a}_vs_FY{args.year_b}.json"
    if not diff_path.exists():
        raise FileNotFoundError(f"Missing diff file: {diff_path}. Run yoy_diff.py first.")

    diff = json.loads(diff_path.read_text())

    classified = {"ticker": ticker, "year_new": args.year_a, "year_old": args.year_b}

    # Classify NEW risks
    new_classified = []
    for r in diff["new_risks"]:
        cls = classify_text(r["heading"] + " " + r["body"])
        new_classified.append({**r, "classification": cls})
    classified["new_risks"] = new_classified

    # Classify MODIFIED risks
    mod_classified = []
    for r in diff["modified_risks"]:
        cls = classify_text(r["heading_new"] + " " + r["body_new"])
        mod_classified.append({**r, "classification": cls})
    classified["modified_risks"] = mod_classified

    # Removed risks: classify based on old wording
    rem_classified = []
    for r in diff["removed_risks"]:
        cls = classify_text(r["heading"] + " " + r["body"])
        rem_classified.append({**r, "classification": cls})
    classified["removed_risks"] = rem_classified

    # Aggregate counts by category
    category_summary = {cat: {"new": 0, "removed": 0, "modified": 0} for cat in CATEGORIES}
    category_summary["uncategorized"] = {"new": 0, "removed": 0, "modified": 0}
    for r in new_classified:
        category_summary[r["classification"]["primary_category"]]["new"] += 1
    for r in rem_classified:
        category_summary[r["classification"]["primary_category"]]["removed"] += 1
    for r in mod_classified:
        category_summary[r["classification"]["primary_category"]]["modified"] += 1
    classified["category_summary"] = category_summary

    out_path = PROCESSED_DIR / f"{ticker}_classified_FY{args.year_a}_vs_FY{args.year_b}.json"
    out_path.write_text(json.dumps(classified, indent=2))

    print(f"\n=== Risk Classification: {ticker} FY{args.year_a} vs FY{args.year_b} ===")
    print(f"\nCategory shifts (NEW / REMOVED / MODIFIED):")
    for cat, c in category_summary.items():
        if c["new"] or c["removed"] or c["modified"]:
            print(f"  {cat:15s}  +{c['new']}  -{c['removed']}  ~{c['modified']}")

    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
