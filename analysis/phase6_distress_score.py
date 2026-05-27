"""
phase6_distress_score.py
Phase 6: produce a continuous Distress Score (0-100) per company-cohort
observation suitable for ranking and lookup-tool display.

Honest design choice: at our N=102 (24 failures + 78 survivor-cohort
pairs), a cross-validated logistic regression on the three binary
signals does not beat random ranking (OOF AUC ~= 0.35). The signal IS
the binary detection pattern from Phase 4 -- 8 possible signal
combinations across 102 observations don't provide enough variance
for a meaningful continuous gradient.

Solution: a transparent rule-based score. Each binary signal contributes
a fixed point budget; a small continuous adjustment (peer-relative
percentile rank elevation) breaks ties within bands and gives a
smoother 0-100 distribution for UI/ranking purposes. The score does
NOT claim higher predictive power than the underlying binary signals
-- it is a ranking affordance, not an independent classifier.

Score formula (transparent, no fitting):
    base = 30 * novelty_spike + 30 * declining_ud + 30 * chronic_ud
    bonus = 10 * max(0, max_rank - 0.5)           # tiebreaker: elevated rank
    score = min(100, round(base + bonus))

Outputs:
    outputs/phase6_distress_score/scored.csv
    outputs/phase6_distress_score/top_rankings.png
    outputs/phase6_distress_score/score_distribution.png
    outputs/phase6_distress_score/precision_by_threshold.png
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHASE_DIR = PROJECT_ROOT / "outputs" / "phase6_distress_score"
PHASE_DIR.mkdir(parents=True, exist_ok=True)

FAILURE_CSV = PROJECT_ROOT / "outputs" / "phase4_chronic_and_fp" / "failure_detection.csv"
SURVIVOR_CSV = PROJECT_ROOT / "outputs" / "phase4_chronic_and_fp" / "survivor_fp_analysis.csv"

# Phase 5 longitudinal-adjusted labels: these survivors had material
# corporate-distress events 2023-2025 (take-private, activist takeover,
# 50%+ stock crash, going-concern adjacent).
SUBSEQUENT_DISTRESS_TICKERS = {"JWN", "WBA", "CVS", "LCID", "KSS", "M"}


def load_data() -> pd.DataFrame:
    failures = pd.read_csv(FAILURE_CSV)
    failures["is_failure_strict"] = 1
    if "class_hint" in failures.columns:
        failures = failures.drop(columns=["class_hint"])

    survivors = pd.read_csv(SURVIVOR_CSV)
    survivors["is_failure_strict"] = 0

    df = pd.concat([failures, survivors], ignore_index=True)
    for col in ("novelty_spike", "declining_ud", "chronic_ud", "any_signal"):
        df[col] = df[col].astype(str).str.lower().map({"true": 1, "false": 0}).fillna(0).astype(int)

    df["is_failure_extended"] = df["is_failure_strict"]
    df.loc[df.subject.isin(SUBSEQUENT_DISTRESS_TICKERS), "is_failure_extended"] = 1
    return df


def compute_distress_score(df: pd.DataFrame) -> pd.DataFrame:
    """Transparent rule-based score. No model fitting, no overclaiming."""
    base = 30 * df["novelty_spike"] + 30 * df["declining_ud"] + 30 * df["chronic_ud"]
    bonus = 10 * np.clip(df["max_rank"] - 0.5, 0, None) / 0.5  # 0-10 points for elevated rank
    df["distress_score"] = np.minimum(100, (base + bonus).round()).astype(int)
    df["signals_fired"] = df[["novelty_spike", "declining_ud", "chronic_ud"]].sum(axis=1)
    return df


def plot_top_rankings(scored: pd.DataFrame, out_path: Path, n: int = 25) -> None:
    top = scored.head(n).copy().reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(11, 0.34 * len(top) + 2.5))
    colors = []
    for _, r in top.iterrows():
        if r.is_failure_strict == 1:
            colors.append("#c0392b")
        elif r.is_failure_extended == 1:
            colors.append("#e67e22")
        else:
            colors.append("#27ae60")
    labels = [f"{r.subject} ({r['sector'][:30]})" if r.subject == r.cohort_of
              else f"{r.subject} vs {r.cohort_of} cohort" for _, r in top.iterrows()]
    y_pos = range(len(top))
    ax.barh(y_pos, top.distress_score, color=colors, alpha=0.88)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Distress score (0-100)")
    ax.set_xlim(0, 105)
    ax.axvline(50, color="grey", linestyle=":", alpha=0.5)
    ax.set_title(f"Top {len(top)} highest-distress observations\n"
                 f"red = confirmed Ch.11 failure | orange = subsequent distress (Phase 5) | green = truly healthy",
                 fontsize=11)
    for i, score in enumerate(top.distress_score):
        ax.text(score + 1, i, str(int(score)), va="center", fontsize=9)
    ax.grid(alpha=0.3, axis="x")
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_score_distribution(scored: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    failures_strict = scored[scored.is_failure_strict == 1].distress_score
    subsequent = scored[(scored.is_failure_strict == 0) & (scored.is_failure_extended == 1)].distress_score
    healthy = scored[scored.is_failure_extended == 0].distress_score
    bins = np.arange(0, 105, 5)
    ax.hist(healthy, bins=bins, alpha=0.65, color="#27ae60", label=f"Truly healthy (n={len(healthy)})")
    ax.hist(subsequent, bins=bins, alpha=0.75, color="#e67e22",
            label=f"Phase 5 subsequent-distress (n={len(subsequent)})")
    ax.hist(failures_strict, bins=bins, alpha=0.7, color="#c0392b", label=f"Ch.11 failures (n={len(failures_strict)})")
    ax.set_xlabel("Distress score (0-100)")
    ax.set_ylabel("Count")
    ax.set_title("Distress-score distribution by extended-horizon outcome class", fontsize=11)
    ax.legend()
    ax.grid(alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_precision_recall_by_threshold(scored: pd.DataFrame, out_path: Path) -> None:
    thresholds = list(range(5, 101, 5))
    rows = []
    for thr in thresholds:
        pred = scored.distress_score >= thr
        for label_col, name in [("is_failure_strict", "Strict (Ch.11)"),
                                ("is_failure_extended", "Extended (incl. Phase 5)")]:
            actual = scored[label_col]
            tp = int(((actual == 1) & pred).sum())
            fp = int(((actual == 0) & pred).sum())
            fn = int(((actual == 1) & ~pred).sum())
            recall = tp / (tp + fn) if (tp + fn) else 0
            precision = tp / (tp + fp) if (tp + fp) else 0
            rows.append({"threshold": thr, "label": name, "recall": recall, "precision": precision})
    perf = pd.DataFrame(rows)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for label in perf.label.unique():
        sub = perf[perf.label == label]
        axes[0].plot(sub.threshold, sub.recall * 100, marker="o", label=label, linewidth=2)
        axes[1].plot(sub.threshold, sub.precision * 100, marker="s", label=label, linewidth=2)
    axes[0].set_xlabel("Distress-score threshold")
    axes[0].set_ylabel("Recall (%)")
    axes[0].set_title("Recall vs threshold")
    axes[0].set_ylim(0, 105); axes[0].grid(alpha=0.3); axes[0].legend()
    axes[1].set_xlabel("Distress-score threshold")
    axes[1].set_ylabel("Precision (%)")
    axes[1].set_title("Precision vs threshold")
    axes[1].set_ylim(0, 105); axes[1].grid(alpha=0.3); axes[1].legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    df = load_data()
    df = compute_distress_score(df)

    n_strict = int(df.is_failure_strict.sum())
    n_extended = int(df.is_failure_extended.sum())
    print(f"Loaded {len(df)} observations: {n_strict} strict failures + "
          f"{n_extended - n_strict} subsequent-distress + {len(df) - n_extended} healthy")

    output = df[["subject", "cohort_of", "sector",
                 "is_failure_strict", "is_failure_extended",
                 "distress_score", "signals_fired",
                 "novelty_spike", "declining_ud", "chronic_ud",
                 "max_rank", "mean_rank", "t0_rank", "own_max_raw"]].copy()
    output = output.sort_values(["distress_score", "max_rank"], ascending=[False, False]).reset_index(drop=True)
    output.to_csv(PHASE_DIR / "scored.csv", index=False)
    print(f"Saved: {PHASE_DIR / 'scored.csv'}")

    plot_top_rankings(output, PHASE_DIR / "top_rankings.png")
    plot_score_distribution(df, PHASE_DIR / "score_distribution.png")
    plot_precision_recall_by_threshold(df, PHASE_DIR / "precision_by_threshold.png")
    print(f"Saved: {PHASE_DIR / 'top_rankings.png'}")
    print(f"Saved: {PHASE_DIR / 'score_distribution.png'}")
    print(f"Saved: {PHASE_DIR / 'precision_by_threshold.png'}")

    print("\n=== Score band summary ===")
    for low, high in [(0, 19), (20, 39), (40, 59), (60, 79), (80, 100)]:
        band = df[(df.distress_score >= low) & (df.distress_score <= high)]
        if band.empty:
            continue
        n_strict_band = int(band.is_failure_strict.sum())
        n_ext_band = int(band.is_failure_extended.sum())
        n_total = len(band)
        print(f"  Score {low:3d}-{high:3d}: n={n_total:3d}  "
              f"Ch.11={n_strict_band:2d}  Ext.distress={n_ext_band:2d}  "
              f"PPV strict={n_strict_band/n_total*100:4.0f}%  "
              f"PPV extended={n_ext_band/n_total*100:4.0f}%")

    print("\n=== Top 20 by distress score ===")
    print(output.head(20)[["subject", "cohort_of", "sector",
                            "is_failure_strict", "is_failure_extended",
                            "distress_score", "signals_fired"]].to_string(index=False))


if __name__ == "__main__":
    main()
