#!/bin/bash
# run_exp2_case_study.sh
# ============================================================
# Experiment 2: Central Vietnam Case Study, SAA, and OOS Insights
# ------------------------------------------------------------
# Runs PB-NSGA on the CV-Large instance across multiple seeds.
# Generates:
#   1. Statistical analysis of convergence (HV, IGD+)
#   2. VNS-TS baseline fronts for trade-off comparison
#   3. PB-NSGA vs VNS-TS Pareto trade-off analysis
#   4. Hub selection stability and sensitivity analysis
#   5. High-fidelity maps of representative solutions
#   6. End-to-end SAA/OOS robustness evaluation (seed-0 Pareto)
# ============================================================

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_CV="$PROJECT/data/cv/cv_large_drnd.json"
DATA_PREP="$PROJECT/data/prep"
SAA_DATA="$DATA_PREP/cv_large_saa100.json"
OOS_DATA="$DATA_PREP/cv_large_oos10.json"
RES2="$PROJECT/results/exp2"
SOLVER_DIR="$PROJECT/src/solver"

# Python venv
PYTHON="$PROJECT/.venv/bin/python3"
if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

mkdir -p "$RES2"
mkdir -p "$DATA_PREP"

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

# ── Step 2: Run VNS-TS baseline (literature comparator) ───────────────────
echo ""
echo "[Step 2] Running VNS-TS baseline (5 seeds) on CV-Large..."
if [ ! -f "$SOLVER_DIR/vns_ts_baseline" ]; then
    g++ -std=c++17 -O2 -I"$SOLVER_DIR" "$SOLVER_DIR/vns_ts_baseline.cpp" -o "$SOLVER_DIR/vns_ts_baseline"
fi

for seed in {0..4}
do
    echo "  [VNS Seed $seed] Running..."
    "$SOLVER_DIR/vns_ts_baseline" "$DATA_CV" \
        --seed "$seed" \
        --iter 180 \
        --time-limit 180 \
        --tabu-tenure 7 \
        --kmax 3 \
        --starts 10 \
        --out "$RES2/cv_large_vns_ts_seed${seed}.json"
done

# ── Step 3: Pareto trade-off (PB-NSGA vs VNS-TS) ─────────────────────────
echo ""
echo "[Step 3] Building PB-NSGA vs VNS-TS Pareto trade-off outputs..."
"$PYTHON" "$PROJECT/src/scripts/exp2_pareto_tradeoff_pbnsga_vs_vnsts.py" \
    --results-exp2 "$RES2" \
    --results-exp1 "$PROJECT/results/exp1" \
    --out-dir "$RES2"

# ── Step 4: Statistical Analysis & Sensitivity ────────────────────────────
echo ""
echo "[Step 4] Analyzing Stability & Scenario Sensitivity..."
# Args: <results_dir> <out_dir> <cv_data_dir>
"$PYTHON" "$PROJECT/src/scripts/exp2_analyze_case_study.py" "$RES2" "$RES2" "$PROJECT/data/cv"

# ── Step 5: High-Fidelity Mapping ─────────────────────────────────────────
echo ""
echo "[Step 5] Generating 1x3 Composite Network Map..."
# We pick a representative solution (usually from seed 0 or combined)
"$PYTHON" "$PROJECT/src/scripts/exp2_map_solution.py" \
    --instance "$DATA_CV" \
    --result "$RES2/cv_large_seed0.json" \
    --out "$PROJECT/figures/cv_large_map_detailed.pdf"

# ── Step 6: Generate SAA/OOS datasets (combinatorial protocol) ───────────
echo ""
echo "[Step 6] Regenerating SAA/OOS datasets (SAA=100, OOS=10 hard)..."
"$PYTHON" "$PROJECT/src/scripts/data_generate_saa_oos.py" \
    --saa-scenarios 100 \
    --oos-scenarios 10 \
    --out-dir "$DATA_PREP"

# ── Step 7: Compile OOS evaluator ─────────────────────────────────────────
echo ""
echo "[Step 7] Preparing evaluate_oos executable..."
if [ ! -f "$SOLVER_DIR/evaluate_oos" ]; then
    g++ -O2 -std=c++17 "$SOLVER_DIR/evaluate_oos.cpp" -o "$SOLVER_DIR/evaluate_oos"
fi

# ── Step 8: Evaluate seed-0 Pareto on SAA/OOS ─────────────────────────────
echo ""
echo "[Step 8] Evaluating seed-0 Pareto on SAA and OOS sets..."
"$SOLVER_DIR/evaluate_oos" "$SAA_DATA" "$RES2/cv_large_seed0.json" "$RES2/CV_large_seed0_saa_eval.json"
"$SOLVER_DIR/evaluate_oos" "$OOS_DATA" "$RES2/cv_large_seed0.json" "$RES2/CV_large_seed0_oos_eval.json"

# ── Step 9: Summarize SAA/OOS robustness ──────────────────────────────────
echo ""
echo "[Step 9] Summarizing SAA/OOS diagnostics..."
"$PYTHON" "$PROJECT/src/scripts/exp2_analyze_saa_oos.py" \
    --saa-eval "$RES2/CV_large_seed0_saa_eval.json" \
    --oos-eval "$RES2/CV_large_seed0_oos_eval.json" \
    --out "$RES2/exp2_saa_oos_summary.json"

echo ""
echo "Experiment 2 (Case Study) Completed."
echo "Results saved to: $RES2/"
echo "Map saved to: figures/cv_large_map_detailed.pdf"
echo "Trade-off outputs: $RES2/exp2_tradeoff_pareto.csv, $RES2/exp2_pareto_pbnsga_vs_vnsts.pdf"
echo "SAA/OOS summary saved to: $RES2/exp2_saa_oos_summary.json"
