@echo off
REM run_exp2_case_study.bat
REM ============================================================
REM Experiment 2: Central Vietnam Case Study, SAA, and OOS Insights
REM
REM Optional flags:
REM   --analyze-only  Skip solver runs; only perform analysis on existing results/
REM ------------------------------------------------------------
REM Runs PB-NSGA on the CV-Large instance across multiple seeds.
REM Generates:
REM   1. Statistical analysis of convergence (HV, IGD+)
REM   2. VNS-TS and GWO-HD baseline fronts for trade-off comparison
REM   3. Pareto trade-off analysis across tracked algorithms
REM   4. Hub selection stability and sensitivity analysis
REM   5. High-fidelity maps of representative solutions
REM   6. End-to-end SAA/OOS robustness evaluation (seed-0 Pareto)
REM ============================================================

SET "PROJECT=%~dp0"
SET "DATA_PREP=%PROJECT%data\prep"
SET "SAA_DATA=%DATA_PREP%\cv_large_saa100.json"
SET "OOS_DATA=%DATA_PREP%\cv_large_oos10.json"
SET "SOLVER_DIR=%PROJECT%src\solver"
SET "DATA_CV="
SET "RES2="

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
    set "RES2=%~2"
    shift
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
if "%RES2%"=="" (
    echo [Error] --instance and --results-dir are required.
    echo Run with --help for usage.
    exit /b 1
)

IF "%ANALYZE_ONLY%"=="1" (
    echo.
    echo [Exp2] Running analysis only on existing results...
    IF NOT EXIST "%RES2%" (
        echo [Error] results\exp2\ not found. Run full experiment first.
        exit /b 1
    )
)

REM Python venv
SET "PYTHON=%PROJECT%.venv\Scripts\python.exe"
IF NOT EXIST "%PYTHON%" (
    SET "PYTHON=python"
)

IF NOT EXIST "%RES2%" mkdir "%RES2%"
IF NOT EXIST "%DATA_PREP%" mkdir "%DATA_PREP%"

IF "%ANALYZE_ONLY%"=="1" GOTO :analysis_steps

REM ── Step 1: Run PB-NSGA (Ours) 20 Seeds ────────────────────────────────────
echo.
echo [Step 1] Running PB-NSGA (20 seeds) on CV-Large...
REM Ensure solver is compiled
IF NOT EXIST "%SOLVER_DIR%\solver.exe" (
    call "%PROJECT%compile.bat"
)

FOR /L %%s IN (0,1,19) DO (
    echo   [Seed %%s] Running...
    "%SOLVER_DIR%\solver.exe" "%DATA_CV%" --pop 200 --gen 500 --seed %%s --out "%RES2%\cv_large_seed%%s.json"
)

REM ── Step 2: Run VNS-TS baseline (literature comparator) ─────────────────
echo.
echo [Step 2] Running VNS-TS baseline (20 seeds) on CV-Large...
IF NOT EXIST "%SOLVER_DIR%\vns_ts_baseline.exe" (
    g++ -std=c++17 -O2 -I"%SOLVER_DIR%" "%SOLVER_DIR%\vns_ts_baseline.cpp" -o "%SOLVER_DIR%\vns_ts_baseline.exe"
)

FOR /L %%s IN (0,1,19) DO (
    echo   [VNS Seed %%s] Running...
    "%SOLVER_DIR%\vns_ts_baseline.exe" "%DATA_CV%" --seed %%s --iter 180 --time-limit 180 --tabu-tenure 7 --kmax 4 --starts 12 --enable-option3 --out "%RES2%\cv_large_vns_ts_seed%%s.json"
)

REM ── Step 2b: Run GWO-HD baseline (literature comparator) ───────────────
echo.
echo [Step 2b] Running GWO-HD baseline (20 seeds) on CV-Large...
IF NOT EXIST "%SOLVER_DIR%\gwo_hd_baseline.exe" (
    g++ -O3 -std=c++17 -I"%SOLVER_DIR%" "%SOLVER_DIR%\gwo_hd_baseline.cpp" -o "%SOLVER_DIR%\gwo_hd_baseline.exe"
)

FOR /L %%s IN (0,1,19) DO (
    echo   [GWO Seed %%s] Running...
    "%SOLVER_DIR%\gwo_hd_baseline.exe" "%DATA_CV%" --out "%RES2%\cv_large_gwo_hd_seed%%s.json" --seed %%s --wolves 30 --iter 560 --time-limit 180 --fracA-start 0.45 --fracA-end 0.06 --fracX-start 0.35 --fracX-end 0.04 --accept-worse 0.03 --stagnation-limit 20 --keep-ratio 0.45 --ps-op-prob 0.35
)

:analysis_steps

REM ── Step 3: Pareto trade-off ───────────────────────────────────────────
echo.
echo [Step 3] Building Pareto trade-off outputs...
"%PYTHON%" "%PROJECT%src\scripts\exp2_pareto_tradeoff.py" --results-exp2 "%RES2%" --results-exp1 "%PROJECT%results\exp1" --out-dir "%RES2%"

REM ── Step 4: Statistical Analysis & Sensitivity ────────────────────────────
echo.
echo [Step 4] Analyzing Stability ^& Scenario Sensitivity...
REM Args: <results_dir> <out_dir> <cv_data_dir> <paper_dir>
"%PYTHON%" "%PROJECT%src\scripts\exp2_analyze_case_study.py" "%RES2%" "%RES2%" "%PROJECT%data\cv" "%PROJECT%paper"

REM ── Step 5: High-Fidelity Mapping ─────────────────────────────────────────
echo.
echo [Step 5] Generating 1x3 Composite Network Map...
REM We pick a representative solution (usually from seed 0 or combined)
"%PYTHON%" "%PROJECT%src\scripts\exp2_map_solution.py" --instance "%DATA_CV%" --result "%RES2%\cv_large_seed0.json" --out "%PROJECT%figures\cv_large_map_detailed.pdf"

REM ── Step 6: Generate SAA/OOS datasets (combinatorial protocol) ──────────
echo.
echo [Step 6] Regenerating SAA/OOS datasets (SAA=100, OOS=10 hard)...
"%PYTHON%" "%PROJECT%src\scripts\data_generate_saa_oos.py" --saa-scenarios 100 --oos-scenarios 10 --out-dir "%DATA_PREP%"

REM ── Step 7: Compile OOS evaluator ────────────────────────────────────────
echo.
echo [Step 7] Preparing evaluate_oos executable...
IF NOT EXIST "%SOLVER_DIR%\evaluate_oos.exe" (
    g++ -O2 -std=c++17 "%SOLVER_DIR%\evaluate_oos.cpp" -o "%SOLVER_DIR%\evaluate_oos.exe"
)

REM ── Step 8: Evaluate seed-0 Pareto on SAA/OOS ────────────────────────────
echo.
echo [Step 8] Evaluating seed-0 Pareto on SAA and OOS sets...
"%SOLVER_DIR%\evaluate_oos.exe" "%SAA_DATA%" "%RES2%\cv_large_seed0.json" "%RES2%\CV_large_seed0_saa_eval.json"
"%SOLVER_DIR%\evaluate_oos.exe" "%OOS_DATA%" "%RES2%\cv_large_seed0.json" "%RES2%\CV_large_seed0_oos_eval.json"

REM ── Step 9: Summarize SAA/OOS robustness ─────────────────────────────────
echo.
echo [Step 9] Summarizing SAA/OOS diagnostics...
"%PYTHON%" "%PROJECT%src\scripts\exp2_analyze_saa_oos.py" --saa-eval "%RES2%\CV_large_seed0_saa_eval.json" --oos-eval "%RES2%\CV_large_seed0_oos_eval.json" --out "%RES2%\exp2_saa_oos_summary.json"

echo.
echo Experiment 2 (Case Study) Completed.
echo Results saved to: %RES2%\
echo Map saved to: figures\cv_large_map_detailed.pdf
echo Trade-off outputs: %RES2%\exp2_tradeoff_pareto.csv, %RES2%\exp2_pareto_tradeoff.pdf
echo Tracked algorithms in Exp2: PB-NSGA, VNS-TS, GWO-HD
echo SAA/OOS summary saved to: %RES2%\exp2_saa_oos_summary.json
exit /b 0

:show_help
echo Usage: run_exp2_case_study.bat --instance ^<cv_large.json^> --results-dir ^<dir^> [--analyze-only]
echo.
echo Required:
echo   --instance ^<path^>     CV-Large instance JSON
echo   --results-dir ^<path^>  Output directory for result files
echo.
echo Flags:
echo   --analyze-only  Skip solver runs; only perform analysis on existing results/
exit /b 0
