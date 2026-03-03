@echo off
REM compile.bat — Compile PB-NSGA-II solver on Windows
REM Requirements: g++ (MinGW or MSYS2), C++17 support
REM Run from project root: .\compile.bat
REM
REM Algorithm version: V2
REM   - W vector: 6 weights (was 3)
REM   - Tiered hub selection with rotation-offset A segment
REM   - Normalised + stochastic demand priority scores
REM   - Hamming diversity tiebreaker in elitist selection

setlocal
set SOLVER_DIR=%~dp0solver_cpp
set OUT=%~dp0solver_cpp\solver.exe

echo [Compile] Building PB-NSGA-II solver (v2)...
g++ -O2 -std=c++17 -Wall ^
    "%SOLVER_DIR%\main.cpp" ^
    -o "%OUT%"

if %ERRORLEVEL% == 0 (
    echo [Compile] SUCCESS: "%OUT%"
) else (
    echo [Compile] FAILED. Check errors above.
    exit /b 1
)
