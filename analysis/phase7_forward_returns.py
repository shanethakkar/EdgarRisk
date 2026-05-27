"""
phase7_forward_returns.py
Phase 7: forward-returns backtest. Does the Phase 6 Distress Score
predict subsequent stock-price underperformance, not just bankruptcy?

For each of the 102 observations in Phase 6, fetch the subject ticker's
price history from yfinance and compute forward total returns at 12-,
24-, and 36-month horizons starting from a standardized reference
date (April 1 of `event_fy + 1`, approximating when the relevant 10-K
became publicly available).

If the score correlates with negative forward returns (controlled for
sector + size), the project becomes investment-relevant. If not, the
honest conclusion is that the signal is a bankruptcy detector, not an
investable predictor.

Outputs:
    outputs/phase7_forward_returns/returns_table.csv
    outputs/phase7_forward_returns/score_vs_return.png
    outputs/phase7_forward_returns/decile_returns.png
    outputs/phase7_forward_returns/regression.txt
"""

from datetime import datetime, timedelta
from pathlib import Path
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import LinearRegression

warnings.filterwarnings("ignore", category=FutureWarning)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHASE_DIR = PROJECT_ROOT / "outputs" / "phase7_forward_returns"
PHASE_DIR.mkdir(parents=True, exist_ok=True)

SCORED_CSV = PROJECT_ROOT / "outputs" / "phase6_distress_score" / "scored.csv"

# Reference date = April 1 of (event_fy + 1) -- approximates when the
# event-year 10-K was publicly filed and the score would be knowable.
REFERENCE_MONTH = 4

# Map each cohort's failure ticker to its event_fy (same as phase3_scale.py)
EVENT_FY = {
    "BA": 2018, "SIVB": 2022, "PTON": 2022, "SI": 2021, "SAVE": 2023,
    "SHLD": 2017, "JCP": 2019, "PIR": 2019, "ASNA": 2019, "BBBY": 2022,
    "WE": 2022, "YELL": 2022, "TUP": 2022,
    "EXPR": 2022, "RAD": 2022, "NKLA": 2023, "RIDE": 2022, "FSR": 2022,
    "CHK": 2019, "WLL": 2019, "ENDP": 2021, "MNK": 2019, "SDC": 2022, "HTZ": 2019,
}

# Tickers that need a yfinance symbol different from our internal label
TICKER_ALIASES = {
    "SIVB": "SIVBQ",       # SVB Financial post-Ch.11
    "SI":   "SICP",        # Silvergate (sometimes SI is Banco Latinoamericano)
    "BBBY": "BBBYQ",
    "JCP":  "JCPNQ",
    "SHLD": "SHLDQ",
    "PIR":  "PIRRQ",
    "ASNA": "ASNAQ",
    "RAD":  "RADCQ",
    "FSR":  "FSRNQ",
    "WLL":  "WLDNQ",       # Whiting post-restructuring; symbol changed
    "MNK":  "MNKKQ",
    "SDC":  "SDCCQ",
    "ENDP": "NDOI",        # Endo's post-reorg entity
    "EXPR": "EXPRQ",
    "WE":   "WEWKQ",
    "YELL": "YELLQ",
    "TUP":  "TUPBQ",
    "PIR":  "PIRRQ",
    "ASNA": "ASNAQ",
    "SAVE": "FLYYQ",       # Spirit post-Ch.11
}

FORWARD_HORIZONS = [12, 24, 36]


def reference_date(event_fy: int) -> datetime:
    return datetime(event_fy + 1, REFERENCE_MONTH, 1)


def fetch_price_history(ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Try original ticker first; fall back to known alias."""
    for sym in [ticker, TICKER_ALIASES.get(ticker)]:
        if sym is None:
            continue
        try:
            hist = yf.download(
                sym,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
                threads=False,
            )
            if hist is not None and not hist.empty:
                return hist
        except Exception:
            continue
    return pd.DataFrame()


def price_at_or_after(hist: pd.DataFrame, target: datetime, tol_days: int = 14):
    """Return the first close price at or after `target` within `tol_days`. None if none."""
    target_ts = pd.Timestamp(target)
    after = hist[hist.index >= target_ts]
    if after.empty:
        return None, None
    first_row = after.iloc[0]
    gap = (first_row.name - target_ts).days
    if gap > tol_days:
        return None, None
    close_val = first_row["Close"]
    if hasattr(close_val, "iloc"):
        close_val = close_val.iloc[0]
    return float(close_val), first_row.name.to_pydatetime()


def fetch_returns(ticker: str, event_fy: int) -> dict:
    ref_date = reference_date(event_fy)
    # Pad window so we can find a near-reference-date price
    start = ref_date - timedelta(days=30)
    end = ref_date + timedelta(days=365 * max(FORWARD_HORIZONS) / 12 + 60)

    hist = fetch_price_history(ticker, start, end)
    if hist.empty:
        return {"data_found": False}

    # Reference price = first close on/after ref_date (within ~2 weeks)
    ref_price, ref_actual = price_at_or_after(hist, ref_date, tol_days=21)
    if ref_price is None:
        return {"data_found": False, "reason": "no ref price"}

    out = {"data_found": True, "ref_price": ref_price, "ref_date": ref_actual.date().isoformat()}
    for months in FORWARD_HORIZONS:
        target = ref_date + timedelta(days=int(365.25 * months / 12))
        target_price, target_actual = price_at_or_after(hist, target, tol_days=21)
        if target_price is None:
            # Fall back to last available price (delisted before horizon)
            last_close_raw = hist["Close"].iloc[-1]
            if hasattr(last_close_raw, "iloc"):
                last_close_raw = last_close_raw.iloc[0]
            last_close = float(last_close_raw)
            last_date = hist.index[-1].to_pydatetime()
            # Only count if last_date is reasonably within the horizon window
            if last_date < ref_date:
                out[f"fwd_{months}m_return"] = np.nan
                out[f"fwd_{months}m_status"] = "no data"
            else:
                ret = (last_close - ref_price) / ref_price
                out[f"fwd_{months}m_return"] = ret
                out[f"fwd_{months}m_status"] = f"delisted_last_{last_date.date().isoformat()}"
        else:
            ret = (target_price - ref_price) / ref_price
            out[f"fwd_{months}m_return"] = ret
            out[f"fwd_{months}m_status"] = "ok"
    return out


def fetch_spy_return(event_fy: int, months: int) -> float:
    """Market benchmark return over the same window."""
    ref_date = reference_date(event_fy)
    start = ref_date - timedelta(days=30)
    end = ref_date + timedelta(days=int(365.25 * months / 12) + 60)
    hist = fetch_price_history("SPY", start, end)
    if hist.empty:
        return np.nan
    ref_price, _ = price_at_or_after(hist, ref_date, tol_days=21)
    target_date = ref_date + timedelta(days=int(365.25 * months / 12))
    target_price, _ = price_at_or_after(hist, target_date, tol_days=21)
    if ref_price is None or target_price is None:
        return np.nan
    return (target_price - ref_price) / ref_price


def main() -> None:
    scored = pd.read_csv(SCORED_CSV)
    print(f"Loaded {len(scored)} scored observations")

    # Each row gets a reference date from its cohort's event_fy
    scored["event_fy"] = scored["cohort_of"].map(EVENT_FY)
    if scored["event_fy"].isna().any():
        missing = scored[scored.event_fy.isna()].cohort_of.unique()
        raise ValueError(f"Missing event_fy mapping for: {missing}")
    scored["event_fy"] = scored["event_fy"].astype(int)
    scored["reference_date"] = scored["event_fy"].apply(
        lambda fy: reference_date(fy).date().isoformat()
    )

    # Pre-fetch SPY benchmark returns per event_fy (much fewer calls)
    print("Fetching SPY benchmark returns per event_fy...")
    unique_fys = sorted(scored.event_fy.unique())
    spy_returns = {}
    for fy in unique_fys:
        spy_returns[fy] = {h: fetch_spy_return(int(fy), h) for h in FORWARD_HORIZONS}
        print(f"  FY{fy}: 12m={spy_returns[fy][12]*100:+.1f}%, "
              f"24m={spy_returns[fy][24]*100:+.1f}%, 36m={spy_returns[fy][36]*100:+.1f}%")

    print(f"\nFetching forward returns for {len(scored)} observations...")
    fetched_rows = []
    for i, r in scored.iterrows():
        res = fetch_returns(r.subject, int(r.event_fy))
        # Add market-adjusted returns
        for h in FORWARD_HORIZONS:
            ret = res.get(f"fwd_{h}m_return")
            spy = spy_returns[int(r.event_fy)][h]
            if ret is not None and not (isinstance(ret, float) and np.isnan(ret)) and not np.isnan(spy):
                res[f"fwd_{h}m_excess"] = ret - spy
            else:
                res[f"fwd_{h}m_excess"] = np.nan
        fetched_rows.append(res)
        if (i + 1) % 20 == 0:
            print(f"  ...{i + 1}/{len(scored)}")

    returns_df = pd.DataFrame(fetched_rows)
    enriched = pd.concat([scored.reset_index(drop=True), returns_df], axis=1)
    enriched.to_csv(PHASE_DIR / "returns_table.csv", index=False)
    print(f"Saved: {PHASE_DIR / 'returns_table.csv'}")

    found = enriched.data_found.sum()
    print(f"\nData coverage: {int(found)}/{len(enriched)} observations have price data "
          f"({found/len(enriched)*100:.0f}%)")

    for h in FORWARD_HORIZONS:
        col = f"fwd_{h}m_return"
        valid = enriched[col].dropna()
        print(f"  {h}m return: n={len(valid)}, mean={valid.mean()*100:+.1f}%, median={valid.median()*100:+.1f}%")

    # Regression analysis: 12m / 24m / 36m on RAW and EXCESS (vs SPY) returns
    from scipy import stats
    regression_lines = ["=== Distress Score vs Forward Returns ==="]
    for horizon in FORWARD_HORIZONS:
        for label, col in [("raw", f"fwd_{horizon}m_return"),
                           ("vs SPY", f"fwd_{horizon}m_excess")]:
            sub = enriched.dropna(subset=[col]).copy()
            if len(sub) < 10:
                continue
            slope, intercept, r_value, p_value, std_err = stats.linregress(
                sub.distress_score, sub[col]
            )
            spear, spear_p = stats.spearmanr(sub.distress_score, sub[col])
            regression_lines.append(
                f"\n{horizon}m {label}:  n={len(sub)}  "
                f"Pearson r={r_value:+.3f} (p={p_value:.3f})  "
                f"Spearman rho={spear:+.3f} (p={spear_p:.3f})"
            )
            regression_lines.append(
                f"  slope = {slope:+.5f} ({slope*10*100:+.1f}pp per 10 score points)"
            )

    # Primary analysis: use 12m excess return as the main result
    analysis = enriched.dropna(subset=["fwd_12m_excess"]).copy()
    if len(analysis) >= 10:
        slope, intercept, r_value, p_value, std_err = stats.linregress(
            analysis.distress_score, analysis.fwd_12m_excess
        )

    (PHASE_DIR / "regression.txt").write_text("\n".join(regression_lines))
    print("\n" + "\n".join(regression_lines))

    # Decile analysis (using market-adjusted returns)
    decile_lines = ["\n=== Quintile analysis (12m market-adjusted forward return) ==="]
    analysis["score_quintile"] = pd.qcut(analysis.distress_score, q=5, labels=False, duplicates="drop")
    for q in sorted(analysis.score_quintile.dropna().unique()):
        sub = analysis[analysis.score_quintile == q]
        decile_lines.append(
            f"  Quintile {int(q)+1}: n={len(sub):3d}, score [{sub.distress_score.min():.0f}-{sub.distress_score.max():.0f}], "
            f"mean excess = {sub.fwd_12m_excess.mean()*100:+.1f}%, "
            f"median excess = {sub.fwd_12m_excess.median()*100:+.1f}%"
        )
    print("\n".join(decile_lines))

    # Plots
    plot_score_vs_return(analysis, PHASE_DIR / "score_vs_return.png", "fwd_12m_excess",
                          "Forward 12-month excess return vs SPY (%)")
    plot_decile_returns(analysis, PHASE_DIR / "decile_returns.png", "fwd_12m_excess",
                         "Mean forward 12m EXCESS return (vs SPY) by Distress Score quintile")
    print(f"\nSaved: {PHASE_DIR / 'score_vs_return.png'}")
    print(f"Saved: {PHASE_DIR / 'decile_returns.png'}")


def plot_score_vs_return(df: pd.DataFrame, out_path: Path,
                          y_col: str, y_label: str) -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    colors = []
    for _, r in df.iterrows():
        if r.is_failure_strict == 1:
            colors.append("#c0392b")
        elif r.is_failure_extended == 1:
            colors.append("#e67e22")
        else:
            colors.append("#27ae60")
    ax.scatter(df.distress_score, df[y_col] * 100, c=colors, alpha=0.7, s=60, edgecolor="black", linewidth=0.5)

    from scipy import stats
    slope, intercept, r_value, p_value, _ = stats.linregress(df.distress_score, df[y_col])
    spear, spear_p = stats.spearmanr(df.distress_score, df[y_col])
    xs = np.linspace(df.distress_score.min(), df.distress_score.max(), 50)
    ax.plot(xs, (slope * xs + intercept) * 100, "k--", alpha=0.6,
            label=f"linear fit (slope={slope*100:+.3f}pp / score-pt, p={p_value:.3f})")
    ax.axhline(0, color="grey", alpha=0.3)
    ax.set_xlabel("Distress score (0-100)")
    ax.set_ylabel(y_label)
    ax.set_title(f"Does Distress Score predict forward returns?\n"
                 f"n={len(df)} | Pearson r={r_value:+.3f} | Spearman ρ={spear:+.3f} (p={spear_p:.3f})",
                 fontsize=11)
    ax.legend(loc="lower left")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_decile_returns(df: pd.DataFrame, out_path: Path,
                         y_col: str, title: str) -> None:
    quintile_summary = (
        df.groupby("score_quintile")
        .agg(mean_return=(y_col, "mean"),
             median_return=(y_col, "median"),
             n=(y_col, "count"),
             score_min=("distress_score", "min"),
             score_max=("distress_score", "max"))
        .reset_index()
    )
    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = quintile_summary.score_quintile + 1
    colors = ["#27ae60", "#7fb069", "#f4d35e", "#e07a5f", "#c0392b"][:len(x)]
    bars = ax.bar(x, quintile_summary.mean_return * 100, color=colors, alpha=0.85)
    ax.axhline(0, color="black", alpha=0.5)
    ax.set_xlabel("Distress score quintile (1=lowest, 5=highest)")
    ax.set_ylabel("Mean forward 12m return (%)")
    ax.set_title(title, fontsize=11)
    ax.set_xticks(x)
    labels = [f"Q{int(q+1)}\n[{int(qmin)}-{int(qmax)}]\nn={int(n)}"
              for q, qmin, qmax, n in zip(quintile_summary.score_quintile,
                                          quintile_summary.score_min,
                                          quintile_summary.score_max,
                                          quintile_summary.n)]
    ax.set_xticklabels(labels)
    for bar, val in zip(bars, quintile_summary.mean_return):
        ax.text(bar.get_x() + bar.get_width()/2, val * 100 + (1 if val > 0 else -3),
                f"{val*100:+.1f}%", ha="center", fontsize=10, fontweight="bold")
    ax.grid(alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
