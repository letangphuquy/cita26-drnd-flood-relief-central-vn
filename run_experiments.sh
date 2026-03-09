#!/bin/bash
# run_experiments.sh — Full experiment pipeline
# ============================================================
# Central Vietnam Relief Network Design (MO-IHLNDP)
# ------------------------------------------------------------
# Narrative:
#   Experiment 1: Baseline Comparison on CV-Small
#   Experiment 2: Case Study & Insights on CV-Large
# ============================================================

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Usage:
#   ./run_experiments.sh          — full run
#   ./run_experiments.sh data     — regenerate datasets only
#   ./run_experiments.sh analyze  — run analysis only

if [ "$1" == "data" ]; then
    echo "Regenerating datasets..."
    PYTHON="$PROJECT/.venv/bin/python3"
    if [ ! -f "$PYTHON" ]; then PYTHON="python3"; fi
    $PYTHON src/scripts/data_generate_cv.py --outdir data/cv
    $PYTHON src/scripts/data_process_hlp_benchmark.py --outdir data/benchmark
    echo "Datasets ready."
    exit 0
fi

# ── EXPERIMENT 1: Baseline Comparison (CV-Small) ──────────────────────────
echo ""
echo ">>> Running Experiment 1 (Baselines)..."
bash "$PROJECT/run_exp1_baselines.sh" $1

# ── EXPERIMENT 2: Case Study (CV-Large) ───────────────────────────────────
echo ""
echo ">>> Running Experiment 2 (Case Study)..."
bash "$PROJECT/run_exp2_case_study.sh" $1

# ── ARCHIVED BENCHMARKS (The data is used for a future study) ─────────────
# Note: Outdated AP and TR81 benchmark runs are preserved here for archival.
# They are not part of the current narrative but available for future research.
# # bash "$PROJECT/run_pbnsga.sh" --instances AP TR81
# ──────────────────────────────────────────────────────────────────────────

echo ""
echo "============================================================"
echo " All experiments in the current narrative completed."
echo "============================================================"
