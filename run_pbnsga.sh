#!/bin/bash
# run_pbnsga.sh

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOLVER="$PROJECT/src/solver/solver"
POP=200
GEN=300
SEEDS=(0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19)
RES1="$PROJECT/results/exp1"
RES2="$PROJECT/results/exp2"
DATA_BENCH="$PROJECT/data/hlp-benchmark"
DATA_CV="$PROJECT/data/cv"

echo "[PB-NSGA] Full 20-seed run started."

# ── ARCHIVED BENCHMARKS (The data is used for a future study) ─────────────
# Note: Outdated AP and TR81 benchmark runs are preserved here for archival.
# They are not part of the current narrative but available for future research.
# ──────────────────────────────────────────────────────────────────────────
# for N in 10 20 25 40 50 100; do
#     echo "[AP$N] Running 20 seeds..."
#     for R in "${SEEDS[@]}"; do
#         "$SOLVER" "$DATA_BENCH/AP${N}_drnd.json" --pop $POP --gen $GEN --seed $R --out "$RES1/AP${N}_seed${R}.json" 2>/dev/null
#     done
#     echo "[AP$N] Done."
# done

# echo "[TR81] Running 20 seeds..."
# for R in "${SEEDS[@]}"; do
#     "$SOLVER" "$DATA_BENCH/TR81_drnd.json" --pop $POP --gen $GEN --seed $R --out "$RES1/TR81_seed${R}.json" 2>/dev/null
# done
# echo "[TR81] Done."

for G in small large; do
    echo "[CV-$G] Running 20 seeds..."
    for R in "${SEEDS[@]}"; do
        "$SOLVER" "$DATA_CV/cv_${G}_drnd.json" --pop $POP --gen $GEN --seed $R --out "$RES2/CV_${G}_seed${R}.json" 2>/dev/null
    done
    echo "[CV-$G] Done."
done

echo "[PB-NSGA] All seeds complete."
