#!/bin/bash
# compile.sh — Compile PB-NSGA-II solver on Unix/Mac
# Requirements: g++ with C++17 support
# Run from project root: ./compile.sh

# Algorithm version: V2
#   - W vector: 6 weights (was 3)
#   - Tiered hub selection with rotation-offset A segment
#   - Normalised + stochastic demand priority scores
#   - Hamming diversity tiebreaker in elitist selection

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOLVER_DIR="$PROJECT_DIR/src/solver"
OUT="$SOLVER_DIR/solver"

echo "[Compile] Building PB-NSGA-II solver (v2)..."
g++ -O3 -std=c++17 -Wall \
    "$SOLVER_DIR/main.cpp" \
    -o "$OUT"

if [ $? -eq 0 ]; then
    echo "[Compile] SUCCESS: $OUT"
else
    echo "[Compile] FAILED. Check errors above."
    exit 1
fi
