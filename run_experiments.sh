#!/bin/bash
# run_experiments.sh — Full experiment pipeline
# ============================================================
# Central Vietnam Relief Network Design (MO-IHLNDP)
# ------------------------------------------------------------
# Narrative:
#   Experiment 1: Baseline Comparison on CV-Small
#   Experiment 2: Case Study & Insights on CV-Large
#
# Modes:
#   ./run_experiments.sh                — full run (compile + data + solve + analyze)
#   ./run_experiments.sh data           — regenerate datasets only
#   ./run_experiments.sh analyze        — run analysis only (requires existing results/)
#   ./run_experiments.sh compile-only   — compile solvers only
# ============================================================

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Usage documentation
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    echo "Usage: ./run_experiments.sh [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  (none)         — Run full pipeline (compile, generate data, solve, analyze)"
    echo "  data           — Regenerate datasets only"
    echo "  analyze        — Run analysis only (assumes results/ exists)"
    echo "  compile-only   — Compile solvers only"
    exit 0
fi

case "$1" in
    "data")
        echo "Regenerating datasets..."
        PYTHON="$PROJECT/.venv/bin/python3"
        if [ ! -f "$PYTHON" ]; then PYTHON="python3"; fi
        $PYTHON src/scripts/data_generate_cv.py --outdir data/cv
        $PYTHON src/scripts/data_process_hlp_benchmark.py --outdir data/benchmark
        echo "Datasets ready."
        exit 0
        ;;
    "compile-only")
        echo "Compiling solvers..."
        bash "$PROJECT/compile.sh"
        exit 0
        ;;
    "analyze")
        echo "Running analysis on existing results/"
        echo ""
        echo ">>> Running Analysis for Experiment 1..."
        bash "$PROJECT/run_exp1_baselines.sh" --analyze-only
        echo ""
        echo ">>> Running Analysis for Experiment 2..."
        bash "$PROJECT/run_exp2_case_study.sh" --analyze-only
        echo ""
        echo "============================================================"
        echo " Analysis complete."
        echo "============================================================"
        exit 0
        ;;
    *)
        # Default: full run
        ;;
esac

# ── EXPERIMENT 1: Baseline Comparison (CV-Small) ──────────────────────────
echo ""
echo ">>> Running Experiment 1 (Baselines)..."
bash "$PROJECT/run_exp1_baselines.sh"

# ── EXPERIMENT 2: Case Study (CV-Large) ───────────────────────────────────
echo ""
echo ">>> Running Experiment 2 (Case Study)..."
bash "$PROJECT/run_exp2_case_study.sh"

# ── ARCHIVED BENCHMARKS (The data is used for a future study) ─────────────
# Note: Outdated AP and TR81 benchmark runs are preserved here for archival.
# They are not part of the current narrative but available for future research.
# # bash "$PROJECT/run_pbnsga.sh" --instances AP TR81
# ──────────────────────────────────────────────────────────────────────────

echo ""
echo "============================================================"
echo " All experiments in the current narrative completed."
echo "============================================================"
