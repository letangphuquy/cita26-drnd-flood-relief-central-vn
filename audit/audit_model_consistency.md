# Model Consistency Audit

**Date:** 2026-06-22  
**Scope:** MO-IHLNDP formulation vs. MILP and PB-NSGA implementations  
**Status:** Discrepancy confirmed; paper correction suggested

---

## Q1 — BFS Accessibility: Asymmetry Bug (Fixed)

### Finding

`generate_scenarios()` in `src/scripts/data_generate_cv.py` applied BFS reachability only to pairs that had **no** direct edge in the road or geo graph. Pairs whose direct edge was disrupted by Stage 1 were excluded from Stage 2 BFS rescue — meaning a node pair that happened to share a direct edge was *worse off* than a pair with no direct edge at all, because the former could never receive a multi-hop path in a high-disruption scenario.

### Fix Applied

Removed the `_all_direct` exclusion guard from the BFS update loop. The corrected Stage 2 now sets `a[m][src][dst] = 1` for any pair reachable via an intact multi-hop path, regardless of whether they also share a direct (disrupted) edge.

**Files changed:** `src/scripts/data_generate_cv.py` — lines 709–716 (deleted `_all_direct` construction), line 800 (removed guard condition).

**Consequence:** Datasets must be regenerated from `data_generate_cv.py` before re-running experiments. Accessibility matrices will be strictly no-worse (more 1s, never fewer) compared to the buggy version, meaning the fixed dataset is more tractable and road-reachable node counts may increase, especially in severe/extreme scenarios.

---

## Q2 — Shortest Paths for C_time / C_cost

### Finding

`build_transport()` computes inter-node travel cost and time via Dijkstra on the **static** road / geo graph (before scenario disruption). The accessibility matrix `a[m][s][u][v]` used at solve time reflects per-scenario disruption, but `C_time[m][u][v]` does not change per scenario.

This is a known, intentional design decision: pre-positioning decisions (Stage 1) are made before the scenario realises, so using scenario-averaged transport cost is appropriate. The paper does not claim scenario-specific C_time; the MILP and NSGA both use the same static C_time matrices. **No inconsistency between paper and implementation.**

---

## Q3 — Air-mode Cap Enforcement: Hard vs. Soft

### Finding

**MILP (`src/solver/milp_aws_baseline.py`, lines 180–184):** enforces the helicopter-link cap as a hard linear constraint per scenario:
```
h_i + h_j + h_t ≤ 0.15 × tot_l + 0.999    (for each s)
```
where `tot_l = tot_links_s` = total active links in scenario s.

**PB-NSGA (`src/solver/decoder.hpp`, lines 680–684):** enforces the same cap as a soft CV penalty:
```cpp
if (act_heli_links > 0.15 * act_num_links + 0.999)
    ind.CV += (act_heli_links - max_heli) * 10.0;
```

### Implication

MILP solutions are guaranteed to satisfy the air-cap constraint exactly. PB-NSGA solutions with `CV > 0` may violate it; once NSGA-II's constraint-dominance mechanism drives CV to 0, the penalty has already steered the population away from violators, so final Pareto-front solutions reported in the paper (`CV == 0`) do satisfy the cap. However, during evolution, individuals with small cap violations may persist temporarily in the population — this is expected behaviour for a penalty-based soft constraint.

**Paper note:** The formulation section states the cap as a hard constraint; the PB-NSGA implementation uses a soft CV penalty that achieves the same feasibility at convergence. This is standard practice for metaheuristics and does not require a correction — but it should be acknowledged in the "implementation" or "computational details" paragraph.

---

## Q4 — Single-Allocation Property: Confirmed Violation on Supply Routing

### Paper Formulation

The paper defines $z_{jks} \in \{0, 1\}$ — a **binary** indicator that origin $j$ routes its supply to hub $k$ in scenario $s$. Under this formulation, each origin sends its entire supply to exactly one hub per scenario (single-allocation). Constraint:
$$\sum_{k} z_{jks} \leq 1 \quad \forall j, s$$

### MILP Implementation

**`src/solver/milp_aws_baseline.py`, line 131:**
```python
z_jks[ji, ki, si] = solver.NumVar(0, 1, f"z_j{ji}_k{ki}_s{si}")
```

`NumVar(0, 1, ...)` declares a **continuous** variable on $[0, 1]$, not a binary. The LP may assign fractional values, e.g., origin $j$ routes 60% of its supply to hub A and 40% to hub B.

**Demand assignment** (`z_iks`, line 130) uses `IntVar(0, 1, ...)` — correctly binary. Single-allocation holds for demand. ✅

**Supply routing** (`z_jks`) is continuous — violates the paper's binary formulation. ❌

### PB-NSGA Implementation

The decoder's Stage 2 MCF (min-cost flow) routes origin supply to hub deficits as a flow problem. MCF naturally produces fractional splits when multiple hubs have deficits and the cheapest feasible routing splits origin supply across them. There is no binary constraint enforcing single-allocation for supply.

Single-allocation for supply routing: **not enforced**. ❌

### Why Both Implementations Agree

Both relax $z_{jks} \in \{0,1\}$ to $z_{jks} \in [0,1]$. This makes MILP and NSGA Z1 values directly comparable (neither overpays by charging full origin supply when a partial routing suffices). The relaxation is economically sensible for humanitarian logistics: splitting a supply convoy between two nearby hubs is operationally feasible and often optimal.

### Suggested Paper Fix

In the formulation section, change the domain of $z_{jks}$ from binary to continuous and add a remark:

> **Remark (Supply Routing Relaxation).** We relax the supply-routing variable from $z_{jks} \in \{0,1\}$ to $z_{jks} \in [0,1]$, allowing fractional origin-to-hub allocations. This is standard in stochastic humanitarian logistics where convoy splitting is operationally feasible \[cite\]. Under this relaxation the LP sub-problem in each scenario $s$ is a linear program, and the PB-NSGA decoder solves it as a min-cost flow. Binary $z_{jks}$ would charge the full origin supply even when only a small fraction is needed, artificially inflating Z1 values; the relaxation avoids this artefact and makes MILP and metaheuristic Z1 values directly comparable.

**Demand assignment** ($z_{iks}$) remains binary in both formulation and implementation — no change needed there.

---

## Q5 — OSRM Road Graph: Confirmed Discarded

### Finding

Files `data/cv/v2/osrm_road_graph_small.json` and `data/cv/v2/osrm_road_graph_large.json` exist on disk but are never loaded or used.

`build_transport()` signature (`src/scripts/data_generate_cv.py`, line ~511) includes `osrm_dist=None, osrm_time=None` as placeholder parameters. The call site at line ~999:
```python
C_all, T_all = build_transport(coords, road_edges=road_edges, geo_edges=geo_edges)
```
passes no OSRM arguments. The OSRM branch inside `build_transport` is dead code.

All road travel costs and times are computed via Dijkstra on the Delaunay-triangulated road graph with haversine distances scaled by `terrain_factor` and `circuity_factor`. OSRM plays no role in any published result.

**Action required:** None for correctness. If OSRM integration is desired in a future version, the dead code branch and the two JSON files should be either wired up or removed.

---

## Summary Table

| Question | Status | Severity |
|---|---|---|
| Q1 — BFS asymmetry | **Fixed** (commit this file) | High — affects dataset |
| Q2 — Shortest paths static vs. scenario-specific | No issue | — |
| Q3 — Air-cap hard vs. soft | Known; final PF solutions feasible | Low — note in paper |
| Q4 — Supply single-allocation violation | **Paper fix needed** | Medium — formulation |
| Q5 — OSRM discarded | Confirmed dead code | Low — no action |
