"""
phase2a_retail.py
Phase 2A: scale the failure dataset within the retail sector. Apply the
locked Phase 1C methodology to 5 retail failures against a shared
5-survivor cohort (BBY, M, KSS, JWN, WSM).

Failures:
    BBBY  -- Bed Bath & Beyond, Ch.11 Apr 2023 (already studied in 1C)
    JCP   -- J.C. Penney, Ch.11 May 2020
    SHLD  -- Sears Holdings, Ch.11 Oct 2018
    PIR   -- Pier 1 Imports, Ch.11 Feb 2020
    ASNA  -- Ascena Retail Group, Ch.11 Jul 2020

This is a real test of generalization. If the BBBY-pattern (size + novelty
fire at high percentile, sentiment is sector-effect) holds across all 5
retail failures, the methodology is robust. If it holds for 1-2 only,
BBBY was a coincidence and the article needs to scale back its claim.

Cohort survivors (5): BBY, M, KSS, JWN, WSM. With 6-company cohort the
discrete percentile space becomes {1/6, 2/6, 3/6, 4/6, 5/6, 6/6}.

Outputs:
    outputs/phase2a_retail_scoreboard.png  -- 5 failures x 3 signals heatmap at t=0
    outputs/phase2a_retail_trajectories.png -- per-failure trajectory grid
    outputs/phase2a_retail_metrics.csv    -- long-form data
    outputs/phase2a_retail_summary.csv    -- aggregate hit rate
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PHASE_DIR = PROJECT_ROOT / "outputs" / "phase2a_retail"
PHASE_DIR.mkdir(parents=True, exist_ok=True)

SURVIVORS = ["BBY", "M", "KSS", "JWN", "WSM"]

COHORTS = [
    {"failure": "SHLD", "event_fy": 2017, "lookback": [2014, 2015, 2016, 2017],
     "label": "Sears Holdings Ch.11 (Oct 2018)"},
    {"failure": "JCP",  "event_fy": 2019, "lookback": [2016, 2017, 2018, 2019],
     "label": "J.C. Penney Ch.11 (May 2020)"},
    {"failure": "PIR",  "event_fy": 2019, "lookback": [2016, 2017, 2018, 2019],
     "label": "Pier 1 Imports Ch.11 (Feb 2020)"},
    {"failure": "ASNA", "event_fy": 2019, "lookback": [2016, 2017, 2018, 2019],
     "label": "Ascena Retail Ch.11 (Jul 2020)"},
    {"failure": "BBBY", "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
     "label": "Bed Bath & Beyond Ch.11 (Apr 2023)"},
]

METRICS = [
    ("risk_chars", "Disclosure Volume"),
    ("neg_ratio", "LM Negative ratio"),
    ("novelty", "YoY Novelty"),
]

THRESHOLD = 0.75  # percentile at t-0 to count a signal as "fired"


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


def build_percentile_long(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for c in COHORTS:
        cohort_tickers = [c["failure"]] + SURVIVORS
        for fy in c["lookback"]:
            year_df = df[(df.ticker.isin(cohort_tickers)) & (df.fiscal_year == fy)]
            if year_df.empty or c["failure"] not in year_df.ticker.values:
                continue
            row = {
                "failure": c["failure"],
                "label": c["label"],
                "fiscal_year": fy,
                "years_to_event": fy - c["event_fy"],
                "cohort_size": len(year_df),
            }
            for col, _ in METRICS:
                f_val = year_df.loc[year_df.ticker == c["failure"], col].iloc[0]
                dist = year_df[col].tolist()
                row[f"{col}_value"] = f_val
                row[f"{col}_pct"] = percentile_rank(f_val, dist)
            out.append(row)
    return pd.DataFrame(out)


def plot_trajectories(pct_df: pd.DataFrame, out_path: Path) -> None:
    fig, axes = plt.subplots(len(COHORTS), 3, figsize=(15, 3.0 * len(COHORTS)))
    if len(COHORTS) == 1:
        axes = [axes]

    for i, c in enumerate(COHORTS):
        sub = pct_df[pct_df.failure == c["failure"]].sort_values("fiscal_year")
        x = sub.years_to_event

        for j, (col, label) in enumerate(METRICS):
            ax = axes[i][j]
            ax.plot(x, sub[f"{col}_pct"], "o-", color="#c0392b", linewidth=2.2, markersize=8)
            ax.axhline(0.5, color="grey", linestyle=":", alpha=0.5)
            ax.axhline(THRESHOLD, color="orange", linestyle="--", alpha=0.5,
                       label=f"{int(THRESHOLD*100)}th pct")
            ax.set_ylim(0, 1.05)
            ax.set_xlabel("Years to event")
            ax.set_ylabel(f"{c['failure']} pct rank")
            ax.set_title(f"{c['failure']}: {label}\n({c['label']})", fontsize=9)
            ax.grid(alpha=0.3)
            if i == 0 and j == 0:
                ax.legend(fontsize=8, loc="lower right")

    plt.tight_layout()
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def plot_scoreboard(pct_df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    rows = []
    for c in COHORTS:
        t0 = pct_df[(pct_df.failure == c["failure"]) & (pct_df.years_to_event == 0)]
        if t0.empty:
            continue
        row = {"failure": c["failure"], "label": c["label"]}
        for col, _ in METRICS:
            row[col] = float(t0[f"{col}_pct"].iloc[0])
        rows.append(row)
    score_df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    matrix = score_df[[m[0] for m in METRICS]].values
    im = ax.imshow(matrix, cmap="RdYlGn_r", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(METRICS)))
    ax.set_xticklabels([m[1] for m in METRICS], fontsize=10)
    ax.set_yticks(range(len(score_df)))
    ax.set_yticklabels(
        [f"{r.failure}\n{r.label[:36]}" for _, r in score_df.iterrows()],
        fontsize=9,
    )
    ax.set_title("Retail failures: percentile rank at t=0 (vs cohort BBY/M/KSS/JWN/WSM)",
                 fontsize=11)
    for i in range(len(score_df)):
        for j in range(len(METRICS)):
            v = matrix[i, j]
            color = "white" if v > 0.6 else "black"
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    color=color, fontsize=11, fontweight="bold")
    plt.colorbar(im, ax=ax, fraction=0.025, pad=0.04)
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return score_df


def hit_rate_summary(pct_df: pd.DataFrame, score_t0: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in COHORTS:
        sub = pct_df[pct_df.failure == c["failure"]].sort_values("fiscal_year")
        if sub.empty:
            continue
        t0 = score_t0[score_t0.failure == c["failure"]].iloc[0]
        first = sub.iloc[0]
        size_traj = float(sub.risk_chars_pct.iloc[-1] - first.risk_chars_pct)
        neg_traj = float(sub.neg_ratio_pct.iloc[-1] - first.neg_ratio_pct)
        novelty_t0 = float(t0.novelty)

        # Detection rules:
        # vol_signal: percentile reached >= 0.75 by t=0 AND grew >= +0.25pp from start (trajectory)
        # neg_signal: same but for negative ratio
        # nov_signal: novelty rank >= 0.75 at any year in lookback (spike, not trajectory)
        vol_signal = (float(t0.risk_chars) >= THRESHOLD) and (size_traj >= 0.25)
        neg_signal = (float(t0.neg_ratio) >= THRESHOLD) and (neg_traj >= 0.25)
        nov_signal = bool((sub.novelty_pct >= THRESHOLD).any())

        rows.append({
            "failure": c["failure"],
            "event_year": c["event_fy"],
            "vol_t0_pct": round(float(t0.risk_chars), 2),
            "vol_pct_traj": round(size_traj, 2),
            "vol_signal": vol_signal,
            "neg_t0_pct": round(float(t0.neg_ratio), 2),
            "neg_pct_traj": round(neg_traj, 2),
            "neg_signal": neg_signal,
            "novelty_max_pct": round(float(sub.novelty_pct.max()), 2),
            "nov_signal": nov_signal,
            "signals_fired": int(vol_signal) + int(neg_signal) + int(nov_signal),
        })
    return pd.DataFrame(rows)


def main() -> None:
    tickers = sorted({c["failure"] for c in COHORTS} | set(SURVIVORS))
    df = pd.concat([load_company(t) for t in tickers], ignore_index=True)

    pct_df = build_percentile_long(df)
    metrics_path = PHASE_DIR / "metrics.csv"
    pct_df.to_csv(metrics_path, index=False)
    print(f"Saved: {metrics_path}")

    traj_path = PHASE_DIR / "trajectories.png"
    plot_trajectories(pct_df, traj_path)
    print(f"Saved: {traj_path}")

    scoreboard_path = PHASE_DIR / "scoreboard.png"
    score_t0 = plot_scoreboard(pct_df, scoreboard_path)
    print(f"Saved: {scoreboard_path}")

    summary = hit_rate_summary(pct_df, score_t0)
    summary_path = PHASE_DIR / "summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Saved: {summary_path}")

    print("\n=== Retail failure detection scorecard ===")
    print(summary.to_string(index=False))

    n = len(summary)
    if n > 0:
        for sig in ["vol_signal", "neg_signal", "nov_signal"]:
            fired = summary[sig].sum()
            print(f"\n{sig}: {fired}/{n} failures detected ({fired/n*100:.0f}%)")
        avg_fired = summary["signals_fired"].mean()
        print(f"\nAverage signals fired per failure: {avg_fired:.1f}/3")
        all_detect = (summary["signals_fired"] >= 1).sum()
        print(f"Detected (>= 1 signal): {all_detect}/{n} ({all_detect/n*100:.0f}%)")


if __name__ == "__main__":
    main()
