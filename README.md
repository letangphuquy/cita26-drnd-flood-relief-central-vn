# Reproducing Experimental Results (MO-IHLNDP)

This guide documents the exact commands required to reproduce the full experimental results (Messages 1 and 2) for the Central Vietnam (CV) case study, reflecting the PB-NSGA evaluation against the rigorous Greedy, Exact MILP, and Branch-and-Bound baselines. 

> **Important Setup Notes:**
> - Ensure your Python virtual environment is activated before running any `python` statements.
> - Run all commands from the root directory of the `CITA_paper` project folder.

## 1. Compilation
First, compile the core `C++17` solvers. 

```bash
# Main PB-NSGA solver
g++ -O3 -std=c++17 solver/main.cpp -I solver -o solver/solver.exe

# Branch-and-Bound solver for exact enumeration proxies
g++ -O3 -std=c++17 solver/bb_solver.cpp -I solver -o solver/bb_solver.exe

# Greedy Baseline heuristic solver
g++ -O3 -std=c++17 solver/greedy_baseline.cpp -I solver -o solver/greedy_baseline.exe

# Flow exporter for visualizations
g++ -O3 -std=c++17 solver/export_flow.cpp -I solver -o solver/export_flow.exe
```

## 2. Running Experiment 1 (Baseline Comparisons on CV-Small)

We benchmark PB-NSGA against three custom baselines. Generating the MILP and exact pareto boundaries will take substantial computational time.

```bash
# A. Run PB-NSGA on CV-Small (and other datasets across 20 independent seeds)
# This evaluates the proposed evolutionary solver using the provided automation script.
run_pbnsga.bat

# B. Run Greedy Baselines (Min-Cost and Min-Deprivation anchors)
solver/greedy_baseline.exe data/cv/cv_small_drnd.json results/exp1/cv_small_greedy.json

# C. Run Branch-and-Bound (Exact Enumeration for ground truth proxy)
solver/bb_solver.exe data/cv/cv_small_drnd.json --out results/exp1/cv_small_bb.json --mode enum --time-limit 1800

# D. Run MILP formulation (epsilon-constraint method via OR-Tools)
python solver/milp_baseline.py --instance data/cv/cv_small_drnd.json --out results/exp1/cv_small_milp.json --steps 5
```

Once all outputs are successfully saved to `results/exp1/`, run the evaluation script to calculate the Hypervolume (HV) and Inverted Generational Distance (IGD+) arrays against the unified ground truth proxy:

```bash
# Calculate metrics and display the formatted outputs for Table 4 
python scripts/evaluate_baselines.py
```

## 3. Running Experiment 2 (Detailed Flow Visualization on CV-Large)

This step executes the case study visualization by identifying a Median-tradeoff solution from the extended `CV-Large` front, extracting its routing logic, and plotting the 3 scenarios.

```bash
# A. Run PB-NSGA on CV-Large (Assuming Seed 0 for the chosen analysis slice)
solver/solver.exe data/cv/cv_large_drnd.json --pop 100 --gen 200 --seed 0 --out results/exp2/cv_large_seed0.json

# B. Export routing and intermediate stage flow
solver/export_flow.exe data/cv/cv_large_drnd.json results/exp2/cv_large_seed0.json results/exp2/cv_large_flow.json

# C. Plot the Geographical Multi-Modal Network
python scripts/map_solution_detailed.py
```

The resulting 1x3 composite figure mapping the truck, boat, and helicopter responses to the Mild, Severe, and Extreme topologies will be successfully produced and saved directly as `figures/cv_large_map_detailed.pdf`.
