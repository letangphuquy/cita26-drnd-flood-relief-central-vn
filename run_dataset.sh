#!/bin/bash
# run_dataset.sh

# Python venv activate
source .venv/bin/activate 2>/dev/null || true

python3 data/prep/patch_coords.py --dry-run

read -p "Do you want to run patch_coords? (y/n): " run_patch
if [[ "$run_patch" =~ ^[Yy]$ ]]; then
    python3 data/prep/patch_coords.py
fi

python3 src/scripts/generate_cv.py --outdir data/cv
python3 data/prep/dataset_visualizer.py
