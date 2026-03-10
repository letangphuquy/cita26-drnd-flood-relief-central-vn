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

# Keep non-AEGA knobs fixed to isolate AEGA effects.
POP=200
GEN=300
SEED=0
PC=0.95
PM_HIGH=0.45
PM_LOW=0.10
SBX_ETA_RW=2.0
PM_ETA_RW=5

MINS=(120 140 160 180 200 220)
MAXS=(220 240 260 280 300 320)
STEPS=(10 20 30 40)

OUT_CSV="$RES/aega_only_scan_summary.csv"
echo "tag,aega_on,aega_min,aega_max,aega_step,pc,pm_high,pm_low,sbx_eta_rw,pm_eta_rw,hv,igd,wall_s,cpu_s" > "$OUT_CSV"

run_eval() {
  local tag="$1"
  local out_json="$2"
  "$PYTHON" "$EVAL" \
    --results-exp1 "$RES" \
    --ours "$out_json" \
    --greedy "$RES/cv_small_greedy.json" \
    --milp "$RES/cv_small_milp_aws.json" >/dev/null

  local row
  row=$(awk -F, '$1=="PB-NSGA" {printf "%s,%s,%s,%s",$3,$5,$7,$8}' "$RES/cv_small_metrics.csv")
  local hv igd wall cpu
  hv=$(echo "$row" | cut -d, -f1)
  igd=$(echo "$row" | cut -d, -f2)
  wall=$(echo "$row" | cut -d, -f3)
  cpu=$(echo "$row" | cut -d, -f4)
  echo "$tag,$hv,$igd,$wall,$cpu"
}

# Reference run with AEGA disabled (same fixed non-AEGA knobs).
TAG_REF="aega_off_ref"
OUT_REF="$RES/cv_small_${TAG_REF}.json"
echo "[Run] $TAG_REF"
"$SOLVER" "$DATA" \
  --pop "$POP" --gen "$GEN" --seed "$SEED" \
  --pc "$PC" --pm-high "$PM_HIGH" --pm-low "$PM_LOW" \
  --sbx-eta-rw "$SBX_ETA_RW" --pm-eta-rw "$PM_ETA_RW" \
  --out "$OUT_REF" >/dev/null

REF_METRICS=$(run_eval "$TAG_REF" "$OUT_REF")
REF_HV=$(echo "$REF_METRICS" | cut -d, -f2)
REF_IGD=$(echo "$REF_METRICS" | cut -d, -f3)
REF_WALL=$(echo "$REF_METRICS" | cut -d, -f4)
REF_CPU=$(echo "$REF_METRICS" | cut -d, -f5)
echo "$TAG_REF,0,,,,$PC,$PM_HIGH,$PM_LOW,$SBX_ETA_RW,$PM_ETA_RW,$REF_HV,$REF_IGD,$REF_WALL,$REF_CPU" >> "$OUT_CSV"

for amin in "${MINS[@]}"; do
  for amax in "${MAXS[@]}"; do
    if (( amin >= amax )); then
      continue
    fi
    for astep in "${STEPS[@]}"; do
      # Ensure at least one step between min and max.
      if (( amax - amin < astep )); then
        continue
      fi

      TAG="aega_${amin}_${amax}_${astep}"
      OUT_JSON="$RES/cv_small_${TAG}.json"

      echo "[Run] $TAG"
      "$SOLVER" "$DATA" \
        --pop "$POP" --gen "$GEN" --seed "$SEED" \
        --pc "$PC" --pm-high "$PM_HIGH" --pm-low "$PM_LOW" \
        --sbx-eta-rw "$SBX_ETA_RW" --pm-eta-rw "$PM_ETA_RW" \
        --aega-pop --aega-min "$amin" --aega-max "$amax" --aega-step "$astep" \
        --out "$OUT_JSON" >/dev/null

      METRICS=$(run_eval "$TAG" "$OUT_JSON")
      HV=$(echo "$METRICS" | cut -d, -f2)
      IGD=$(echo "$METRICS" | cut -d, -f3)
      WALL=$(echo "$METRICS" | cut -d, -f4)
      CPU=$(echo "$METRICS" | cut -d, -f5)

      echo "$TAG,1,$amin,$amax,$astep,$PC,$PM_HIGH,$PM_LOW,$SBX_ETA_RW,$PM_ETA_RW,$HV,$IGD,$WALL,$CPU" >> "$OUT_CSV"
    done
  done
done

echo ""
echo "[Done] AEGA-only summary: $OUT_CSV"

echo "[Rank] by HV desc, IGD asc, wall asc"
python3 - << 'PY'
import csv
from pathlib import Path
p = Path("results/exp1/aega_only_scan_summary.csv")
rows = list(csv.DictReader(p.open()))
runs = [r for r in rows if r["aega_on"] == "1"]
runs.sort(key=lambda r: (-float(r["hv"]), float(r["igd"]), float(r["wall_s"]), float(r["cpu_s"])))
for i, r in enumerate(runs[:20], 1):
    print(f"{i:2d}. {r['tag']}  HV={float(r['hv']):.6f}  IGD={float(r['igd']):.6f}  wall={r['wall_s']}  cpu={r['cpu_s']}")
ref = next((r for r in rows if r["aega_on"] == "0"), None)
if ref:
    print("[Ref] AEGA OFF:", f"HV={float(ref['hv']):.6f}", f"IGD={float(ref['igd']):.6f}", f"wall={ref['wall_s']}", f"cpu={ref['cpu_s']}")
PY
