#!/bin/bash
# compile.sh — Compile PB-NSGA-II solver on Unix/Mac
# Requirements: g++ with C++17 support
# Run from project root: ./compile.sh [--all]

# Algorithm version: V2
#   - W vector: 6 weights (was 3); W[5] = Pass-1 window depth
#   - Tiered hub selection with anchor-based hub ordering (A~anchor hub)
#   - Normalised + stochastic demand priority scores
#   - Hamming diversity tiebreaker in elitist selection

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOLVER_DIR="$PROJECT_DIR/src/solver"
OUT="$SOLVER_DIR/solver"

COMPILE_ALL=0
for arg in "$@"; do
    case "$arg" in
        --all)
            COMPILE_ALL=1
            ;;
        --help|-h)
            echo "Usage: ./compile.sh [--all]"
            echo ""
            echo "Flags:"
            echo "  --all   Compile PB-NSGA and all C++ comparison solvers"
            exit 0
            ;;
        *)
            ;;
    esac
done

compile_one() {
    local src="$1"
    local out="$2"
    local name="$3"
    echo "[Compile] Building $name..."
    g++ -O3 -std=c++17 -Wall "$src" -o "$out"
    if [ $? -ne 0 ]; then
        echo "[Compile] FAILED: $name"
        exit 1
    fi
    echo "[Compile] SUCCESS: $out"
}

compile_one "$SOLVER_DIR/main.cpp" "$OUT" "PB-NSGA-II solver (v2)"

if [ "$COMPILE_ALL" -eq 1 ]; then
    compile_one "$SOLVER_DIR/greedy_baseline.cpp" "$SOLVER_DIR/greedy_baseline" "Greedy baseline"
    compile_one "$SOLVER_DIR/bb_solver.cpp" "$SOLVER_DIR/bb_solver" "BB-Exact baseline"
    compile_one "$SOLVER_DIR/vns_ts_baseline.cpp" "$SOLVER_DIR/vns_ts_baseline" "VNS-TS baseline"
    compile_one "$SOLVER_DIR/gwo_hd_baseline.cpp" "$SOLVER_DIR/gwo_hd_baseline" "GWO-HD baseline"
fi
