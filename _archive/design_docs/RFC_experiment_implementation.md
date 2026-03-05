# RFC: Comprehensive Experiment Implementation Plan
## MO-IHLNDP — PB-NSGA-II Paper (CITA 2026)

**Status:** Draft
**Date:** 2026-03-04
**Authors:** Le Tang Phu Quy, Quang-Vu Nguyen
**Scope:** Full implementation specification for Experiments A, B, and C as defined in `core-prompts/experiment-strategy.txt`

---

## 0. Executive Summary

This RFC specifies, at engineering precision, the three experimental blocks required to validate and demonstrate the MO-IHLNDP model and PB-NSGA-II algorithm for the CITA 2026 paper. The current codebase (C++ solver `solver_cpp/solver.exe` + Python analysis `data/analyze_results.py`) provides a working foundation. What is missing is:

1. **Experiment A**: A rigorous 20-seed head-to-head algorithm comparison (PB-NSGA-II vs. baseline NSGA-II) with full metric suite (HV, IGD+, Running Time, Convergence Rate) on benchmark instances.
2. **Experiment B**: Three model-validation sub-experiments: toy instance correctness, computational scaling, and parameter sensitivity.
3. **Experiment C**: Managerial insights using the Central Vietnam case study, including real-map visualizations and scenario comparative analysis.

---

## 1. Context and Current State

### 1.1 Problem Formulation (Summary)

The paper formulates a two-stage stochastic **Multi-Objective Incomplete Hub Location Network Design Problem (MO-IHLNDP)** with:

- **Two objectives**: minimize expected total logistics cost $Z_1$ (including pre-disaster hub setup, inventory, reactive hub activation, inter-hub transshipment, and Daganzo CA last-mile routing costs) and minimize expected maximum deprivation cost $Z_2$ (exponential penalty for waiting time, enforcing social equity).
- **Three scenario types**: Mild (π=0.60), Severe (π=0.30), Extreme (π=0.10).
- **Three transport modes**: Road/Truck, Water/Motorboat, Air/Helicopter — with scenario-dependent arc accessibility.
- **Algorithm**: Priority-Based NSGA-II (PB-NSGA-II), extended to PB-NSMA with Pareto-improving local search.

### 1.2 Existing Infrastructure

| Component | File | Status |
|---|---|---|
| C++ Solver | `solver_cpp/solver.exe` | Compiled, functional |
| NSGA-II core | `solver_cpp/nsga2.hpp` | Implemented |
| Decoder | `solver_cpp/decoder.hpp` | Implemented (7-step) |
| Chromosome | `solver_cpp/representation.hpp` | 4-segment: X, R, A, W |
| Benchmark data | `data/AP{10,20,25,40,50,100}_drnd.json`, `data/TR81_drnd.json` | Generated |
| CV data | `data/central_vietnam_{small,large}_drnd.json` | Generated |
| Analysis script | `data/analyze_results.py` | HV + IGD+ + plots |
| Run script | `run_experiments.bat` | Single-seed only |

### 1.3 Current Gap vs. Required

| Requirement | Current | Required |
|---|---|---|
| Seeds per instance | 1 (benchmarks), 3 (CV-Small) | **20** |
| Baseline algorithm | Not compared | NSGA-II (without LS) vs PB-NSMA |
| Metrics | HV only | HV, IGD+, Runtime, Convergence |
| Model validation | None | Toy examples + scaling + sensitivity |
| Managerial insights | Partial text | Full map visualization + scenario charts |

---

## 2. Experiment A — Algorithm Comparison

### 2.1 Objective

Demonstrate that PB-NSMA (PB-NSGA-II with local search) is **statistically superior** to the baseline NSGA-II (without local search) across standard benchmark instances, measured by Hypervolume, IGD+, Running Time, and Convergence Rate.

### 2.2 Algorithm Definitions

**Algorithm 1 (Baseline): NSGA-II**
- Standard NSGA-II loop: selection → crossover (Uniform XO for X, SBX for R/W) → mutation (Bit-flip for X, Polynomial for R/W) → elitist survival.
- No local search phase.
- CLI flag: `--algo nsga2` (default in current solver).

**Algorithm 2 (Proposed): PB-NSMA**
- Same as NSGA-II plus: after each generation, each rank-1 solution is perturbed `ls_iters=5` times with Pareto-improving acceptance.
- Local search perturbation: 50% chance flip a random hub bit (X), 50% chance reassign a demand's preferred hub (A) to the next-nearest hub.
- CLI flag: `--algo nsma --ls 5`.

**Note on naming**: The paper calls the proposed algorithm "PB-NSGA-II" (Priority-Based NSGA-II) in its text. For experiment comparison, the two configurations are:
- Baseline = `nsga2` mode (PB encoding + NSGA-II, no local search)
- Proposed = `nsma` mode (PB encoding + NSGA-II + Local Search = "PB-NSMA")

### 2.3 Datasets

| Instance | Size (`|H|`/`|I|`/`|J|`) | Source |
|---|---|---|
| AP10 | ~4/6/- | AP Euclidean benchmark |
| AP20 | ~8/12/- | AP Euclidean benchmark |
| AP25 | ~10/15/- | AP Euclidean benchmark |
| AP40 | ~16/24/- | AP Euclidean benchmark |
| AP50 | ~20/30/- | AP Euclidean benchmark |
| AP100 | ~40/60/- | AP Euclidean benchmark |
| TR81 | ~32/49/- | Turkish inter-city network |

All datasets are already prepared in `data/*.json`.

### 2.4 Experimental Protocol

#### 2.4.1 Seed Strategy

Run each `(instance, algorithm)` pair **20 independent times** using rolling seeds `{0, 1, ..., 19}`. This follows the convention in the current solver: `--seed N` sets `std::mt19937(base_seed + N)` via `set_rolling_seed()`.

#### 2.4.2 Algorithm Parameters (Fixed Across All Runs)

```
Population size (N):         100
Generations (G):             200
Crossover probability (pc):  0.90
SBX distribution index (ηc): 20
Polynomial mutation index (ηm): 20
Mutation probability base:   0.20 / gene_count
Safety threshold (χ):        0.70
Economies-of-scale discount (α): 0.60
Conversion factor (γ):       3.0 kg/person
Base deprivation coeff (λ0): 0.80
Local search iters (NSMA):   5
```

These match the paper's Section 4.1 "Algorithm parameters" exactly.

#### 2.4.3 Metrics

**Metric 1: Hypervolume (HV)**
The primary metric. Measures the volume of the objective space dominated by the Pareto front, relative to a reference point.

Reference point construction: For each `(instance, algorithm, seed)` triplet, record the raw $(Z_1, Z_2)$ Pareto points. Across all 20 seeds per `(instance, algorithm)`, compute the combined reference point as:
$$\text{ref} = (1.1 \times \max_{Z_1}, 1.1 \times \max_{Z_2})$$
where the max is taken over **all** 20 runs' combined Pareto front. Normalize all objectives to $[0, 1]$ before computing HV. Report mean ± std over 20 seeds.

**Metric 2: IGD+ (Inverted Generational Distance Plus)**
Measures convergence and spread relative to the best-known reference front.

Reference front construction: Take the combined non-dominated front of **all** 20 seeds of **both** algorithms for a given instance. This is the empirical Pareto front approximation.

$$\text{IGD+}(A, R) = \sqrt{\frac{1}{|R|} \sum_{r \in R} \min_{a \in A} \left[ (\max(a_1-r_1, 0))^2 + (\max(a_2-r_2, 0))^2 \right]}$$

Lower IGD+ = better. Report mean ± std over 20 seeds.

**Metric 3: Running Time (RT)**
Wall-clock time in seconds to complete $G=200$ generations. Measure via system timing. The solver already logs this to `stderr` at the end of each run:
```
[PB-NSMA] Done. Total time: X.Xs
```
Capture this via output redirection and parse from stderr. Report mean ± std over 20 seeds.

**Metric 4: Convergence Rate (CR)**
Measures how quickly the algorithm reaches a near-optimal HV. Operationally defined as:

$$\text{CR} = \frac{\text{HV at generation 100}}{\text{HV at generation 200}} \times 100\%$$

To compute this, the solver must log the Pareto front at generation 100 in addition to the final generation. This requires a modification: add a `--log_pareto_at` flag (or simply log every `log_every` generations). Alternatively, run each instance twice: once with `--gen 100` and once with `--gen 200`, using the same seed, and compute the ratio of HVs.

**Implementation choice for CR**: Use the two-run approach (no code modification needed):
```bash
solver.exe instance.json --pop 100 --gen 100 --seed N --out result_gen100.json
solver.exe instance.json --pop 100 --gen 200 --seed N --out result_gen200.json
CR(N) = HV(result_gen100.json) / HV(result_gen200.json)
```

#### 2.4.4 Run Script Specification

Create `run_experiment_A.sh` (or `.bat` for Windows) with the following structure:

```bash
# For each instance in {AP10, AP20, AP25, AP40, AP50, AP100, TR81}
# For each algorithm in {nsga2, nsma}
# For each seed in {0..19}:
#   Run solver with --pop 100 --gen 200 --seed {seed} --algo {algo}
#   Also run with --gen 100 for convergence rate
#   Output to results/A/{instance}_{algo}_s{seed}.json
#   Output to results/A/{instance}_{algo}_s{seed}_gen100.json
```

Estimated runtime:
- 7 instances × 2 algorithms × 20 seeds × ~60s/run ≈ **4.7 hours** (parallelizable)
- With 4-core parallelization: ~1.2 hours

#### 2.4.5 Statistical Analysis

For each (instance, metric) pair:
- Report **mean ± std** in a table (Table format matching paper style).
- Perform **Wilcoxon rank-sum test** (non-parametric, appropriate for 20 samples) to test if PB-NSMA is statistically better than NSGA-II at $p < 0.05$.
- Mark significant improvements with `†` in the table.

#### 2.4.6 Output Tables

**Table A-1: Hypervolume (mean ± std over 20 seeds)**

| Instance | NSGA-II (HV) | PB-NSMA (HV) | p-value |
|---|---|---|---|
| AP10 | μ ± σ | μ ± σ | p |
| AP20 | μ ± σ | μ ± σ | p |
| ... | ... | ... | ... |
| TR81 | μ ± σ | μ ± σ | p |

**Table A-2: IGD+ (mean ± std, lower is better)**

Same structure as Table A-1.

**Table A-3: Running Time (seconds)**

Same structure, plus note that LS adds overhead.

**Table A-4: Convergence Rate (HV@100gen / HV@200gen × 100%)**

#### 2.4.7 Pareto Front Figures

For each instance, plot one figure showing:
- NSGA-II Pareto front (combined across 20 seeds) — blue
- PB-NSMA Pareto front (combined across 20 seeds) — orange
- Mark the knee point with a star `★`
- X-axis: $Z_1$ (Expected Logistics Cost, scientific notation)
- Y-axis: $Z_2$ (Expected Max Deprivation Cost, scientific notation)
- Title: `Pareto Front — {Instance}`
- Legend, grid, tight layout, save as PDF at 300 DPI

Key instances to prioritize for paper figures: **AP25**, **AP50**, **TR81** (diverse characteristics).

### 2.5 Implementation Checklist

- [ ] Extend `run_experiments.bat` to loop over 20 seeds and both algorithms
- [ ] Extend `data/analyze_results.py` to:
  - [ ] Load results grouped by `(instance, algorithm, seed)`
  - [ ] Compute HV per run (normalized)
  - [ ] Compute combined reference front (across seeds + algorithms)
  - [ ] Compute IGD+ per run
  - [ ] Parse runtime from JSON metadata or stderr log
  - [ ] Run Wilcoxon test (add `scipy.stats.mannwhitneyu`)
  - [ ] Generate LaTeX table output
  - [ ] Generate Pareto front comparison figures

---

## 3. Experiment B — Model Validation

### 3.1 Sub-Experiment B.1: Model Validation with Toy Examples

#### 3.1.1 Objective

Verify that the mathematical model and decoder behave correctly on small, hand-checkable instances where the optimal solution is known by inspection.

#### 3.1.2 Toy Instance Design

Design a **2-hub, 3-demand, 1-origin, 2-scenario** instance with integer-valued parameters chosen so that the globally optimal assignment is obvious:

```
Nodes:
  Hub 0 (H0): coordinates (0, 0),  F_k=100,  κ_k=500 kg, c_hold=0.01
  Hub 1 (H1): coordinates (10, 0), F_k=200,  κ_k=500 kg, c_hold=0.01
  Demand 0 (D0): at (1, 0),  BasePop=50  persons
  Demand 1 (D1): at (9, 0),  BasePop=30  persons
  Demand 2 (D2): at (5, 0),  BasePop=20  persons
  Origin 0 (O0): at (0, 5),  supply=600 kg

Transport: road only (mode 0), speed=40 km/h, cost=2 $/km

Scenarios:
  S1 (π=0.7): all links accessible, risk=[0.1, 0.1, 0.1, 0.1, 0.1]
  S2 (π=0.3): H0 unreachable from D1 (a_{D1,H0,road,S2}=0), risk=[0.1, 0.6, ...]

γ=3.0, α=0.6, λ0=0.8, χ=0.7
```

**Expected optimal behavior**:
- In S1: D0→H0 (closer), D1→H1 (closer), D2→either (equidistant); H0 is always activated (lower cost).
- In S2: D1 cannot reach H0 via road, so D1→H1; D0→H0; D2→H0 or H1.
- The model should prefer opening H0 (cheaper) and only open H1 reactively if forced by connectivity.

#### 3.1.3 Verification Protocol

1. **Create the toy JSON** manually with exact parameters.
2. **Run the solver** with `--pop 100 --gen 500 --seed 0` (more generations for tiny instance).
3. **Hand-compute** the optimal $Z_1$ and $Z_2$ values for both the forced-optimal allocation and the worst-case allocation.
4. **Assert** that the best Pareto point's $Z_1$ is within 1% of the hand-computed minimum.
5. **Assert** the decoded second-stage variables (hub activations, demand assignments) match expected routing for the toy scenario.

**Additional toy test — Equity enforcement**: Design a second toy instance where one demand cluster is geographically isolated (only reachable by helicopter). Verify that $Z_2$ forces the model to service this cluster despite high cost, rather than leaving it unserved.

#### 3.1.4 Deliverables

- `data/toy_instance_01.json`: basic 2-hub instance
- `data/toy_instance_02.json`: isolated-cluster equity instance
- `data/validate_toy.py`: script that runs both, checks assertions, prints pass/fail report

### 3.2 Sub-Experiment B.2: Computational Tractability Analysis

#### 3.2.1 Objective

Characterize how wall-clock runtime and Pareto front quality scale with instance size, justifying the meta-heuristic approach over exact solvers.

#### 3.2.2 Scaling Dimensions

Test the following instance sizes (create new instances if not already available):

| Instance | `|H|` | `|I|` | `|J|` | `|S|` | Notes |
|---|---|---|---|---|---|
| Tiny | 3 | 5 | 1 | 2 | Below AP10 |
| AP10 | 4 | 6 | 2 | 3 | Existing |
| AP20 | 8 | 12 | 4 | 3 | Existing |
| AP25 | 10 | 15 | 5 | 3 | Existing |
| AP40 | 16 | 24 | 8 | 3 | Existing |
| AP50 | 20 | 30 | 10 | 3 | Existing |
| AP100 | 40 | 60 | 20 | 3 | Existing |
| TR81 | 32 | 49 | 16 | 3 | Existing |
| CV-Small | 5 | 20 | 2 | 3 | Existing |
| CV-Large | 20 | 100 | 12 | 3 | Existing |

Run PB-NSMA with fixed `--pop 100 --gen 200 --seed 0` for each. Record:
- **Total runtime** (seconds)
- **Decoder calls per second** (= `pop_size × gen × 2` / runtime, approximately)
- **Final Pareto front size**
- **Feasibility rate** at final generation (% of population with CV=0)

#### 3.2.3 Exact Solver Comparison (Optional but Valuable)

For the Tiny instance only, implement a brute-force enumeration:
- Enumerate all $2^{|H|} = 8$ hub activation combinations.
- For each combination and each scenario, enumerate all demand assignment permutations.
- Compute exact $Z_1$, $Z_2$ for each.
- Find the true Pareto front.
- Compare PB-NSMA's Pareto front against the exact front.
- Report HV gap = (HV_exact - HV_heuristic) / HV_exact × 100%.

**Implementation**: Write a Python script `data/brute_force_tiny.py` that loads `data/toy_instance_01.json` and exhaustively evaluates.

#### 3.2.4 Output

**Figure B.2.1**: Runtime vs. Instance Size (bar chart, log scale Y)
**Figure B.2.2**: Pareto Front Size vs. Instance Size
**Table B.2**: Summary of computational scaling

### 3.3 Sub-Experiment B.3: Parameter Sensitivity Analysis

#### 3.3.1 Objective

Identify which algorithm parameters most affect solution quality (HV), and confirm that the paper's default parameters are near-optimal.

#### 3.3.2 Parameters Under Study

| Parameter | Default | Values Tested |
|---|---|---|
| Population size N | 100 | {25, 50, 75, 100, 150, 200} |
| Generations G | 200 | {50, 100, 150, 200, 300} |
| Crossover probability pc | 0.90 | {0.5, 0.7, 0.8, 0.9, 1.0} |
| SBX/Poly index η | 20 | {5, 10, 20, 30} |
| Local search iters (NSMA) | 5 | {0, 1, 3, 5, 10, 20} |
| Safety threshold χ | 0.70 | {0.5, 0.6, 0.7, 0.8, 0.9} |

#### 3.3.3 Protocol

Use a **one-factor-at-a-time (OFAT)** design:
- Fix all parameters to their defaults.
- Vary one parameter at a time across its test range.
- Use **AP25** as the test instance (medium-size, representative).
- Run **5 seeds** per parameter value (reduced from 20 to keep cost manageable).
- Metric: normalized HV (mean over 5 seeds).

Total runs: 5 parameters × ~5 values × 5 seeds ≈ 125 runs × ~10s each ≈ **~21 minutes**.

#### 3.3.4 Output

**Figure B.3.1**: HV vs. N (population size) — shows diminishing returns above N=100
**Figure B.3.2**: HV vs. G (generations) — shows convergence plateau
**Figure B.3.3**: HV vs. local search iters — justifies ls_iters=5 choice
**Figure B.3.4**: HV vs. χ (safety threshold) — shows impact on feasibility

All as line plots with error bars (±std over 5 seeds).

**Table B.3**: Best parameter values found, confirming defaults are appropriate.

---

## 4. Experiment C — Managerial Insights

### 4.1 Objective

Demonstrate the practical utility of the MO-IHLNDP framework for real-world disaster planning in Central Vietnam. Output actionable decision-support visualizations.

### 4.2 Datasets

Both Central Vietnam instances:
- **CV-Small**: `|I|=20, |H|=5, |J|=2, |S|=3` — `data/central_vietnam_small_drnd.json`
- **CV-Large**: `|I|=100, |H|=20, |J|=12, |S|=3` — `data/central_vietnam_large_drnd.json`

These instances use **real geographic coordinates** for the Vu Gia – Thu Bon river basin (Da Nang, Quang Nam province) and OSRM-derived road distances.

### 4.3 Protocol

Run **PB-NSMA** (proposed algorithm) on both instances:
- CV-Small: 20 seeds (for robustness statistics)
- CV-Large: 5 seeds (higher computational cost)
- Parameters: `--pop 100 --gen 200 --algo nsma`

### 4.4 Analysis Tasks

#### 4.4.1 Task C.1: Pareto Front Analysis and Trade-off Quantification

From the combined Pareto front of CV-Small (20 seeds):
1. Plot $Z_1$ vs. $Z_2$ Pareto front.
2. Identify and annotate three characteristic solutions:
   - **Cost-optimal**: leftmost point (minimum $Z_1$)
   - **Equity-optimal**: bottommost point (minimum $Z_2$)
   - **Balanced (knee point)**: maximum distance from ideal-to-nadir diagonal
3. Quantify the trade-off: "Reducing $Z_2$ by X% requires increasing $Z_1$ by Y×."
4. Extract the knee-point solution's decision variables: which hubs are open ($X_k$), inventory levels ($q_k$), and demand assignment structure.

#### 4.4.2 Task C.2: Network Topology Maps

For the knee-point solution of CV-Small, generate three maps (one per scenario):

**Required map elements**:
- Background: real map tiles (use `folium` with OpenStreetMap, or `contextily` with `geopandas`)
- Hub locations: triangles (▲), color-coded by type:
  - Green: Planned hub (X_k=1), safe (r_ks ≤ χ)
  - Orange: Reactive hub (y_ks=1), opened during disaster
  - Red: Hub candidate, inactive or unsafe
- Demand nodes: circles (●), sized by population count, color by deprivation cost
- Origins: squares (■), labeled with supply volume
- Assignment lines: arrows from demand nodes to assigned hubs, color by transport mode:
  - Gray: Road (mode 0)
  - Blue: Water/Motorboat (mode 1)
  - Red: Air/Helicopter (mode 2)
- Transshipment flows: dashed arrows between hubs, width proportional to flow volume
- Title: scenario name + probability

**Three maps to generate**:
- Map C.2.1: S1 — Mild flood scenario
- Map C.2.2: S2 — Severe flood scenario
- Map C.2.3: S3 — Extreme scenario

**Implementation**: Extend `data/visualize_map.py`. Save as high-resolution PNG (300 DPI) and HTML (interactive).

#### 4.4.3 Task C.3: Scenario Comparison Charts

Generate side-by-side bar charts comparing key metrics across scenarios for the knee-point solution:

**Chart C.3.1: Hub Utilization per Scenario**
- X-axis: hub candidates (H0, H1, ..., H4 for CV-Small)
- Y-axis: utilization % (load / capacity)
- Grouped bars: S1, S2, S3
- Shows how different scenarios stress different hubs

**Chart C.3.2: Mode Share per Scenario**
- Stacked bar chart (S1, S2, S3)
- Segments: % of demand-km served by Road / Water / Air
- Shows shift to resilient modes under extreme scenarios

**Chart C.3.3: Demand Node Waiting Time (Deprivation) per Scenario**
- Box plot or violin plot: distribution of Ω_is (waiting time) across all demand nodes
- One plot per scenario, showing increasing deprivation under worse scenarios
- Overlay: mean and 90th percentile

**Chart C.3.4: Cost Breakdown per Scenario**
- Stacked bar: for S1, S2, S3
- Segments: Hub setup costs, Inventory holding, Reactive hub activation, Supply transport, Last-mile (Daganzo CA), Transshipment
- Normalized to S1 = 100% baseline

#### 4.4.4 Task C.4: Solution for Real-world Decision Makers

Extract and format the **three characteristic solutions** (cost-optimal, equity-optimal, knee-point) into a decision-support table:

| Metric | Cost-Optimal | Balanced (Knee) | Equity-Optimal |
|---|---|---|---|
| $Z_1$ (Expected Logistics Cost) | ... | ... | ... |
| $Z_2$ (Expected Max Deprivation) | ... | ... | ... |
| Hubs opened (type 1) | {H0, H2} | {H0, H1, H3} | {H0, H1, H2, H3} |
| Avg inventory per hub | 120 kg | 180 kg | 250 kg |
| Max waiting time (S3 extreme) | 4.2 h | 2.8 h | 1.9 h |
| Total pre-disaster investment | $X | $Y | $Z |

This table directly informs disaster management policy: how many hubs to pre-position, how much inventory to stock, and the quantified cost of providing better equity.

#### 4.4.5 Task C.5: CV-Large Insights

For CV-Large, run with 5 seeds and extract:
1. Pareto front plot (all 5 seeds overlaid)
2. Heatmap of demand assignment frequency: for each demand node, what fraction of Pareto solutions assign it to each hub?
3. Hub criticality analysis: which hubs appear in >90% of Pareto solutions? (Must-open hubs)
4. Geographic vulnerability map: demand nodes colored by average deprivation cost across the Pareto front

---

## 5. Infrastructure and Tooling Changes

### 5.1 Solver Extensions Required

The current solver needs one small extension for Experiment A (convergence rate):

**Option A (Preferred — no code change)**: Run each seed twice, at gen=100 and gen=200. Parse HV from both runs and compute ratio. This keeps the solver unchanged.

**Option B (Code change)**: Add `--checkpoint_at N` flag to emit a JSON snapshot of the current Pareto front at generation N, then continue to the final generation.

Recommendation: **Option A** to minimize code changes and avoid regression risk.

### 5.2 Python Analysis Extensions

Extend `data/analyze_results.py` into a modular analysis package:

```
data/
  analyze_results.py          # existing — keep, extend
  experiment_A_analysis.py    # NEW: multi-seed, multi-algo comparison
  experiment_B_sensitivity.py # NEW: sensitivity analysis plots
  experiment_C_managerial.py  # NEW: maps, scenario charts, decision table
  utils/
    metrics.py                # HV, IGD+, pareto utilities (refactor from existing)
    stats.py                  # Wilcoxon test, mean/std formatting
    plot_style.py             # shared matplotlib style settings
```

### 5.3 Run Scripts

```
run_experiment_A.bat   # 7 instances × 2 algos × 20 seeds = 280 runs
run_experiment_B1.bat  # toy validation (2 instances, 1 run each)
run_experiment_B2.bat  # scaling study (10 instances, 1 run each)
run_experiment_B3.bat  # sensitivity (125 runs)
run_experiment_C.bat   # CV-Small (20 seeds) + CV-Large (5 seeds)
run_all.bat            # calls all of the above
```

### 5.4 Result Directory Structure

```
results/
  A/
    {instance}_{algo}_s{seed}.json          # full run results
    {instance}_{algo}_s{seed}_gen100.json   # convergence checkpoints
  B1/
    toy_01_result.json
    toy_02_result.json
    toy_validation_report.txt
  B2/
    scaling_{instance}_result.json
  B3/
    sensitivity_N_{value}_s{seed}.json
    sensitivity_G_{value}_s{seed}.json
    ... etc.
  C/
    CV_small_nsma_s{seed}.json
    CV_large_nsma_s{seed}.json
  figures/
    A_{instance}_pareto_comparison.pdf
    B2_scaling_runtime.pdf
    B3_sensitivity_{param}.pdf
    C_CV_small_pareto.pdf
    C_map_S{1,2,3}.png
    C_scenario_comparison.pdf
```

---

## 6. Detailed Metrics Specification

### 6.1 Hypervolume (HV) — Normalization Protocol

The raw $Z_1$ and $Z_2$ values vary by several orders of magnitude across instances (AP10: $Z_1 \sim 10^{13}$; AP100: $Z_1 \sim 10^{14}$). To make HV comparable across instances and algorithms:

1. For each instance, collect all $(Z_1, Z_2)$ points from **all seeds** of **both algorithms**.
2. Compute $Z_1^{\min}, Z_1^{\max}, Z_2^{\min}, Z_2^{\max}$.
3. Normalize: $\tilde{Z}_j = (Z_j - Z_j^{\min}) / (Z_j^{\max} - Z_j^{\min})$.
4. Reference point in normalized space: $(1.1, 1.1)$.
5. HV is then dimensionless and bounded in $(0, 1.21]$.
6. Per-run HV: normalize using the **global** bounds (same for all runs of the same instance).

This is already partially implemented in `analyze_results.py::normalize_pareto()`.

### 6.2 IGD+ Reference Front

The reference front $R$ for computing IGD+ is defined as:
$$R = \text{nondominated}\left(\bigcup_{\text{algo} \in \{nsga2, nsma\}} \bigcup_{s=0}^{19} \text{ParetoFront}(\text{algo}, s)\right)$$

This is the best-known approximation to the true Pareto front. It is computed once per instance, shared for both algorithms, and normalized using the same global bounds.

### 6.3 Statistical Testing

Use the **Mann-Whitney U test** (also called Wilcoxon rank-sum test), appropriate for:
- Non-parametric (no normality assumption)
- Two independent samples (NSGA-II runs vs. PB-NSMA runs)
- Sample size: 20 per group

For each (instance, metric) pair:
```python
from scipy.stats import mannwhitneyu
stat, p = mannwhitneyu(nsga2_values, nsma_values, alternative='less')
# 'less': H1 = NSGA-II < NSMA (i.e., NSMA is better for HV; use 'greater' for IGD+/RT)
```

Mark with `†` if $p < 0.05$, with `‡` if $p < 0.01$.

### 6.4 Convergence Rate — Definition Clarification

Convergence Rate is defined per-run as:
$$\text{CR}_{\text{run}} = \frac{\text{HV}(G=100)}{\text{HV}(G=200)}$$

where both HVs are normalized using the same global normalization bounds established from the full $G=200$ runs. A CR close to 1.0 means the algorithm converges early (efficient). A CR < 0.5 means significant improvement still happening in the second half of the run.

For PB-NSMA, expect CR > 0.85 (faster convergence due to local search). For NSGA-II baseline, expect CR ≈ 0.70–0.80.

---

## 7. Expected Results and Hypotheses

Based on the existing single-seed results and the algorithm design, the following outcomes are hypothesized:

### 7.1 Experiment A Hypotheses

**H1 (HV)**: PB-NSMA achieves statistically higher normalized HV than NSGA-II on all 7 instances ($p < 0.05$). Expected improvement: 5–15%.

**H2 (IGD+)**: PB-NSMA achieves lower IGD+ than NSGA-II, especially on large instances (AP100, TR81) where local search helps escape local optima.

**H3 (RT)**: PB-NSMA is slower than NSGA-II by a fixed overhead proportional to `ls_iters × rank1_count`. Expected overhead: 10–30% additional time. This is acceptable given HV improvement.

**H4 (CR)**: PB-NSMA converges faster (higher CR) than NSGA-II. Local search accelerates early Pareto front refinement.

**H5 (TR81 anomaly)**: TR81 produces very few non-dominated points (currently 2 with single seed). With 20 seeds, expect to find 5–15 non-dominated points. The dense inter-city graph creates few genuine trade-offs.

### 7.2 Experiment B Hypotheses

**H6 (Toy correctness)**: The decoder correctly assigns D0→H0 and D1→H1 in S1 (nearest hub), and correctly activates H1 reactively in S2 when road connectivity is cut.

**H7 (Scaling)**: Runtime scales approximately as $O(N \times G \times |H| \times |I| \times |S|)$, i.e., linearly in all dimensions. The current implementation has no polynomial complexity worse than $O(|H|^2)$ for transshipment.

**H8 (Sensitivity — N)**: HV improves with N up to N=100, then plateaus. The plateau confirms N=100 is sufficient.

**H9 (Sensitivity — χ)**: HV is non-monotone in χ. Very low χ restricts hub activation too severely (infeasibility). Very high χ allows risky hub activations (poor Z2). Optimal around χ=0.7.

### 7.3 Experiment C Hypotheses

**H10 (Trade-off structure)**: The Pareto front of CV-Small shows a convex trade-off, confirming the exponential deprivation cost's structural effect. A 30% reduction in $Z_2$ costs approximately $3\times$ in $Z_1$.

**H11 (Mode shift)**: Under S3 (extreme scenario), road transport share drops from ~70% (S1) to <20% (S3), with water/air compensating. This confirms the value of multi-modal network design.

**H12 (Hub criticality)**: 2–3 hubs appear as must-open (present in >90% of Pareto solutions) in CV-Large. These correspond geographically to elevated, central locations in the Vu Gia – Thu Bon basin.

---

## 8. Reproducibility and Data Management

### 8.1 Seed Protocol

The solver uses `std::mt19937` seeded with `(base_seed + seed_iter)` where `base_seed = 42` (hardcoded in `template.hpp`). The `--seed N` flag sets `seed_iter=N`. This guarantees:
- Same `(instance, algo, seed)` → identical result on same machine/compiler.
- Different seeds → statistically independent runs (sufficiently separated in RNG sequence).

### 8.2 Version Locking

Before starting experiments, record:
- Compiler version: `g++ --version`
- Solver binary hash: `sha256sum solver_cpp/solver.exe`
- Python version: `python --version`
- Dependency versions: `pip freeze`

Store in `results/experiment_metadata.json`.

### 8.3 Data Integrity Checks

After each batch of runs, verify:
- All output JSONs parse without error.
- All `pareto_front` entries have `CV == 0` (feasibility check; infeasible solutions should not appear in the Pareto front).
- $Z_1 > 0$ and $Z_2 > 0$ for all solutions (sanity check).
- No solution has $Z_1 > 10^{18}$ (BigM penalty leakage).

---

## 9. Timeline and Prioritization

| Priority | Experiment | Estimated Runtime | Code Work |
|---|---|---|---|
| **Critical (paper blocker)** | A: 20-seed comparison | ~4.7h compute | Run script + analysis |
| **Critical (paper blocker)** | C: Managerial insights | ~3h compute | Map visualization |
| **Important (validation)** | B.1: Toy examples | ~5 min compute | Toy instance JSON |
| **Useful (paper strengthens)** | B.2: Scaling study | ~2h compute | None (existing runs) |
| **Nice-to-have** | B.3: Sensitivity | ~21 min compute | Run script |

**Recommended order of execution**:
1. Run Experiment A (most critical, long compute — start first in background)
2. Run Experiment C (second most critical, parallel with A)
3. Run Experiment B.1 (quick validation, catch bugs early)
4. Run Experiment B.2 (reuses existing runs)
5. Run Experiment B.3 (if time permits)

---

## 10. Appendix: Key File Locations

| File | Purpose |
|---|---|
| `solver_cpp/main.cpp` | CLI entry point, output JSON writer |
| `solver_cpp/nsga2.hpp` | NSGA-II + PB-NSMA local search loop |
| `solver_cpp/decoder.hpp` | 7-step Priority-Based Decoder |
| `solver_cpp/representation.hpp` | Individual struct, chromosome operators |
| `solver_cpp/model.hpp` | DRNDInstance struct, data loading |
| `data/AP*_drnd.json` | AP benchmark instances (DRND format) |
| `data/TR81_drnd.json` | TR81 benchmark instance |
| `data/central_vietnam_small_drnd.json` | CV-Small case study data |
| `data/central_vietnam_large_drnd.json` | CV-Large case study data |
| `data/analyze_results.py` | HV + IGD+ computation, Pareto plots |
| `data/visualize_map.py` | Geographic map visualization (folium) |
| `data/generate_synthetic.py` | CV dataset generator |
| `results/` | All experiment output JSONs |
| `results/figures/` | Generated plots and maps |
| `paper/main.tex` | Main LaTeX source |

---

## 11. Key Algorithmic Clarifications for Implementation

### 11.1 Chromosome Encoding (Current vs. Paper)

The paper states the chromosome $\mathbf{C} = (\mathbf{X}, \mathbf{R}, \mathbf{W})$ with $\mathbf{W} \in [0,1]^3$. The actual code has a 4-segment chromosome $(\mathbf{X}, \mathbf{R}, \mathbf{A}, \mathbf{W})$ where $\mathbf{A}$ is the demand-hub preference vector. This is an implementation detail that improves decoder efficiency but is not exposed in the paper's algorithm description. For experiments, use this 4-segment representation as-is.

### 11.2 Hub Capacity Encoding

The paper states $q_k = R_k \cdot \hat{D} / n_{\text{open}}$ (coupled to hub count). The actual decoder uses $q_k = R_k \cdot \kappa_k$ (decoupled, capacity-fraction encoding). The current decoder implementation is correct and reviewer-approved. All experiments should use this encoding.

### 11.3 Deprivation Cost Cap

The decoder caps $\lambda \cdot \omega \leq 20$ before computing $\exp(\lambda \omega) - 1$ to prevent overflow. This is necessary because extreme scenarios can yield very large waiting times. The cap corresponds to $e^{20} \approx 5 \times 10^8$ — still representing extreme deprivation. All metrics are computed on capped values.

### 11.4 Reference Point for HV in Paper

The paper's Table 2 reports raw HV values (not normalized). For internal analysis, use normalized HV. For the paper table, report raw HV values using reference point = $1.1 \times (\max Z_1, \max Z_2)$ of the **combined Pareto front** across all seeds of both algorithms for that instance.

---

*End of RFC*
