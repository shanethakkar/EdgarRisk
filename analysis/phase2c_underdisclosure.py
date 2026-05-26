"""
phase2c_underdisclosure.py
Phase 2C: complementary under-disclosure detector.

Phase 2A/2B established that YoY novelty in 10-K Risk Factors catches
"deterioration via expanding disclosure" failures (7/7 hit rate). It
misses the class where management refused to update language pre-event
(JCP, SAVE).

This module defines and applies a complementary signal: novelty rank
DECLINED across the lookback window, ending in the bottom of the
cohort. Pattern: the company became MORE static as failure approached,
even while peers were updating their own disclosures.

Signal definition (under_disclosure_fires):
    1. Failure's novelty percentile at t=0 is <= 0.30 (bottom of cohort)
    2. AND the failure's novelty percentile at t=0 is strictly less
       than its percentile at the earliest measurable year in the
       lookback (downward trajectory)
    3. AND the cohort had at least one peer year with raw novelty > 0.10
       (i.e., the cohort wasn't uniformly quiet -- there was something
       to update against)

Unified detection: novelty_spike (Phase 2A/2B) OR under_disclosure.

Applied to all 13 failures across Phase 1C/1D/2A/2B.

Outputs:
    outputs/phase2c_unified_scoreboard.png -- combined detection across
                                              all 13 failures
    outputs/phase2c_underdisclosure_metrics.csv
    outputs/phase2c_unified_summary.csv
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PHASE_DIR = PROJECT_ROOT / "outputs" / "phase2c_underdisclosure"
PHASE_DIR.mkdir(parents=True, exist_ok=True)

# Failure -> cohort + lookback definitions, harmonized across all phases.
ALL_FAILURES = [
    # Phase 1C/1D: development set
    {"failure": "BA",   "event_fy": 2018, "lookback": [2015, 2016, 2017, 2018],
     "survivors": ["LMT", "GD", "NOC"],
     "sector": "Aerospace/Defense", "class_hint": "industry shock"},
    {"failure": "SIVB", "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
     "survivors": ["KEY", "FITB", "HBAN"],
     "sector": "Mid-cap commercial bank", "class_hint": "sudden shock"},
    {"failure": "PTON", "event_fy": 2022, "lookback": [2020, 2021, 2022],
     "survivors": ["GRMN", "LULU", "ROK"],
     "sector": "D2C consumer subscription", "class_hint": "chronic anomaly"},
    {"failure": "SI",   "event_fy": 2021, "lookback": [2019, 2020, 2021],
     "survivors": ["WAL", "CUBI", "KEY"],
     "sector": "Small-cap regional bank", "class_hint": "sudden shock"},
    {"failure": "SAVE", "event_fy": 2023, "lookback": [2020, 2021, 2022, 2023],
     "survivors": ["ULCC", "ALK", "LUV"],
     "sector": "ULCC airline", "class_hint": "under-disclosure"},
    # Phase 2A: retail
    {"failure": "SHLD", "event_fy": 2017, "lookback": [2014, 2015, 2016, 2017],
     "survivors": ["BBY", "M", "KSS", "JWN", "WSM"],
     "sector": "Dept store retail", "class_hint": "expanding disclosure"},
    {"failure": "JCP",  "event_fy": 2019, "lookback": [2016, 2017, 2018, 2019],
     "survivors": ["BBY", "M", "KSS", "JWN", "WSM"],
     "sector": "Dept store retail", "class_hint": "under-disclosure"},
    {"failure": "PIR",  "event_fy": 2019, "lookback": [2016, 2017, 2018, 2019],
     "survivors": ["BBY", "M", "KSS", "JWN", "WSM"],
     "sector": "Home goods specialty retail", "class_hint": "expanding disclosure"},
    {"failure": "ASNA", "event_fy": 2019, "lookback": [2016, 2017, 2018, 2019],
     "survivors": ["BBY", "M", "KSS", "JWN", "WSM"],
     "sector": "Specialty retail", "class_hint": "expanding disclosure"},
    {"failure": "BBBY", "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
     "survivors": ["BBY", "M", "KSS", "JWN", "WSM"],
     "sector": "Specialty retail", "class_hint": "expanding disclosure"},
    # Phase 2B: industrial
    {"failure": "WE",   "event_fy": 2022, "lookback": [2020, 2021, 2022],
     "survivors": ["CWK", "NMRK", "IRM"],
     "sector": "Commercial real estate / coworking", "class_hint": "expanding disclosure"},
    {"failure": "YELL", "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
     "survivors": ["ODFL", "ARCB", "XPO"],
     "sector": "LTL trucking", "class_hint": "expanding disclosure"},
    {"failure": "TUP",  "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
     "survivors": ["CHD", "CL", "CLX"],
     "sector": "Household consumer products", "class_hint": "expanding disclosure"},
]

NOVELTY_SPIKE_THRESHOLD = 0.75  # max percentile in window
NOVELTY_SPIKE_RAW_FLOOR = 0.10  # failure's own raw novelty must have been substantive
UNDER_DISCLOSURE_BOTTOM = 0.34  # bottom-third of cohort at t=0
UNDER_DISCLOSURE_DROP = 0.20    # rank must have declined by >= 0.20pp
COHORT_ACTIVITY_GATE = 0.10     # minimum raw novelty SOMEWHERE in cohort


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
            "risk_chars": entry["risk_factors_chars"],
            "novelty": nov.get("novelty"),
        })
    return pd.DataFrame(rows).sort_values("fiscal_year").reset_index(drop=True)


def percentile_rank(value, distribution) -> float:
    arr = np.asarray([v for v in distribution if v is not None and not np.isnan(v)])
    if arr.size == 0:
        return np.nan
    return float((arr <= value).sum()) / arr.size


def evaluate_failure(case: dict, df: pd.DataFrame) -> dict:
    cohort_tickers = [case["failure"]] + case["survivors"]
    failure = case["failure"]

    novelty_path = []
    cohort_raw_novelty_max_in_window = 0.0
    for fy in case["lookback"]:
        year_df = df[(df.ticker.isin(cohort_tickers)) & (df.fiscal_year == fy)]
        if year_df.empty or failure not in year_df.ticker.values:
            continue
        f_nov = year_df.loc[year_df.ticker == failure, "novelty"].iloc[0]
        if f_nov is None or (isinstance(f_nov, float) and np.isnan(f_nov)):
            continue
        dist = year_df["novelty"].dropna().tolist()
        if not dist:
            continue
        rank = percentile_rank(f_nov, dist)
        cohort_year_max_raw = max([v for v in dist if v is not None and not np.isnan(v)])
        cohort_raw_novelty_max_in_window = max(cohort_raw_novelty_max_in_window, cohort_year_max_raw)
        novelty_path.append({"fy": fy, "years_to_event": fy - case["event_fy"],
                             "raw_novelty": f_nov, "pct_rank": rank,
                             "cohort_year_max_raw": cohort_year_max_raw})

    if not novelty_path:
        return {"failure": failure, "novelty_spike_signal": False,
                "under_disclosure_signal": False, "detected": False,
                "novelty_max_rank": np.nan, "t0_rank": np.nan,
                "first_rank": np.nan, "cohort_max_raw_in_window": np.nan,
                "class_hint": case["class_hint"]}

    ranks = [p["pct_rank"] for p in novelty_path]
    raws = [p["raw_novelty"] for p in novelty_path]
    max_rank = max(ranks)
    first_rank = ranks[0]
    t0 = novelty_path[-1]
    t0_rank = t0["pct_rank"]
    failure_max_raw = max(raws)

    novelty_spike = (max_rank >= NOVELTY_SPIKE_THRESHOLD
                     and failure_max_raw >= NOVELTY_SPIKE_RAW_FLOOR)
    under_disclosure = (
        t0_rank <= UNDER_DISCLOSURE_BOTTOM
        and (first_rank - t0_rank) >= UNDER_DISCLOSURE_DROP
        and cohort_raw_novelty_max_in_window >= COHORT_ACTIVITY_GATE
    )
    detected = novelty_spike or under_disclosure

    return {
        "failure": failure,
        "sector": case["sector"],
        "class_hint": case["class_hint"],
        "novelty_max_rank": round(max_rank, 2),
        "first_rank": round(first_rank, 2),
        "t0_rank": round(t0_rank, 2),
        "cohort_max_raw_in_window": round(cohort_raw_novelty_max_in_window, 3),
        "novelty_spike_signal": novelty_spike,
        "under_disclosure_signal": under_disclosure,
        "detected": detected,
    }


def plot_unified_scoreboard(results: pd.DataFrame, out_path: Path) -> None:
    """Each row is a failure. Two columns: novelty_spike, under_disclosure.
    Color = green (signal fired), red (silent). Border around fully-detected."""
    fig, ax = plt.subplots(figsize=(11, 7.0))
    matrix = results[["novelty_spike_signal", "under_disclosure_signal"]].astype(int).values
    n = len(results)
    ax.imshow(matrix, cmap="RdYlGn", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Novelty spike (expanding\ndisclosure pattern)",
                        "Under-disclosure (static\ntext + sector active)"],
                       fontsize=10)
    ax.set_yticks(range(n))
    ax.set_yticklabels(
        [f"{r.failure}  ({r['class_hint']})" for _, r in results.iterrows()],
        fontsize=9,
    )
    ax.set_title("Unified signal scoreboard: novelty-spike OR under-disclosure (n=13)",
                 fontsize=12)
    for i in range(n):
        for j in range(2):
            v = matrix[i, j]
            label = "FIRED" if v else "quiet"
            ax.text(j, i, label, ha="center", va="center",
                    color="white" if v else "black",
                    fontsize=11, fontweight="bold")

    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    all_tickers = sorted({c["failure"] for c in ALL_FAILURES}
                         | {s for c in ALL_FAILURES for s in c["survivors"]})
    df = pd.concat([load_company(t) for t in all_tickers], ignore_index=True)

    rows = [evaluate_failure(c, df) for c in ALL_FAILURES]
    results = pd.DataFrame(rows)

    metrics_path = PHASE_DIR / "metrics.csv"
    results.to_csv(metrics_path, index=False)
    print(f"Saved: {metrics_path}")

    scoreboard_path = PHASE_DIR / "unified_scoreboard.png"
    plot_unified_scoreboard(results, scoreboard_path)
    print(f"Saved: {scoreboard_path}")

    print("\n=== Per-failure detection ===")
    show = results[["failure", "sector", "class_hint",
                    "first_rank", "novelty_max_rank", "t0_rank",
                    "cohort_max_raw_in_window",
                    "novelty_spike_signal", "under_disclosure_signal", "detected"]]
    print(show.to_string(index=False))

    n_total = len(results)
    by_spike = int(results["novelty_spike_signal"].sum())
    by_ud = int(results["under_disclosure_signal"].sum())
    by_either = int(results["detected"].sum())
    print(f"\nNovelty-spike detection:     {by_spike}/{n_total} ({by_spike/n_total*100:.0f}%)")
    print(f"Under-disclosure detection:  {by_ud}/{n_total} ({by_ud/n_total*100:.0f}%)")
    print(f"Either signal detected:      {by_either}/{n_total} ({by_either/n_total*100:.0f}%)")

    print("\n=== By class_hint ===")
    cl = results.groupby("class_hint").agg(
        n=("failure", "count"),
        spike=("novelty_spike_signal", "sum"),
        ud=("under_disclosure_signal", "sum"),
        either=("detected", "sum"),
    ).reset_index()
    print(cl.to_string(index=False))


if __name__ == "__main__":
    main()
