"""
phase1a_sentiment.py
Phase 1A: extend the case-control validation with Loughran-McDonald
sentiment ratios per fiscal year, alongside the Phase 0 disclosure-volume
and red-flag metrics.

Produces:
    outputs/phase1a_sentiment_trajectories.png  -- headline chart, all 10
                                                   companies on one panel,
                                                   x = years-before-event
    outputs/phase1a_per_pair.png                -- 5 pairs x 3 panels
                                                   (size, sentiment, red flags)
    outputs/phase1a_metrics.csv                 -- long-form table
    outputs/phase1a_yoy_summary.csv             -- per-pair sentiment deltas
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PHASE_DIR = PROJECT_ROOT / "outputs" / "phase1a_sentiment"
PHASE_DIR.mkdir(parents=True, exist_ok=True)

PAIRS = [
    {"failure": "BA",   "survivor": "LMT",  "event": "Boeing 737 MAX (Oct 2018)",       "event_fy": 2018, "lookback": [2017, 2018]},
    {"failure": "SIVB", "survivor": "JPM",  "event": "SVB collapse (Mar 2023)",          "event_fy": 2022, "lookback": [2020, 2021, 2022]},
    {"failure": "BBBY", "survivor": "BBY",  "event": "Bed Bath & Beyond Ch.11 (Apr 2023)","event_fy": 2022, "lookback": [2019, 2020, 2021, 2022]},
    {"failure": "PTON", "survivor": "GRMN", "event": "Peloton drawdown (FY2022)",        "event_fy": 2022, "lookback": [2022, 2023, 2024]},
    {"failure": "SI",   "survivor": "JPM",  "event": "Silvergate wind-down (Mar 2023)",  "event_fy": 2021, "lookback": [2019, 2020, 2021]},
]

FAILURE_TICKERS = {p["failure"] for p in PAIRS}


def load_company(ticker: str) -> pd.DataFrame:
    summary = json.loads((PROCESSED_DIR / f"{ticker}_parsed_summary.json").read_text())
    redflags = json.loads((PROCESSED_DIR / f"{ticker}_redflags.json").read_text())
    sentiment = json.loads((PROCESSED_DIR / f"{ticker}_sentiment_risk_factors.json").read_text())

    rows = []
    for entry in summary:
        fy = entry["fiscal_year"]
        rf = redflags.get(fy, {})
        sent = sentiment.get(fy, {})
        rows.append({
            "ticker": ticker,
            "fiscal_year": int(fy),
            "risk_chars": entry["risk_factors_chars"],
            "redflag_total": sum(v["count"] for v in rf.values()),
            "token_count": sent.get("token_count", 0),
            "neg_ratio": sent.get("Negative_ratio", 0.0),
            "unc_ratio": sent.get("Uncertainty_ratio", 0.0),
            "lit_ratio": sent.get("Litigious_ratio", 0.0),
            "netneg_ratio": sent.get("NetNegative_ratio", 0.0),
        })
    return pd.DataFrame(rows).sort_values("fiscal_year").reset_index(drop=True)


def build_long_table() -> pd.DataFrame:
    tickers = sorted({p["failure"] for p in PAIRS} | {p["survivor"] for p in PAIRS})
    df = pd.concat([load_company(t) for t in tickers], ignore_index=True)
    df["group"] = df["ticker"].apply(lambda t: "failure" if t in FAILURE_TICKERS else "survivor")
    return df


def plot_headline(df: pd.DataFrame, out_path: Path) -> None:
    """One panel, x = years before event, y = Negative ratio."""
    fig, ax = plt.subplots(figsize=(11, 6.5))

    for pair in PAIRS:
        years = pair["lookback"]
        event_fy = pair["event_fy"]
        for role, t, color, marker in [
            ("failure", pair["failure"], "#c0392b", "o"),
            ("survivor", pair["survivor"], "#27ae60", "s"),
        ]:
            sub = df[(df.ticker == t) & (df.fiscal_year.isin(years))].sort_values("fiscal_year")
            if sub.empty:
                continue
            x = sub.fiscal_year - event_fy
            ax.plot(
                x, sub.neg_ratio * 100,
                marker=marker, color=color, alpha=0.7, linewidth=1.8,
                label=f"{t} ({role}: {pair['failure']}/{pair['survivor']})",
            )
            ax.annotate(t, (x.iloc[-1], sub.neg_ratio.iloc[-1] * 100),
                        textcoords="offset points", xytext=(6, 0), fontsize=8, color=color)

    ax.axvline(0, color="black", linestyle="--", alpha=0.4, linewidth=1)
    ax.text(0.05, ax.get_ylim()[1] * 0.95, "event year", fontsize=9, alpha=0.6)
    ax.set_xlabel("Years before failure event (0 = last 10-K before the event)")
    ax.set_ylabel("Negative-word ratio (%, Loughran-McDonald)")
    ax.set_title("Negative Sentiment in 10-K Risk Factors: Failures vs Survivors", fontsize=13)
    ax.grid(alpha=0.3)

    failure_line = plt.Line2D([], [], color="#c0392b", marker="o", linestyle="-", label="failure")
    survivor_line = plt.Line2D([], [], color="#27ae60", marker="s", linestyle="-", label="survivor")
    ax.legend(handles=[failure_line, survivor_line], loc="upper left", fontsize=10)

    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_per_pair(df: pd.DataFrame, out_path: Path) -> None:
    """Per-pair grid: 5 rows x 3 cols (size, neg sentiment, red flags)."""
    fig, axes = plt.subplots(len(PAIRS), 3, figsize=(15, 3.0 * len(PAIRS)))
    if len(PAIRS) == 1:
        axes = [axes]

    for i, pair in enumerate(PAIRS):
        years = pair["lookback"]
        f_df = df[(df.ticker == pair["failure"]) & (df.fiscal_year.isin(years))].sort_values("fiscal_year")
        s_df = df[(df.ticker == pair["survivor"]) & (df.fiscal_year.isin(years))].sort_values("fiscal_year")

        ax = axes[i][0]
        ax.plot(f_df.fiscal_year, f_df.risk_chars / 1000, "o-", color="#c0392b", linewidth=2, label=pair["failure"])
        ax.plot(s_df.fiscal_year, s_df.risk_chars / 1000, "s-", color="#27ae60", linewidth=2, label=pair["survivor"])
        ax.set_title(f"Risk-section size (KB)\n{pair['event']}", fontsize=9)
        ax.set_xlabel("FY")
        ax.set_ylabel("1000 chars")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)

        ax = axes[i][1]
        ax.plot(f_df.fiscal_year, f_df.neg_ratio * 100, "o-", color="#c0392b", linewidth=2, label=pair["failure"])
        ax.plot(s_df.fiscal_year, s_df.neg_ratio * 100, "s-", color="#27ae60", linewidth=2, label=pair["survivor"])
        ax.set_title(f"Negative-word ratio (%)\n{pair['event']}", fontsize=9)
        ax.set_xlabel("FY")
        ax.set_ylabel("LM Negative %")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)

        ax = axes[i][2]
        x_pos = list(range(len(f_df)))
        width = 0.35
        ax.bar([p - width/2 for p in x_pos], f_df.redflag_total, width, color="#c0392b", alpha=0.85, label=pair["failure"])
        s_vals = list(s_df.redflag_total) + [0] * max(0, len(x_pos) - len(s_df))
        ax.bar([p + width/2 for p in x_pos], s_vals[:len(x_pos)], width, color="#27ae60", alpha=0.85, label=pair["survivor"])
        ax.set_xticks(x_pos)
        ax.set_xticklabels(list(f_df.fiscal_year))
        ax.set_title(f"Red-flag count\n{pair['event']}", fontsize=9)
        ax.set_xlabel("FY")
        ax.set_ylabel("Total hits")
        ax.grid(alpha=0.3, axis="y")
        ax.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def yoy_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pair in PAIRS:
        years = pair["lookback"]
        for role, t in [("failure", pair["failure"]), ("survivor", pair["survivor"])]:
            sub = df[(df.ticker == t) & (df.fiscal_year.isin(years))].sort_values("fiscal_year")
            if len(sub) < 2:
                continue
            first, last = sub.iloc[0], sub.iloc[-1]
            rows.append({
                "pair": f"{pair['failure']} vs {pair['survivor']}",
                "role": role,
                "ticker": t,
                "fy_start": int(first.fiscal_year),
                "fy_end": int(last.fiscal_year),
                "size_pct_growth": round((last.risk_chars - first.risk_chars) / first.risk_chars * 100, 1),
                "neg_ratio_start_pct": round(first.neg_ratio * 100, 2),
                "neg_ratio_end_pct": round(last.neg_ratio * 100, 2),
                "neg_ratio_delta_pp": round((last.neg_ratio - first.neg_ratio) * 100, 2),
                "lit_ratio_delta_pp": round((last.lit_ratio - first.lit_ratio) * 100, 2),
                "netneg_delta_pp": round((last.netneg_ratio - first.netneg_ratio) * 100, 2),
                "redflag_delta": int(last.redflag_total - first.redflag_total),
            })
    return pd.DataFrame(rows)


def main() -> None:
    df = build_long_table()
    metrics_path = PHASE_DIR / "metrics.csv"
    df.to_csv(metrics_path, index=False)
    print(f"Saved: {metrics_path}")

    headline_path = PHASE_DIR / "sentiment_trajectories.png"
    plot_headline(df, headline_path)
    print(f"Saved: {headline_path}")

    per_pair_path = PHASE_DIR / "per_pair.png"
    plot_per_pair(df, per_pair_path)
    print(f"Saved: {per_pair_path}")

    summary = yoy_summary(df)
    summary_path = PHASE_DIR / "yoy_summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Saved: {summary_path}")

    print("\n=== Per-pair sentiment deltas (failure vs survivor) ===")
    print(summary[["pair", "role", "ticker", "neg_ratio_delta_pp",
                   "lit_ratio_delta_pp", "netneg_delta_pp", "size_pct_growth"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
