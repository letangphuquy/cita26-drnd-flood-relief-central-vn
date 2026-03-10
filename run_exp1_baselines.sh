#!/bin/bash
# run_exp1_baselines.sh
# ============================================================
# Experiment 1: Baseline Comparison on Central Vietnam (CV-Small)
# ------------------------------------------------------------
# Benchmarks PB-NSGA against:
#   1. Greedy Heuristic (Stochastic Multi-Restart)
#   2. MILP Adaptive Weighted Sum (Exact/Bounded solver)
#
# Evaluation Metrics: HV, IGD+, CPU Time
# ============================================================

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_CV="$PROJECT/data/cv/cv_small_drnd.json"
RES1="$PROJECT/results/exp1"
SOLVER_DIR="$PROJECT/src/solver"

# Toggle temporary AEGA population adaptation in PB-NSGA step.
# 1 = on, 0 = off
AEGA_ON=1

# Toggle post-run solution audit (structure + consistency checks).
# 1 = on, 0 = off
AUDIT_ON=1

# Python venv
PYTHON="$PROJECT/.venv/bin/python3"
if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

mkdir -p "$RES1"

# ── Step 1: Recompile greedy_baseline ──────────────────────────────────────
echo ""
echo "[Step 1] Compiling greedy_baseline.cpp (stochastic multi-restart)..."
g++ -O3 -std=c++17 \
    "$SOLVER_DIR/greedy_baseline.cpp" \
    -o "$SOLVER_DIR/greedy_baseline"
if [ $? -ne 0 ]; then
    echo "[Error] Compilation failed."
    exit 1
fi

# ── Step 2: Run Greedy Heuristic (500 restarts) ───────────────────────────
echo ""
echo "[Step 2] Running Greedy Heuristic (500 restarts)..."
"$SOLVER_DIR/greedy_baseline" "$DATA_CV" \
    --restarts 500 \
    --seed 42 \
    --out "$RES1/cv_small_greedy.json"

# ── Step 3: Run MILP Adaptive Weighted Sum (unchanged) ───────────────────
echo ""
echo "[Step 3] Running MILP Adaptive Weighted Sum (AWS)..."
echo "          This may take some time depending on complexity."
"$PYTHON" "$SOLVER_DIR/milp_aws_baseline.py" \
    --instance "$DATA_CV" \
    --out "$RES1/cv_small_milp_aws.json" \
    --time_limit 600

# ── Step 3b: Run MILP Epsilon-Constraint Baseline ────────────────────────
echo ""
echo "[Step 3b] Running MILP Epsilon-Constraint Baseline..."
"$PYTHON" "$SOLVER_DIR/milp_epsilon.py" \
    --instance "$DATA_CV" \
    --out "$RES1/cv_small_milp_eps.json" \
    --time_limit 600 \
    --epsilon_steps 20

# ── Step 4: Run PB-NSGA (Ours) ─────────────────────────────────────────────
echo ""
echo "[Step 4] Running PB-NSGA (Ours) on CV-Small..."
# Ensure solver is compiled
if [ ! -f "$SOLVER_DIR/solver" ]; then
    bash "$PROJECT/compile.sh"
fi

AEGA_ARGS=()
if [ "$AEGA_ON" -eq 1 ]; then
    AEGA_ARGS=(--aega-pop --aega-min 120 --aega-max 320 --aega-step 30)
    echo "          AEGA: ON  (min=120, max=320, step=30)"
else
    echo "          AEGA: OFF"
fi

"$SOLVER_DIR/solver" "$DATA_CV" \
    --pop 200 \
    --gen 300 \
    --seed 0 \
    --pc 0.98 \
    --pm-high 0.40 \
    --pm-low 0.10 \
    --sbx-eta-rw 1.5 \
    --pm-eta-rw 8 \
    "${AEGA_ARGS[@]}" \
    --out "$RES1/cv_small_pb_nsga.json"

# ── Step 5: Final Comparison Table ────────────────────────────────────────
echo ""
echo "[Step 5] Generating Comparison Metrics (HV, IGD+)..."
"$PYTHON" "$PROJECT/src/scripts/exp1_evaluate_cv_small.py" \
    --results-exp1 "$RES1" \
    --ours "$RES1/cv_small_pb_nsga.json" \
    --greedy "$RES1/cv_small_greedy.json" \
    --milp-aws "$RES1/cv_small_milp_aws.json" \
    --milp-eps "$RES1/cv_small_milp_eps.json"

# ── Step 6: Audit Solver Outputs (optional) ───────────────────────────────
if [ "$AUDIT_ON" -eq 1 ]; then
    echo ""
    echo "[Step 6] Auditing output correctness/completeness..."
    "$PYTHON" "$PROJECT/src/scripts/audit_solution_outputs.py" \
        --instance "$DATA_CV" \
        --solutions \
        "$RES1/cv_small_pb_nsga.json" \
        "$RES1/cv_small_greedy.json" \
        "$RES1/cv_small_milp_aws.json" \
        "$RES1/cv_small_milp_eps.json"
fi

echo ""
echo "Experiment 1 (Baselines) Completed."
echo "Results saved to: $RES1/cv_small_metrics.csv"
