@echo off
setlocal EnableDelayedExpansion
set "PROJECT=%~dp0"

echo ============================================================
echo  EXPERIMENT 2: END-TO-END PIPELINE (Case Study)
echo ============================================================
echo.

echo [Step 1] Recompiling Solvers...
call "%PROJECT%compile.bat"
if !ERRORLEVEL! NEQ 0 (
    echo [Error] Compilation failed.
    exit /b 1
)

echo.
echo [Step 2] Running PB-NSGA 20-Seed Case Study...
echo This involves 20 seeds for both CV-Small and CV-Large.
echo PopSize=200, Gen=300
set "SOLVER=%PROJECT%src\solver\solver.exe"
set "DATA_CV=%PROJECT%data\cv"
set "RES2=%PROJECT%results\exp2"
set "POP=200"
set "GEN=300"
set "SEEDS=0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19"

if not exist "%RES2%" mkdir "%RES2%"

for %%G in (small large) do (
    echo   - Running CV-%%G (20 seeds)...
    for %%R in (%SEEDS%) do (
        "%SOLVER%" "!DATA_CV!\cv_%%G_drnd.json" --pop %POP% --gen %GEN% --seed %%R --out "!RES2!\CV_%%G_seed%%R.json" 2>NUL
    )
)

echo.
echo [Step 3] Running Analysis and Sensitivity Mapping...
set "PYTHON=%PROJECT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" "%PROJECT%src\scripts\analyze_exp2.py" "%RES2%" "%RES2%" "%DATA_CV%"

echo.
echo [Step 4] Syncing Results to Paper...
if not exist "%PROJECT%paper\figures" mkdir "%PROJECT%paper\figures"
if not exist "%PROJECT%paper\maps" mkdir "%PROJECT%paper\maps"

copy /Y "%RES2%\exp2_metrics.csv" "%PROJECT%paper\"
copy /Y "%RES2%\exp2_hub_stability.csv" "%PROJECT%paper\"
copy /Y "%RES2%\figures\*.pdf" "%PROJECT%paper\figures\"
copy /Y "%RES2%\maps\*.pdf" "%PROJECT%paper\maps\"

echo.
echo ============================================================
echo  Exp2 Full Pipeline Completed.
echo ============================================================
pause
