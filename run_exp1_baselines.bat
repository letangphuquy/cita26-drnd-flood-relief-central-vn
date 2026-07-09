@echo off
REM run_exp1_baselines.bat
REM ============================================================

REM Optional flags:
REM   --skip-unchanged   Skip compile/run steps whose outputs are newer than inputs
REM   --analyze-only     Skip solver runs; only perform analysis on existing results/
REM Experiment 1: Baseline Comparison on Central Vietnam (CV-Small)
REM ------------------------------------------------------------
REM Benchmarks PB-NSGA against:
REM   1. Greedy Heuristic (Stochastic Multi-Restart)
REM   2. MILP Adaptive Weighted Sum (Exact/Bounded solver)
REM
REM Evaluation Metrics: HV, IGD+, CPU Time
REM ============================================================

SET "PROJECT=%~dp0"
SET "SOLVER_DIR=%PROJECT%src\solver"
SET "DATA_CV="
SET "RES1="

SET "SKIP_UNCHANGED=0"
SET "ANALYZE_ONLY=0"
if "%~1"=="" goto :after_args
:parse_args
if "%~1"=="" goto :after_args
if /I "%~1"=="--instance" (
    if "%~2"=="" goto :missing_value
    set "DATA_CV=%~2"
    shift
    shift
    goto :parse_args
)
if /I "%~1"=="--results-dir" (
    if "%~2"=="" goto :missing_value
    set "RES1=%~2"
    shift
    shift
    goto :parse_args
)
if /I "%~1"=="--skip-unchanged" (
    set "SKIP_UNCHANGED=1"
    shift
    goto :parse_args
)
if /I "%~1"=="--analyze-only" (
    set "ANALYZE_ONLY=1"
    shift
    goto :parse_args
)
if /I "%~1"=="--help" goto :show_help
if /I "%~1"=="-h" goto :show_help
echo [Error] Unknown argument: %~1
echo Run with --help for usage.
exit /b 1

:missing_value
echo [Error] Missing value for %~1
echo Run with --help for usage.
exit /b 1

:after_args
if "%DATA_CV%"=="" (
    echo [Error] --instance and --results-dir are required.
    echo Run with --help for usage.
    exit /b 1
)
if "%RES1%"=="" (
    echo [Error] --instance and --results-dir are required.
    echo Run with --help for usage.
    exit /b 1
)

REM Toggle temporary AEGA population adaptation in PB-NSGA step.
REM 1 = on, 0 = off
SET "AEGA_ON=0"

REM Toggle post-run solution audit (structure + consistency checks).
REM 1 = on, 0 = off
SET "AUDIT_ON=1"

REM Python venv
SET "PYTHON=%PROJECT%.venv\Scripts\python.exe"
IF NOT EXIST "%PYTHON%" (
    SET "PYTHON=python"
)

IF "%ANALYZE_ONLY%"=="1" (
    echo.
    echo [Exp1] Running analysis only on existing results...
    IF NOT EXIST "%RES1%" (
        echo [Error] results\exp1\ not found. Run full experiment first.
        exit /b 1
    )
    GOTO :analysis_steps
)

IF NOT EXIST "%RES1%" mkdir "%RES1%"

REM ── Step 1: Recompile greedy_baseline ──────────────────────────────────────
echo.
echo [Step 1] Compiling greedy_baseline.cpp (stochastic multi-restart)...
CALL :ShouldRun "%SOLVER_DIR%\greedy_baseline.exe" "%SOLVER_DIR%\greedy_baseline.cpp"
IF %ERRORLEVEL% EQU 0 (
    g++ -O3 -std=c++17 "%SOLVER_DIR%\greedy_baseline.cpp" -o "%SOLVER_DIR%\greedy_baseline.exe"
    IF %ERRORLEVEL% NEQ 0 (
        echo [Error] Compilation failed.
        exit /b 1
    )
) ELSE (
    echo [Skip] greedy_baseline compile unchanged.
)

REM ── Step 2: Run Greedy Heuristic (500 restarts) ───────────────────────────
echo.
echo [Step 2] Running Greedy Heuristic (500 restarts)...
CALL :ShouldRun "%RES1%\cv_small_greedy.json" "%SOLVER_DIR%\greedy_baseline.exe" "%DATA_CV%"
IF %ERRORLEVEL% EQU 0 (
    "%SOLVER_DIR%\greedy_baseline.exe" "%DATA_CV%" --restarts 500 --seed 42 --out "%RES1%\cv_small_greedy.json"
) ELSE (
    echo [Skip] Greedy run unchanged.
)

REM ── Step 2b: BB-Exact baseline (disabled) ───────────────────────────────
echo.
echo [Step 2b] BB-Exact baseline is disabled (not tracked).

REM ── Step 2c: Recompile + Run VNS-TS baseline ───────────────────────────
echo.
echo [Step 2c] Compiling and running VNS-TS baseline...
CALL :ShouldRun "%SOLVER_DIR%\vns_ts_baseline.exe" "%SOLVER_DIR%\vns_ts_baseline.cpp"
IF %ERRORLEVEL% EQU 0 (
    g++ -O3 -std=c++17 "%SOLVER_DIR%\vns_ts_baseline.cpp" -o "%SOLVER_DIR%\vns_ts_baseline.exe"
    IF %ERRORLEVEL% NEQ 0 (
        echo [Error] VNS-TS compilation failed.
        exit /b 1
    )
) ELSE (
    echo [Skip] VNS-TS compile unchanged.
)
CALL :ShouldRun "%RES1%\cv_small_vns_ts.json" "%SOLVER_DIR%\vns_ts_baseline.exe" "%DATA_CV%"
IF %ERRORLEVEL% EQU 0 (
    "%SOLVER_DIR%\vns_ts_baseline.exe" "%DATA_CV%" --out "%RES1%\cv_small_vns_ts.json" --seed 42 --iter 120 --time-limit 60 --tabu-tenure 5 --kmax 4 --starts 12 --enable-option3
) ELSE (
    echo [Skip] VNS-TS run unchanged.
)

REM ── Step 2d: Recompile + Run GWO-HD baseline ───────────────────────────
echo.
echo [Step 2d] Compiling and running GWO-HD baseline...
CALL :ShouldRun "%SOLVER_DIR%\gwo_hd_baseline.exe" "%SOLVER_DIR%\gwo_hd_baseline.cpp"
IF %ERRORLEVEL% EQU 0 (
    g++ -O3 -std=c++17 "%SOLVER_DIR%\gwo_hd_baseline.cpp" -o "%SOLVER_DIR%\gwo_hd_baseline.exe"
    IF %ERRORLEVEL% NEQ 0 (
        echo [Error] GWO-HD compilation failed.
        exit /b 1
    )
) ELSE (
    echo [Skip] GWO-HD compile unchanged.
)
CALL :ShouldRun "%RES1%\cv_small_gwo_hd.json" "%SOLVER_DIR%\gwo_hd_baseline.exe" "%DATA_CV%"
IF %ERRORLEVEL% EQU 0 (
    "%SOLVER_DIR%\gwo_hd_baseline.exe" "%DATA_CV%" --out "%RES1%\cv_small_gwo_hd.json" --seed 42 --wolves 30 --iter 560 --time-limit 140 --fracA-start 0.45 --fracA-end 0.06 --fracX-start 0.35 --fracX-end 0.04 --accept-worse 0.03 --stagnation-limit 20 --keep-ratio 0.45 --ps-op-prob 0.35
) ELSE (
    echo [Skip] GWO-HD run unchanged.
)

REM ── Step 3: Run MILP Adaptive Weighted Sum ────────────────────────────────
echo.
echo [Step 3] Running MILP Adaptive Weighted Sum (AWS)...
echo           This may take some time depending on complexity.
CALL :ShouldRun "%RES1%\cv_small_milp_aws.json" "%SOLVER_DIR%\milp_aws_baseline.py" "%DATA_CV%"
IF %ERRORLEVEL% EQU 0 (
    "%PYTHON%" "%SOLVER_DIR%\milp_aws_baseline.py" --instance "%DATA_CV%" --out "%RES1%\cv_small_milp_aws.json" --time_limit 600
) ELSE (
    echo [Skip] MILP AWS run unchanged.
)

REM ── Step 3b: MILP Epsilon-Constraint baseline (disabled) ─────────────────
echo.
echo [Step 3b] MILP EPS baseline is disabled (not tracked).

REM ── Step 4: Run PB-NSGA (Ours) ─────────────────────────────────────────────
echo.
echo [Step 4] Running PB-NSGA (Ours) on CV-Small...
REM Ensure solver is compiled
IF NOT EXIST "%SOLVER_DIR%\solver.exe" (
    call "%PROJECT%compile.bat"
)

SET "AEGA_ARGS="
IF "%AEGA_ON%"=="1" (
    SET "AEGA_ARGS=--aega-pop --aega-min 220 --aega-max 280 --aega-step 10"
    echo          AEGA: ON  (min=220, max=280, step=10)
) ELSE (
    echo           AEGA: OFF
)

CALL :ShouldRun "%RES1%\cv_small_pb_nsga.json" "%SOLVER_DIR%\solver.exe" "%DATA_CV%" "%SOLVER_DIR%\main.cpp" "%SOLVER_DIR%\nsga2.hpp" "%SOLVER_DIR%\representation.hpp"
IF %ERRORLEVEL% EQU 0 (
    "%SOLVER_DIR%\solver.exe" "%DATA_CV%" --pop 200 --gen 300 --seed 15 --pc 0.98 --pm-high 0.40 --pm-low 0.10 --sbx-eta-rw 1.5 --pm-eta-rw 8 %AEGA_ARGS% --out "%RES1%\cv_small_pb_nsga.json"
) ELSE (
    echo [Skip] PB-NSGA run unchanged.
)

:analysis_steps
REM ── Step 5: Final Comparison Table ────────────────────────────────────────
echo.
echo [Step 5] Generating Comparison Metrics (HV, IGD+)...
CALL :ShouldRun "%RES1%\cv_small_metrics.csv" "%PROJECT%src\scripts\exp1_evaluate_cv_small.py" "%RES1%\cv_small_pb_nsga.json" "%RES1%\cv_small_vns_ts.json" "%RES1%\cv_small_gwo_hd.json" "%RES1%\cv_small_greedy.json" "%RES1%\cv_small_milp_aws.json"
IF %ERRORLEVEL% EQU 0 (
    "%PYTHON%" "%PROJECT%src\scripts\exp1_evaluate_cv_small.py" --results-exp1 "%RES1%" --ours "%RES1%\cv_small_pb_nsga.json" --vns-ts "%RES1%\cv_small_vns_ts.json" --gwo-hd "%RES1%\cv_small_gwo_hd.json" --greedy "%RES1%\cv_small_greedy.json" --milp-aws "%RES1%\cv_small_milp_aws.json"
) ELSE (
    echo [Skip] Metrics evaluation unchanged.
)

REM ── Step 6: Audit Solver Outputs (optional) ───────────────────────────────
IF "%AUDIT_ON%"=="1" (
    echo.
    echo [Step 6] Auditing output correctness/completeness...
    "%PYTHON%" "%PROJECT%src\scripts\audit_solution_outputs.py" --instance "%DATA_CV%" --solutions "%RES1%\cv_small_pb_nsga.json" "%RES1%\cv_small_vns_ts.json" "%RES1%\cv_small_gwo_hd.json" "%RES1%\cv_small_greedy.json" "%RES1%\cv_small_milp_aws.json"
)

echo.
echo Experiment 1 (Baselines) Completed.
echo Results saved to: %RES1%\cv_small_metrics.csv
exit /b 0

:show_help
echo Usage: run_exp1_baselines.bat --instance ^<cv_small.json^> --results-dir ^<dir^> [--skip-unchanged] [--analyze-only]
echo.
echo Required:
echo   --instance ^<path^>     CV-Small instance JSON
echo   --results-dir ^<path^>  Output directory for result files and metrics CSV
echo.
echo Flags:
echo   --skip-unchanged  Skip compile/run steps whose outputs are newer than inputs
echo   --analyze-only    Skip solver runs; only perform analysis on existing results/
exit /b 0

:ShouldRun
if "%SKIP_UNCHANGED%" NEQ "1" exit /b 0
if not exist "%~1" exit /b 0
set "OUT=%~f1"
shift
:ShouldRunLoop
if "%~1"=="" exit /b 1
if not exist "%~1" exit /b 0
powershell -NoProfile -Command "if ((Get-Item '%~f1').LastWriteTimeUtc -gt (Get-Item '%OUT%').LastWriteTimeUtc) { exit 0 } else { exit 1 }"
if %ERRORLEVEL% EQU 0 exit /b 0
shift
goto :ShouldRunLoop
