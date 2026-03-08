# Reproducing Experimental Results (MO-IHLNDP)

This guide documents the exact commands required to reproduce the full experimental results (Messages 1 and 2) for the Central Vietnam (CV) case study, reflecting the PB-NSGA evaluation against the rigorous Greedy, Exact MILP, and Branch-and-Bound baselines. 

> **Important Setup Notes:**
> - Ensure your Python virtual environment is activated before running any `python` statements.
> - Run all commands from the root directory of the `CITA_paper` project folder.
> - For a detailed guide on the project layout, refer to [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).

## 1. Compilation
First, compile the core `C++17` solvers. 

```bash
# Main PB-NSGA solver
g++ -O3 -std=c++17 src\solver\main.cpp -I src\solver -o src\solver\solver.exe

# Branch-and-Bound solver for exact enumeration proxies
g++ -O3 -std=c++17 src\solver\bb_solver.cpp -I src\solver -o src\solver\bb_solver.exe

# Greedy Baseline heuristic solver
g++ -O3 -std=c++17 src\solver\greedy_baseline.cpp -I src\solver -o src\solver\greedy_baseline.exe

# Flow exporter for visualizations
g++ -O3 -std=c++17 src\solver\export_flow.cpp -I src\solver -o src\solver\export_flow.exe
```

## 2. Running Experiment 1 (Baseline Comparisons on CV-Small)

We benchmark PB-NSGA against three custom baselines. Generating the MILP and exact pareto boundaries will take substantial computational time.

```bash
# A. Run PB-NSGA on CV-Small (and other datasets across 20 independent seeds)
# This evaluates the proposed evolutionary solver using the provided automation script.
run_pbnsga.bat

# B. Run Greedy Baselines (Min-Cost and Min-Deprivation anchors)
src\solver\greedy_baseline.exe data\cv\cv_small_drnd.json results\exp1\cv_small_greedy.json

# C. Run Branch-and-Bound (Exact Enumeration for ground truth proxy)
src\solver\bb_solver.exe data\cv\cv_small_drnd.json --out results\exp1\cv_small_bb.json --mode enum --time-limit 1800

# D. Run MILP formulation (epsilon-constraint method via OR-Tools)
python src\solver\milp_baseline.py --instance data\cv\cv_small_drnd.json --out results\exp1\cv_small_milp.json --steps 5
```

Once all outputs are successfully saved to `results\exp1\`, run the evaluation script to calculate the Hypervolume (HV) and Inverted Generational Distance (IGD+) arrays against the unified ground truth proxy:

```bash
# Calculate metrics and display the formatted outputs for Table 4 
python src\scripts\evaluate_baselines.py
```

## 3. Running Experiment 2 (Detailed Flow Visualization on CV-Large)

This step executes the case study visualization by identifying a Median-tradeoff solution from the extended `CV-Large` front, extracting its routing logic, and plotting the 3 scenarios.

```bash
# A. Run PB-NSGA on CV-Large (Assuming Seed 0 for the chosen analysis slice)
src\solver\solver.exe data\cv\cv_large_drnd.json --pop 200 --gen 300 --seed 0 --out results\exp2\cv_large_seed0.json

# B. Export routing and intermediate stage flow
src\solver\export_flow.exe data\cv\cv_large_drnd.json results\exp2\cv_large_seed0.json results\exp2\cv_large_flow.json

# C. Plot the Geographical Multi-Modal Network
python src\scripts\map_solution_detailed.py --instance data\cv\cv_large_drnd.json --flow results\exp2\cv_large_flow.json --out figures\cv_large_map_detailed.pdf
```

The resulting 1x3 composite figure mapping the truck, boat, and helicopter responses to the Mild, Severe, and Extreme topologies will be produced and saved directly as `figures\cv_large_map_detailed.pdf`.

## 4. Automated End-to-End Reproduction

For a "one-click" reproduction of all results (recompile, run experiments, analyze, and sync to paper), use these scripts:

```bash
# A. Experiment 1: Benchmarks
# Recompiles, runs baseline comparisons and benchmarks, analyzes, and syncs to paper/
run_exp1_full.bat

# B. Experiment 2: Case Study
# Recompiles, runs 20-seed runs for CV-Small/Large, generates maps, and syncs to paper/
run_exp2_full.bat
```

## 5. Manual Running and Analysis

If you prefer to run steps manually, follow these instructions:

### A. Compilation
```bash
# Main PB-NSGA solver
g++ -O3 -std=c++17 src\solver\main.cpp -I src\solver -o src\solver\solver.exe
```

### B. Analysis Scripts
```bash
# Exp1 Metrics
python src\scripts\analyze_exp1.py results\exp1

# Exp2 Metrics & Maps
python src\scripts\analyze_exp2.py results\exp2 results\exp2 data\cv
```

## 6. Updating the Manuscript (LaTeX)
The automated scripts above already handle syncing. If running manually, copy assets to `paper/`:
```bash
copy /Y results\exp1\exp1_metrics.csv paper\
copy /Y results\exp2\figures\*.pdf paper\figures\
```
