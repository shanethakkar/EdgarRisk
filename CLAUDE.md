# EdgarRisk — Project Guide

A text-based corporate distress detector built on SEC 10-K Risk Factor disclosures. The project tests whether peer-relative novelty / under-disclosure signals in annual filings predict subsequent operational failures.

**Status as of last update:** Methodology locked; n=24 failures + 42 survivors across 15 sectors; 79% recall + 61% extended-horizon precision; longitudinal validation complete. The canonical writeup is in [ARTICLE.md](ARTICLE.md). User-facing intro is in [README.md](README.md).

## Reading guide

Start here:
- [ARTICLE.md](ARTICLE.md) — full ~2,800 word writeup of methodology, findings, and limitations
- [README.md](README.md) — practical project intro with reproduction instructions
- [outputs/phase5_longitudinal/findings.md](outputs/phase5_longitudinal/findings.md) — the strongest single finding (longitudinal FP follow-up)
- [outputs/phase4_chronic_and_fp/findings.md](outputs/phase4_chronic_and_fp/findings.md) — false-positive validation that forced honest reframing
- [outputs/phase3_scale/findings.md](outputs/phase3_scale/findings.md) — scale-out to 24 failures

Per-phase findings docs are in `outputs/phase[0-5]*_findings.md`, ordered by commit history.

## Working directory

`c:\Users\shane\Projects\RiskAnalyzer`

When running scripts: `uv run python skills/<skill>.py` or `uv run python analysis/<phase>.py` from the project root.

## Core methodology — what to preserve

The methodology is locked. Don't change these without explicit reason:

1. **Peer-relative percentile-rank scoring** against sector-matched cohorts of 3-5 survivors per failure. Absolute scoring (e.g., raw Loughran-McDonald Negative ratio) is anti-predictive — it's a sector classifier, not a distress signal. Healthy JPMorgan has higher LM-Negative ratio than every retail failure in the dataset.

2. **Three signals**, evaluated independently then OR'd:
   - **`novelty_spike`**: `max_pct_rank >= 0.75` in any lookback year AND `own_max_raw_novelty >= 0.10` (raw floor critical to filter spurious signals in static cohorts)
   - **`declining_under_disclosure`**: `t0_rank <= 0.34` AND `(first_rank - t0_rank) >= 0.20pp` AND `cohort_max_raw >= 0.10`
   - **`chronic_under_disclosure`**: `mean_rank <= 0.34` AND `max_rank <= 0.50` AND `cohort_max_raw >= 0.10` AND `own_max_raw < 0.10`

3. **Standard lookback window**: t-3 to t-0 where data permits, else t-2 to t-0. Some failures (post-SPAC EVs, Spirit Airlines, Silvergate) have shorter windows due to limited public history.

4. **Hand-picked cohorts** — sector and size-matched survivors, 3-5 per failure. These are committed in the analysis scripts (`analysis/phase3_scale.py:ALL_FAILURES`). Cohort selection is the one judgment call where the methodology has discretion; document any new cohorts carefully.

## What NOT to do

- **Don't add new signals without false-positive validation** against the survivor population. Phase 4 showed `novelty_spike` has 40% unique-ticker FP rate. New signals should have FP rate measured before being claimed.
- **Don't tune thresholds to catch a single new failure case.** The current thresholds are set defensibly across the n=24 set. Adding a new threshold to catch a specific case is overfitting.
- **Don't run the legacy two-agent system on new analysis.** The original Boeing pilot used a Filing Agent + Analyst Agent split that produced the FY2025-vs-FY2024 memo. That workflow still works for single-ticker investor memos but is not where the project's primary work lives. New analysis goes in `analysis/phaseN_*.py`.
- **Don't modify processed JSON files manually.** They are skill outputs; regenerate by re-running the relevant skill if needed.
- **Don't claim "100% detection" anywhere.** The honest claim is 79% recall + 61% extended-horizon precision. Phase 1B made the over-claim and Phase 4 had to retract it; don't reintroduce.

## How to add a new failure case

If you want to test the model on a new bankruptcy or corporate failure:

1. **Look up the CIK** via EDGAR full-text search (`https://efts.sec.gov/LATEST/search-index?q=...&forms=10-K`).
2. **Pick a sector cohort** — 3-5 sector + size-matched public survivors that have 10-Ks covering the failure's lookback window. Be careful about survivors that subsequently failed (don't use them as controls).
3. **Fetch the failure and any new survivors**: `uv run python skills/fetch_10k.py --cik {CIK} --label {TICKER} --years N` (or `--ticker` for active issuers).
4. **Parse + sentiment + novelty**: run `section_parser.py`, `sentiment_scorer.py`, `novelty_scorer.py` for each new ticker.
5. **Add to `analysis/phase3_scale.py:ALL_FAILURES`** with the lookback window, survivors, sector, and class_hint.
6. **Re-run `phase3_scale.py`** and `phase4_chronic.py` to update aggregate metrics.
7. **Update findings docs** with the new case classification.

## Skills (atomic, reusable)

- [fetch_10k.py](skills/fetch_10k.py) — Download 10-Ks from EDGAR. Supports `--ticker` (active issuers only) and `--cik --label` (any issuer, including delisted/private).
- [section_parser.py](skills/section_parser.py) — Extract Item 1A (Risk Factors) and Item 7 (MD&A) from 10-K HTML. Some failures (JPM's MD&A in particular) have parser fragility — risk-section char count is more reliable than item count.
- [sentiment_scorer.py](skills/sentiment_scorer.py) — Loughran-McDonald word-frequency scoring (7 categories: Negative, Positive, Uncertainty, Litigious, Strong/Weak Modal, Constraining).
- [novelty_scorer.py](skills/novelty_scorer.py) — TF-IDF cosine similarity between consecutive years, with unigrams + bigrams.
- [redflag_detector.py](skills/redflag_detector.py) — Legacy keyword-based detector. Phase 1A revealed it has too much boilerplate noise to be useful as-is. Superseded by sentiment + novelty. Still useful if context-aware matching is added.
- [yoy_diff.py](skills/yoy_diff.py), [risk_classifier.py](skills/risk_classifier.py), [memo_writer.py](skills/memo_writer.py) — Original Boeing-pilot skills. Still functional for single-ticker investor memos.

## Data sources

- **SEC EDGAR** (free, public): 10-K HTML via `data.sec.gov/submissions` and `sec.gov/Archives/edgar/data/`. Requires User-Agent header.
- **Loughran-McDonald Master Dictionary 1993-2024** in `data/reference/`. Originally distributed by Notre Dame SRAF on a Google Drive link; checked in for reproducibility. Non-commercial research license.

## Known data gotchas

- **FDIC-supervised banks** (First Republic, Signature Bank) don't file SEC 10-Ks. SEC-text-based studies of bank failures have a structural blind spot for this entire class.
- **Companies taken private** (JWN/Nordstrom 2025, WBA/Walgreens 2025) drop out of EDGAR's active ticker map but keep their CIK. Fetch via `--cik`.
- **Post-bankruptcy ticker mangling**: SAVE → SAVEQ → FLYYQ (Spirit Airlines). CIK persists.
- **Heavy filers** (Boeing): EDGAR's `recent` filings block holds ~1000 most recent items. For 5+ years of history on heavy filers, the script walks the historical `files` chunks. Handled in `fetch_10k.py:get_recent_10k_filings`.

## Project structure

```
EdgarRisk/
├── README.md                 # Public project intro
├── ARTICLE.md                # Canonical writeup (~2,800 words)
├── CLAUDE.md                 # This file
├── pyproject.toml + uv.lock  # Dependencies (Python 3.12, uv-managed)
├── agents/                   # Legacy two-agent definitions
├── skills/                   # Atomic reusable skills
├── analysis/                 # Per-phase analysis scripts
├── data/
│   ├── reference/            # Frozen LM dictionary
│   ├── raw/                  # HTML (gitignored) + manifests (tracked)
│   └── processed/            # Parsed JSON + scores (tracked)
└── outputs/                  # Findings docs + charts + CSVs
```

## Project history (the 12-phase arc)

```
23c8c08 Phase 5: longitudinal FP follow-up shows 'false positives' are leading indicators
5968486 Phase 4: chronic UD detector + false-positive validation forces honest reframing
c54afc6 Phase 3: scale to 24 failures across 15 sectors, 17/24 detected
a199124 Phase 2C: under-disclosure detector closes the SAVE/JCP gap, 9/9 detectable
b8b871b Phase 2B: cross-sector generalization, novelty detects 7/7 expanding-disclosure failures
46c9ba9 Phase 2A: retail sector expansion to 5 failures, 80% novelty detection
0faf54a Phase 1D: Spirit Airlines out-of-sample test (negative result)
d0668dc Phase 1C: cohorts, standard windows, percentile-rank scoring
2fa7441 Phase 1B: TF-IDF YoY novelty scoring + 3-signal composite scoreboard
e004db6 Phase 1A: Loughran-McDonald sentiment scoring + signal-richer comparison
b663df8 Phase 0: case-control validation across 5 failure/survivor pairs
8edffd1 Initial: Boeing 10-K Risk Analyzer pilot + EdgarRisk rename + uv env
```

Each commit message contains the phase's findings summary; the per-phase `outputs/phaseN_*_findings.md` docs have the full analysis with charts.

## Default demo task (legacy)

If you're asked to "run the demo" without further context, the original Boeing-pilot workflow still works:
- Ticker: BA (Boeing)
- Workflow: fetch → parse → diff → classify → redflag → memo
- Output: `outputs/BA_risk_memo_FY2025_vs_FY2024.md`

But the project's primary analytical work now lives in `analysis/phase*.py`. New questions about distress detection should run those scripts, not the legacy two-agent memo pipeline.
