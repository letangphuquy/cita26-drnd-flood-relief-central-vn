@echo off
REM compile.bat — Compile PB-NSGA-II solver on Windows
REM Requirements: g++ (MinGW or MSYS2), C++17 support
REM Run from project root: .\compile.bat [--all]
REM
REM Algorithm version: V2
REM   - W vector: 6 weights (was 3); W[5] = Pass-1 window depth
REM   - Tiered hub selection with anchor-based hub ordering (A~anchor hub)
REM   - Normalised + stochastic demand priority scores
REM   - Hamming diversity tiebreaker in elitist selection

setlocal
set SOLVER_DIR=%~dp0src\solver
set OUT=%~dp0src\solver\solver.exe
set "COMPILE_ALL=0"

for %%A in (%*) do (
    if /I "%%~A"=="--all" set "COMPILE_ALL=1"
    if /I "%%~A"=="--help" goto :show_help
    if /I "%%~A"=="-h" goto :show_help
)

echo [Compile] Building PB-NSGA-II solver (v2)...
g++ -O3 -std=c++17 -Wall ^
    "%SOLVER_DIR%\main.cpp" ^
    -o "%OUT%"

if %ERRORLEVEL% NEQ 0 (
    echo [Compile] FAILED. Check errors above.
    exit /b 1
)
echo [Compile] SUCCESS: "%OUT%"

if "%COMPILE_ALL%"=="1" (
    echo [Compile] Building Greedy baseline...
    g++ -O3 -std=c++17 -Wall "%SOLVER_DIR%\greedy_baseline.cpp" -o "%SOLVER_DIR%\greedy_baseline.exe"
    if ERRORLEVEL 1 (
        echo [Compile] FAILED: Greedy baseline
        exit /b 1
    )
    echo [Compile] SUCCESS: "%SOLVER_DIR%\greedy_baseline.exe"

    echo [Compile] Building BB-Exact baseline...
    g++ -O3 -std=c++17 -Wall "%SOLVER_DIR%\bb_solver.cpp" -o "%SOLVER_DIR%\bb_solver.exe"
    if ERRORLEVEL 1 (
        echo [Compile] FAILED: BB-Exact baseline
        exit /b 1
    )
    echo [Compile] SUCCESS: "%SOLVER_DIR%\bb_solver.exe"

    echo [Compile] Building VNS-TS baseline...
    g++ -O3 -std=c++17 -Wall "%SOLVER_DIR%\vns_ts_baseline.cpp" -o "%SOLVER_DIR%\vns_ts_baseline.exe"
    if ERRORLEVEL 1 (
        echo [Compile] FAILED: VNS-TS baseline
        exit /b 1
    )
    echo [Compile] SUCCESS: "%SOLVER_DIR%\vns_ts_baseline.exe"

    echo [Compile] Building GWO-HD baseline...
    g++ -O3 -std=c++17 -Wall "%SOLVER_DIR%\gwo_hd_baseline.cpp" -o "%SOLVER_DIR%\gwo_hd_baseline.exe"
    if ERRORLEVEL 1 (
        echo [Compile] FAILED: GWO-HD baseline
        exit /b 1
    )
    echo [Compile] SUCCESS: "%SOLVER_DIR%\gwo_hd_baseline.exe"
)

exit /b 0

:show_help
echo Usage: .\compile.bat [--all]
echo.
echo Flags:
echo   --all   Compile PB-NSGA and all C++ comparison solvers
exit /b 0
