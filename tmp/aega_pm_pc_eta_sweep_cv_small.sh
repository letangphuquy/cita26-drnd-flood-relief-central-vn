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

# Broader search over currently active parameters only.
AEGA_CANDIDATES=(
  "180 260 20"
  "180 280 20"
  "200 280 20"
)
PCS=(0.90 0.95 0.98)
PM_HIGHS=(0.40 0.45 0.50)
PM_LOWS=(0.08 0.10)
SBX_ETA_RWS=(1.5 2.0 2.5 3.0)
PM_ETA_RWS=(3 5 8)

OUT_CSV="$RES/aega_pm_pc_eta_sweep_summary.csv"
echo "tag,aega_min,aega_max,aega_step,pc,pm_high,pm_low,sbx_eta_rw,pm_eta_rw,hv,igd,wall_s,cpu_s" > "$OUT_CSV"

for A in "${AEGA_CANDIDATES[@]}"; do
  read -r AEGA_MIN AEGA_MAX AEGA_STEP <<< "$A"
  for PC in "${PCS[@]}"; do
    for PM_HIGH in "${PM_HIGHS[@]}"; do
      for PM_LOW in "${PM_LOWS[@]}"; do
        # Keep valid decay schedule only.
        if ! awk -v hi="$PM_HIGH" -v lo="$PM_LOW" 'BEGIN { exit !(lo < hi) }'; then
          continue
        fi
        for SRW in "${SBX_ETA_RWS[@]}"; do
          for PRW in "${PM_ETA_RWS[@]}"; do
            TAG="aega_${AEGA_MIN}_${AEGA_MAX}_${AEGA_STEP}_pc${PC}_pm${PM_HIGH}_${PM_LOW}_rw${SRW}_${PRW}"
            OUT_JSON="$RES/cv_small_${TAG}.json"

            echo "[Run] $TAG"
            "$SOLVER" "$DATA" \
              --pop 200 --gen 300 --seed 0 \
              --pc "$PC" --pm-high "$PM_HIGH" --pm-low "$PM_LOW" \
              --sbx-eta-rw "$SRW" --pm-eta-rw "$PRW" \
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

            echo "$TAG,$AEGA_MIN,$AEGA_MAX,$AEGA_STEP,$PC,$PM_HIGH,$PM_LOW,$SRW,$PRW,$HV,$IGD,$WALL,$CPU" >> "$OUT_CSV"
          done
        done
      done
    done
  done
done

echo ""
echo "[Done] Sweep summary: $OUT_CSV"

echo "[Rank] by HV desc, IGD asc, wall asc"
python3 - << 'PY'
import csv
from pathlib import Path
p = Path("results/exp1/aega_pm_pc_eta_sweep_summary.csv")
rows = list(csv.DictReader(p.open()))
rows.sort(key=lambda r: (-float(r["hv"]), float(r["igd"]), float(r["wall_s"]), float(r["cpu_s"])))
for i, r in enumerate(rows[:15], 1):
    print(f"{i:2d}. {r['tag']}  HV={float(r['hv']):.6f}  IGD={float(r['igd']):.6f}  wall={r['wall_s']}  cpu={r['cpu_s']}")
PY
