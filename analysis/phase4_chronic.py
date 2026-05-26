"""
phase4_chronic.py
Phase 4: extend the under-disclosure signal with a "chronic" variant that
catches EXPR / SDC -- failures that were never elevated, never deviated,
and had near-zero absolute novelty throughout the window.

Critically also tests the false-positive rate of the new signal against
the survivor population. A signal that fires on healthy companies isn't
a failure predictor.

Three-signal unified detector:
  novelty_spike        -- previously elevated rank + meaningful raw change
  declining_under_disc -- rank decreased to bottom (Phase 2C signal)
  chronic_under_disc   -- persistent bottom rank + frozen raw novelty (NEW)

Outputs:
    outputs/phase4_extended_scoreboard.png
    outputs/phase4_survivor_fp_analysis.csv
    outputs/phase4_failure_detection.csv
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# Import the failure list from Phase 3
from phase3_scale import ALL_FAILURES

NOVELTY_SPIKE_THRESHOLD = 0.75
NOVELTY_SPIKE_RAW_FLOOR = 0.10
UNDER_DISCLOSURE_BOTTOM = 0.34
UNDER_DISCLOSURE_DROP = 0.20
COHORT_ACTIVITY_GATE = 0.10
# Chronic under-disclosure parameters
CHRONIC_MEAN_RANK_MAX = 0.34
CHRONIC_PEAK_RANK_MAX = 0.50
CHRONIC_OWN_RAW_MAX = 0.10


def load_company(ticker: str) -> pd.DataFrame:
    summary = json.loads((PROCESSED_DIR / f"{ticker}_parsed_summary.json").read_text())
    novelty = json.loads((PROCESSED_DIR / f"{ticker}_novelty.json").read_text())
    rows = []
    for entry in summary:
        fy = entry["fiscal_year"]
        nov = novelty.get(fy, {})
        rows.append({
            "ticker": ticker,
            "fiscal_year": int(fy),
            "novelty": nov.get("novelty"),
        })
    return pd.DataFrame(rows).sort_values("fiscal_year").reset_index(drop=True)


def percentile_rank(value, distribution) -> float:
    arr = np.asarray([v for v in distribution if v is not None and not np.isnan(v)])
    if arr.size == 0:
        return np.nan
    return float((arr <= value).sum()) / arr.size


def evaluate_subject(subject: str, case: dict, df: pd.DataFrame) -> dict:
    """Treat `subject` as the focal company in the cohort and evaluate signals.
    `subject` may be either a failure or a survivor in the cohort."""
    cohort_tickers = [case["failure"]] + case["survivors"]
    if subject not in cohort_tickers:
        return None

    path = []
    cohort_max_raw = 0.0
    for fy in case["lookback"]:
        year_df = df[(df.ticker.isin(cohort_tickers)) & (df.fiscal_year == fy)]
        if year_df.empty or subject not in year_df.ticker.values:
            continue
        s_nov = year_df.loc[year_df.ticker == subject, "novelty"].iloc[0]
        if s_nov is None or (isinstance(s_nov, float) and np.isnan(s_nov)):
            continue
        dist = year_df["novelty"].dropna().tolist()
        if not dist:
            continue
        rank = percentile_rank(s_nov, dist)
        year_max = max([v for v in dist if v is not None and not np.isnan(v)])
        cohort_max_raw = max(cohort_max_raw, year_max)
        path.append({"fy": fy, "raw": s_nov, "rank": rank})

    if not path:
        return None

    ranks = [p["rank"] for p in path]
    raws = [p["raw"] for p in path]
    mean_rank = float(np.mean(ranks))
    max_rank = max(ranks)
    first_rank = ranks[0]
    t0_rank = ranks[-1]
    own_max_raw = max(raws)

    novelty_spike = (max_rank >= NOVELTY_SPIKE_THRESHOLD
                     and own_max_raw >= NOVELTY_SPIKE_RAW_FLOOR)
    declining_ud = (
        t0_rank <= UNDER_DISCLOSURE_BOTTOM
        and (first_rank - t0_rank) >= UNDER_DISCLOSURE_DROP
        and cohort_max_raw >= COHORT_ACTIVITY_GATE
    )
    chronic_ud = (
        mean_rank <= CHRONIC_MEAN_RANK_MAX
        and max_rank <= CHRONIC_PEAK_RANK_MAX
        and cohort_max_raw >= COHORT_ACTIVITY_GATE
        and own_max_raw < CHRONIC_OWN_RAW_MAX
    )

    return {
        "subject": subject,
        "cohort_of": case["failure"],
        "sector": case["sector"],
        "n_years": len(path),
        "mean_rank": round(mean_rank, 2),
        "max_rank": round(max_rank, 2),
        "first_rank": round(first_rank, 2),
        "t0_rank": round(t0_rank, 2),
        "own_max_raw": round(own_max_raw, 3),
        "cohort_max_raw": round(cohort_max_raw, 3),
        "novelty_spike": novelty_spike,
        "declining_ud": declining_ud,
        "chronic_ud": chronic_ud,
        "any_signal": novelty_spike or declining_ud or chronic_ud,
    }


def main() -> None:
    all_tickers = sorted({c["failure"] for c in ALL_FAILURES}
                         | {s for c in ALL_FAILURES for s in c["survivors"]})
    df = pd.concat([load_company(t) for t in all_tickers], ignore_index=True)

    # Failure-side evaluation
    failure_results = []
    for case in ALL_FAILURES:
        r = evaluate_subject(case["failure"], case, df)
        if r:
            r["class_hint"] = case["class_hint"]
            failure_results.append(r)
    f_df = pd.DataFrame(failure_results)
    f_df.to_csv(OUTPUTS_DIR / "phase4_failure_detection.csv", index=False)

    # Survivor-side evaluation (false-positive testing). For each cohort, evaluate every
    # survivor as the "subject" -- ask whether the signal would have fired on a healthy
    # company in this position.
    survivor_results = []
    for case in ALL_FAILURES:
        for s in case["survivors"]:
            r = evaluate_subject(s, case, df)
            if r:
                survivor_results.append(r)
    s_df = pd.DataFrame(survivor_results)
    s_df.to_csv(OUTPUTS_DIR / "phase4_survivor_fp_analysis.csv", index=False)

    print("=== FAILURE DETECTION (n=%d) ===" % len(f_df))
    print(f"novelty_spike fires:    {int(f_df['novelty_spike'].sum())}/{len(f_df)}")
    print(f"declining_ud fires:     {int(f_df['declining_ud'].sum())}/{len(f_df)}")
    print(f"chronic_ud fires (NEW): {int(f_df['chronic_ud'].sum())}/{len(f_df)}")
    print(f"any_signal (detected):  {int(f_df['any_signal'].sum())}/{len(f_df)}")

    new_caught = f_df[f_df.chronic_ud & ~f_df.novelty_spike & ~f_df.declining_ud]
    if not new_caught.empty:
        print(f"\nNewly caught by chronic_ud only:")
        print(new_caught[["subject", "sector", "class_hint",
                          "mean_rank", "max_rank", "own_max_raw"]].to_string(index=False))

    print(f"\n=== SURVIVOR FALSE-POSITIVE TEST (n={len(s_df)} subject-cohort pairs) ===")
    print(f"novelty_spike false-positive: {int(s_df['novelty_spike'].sum())}/{len(s_df)} ({s_df['novelty_spike'].mean()*100:.1f}%)")
    print(f"declining_ud false-positive:  {int(s_df['declining_ud'].sum())}/{len(s_df)} ({s_df['declining_ud'].mean()*100:.1f}%)")
    print(f"chronic_ud false-positive:    {int(s_df['chronic_ud'].sum())}/{len(s_df)} ({s_df['chronic_ud'].mean()*100:.1f}%)")
    print(f"any_signal false-positive:    {int(s_df['any_signal'].sum())}/{len(s_df)} ({s_df['any_signal'].mean()*100:.1f}%)")

    fp_chronic = s_df[s_df.chronic_ud]
    if not fp_chronic.empty:
        print(f"\nSurvivors that fire chronic_ud (false positives):")
        print(fp_chronic[["subject", "cohort_of", "sector",
                          "mean_rank", "max_rank", "own_max_raw"]].to_string(index=False))

    # Plot
    fig, ax = plt.subplots(figsize=(12, 11))
    matrix = f_df[["novelty_spike", "declining_ud", "chronic_ud"]].astype(int).values
    n = len(f_df)
    ax.imshow(matrix, cmap="RdYlGn", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["Novelty spike\n(expanding)",
                        "Declining UD\n(rank dropped)",
                        "Chronic UD\n(always bottom + frozen)"], fontsize=10)
    ax.set_yticks(range(n))
    ax.set_yticklabels([f"{r.subject}  ({r.sector})" for _, r in f_df.iterrows()],
                       fontsize=9)
    ax.set_title("Extended three-signal scoreboard (n=24 failures)", fontsize=12)
    for i in range(n):
        for j in range(3):
            v = matrix[i, j]
            ax.text(j, i, "FIRED" if v else "quiet",
                    ha="center", va="center",
                    color="white" if v else "black",
                    fontsize=9, fontweight="bold")
    plt.tight_layout()
    plt.savefig(OUTPUTS_DIR / "phase4_extended_scoreboard.png",
                dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"\nSaved: outputs/phase4_extended_scoreboard.png")


if __name__ == "__main__":
    main()
