"""
phase1c_percentile.py
Phase 1C: methodological refinement of Phase 1B.

Three structural changes:
  1. Multi-control cohorts (3 survivors per failure, not 1)
  2. Standardized lookback windows (t-3 -> t-0 where data available,
     else t-2 -> t-0 -- noted per cohort)
  3. Percentile-rank scoring against the cohort distribution, replacing
     hand-picked binary thresholds

Each year, for each metric (size, LM negative ratio, novelty), the
failure's value is ranked within {failure + survivors}. A failure
sitting at the top (rank ~1.0) is the most extreme in its peer group;
sitting at the median (~0.5) is unremarkable.

Outputs:
  outputs/phase1c_percentile_trajectories.png -- per-pair grid (5x3),
      each panel showing the failure's percentile rank over the
      lookback window for one metric
  outputs/phase1c_scoreboard.png  -- continuous scoreboard heatmap:
      5 pairs x 3 signals, color = percentile rank at t-0
  outputs/phase1c_metrics.csv     -- long-form with percentile ranks
  outputs/phase1c_scorecard.csv   -- one row per pair, summary
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PHASE_DIR = PROJECT_ROOT / "outputs" / "phase1c_methodology_lockdown"
PHASE_DIR.mkdir(parents=True, exist_ok=True)

COHORTS = [
    {
        "failure": "BA", "event_fy": 2018, "lookback": [2015, 2016, 2017, 2018],
        "survivors": ["LMT", "GD", "NOC"],
        "label": "Boeing 737 MAX (Oct 2018)",
        "window_note": "full t-3 to t-0",
    },
    {
        "failure": "SIVB", "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
        "survivors": ["KEY", "FITB", "HBAN"],
        "label": "SVB collapse (Mar 2023)",
        "window_note": "full t-3 to t-0",
    },
    {
        "failure": "BBBY", "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
        "survivors": ["BBY", "M", "KSS"],
        "label": "Bed Bath & Beyond Ch.11 (Apr 2023)",
        "window_note": "full t-3 to t-0",
    },
    {
        "failure": "PTON", "event_fy": 2022, "lookback": [2020, 2021, 2022],
        "survivors": ["GRMN", "LULU", "ROK"],
        "label": "Peloton drawdown (FY2022)",
        "window_note": "t-2 to t-0 only (Peloton IPO'd Sept 2019)",
    },
    {
        "failure": "SI", "event_fy": 2021, "lookback": [2019, 2020, 2021],
        "survivors": ["WAL", "CUBI", "KEY"],
        "label": "Silvergate wind-down (Mar 2023)",
        "window_note": "t-2 to t-0 only (Silvergate IPO'd Nov 2019)",
    },
]

METRICS = [
    ("risk_chars", "Disclosure Volume"),
    ("neg_ratio", "LM Negative ratio"),
    ("novelty", "YoY Novelty"),
]


def load_company(ticker: str) -> pd.DataFrame:
    summary = json.loads((PROCESSED_DIR / f"{ticker}_parsed_summary.json").read_text())
    sentiment = json.loads((PROCESSED_DIR / f"{ticker}_sentiment_risk_factors.json").read_text())
    novelty = json.loads((PROCESSED_DIR / f"{ticker}_novelty.json").read_text())

    rows = []
    for entry in summary:
        fy = entry["fiscal_year"]
        sent = sentiment.get(fy, {})
        nov = novelty.get(fy, {})
        rows.append({
            "ticker": ticker,
            "fiscal_year": int(fy),
            "risk_chars": entry["risk_factors_chars"],
            "neg_ratio": sent.get("Negative_ratio", 0.0),
            "lit_ratio": sent.get("Litigious_ratio", 0.0),
            "novelty": nov.get("novelty"),
        })
    return pd.DataFrame(rows).sort_values("fiscal_year").reset_index(drop=True)


def percentile_rank(value, distribution) -> float:
    """Return fraction of distribution <= value (inclusive). Range [0, 1]."""
    arr = np.asarray([v for v in distribution if v is not None and not np.isnan(v)])
    if arr.size == 0:
        return np.nan
    return float((arr <= value).sum()) / arr.size


def build_percentile_long(df: pd.DataFrame) -> pd.DataFrame:
    """For each cohort/year/metric, compute the failure's percentile rank
    within {failure + survivors}.
    """
    out = []
    for c in COHORTS:
        f = c["failure"]
        for fy in c["lookback"]:
            cohort_tickers = [f] + c["survivors"]
            cohort_year_df = df[(df.ticker.isin(cohort_tickers)) & (df.fiscal_year == fy)]
            if cohort_year_df.empty or f not in cohort_year_df.ticker.values:
                continue

            row = {
                "cohort": f,
                "label": c["label"],
                "fiscal_year": fy,
                "years_to_event": fy - c["event_fy"],
            }
            for col, _ in METRICS:
                f_val = cohort_year_df.loc[cohort_year_df.ticker == f, col].iloc[0]
                dist = cohort_year_df[col].tolist()
                row[f"{col}_value"] = f_val
                row[f"{col}_pct"] = percentile_rank(f_val, dist)
            out.append(row)
    return pd.DataFrame(out)


def per_pair_trajectories(pct_df: pd.DataFrame, out_path: Path) -> None:
    fig, axes = plt.subplots(len(COHORTS), 3, figsize=(15, 3.0 * len(COHORTS)))
    if len(COHORTS) == 1:
        axes = [axes]

    for i, c in enumerate(COHORTS):
        sub = pct_df[pct_df.cohort == c["failure"]].sort_values("fiscal_year")
        x = sub.years_to_event

        for j, (col, label) in enumerate(METRICS):
            ax = axes[i][j]
            pcts = sub[f"{col}_pct"]
            ax.plot(x, pcts, "o-", color="#c0392b", linewidth=2.2, markersize=8)
            ax.axhline(0.5, color="grey", linestyle=":", alpha=0.5, label="cohort median")
            ax.axhline(0.75, color="orange", linestyle="--", alpha=0.5, label="75th pct threshold")
            ax.set_ylim(0, 1.05)
            ax.set_xlabel("Years to event")
            ax.set_ylabel(f"{c['failure']} percentile rank in cohort")
            ax.set_title(f"{c['failure']}: {label}\n({c['label']})", fontsize=9)
            ax.grid(alpha=0.3)
            if i == 0 and j == 0:
                ax.legend(fontsize=8, loc="lower right")

    plt.tight_layout()
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def scoreboard_continuous(pct_df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    """Heatmap: rows = cohorts, cols = signals, color = percentile rank at t=0."""
    fig, ax = plt.subplots(figsize=(11, 5.5))

    rows = []
    for c in COHORTS:
        t0 = pct_df[(pct_df.cohort == c["failure"]) & (pct_df.years_to_event == 0)]
        if t0.empty:
            continue
        row = {"failure": c["failure"], "label": c["label"]}
        for col, _ in METRICS:
            row[col] = float(t0[f"{col}_pct"].iloc[0])
        rows.append(row)
    score_df = pd.DataFrame(rows)

    matrix = score_df[[m[0] for m in METRICS]].values
    im = ax.imshow(matrix, cmap="RdYlGn_r", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(METRICS)))
    ax.set_xticklabels([m[1] for m in METRICS], fontsize=10)
    ax.set_yticks(range(len(score_df)))
    ax.set_yticklabels(
        [f"{r.failure}\n{r.label[:32]}" for _, r in score_df.iterrows()],
        fontsize=9,
    )
    ax.set_title("Failure's percentile rank in its cohort at t=0 (event year)",
                 fontsize=12)

    for i in range(len(score_df)):
        for j in range(len(METRICS)):
            v = matrix[i, j]
            color = "white" if v > 0.6 else "black"
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    color=color, fontsize=11, fontweight="bold")

    cbar = plt.colorbar(im, ax=ax, fraction=0.025, pad=0.04)
    cbar.set_label("Percentile rank (1.0 = most extreme in cohort)", fontsize=9)

    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return score_df


def build_summary(pct_df: pd.DataFrame, score_t0: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in COHORTS:
        sub = pct_df[pct_df.cohort == c["failure"]].sort_values("fiscal_year")
        if sub.empty:
            continue
        t0 = score_t0[score_t0.failure == c["failure"]].iloc[0]
        # Trajectory: did the failure's percentile rank rise from the
        # earliest lookback year to the event year?
        first = sub.iloc[0]
        last = sub.iloc[-1]
        rows.append({
            "failure": c["failure"],
            "label": c["label"],
            "window": c["window_note"],
            "size_pct_start": round(float(first.risk_chars_pct), 2),
            "size_pct_t0": round(float(t0.risk_chars), 2),
            "neg_pct_start": round(float(first.neg_ratio_pct), 2),
            "neg_pct_t0": round(float(t0.neg_ratio), 2),
            "novelty_pct_start": round(float(first.novelty_pct) if first.novelty_pct is not None else np.nan, 2),
            "novelty_pct_t0": round(float(t0.novelty), 2),
            "signals_above_75": int(
                (t0.risk_chars >= 0.75) + (t0.neg_ratio >= 0.75) + (t0.novelty >= 0.75)
            ),
        })
    return pd.DataFrame(rows)


def main() -> None:
    tickers = sorted({c["failure"] for c in COHORTS} | {s for c in COHORTS for s in c["survivors"]})
    df = pd.concat([load_company(t) for t in tickers], ignore_index=True)

    pct_df = build_percentile_long(df)
    metrics_path = PHASE_DIR / "metrics.csv"
    pct_df.to_csv(metrics_path, index=False)
    print(f"Saved: {metrics_path}")

    traj_path = PHASE_DIR / "percentile_trajectories.png"
    per_pair_trajectories(pct_df, traj_path)
    print(f"Saved: {traj_path}")

    scoreboard_path = PHASE_DIR / "scoreboard.png"
    score_t0 = scoreboard_continuous(pct_df, scoreboard_path)
    print(f"Saved: {scoreboard_path}")

    summary = build_summary(pct_df, score_t0)
    summary_path = PHASE_DIR / "scorecard.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Saved: {summary_path}")

    print("\n=== Percentile-rank trajectory (start of window -> event year) ===")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
