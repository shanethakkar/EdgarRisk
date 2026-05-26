"""
phase1d_spirit.py
Phase 1D: out-of-sample validation. Apply the locked Phase 1C
methodology to Spirit Airlines (Ch. 11 filed Nov 2024) -- a case
that was NOT used to develop or tune the methodology.

If the BBBY-pattern (size + novelty at high percentile against
sector peers) reappears here, that's evidence the model generalizes.
If not, that's evidence of overfitting to the development set.

Cohort:
    SAVE  (Spirit Airlines, Ch.11 Nov 2024)
    ULCC  (Frontier, ULCC peer)
    ALK   (Alaska, mid-cap survivor)
    LUV   (Southwest, established LCC)

Lookback: 2020-2023 (t-3 -> t-0). Frontier ULCC IPO'd April 2021 so
only FY2021-FY2023 available for that survivor; analysis handles
missing-year gracefully.

Outputs:
    outputs/phase1d_spirit_scoreboard.png
    outputs/phase1d_spirit_trajectories.png
    outputs/phase1d_spirit_metrics.csv
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

COHORT = {
    "failure": "SAVE",
    "event_fy": 2023,
    "lookback": [2020, 2021, 2022, 2023],
    "survivors": ["ULCC", "ALK", "LUV"],
    "label": "Spirit Airlines Ch.11 (Nov 2024)",
    "window_note": "t-3 to t-0 (ULCC IPO'd Apr 2021 so missing FY2020)",
}

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
            "novelty": nov.get("novelty"),
        })
    return pd.DataFrame(rows).sort_values("fiscal_year").reset_index(drop=True)


def percentile_rank(value, distribution) -> float:
    arr = np.asarray([v for v in distribution if v is not None and not np.isnan(v)])
    if arr.size == 0:
        return np.nan
    return float((arr <= value).sum()) / arr.size


def build_percentile_long(df: pd.DataFrame, cohort: dict) -> pd.DataFrame:
    out = []
    cohort_tickers = [cohort["failure"]] + cohort["survivors"]
    for fy in cohort["lookback"]:
        year_df = df[(df.ticker.isin(cohort_tickers)) & (df.fiscal_year == fy)]
        if year_df.empty or cohort["failure"] not in year_df.ticker.values:
            continue
        row = {
            "fiscal_year": fy,
            "years_to_event": fy - cohort["event_fy"],
            "cohort_size": len(year_df),
        }
        for col, _ in METRICS:
            f_val = year_df.loc[year_df.ticker == cohort["failure"], col].iloc[0]
            dist = year_df[col].tolist()
            row[f"{col}_value"] = f_val
            row[f"{col}_pct"] = percentile_rank(f_val, dist)
        out.append(row)
    return pd.DataFrame(out)


def plot_trajectories(pct_df: pd.DataFrame, cohort: dict, out_path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    for j, (col, label) in enumerate(METRICS):
        ax = axes[j]
        ax.plot(pct_df.years_to_event, pct_df[f"{col}_pct"],
                "o-", color="#c0392b", linewidth=2.4, markersize=10)
        ax.axhline(0.5, color="grey", linestyle=":", alpha=0.5, label="cohort median")
        ax.axhline(0.75, color="orange", linestyle="--", alpha=0.5, label="75th pct threshold")
        ax.set_ylim(0, 1.05)
        ax.set_xlabel("Years to event")
        ax.set_ylabel("SAVE percentile rank in airline cohort")
        ax.set_title(f"SAVE: {label}\nCohort: ULCC, ALK, LUV", fontsize=10)
        ax.grid(alpha=0.3)
        if j == 0:
            ax.legend(fontsize=8, loc="lower right")

    plt.suptitle(f"Out-of-sample test: {cohort['label']}", fontsize=13, y=1.02)
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_scoreboard(pct_df: pd.DataFrame, out_path: Path) -> None:
    t0 = pct_df[pct_df.years_to_event == 0]
    if t0.empty:
        return
    values = [float(t0[f"{col}_pct"].iloc[0]) for col, _ in METRICS]

    fig, ax = plt.subplots(figsize=(9, 2.4))
    matrix = np.array([values])
    im = ax.imshow(matrix, cmap="RdYlGn_r", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(METRICS)))
    ax.set_xticklabels([m[1] for m in METRICS], fontsize=11)
    ax.set_yticks([0])
    ax.set_yticklabels(["SAVE\nCh.11 Nov 2024"], fontsize=10)
    ax.set_title("Spirit Airlines: percentile rank at t=0 (FY2023, last 10-K before Ch.11)",
                 fontsize=11)
    for j, v in enumerate(values):
        color = "white" if v > 0.6 else "black"
        ax.text(j, 0, f"{v:.2f}", ha="center", va="center",
                color=color, fontsize=14, fontweight="bold")

    plt.colorbar(im, ax=ax, fraction=0.04, pad=0.04)
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    tickers = [COHORT["failure"]] + COHORT["survivors"]
    df = pd.concat([load_company(t) for t in tickers], ignore_index=True)

    print("=== Raw values per company-year ===")
    show = df[df.fiscal_year.isin(COHORT["lookback"])].sort_values(["fiscal_year", "ticker"])
    print(show.to_string(index=False))

    pct_df = build_percentile_long(df, COHORT)
    metrics_path = OUTPUTS_DIR / "phase1d_spirit_metrics.csv"
    pct_df.to_csv(metrics_path, index=False)
    print(f"\nSaved: {metrics_path}")

    traj_path = OUTPUTS_DIR / "phase1d_spirit_trajectories.png"
    plot_trajectories(pct_df, COHORT, traj_path)
    print(f"Saved: {traj_path}")

    score_path = OUTPUTS_DIR / "phase1d_spirit_scoreboard.png"
    plot_scoreboard(pct_df, score_path)
    print(f"Saved: {score_path}")

    print("\n=== SAVE percentile trajectory ===")
    print(pct_df.to_string(index=False))


if __name__ == "__main__":
    main()
