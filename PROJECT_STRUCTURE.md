# Project Directory Structure (PDS)

This project follows a standard research directory structure to maintain organization and clarity.

## Layout Overview

- `src/`: Consolidated source code.
  - `solver/`: C++ and Python implementations of the solvers (PB-NSGA-II, MILP, Greedy, BB).
  - `scripts/`: Python scripts for data analysis, result processing, and visualization.
- `data/`: Raw and processed dataset instances.
  - `prep/`: Prepared datasets (SAA/OOS variants for robustness evaluation).
  - `benchmark/`: External benchmark instances (AP, TR81, etc.) for archival.
  - `cv/`: Case study instances for Central Vietnam.
  - `hlp/`: HLP benchmark reference instances.
- `results/`: Output files from experiments.
  - `exp1/`: Results for algorithm benchmarking.
  - `exp2/`: Results for the Central Vietnam case study.
- `paper/`: LaTeX source files for the research paper.
- `figures/`: Generated publication figures and maps.
- `manuscript/`: Published or finalized PDF versions of the paper.
- `ref/`: Consolidated research papers and reference materials.
- `logs/`: Execution logs and terminal outputs.
- `build/`: Temporary build artifacts (e.g., `.o` files).
- `core-prompts/`: Project notes, design thoughts, and LLM prompt materials.
- `intern/`: Related internship projects and reports.

## Key Entry Points

- `compile.bat` / `compile.sh`: Compiles the PB-NSGA-II C++ solver.
- `run_experiments.bat` / `run_experiments.sh`: End-to-end pipeline orchestrating Exp1 and Exp2 (datasets → solver runs → analysis).
- `run_exp1_baselines.bat` / `run_exp1_baselines.sh`: Experiment 1 (CV-Small, baseline comparison).
- `run_exp2_case_study.bat` / `run_exp2_case_study.sh`: Experiment 2 (CV-Large, case study & insights).
- `run_dataset.bat` / `run_dataset.sh`: Utilities for dataset regeneration.
- `README.md`: General project introduction and setup guide.
