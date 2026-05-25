"""
memo_writer.py
Skill: Generate the final investor memo as Markdown.

Pulls together:
  - YoY diff counts and category shifts
  - Top NEW risks with classification + severity
  - Top REMOVED risks
  - Materially MODIFIED risks
  - Red-flag findings with YoY comparison

Output: outputs/{TICKER}_risk_memo_FY{A}_vs_FY{B}.md

The Analyst Agent can read this memo and add narrative interpretation
on top before presenting to the user.

Usage:
    python3 memo_writer.py --ticker BA --year_a 2024 --year_b 2023
"""

import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def truncate(text: str, n: int = 500) -> str:
    text = " ".join(text.split())
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0] + "..."


def severity_badge(sev: str) -> str:
    return {"high": "**[HIGH SEVERITY]**", "medium": "*[medium severity]*", "low": "[low]"}.get(
        sev, "[unspecified]"
    )


def build_memo(ticker: str, year_a: str, year_b: str) -> str:
    classified_path = PROCESSED_DIR / f"{ticker}_classified_FY{year_a}_vs_FY{year_b}.json"
    redflags_path = PROCESSED_DIR / f"{ticker}_redflags.json"

    classified = json.loads(classified_path.read_text())
    redflags = json.loads(redflags_path.read_text()) if redflags_path.exists() else {}

    lines = []
    lines.append(f"# {ticker} 10-K Risk Factor Analysis")
    lines.append(f"## FY{year_a} vs FY{year_b}")
    lines.append("")

    # Executive summary counts
    counts_new = sum(1 for _ in classified["new_risks"])
    counts_rem = sum(1 for _ in classified["removed_risks"])
    counts_mod = sum(1 for _ in classified["modified_risks"])

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- **{counts_new} new risk(s)** disclosed in FY{year_a} not present in FY{year_b}")
    lines.append(f"- **{counts_rem} risk(s) removed** that were present in FY{year_b}")
    lines.append(f"- **{counts_mod} risk(s) materially modified** between filings")
    lines.append("")

    # Category shifts table
    lines.append("## Category Shifts")
    lines.append("")
    lines.append("| Category | New | Removed | Modified |")
    lines.append("|---|---|---|---|")
    for cat, c in classified["category_summary"].items():
        if c["new"] or c["removed"] or c["modified"]:
            lines.append(f"| {cat} | +{c['new']} | -{c['removed']} | ~{c['modified']} |")
    lines.append("")

    # New risks
    lines.append(f"## New Risks Disclosed in FY{year_a}")
    lines.append("")
    if not classified["new_risks"]:
        lines.append("*(none)*")
    else:
        for i, r in enumerate(classified["new_risks"], 1):
            cls = r["classification"]
            lines.append(
                f"### {i}. {r['heading']}  "
                f"`{cls['primary_category']}` {severity_badge(cls['severity'])}"
            )
            lines.append("")
            lines.append(f"> {truncate(r['body'], 600)}")
            lines.append("")

    # Removed risks
    lines.append(f"## Risks Removed Since FY{year_b}")
    lines.append("")
    if not classified["removed_risks"]:
        lines.append("*(none)*")
    else:
        for i, r in enumerate(classified["removed_risks"], 1):
            cls = r["classification"]
            lines.append(f"### {i}. {r['heading']}  `{cls['primary_category']}`")
            lines.append("")
            lines.append(f"> {truncate(r['body'], 400)}")
            lines.append("")

    # Modified risks
    lines.append("## Materially Modified Risks")
    lines.append("")
    if not classified["modified_risks"]:
        lines.append("*(none)*")
    else:
        for i, r in enumerate(classified["modified_risks"], 1):
            cls = r["classification"]
            lines.append(
                f"### {i}. {r['heading_new']}  "
                f"`{cls['primary_category']}` {severity_badge(cls['severity'])}  "
                f"_(similarity: {r['similarity']})_"
            )
            lines.append("")
            lines.append(f"**FY{year_b} wording:**")
            lines.append("")
            lines.append(f"> {truncate(r['body_old'], 400)}")
            lines.append("")
            lines.append(f"**FY{year_a} wording:**")
            lines.append("")
            lines.append(f"> {truncate(r['body_new'], 400)}")
            lines.append("")

    # Red flags
    lines.append("## Red Flag Scan (Risk Factors + MD&A)")
    lines.append("")
    if not redflags:
        lines.append("*(no red flag report found — run redflag_detector.py)*")
    else:
        years_sorted = sorted(redflags.keys(), reverse=True)
        if len(years_sorted) >= 2:
            newest, prior = years_sorted[0], years_sorted[1]
            lines.append(f"| Red Flag Category | FY{prior} | FY{newest} | Change |")
            lines.append("|---|---|---|---|")
            all_cats = set(redflags[newest].keys()) | set(redflags[prior].keys())
            for cat in sorted(all_cats):
                new_count = redflags[newest].get(cat, {}).get("count", 0)
                old_count = redflags[prior].get(cat, {}).get("count", 0)
                delta = new_count - old_count
                arrow = "increase" if delta > 0 else ("decrease" if delta < 0 else "no change")
                lines.append(f"| {cat} | {old_count} | {new_count} | {arrow} |")
            lines.append("")

            # Sample contexts for any newly appeared red flags
            for cat in sorted(all_cats):
                new_count = redflags[newest].get(cat, {}).get("count", 0)
                old_count = redflags[prior].get(cat, {}).get("count", 0)
                if new_count > 0 and new_count > old_count:
                    lines.append(f"### {cat} — sample contexts (FY{newest})")
                    lines.append("")
                    for s in redflags[newest][cat]["samples"][:3]:
                        lines.append(f'- "...{truncate(s["context"], 300)}..."')
                    lines.append("")

    # Footer for analyst narrative
    lines.append("---")
    lines.append("")
    lines.append("## Analyst Narrative")
    lines.append("")
    lines.append("*The Analyst Agent should fill in this section with interpretive commentary*")
    lines.append("*synthesizing the above findings into an investment implication.*")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--year_a", required=True)
    parser.add_argument("--year_b", required=True)
    args = parser.parse_args()

    ticker = args.ticker.upper()
    memo = build_memo(ticker, args.year_a, args.year_b)

    out_path = OUTPUTS_DIR / f"{ticker}_risk_memo_FY{args.year_a}_vs_FY{args.year_b}.md"
    out_path.write_text(memo)

    print(f"\nMemo written: {out_path}")
    print(f"Length: {len(memo):,} characters, {memo.count(chr(10)) + 1} lines")


if __name__ == "__main__":
    main()
