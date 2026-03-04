@echo off
REM run_experiments.bat — Full experiment pipeline
REM Usage: run_experiments.bat [quick]
REM   quick: pop=30, gen=20 (smoke test)
REM   default: pop=100, gen=200 (full paper quality)

setlocal EnableDelayedExpansion
set "PROJECT=%~dp0"
set "SOLVER=%PROJECT%solver_cpp\solver.exe"
set "DATA=%PROJECT%data"
set "DATA_CV=%PROJECT%data_prep"
set "RESULTS=%PROJECT%results"

REM Create results folder
if not exist "%RESULTS%" mkdir "%RESULTS%"

REM Check solver exists
if not exist "%SOLVER%" (
    echo [Error] Solver not found. Run compile.bat first.
    exit /b 1
)

REM Parameters
set "POP=100"
set "GEN=200"
if "%1"=="quick" (
    set "POP=30"
    set "GEN=20"
    echo [Mode] Quick test: pop=!POP! gen=!GEN!
) else (
    echo [Mode] Full run: pop=%POP% gen=%GEN%
)

REM ── EXPERIMENT 1: BENCHMARK DATASETS ─────────────────────────────────────
echo.
echo === EXPERIMENT 1: Benchmark Datasets ===

for %%S in (10 20 25 40 50 100) do (
    set "INST=%DATA%\AP%%S_drnd.json"
    set "OUT=%RESULTS%\AP%%S_result.json"
    if exist "!INST!" (
        echo [AP%%S] Running solver...
        "%SOLVER%" "!INST!" --pop %POP% --gen %GEN% --seed 0 --out "!OUT!"
        if !ERRORLEVEL! == 0 (
            echo [AP%%S] Done: !OUT!
        ) else (
            echo [AP%%S] FAILED
        )
    ) else (
        echo [AP%%S] Instance not found: !INST!. Run: python data\process_benchmark.py
    )
)

if exist "%DATA%\TR81_drnd.json" (
    echo [TR81] Running solver...
    "%SOLVER%" "%DATA%\TR81_drnd.json" --pop %POP% --gen %GEN% --seed 0 --out "%RESULTS%\TR81_result.json"
    echo [TR81] Done.
)

REM ── EXPERIMENT 2: CENTRAL VIETNAM CASE STUDY ──────────────────────────────
echo.
echo === EXPERIMENT 2: Central Vietnam Case Study ===

if exist "%DATA_CV%\cv_small_drnd.json" (
    echo [CV-Small] Running solver ^(3 seeds for robustness^)...
    for %%R in (0 1 2) do (
        "%SOLVER%" "%DATA_CV%\cv_small_drnd.json" ^
            --pop %POP% --gen %GEN% --seed %%R ^
            --out "%RESULTS%\CV_small_seed%%R.json"
        echo [CV-Small] Seed=%%R done.
    )
) else (
    echo [CV] Small instance not found. Run: python data_prep\generate_drnd.py
)

if exist "%DATA_CV%\cv_large_drnd.json" (
    echo [CV-Large] Running solver...
    "%SOLVER%" "%DATA_CV%\cv_large_drnd.json" ^
        --pop %POP% --gen %GEN% --seed 0 ^
        --out "%RESULTS%\CV_large_seed0.json"
    echo [CV-Large] Done.
) else (
    echo [CV] Large instance not found. Run: python data_prep\generate_drnd.py
)

REM ── ANALYSIS ──────────────────────────────────────────────────────────────
echo.
echo === Running Analysis Scripts ===
python "%DATA%\analyze_results.py" "%RESULTS%"
echo.
echo === All experiments complete. Results in: %RESULTS% ===
