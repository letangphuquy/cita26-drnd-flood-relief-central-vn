#!/usr/bin/env bash
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RES="$PROJECT/results/exp1"

if [[ ! -d "$RES" ]]; then
  echo "[Error] Missing directory: $RES"
  exit 1
fi

shopt -s nullglob
matches_before=("$RES"/cv_small_aega*)
total_before=${#matches_before[@]}

echo "[Info] Matching files before cleanup: $total_before"

rm -f -- "$RES"/cv_small_aega* 2>/dev/null || true

matches_after=("$RES"/cv_small_aega*)
total_after=${#matches_after[@]}

echo "[Done] Matching files after cleanup: $total_after"
