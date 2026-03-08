# Project Directory Structure (PDS)

This project follows a standard research directory structure to maintain organization and clarity.

## Layout Overview

- `src/`: Consolidated source code.
  - `solver/`: C++ and Python implementations of the solvers (PB-NSGA-II, MILP, Greedy, BB).
  - `scripts/`: Python scripts for data analysis, result processing, and visualization.
- `data/`: Raw and processed dataset instances.
  - `prep/`: Utility scripts for data preparation and verification.
  - `hlp-benchmark/`: External benchmark instances (AP, TR81, etc.).
  - `cv/`: Case study instances for Central Vietnam.
- `results/`: Output files from experiments.
  - `exp1/`: Results for algorithm benchmarking.
  - `exp2/`: Results for the Central Vietnam case study.
- `paper/`: LaTeX source files for the research paper.
- `manuscript/`: Published or finalized PDF versions of the paper.
- `references/`: Consolidated research papers and reference materials.
- `logs/`: Execution logs and terminal outputs.
- `build/`: Temporary build artifacts (e.g., `.o` files).
- `core-prompts/`: Project notes, design thoughts, and LLM prompt materials.
- `intern/`: Related internship projects and reports.

## Key Entry Points

- `compile.bat`: Compiles the PB-NSGA-II C++ solver.
- `run_experiments.bat`: The main pipeline to generate data, run solvers, and perform analysis.
- `run_cv_small_baselines.bat`: Specifically runs baseline comparisons for the CV-Small instance.
- `run_dataset.bat`: Utilities for dataset patching and visualization.
- `README.md`: General project introduction and setup guide.
