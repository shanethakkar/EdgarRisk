"""
sentiment_scorer.py
Skill: Score 10-K Risk Factors text using the Loughran-McDonald financial
sentiment dictionary.

The LM dictionary is the canonical finance-NLP wordlist (Loughran &
McDonald 2011, JF). Each English word is tagged with zero or more of:
Negative, Positive, Uncertainty, Litigious, Strong_Modal, Weak_Modal,
Constraining. For each year's filing we compute raw counts plus
normalized ratios (count / total_tokens).

Usage:
    uv run python skills/sentiment_scorer.py --ticker BA
    uv run python skills/sentiment_scorer.py --ticker BA --section mdna

The default --section risk_factors scores only Item 1A; --section mdna
scores Item 7; --section combined scores both.
"""

import argparse
import csv
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DICT_PATH = PROJECT_ROOT / "data" / "reference" / "LoughranMcDonald_MasterDictionary.csv"

LM_CATEGORIES = (
    "Negative",
    "Positive",
    "Uncertainty",
    "Litigious",
    "Strong_Modal",
    "Weak_Modal",
    "Constraining",
)

TOKEN_RE = re.compile(r"[A-Za-z]+")


def load_lm_dictionary(path: Path) -> dict:
    """Map UPPERCASE word -> set of LM categories it belongs to.

    LM CSV stores 0 for non-membership and a non-zero value (often the year
    the word was added) for membership. We treat any non-zero as membership.
    """
    word_to_cats: dict = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cats = tuple(c for c in LM_CATEGORIES if row.get(c, "0") not in ("0", "", None))
            if cats:
                word_to_cats[row["Word"].upper()] = cats
    return word_to_cats


def tokenize(text: str) -> list:
    """Word-level tokenization; alphabetic-only, uppercased to match LM."""
    return [m.group(0).upper() for m in TOKEN_RE.finditer(text)]


def score_text(text: str, lm: dict) -> dict:
    tokens = tokenize(text)
    n = len(tokens)
    counts = {c: 0 for c in LM_CATEGORIES}
    for t in tokens:
        cats = lm.get(t)
        if cats:
            for c in cats:
                counts[c] += 1

    ratios = {f"{c}_ratio": (counts[c] / n if n else 0.0) for c in LM_CATEGORIES}
    return {
        "token_count": n,
        "unique_token_count": len(set(tokens)),
        **{f"{c}_count": counts[c] for c in LM_CATEGORIES},
        **ratios,
        # Net Negative is a commonly-cited derived metric.
        "NetNegative_ratio": ratios["Negative_ratio"] - ratios["Positive_ratio"],
    }


def section_text(parsed: dict, section: str) -> str:
    if section == "risk_factors":
        return parsed.get("risk_factors_text", "")
    if section == "mdna":
        return parsed.get("mdna_text", "")
    if section == "combined":
        return (parsed.get("risk_factors_text", "") + "\n\n"
                + parsed.get("mdna_text", ""))
    raise ValueError(f"Unknown section: {section}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument(
        "--section",
        choices=["risk_factors", "mdna", "combined"],
        default="risk_factors",
    )
    args = parser.parse_args()

    if not DICT_PATH.exists():
        raise FileNotFoundError(
            f"Missing LM dictionary at {DICT_PATH}. "
            "Download it to data/reference/ first."
        )

    ticker = args.ticker.upper()
    summary_path = PROCESSED_DIR / f"{ticker}_parsed_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing {summary_path}. Run section_parser.py first.")

    lm = load_lm_dictionary(DICT_PATH)
    print(f"Loaded LM dictionary: {len(lm):,} tagged words")

    summary = json.loads(summary_path.read_text())
    results = {}
    for entry in summary:
        fy = entry["fiscal_year"]
        parsed_path = PROCESSED_DIR / f"{ticker}_FY{fy}_parsed.json"
        parsed = json.loads(parsed_path.read_text())
        text = section_text(parsed, args.section)
        scored = score_text(text, lm)
        results[fy] = scored

        print(
            f"  FY{fy} ({args.section}, n={scored['token_count']:,}): "
            f"Neg={scored['Negative_ratio']*100:.2f}%  "
            f"Unc={scored['Uncertainty_ratio']*100:.2f}%  "
            f"Lit={scored['Litigious_ratio']*100:.2f}%  "
            f"NetNeg={scored['NetNegative_ratio']*100:+.2f}%"
        )

    out_path = PROCESSED_DIR / f"{ticker}_sentiment_{args.section}.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
