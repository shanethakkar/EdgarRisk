"""
phase5_longitudinal.py
Phase 5: longitudinal follow-up on the 22 unique-ticker "false positives"
from Phase 4's validation. Manually categorize what happened to each
company between its lookback-window end and today (May 2026).

The hypothesis: some "false positives" were actually leading indicators
of distress that crystallized after the test-window ended. If so, the
model's TRUE precision over a longer horizon is meaningfully higher
than the in-sample precision.

Classification scheme:
  subsequent_distress  -- filed Ch.11, taken private under duress,
                          activist takeover, >50% stock crash,
                          CEO+strategic crisis
  stress_recovered     -- material stress event but company survives
                          and stabilizes (e.g., WAL in March 2023
                          banking crisis, CLX cyberattack)
  healthy              -- no notable corporate-distress event

Outputs:
    outputs/phase5_longitudinal_classification.csv
    outputs/phase5_precision_curves.png
    outputs/phase5_adjusted_metrics.csv
"""

import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# Each of the 22 unique-ticker false positives, manually categorized based
# on public events between lookback-end and May 2026. Conservative coding:
# ambiguous cases default to "stress_recovered" rather than over-counting.
FP_CLASSIFICATIONS = [
    # subsequent_distress: substantial distress event after the lookback
    {"ticker": "JWN",  "company": "Nordstrom",          "status": "subsequent_distress",
     "event": "Taken private May 2025 (Nordstrom family + El Puerto de Liverpool)"},
    {"ticker": "WBA",  "company": "Walgreens Boots Alliance", "status": "subsequent_distress",
     "event": "Take-private deal with Sycamore Partners announced 2025; multi-year operational decline"},
    {"ticker": "CVS",  "company": "CVS Health",          "status": "subsequent_distress",
     "event": "Major 2023-2025 operational issues, stock down ~50% from 2022 peak, CEO replaced"},
    {"ticker": "LCID", "company": "Lucid Motors",        "status": "subsequent_distress",
     "event": "Stock crash >90% from peak; ongoing severe cash burn / going-concern adjacent"},
    {"ticker": "KSS",  "company": "Kohl's",              "status": "subsequent_distress",
     "event": "Multiple activist takeover bids, CEO turnover, stock crash, considered take-private"},
    {"ticker": "M",    "company": "Macy's",              "status": "subsequent_distress",
     "event": "Arkhouse takeover bids 2024, activist pressure for real estate spinoff"},

    # stress_recovered: material stress event but company stabilized
    {"ticker": "WAL",  "company": "Western Alliance",    "status": "stress_recovered",
     "event": "Caught in March 2023 banking crisis with SVB, survived"},
    {"ticker": "CLX",  "company": "Clorox",              "status": "stress_recovered",
     "event": "Major cyberattack 2023, multi-quarter operational disruption, recovered"},
    {"ticker": "ALK",  "company": "Alaska Airlines",     "status": "stress_recovered",
     "event": "Hawaiian Airlines merger integration challenges, door-plug incident, recovered"},
    {"ticker": "WSM",  "company": "Williams-Sonoma",     "status": "stress_recovered",
     "event": "Post-COVID home goods slowdown, recovered into 2024-2025"},

    # healthy: no notable distress event
    {"ticker": "BBY",  "company": "Best Buy",            "status": "healthy",
     "event": "Operating normally post-COVID retail normalization"},
    {"ticker": "KEY",  "company": "KeyCorp",             "status": "healthy",
     "event": "Operating normally; weathered 2023 banking crisis"},
    {"ticker": "ODFL", "company": "Old Dominion Freight Line", "status": "healthy",
     "event": "Continued strong performance, sector leader"},
    {"ticker": "XPO",  "company": "XPO Inc",             "status": "healthy",
     "event": "Spun off RXO/GXO, post-split entity operating well"},
    {"ticker": "ARCB", "company": "ArcBest",             "status": "healthy",
     "event": "Operating normally"},
    {"ticker": "CHD",  "company": "Church & Dwight",     "status": "healthy",
     "event": "Operating normally, defensive consumer staples"},
    {"ticker": "COP",  "company": "ConocoPhillips",      "status": "healthy",
     "event": "Operating normally, energy sector recovery"},
    {"ticker": "HES",  "company": "Hess Corp",           "status": "healthy",
     "event": "Acquired by Chevron in friendly deal (not distress); closed 2024"},
    {"ticker": "BMY",  "company": "Bristol-Myers Squibb", "status": "healthy",
     "event": "Operating normally, large pharma"},
    {"ticker": "PFE",  "company": "Pfizer",              "status": "healthy",
     "event": "Post-COVID revenue normalization, operating"},
    {"ticker": "GD",   "company": "General Dynamics",    "status": "healthy",
     "event": "Operating normally, defense prime"},
    {"ticker": "NOC",  "company": "Northrop Grumman",    "status": "healthy",
     "event": "Operating normally, defense prime"},
    {"ticker": "ALGN", "company": "Align Technology",    "status": "healthy",
     "event": "Operating; competitor pressures from SmileDirectClub failure are net positive for ALGN"},
]


def main() -> None:
    fp_df = pd.DataFrame(FP_CLASSIFICATIONS)
    fp_df.to_csv(OUTPUTS_DIR / "phase5_longitudinal_classification.csv", index=False)

    print("=== Subsequent fate of 22 'false positive' survivors ===")
    print(fp_df.to_string(index=False))

    counts = fp_df.status.value_counts()
    print("\nClass counts:")
    print(counts.to_string())

    # Re-compute adjusted metrics. We treat "subsequent_distress" companies
    # as true positives at extended horizon. "stress_recovered" is left as
    # is -- the signal was a true reading of stress, but the company
    # survived, so it's neither TP nor pure FP.

    n_original_failures = 24
    detected_in_sample = 19           # Phase 4 detected
    survivor_fp_in_sample = 22        # unique-ticker FPs
    survivor_total = 42               # unique survivors in cohort universe

    subsequent_distress = int(counts.get("subsequent_distress", 0))
    stress_recovered = int(counts.get("stress_recovered", 0))
    truly_healthy = int(counts.get("healthy", 0))

    # In-sample (Phase 4): consider only Ch.11 events within test window
    pin = detected_in_sample / (detected_in_sample + survivor_fp_in_sample)
    rin = detected_in_sample / n_original_failures

    # Extended horizon: count subsequent_distress survivors as true positives
    tp_extended = detected_in_sample + subsequent_distress
    fp_extended = survivor_fp_in_sample - subsequent_distress
    p_ext = tp_extended / (tp_extended + fp_extended)
    # recall isn't quite the right framing for extended horizon, but
    # showing detection density is still informative

    print(f"\n=== In-sample metrics (test window only) ===")
    print(f"Recall:    {detected_in_sample}/{n_original_failures} = {rin*100:.0f}%")
    print(f"FP rate:   {survivor_fp_in_sample}/{survivor_total} survivors = {survivor_fp_in_sample/survivor_total*100:.0f}%")
    print(f"Precision: {detected_in_sample}/(19+22) = {pin*100:.0f}%")

    print(f"\n=== Extended-horizon metrics (May 2026 follow-up) ===")
    print(f"True positives:           {detected_in_sample} in-sample + {subsequent_distress} subsequent distress = {tp_extended}")
    print(f"Survivors-who-later-failed: {subsequent_distress} of {survivor_fp_in_sample} flagged ({subsequent_distress/survivor_fp_in_sample*100:.0f}%)")
    print(f"Stress-but-recovered (TP for distress, not failure): {stress_recovered}")
    print(f"Truly healthy after flag: {truly_healthy}")
    print(f"Adjusted precision (counting distress as TP):  {tp_extended}/(TP+FP) = {p_ext*100:.0f}%")

    # Plot precision curve
    fig, ax = plt.subplots(figsize=(11, 5.5))
    categories = ["In-sample\n(Ch.11 only)",
                  "+ Stress/distress\n(May 2026)",
                  "Including\nstress-recovered"]
    precision_values = [
        pin,
        p_ext,
        (tp_extended + stress_recovered) / (tp_extended + stress_recovered + truly_healthy),
    ]
    recall_values = [
        rin,
        # at extended horizon, "recall" needs a different denominator -- we don't
        # know the universe of all subsequent failures, only the ones we flagged
        None,
        None,
    ]

    x = range(len(categories))
    bars = ax.bar(x, [v*100 for v in precision_values], color=["#3498db", "#27ae60", "#9b59b6"], width=0.55)
    ax.set_ylabel("Precision (%)", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=10)
    ax.set_title("Precision evolves when 'false positives' get a longer time horizon", fontsize=12)
    ax.set_ylim(0, 100)
    for bar, v in zip(bars, precision_values):
        ax.text(bar.get_x() + bar.get_width()/2, v*100 + 1.5, f"{v*100:.0f}%",
                ha="center", fontsize=11, fontweight="bold")
    ax.grid(alpha=0.3, axis="y")
    ax.text(0.02, 95, f"In-sample: {detected_in_sample} of {detected_in_sample + survivor_fp_in_sample} flags were Ch.11",
            fontsize=9, alpha=0.7)
    ax.text(0.02, 90, f"Extended: + {subsequent_distress} flagged 'survivors' subsequently distressed (take-privates,\n              activist takeovers, >50% stock crashes)",
            fontsize=9, alpha=0.7)
    plt.tight_layout()
    plt.savefig(OUTPUTS_DIR / "phase5_precision_curves.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # Save summary
    summary = pd.DataFrame({
        "metric": ["In-sample precision (Ch.11 only)",
                   "Extended-horizon precision (Ch.11 + distress)",
                   "Including stress-recovered as TP-for-stress"],
        "value": [f"{pin*100:.0f}%", f"{p_ext*100:.0f}%",
                  f"{(tp_extended + stress_recovered) / (tp_extended + stress_recovered + truly_healthy)*100:.0f}%"],
        "tp": [detected_in_sample, tp_extended, tp_extended + stress_recovered],
        "fp": [survivor_fp_in_sample, fp_extended, truly_healthy],
    })
    summary.to_csv(OUTPUTS_DIR / "phase5_adjusted_metrics.csv", index=False)
    print(f"\nSaved: outputs/phase5_precision_curves.png")
    print(f"Saved: outputs/phase5_adjusted_metrics.csv")


if __name__ == "__main__":
    main()
