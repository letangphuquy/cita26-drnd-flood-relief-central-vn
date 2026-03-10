# JSON Data Schema Reference — CITA / MO-IHLNDP Project

> **Date:** 2026-03-09  
> **Purpose:** Document every JSON file format transmitted between modules (data prep → solver → analysis → paper).  
> Intended audience: developers, future maintainers, and reviewers reproducing experiments.

---

## Table of Contents

1. [DRND Instance JSON](#1-drnd-instance-json)
2. [Solver Output / Pareto Front JSON](#2-solver-output--pareto-front-json)
3. [Flow Details JSON](#3-flow-details-json-export_flow)
4. [Out-of-Sample / SAA Evaluation JSON](#4-out-of-sample--saa-evaluation-json)
5. [Data-Flow Diagram](#5-data-flow-diagram)
6. [Field Index](#6-field-index)

---

## 1. DRND Instance JSON

### Overview

| Item | Detail |
|---|---|
| **File pattern** | `data/benchmark/<name>_seed<N>_drnd.json`, `data/cv/*.json`, `data/hlp/*.json` |
| **Source (producer)** | `src/scripts/process_benchmark.py` (benchmark datasets) · `generate_synthetic.py` (synthetic) |
| **Consumers** | `src/solver/solver.exe` (PB-NSGA/PB-NSMA) · `src/solver/bb_solver.exe` · `src/solver/milp_epsilon.py` · `src/solver/export_flow.exe` · `src/solver/evaluate_oos.exe` |
| **Reproducibility** | Re-generate with `python src/scripts/process_benchmark.py --seed <N>`. Deterministic for fixed `--seed`. |
| **Debug hints** | Check `dimensions` counts match actual array lengths. `accessibility[m]` must be a `num_nodes × num_nodes` 2-D array. `theta` is `[num_H][num_I][num_S]`. |

### Top-level schema

```jsonc
{
  "meta": {
    "source":      "benchmark" | "synthetic",  // origin tag
    "seed":        42,                          // integer RNG seed
    "name":        "AP10",                      // instance identifier
    "description": "AP benchmark (n=10) ..."   // human-readable note
  },

  "dimensions": {
    "num_I": 5,   // number of demand nodes
    "num_H": 3,   // number of candidate hub nodes
    "num_J": 2,   // number of supply/origin nodes
    "num_S": 3,   // number of disaster scenarios
    "num_M": 3    // number of transport modes (road=0, water=1, air=2)
  },

  "nodes": {
    "coords":         [[x, y], ...],        // float[num_nodes][2], planar or lat/lon
    "names":          ["Node_0", ...],      // string[num_nodes]
    "demand_indices": [1, 3, 4, ...],       // int[num_I] — global node indices of demand nodes
    "hub_indices":    [6, 7, 9],            // int[num_H] — global node indices of hub candidates
    "origin_indices": [0, 2]               // int[num_J] — global node indices of supply origins
  },

  "global_params": {
    "alpha":       0.6,         // inter-hub transshipment cost discount factor
    "chi":         0.7,         // maximum tolerated hub risk (safety threshold)
    "gamma":       3.0,         // demand-to-relief-item conversion ratio
    "big_M":       1e9,         // penalty for unmet demand/supply in Z1
    "daganzo_phi": 0.57,        // Daganzo last-mile CA constant φ
    "daganzo_eta": 5            // Daganzo last-mile service area density η
  },

  "hub_params": {
    "capacity":   { "6": 102464, ... },    // float, per hub node index key (string)
    "fixed_cost": { "6": 20693.9, ... },   // float, fixed establishment cost F_k
    "hold_cost":  { "6": 0.914, ... }      // float, unit inventory holding cost C_k
  },

  "base_population": { "1": 1775, ... }, // int, per demand node — baseline population
  "area_km2":        { "1": 3000.0, ... }, // float, per demand node — catchment area

  "transport": {
    // Both arrays: [mode][src_node][dst_node] — space-separated string rows or nested arrays
    "cost": [                              // float[num_M][num_nodes][num_nodes]
      ["0.0 521.89 ...", ...],             // mode 0 (road): cost per unit
      ["0.0 1304.7 ...", ...],             // mode 1 (water)
      ["0.0 10437 ...", ...]               // mode 2 (air)
    ],
    "time": [                              // float[num_M][num_nodes][num_nodes]
      ["0.0 7.46 ...", ...],               // mode 0: travel time (hours)
      ["0.0 10.44 ...", ...],              // mode 1
      ["0.0 1.74 ...", ...]                // mode 2
    ]
  },

  "scenarios": [
    {
      "name":              "mild",          // string label
      "probability":       0.6,             // float, Σ_s p_s = 1.0
      "epicenters": [
        { "node": 0, "intensity": 0.693 }   // epicenter node index + Gaussian intensity
      ],
      "risk":              [0.619, 0.080, ...], // float[num_nodes] — node-level risk r_ks
      "hub_risk":          { "6": 0.080, ... }, // float, subset of risk for hub nodes (string key)
      "accessibility": [
        [[true/1, ...], ...],  // bool/int[num_M][num_nodes][num_nodes] — arc reachability a_{km}
        ...
      ],
      "demand":            { "1": 297.9, ... }, // float, per demand node — scenario demand D_{is}
      "supply":            { "0": 5000.0, ... }, // float, per origin node — scenario supply
      "hub_reactive_cost": { "6": 52591.3, ... }, // float — reactive activation cost in this scenario
      "hub_process_time":  { "6": 2.034, ... }    // float — processing delay τ_{ks} (hours)
    }
    // × num_S
  ],

  // Daganzo CA last-mile cost: theta[hub_local_idx][demand_local_idx][scenario_idx]
  "theta": [[[8415.3, 46743.6, 439246.5], ...], ...], // float[num_H][num_I][num_S]

  // Deprivation rate: lambda["{demand_node}_{scenario_idx}"]
  "lambda": {
    "1_0": 0.864,   // float — exponential deprivation rate λ_{is}
    "3_0": 0.864,
    ...
  }
}
```

### Notes
- `transport.cost` / `transport.time` rows may be serialized as **space-separated strings** (legacy PowerShell artifact) or as **nested float arrays** — the C++ loader (`decoder.hpp`) handles both styles.
- `accessibility[m]` encodes whether a road/water/air link exists between any two nodes. Disruption is pre-applied per scenario.
- All node-keyed dicts (`demand`, `supply`, `hub_risk`, etc.) use **string** keys matching the global node index.

---

## 2. Solver Output / Pareto Front JSON

### Overview

| Item | Detail |
|---|---|
| **File pattern** | `results/exp1/<name>_seed<N>.json`, `results/exp2/CV_*_seed<N>.json`, `results/exp1/CV_small_*.json` |
| **Producers** | `src/solver/solver.exe` (PB-NSGA · PB-NSMA) · `src/solver/bb_solver.exe` · `src/solver/milp_epsilon.py` · `src/solver/milp_aws_baseline.py` |
| **Consumers** | `src/scripts/analyze_exp1.py` · `src/scripts/analyze_exp2.py` · `src/solver/export_flow.exe` · `src/solver/evaluate_oos.exe` · `src/scripts/map_solution*.py` |
| **Reproducibility** | `./run_experiments.sh` or `run_experiments.bat`. Seed controlled by `--seed`. |
| **Debug hints** | If `pareto_front` is empty, check that the instance has ≥1 feasible hub configuration. `CV=0` is required for a solution to be classified as feasible. Filter by `CV==0` before computing HV/IGD+. |

### Schema

```jsonc
{
  "meta": {
    "solver":         "PB-NSGA" | "PB-NSMA" | "BB_Enum" | "MILP_WeightedSum_SCIP",
    "elapsed_s":      12.4,          // float — wall-clock time
    "cpu_time_s":     11.9,          // float — CPU time (main solver only)
    "seed":           0,             // int — seed_iter CLI arg
    "pop_size":       200,           // int — (evolutionary solvers only)
    "num_gen":        300,           // int — (evolutionary solvers only)
    "pm_high":        0.40,          // float — initial mutation rate
    "pm_low":         0.10,          // float — final mutation rate
    "stag_threshold": 20,            // int — stagnation window
    "tournament_size":2,             // int — binary tournament size
    // MILP-specific additional fields:
    "instance":       "path/to.json",
    "steps":          1000,          // number of weighted-sum solve iterations
    "time_limit_s":   600,           // per-solve SCIP time limit
    "total_elapsed_s":3600.0,
    "per_solve_time_s": [1.09, ...]  // float[] — time per weighted-sum point
  },

  // Primary output: Pareto-optimal solutions (deduplicated, CV=0)
  "pareto_front": [
    {
      "Z1":   108288754.09,  // float — expected logistics cost (Objective 1, minimise)
      "Z2":   633823129.06,  // float — expected maximum deprivation cost (Objective 2, minimise)
      "CV":   0.0,           // float — constraint violation; 0 = feasible
      "rank": 1,             // int — NSGA-II non-domination rank (always 1 in pareto_front)
      "X":    [0, 0, 1, ...], // int[num_H] — hub establishment: 1=planned, 0=not
      "R":    [0.0, 0.023, ...], // float[num_H] — pre-positioned inventory ratio r_k ∈ [0,1]
      "A":    [1, 2, 2, ...], // int[num_I] — transport mode assignment per demand node (0/1/2)
      "W":    [0.075, 0.078, ...] // float[6] — scenario–mode weight vector (internal decoder weights)
    }
    // × |Pareto front|
  ],

  // Secondary: all feasible individuals in final population (for analysis)
  "all_feasible": [
    {
      "Z1": ..., "Z2": ...,
      "rank":     2,         // int — NSGA-II rank (≥1); only rank=1 in pareto_front
      "crowding": 0.45,      // float — crowding distance
      "X": [...], "R": [...], "A": [...], "W": [...]
    }
  ],

  // MILP baseline only — status per weighted-sum solve
  "status": "OPTIMAL" | "FEASIBLE" | "INFEASIBLE"  // (inside each pareto_front entry for MILP)
}
```

### Decision variables glossary

| Field | Type | Dimension | Meaning |
|---|---|---|---|
| `X` | `int[]` | `[num_H]` | Binary hub establishment (`x_k`) |
| `R` | `float[]` | `[num_H]` | Inventory pre-positioning ratio (`q_k / κ_k`) |
| `A` | `int[]` | `[num_I]` | Per-demand transport mode index (`a_{im}`) |
| `W` | `float[]` | `[6]` | Internal weight vector for priority-based decoder |

---

## 3. Flow Details JSON (`export_flow`)

### Overview

| Item | Detail |
|---|---|
| **File pattern** | `results/exp2/cv_large_flow.json`, `results/exp2/cv_large_seed0_verify.json` |
| **Producer** | `src/solver/export_flow.exe` — reads instance + solver output, picks median-Z1 solution |
| **Consumers** | `src/scripts/map_solution_detailed.py` · `src/scripts/map_solution_v2.py` · `src/scripts/analyze_exp2.py` (hub stability) |
| **Reproducibility** | `export_flow.exe <instance.json> <results.json> <out_flow.json>` |
| **Debug hints** | `meta.Z1` / `meta.Z2` should match the selected solution in the parent Pareto front. Missing assignments (`hub_idx = -1`) indicate infeasible routing for that demand/origin node. |

### Schema

```jsonc
{
  "meta": {
    "Z1":  18071696.04,   // float — objective value of the selected solution
    "Z2":  11140427.02,   // float
    "CV":  0.0,           // float — constraint violation
    "X":   [1, 0, 0],     // int[num_H] — hub configuration
    "R":   [0.0, 0.13, ...] // float[num_H] — inventory ratios
  },

  "scenarios": [
    {
      "scenario": 0,            // int — scenario index (0-based)

      // Active hub flags after safety check
      "y_ks": [true, false, ...],           // bool[num_H] — reactive hub activation per hub

      // Inventory held at each hub (after allocation)
      "inventory_held": [1200.5, 0.0, ...], // float[num_H]

      // Each demand node → assigned hub + mode
      "demand_assignments": [
        {
          "demand_idx": 1,    // int — global node index of the demand node
          "hub_idx":    6,    // int — global node index of the assigned hub (-1 if unassigned)
          "mode":       0     // int — transport mode used (0=road, 1=water, 2=air)
        }
        // × num_I
      ],

      // Each supply origin → assigned hub + mode
      "origin_assignments": [
        {
          "origin_idx": 0,    // int — global node index of the origin
          "hub_idx":    6,    // int — assigned hub global index
          "mode":       1     // int — transport mode
        }
        // × num_J
      ],

      // Lateral transshipment flows between hubs
      "transshipment": [
        {
          "src_hub_idx": 118,    // int — source hub (global node index)
          "dst_hub_idx": 108,    // int — destination hub (global node index)
          "mode":        0,      // int — transport mode
          "flow":        21608.16 // float — units transferred
        }
        // variable length
      ]
    }
    // × num_S
  ]
}
```

---

## 4. Out-of-Sample / SAA Evaluation JSON

### Overview

| Item | Detail |
|---|---|
| **File pattern** | `results/exp2/CV_large_seed0_oos_eval.json`, `*_saa_eval.json` |
| **Producer** | `src/solver/evaluate_oos.exe` — re-evaluates Pareto solutions on a new (OOS/SAA) instance |
| **Consumers** | `src/scripts/analyze_saa_oos.py` · `src/scripts/analyze_exp2.py` |
| **Reproducibility** | `evaluate_oos.exe <oos_instance.json> <pareto_front.json> <output.json>` |
| **Debug hints** | `orig_Z1` / `orig_Z2` come from the training-instance Pareto front; `new_Z1` / `new_Z2` are the objective values re-decoded on the OOS instance. A large ratio `new_Z1/orig_Z1` signals poor out-of-sample robustness. |

### Schema

```jsonc
{
  "meta": {
    "instance":      "path/to/oos_instance.json", // OOS instance path
    "pareto_source": "path/to/pareto.json"         // source Pareto front path
  },

  "evaluations": [
    {
      "idx":      0,              // int — index within the original Pareto front
      "orig_Z1":  822574513.45,   // float — Z1 on training instance
      "orig_Z2":  62652.23,       // float — Z2 on training instance
      "new_Z1":   2598299037.27,  // float — Z1 re-decoded on OOS instance
      "new_Z2":   1314818.63,     // float — Z2 re-decoded on OOS instance
      "new_CV":   0.0,            // float — feasibility on OOS instance
      "X": [0, 1, 0, ...],        // int[num_H] — unchanged (same hub configuration)
      "W": [0.777, 0.485, ...]    // float[6] — decoder weights (unchanged)
    }
    // × |pareto_front|
  ]
}
```

---

## 5. Data-Flow Diagram

```
┌──────────────────────────────┐
│  process_benchmark.py /       │
│  generate_synthetic.py        │  ← benchmark .txt / lat-lon coords
│  (src/scripts/)               │
└────────────┬─────────────────┘
             │ produces
             ▼
 ┌───────────────────────────────────────┐
 │  DRND Instance JSON                   │
 │  data/benchmark/<name>_seed<N>.json   │  [Schema §1]
 │  data/cv/*.json                       │
 └──┬──────────────┬────────────┬────────┘
    │              │            │
    ▼              ▼            ▼
solver.exe    bb_solver.exe  milp_epsilon.py
(PB-NSGA/     (exhaustive    (SCIP weighted-sum)
 PB-NSMA)      enum/BB)
    │              │            │
    └──────────────┴────────────┘
             │ all produce
             ▼
 ┌───────────────────────────────────────┐
 │  Pareto Front JSON                    │
 │  results/exp1/<name>_seed<N>.json     │  [Schema §2]
 │  results/exp2/CV_*_seed<N>.json       │
 └─────────┬──────────────┬─────────────┘
           │              │
           ▼              ▼
   export_flow.exe    evaluate_oos.exe
           │              │
           ▼              ▼
 ┌─────────────────┐  ┌──────────────────────────┐
 │ Flow Details    │  │ OOS / SAA Evaluation JSON │
 │ *_flow.json     │  │ *_oos_eval.json           │  [Schema §4]
 │ [Schema §3]     │  │ *_saa_eval.json           │
 └────────┬────────┘  └────────────┬─────────────┘
          │                        │
          ▼                        ▼
   map_solution*.py          analyze_saa_oos.py
   (figures/maps)            analyze_exp2.py → exp2_metrics.csv
                                              → exp2_hub_stability.csv

analyze_exp1.py ← results/exp1/*_seed*.json → exp1_metrics.csv, exp1_timing.csv
```

---

## 6. Field Index

Quick lookup: field name → which schema(s) contains it.

| Field | Schema(s) |
|---|---|
| `meta` | §1, §2, §3, §4 |
| `dimensions` | §1 |
| `nodes` | §1 |
| `global_params` | §1 |
| `hub_params` | §1 |
| `transport.cost` | §1 |
| `transport.time` | §1 |
| `scenarios[s].risk` | §1 |
| `scenarios[s].accessibility` | §1 |
| `scenarios[s].demand` | §1 |
| `scenarios[s].supply` | §1 |
| `scenarios[s].hub_process_time` | §1 |
| `theta` | §1 |
| `lambda` | §1 |
| `pareto_front` | §2 |
| `pareto_front[].Z1` / `Z2` | §2 |
| `pareto_front[].CV` | §2 |
| `pareto_front[].X` | §2 |
| `pareto_front[].R` | §2 |
| `pareto_front[].A` | §2 |
| `pareto_front[].W` | §2 |
| `all_feasible` | §2 |
| `scenarios[s].demand_assignments` | §3 |
| `scenarios[s].origin_assignments` | §3 |
| `scenarios[s].transshipment` | §3 |
| `scenarios[s].y_ks` | §3 |
| `evaluations[].orig_Z1` / `new_Z1` | §4 |
| `evaluations[].new_CV` | §4 |

---

*Last updated automatically — do not edit the JSON examples by hand; re-run the relevant script and verify with `python -c "import json; json.load(open('file'))"` to confirm validity.*
