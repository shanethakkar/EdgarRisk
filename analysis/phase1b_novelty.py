"""
phase1b_novelty.py
Phase 1B: combine the three text signals (disclosure volume, LM sentiment,
YoY novelty) into a single per-company per-year scorecard, and surface
which signals fire for each failure vs its survivor pair.

Produces:
    outputs/phase1b_per_pair.png   -- 5 pairs x 3 panels (size / negative
                                      sentiment / novelty), with the
                                      "novelty" panel being the new
                                      Phase 1B contribution
    outputs/phase1b_scoreboard.png -- the "did this signal fire?"
                                      summary visualization
    outputs/phase1b_metrics.csv    -- full per-company per-year table
    outputs/phase1b_scorecard.csv  -- one row per failure-survivor pair,
                                      one column per signal
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PHASE_DIR = PROJECT_ROOT / "outputs" / "phase1b_novelty"
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
            "netneg_ratio": sent.get("NetNegative_ratio", 0.0),
            "novelty": nov.get("novelty"),
        })
    return pd.DataFrame(rows).sort_values("fiscal_year").reset_index(drop=True)


def build_long_table() -> pd.DataFrame:
    tickers = sorted({p["failure"] for p in PAIRS} | {p["survivor"] for p in PAIRS})
    df = pd.concat([load_company(t) for t in tickers], ignore_index=True)
    df["group"] = df["ticker"].apply(lambda t: "failure" if t in FAILURE_TICKERS else "survivor")
    return df


def per_pair_panels(df: pd.DataFrame, out_path: Path) -> None:
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
        ax.grid(alpha=0.3); ax.legend(fontsize=8)
        ax.set_xlabel("FY"); ax.set_ylabel("1000 chars")

        ax = axes[i][1]
        ax.plot(f_df.fiscal_year, f_df.neg_ratio * 100, "o-", color="#c0392b", linewidth=2, label=pair["failure"])
        ax.plot(s_df.fiscal_year, s_df.neg_ratio * 100, "s-", color="#27ae60", linewidth=2, label=pair["survivor"])
        ax.set_title(f"LM Negative-word ratio (%)\n{pair['event']}", fontsize=9)
        ax.grid(alpha=0.3); ax.legend(fontsize=8)
        ax.set_xlabel("FY"); ax.set_ylabel("Negative %")

        ax = axes[i][2]
        f_nov = f_df.dropna(subset=["novelty"])
        s_nov = s_df.dropna(subset=["novelty"])
        ax.plot(f_nov.fiscal_year, f_nov.novelty, "o-", color="#c0392b", linewidth=2, label=pair["failure"])
        ax.plot(s_nov.fiscal_year, s_nov.novelty, "s-", color="#27ae60", linewidth=2, label=pair["survivor"])
        ax.set_title(f"YoY text novelty (1 - cosine sim)\n{pair['event']}", fontsize=9)
        ax.grid(alpha=0.3); ax.legend(fontsize=8)
        ax.set_xlabel("FY"); ax.set_ylabel("novelty (0-1)")

    plt.tight_layout()
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def compute_scorecard(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pair in PAIRS:
        years = pair["lookback"]
        f = df[(df.ticker == pair["failure"]) & (df.fiscal_year.isin(years))].sort_values("fiscal_year")
        s = df[(df.ticker == pair["survivor"]) & (df.fiscal_year.isin(years))].sort_values("fiscal_year")
        if len(f) < 2 or len(s) < 2:
            continue

        size_growth_f = (f.risk_chars.iloc[-1] - f.risk_chars.iloc[0]) / f.risk_chars.iloc[0] * 100
        size_growth_s = (s.risk_chars.iloc[-1] - s.risk_chars.iloc[0]) / s.risk_chars.iloc[0] * 100
        neg_delta_f = (f.neg_ratio.iloc[-1] - f.neg_ratio.iloc[0]) * 100
        neg_delta_s = (s.neg_ratio.iloc[-1] - s.neg_ratio.iloc[0]) * 100
        novelty_max_f = f.novelty.dropna().max() if not f.novelty.dropna().empty else 0.0
        novelty_max_s = s.novelty.dropna().max() if not s.novelty.dropna().empty else 0.0

        # Signal definitions:
        # volume signal: failure size grew >20pp more than survivor
        # sentiment signal: failure neg_ratio grew >0.15pp more than survivor
        # novelty signal: failure peak novelty > 0.20 AND > 2x survivor's peak
        vol_signal = (size_growth_f - size_growth_s) > 20.0
        sent_signal = (neg_delta_f - neg_delta_s) > 0.15
        nov_signal = (novelty_max_f > 0.20) and (novelty_max_f > 2 * novelty_max_s)

        rows.append({
            "pair": f"{pair['failure']} vs {pair['survivor']}",
            "event": pair["event"],
            "failure_ticker": pair["failure"],
            "size_growth_F_pct": round(size_growth_f, 1),
            "size_growth_S_pct": round(size_growth_s, 1),
            "neg_delta_F_pp": round(neg_delta_f, 2),
            "neg_delta_S_pp": round(neg_delta_s, 2),
            "novelty_max_F": round(novelty_max_f, 3),
            "novelty_max_S": round(novelty_max_s, 3),
            "vol_signal": vol_signal,
            "sent_signal": sent_signal,
            "nov_signal": nov_signal,
            "signals_fired": int(vol_signal) + int(sent_signal) + int(nov_signal),
        })
    return pd.DataFrame(rows)


def plot_scoreboard(scorecard: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 4.5))

    signals = ["vol_signal", "sent_signal", "nov_signal"]
    labels = ["Volume Δ", "Sentiment Δ", "Novelty spike"]
    n_pairs = len(scorecard)

    matrix = scorecard[signals].astype(int).values
    pairs_labels = [f"{r.failure_ticker}\n{r.event[:30]}" for _, r in scorecard.iterrows()]

    ax.imshow(matrix, cmap="RdYlGn", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_yticks(range(n_pairs))
    ax.set_yticklabels(pairs_labels, fontsize=9)
    ax.set_title("Did this signal fire for the failure case?", fontsize=12)
    for i in range(n_pairs):
        for j in range(len(labels)):
            v = matrix[i, j]
            ax.text(j, i, "FIRED" if v else "quiet",
                    ha="center", va="center",
                    color="white" if v else "black", fontsize=10, fontweight="bold")

    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    df = build_long_table()
    metrics_path = PHASE_DIR / "metrics.csv"
    df.to_csv(metrics_path, index=False)
    print(f"Saved: {metrics_path}")

    per_pair_path = PHASE_DIR / "per_pair.png"
    per_pair_panels(df, per_pair_path)
    print(f"Saved: {per_pair_path}")

    scorecard = compute_scorecard(df)
    scorecard_path = PHASE_DIR / "scorecard.csv"
    scorecard.to_csv(scorecard_path, index=False)
    print(f"Saved: {scorecard_path}")

    scoreboard_path = PHASE_DIR / "scoreboard.png"
    plot_scoreboard(scorecard, scoreboard_path)
    print(f"Saved: {scoreboard_path}")

    print("\n=== Signal scorecard ===")
    display = scorecard[["failure_ticker", "size_growth_F_pct", "size_growth_S_pct",
                         "neg_delta_F_pp", "neg_delta_S_pp",
                         "novelty_max_F", "novelty_max_S",
                         "vol_signal", "sent_signal", "nov_signal", "signals_fired"]]
    print(display.to_string(index=False))


if __name__ == "__main__":
    main()
