"""
phase0_validation.py
Phase 0 minimum-viable-validation: does disclosure language differ between
companies that subsequently failed and matched survivors?

Loads parsed JSON + redflag JSON for 5 failure / 5 survivor pairs, builds a
long-form metrics table, and renders a side-by-side comparison chart.

Outputs:
    outputs/phase0_metrics.csv
    outputs/phase0_comparison.png
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

PAIRS = [
    {"failure": "BA",   "survivor": "LMT",  "event": "Boeing 737 MAX crisis (Oct 2018)",      "event_fy": 2018, "lookback": [2017, 2018]},
    {"failure": "SIVB", "survivor": "JPM",  "event": "SVB collapse (Mar 2023)",                "event_fy": 2022, "lookback": [2020, 2021, 2022]},
    {"failure": "BBBY", "survivor": "BBY",  "event": "Bed Bath & Beyond Ch.11 (Apr 2023)",     "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022]},
    {"failure": "PTON", "survivor": "GRMN", "event": "Peloton mass drawdown (FY2022)",         "event_fy": 2022, "lookback": [2022, 2023, 2024]},
    {"failure": "SI",   "survivor": "JPM",  "event": "Silvergate voluntary wind-down (Mar 23)","event_fy": 2021, "lookback": [2019, 2020, 2021]},
]

HIGH_SEVERITY_CATS = {"going_concern", "restatement", "regulatory_investigation", "auditor_concerns"}


def load_metrics(ticker: str) -> pd.DataFrame:
    summary_path = PROCESSED_DIR / f"{ticker}_parsed_summary.json"
    redflags_path = PROCESSED_DIR / f"{ticker}_redflags.json"
    summary = json.loads(summary_path.read_text())
    redflags = json.loads(redflags_path.read_text())

    rows = []
    for entry in summary:
        fy = entry["fiscal_year"]
        rf = redflags.get(fy, {})
        total_rf = sum(v["count"] for v in rf.values())
        n_cats = len(rf)
        high_sev = sum(v["count"] for k, v in rf.items() if k in HIGH_SEVERITY_CATS)
        rows.append({
            "ticker": ticker,
            "fiscal_year": int(fy),
            "risk_chars": entry["risk_factors_chars"],
            "risk_count": entry["risk_factors_count"],
            "mdna_chars": entry["mdna_chars"],
            "redflag_total": total_rf,
            "redflag_categories": n_cats,
            "high_severity_redflags": high_sev,
        })
    return pd.DataFrame(rows).sort_values("fiscal_year").reset_index(drop=True)


def build_long_table() -> pd.DataFrame:
    all_tickers = set()
    for p in PAIRS:
        all_tickers.add(p["failure"])
        all_tickers.add(p["survivor"])

    frames = [load_metrics(t) for t in sorted(all_tickers)]
    df = pd.concat(frames, ignore_index=True)

    # Tag each row's group (failure / survivor) per pair it belongs to.
    # JPM is used as survivor twice (SIVB, SI), so we tag by ticker only.
    failure_tickers = {p["failure"] for p in PAIRS}
    df["group"] = df["ticker"].apply(lambda t: "failure" if t in failure_tickers else "survivor")
    return df


def plot_comparison(df: pd.DataFrame, out_path: Path) -> None:
    fig, axes = plt.subplots(len(PAIRS), 2, figsize=(13, 3.0 * len(PAIRS)))
    if len(PAIRS) == 1:
        axes = [axes]

    for i, pair in enumerate(PAIRS):
        years = pair["lookback"]
        f_df = df[(df.ticker == pair["failure"]) & (df.fiscal_year.isin(years))].sort_values("fiscal_year")
        s_df = df[(df.ticker == pair["survivor"]) & (df.fiscal_year.isin(years))].sort_values("fiscal_year")

        ax1 = axes[i][0]
        ax1.plot(f_df.fiscal_year, f_df.risk_chars / 1000, marker="o", color="#c0392b", label=f"{pair['failure']} (failure)", linewidth=2)
        ax1.plot(s_df.fiscal_year, s_df.risk_chars / 1000, marker="s", color="#27ae60", label=f"{pair['survivor']} (survivor)", linewidth=2)
        ax1.set_title(f"Risk Factor Section Size (KB)\n{pair['event']}", fontsize=10)
        ax1.set_xlabel("Fiscal Year")
        ax1.set_ylabel("Section length (1000 chars)")
        ax1.legend(fontsize=8)
        ax1.grid(alpha=0.3)
        for fy in f_df.fiscal_year:
            if fy == pair["event_fy"]:
                ax1.axvline(fy, color="#c0392b", linestyle="--", alpha=0.3)

        ax2 = axes[i][1]
        f_total = f_df.redflag_total.values
        s_total = s_df.redflag_total.values
        x = list(f_df.fiscal_year)
        width = 0.35
        x_pos = range(len(x))
        ax2.bar([p - width/2 for p in x_pos], f_total, width, color="#c0392b", label=f"{pair['failure']}", alpha=0.85)
        ax2.bar([p + width/2 for p in x_pos], s_total[:len(x)] if len(s_total) >= len(x) else list(s_total) + [0]*(len(x)-len(s_total)), width, color="#27ae60", label=f"{pair['survivor']}", alpha=0.85)
        ax2.set_xticks(x_pos)
        ax2.set_xticklabels(x)
        ax2.set_title(f"Red-flag occurrences (total)\n{pair['event']}", fontsize=10)
        ax2.set_xlabel("Fiscal Year")
        ax2.set_ylabel("Total red-flag hits")
        ax2.legend(fontsize=8)
        ax2.grid(alpha=0.3, axis="y")

    plt.tight_layout()
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def yoy_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per pair: % growth in risk_chars over lookback window, failure vs survivor."""
    rows = []
    for pair in PAIRS:
        years = pair["lookback"]
        for role, t in [("failure", pair["failure"]), ("survivor", pair["survivor"])]:
            sub = df[(df.ticker == t) & (df.fiscal_year.isin(years))].sort_values("fiscal_year")
            if len(sub) < 2:
                continue
            first, last = sub.iloc[0], sub.iloc[-1]
            pct = (last.risk_chars - first.risk_chars) / first.risk_chars * 100
            redflag_delta = int(last.redflag_total - first.redflag_total)
            rows.append({
                "pair": f"{pair['failure']} vs {pair['survivor']}",
                "role": role,
                "ticker": t,
                "fy_start": int(first.fiscal_year),
                "fy_end": int(last.fiscal_year),
                "risk_chars_start": int(first.risk_chars),
                "risk_chars_end": int(last.risk_chars),
                "risk_chars_pct_growth": round(pct, 1),
                "redflag_start": int(first.redflag_total),
                "redflag_end": int(last.redflag_total),
                "redflag_delta": redflag_delta,
            })
    return pd.DataFrame(rows)


def main() -> None:
    df = build_long_table()
    metrics_path = OUTPUTS_DIR / "phase0_metrics.csv"
    df.to_csv(metrics_path, index=False)
    print(f"Saved long metrics table: {metrics_path}")

    chart_path = OUTPUTS_DIR / "phase0_comparison.png"
    plot_comparison(df, chart_path)
    print(f"Saved comparison chart: {chart_path}")

    summary = yoy_summary(df)
    summary_path = OUTPUTS_DIR / "phase0_yoy_summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Saved YoY summary: {summary_path}")

    print("\n=== Pre-event disclosure growth (failure vs survivor) ===")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
