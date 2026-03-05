@echo off
REM run_experiments.bat — Full experiment pipeline
REM
REM Usage: run_experiments.bat [quick]
REM   quick: pop=30, gen=50  (smoke test, ~2 min)
REM   default: pop=100, gen=200  (full paper quality, ~hours)
REM
REM Experiments:
REM   Exp 1 — Algorithm efficiency (BB-Exact vs PB-NSGA-II) on HLP benchmarks
REM           BB-Exact: AP10, AP20, AP25, AP40, CV-Small (exact enumeration)
REM           PB-NSGA-II: all instances, 20 seeds each
REM   Exp 2 — Case study Central Vietnam (PB-NSGA-II only, 20 seeds)

setlocal EnableDelayedExpansion
set "PROJECT=%~dp0"
set "SOLVER=%PROJECT%solver_cpp\solver.exe"
set "BB=%PROJECT%solver_cpp\bb_solver.exe"
set "DATA=%PROJECT%hlp-dataset"
set "DATA_CV=%PROJECT%data_prep"
set "RESULTS=%PROJECT%results"

if not exist "%RESULTS%" mkdir "%RESULTS%"
if not exist "%RESULTS%\figures" mkdir "%RESULTS%\figures"

REM ── Parameter mode ────────────────────────────────────────────────────────
set "POP=100"
set "GEN=200"
set "SEEDS=0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19"
set "BB_TIME=1800"
if "%1"=="quick" (
    set "POP=30"
    set "GEN=50"
    set "SEEDS=0 1 2"
    set "BB_TIME=120"
    echo [Mode] Quick test: pop=!POP! gen=!GEN! seeds=3
) else (
    echo [Mode] Full run: pop=%POP% gen=%GEN% seeds=20
)

REM Check solvers
if not exist "%SOLVER%" (
    echo [Error] solver.exe not found. Compile first: g++ -O2 -std=c++17 main.cpp -o solver
    exit /b 1
)
if not exist "%BB%" (
    echo [Error] bb_solver.exe not found. Compile first: g++ -O2 -std=c++17 bb_solver.cpp -o bb_solver
    exit /b 1
)

REM ══════════════════════════════════════════════════════════════════════════
REM EXPERIMENT 1 — Algorithm Efficiency on HLP Benchmarks
REM ══════════════════════════════════════════════════════════════════════════
echo.
echo ============================================================
echo  EXPERIMENT 1: Algorithm Efficiency on HLP Benchmarks
echo ============================================================

REM ── 1a. BB-Exact (Complete Enumeration ground-truth Pareto fronts) ──────────
echo.
echo --- Exp1a: BB-Exact (complete enumeration, ground-truth Pareto fronts) ---
for %%S in (10 20 25 40) do (
    set "INST=%DATA%\AP%%S_drnd.json"
    set "OUT=%RESULTS%\AP%%S_bb.json"
    if exist "!INST!" (
        echo [BB AP%%S] Running complete enumeration...
        "%BB%" "!INST!" --out "!OUT!" --mode enum --trials 500 --time-limit %BB_TIME%
        if !ERRORLEVEL!==0 (echo [BB AP%%S] Done.) else (echo [BB AP%%S] FAILED/Timeout)
    ) else (
        echo [BB AP%%S] Instance not found: !INST!
    )
)

if exist "%DATA_CV%\cv_small_drnd.json" (
    echo [BB CV-Small] Running complete enumeration...
    "%BB%" "%DATA_CV%\cv_small_drnd.json" --out "%RESULTS%\CV_small_bb.json" --mode enum --trials 500 --time-limit %BB_TIME%
    if !ERRORLEVEL!==0 (echo [BB CV-Small] Done.) else (echo [BB CV-Small] FAILED/Timeout)
)

REM ── 1b. PB-NSGA-II (20 seeds) on all benchmark instances ─────────────────
echo.
echo --- Exp1b: PB-NSGA-II (20 seeds) on HLP benchmarks ---
for %%S in (10 20 25 40 50 100) do (
    set "INST=%DATA%\AP%%S_drnd.json"
    if exist "!INST!" (
        echo [PB-NSGA AP%%S] Running 20 seeds...
        for %%R in (%SEEDS%) do (
            "%SOLVER%" "!INST!" --pop %POP% --gen %GEN% --seed %%R ^
                --out "%RESULTS%\AP%%S_seed%%R.json"
        )
        echo [PB-NSGA AP%%S] Done.
    ) else (
        echo [AP%%S] Instance not found: !INST!
    )
)

if exist "%DATA%\TR81_drnd.json" (
    echo [PB-NSGA TR81] Running 20 seeds...
    for %%R in (%SEEDS%) do (
        "%SOLVER%" "%DATA%\TR81_drnd.json" --pop %POP% --gen %GEN% --seed %%R ^
            --out "%RESULTS%\TR81_seed%%R.json"
    )
    echo [PB-NSGA TR81] Done.
)

REM ══════════════════════════════════════════════════════════════════════════
REM EXPERIMENT 2 — Case Study: Central Vietnam (PB-NSGA-II only)
REM ══════════════════════════════════════════════════════════════════════════
echo.
echo ============================================================
echo  EXPERIMENT 2: Case Study — Central Vietnam
echo ============================================================

if exist "%DATA_CV%\cv_small_drnd.json" (
    echo [CV-Small] Running PB-NSGA-II 20 seeds...
    for %%R in (%SEEDS%) do (
        "%SOLVER%" "%DATA_CV%\cv_small_drnd.json" ^
            --pop %POP% --gen %GEN% --seed %%R ^
            --out "%RESULTS%\CV_small_seed%%R.json"
    )
    echo [CV-Small] Done.
) else (
    echo [CV-Small] Instance not found. Run: python data_prep\generate_drnd.py
)

if exist "%DATA_CV%\cv_large_drnd.json" (
    echo [CV-Large] Running PB-NSGA-II 20 seeds...
    for %%R in (%SEEDS%) do (
        "%SOLVER%" "%DATA_CV%\cv_large_drnd.json" ^
            --pop %POP% --gen %GEN% --seed %%R ^
            --out "%RESULTS%\CV_large_seed%%R.json"
    )
    echo [CV-Large] Done.
) else (
    echo [CV-Large] Instance not found. Run: python data_prep\generate_drnd.py
)

REM ══════════════════════════════════════════════════════════════════════════
REM ANALYSIS & VISUALIZATION
REM ══════════════════════════════════════════════════════════════════════════
echo.
echo ============================================================
echo  Analysis and Visualization
echo ============================================================

python "%PROJECT%hlp-dataset\analyze_results.py" "%RESULTS%"

echo.
echo [Map Viz] Generating solution map for CV-Small...
if exist "%RESULTS%\CV_small_seed0.json" (
    python "%DATA%\map_solution.py" ^
        --instance "%DATA_CV%\cv_small_drnd.json" ^
        --result   "%RESULTS%\CV_small_seed0.json" ^
        --out      "%RESULTS%\figures\CV_small_map.pdf"
)

echo.
echo ============================================================
echo  All experiments complete. Results in: %RESULTS%
echo ============================================================
