@echo off
REM run_exp1_baselines.bat
REM ============================================================
REM Experiment 1: Baseline Comparison on Central Vietnam (CV-Small)
REM ------------------------------------------------------------
REM Benchmarks PB-NSGA against:
REM   1. Greedy Heuristic (Stochastic Multi-Restart)
REM   2. MILP Adaptive Weighted Sum (Exact/Bounded solver)
REM
REM Evaluation Metrics: HV, IGD+, CPU Time
REM ============================================================

SET "PROJECT=%~dp0"
SET "DATA_CV=%PROJECT%data\cv\cv_small_drnd.json"
SET "RES1=%PROJECT%results\exp1"
SET "SOLVER_DIR=%PROJECT%src\solver"

REM Toggle temporary AEGA population adaptation in PB-NSGA step.
REM 1 = on, 0 = off
SET "AEGA_ON=1"

REM Toggle post-run solution audit (structure + consistency checks).
REM 1 = on, 0 = off
SET "AUDIT_ON=1"

REM Python venv
SET "PYTHON=%PROJECT%.venv\Scripts\python.exe"
IF NOT EXIST "%PYTHON%" (
    SET "PYTHON=python"
)

IF NOT EXIST "%RES1%" mkdir "%RES1%"

REM ── Step 1: Recompile greedy_baseline ──────────────────────────────────────
echo.
echo [Step 1] Compiling greedy_baseline.cpp (stochastic multi-restart)...
g++ -O3 -std=c++17 "%SOLVER_DIR%\greedy_baseline.cpp" -o "%SOLVER_DIR%\greedy_baseline.exe"
IF %ERRORLEVEL% NEQ 0 (
    echo [Error] Compilation failed.
    exit /b 1
)

REM ── Step 2: Run Greedy Heuristic (500 restarts) ───────────────────────────
echo.
echo [Step 2] Running Greedy Heuristic (500 restarts)...
"%SOLVER_DIR%\greedy_baseline.exe" "%DATA_CV%" --restarts 500 --seed 42 --out "%RES1%\cv_small_greedy.json"

REM ── Step 3: Run MILP Adaptive Weighted Sum ────────────────────────────────
echo.
echo [Step 3] Running MILP Adaptive Weighted Sum (AWS)...
echo           This may take some time depending on complexity.
"%PYTHON%" "%SOLVER_DIR%\milp_aws_baseline.py" --instance "%DATA_CV%" --out "%RES1%\cv_small_milp_aws.json" --time_limit 600

REM ── Step 3b: Run MILP Epsilon-Constraint Baseline ────────────────────────
echo.
echo [Step 3b] Running MILP Epsilon-Constraint Baseline...
"%PYTHON%" "%SOLVER_DIR%\milp_epsilon.py" --instance "%DATA_CV%" --out "%RES1%\cv_small_milp_eps.json" --time_limit 600 --epsilon_steps 20

REM ── Step 4: Run PB-NSGA (Ours) ─────────────────────────────────────────────
echo.
echo [Step 4] Running PB-NSGA (Ours) on CV-Small...
REM Ensure solver is compiled
IF NOT EXIST "%SOLVER_DIR%\solver.exe" (
    call "%PROJECT%compile.bat"
)

SET "AEGA_ARGS="
IF "%AEGA_ON%"=="1" (
    SET "AEGA_ARGS=--aega-pop --aega-min 120 --aega-max 320 --aega-step 30"
    echo           AEGA: ON  (min=120, max=320, step=30)
) ELSE (
    echo           AEGA: OFF
)

"%SOLVER_DIR%\solver.exe" "%DATA_CV%" --pop 200 --gen 300 --seed 0 --pc 0.98 --pm-high 0.40 --pm-low 0.10 --sbx-eta-rw 1.5 --pm-eta-rw 8 %AEGA_ARGS% --out "%RES1%\cv_small_pb_nsga.json"

REM ── Step 5: Final Comparison Table ────────────────────────────────────────
echo.
echo [Step 5] Generating Comparison Metrics (HV, IGD+)...
"%PYTHON%" "%PROJECT%src\scripts\exp1_evaluate_cv_small.py" --results-exp1 "%RES1%" --ours "%RES1%\cv_small_pb_nsga.json" --greedy "%RES1%\cv_small_greedy.json" --milp-aws "%RES1%\cv_small_milp_aws.json" --milp-eps "%RES1%\cv_small_milp_eps.json"

REM ── Step 6: Audit Solver Outputs (optional) ───────────────────────────────
IF "%AUDIT_ON%"=="1" (
    echo.
    echo [Step 6] Auditing output correctness/completeness...
    "%PYTHON%" "%PROJECT%src\scripts\audit_solution_outputs.py" --instance "%DATA_CV%" --solutions "%RES1%\cv_small_pb_nsga.json" "%RES1%\cv_small_greedy.json" "%RES1%\cv_small_milp_aws.json" "%RES1%\cv_small_milp_eps.json"
)

echo.
echo Experiment 1 (Baselines) Completed.
echo Results saved to: %RES1%\cv_small_metrics.csv
