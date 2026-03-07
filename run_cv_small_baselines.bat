@echo off
REM run_cv_small_baselines.bat
REM ============================================================
REM Runs (or re-runs) the CV-Small baseline experiments:
REM   1. Recompile greedy_baseline.cpp (stochastic multi-restart)
REM   2. Run greedy on cv_small_drnd.json  → results/exp1/cv_small_greedy.json
REM   3. Run MILP (10 min/step, 9 steps)   → results/exp1/cv_small_milp.json
REM   4. Evaluate all baselines + PB-NSGA  → results/exp1/cv_small_metrics.csv
REM
REM Usage:
REM   run_cv_small_baselines.bat            -- full run
REM   run_cv_small_baselines.bat analyze    -- skip solver runs, just evaluate
REM ============================================================

setlocal EnableDelayedExpansion

set "PROJECT=%~dp0"
set "DATA_CV=%PROJECT%data\cv\cv_small_drnd.json"
set "RES1=%PROJECT%results\exp1"
set "RES2=%PROJECT%results\exp2"
set "SOLVER_DIR=%PROJECT%solver"

REM Python venv
set "PYTHON=%PROJECT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

if "%1"=="analyze" goto :analyze

REM ── Step 1: Recompile greedy_baseline ──────────────────────────────────────
echo.
echo [Step 1] Compiling greedy_baseline.cpp (stochastic multi-restart)...
g++ -O2 -std=c++17 ^
    "%SOLVER_DIR%\greedy_baseline.cpp" ^
    -o "%SOLVER_DIR%\greedy_baseline.exe"
if !ERRORLEVEL! NEQ 0 (
    echo [Error] Compilation failed. Check g++ is in PATH.
    exit /b 1
)
echo [Step 1] Done.

REM ── Step 2: Run greedy ─────────────────────────────────────────────────────
echo.
echo [Step 2] Running stochastic greedy (500 restarts)...
if not exist "%DATA_CV%" (
    echo [Error] cv_small_drnd.json not found at %DATA_CV%
    echo         Run: python scripts\generate_cv.py --outdir data\cv
    exit /b 1
)
"%SOLVER_DIR%\greedy_baseline.exe" "%DATA_CV%" ^
    --restarts 500 ^
    --seed 42 ^
    --out "%RES1%\cv_small_greedy.json"
if !ERRORLEVEL! NEQ 0 (
    echo [Error] Greedy baseline failed.
    exit /b 1
)
echo [Step 2] Done. Output: %RES1%\cv_small_greedy.json

REM ── Step 3: Fix BB data (copy exp2 → exp1) ────────────────────────────────
echo.
echo [Step 3] Copying BB result from exp2 to exp1...
copy /Y "%RES2%\CV_small_bb.json" "%RES1%\cv_small_bb.json"
echo [Step 3] Done.

REM ── Step 4: Run MILP (10 min per epsilon step, 9 steps) ───────────────────
echo.
echo [Step 4] Running MILP epsilon-constraint (600s per step, 9 steps)...
echo          This may take up to ~90 minutes.
"%PYTHON%" "%SOLVER_DIR%\milp_baseline.py" ^
    --instance "%DATA_CV%" ^
    --out "%RES1%\cv_small_milp.json" ^
    --steps 9
if !ERRORLEVEL! NEQ 0 (
    echo [Warning] MILP run returned non-zero exit. Partial results may be saved.
)
echo [Step 4] Done. Output: %RES1%\cv_small_milp.json

:analyze
REM ── Step 5: Evaluate all algorithms ───────────────────────────────────────
echo.
echo [Step 5] Evaluating all CV-Small baselines...
"%PYTHON%" "%PROJECT%scripts\evaluate_cv_small.py" ^
    --results-exp1 "%RES1%" ^
    --results-exp2 "%RES2%"
echo [Step 5] Done.

echo.
echo ============================================================
echo  CV-Small baseline run complete.
echo  Results: %RES1%\cv_small_metrics.csv
echo ============================================================
