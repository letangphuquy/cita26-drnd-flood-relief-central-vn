#!/bin/bash
# make_submission.sh
# ============================================================
# One-shot CITA EasyChair submission builder (Paper 419)
# ============================================================
# Regenerates all three paper figures from existing solver results,
# compiles paper/main.tex to PDF, and packages a submission-ready
# .zip + .pdf in submission/ — no solver is re-run.
#
# Usage:
#   ./make_submission.sh
#
# Outputs:
#   submission/mypaper419.zip   — zip archive for EasyChair upload
#   submission/paper419_main.pdf — PDF for EasyChair upload
#
# EasyChair upload fields:
#   Main LaTeX file         : main.tex
#   Program for main file   : pdflatex
#   Program for bibliography: bibtex
# ============================================================

set -euo pipefail

# ── Phase 0: Variable Definitions ────────────────────────────────────────────

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAPER="$PROJECT_DIR/paper"
FIG_DIR="$PAPER/figures"          # paper/figures/ — where main.tex reads from
FIGURES_ROOT="$PROJECT_DIR/figures" # root-level figures/ — exp_saa_convergence.py writes here
RES2="$PROJECT_DIR/results/exp2"
RES1="$PROJECT_DIR/results/exp1"
SAA_RESULTS="$PROJECT_DIR/results/saa_convergence"
SUBMISSION="$PROJECT_DIR/submission"

# Python interpreter: prefer .venv, fall back to system python3
PYTHON="$PROJECT_DIR/.venv/bin/python3"
if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

mkdir -p "$SUBMISSION" "$FIGURES_ROOT" "$FIG_DIR"

echo ""
echo "============================================================"
echo " make_submission.sh — CITA EasyChair Paper 419"
echo "============================================================"
echo "  Project : $PROJECT_DIR"
echo "  Python  : $PYTHON"
echo ""

# ── Phase 1: Pre-flight Prerequisite Checks ───────────────────────────────────

echo "[Phase 1] Checking prerequisites..."

# Helper: abort with a clear message if a file is missing
require_file() {
    if [ ! -f "$1" ]; then
        echo "[ERROR] Required file missing: $1"
        exit 1
    fi
}

# Check toolchain
if ! command -v pdflatex >/dev/null 2>&1; then
    echo "[ERROR] pdflatex not found. Install a TeX distribution (e.g. MacTeX)."
    exit 1
fi
if ! command -v bibtex >/dev/null 2>&1; then
    echo "[ERROR] bibtex not found. Install a TeX distribution (e.g. MacTeX)."
    exit 1
fi
echo "  OK: pdflatex and bibtex available"

# Check LaTeX source files (non-standard files that must go in the zip)
require_file "$PAPER/main.tex"
require_file "$PAPER/cite-class.bib"
require_file "$PAPER/llncs.cls"
echo "  OK: paper/main.tex, paper/cite-class.bib, paper/llncs.cls"

# Check Figure 1 inputs: results/saa_convergence/N*_rep*_bb.json (70 files)
SAA_COUNT=$(ls "$SAA_RESULTS"/N*_rep*_bb.json 2>/dev/null | wc -l | tr -d ' ')
if [ "$SAA_COUNT" -lt 70 ]; then
    echo "[ERROR] Expected ≥70 saa_convergence result files, found $SAA_COUNT"
    echo "        Run: python src/scripts/exp_saa_convergence.py"
    exit 1
fi
echo "  OK: $SAA_COUNT saa_convergence result files"

# Check Figure 2 inputs (exp1)
require_file "$RES1/cv_small_pb_nsga.json"
require_file "$RES1/cv_small_vns_ts.json"
require_file "$RES1/cv_small_gwo_hd.json"
require_file "$RES1/cv_small_milp_aws.json"
require_file "$RES1/cv_small_milp_eps.json"
echo "  OK: results/exp1/ cv_small_pb_nsga, vns_ts, gwo_hd, milp_aws, milp_eps"

# Check Figure 2 inputs (exp2): PB-NSGA, VNS-TS, GWO-HD seeds 0-19
PB_COUNT=$(ls "$RES2"/[Cc][Vv]_large_seed*.json 2>/dev/null | grep -E "seed[0-9]+\.json$" | wc -l | tr -d ' ')
VNS_COUNT=$(ls "$RES2"/cv_large_vns_ts_seed*.json 2>/dev/null | wc -l | tr -d ' ')
GWO_COUNT=$(ls "$RES2"/cv_large_gwo_hd_seed*.json 2>/dev/null | wc -l | tr -d ' ')
if [ "$PB_COUNT" -lt 20 ]; then
    echo "[ERROR] Expected ≥20 CV-large PB-NSGA seed files, found $PB_COUNT in $RES2/"
    exit 1
fi
if [ "$VNS_COUNT" -lt 20 ]; then
    echo "[ERROR] Expected ≥20 CV-large VNS-TS seed files, found $VNS_COUNT in $RES2/"
    exit 1
fi
if [ "$GWO_COUNT" -lt 20 ]; then
    echo "[ERROR] Expected ≥20 CV-large GWO-HD seed files, found $GWO_COUNT in $RES2/"
    exit 1
fi
echo "  OK: $PB_COUNT PB-NSGA, $VNS_COUNT VNS-TS, $GWO_COUNT GWO-HD cv_large seed files"

# Check Figure 3 inputs: specific seed used for the map
require_file "$RES2/cv_large_seed0.json"
require_file "$PROJECT_DIR/data/cv/cv_large_drnd.json"
echo "  OK: results/exp2/cv_large_seed0.json and data/cv/cv_large_drnd.json"

echo "  All prerequisites satisfied."
echo ""

# ── Phase 2: Figure 1 — saa_convergence.pdf ──────────────────────────────────

echo "[Phase 2] Generating saa_convergence.pdf..."
echo "  Script : src/scripts/exp_saa_convergence.py --skip-solve"
echo "  Input  : results/saa_convergence/N*_rep*_bb.json ($SAA_COUNT files)"
echo "  Output : figures/saa_convergence.pdf → paper/figures/saa_convergence.pdf"

cd "$PROJECT_DIR"
"$PYTHON" src/scripts/exp_saa_convergence.py --skip-solve

require_file "$FIGURES_ROOT/saa_convergence.pdf"
cp "$FIGURES_ROOT/saa_convergence.pdf" "$FIG_DIR/saa_convergence.pdf"
echo "  -> Synced: paper/figures/saa_convergence.pdf"
echo ""

# ── Phase 3: Figure 2 — exp2_pareto_tradeoff.pdf ─────────────────────────────

echo "[Phase 3] Generating exp2_pareto_tradeoff.pdf..."
echo "  Script : src/scripts/exp2_pareto_tradeoff.py"
echo "  Input  : results/exp1/ (5 files) + results/exp2/ (PB-NSGA, VNS-TS, GWO-HD)"
echo "  Output : results/exp2/exp2_pareto_tradeoff.pdf → paper/figures/exp2_pareto_tradeoff.pdf"

cd "$PROJECT_DIR"
"$PYTHON" src/scripts/exp2_pareto_tradeoff.py \
    --results-exp2 "$RES2" \
    --results-exp1 "$RES1" \
    --out-dir      "$RES2"

require_file "$RES2/exp2_pareto_tradeoff.pdf"
cp "$RES2/exp2_pareto_tradeoff.pdf" "$FIG_DIR/exp2_pareto_tradeoff.pdf"
echo "  -> Synced: paper/figures/exp2_pareto_tradeoff.pdf"
echo ""

# ── Phase 4: Figure 3 — CV_large_solution_map.pdf ────────────────────────────

echo "[Phase 4] Generating CV_large_solution_map.pdf..."
echo "  Script : src/scripts/exp2_map_solution.py"
echo "  Input  : data/cv/cv_large_drnd.json + results/exp2/cv_large_seed0.json"
echo "  Output : paper/figures/CV_large_solution_map.pdf (written directly)"

cd "$PROJECT_DIR"
"$PYTHON" src/scripts/exp2_map_solution.py \
    --instance "$PROJECT_DIR/data/cv/cv_large_drnd.json" \
    --result   "$RES2/cv_large_seed0.json" \
    --out      "$FIG_DIR/CV_large_solution_map.pdf"

require_file "$FIG_DIR/CV_large_solution_map.pdf"
echo "  -> Written: paper/figures/CV_large_solution_map.pdf"
echo ""

# ── Phase 5: Verify All Three Figures Are Present ────────────────────────────

echo "[Phase 5] Verifying paper/figures/ contents..."
for f in "saa_convergence.pdf" "exp2_pareto_tradeoff.pdf" "CV_large_solution_map.pdf"; do
    if [ ! -f "$FIG_DIR/$f" ]; then
        echo "[ERROR] Missing figure: paper/figures/$f"
        exit 1
    fi
    echo "  OK: paper/figures/$f"
done
echo ""

# ── Phase 6: LaTeX Compilation (4-pass) ──────────────────────────────────────

echo "[Phase 6] Compiling paper/main.tex (pdflatex → bibtex → pdflatex × 2)..."
cd "$PAPER"

echo "  [6a] pdflatex pass 1..."
pdflatex -interaction=nonstopmode main 2>&1 | tail -5
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "[ERROR] pdflatex pass 1 failed. Check paper/main.log for details."
    exit 1
fi

echo "  [6b] bibtex..."
bibtex main 2>&1 | tail -5
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "[ERROR] bibtex failed. Check paper/main.blg for details."
    exit 1
fi

echo "  [6c] pdflatex pass 2..."
pdflatex -interaction=nonstopmode main 2>&1 | tail -5
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "[ERROR] pdflatex pass 2 failed. Check paper/main.log for details."
    exit 1
fi

echo "  [6d] pdflatex pass 3 (final)..."
pdflatex -interaction=nonstopmode main 2>&1 | tail -5
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "[ERROR] pdflatex pass 3 failed. Check paper/main.log for details."
    exit 1
fi

# Scan for fatal LaTeX errors in the log
if grep -q "^!" main.log 2>/dev/null; then
    echo ""
    echo "[ERROR] Fatal LaTeX errors detected in paper/main.log:"
    grep -A3 "^!" main.log | head -40
    exit 1
fi

require_file "$PAPER/main.pdf"
echo "  Compilation successful: paper/main.pdf"
echo ""

# ── Phase 7: Package the Zip ─────────────────────────────────────────────────

echo "[Phase 7] Packaging submission zip..."
echo "  Contents: main.tex, cite-class.bib, llncs.cls, main.bbl, figures/"

cd "$PAPER"
ZIP_PATH="$SUBMISSION/mypaper419.zip"
rm -f "$ZIP_PATH"

# Explicit file list — no wildcard to avoid including build artifacts or drafts.
# main.bbl is included so bibliography renders correctly even if the conference's
# bibtex version differs from the one used here.
zip -r "$ZIP_PATH" \
    main.tex        \
    cite-class.bib  \
    llncs.cls       \
    main.bbl        \
    figures/

if [ $? -ne 0 ]; then
    echo "[ERROR] zip failed."
    exit 1
fi

# Copy the standalone PDF (EasyChair requires it as a separate upload)
cp "$PAPER/main.pdf" "$SUBMISSION/paper419_main.pdf"
echo "  Copied: submission/paper419_main.pdf"
echo ""

# ── Phase 8: Summary & Manifest ──────────────────────────────────────────────

PDF_SIZE=$(du -h "$SUBMISSION/paper419_main.pdf" | cut -f1)
ZIP_SIZE=$(du -h "$SUBMISSION/mypaper419.zip" | cut -f1)

echo "============================================================"
echo " SUBMISSION ARTIFACTS READY"
echo "============================================================"
echo "  ZIP  ($ZIP_SIZE) : submission/mypaper419.zip"
echo "  PDF  ($PDF_SIZE) : submission/paper419_main.pdf"
echo ""
echo " EasyChair upload fields:"
echo "  Zip file                : mypaper419.zip"
echo "  PDF file                : paper419_main.pdf"
echo "  Main LaTeX file         : main.tex"
echo "  Program for main file   : pdflatex"
echo "  Program for bibliography: bibtex"
echo ""
echo " *** Upload signed copyright form separately ***"
echo "============================================================"
echo ""
echo "Zip contents:"
zip -sf "$ZIP_PATH"
