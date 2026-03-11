#!/bin/bash
# run_exp1_baselines.sh
# ============================================================

# Optional flags:
#   --skip-unchanged   Skip compile/run steps whose outputs are newer than inputs
#   --analyze-only     Skip solver runs; only perform analysis on existing results/
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

SKIP_UNCHANGED=0
ANALYZE_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --skip-unchanged)
            SKIP_UNCHANGED=1
            ;;
        --analyze-only)
            ANALYZE_ONLY=1
            ;;
        --help|-h)
            echo "Usage: ./run_exp1_baselines.sh [--skip-unchanged] [--analyze-only]"
            echo ""
            echo "Flags:"
            echo "  --skip-unchanged  Skip compile/run steps whose outputs are newer than inputs"
            echo "  --analyze-only    Skip solver runs; only perform analysis on existing results/"
            exit 0
            ;;
        *)
            ;;
    esac
done

if [ "$ANALYZE_ONLY" -eq 1 ]; then
    echo ""
    echo "[Exp1] Running analysis only on existing results..."
    if [ ! -d "$RES1" ]; then
        echo "[Error] results/exp1/ not found. Run full experiment first."
        exit 1
    fi
fi

should_run_step() {
    local out="$1"
    shift
    if [ "$SKIP_UNCHANGED" -eq 0 ]; then
        return 0
    fi
    if [ ! -f "$out" ]; then
        return 0
    fi
    for dep in "$@"; do
        if [ ! -e "$dep" ]; then
            return 0
        fi
        if [ "$dep" -nt "$out" ]; then
            return 0
        fi
    done
    return 1
}

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

# ── Skip all solver/compile steps if --analyze-only ──────────────────────
if [ "$ANALYZE_ONLY" -eq 0 ]; then

# ── Step 1: Recompile greedy_baseline ──────────────────────────────────────
echo ""
echo "[Step 1] Compiling greedy_baseline.cpp (stochastic multi-restart)..."
if should_run_step "$SOLVER_DIR/greedy_baseline" "$SOLVER_DIR/greedy_baseline.cpp"; then
    g++ -O3 -std=c++17 \
        "$SOLVER_DIR/greedy_baseline.cpp" \
        -o "$SOLVER_DIR/greedy_baseline"
    if [ $? -ne 0 ]; then
        echo "[Error] Compilation failed."
        exit 1
    fi
else
    echo "[Skip] greedy_baseline compile unchanged."
fi

# ── Step 2: Run Greedy Heuristic (500 restarts) ───────────────────────────
echo ""
echo "[Step 2] Running Greedy Heuristic (500 restarts)..."
if should_run_step "$RES1/cv_small_greedy.json" "$SOLVER_DIR/greedy_baseline" "$DATA_CV"; then
    "$SOLVER_DIR/greedy_baseline" "$DATA_CV" \
        --restarts 500 \
        --seed 42 \
        --out "$RES1/cv_small_greedy.json"
else
    echo "[Skip] Greedy run unchanged."
fi

# ── Step 2b: Recompile + Run BB-Exact baseline ────────────────────────────
echo ""
echo "[Step 2b] Compiling and running BB-Exact baseline..."
if should_run_step "$SOLVER_DIR/bb_solver" "$SOLVER_DIR/bb_solver.cpp"; then
    g++ -O3 -std=c++17 \
        "$SOLVER_DIR/bb_solver.cpp" \
        -o "$SOLVER_DIR/bb_solver"
    if [ $? -ne 0 ]; then
        echo "[Error] BB compilation failed."
        exit 1
    fi
else
    echo "[Skip] BB compile unchanged."
fi
if should_run_step "$RES1/cv_small_bb.json" "$SOLVER_DIR/bb_solver" "$DATA_CV"; then
    "$SOLVER_DIR/bb_solver" "$DATA_CV" \
        --out "$RES1/cv_small_bb.json" \
        --mode enum \
        --trials 300 \
        --time-limit 180
else
    echo "[Skip] BB run unchanged."
fi

# ── Step 2c: Recompile + Run VNS-TS baseline ──────────────────────────────
echo ""
echo "[Step 2c] Compiling and running VNS-TS baseline..."
if should_run_step "$SOLVER_DIR/vns_ts_baseline" "$SOLVER_DIR/vns_ts_baseline.cpp"; then
    g++ -O3 -std=c++17 \
        "$SOLVER_DIR/vns_ts_baseline.cpp" \
        -o "$SOLVER_DIR/vns_ts_baseline"
    if [ $? -ne 0 ]; then
        echo "[Error] VNS-TS compilation failed."
        exit 1
    fi
else
    echo "[Skip] VNS-TS compile unchanged."
fi
if should_run_step "$RES1/cv_small_vns_ts.json" "$SOLVER_DIR/vns_ts_baseline" "$DATA_CV"; then
    "$SOLVER_DIR/vns_ts_baseline" "$DATA_CV" \
        --out "$RES1/cv_small_vns_ts.json" \
        --seed 42 \
        --iter 120 \
        --time-limit 60 \
        --tabu-tenure 5 \
        --kmax 3 \
        --starts 8
else
    echo "[Skip] VNS-TS run unchanged."
fi

# ── Step 2d: Recompile + Run GWO-HD baseline ─────────────────────────────
echo ""
echo "[Step 2d] Compiling and running GWO-HD baseline..."
if should_run_step "$SOLVER_DIR/gwo_hd_baseline" "$SOLVER_DIR/gwo_hd_baseline.cpp"; then
    g++ -O3 -std=c++17 \
        "$SOLVER_DIR/gwo_hd_baseline.cpp" \
        -o "$SOLVER_DIR/gwo_hd_baseline"
    if [ $? -ne 0 ]; then
        echo "[Error] GWO-HD compilation failed."
        exit 1
    fi
else
    echo "[Skip] GWO-HD compile unchanged."
fi
if should_run_step "$RES1/cv_small_gwo_hd.json" "$SOLVER_DIR/gwo_hd_baseline" "$DATA_CV"; then
    "$SOLVER_DIR/gwo_hd_baseline" "$DATA_CV" \
        --out "$RES1/cv_small_gwo_hd.json" \
        --seed 42 \
        --wolves 30 \
        --iter 560 \
        --time-limit 140 \
        --fracA-start 0.45 \
        --fracA-end 0.06 \
        --fracX-start 0.35 \
        --fracX-end 0.04 \
        --accept-worse 0.03 \
        --stagnation-limit 20 \
        --keep-ratio 0.45 \
        --ps-op-prob 0.35
else
    echo "[Skip] GWO-HD run unchanged."
fi

# ── Step 3: Run MILP Adaptive Weighted Sum (unchanged) ───────────────────
echo ""
echo "[Step 3] Running MILP Adaptive Weighted Sum (AWS)..."
echo "          This may take some time depending on complexity."
if should_run_step "$RES1/cv_small_milp_aws.json" "$SOLVER_DIR/milp_aws_baseline.py" "$DATA_CV"; then
    "$PYTHON" "$SOLVER_DIR/milp_aws_baseline.py" \
        --instance "$DATA_CV" \
        --out "$RES1/cv_small_milp_aws.json" \
        --time_limit 600
else
    echo "[Skip] MILP AWS run unchanged."
fi

# ── Step 3b: Run MILP Epsilon-Constraint Baseline ────────────────────────
echo ""
echo "[Step 3b] Running MILP Epsilon-Constraint Baseline..."
if should_run_step "$RES1/cv_small_milp_eps.json" "$SOLVER_DIR/milp_epsilon.py" "$DATA_CV"; then
    "$PYTHON" "$SOLVER_DIR/milp_epsilon.py" \
        --instance "$DATA_CV" \
        --out "$RES1/cv_small_milp_eps.json" \
        --time_limit 600 \
        --epsilon_steps 20
else
    echo "[Skip] MILP EPS run unchanged."
fi

# ── Step 4: Run PB-NSGA (Ours) ─────────────────────────────────────────────
echo ""
echo "[Step 4] Running PB-NSGA (Ours) on CV-Small..."
# Ensure solver is compiled
if [ ! -f "$SOLVER_DIR/solver" ]; then
    bash "$PROJECT/compile.sh"
fi

AEGA_ARGS=()
if [ "$AEGA_ON" -eq 1 ]; then
    AEGA_ARGS=(--aega-pop --aega-min 220 --aega-max 280 --aega-step 10)
    echo "          AEGA: ON  (min=220, max=280, step=10)"
else
    echo "          AEGA: OFF"
fi

if should_run_step "$RES1/cv_small_pb_nsga.json" \
    "$SOLVER_DIR/solver" "$DATA_CV" "$SOLVER_DIR/main.cpp" "$SOLVER_DIR/nsga2.hpp" "$SOLVER_DIR/representation.hpp"; then
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
else
    echo "[Skip] PB-NSGA run unchanged."
fi

fi  # End of: if [ "$ANALYZE_ONLY" -eq 0 ]; then

# ── Step 5: Final Comparison Table ────────────────────────────────────────
echo ""
echo "[Step 5] Generating Comparison Metrics (HV, IGD+)..."
if should_run_step "$RES1/cv_small_metrics.csv" \
    "$PROJECT/src/scripts/exp1_evaluate_cv_small.py" \
    "$RES1/cv_small_pb_nsga.json" "$RES1/cv_small_bb.json" "$RES1/cv_small_vns_ts.json" "$RES1/cv_small_gwo_hd.json" \
    "$RES1/cv_small_greedy.json" "$RES1/cv_small_milp_aws.json" "$RES1/cv_small_milp_eps.json"; then
    "$PYTHON" "$PROJECT/src/scripts/exp1_evaluate_cv_small.py" \
        --results-exp1 "$RES1" \
        --ours "$RES1/cv_small_pb_nsga.json" \
        --bb "$RES1/cv_small_bb.json" \
        --vns-ts "$RES1/cv_small_vns_ts.json" \
        --gwo-hd "$RES1/cv_small_gwo_hd.json" \
        --greedy "$RES1/cv_small_greedy.json" \
        --milp-aws "$RES1/cv_small_milp_aws.json" \
        --milp-eps "$RES1/cv_small_milp_eps.json"
else
    echo "[Skip] Metrics evaluation unchanged."
fi

# ── Step 6: Audit Solver Outputs (optional) ───────────────────────────────
if [ "$AUDIT_ON" -eq 1 ]; then
    echo ""
    echo "[Step 6] Auditing output correctness/completeness..."
    "$PYTHON" "$PROJECT/src/scripts/audit_solution_outputs.py" \
        --instance "$DATA_CV" \
        --solutions \
        "$RES1/cv_small_pb_nsga.json" \
        "$RES1/cv_small_bb.json" \
        "$RES1/cv_small_vns_ts.json" \
        "$RES1/cv_small_gwo_hd.json" \
        "$RES1/cv_small_greedy.json" \
        "$RES1/cv_small_milp_aws.json" \
        "$RES1/cv_small_milp_eps.json"
fi

echo ""
echo "Experiment 1 (Baselines) Completed."
echo "Results saved to: $RES1/cv_small_metrics.csv"
