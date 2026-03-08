@echo off
setlocal EnableDelayedExpansion
set "PROJECT=%~dp0"

echo ============================================================
echo  EXPERIMENT 1: END-TO-END PIPELINE (Benchmarks)
echo ============================================================
echo.

echo [Step 1] Recompiling Solvers...
call "%PROJECT%compile.bat"
if !ERRORLEVEL! NEQ 0 (
    echo [Error] Compilation failed.
    exit /b 1
)

echo.
echo [Step 2] Running Baseline Comparisons (CV-Small)...
echo This includes Greedy, BB, and MILP (1000 steps).
call "%PROJECT%run_cv_small_baselines.bat"
if !ERRORLEVEL! NEQ 0 (
    echo [Warning] CV-Small baselines encountered issues.
)

echo.
echo [Step 3] Running PB-NSGA on HLP Benchmarks...
set "SOLVER=%PROJECT%src\solver\solver.exe"
set "DATA_BENCH=%PROJECT%data\hlp-benchmark"
set "RES1=%PROJECT%results\exp1"
set "POP=200"
set "GEN=300"

for %%N in (10 20 25 40 50 100) do (
    echo   - Running AP%%N (Seed 0)...
    "%SOLVER%" "!DATA_BENCH!\AP%%N_drnd.json" --pop %POP% --gen %GEN% --seed 0 --out "!RES1!\AP%%N_seed0.json" 2>NUL
)
echo   - Running TR81 (Seed 0)...
"%SOLVER%" "!DATA_BENCH!\TR81_drnd.json" --pop %POP% --gen %GEN% --seed 0 --out "!RES1!\TR81_seed0.json" 2>NUL

echo.
echo [Step 4] Running Analysis and Metrics Generation...
set "PYTHON=%PROJECT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" "%PROJECT%src\scripts\analyze_exp1.py" "%RES1%" "%RES1%"

echo.
echo [Step 5] Syncing Results to Paper...
if not exist "%PROJECT%paper\figures" mkdir "%PROJECT%paper\figures"
copy /Y "%RES1%\exp1_metrics.csv" "%PROJECT%paper\"
copy /Y "%RES1%\exp1_timing.csv" "%PROJECT%paper\"
copy /Y "%RES1%\figures\*.pdf" "%PROJECT%paper\figures\"

echo.
echo ============================================================
echo  Exp1 Full Pipeline Completed.
echo ============================================================
pause
