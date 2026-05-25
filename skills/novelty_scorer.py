"""
novelty_scorer.py
Skill: Quantify how much of each year's Risk Factors text is NEW vs.
boilerplate copy-paste from the prior year.

Method: Build a single TF-IDF vocabulary across all of a ticker's
filings, vectorize each year's Risk Factors text, then compute the
cosine similarity between year N and year N-1.

    novelty(N) = 1 - cosine_sim(vec_N, vec_{N-1})

Higher novelty = more new/changed text relative to the prior filing.
Most 10-Ks are heavy on boilerplate; when a company rewrites significant
portions of their risk section, that's the signal -- something changed
in management's actual concerns.

Usage:
    uv run python skills/novelty_scorer.py --ticker BBBY
"""

import argparse
import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def load_yearly_texts(ticker: str) -> dict:
    """Return {fiscal_year: risk_factors_text} for all parsed filings."""
    summary_path = PROCESSED_DIR / f"{ticker}_parsed_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing {summary_path}. Run section_parser.py first.")
    summary = json.loads(summary_path.read_text())

    texts: dict = {}
    for entry in summary:
        fy = entry["fiscal_year"]
        parsed = json.loads((PROCESSED_DIR / f"{ticker}_FY{fy}_parsed.json").read_text())
        texts[fy] = parsed.get("risk_factors_text", "")
    return texts


def compute_yoy_novelty(texts: dict) -> dict:
    """For each year, compute 1 - cosine_sim against the prior year.

    The first year's novelty is undefined and reported as None.
    """
    years = sorted(texts.keys())
    docs = [texts[fy] for fy in years]

    vec = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        min_df=1,
        max_df=1.0,
        stop_words="english",
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b",
    )
    matrix = vec.fit_transform(docs)
    sims = cosine_similarity(matrix)

    results: dict = {}
    for i, fy in enumerate(years):
        if i == 0:
            results[fy] = {"novelty": None, "prior_fy": None, "cosine_sim": None,
                           "token_vocab_size": int(matrix.shape[1])}
        else:
            sim = float(sims[i, i - 1])
            results[fy] = {
                "novelty": round(1 - sim, 4),
                "prior_fy": years[i - 1],
                "cosine_sim": round(sim, 4),
                "token_vocab_size": int(matrix.shape[1]),
            }
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args()
    ticker = args.ticker.upper()

    texts = load_yearly_texts(ticker)
    if len(texts) < 2:
        raise SystemExit(f"Need at least 2 fiscal years for {ticker}, have {len(texts)}.")

    results = compute_yoy_novelty(texts)
    for fy in sorted(results.keys()):
        r = results[fy]
        if r["novelty"] is None:
            print(f"  FY{fy}: (baseline -- no prior year)")
        else:
            print(f"  FY{fy} vs FY{r['prior_fy']}: novelty={r['novelty']:.3f}  "
                  f"cosine_sim={r['cosine_sim']:.3f}")

    out_path = PROCESSED_DIR / f"{ticker}_novelty.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
