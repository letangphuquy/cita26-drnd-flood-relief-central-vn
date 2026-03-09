#!/bin/bash
# run_exp2_case_study.sh
# ============================================================
# Experiment 2: Central Vietnam Case Study, SAA, and Insights
# ------------------------------------------------------------
# Runs PB-NSGA on the CV-Large instance across multiple seeds.
# Generates:
#   1. Statistical analysis of convergence (HV, IGD+)
#   2. Hub selection stability and sensitivity analysis
#   3. High-fidelity maps of representative solutions
# ============================================================

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_CV="$PROJECT/data/cv/cv_large_drnd.json"
RES2="$PROJECT/results/exp2"
SOLVER_DIR="$PROJECT/src/solver"

# Python venv
PYTHON="$PROJECT/.venv/bin/python3"
if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

mkdir -p "$RES2"

# ── Step 1: Run PB-NSGA (Ours) 20 Seeds ────────────────────────────────────
echo ""
echo "[Step 1] Running PB-NSGA (20 seeds) on CV-Large..."
# Ensure solver is compiled
if [ ! -f "$SOLVER_DIR/solver" ]; then
    bash "$PROJECT/compile.sh"
fi

for seed in {0..19}
do
    echo "  [Seed $seed] Running..."
    "$SOLVER_DIR/solver" "$DATA_CV" \
        --pop 200 \
        --gen 500 \
        --seed "$seed" \
        --out "$RES2/cv_large_seed${seed}.json"
done

# ── Step 2: Statistical Analysis & Sensitivity ────────────────────────────
echo ""
echo "[Step 2] Analyzing Stability & Scenario Sensitivity..."
# Args: <results_dir> <out_dir> <cv_data_dir>
"$PYTHON" "$PROJECT/src/scripts/exp2_analyze_case_study.py" "$RES2" "$RES2" "$PROJECT/data/cv"

# ── Step 3: High-Fidelity Mapping ─────────────────────────────────────────
echo ""
echo "[Step 3] Generating 1x3 Composite Network Map..."
# We pick a representative solution (usually from seed 0 or combined)
"$PYTHON" "$PROJECT/src/scripts/exp2_map_solution.py" \
    --instance "$DATA_CV" \
    --result "$RES2/cv_large_seed0.json" \
    --out "$PROJECT/figures/cv_large_map_detailed.pdf"

echo ""
echo "Experiment 2 (Case Study) Completed."
echo "Results saved to: $RES2/"
echo "Map saved to: figures/cv_large_map_detailed.pdf"
