@echo off
REM run_experiments.bat — Full experiment pipeline
REM ============================================================
REM Central Vietnam Relief Network Design (MO-IHLNDP)
REM ------------------------------------------------------------
REM Narrative:
REM   Experiment 1: Baseline Comparison on CV-Small
REM   Experiment 2: Case Study & Insights on CV-Large
REM
REM Modes:
REM   run_experiments.bat               — full run (compile + data + solve + analyze)
REM   run_experiments.bat data          — regenerate datasets only
REM   run_experiments.bat analyze       — run analysis only (requires existing results/)
REM   run_experiments.bat compile-only  — compile solvers only
REM ============================================================

SET "PROJECT=%~dp0"

IF /I "%1"=="--help" GOTO :show_help
IF /I "%1"=="-h" GOTO :show_help

IF "%1"=="data" (
    echo Regenerating datasets...
    SET "PYTHON=.venv\Scripts\python.exe"
    IF NOT EXIST "%PYTHON%" SET "PYTHON=python"
    "%PYTHON%" src\scripts\data_generate_cv.py --outdir data\cv
    "%PYTHON%" src\scripts\data_process_hlp_benchmark.py --outdir data\benchmark
    echo Datasets ready.
    exit /b 0
)

IF "%1"=="compile-only" (
    echo Compiling solvers...
    call "%PROJECT%compile.bat"
    exit /b 0
)

IF "%1"=="analyze" (
    echo Running analysis on existing results/
    echo.
    echo ^>^>^> Running Analysis for Experiment 1...
    call "%PROJECT%run_exp1_baselines.bat" --instance "%PROJECT%data\cv\cv_small_drnd.json" --results-dir "%PROJECT%results\exp1" --analyze-only
    echo.
    echo ^>^>^> Running Analysis for Experiment 2...
    call "%PROJECT%run_exp2_case_study.bat" --instance "%PROJECT%data\cv\cv_large_drnd.json" --results-dir "%PROJECT%results\exp2" --analyze-only
    echo.
    echo ============================================================
    echo  Analysis complete.
    echo ============================================================
    exit /b 0
)

REM ── EXPERIMENT 1: Baseline Comparison (CV-Small) ──────────────────────────
if not "%1"=="" if /I not "%1"=="--skip-unchanged" (
    echo [Error] Unknown argument: %1
    echo Run with --help for usage.
    exit /b 1
)

echo.
echo ^>^>^> Running Experiment 1 (Baselines)...
if /I "%1"=="--skip-unchanged" (
    call "%PROJECT%run_exp1_baselines.bat" --instance "%PROJECT%data\cv\cv_small_drnd.json" --results-dir "%PROJECT%results\exp1" --skip-unchanged
) else (
    call "%PROJECT%run_exp1_baselines.bat" --instance "%PROJECT%data\cv\cv_small_drnd.json" --results-dir "%PROJECT%results\exp1"
)
if errorlevel 1 exit /b 1

REM ── EXPERIMENT 2: Case Study (CV-Large) ───────────────────────────────────
echo.
echo ^>^>^> Running Experiment 2 (Case Study)...
call "%PROJECT%run_exp2_case_study.bat" --instance "%PROJECT%data\cv\cv_large_drnd.json" --results-dir "%PROJECT%results\exp2"
if errorlevel 1 exit /b 1

REM ── ARCHIVED BENCHMARKS (The data is used for a future study) ─────────────
REM Note: Outdated AP and TR81 benchmark runs are preserved here for archival.
REM They are not part of the current narrative but available for future research.
REM REM call "%PROJECT%run_pbnsga.bat" --instances AP TR81
REM ──────────────────────────────────────────────────────────────────────────

echo.
echo ============================================================
echo  All experiments in the current narrative completed.
echo ============================================================
exit /b 0

:show_help
echo Usage: run_experiments.bat [COMMAND]
echo.
echo Commands:
echo   (none)         - Run full pipeline (compile, generate data, solve, analyze)
echo   data           - Regenerate datasets only
echo   analyze        - Run analysis only (assumes results/ exists)
echo   compile-only   - Compile solvers only
exit /b 0
