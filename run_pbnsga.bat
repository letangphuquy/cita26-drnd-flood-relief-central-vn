@echo off
setlocal EnableDelayedExpansion
set "PROJECT=%~dp0"
set "SOLVER=%PROJECT%solver\solver.exe"
set "POP=100"
set "GEN=200"
set "SEEDS=0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19"
set "RES1=%PROJECT%results\exp1"
set "RES2=%PROJECT%results\exp2"
set "DATA_BENCH=%PROJECT%data\benchmark"
set "DATA_CV=%PROJECT%data\cv"

echo [PB-NSGA] Full 20-seed run started.

for %%N in (10 20 25 40 50 100) do (
    echo [AP%%N] Running 20 seeds...
    for %%R in (%SEEDS%) do (
        "%SOLVER%" "!DATA_BENCH!\AP%%N_drnd.json" --pop %POP% --gen %GEN% --seed %%R --out "!RES1!\AP%%N_seed%%R.json" 2>/dev/null
    )
    echo [AP%%N] Done.
)

echo [TR81] Running 20 seeds...
for %%R in (%SEEDS%) do (
    "%SOLVER%" "!DATA_BENCH!\TR81_drnd.json" --pop %POP% --gen %GEN% --seed %%R --out "!RES1!\TR81_seed%%R.json" 2>/dev/null
)
echo [TR81] Done.

for %%G in (small large) do (
    echo [CV-%%G] Running 20 seeds...
    for %%R in (%SEEDS%) do (
        "%SOLVER%" "!DATA_CV!\cv_%%G_drnd.json" --pop %POP% --gen %GEN% --seed %%R --out "!RES2!\CV_%%G_seed%%R.json" 2>/dev/null
    )
    echo [CV-%%G] Done.
)

echo [PB-NSGA] All seeds complete.
