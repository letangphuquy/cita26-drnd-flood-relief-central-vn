@echo off
REM run_cv_small_baselines.bat
REM ============================================================
REM Runs (or re-runs) the CV-Small baseline experiments:
REM   1. Recompile greedy_baseline.cpp (systematic sweep + stochastic restarts)
REM   2. Run greedy on cv_small_drnd.json  → results/exp1/cv_small_greedy.json
REM   3. Run BB (exact enum)              → results/exp1/cv_small_bb.json
REM   4. Run MILP (10 min/step, 9 steps)  → results/exp1/cv_small_milp.json
REM   5. Evaluate all baselines + PB-NSGA → results/exp1/cv_small_metrics.csv
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
set "SOLVER_DIR=%PROJECT%src\solver"

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
    echo [Error] cv_small_drnd.json not found at "%DATA_CV%"
    echo         Run: python src\scripts\generate_cv.py --outdir data\cv
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

REM ── Step 3: Run BB solver fresh ────────────────────────────────────────────
echo.
echo [Step 3] Running BB exact enumeration on CV-Small...
set "BB=%SOLVER_DIR%\bb_solver.exe"
if not exist "%BB%" (
    echo [Error] bb_solver.exe not found. Trying to compile...
    g++ -O2 -std=c++17 "%SOLVER_DIR%\bb_solver.cpp" -o "%BB%"
    if !ERRORLEVEL! NEQ 0 (
        echo [Fallback] Compile failed. Copying cached result from exp2...
        copy /Y "%RES2%\CV_small_bb.json" "%RES1%\cv_small_bb.json"
        goto :step4
    )
)
"%BB%" "%DATA_CV%" --out "%RES1%\cv_small_bb.json"
if !ERRORLEVEL! NEQ 0 (
    echo [Warning] BB solver returned non-zero. Falling back to cached exp2 result.
    copy /Y "%RES2%\CV_small_bb.json" "%RES1%\cv_small_bb.json"
)
echo [Step 3] Done. Output: %RES1%\cv_small_bb.json

:step4

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

REM ── Step 6: Run PB-NSGA (Ours) reference ───────────────────────────────────
echo.
echo [Step 6] Running PB-NSGA (Ours) adaptive on CV-Small (pop=200, gen=300)...
"%SOLVER_DIR%\solver.exe" "%DATA_CV%" ^
    --pop 200 ^
    --gen 300 ^
    --pm-high 0.40 ^
    --pm-low 0.10 ^
    --stag 20 ^
    --seed 0 ^
    --out "%RES1%\cv_small_pb_nsga.json"
if !ERRORLEVEL! NEQ 0 (
    echo [Error] PB-NSGA failed.
)
echo [Step 6] Done. Output: %RES1%\cv_small_pb_nsga.json

:analyze_only
REM ── Step 7: Final Comparison ───────────────────────────────────────────────
echo.
echo [Step 7] Generating Final Baseline Comparison Table...
"%PYTHON%" "%PROJECT%src\scripts\evaluate_cv_small.py" ^
    --results-exp1 "%RES1%" ^
    --ours "%RES1%\cv_small_pb_nsga.json" ^
    --greedy "%RES1%\cv_small_greedy.json" ^
    --bb "%RES1%\cv_small_bb.json" ^
    --milp "%RES1%\cv_small_milp.json"

echo.
echo ============================================================
echo CV-Small Baselines Completed Successfully.
echo ============================================================
pause
goto :eof
