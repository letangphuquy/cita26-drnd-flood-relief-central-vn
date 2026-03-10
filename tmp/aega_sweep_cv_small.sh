#!/usr/bin/env bash
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="$PROJECT/data/cv/cv_small_drnd.json"
RES="$PROJECT/results/exp1"
SOLVER="$PROJECT/src/solver/solver"
EVAL="$PROJECT/src/scripts/exp1_evaluate_cv_small.py"

PYTHON="$PROJECT/.venv/bin/python3"
if [[ ! -f "$PYTHON" ]]; then
  PYTHON="python3"
fi

mkdir -p "$RES"

if [[ ! -x "$SOLVER" ]]; then
  echo "[Info] solver not found/executable. Building..."
  "$PROJECT/compile.sh"
fi

if [[ ! -f "$RES/cv_small_greedy.json" || ! -f "$RES/cv_small_milp_aws.json" ]]; then
  echo "[Error] Baselines missing in $RES. Run ./run_exp1_baselines.sh first."
  exit 1
fi

# Keep AEGA at the current best from prior sweep; now tune pm/pc on top.
AEGA_MIN=180
AEGA_MAX=260
AEGA_STEP=20

PM_HIGHS=(0.35 0.40 0.45)
PM_LOWS=(0.08 0.10 0.12)
PCS=(0.85 0.90 0.95)

OUT_CSV="$RES/aega_pm_pc_sweep_summary.csv"
echo "tag,aega_min,aega_max,aega_step,pc,pm_high,pm_low,hv,igd,wall_s,cpu_s" > "$OUT_CSV"

for PCH in "${PCS[@]}"; do
  for PMH in "${PM_HIGHS[@]}"; do
    for PML in "${PM_LOWS[@]}"; do
      # Skip invalid schedules where final mutation is not lower than initial.
      if ! awk -v hi="$PMH" -v lo="$PML" 'BEGIN { exit !(lo < hi) }'; then
        continue
      fi

      TAG="aega_${AEGA_MIN}_${AEGA_MAX}_${AEGA_STEP}_pc${PCH}_pm${PMH}_${PML}"
      OUT_JSON="$RES/cv_small_${TAG}.json"

      echo "[Run] $TAG"
      "$SOLVER" "$DATA" \
        --pop 200 --gen 300 --seed 0 \
        --pc "$PCH" --pm-high "$PMH" --pm-low "$PML" \
        --aega-pop --aega-min "$AEGA_MIN" --aega-max "$AEGA_MAX" --aega-step "$AEGA_STEP" \
        --out "$OUT_JSON" >/dev/null

      "$PYTHON" "$EVAL" \
        --results-exp1 "$RES" \
        --ours "$OUT_JSON" \
        --greedy "$RES/cv_small_greedy.json" \
        --milp "$RES/cv_small_milp_aws.json" >/dev/null

      ROW=$(awk -F, '$1=="PB-NSGA" {printf "%s,%s,%s,%s",$3,$5,$7,$8}' "$RES/cv_small_metrics.csv")
      HV=$(echo "$ROW" | cut -d, -f1)
      IGD=$(echo "$ROW" | cut -d, -f2)
      WALL=$(echo "$ROW" | cut -d, -f3)
      CPU=$(echo "$ROW" | cut -d, -f4)

      echo "$TAG,$AEGA_MIN,$AEGA_MAX,$AEGA_STEP,$PCH,$PMH,$PML,$HV,$IGD,$WALL,$CPU" >> "$OUT_CSV"
    done
  done
done

echo ""
echo "[Done] Sweep summary: $OUT_CSV"

echo "[Rank] by HV desc, IGD asc"
python3 - << 'PY'
import csv
from pathlib import Path
p = Path("results/exp1/aega_pm_pc_sweep_summary.csv")
rows = list(csv.DictReader(p.open()))
rows.sort(key=lambda r: (-float(r["hv"]), float(r["igd"])))
for i,r in enumerate(rows,1):
  print(f"{i:2d}. {r['tag']}  HV={float(r['hv']):.6f}  IGD={float(r['igd']):.6f}  wall={r['wall_s']}  cpu={r['cpu_s']}")
PY
