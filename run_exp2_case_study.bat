@echo off
REM run_exp2_case_study.bat
REM ============================================================
REM Experiment 2: Central Vietnam Case Study, SAA, and Insights
REM ------------------------------------------------------------
REM Runs PB-NSGA on the CV-Large instance across multiple seeds.
REM Generates:
REM   1. Statistical analysis of convergence (HV, IGD+)
REM   2. Hub selection stability and sensitivity analysis
REM   3. High-fidelity maps of representative solutions
REM ============================================================

SET "PROJECT=%~dp0"
SET "DATA_CV=%PROJECT%data\cv\cv_large_drnd.json"
SET "RES2=%PROJECT%results\exp2"
SET "SOLVER_DIR=%PROJECT%src\solver"

REM Python venv
SET "PYTHON=%PROJECT%.venv\Scripts\python.exe"
IF NOT EXIST "%PYTHON%" (
    SET "PYTHON=python"
)

IF NOT EXIST "%RES2%" mkdir "%RES2%"

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

REM ── Step 2: Statistical Analysis & Sensitivity ────────────────────────────
echo.
echo [Step 2] Analyzing Stability ^& Scenario Sensitivity...
"%PYTHON%" "%PROJECT%src\scripts\analyze_exp2.py" "%RES2%" "%PROJECT%data\cv"

REM ── Step 3: High-Fidelity Mapping ─────────────────────────────────────────
echo.
echo [Step 3] Generating 1x3 Composite Network Map...
REM We pick a representative solution (usually from seed 0 or combined)
"%PYTHON%" "%PROJECT%src\scripts\map_solution_v2.py" --instance "%DATA_CV%" --result "%RES2%\cv_large_seed0.json" --out "%PROJECT%figures\cv_large_map_detailed.pdf"

echo.
echo Experiment 2 (Case Study) Completed.
echo Results saved to: %RES2%\
echo Map saved to: figures\cv_large_map_detailed.pdf
