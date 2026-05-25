"""
section_parser.py
Skill: Extract Risk Factors (Item 1A) and MD&A (Item 7) from 10-K HTML.

10-K filings are messy HTML. This skill isolates the two sections that
matter most for risk analysis and saves them as clean text + structured
JSON (one entry per risk factor paragraph/heading).

Usage:
    python3 section_parser.py --ticker BA
"""

import argparse
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def html_to_text(html: str) -> str:
    """Strip tags and normalize whitespace."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # collapse runs of blank lines but keep paragraph breaks
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def find_section(text: str, start_patterns, end_patterns) -> str:
    """Slice out a section between any of the start patterns and any end pattern."""
    start_idx = -1
    for p in start_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            # take the LAST match before half the document — the TOC has a
            # match, the real section header is later
            all_matches = list(re.finditer(p, text, re.IGNORECASE))
            if len(all_matches) >= 2:
                start_idx = all_matches[1].start()
            else:
                start_idx = m.start()
            break
    if start_idx == -1:
        return ""

    end_idx = len(text)
    for p in end_patterns:
        m = re.search(p, text[start_idx + 100 :], re.IGNORECASE)
        if m:
            end_idx = start_idx + 100 + m.start()
            break

    return text[start_idx:end_idx].strip()


def split_risk_factors(risk_text: str) -> list:
    """Break Risk Factors into individual risk items by their headings."""
    # Risk factor headings are typically short lines (under ~200 chars) that
    # often end without a period and are followed by a longer paragraph.
    lines = risk_text.split("\n")
    risks = []
    current_heading = None
    current_body = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Heuristic: a heading is short, doesn't end with sentence punctuation,
        # and is followed by lowercase or detailed text.
        is_heading = (
            len(line) < 200
            and len(line) > 10
            and not line.endswith(".")
            and not line.endswith(",")
            and not line.lower().startswith(("the ", "we ", "our ", "if ", "in "))
        )
        if is_heading and current_body:
            risks.append(
                {"heading": current_heading or "(no heading)", "body": " ".join(current_body)}
            )
            current_body = []
            current_heading = line
        elif is_heading:
            current_heading = line
        else:
            current_body.append(line)

    if current_body:
        risks.append({"heading": current_heading or "(no heading)", "body": " ".join(current_body)})

    # Filter junk: skip very short bodies and TOC-like entries
    risks = [r for r in risks if len(r["body"]) > 200]
    return risks


def parse_filing(html_path: Path, ticker: str, fiscal_year: str) -> dict:
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    text = html_to_text(html)

    risk_section = find_section(
        text,
        start_patterns=[
            r"item\s*1a\.?\s*risk\s*factors",
            r"risk\s*factors",
        ],
        end_patterns=[
            r"item\s*1b",
            r"item\s*2\.?\s*properties",
            r"unresolved\s*staff\s*comments",
        ],
    )

    mdna_section = find_section(
        text,
        start_patterns=[
            r"item\s*7\.?\s*management.{0,5}s\s*discussion",
            r"management.{0,5}s\s*discussion\s*and\s*analysis",
        ],
        end_patterns=[
            r"item\s*7a",
            r"item\s*8\.?\s*financial\s*statements",
            r"quantitative\s*and\s*qualitative\s*disclosures",
        ],
    )

    risks = split_risk_factors(risk_section) if risk_section else []

    parsed = {
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "risk_factors_text": risk_section,
        "risk_factors_count": len(risks),
        "risks": risks,
        "mdna_text": mdna_section,
        "mdna_char_count": len(mdna_section),
    }
    return parsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args()

    ticker = args.ticker.upper()
    manifest_path = RAW_DIR / f"{ticker}_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No manifest at {manifest_path}. Run fetch_10k.py first."
        )

    manifest = json.loads(manifest_path.read_text())

    parsed_summary = []
    for entry in manifest:
        html_path = Path(entry["local_path"])
        fy = entry["fiscal_year"]
        print(f"Parsing FY{fy} ({html_path.name})...")
        parsed = parse_filing(html_path, ticker, fy)

        out_path = PROCESSED_DIR / f"{ticker}_FY{fy}_parsed.json"
        out_path.write_text(json.dumps(parsed, indent=2))

        parsed_summary.append(
            {
                "fiscal_year": fy,
                "risk_factors_count": parsed["risk_factors_count"],
                "risk_factors_chars": len(parsed["risk_factors_text"]),
                "mdna_chars": parsed["mdna_char_count"],
                "output": str(out_path),
            }
        )
        print(f"  Risk Factors: {parsed['risk_factors_count']} items, "
              f"{len(parsed['risk_factors_text']):,} chars")
        print(f"  MD&A: {parsed['mdna_char_count']:,} chars")
        print(f"  Saved: {out_path}")

    summary_path = PROCESSED_DIR / f"{ticker}_parsed_summary.json"
    summary_path.write_text(json.dumps(parsed_summary, indent=2))
    print(f"\nSummary: {summary_path}")


if __name__ == "__main__":
    main()
