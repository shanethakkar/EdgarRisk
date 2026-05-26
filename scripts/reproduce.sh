#!/usr/bin/env bash
# EdgarRisk - Reproduce All Analysis (Bash, for Linux/macOS)
#
# Runs every phase analysis script in order, regenerating all charts and CSVs
# in outputs/. Assumes uv is on PATH and data/processed/ is already populated
# (which it is in the committed repo).
#
# If data/processed/ is empty (e.g., after a fresh clone with raw HTML missing),
# you need to re-fetch the 10-K corpus first. See README.md for the per-ticker
# fetch + parse + score workflow.
#
# Usage: from project root, run
#   ./scripts/reproduce.sh

set -euo pipefail

SCRIPTS=(
    "analysis/phase0_validation.py"
    "analysis/phase1a_sentiment.py"
    "analysis/phase1b_novelty.py"
    "analysis/phase1c_percentile.py"
    "analysis/phase1d_spirit.py"
    "analysis/phase2a_retail.py"
    "analysis/phase2b_industrial.py"
    "analysis/phase2c_underdisclosure.py"
    "analysis/phase3_scale.py"
    "analysis/phase4_chronic.py"
    "analysis/phase5_longitudinal.py"
)

echo "=== EdgarRisk: regenerating all phase outputs ==="
for s in "${SCRIPTS[@]}"; do
    echo
    echo "==> $s"
    uv run python "$s"
done

echo
echo "=== Done. Outputs in outputs/ ==="
echo "Hero chart: outputs/phase5_longitudinal/precision_curves.png"
