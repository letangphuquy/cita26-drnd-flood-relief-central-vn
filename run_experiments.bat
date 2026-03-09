@echo off
REM run_experiments.bat — Full experiment pipeline
REM ============================================================
REM Central Vietnam Relief Network Design (MO-IHLNDP)
REM ------------------------------------------------------------
REM Narrative:
REM   Experiment 1: Baseline Comparison on CV-Small
REM   Experiment 2: Case Study & Insights on CV-Large
REM ============================================================

SET "PROJECT=%~dp0"

REM Usage:
REM   run_experiments.bat          — full run
REM   run_experiments.bat data     — regenerate datasets only
REM   run_experiments.bat analyze  — run analysis only

IF "%1"=="data" (
    echo Regenerating datasets...
    SET "PYTHON=.venv\Scripts\python.exe"
    IF NOT EXIST "%PYTHON%" SET "PYTHON=python"
    "%PYTHON%" src\scripts\generate_cv.py --outdir data\cv
    "%PYTHON%" src\scripts\process_benchmark.py --outdir data\benchmark
    echo Datasets ready.
    exit /b 0
)

REM ── EXPERIMENT 1: Baseline Comparison (CV-Small) ──────────────────────────
echo.
echo ^>^>^> Running Experiment 1 (Baselines)...
call "%PROJECT%run_exp1_baselines.bat" %1

REM ── EXPERIMENT 2: Case Study (CV-Large) ───────────────────────────────────
echo.
echo ^>^>^> Running Experiment 2 (Case Study)...
call "%PROJECT%run_exp2_case_study.bat" %1

REM ── ARCHIVED BENCHMARKS (The data is used for a future study) ─────────────
REM Note: Outdated AP and TR81 benchmark runs are preserved here for archival.
REM They are not part of the current narrative but available for future research.
REM REM call "%PROJECT%run_pbnsga.bat" --instances AP TR81
REM ──────────────────────────────────────────────────────────────────────────

echo.
echo ============================================================
echo  All experiments in the current narrative completed.
echo ============================================================
