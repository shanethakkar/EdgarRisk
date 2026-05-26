"""
phase2b_industrial.py
Phase 2B: Extend the test to three different industrial sectors. Each
failure gets its own 3-survivor sector cohort. Tests whether the 80%
novelty hit rate from Phase 2A retail generalizes to non-retail sectors
with different business models.

Cohorts:
    WE   (WeWork, Ch.11 Nov 2023)
         vs CWK, NMRK, IRM           -- commercial real estate / storage
    YELL (Yellow Corp, Ch.11 Aug 2023)
         vs ODFL, ARCB, XPO          -- LTL trucking
    TUP  (Tupperware Brands, Ch.11 Sept 2024)
         vs CHD, CL, CLX             -- household consumer products

If novelty detects most or all of these failures, the retail finding
generalizes. If it misses several, the methodology is retail-specific.
Tupperware in particular is a stress test -- direct-sales business
model has no perfect public peer, so the cohort is approximate.

Outputs:
    outputs/phase2b_industrial_scoreboard.png
    outputs/phase2b_industrial_trajectories.png
    outputs/phase2b_industrial_metrics.csv
    outputs/phase2b_industrial_summary.csv
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PHASE_DIR = PROJECT_ROOT / "outputs" / "phase2b_industrial"
PHASE_DIR.mkdir(parents=True, exist_ok=True)

COHORTS = [
    {
        "failure": "WE", "event_fy": 2022, "lookback": [2020, 2021, 2022],
        "survivors": ["CWK", "NMRK", "IRM"],
        "label": "WeWork Ch.11 (Nov 2023)",
        "sector": "Commercial real estate / coworking",
        "window_note": "t-2 to t-0 (WE SPAC'd Oct 2021; only 3 10-Ks total)",
    },
    {
        "failure": "YELL", "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
        "survivors": ["ODFL", "ARCB", "XPO"],
        "label": "Yellow Corp Ch.11 (Aug 2023)",
        "sector": "LTL trucking",
        "window_note": "full t-3 to t-0",
    },
    {
        "failure": "TUP", "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
        "survivors": ["CHD", "CL", "CLX"],
        "label": "Tupperware Ch.11 (Sept 2024)",
        "sector": "Household consumer products",
        "window_note": "full t-3 to t-0; imperfect cohort (no direct-sales peer)",
    },
]

METRICS = [
    ("risk_chars", "Disclosure Volume"),
    ("neg_ratio", "LM Negative ratio"),
    ("novelty", "YoY Novelty"),
]

THRESHOLD = 0.75


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
        cohort_tickers = [c["failure"]] + c["survivors"]
        for fy in c["lookback"]:
            year_df = df[(df.ticker.isin(cohort_tickers)) & (df.fiscal_year == fy)]
            if year_df.empty or c["failure"] not in year_df.ticker.values:
                continue
            row = {
                "failure": c["failure"],
                "label": c["label"],
                "sector": c["sector"],
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
    fig, axes = plt.subplots(len(COHORTS), 3, figsize=(15, 3.3 * len(COHORTS)))
    if len(COHORTS) == 1:
        axes = [axes]

    for i, c in enumerate(COHORTS):
        sub = pct_df[pct_df.failure == c["failure"]].sort_values("fiscal_year")
        x = sub.years_to_event

        for j, (col, label) in enumerate(METRICS):
            ax = axes[i][j]
            ax.plot(x, sub[f"{col}_pct"], "o-", color="#c0392b", linewidth=2.2, markersize=8)
            ax.axhline(0.5, color="grey", linestyle=":", alpha=0.5)
            ax.axhline(THRESHOLD, color="orange", linestyle="--", alpha=0.5)
            ax.set_ylim(0, 1.05)
            ax.set_xlabel("Years to event")
            ax.set_ylabel(f"{c['failure']} pct rank")
            ax.set_title(f"{c['failure']} ({c['sector']}): {label}\n{c['label']}", fontsize=9)
            ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def plot_scoreboard(pct_df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    rows = []
    for c in COHORTS:
        t0 = pct_df[(pct_df.failure == c["failure"]) & (pct_df.years_to_event == 0)]
        if t0.empty:
            continue
        row = {"failure": c["failure"], "label": c["label"], "sector": c["sector"]}
        for col, _ in METRICS:
            row[col] = float(t0[f"{col}_pct"].iloc[0])
        rows.append(row)
    score_df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(12, 4.5))
    matrix = score_df[[m[0] for m in METRICS]].values
    im = ax.imshow(matrix, cmap="RdYlGn_r", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(METRICS)))
    ax.set_xticklabels([m[1] for m in METRICS], fontsize=11)
    ax.set_yticks(range(len(score_df)))
    ax.set_yticklabels(
        [f"{r.failure}\n{r.sector}\n{r.label[:30]}" for _, r in score_df.iterrows()],
        fontsize=9,
    )
    ax.set_title("Industrial failures: percentile rank at t=0 (each vs own sector cohort)",
                 fontsize=12)
    for i in range(len(score_df)):
        for j in range(len(METRICS)):
            v = matrix[i, j]
            color = "white" if v > 0.6 else "black"
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    color=color, fontsize=12, fontweight="bold")
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
        novelty_max = float(sub.novelty_pct.max() if sub.novelty_pct.notna().any() else np.nan)

        vol_signal = float(t0.risk_chars) >= THRESHOLD
        neg_signal = float(t0.neg_ratio) >= THRESHOLD
        nov_signal = (not np.isnan(novelty_max)) and (novelty_max >= THRESHOLD)

        rows.append({
            "failure": c["failure"],
            "sector": c["sector"],
            "vol_t0_pct": round(float(t0.risk_chars), 2),
            "neg_t0_pct": round(float(t0.neg_ratio), 2),
            "novelty_max_pct": round(novelty_max, 2) if not np.isnan(novelty_max) else None,
            "vol_signal": vol_signal,
            "neg_signal": neg_signal,
            "nov_signal": nov_signal,
            "signals_fired": int(vol_signal) + int(neg_signal) + int(nov_signal),
        })
    return pd.DataFrame(rows)


def main() -> None:
    tickers = sorted({c["failure"] for c in COHORTS} | {s for c in COHORTS for s in c["survivors"]})
    df = pd.concat([load_company(t) for t in tickers], ignore_index=True)

    pct_df = build_percentile_long(df)
    metrics_path = PHASE_DIR / "metrics.csv"
    pct_df.to_csv(metrics_path, index=False)
    print(f"Saved: {metrics_path}")

    traj_path = PHASE_DIR / "trajectories.png"
    plot_trajectories(pct_df, traj_path)
    print(f"Saved: {traj_path}")

    score_path = PHASE_DIR / "scoreboard.png"
    score_t0 = plot_scoreboard(pct_df, score_path)
    print(f"Saved: {score_path}")

    summary = hit_rate_summary(pct_df, score_t0)
    summary_path = PHASE_DIR / "summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Saved: {summary_path}")

    print("\n=== Industrial failure detection scorecard ===")
    print(summary.to_string(index=False))

    n = len(summary)
    if n > 0:
        for sig in ["vol_signal", "neg_signal", "nov_signal"]:
            fired = summary[sig].sum()
            print(f"\n{sig}: {fired}/{n} failures detected ({fired/n*100:.0f}%)")


if __name__ == "__main__":
    main()
