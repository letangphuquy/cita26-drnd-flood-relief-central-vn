# Reproducing Experimental Results (MO-IHLNDP)

This guide documents the procedures to reproduce the experimental results for the Central Vietnam (CV) Relief Network Design case study. The experiments benchmark the **PB-NSGA-II** solver against rigorous **Greedy**, **Exact MILP (AWS)**, and **Branch-and-Bound** baselines.

## 1. Environment Setup

- **Python**: Ensure `.venv` is activated.
- **Dependencies**: `pip install -r requirements.txt` (requires `pymoo`, `ortools`, `numpy`, `matplotlib`, `contextily`).
- **OS**: Scripts are provided for both Windows (`.bat`) and Mac/Linux (`.sh`).

## 1.1 Data Assumptions

**Transport Network Symmetry**: All datasets (`cv_small_drnd.json`, `cv_large_drnd.json`, SAA/OOS variants) guarantee that transport cost/time matrices (`transport.cost`, `transport.time`) and accessibility matrices (`scenarios[s].accessibility`) are **symmetric** — i.e., the two-way routing cost/time between any pair of nodes (i, j) is identical, and disruption routing is bidirectional. This symmetric property is essential for model and solver correctness and is validated during dataset generation.

## 2. Compilation

Compile the core `C++17` solvers using the provided universal scripts:

**Mac / Linux:**
```bash
bash compile.sh
```

**Windows:**
```powershell
.\compile.bat
```

This creates the following binary in `src/solver/`:
- `solver` (or `solver.exe`): Main PB-NSGA-II solver.

> **Note**: `greedy_baseline` is compiled automatically by `run_exp1_baselines.bat/.sh` (Step 1).
> `bb_solver` is pre-compiled and provided in `src/solver/`.

## 3. High-Level Experiment Pipeline

The experiments are divided into two main parts:

### Experiment 1: Baseline Comparison (CV-Small)
Benchmarks algorithms on a smaller instance to validate Pareto optimality, Hypervolume (HV), and IGD+ metrics.
- **Algorithms**: PB-NSGA, Greedy (500 restarts), MILP (Adaptive Weighted Sum), BB-Exact.
- **Logic**: Calls `run_exp1_baselines.sh` / `.bat`.

### Experiment 2: Case Study & Managerial Insights (CV-Large)
Extended evaluation on a large-scale instance with 20 independent seeds.
- **Outputs**: PB-NSGA vs VNS-TS Pareto trade-off front, stability analysis, scenario sensitivity (heatmap), and high-fidelity network maps.
- **Logic**: Calls `run_exp2_case_study.sh` / `.bat`.

## 4. Execution Commands

### Full Reproduction (One-Click)
To run the entire pipeline (Datasets → Exp 1 → Exp 2):

**Mac / Linux:**
```bash
./run_experiments.sh
```

**Windows:**
```powershell
.\run_experiments.bat
```

### Individual Experiment Runs

| Experiment | Mac / Linux | Windows |
| :--- | :--- | :--- |
| **All (Datasets + Exp1 + Exp2)** | `./run_experiments.sh` | `.\run_experiments.bat` |
| **Experiment 1 (Baselines)** | `./run_exp1_baselines.sh` | `.\run_exp1_baselines.bat` |
| **Experiment 2 (Case Study)** | `./run_exp2_case_study.sh` | `.\run_exp2_case_study.bat` |
| **Analysis Only** (re-run analysis on existing `results/`) | `./run_experiments.sh analyze` | `.\run_experiments.bat analyze` |
| **Regenerate Datasets Only** | `./run_experiments.sh data` | `.\run_experiments.bat data` |

### Dataset Regeneration (Detailed)

Use this section when you need to rebuild dataset artifacts explicitly.

1. Regenerate base CV instances (`cv_small_drnd.json`, `cv_large_drnd.json`):

**Mac / Linux:**
```bash
./run_dataset.sh
```

**Windows:**
```powershell
.\run_dataset.bat
```

2. Regenerate SAA/OOS datasets for Experiment 2 (combinatorial protocol):

**Mac / Linux:**
```bash
python src/scripts/data_generate_saa_oos.py --saa-scenarios 100 --oos-scenarios 10 --out-dir data/prep
```

**Windows:**
```powershell
python src\scripts\data_generate_saa_oos.py --saa-scenarios 100 --oos-scenarios 10 --out-dir data\prep
```

Key outputs written to `data/prep/`:
- `cv_large_saa100.json` (in-sample SAA training set)
- `cv_large_oos10.json` (hard OOS evaluation set)
- `cv_large_saa50.json` and `cv_large_oos.json` (compatibility aliases for older scripts)

3. Generate the Exp2 Pareto trade-off comparison manually:

**Mac / Linux:**
```bash
python src/scripts/exp2_pareto_tradeoff.py --results-exp2 results/exp2 --out-dir results/exp2
```

**Windows:**
```powershell
python src\scripts\exp2_pareto_tradeoff.py --results-exp2 results\exp2 --out-dir results\exp2
```

Trade-off outputs:
- `results/exp2/exp2_tradeoff_pareto.csv`
- `results/exp2/exp2_tradeoff_summary.json`
- `results/exp2/exp2_pareto_tradeoff.pdf`

Exp2 tracked algorithms:
- `PB-NSGA`
- `VNS-TS`
- `GWO-HD`

## 5. Manual Running and Analysis

If you prefer to run specific stages or analysis scripts manually:

**Mac / Linux:**
```bash
# Run PB-NSGA Seed 0 on CV-Large (Exp 2 uses --gen 500)
./src/solver/solver data/cv/cv_large_drnd.json --pop 200 --gen 500 --seed 0 --out results/exp2/cv_large_seed0.json

# Run Analysis for Experiment 2 (args: results_dir out_dir cv_data_dir)
python src/scripts/exp2_analyze_case_study.py results/exp2 results/exp2 data/cv

# Generate high-fidelity map (representative seed)
python src/scripts/exp2_map_solution.py --instance data/cv/cv_large_drnd.json --result results/exp2/cv_large_seed0.json --out figures/cv_large_map_detailed.pdf
```

**Windows:**
```powershell
# Run PB-NSGA Seed 0 on CV-Large (Exp 2 uses --gen 500)
.\src\solver\solver.exe data\cv\cv_large_drnd.json --pop 200 --gen 500 --seed 0 --out results\exp2\cv_large_seed0.json

# Run Analysis for Experiment 2 (args: results_dir out_dir cv_data_dir)
python src\scripts\exp2_analyze_case_study.py results\exp2 results\exp2 data\cv

# Generate high-fidelity map (representative seed)
python src\scripts\exp2_map_solution.py --instance data\cv\cv_large_drnd.json --result results\exp2\cv_large_seed0.json --out figures\cv_large_map_detailed.pdf
```

## 6. CLI Reference & Parameters

Detailed command-line arguments for the solvers and reproduction scripts.

### 6.1. Main PB-NSGA Solver (`src/solver/solver`)
| Argument | Type | Default | Description |
| :------- | :--- | :------ | :---------- |
| `instance` | Path | (Required) | Positional: Path to the `.json` instance. |
| `--pop` | Int | `200` | Population size (number of individuals). |
| `--gen` | Int | `300` | Number of generations to evolve. |
| `--seed` | Int | `0` | Base seed for the random number generator. |
| `--algo` | Enum | `nsga2` | Solver type: `nsga2` or `nsma` (Memetic). |
| `--pm-high` | Float | `0.40` | Initial mutation rate $(\eta/L)$. |
| `--pm-low` | Float | `0.10` | Final mutation rate after annealing. |
| `--stag` | Int | `20` | Generations before triggering stagnation reset. |
| `--tourney` | Int | `2` | Tournament selection size. |
| `--out` | Path | `stdout` | Destination path for the result JSON. |

### 6.2. MILP Epsilon-Constraint Baseline (`src/solver/milp_epsilon.py`)
| Argument | Type | Default | Description |
| :------- | :--- | :------ | :---------- |
| `--instance` | Path | (Required) | Path to the `.json` instance. |
| `--out` | Path | (Required) | Destination path for result JSON. |
| `--time_limit`| Int | `300` | Max seconds allowed PER objective solve. |
| `--epsilon_steps` | Int | `20` | Number of epsilon intervals used to sweep the Z1 bound. |

### 6.3. Branch-and-Bound / Greedy Baselines
| Solver | Key Argument | Default | Effect |
| :----- | :----------- | :------ | :----- |
| `bb_solver` | `--mode` | `enum` | Use `enum` for ground-truth; `bb` for B&B pruning. |
| `bb_solver` | `--trials` | `500` | Sub-problem trials per hub configuration. |
| `bb_solver` | `--time-limit`| `3600` | Total global runtime limit (seconds). |
| `greedy_baseline` | `--restarts` | `500` | Number of stochastic multi-restarts. |

### 6.4. Evaluation Metrics (`src/scripts/exp1_evaluate_cv_small.py`)
| Argument | Description |
| :------- | :---------- |
| `--results-exp1` | Directory containing baseline JSONs (`results/exp1/`). |
| `--ours` | Path to PB-NSGA result JSON (`cv_small_pb_nsga.json`). |
| `--greedy` | Path to Greedy result JSON (`cv_small_greedy.json`). |
| `--milp` | Path to MILP AWS result JSON (`cv_small_milp_aws.json`). |

## 7. Strategic & Economic Parameters

The following parameters are typically defined inside the instance JSON files but are critical to the solver's behavior:

| Symbol | Parameter | Value (CV Case Study) | Description |
| :----- | :-------- | :------------------- | :---------- |
| $\chi$ | Risk Threshold | `0.5` | Max allowable risk score for planned hubs. |
| $\gamma$ | Demand priority | `1.0` | Scaling factor for service level importance. |
| $\lambda$ | Decay rate | `0.005-0.02` | Distance/Time deprivation decay per mode. |
| $\Phi$ | Pre-positioned % | `0.5 - 1.0` | Inventory held for reactive response. |

## 8. Result Locations

- **Exp 1 Metrics**: `results/exp1/cv_small_metrics.csv` (Table 4 data).
- **Exp 2 Metrics**: `results/exp2/exp2_metrics.csv` — HV, IGD+ mean±std across 20 seeds.
- **Hub Stability**: `results/exp2/exp2_hub_stability.csv` — hub selection frequency per scenario.
- **Pareto Figures**: `results/exp2/figures/` — Pareto fronts, hub frequency bars, risk heatmaps.
- **Solution Map**: `figures/cv_large_map_detailed.pdf` — 1×3 scenario composite map (Step 3 of Exp 2).

---
*Note: Outdated benchmark datasets (AP, TR) are archived in the code and marked for future study. They can be triggered via `run_pbnsga.sh --instances AP TR81` or `run_pbnsga.bat --instances AP TR81` if needed for comparative research.*
