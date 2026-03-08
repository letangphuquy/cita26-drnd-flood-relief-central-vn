@echo off
REM run_experiments.bat — Full experiment pipeline
REM
REM Usage:
REM   run_experiments.bat          — full paper run (pop=200, gen=300, 20 seeds)
REM   run_experiments.bat quick    — smoke test      (pop=30,  gen=50,  3 seeds)
REM   run_experiments.bat data     — regenerate datasets only
REM   run_experiments.bat analyze  — re-run analysis on existing results
REM
REM Directory layout:
REM   data\benchmark\    — HLP → DRND processed instances (AP*, TR81)
REM   data\cv\           — Central Vietnam instances (cv_small, cv_large)
REM   results\exp1\      — Experiment 1 outputs (benchmarks)
REM   results\exp2\      — Experiment 2 outputs (case study CV)
REM   scripts\           — Python analysis scripts
REM   src\solver\        — C++ solvers (solver.exe, bb_solver.exe)
REM
REM Experiment 1 — Algorithm Benchmarking
REM   Step 1a: BB complete enumeration on AP10/20/25/40 (ground-truth Pareto)
REM   Step 1b: PB-NSGA on all instances, 20 seeds each
REM   Step 1c: Analysis — metrics table + stress-test timing chart
REM
REM Experiment 2 — Case Study: Central Vietnam
REM   Step 2a: PB-NSGA on CV-Small and CV-Large, 20 seeds each
REM   Step 2b: Analysis — sensitivity, hub stability, map visualisation

setlocal EnableDelayedExpansion

set "PROJECT=%~dp0"
set "SOLVER=%PROJECT%src\solver\solver.exe"
set "BB=%PROJECT%src\solver\bb_solver.exe"

REM Canonical dataset directories
set "DATA_BENCH=%PROJECT%data\hlp-benchmark"
set "DATA_CV=%PROJECT%data\cv"

REM Results directories
set "RES1=%PROJECT%results\exp1"
set "RES2=%PROJECT%results\exp2"

REM Python scripts
set "SCRIPT_EXP1=%PROJECT%src\scripts\analyze_exp1.py"
set "SCRIPT_EXP2=%PROJECT%src\scripts\analyze_exp2.py"

REM Create output directories
if not exist "%DATA_BENCH%" mkdir "%DATA_BENCH%"
if not exist "%DATA_CV%"    mkdir "%DATA_CV%"
if not exist "%RES1%\figures"       mkdir "%RES1%\figures"
if not exist "%RES2%\figures"       mkdir "%RES2%\figures"
if not exist "%RES2%\maps"          mkdir "%RES2%\maps"

REM ── Parameter mode ─────────────────────────────────────────────────────────
set "POP=200"
set "GEN=300"
set "SEEDS=0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19"
set "BB_TIME=1800"
set "PM_HIGH=0.40"
set "PM_LOW=0.10"

if "%1"=="quick" (
    set "POP=30"
    set "GEN=50"
    set "SEEDS=0 1 2"
    set "BB_TIME=120"
    set "PM_HIGH=0.40"
    set "PM_LOW=0.10"
    echo [Mode] Quick smoke test: pop=!POP! gen=!GEN! seeds=3
    goto :dataset_check
)
if "%1"=="data" (
    echo [Mode] Dataset generation only.
    goto :gen_datasets
)
if "%1"=="analyze" (
    echo [Mode] Analysis only — skipping solver runs.
    goto :analyze
)
echo [Mode] Full run: pop=%POP% gen=%GEN% pm=%PM_HIGH%^>%PM_LOW% seeds=20

REM ── Solver availability check ───────────────────────────────────────────────
:dataset_check
if not exist "%SOLVER%" (
    echo [Error] solver.exe not found.
    echo         Compile: g++ -O2 -std=c++17 src\solver\main.cpp -o src\solver\solver.exe
    exit /b 1
)
if not exist "%BB%" (
    echo [Error] bb_solver.exe not found.
    echo         Compile: g++ -O2 -std=c++17 src\solver\bb_solver.cpp -o src\solver\bb_solver.exe
    exit /b 1
)
set "GREEDY=%PROJECT%src\solver\greedy_baseline.exe"
if not exist "%GREEDY%" (
    echo [Warning] greedy_baseline.exe not found - greedy runs will be skipped.
    echo           Compile: g++ -O2 -std=c++17 src\solver\greedy_baseline.cpp -o src\solver\greedy_baseline.exe
)

REM ══════════════════════════════════════════════════════════════════════════
REM DATASET GENERATION
REM ══════════════════════════════════════════════════════════════════════════
:gen_datasets
echo.
echo ============================================================
echo  Generating / verifying datasets
echo ============================================================

REM Benchmark instances (HLP → DRND) via scripts\process_benchmark.py
set "BENCH_SCRIPT=%PROJECT%src\scripts\process_benchmark.py"
if not exist "%BENCH_SCRIPT%" (
    echo [Error] src\scripts\process_benchmark.py not found.
    exit /b 1
)
python "%BENCH_SCRIPT%" --outdir "%DATA_BENCH%"
echo [Datasets] Benchmark instances written to %DATA_BENCH%

REM CV instances via scripts\generate_cv.py
set "CV_SCRIPT=%PROJECT%src\scripts\generate_cv.py"
if not exist "%CV_SCRIPT%" (
    echo [Error] src\scripts\generate_cv.py not found.
    exit /b 1
)
python "%CV_SCRIPT%" --outdir "%DATA_CV%"
echo [Datasets] CV instances written to %DATA_CV%

if "%1"=="data" goto :end

REM ══════════════════════════════════════════════════════════════════════════
REM EXPERIMENT 1 — Algorithm Benchmarking
REM ══════════════════════════════════════════════════════════════════════════
echo.
echo ============================================================
echo  EXPERIMENT 1: Algorithm Benchmarking
echo ============================================================

REM ── 1a. BB complete enumeration (ground-truth Pareto fronts) ───────────────
echo.
echo --- Exp1a: Complete enumeration (ground-truth Pareto fronts) ---
for %%N in (10 20 25 40) do (
    set "INST=%DATA_BENCH%\AP%%N_drnd.json"
    set "OUT=%RES1%\AP%%N_bb.json"
    if exist "!INST!" (
        echo [BB AP%%N] Running...
        "%BB%" "!INST!" --out "!OUT!" --mode enum --trials 500 --time-limit %BB_TIME%
        if !ERRORLEVEL!==0 (echo [BB AP%%N] Done.) else (echo [BB AP%%N] FAILED/Timeout)
    ) else (
        echo [BB AP%%N] Instance not found: !INST! — check data\benchmark\
    )
)

REM ── 1b. PB-NSGA on all benchmark instances (20 seeds) ─────────────────────
echo.
echo --- Exp1b: PB-NSGA (20 seeds per instance) ---
for %%N in (10 20 25 40 50 100) do (
    set "INST=%DATA_BENCH%\AP%%N_drnd.json"
    if exist "!INST!" (
        echo [PB-NSGA AP%%N] Running %POP%x%GEN%, seeds...
        for %%R in (%SEEDS%) do (
            "%SOLVER%" "!INST!" --pop %POP% --gen %GEN% --seed %%R ^
                --out "%RES1%\AP%%N_seed%%R.json"
        )
        echo [PB-NSGA AP%%N] Done.
    ) else (
        echo [AP%%N] Instance not found: !INST!
    )
)

if exist "%DATA_BENCH%\TR81_drnd.json" (
    echo [PB-NSGA TR81] Running %POP%x%GEN%, seeds...
    for %%R in (%SEEDS%) do (
        "%SOLVER%" "%DATA_BENCH%\TR81_drnd.json" --pop %POP% --gen %GEN% --seed %%R ^
            --out "%RES1%\TR81_seed%%R.json"
    )
    echo [PB-NSGA TR81] Done.
) else (
    echo [TR81] Instance not found: %DATA_BENCH%\TR81_drnd.json
)

REM ══════════════════════════════════════════════════════════════════════════
REM EXPERIMENT 2 — Case Study: Central Vietnam
REM ══════════════════════════════════════════════════════════════════════════
echo.
echo ============================================================
echo  EXPERIMENT 2: Case Study — Central Vietnam
echo ============================================================

for %%G in (small large) do (
    set "INST=%DATA_CV%\cv_%%G_drnd.json"
    if exist "!INST!" (
        echo [CV-%%G] Running PB-NSGA %POP%x%GEN%, seeds...
        for %%R in (%SEEDS%) do (
            "%SOLVER%" "!INST!" --pop %POP% --gen %GEN% --seed %%R ^
                --out "%RES2%\CV_%%G_seed%%R.json"
        )
        echo [CV-%%G] Done.
    ) else (
        echo [CV-%%G] Instance not found: !INST!
        echo          Run: python src\scripts\generate_cv.py --outdir data\cv
    )
)

REM ══════════════════════════════════════════════════════════════════════════
REM ANALYSIS AND VISUALISATION
REM ══════════════════════════════════════════════════════════════════════════
:analyze
echo.
echo ============================================================
echo  Analysis and Visualisation
echo ============================================================

echo.
echo --- Exp1 Analysis ---
python "%SCRIPT_EXP1%" "%RES1%" "%RES1%"

echo.
echo --- Exp2 Analysis ---
python "%SCRIPT_EXP2%" "%RES2%" "%RES2%" "%DATA_CV%"

echo.
echo --- CV-Small Baseline Evaluation (Greedy / MILP / BB vs PB-NSGA) ---
python "%PROJECT%src\scripts\evaluate_cv_small.py" ^
    --results-exp1 "%RES1%" ^
    --results-exp2 "%RES2%"

:end
echo.
echo ============================================================
echo  Pipeline complete.
echo  Exp1 results : %RES1%
echo  Exp2 results : %RES2%
echo ============================================================
