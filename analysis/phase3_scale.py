"""
phase3_scale.py
Phase 3: scale-out to 24 corporate failures across 7 sectors. Apply
the locked Phase 2C unified detector (novelty-spike OR under-disclosure)
without modification.

If the methodology generalizes, the 9/9 detectable rate from Phase 2C
should hold at 22-24/24 (counting some chronic-anomaly / shock cases
that the model is expected to miss).

Sectors and cohorts:
    Specialty/dept retail (5):  BBY, M, KSS, JWN, WSM
    Aerospace/Defense (3):       LMT, GD, NOC
    Mid-cap commercial banks (3): KEY, FITB, HBAN
    Small-cap regional banks (3): WAL, CUBI, KEY
    D2C consumer subscription (3): GRMN, LULU, ROK
    ULCC airline (3):            ULCC, ALK, LUV
    Commercial real estate (3):  CWK, NMRK, IRM
    LTL trucking (3):            ODFL, ARCB, XPO
    Household consumer (3):      CHD, CL, CLX
    Drugstore (2):               CVS, WBA
    EV / cleantech (3):          LCID, RIVN, CHPT
    Energy E&P (3):              COP, DVN, HES
    Specialty pharma (3):        PFE, BMY, MRK
    Dental / consumer health (2): ALGN, HSIC
    Car rental / equipment (2):  CAR, URI

Outputs:
    outputs/phase3_final_scoreboard.png -- 24-failure unified scoreboard
    outputs/phase3_per_sector_summary.png -- detection rate by sector
    outputs/phase3_metrics.csv
    outputs/phase3_summary.csv
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PHASE_DIR = PROJECT_ROOT / "outputs" / "phase3_scale"
PHASE_DIR.mkdir(parents=True, exist_ok=True)

ALL_FAILURES = [
    # --- Phase 1C development set (5) ---
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
    # --- Phase 1D out-of-sample (1) ---
    {"failure": "SAVE", "event_fy": 2023, "lookback": [2020, 2021, 2022, 2023],
     "survivors": ["ULCC", "ALK", "LUV"],
     "sector": "ULCC airline", "class_hint": "under-disclosure"},
    # --- Phase 2A retail (4 new) ---
    {"failure": "SHLD", "event_fy": 2017, "lookback": [2014, 2015, 2016, 2017],
     "survivors": ["BBY", "M", "KSS", "JWN", "WSM"],
     "sector": "Dept store retail", "class_hint": "expanding disclosure"},
    {"failure": "JCP",  "event_fy": 2019, "lookback": [2016, 2017, 2018, 2019],
     "survivors": ["BBY", "M", "KSS", "JWN", "WSM"],
     "sector": "Dept store retail", "class_hint": "under-disclosure"},
    {"failure": "PIR",  "event_fy": 2019, "lookback": [2016, 2017, 2018, 2019],
     "survivors": ["BBY", "M", "KSS", "JWN", "WSM"],
     "sector": "Home goods specialty", "class_hint": "expanding disclosure"},
    {"failure": "ASNA", "event_fy": 2019, "lookback": [2016, 2017, 2018, 2019],
     "survivors": ["BBY", "M", "KSS", "JWN", "WSM"],
     "sector": "Specialty retail", "class_hint": "expanding disclosure"},
    {"failure": "BBBY", "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
     "survivors": ["BBY", "M", "KSS", "JWN", "WSM"],
     "sector": "Specialty retail", "class_hint": "expanding disclosure"},
    # --- Phase 2B industrial (3) ---
    {"failure": "WE",   "event_fy": 2022, "lookback": [2020, 2021, 2022],
     "survivors": ["CWK", "NMRK", "IRM"],
     "sector": "Commercial real estate", "class_hint": "expanding disclosure"},
    {"failure": "YELL", "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
     "survivors": ["ODFL", "ARCB", "XPO"],
     "sector": "LTL trucking", "class_hint": "expanding disclosure"},
    {"failure": "TUP",  "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
     "survivors": ["CHD", "CL", "CLX"],
     "sector": "Household consumer", "class_hint": "expanding disclosure"},
    # --- Phase 3 scale-out (11) ---
    {"failure": "EXPR", "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
     "survivors": ["BBY", "M", "KSS", "JWN", "WSM"],
     "sector": "Specialty apparel retail", "class_hint": "unknown"},
    {"failure": "RAD",  "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
     "survivors": ["CVS", "WBA"],
     "sector": "Drugstore", "class_hint": "unknown"},
    {"failure": "NKLA", "event_fy": 2023, "lookback": [2020, 2021, 2022, 2023],
     "survivors": ["LCID", "RIVN", "CHPT"],
     "sector": "EV / cleantech", "class_hint": "unknown"},
    {"failure": "RIDE", "event_fy": 2022, "lookback": [2020, 2021, 2022],
     "survivors": ["LCID", "RIVN", "CHPT"],
     "sector": "EV / cleantech", "class_hint": "unknown"},
    {"failure": "FSR",  "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
     "survivors": ["LCID", "RIVN", "CHPT"],
     "sector": "EV / cleantech", "class_hint": "unknown"},
    {"failure": "CHK",  "event_fy": 2019, "lookback": [2016, 2017, 2018, 2019],
     "survivors": ["COP", "DVN", "HES"],
     "sector": "Energy E&P", "class_hint": "unknown"},
    {"failure": "WLL",  "event_fy": 2019, "lookback": [2016, 2017, 2018, 2019],
     "survivors": ["COP", "DVN", "HES"],
     "sector": "Energy E&P", "class_hint": "unknown"},
    {"failure": "ENDP", "event_fy": 2021, "lookback": [2018, 2019, 2020, 2021],
     "survivors": ["PFE", "BMY", "MRK"],
     "sector": "Specialty pharma", "class_hint": "unknown"},
    {"failure": "MNK",  "event_fy": 2019, "lookback": [2016, 2017, 2018, 2019],
     "survivors": ["PFE", "BMY", "MRK"],
     "sector": "Specialty pharma", "class_hint": "unknown"},
    {"failure": "SDC",  "event_fy": 2022, "lookback": [2019, 2020, 2021, 2022],
     "survivors": ["ALGN", "HSIC"],
     "sector": "Dental / consumer health", "class_hint": "unknown"},
    {"failure": "HTZ",  "event_fy": 2019, "lookback": [2016, 2017, 2018, 2019],
     "survivors": ["CAR", "URI"],
     "sector": "Car rental / equipment", "class_hint": "unknown"},
]

NOVELTY_SPIKE_THRESHOLD = 0.75
NOVELTY_SPIKE_RAW_FLOOR = 0.10
UNDER_DISCLOSURE_BOTTOM = 0.34
UNDER_DISCLOSURE_DROP = 0.20
COHORT_ACTIVITY_GATE = 0.10


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


def evaluate_failure(case: dict, df: pd.DataFrame) -> dict:
    cohort_tickers = [case["failure"]] + case["survivors"]
    failure = case["failure"]

    path = []
    cohort_max_raw = 0.0
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
        year_max = max([v for v in dist if v is not None and not np.isnan(v)])
        cohort_max_raw = max(cohort_max_raw, year_max)
        path.append({"fy": fy, "raw": f_nov, "rank": rank})

    if not path:
        return {"failure": failure, "sector": case["sector"], "class_hint": case["class_hint"],
                "novelty_spike": False, "under_disclosure": False, "detected": False,
                "first_rank": np.nan, "max_rank": np.nan, "t0_rank": np.nan,
                "failure_max_raw": np.nan, "cohort_max_raw": np.nan,
                "n_lookback_years": 0}

    ranks = [p["rank"] for p in path]
    raws = [p["raw"] for p in path]
    first_rank = ranks[0]
    max_rank = max(ranks)
    t0_rank = ranks[-1]
    failure_max_raw = max(raws)

    novelty_spike = (max_rank >= NOVELTY_SPIKE_THRESHOLD
                     and failure_max_raw >= NOVELTY_SPIKE_RAW_FLOOR)
    under_disclosure = (
        t0_rank <= UNDER_DISCLOSURE_BOTTOM
        and (first_rank - t0_rank) >= UNDER_DISCLOSURE_DROP
        and cohort_max_raw >= COHORT_ACTIVITY_GATE
    )

    return {
        "failure": failure,
        "sector": case["sector"],
        "class_hint": case["class_hint"],
        "n_lookback_years": len(path),
        "first_rank": round(first_rank, 2),
        "max_rank": round(max_rank, 2),
        "t0_rank": round(t0_rank, 2),
        "failure_max_raw": round(failure_max_raw, 3),
        "cohort_max_raw": round(cohort_max_raw, 3),
        "novelty_spike": novelty_spike,
        "under_disclosure": under_disclosure,
        "detected": novelty_spike or under_disclosure,
    }


def plot_unified_24(results: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 11))
    matrix = results[["novelty_spike", "under_disclosure"]].astype(int).values
    n = len(results)
    ax.imshow(matrix, cmap="RdYlGn", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Novelty spike\n(expanding disclosure)",
                        "Under-disclosure\n(static + active cohort)"], fontsize=10)
    ax.set_yticks(range(n))
    ax.set_yticklabels(
        [f"{r.failure}  ({r.sector})" for _, r in results.iterrows()],
        fontsize=9,
    )
    ax.set_title(f"Unified text-signal scoreboard (n=24 failures, 15 sectors)",
                 fontsize=12)
    for i in range(n):
        for j in range(2):
            v = matrix[i, j]
            ax.text(j, i, "FIRED" if v else "quiet",
                    ha="center", va="center",
                    color="white" if v else "black",
                    fontsize=10, fontweight="bold")

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

    scoreboard_path = PHASE_DIR / "final_scoreboard.png"
    plot_unified_24(results, scoreboard_path)
    print(f"Saved: {scoreboard_path}")

    n_total = len(results)
    detected = int(results["detected"].sum())
    by_spike = int(results["novelty_spike"].sum())
    by_ud = int(results["under_disclosure"].sum())
    by_both = int((results["novelty_spike"] & results["under_disclosure"]).sum())

    print(f"\n=== Phase 3 Final Detection (n={n_total}) ===")
    print(f"Novelty-spike signal:      {by_spike}/{n_total} ({by_spike/n_total*100:.0f}%)")
    print(f"Under-disclosure signal:   {by_ud}/{n_total} ({by_ud/n_total*100:.0f}%)")
    print(f"Both signals fire:         {by_both}/{n_total} ({by_both/n_total*100:.0f}%)")
    print(f"Either signal (detected):  {detected}/{n_total} ({detected/n_total*100:.0f}%)")

    # By known undetectable class (from Phase 2C analysis):
    known_undetectable = results[results["class_hint"].isin(
        ["sudden shock", "industry shock", "chronic anomaly"]
    )]
    new_or_detectable = results[~results.failure.isin(known_undetectable.failure)]
    new_n = len(new_or_detectable)
    new_detected = int(new_or_detectable["detected"].sum())
    print(f"\nExcluding 4 known-undetectable cases (BA, SIVB, SI, PTON):")
    print(f"   {new_detected}/{new_n} ({new_detected/new_n*100:.0f}%)")

    print("\n=== By sector ===")
    sec = results.groupby("sector").agg(
        n=("failure", "count"),
        detected=("detected", "sum"),
    ).reset_index()
    print(sec.to_string(index=False))

    # Save summary
    summary_path = PHASE_DIR / "summary.csv"
    results.to_csv(summary_path, index=False)
    print(f"\nSaved: {summary_path}")


if __name__ == "__main__":
    main()
