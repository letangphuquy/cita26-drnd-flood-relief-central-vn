# PB-NSGA Performance Audit — CV-Small v2 Dataset

**Date:** 2026-06-21  
**Triggered by:** User observation that PB-NSGA "performs terribly" on the new v2 planar dataset  
**Conclusion:** PB-NSGA is not broken. It exposes a real algorithmic limitation that is scientifically meaningful for the paper.

---

## 1. Observed Symptoms

Running `run_exp1_baselines.sh` on the v2 CV-Small instance produced:

| Algorithm | HV (v1) | HV (v2) | IGD (v1) | IGD (v2) | Wall time (v2) |
|---|---|---|---|---|---|
| Greedy    | 0.292 | 0.000 | 0.333 | 3.541 | 0.0 s |
| VNS-TS    | 0.777 | 0.042 | 0.117 | 0.827 | 60.1 s |
| GWO-HD    | 0.780 | 0.383 | 0.152 | 0.384 | 0.8 s |
| MILP-AWS  | 0.997 | **0.959** | 0.005 | 0.032 | 49.1 s |
| PB-NSGA   | 0.925 | **0.629** | 0.039 | 0.175 | 1.2 s |

HV and IGD are computed against the combined non-dominated reference front from all five algorithms.

On v1, the PB-NSGA vs MILP-AWS HV gap was 0.072. On v2 it widens to **0.330**. This is the phenomenon to explain.

---

## 2. Root Cause A — Theta Inflation (Why Z1 values are ~9× larger on v2)

This is background context, not the primary performance gap driver.

### 2a. Dataset-level changes

The v2 dataset differs from v1 in two ways that directly inflate the Daganzo theta matrix:

**i. Higher scenario demand** (from a re-seed in scenario generation):

| Scenario | v1 total demand | v2 total demand |
|---|---|---|
| Mild     | 31,407 persons  | 37,140 persons  |
| Severe   | 105,313 persons | 159,647 persons |
| Extreme  | 163,141 persons | **292,646 persons** |

Base populations are identical (same nodes, same coordinates). The difference comes from `random.seed(SEED + 2)` introduced in v2 to decouple road-graph topology from scenario draws. The new seed happened to place epicenters in positions that produce substantially higher exposure values `raw_exp[i]`.

**ii. Fewer road-accessible hub-demand pairs** (from the planar road graph):

| Mode pattern | v1 entries | v2 entries |
|---|---|---|
| road-accessible   | 146 | 110 (−36) |
| water-only        | 142 | 143 (+1)  |
| **air-only**      | 12  | **47 (+35)** |

The v2 road graph removes sea-crossing edges (`_FORBIDDEN_ROAD_PAIRS`) and excludes island nodes. 36 hub-demand-scenario pairs that had road access in v1 now have only air access in v2. Those 35 extra air-only pairs shift from vehicle cap=60 (road) to cap=10 (air) — 6× more trips for the same demand — at 20× higher cost per km. The compound effect on theta is multiplicative.

### 2b. Theta comparison

| | v1 | v2 | ratio |
|---|---|---|---|
| Mean accessible D_is | 4,998 | 8,157 | 1.63× |
| Mean best-mode c_km | $397.96 | $802.54 | 2.02× |
| Mean trips chosen | 169.2 | 404.2 | 2.39× |
| **Mean theta (finite)** | **146,591** | **1,336,578** | **9.1×** |

The 9× theta inflation is expected behavior — not a bug. The planar graph is geographically correct (you cannot drive across Da Nang Bay), and the re-seed was necessary to prevent road-topology changes from corrupting demand draws.

**Important**: PB-NSGA is NOT performing poorly because of theta inflation. MILP-AWS is also affected by the same theta values and still achieves HV=0.959. The performance gap is algorithmic, not dataset-level.

---

## 3. Root Cause B — Suboptimal Inventory Allocation (The real PB-NSGA weakness)

### 3a. The combined reference front

The 15-solution combined non-dominated front is split cleanly between the two algorithms:

| Z1 | Z2 | Algorithm |
|---|---|---|
| $9.50M | 128,154 | **PB-NSGA** |
| $10.23M | 125,636 | **PB-NSGA** |
| $10.37M | 119,253 | **PB-NSGA** |
| $10.57M | 119,181 | **PB-NSGA** |
| $10.75M | 114,917 | **PB-NSGA** |
| $11.06M | 114,693 | **PB-NSGA** |
| $11.08M | 109,923 | MILP-AWS |
| $11.16M | 95,178  | MILP-AWS |
| $11.17M | 94,954  | MILP-AWS |
| $11.17M | 94,721  | MILP-AWS |
| $13.31M | 80,772  | MILP-AWS |
| $13.85M | 77,920  | MILP-AWS |
| $16.44M | 69,287  | MILP-AWS |
| $16.87M | 68,624  | MILP-AWS |
| $17.84M | 67,859  | MILP-AWS |

PB-NSGA owns the **low-Z1 frontier** (all 6 solutions below $11.1M). MILP-AWS owns the **low-Z2 frontier** (all 9 solutions with Z2 < 109,923). There is no overlap — the algorithms are complementary, not competing for the same region.

### 3b. The inventory overfilling finding

At comparable Z2 ≈ 109,000–110,000:

| | MILP-AWS | PB-NSGA |
|---|---|---|
| Z1 | $11.08M | $11.34M |
| Z2 | 109,923 | 109,690 |
| **Total inventory pre-positioned** | **481,766 units** | **657,061 units** |
| **Tam_Ky_Logistics_Hub fill ratio** | **25.5%** | **98.0%** |

Same Z2. PB-NSGA uses **36% more inventory** to achieve it.

Hub capacities on v2 are highly heterogeneous:

| Hub | Capacity |
|---|---|
| Tam_Ky_Logistics_Hub | 207,168 (largest) |
| Da_Nang_Airport_Hub  | 164,561 |
| Dong_Giang_Rescue_Stn | 108,724 |
| Thang_Binh_Depot | 104,651 |
| A_Luoi_Relief_Center | 77,256 (smallest) |

Tam_Ky has 2.7× the capacity of the smallest hub and 1.97× the next-smallest. Filling it to 98% is far more expensive in Z1 than filling it to 25%.

**MILP's LP dual prices** correctly identify that Tam_Ky's marginal inventory contributes little additional Z2 reduction beyond 25% fill — because the demand nodes Tam_Ky uniquely serves (particularly those air-only on v2) already incur a fixed high theta regardless of how much inventory is staged there. The LP relaxation resolves this precisely at each epsilon-constraint value.

**PB-NSGA's evolutionary operators** — crossover and Gaussian mutation on independent R scalars — have no mechanism to discover this. The dominance-based selection signal from the full objective is too coarse to teach the algorithm that `R[Tam_Ky] = 0.25` dominates `R[Tam_Ky] = 0.98` when holding total Z2 fixed.

This effect is consistent across all PB-NSGA solutions with all 5 hubs open: Tam_Ky fill ratio is always 78–100%, never below 78%.

### 3c. Why this was not a problem on v1

On v1, hub capacities average 616,190 (4.7× larger). The absolute cost of filling any single hub to 100% is large in absolute terms but similar across hubs (no single hub is disproportionately capacious). More importantly, with theta 9× smaller, Z2 has low sensitivity to the precise R allocation — a suboptimal distribution still produces acceptable Z2. The "fill everything" heuristic that PB-NSGA converges to works well enough on v1 because the objective landscape is comparatively flat with respect to R.

On v2: high theta + heterogeneous capacities = steep Z2 sensitivity to per-hub R. The difference between `R[Tam_Ky]=0.25` and `R[Tam_Ky]=1.0` is 151,000 inventory units, which translates to a large Z1 penalty. PB-NSGA pays that penalty without the compensating Z2 benefit.

---

## 4. What PB-NSGA Still Does Well on v2

- **Finds the lowest-Z1 solutions**: All 6 reference-front points below $11.1M are PB-NSGA's. MILP-AWS cannot produce solutions with Z1 < $11.08M because its epsilon-constraint sweep doesn't explore that region.
- **Dominates all non-exact baselines**: Greedy HV=0.000, VNS-TS HV=0.042, GWO-HD HV=0.383 vs PB-NSGA HV=0.629.
- **Computational advantage grows on v2**: PB-NSGA runs in 1.19s vs MILP-AWS at 49.1s (41× faster on v2 vs 4.7× faster on v1), because MILP solve time scales with problem hardness.
- **Produces a richer front**: 31 feasible solutions on PF vs 11 for MILP-AWS.

---

## 5. Implications for the Paper

### If the paper reports v1 results only

No action needed. The v1 claims are accurate and not affected by these findings.

### If the paper reports v2 as primary or updated dataset

The claim "PB-NSGA is competitive with MILP-AWS" must be qualified. The accurate framing is:

> *PB-NSGA uniquely covers the cost-efficient region of the Pareto front (Z1 < $11M) and is the only method reaching solutions unavailable to exact solvers within the epsilon-constraint framework. In the deprivation-minimizing region (Z2 < 110K), MILP-AWS is superior due to its exact LP-based optimal inventory allocation. This complementarity suggests a hybrid approach (PB-NSGA for low-Z1 exploration, MILP for Z2-optimal refinement) as a direction for future work.*

### Specific claims to verify against the paper

1. **"PB-NSGA outperforms all baselines"** — True on v2 only if MILP-AWS is excluded from "baselines" (i.e., if it is treated as a reference solver, not a competing heuristic). If MILP-AWS is included as a baseline, PB-NSGA loses on HV and IGD.

2. **"PB-NSGA achieves near-MILP solution quality"** — True on v1 (HV gap 0.072). False on v2 (HV gap 0.330). Needs to be scoped to instances where hub capacity is more homogeneous.

3. **"PB-NSGA is efficient"** — Strongly true. 1.2s vs 49.1s, 41× speedup, still covers 40% of the reference front on v2.

4. **Algorithmic contribution**: The v2 result is scientifically useful as a scope condition — it identifies the class of instances where PB-NSGA's evolutionary R-allocation is insufficient (high theta × heterogeneous hub capacity). This can be reported as a limitation or as motivation for a continuous-subproblem improvement.

---

## 6. Key Numbers for Reference

### v2 CV-Small instance facts
- Hub capacities (units): Da_Nang 164,561 · Tam_Ky 207,168 · A_Luoi 77,256 · Dong_Giang 108,724 · Thang_Binh 104,651
- Hub capacity ratio max/min: 2.68×
- Total demand (extreme scenario): 292,646 persons
- Theta mean (accessible entries): 1,336,578
- Road-accessible hub-demand-scenario entries: 110 / 300 (36.7%)
- Air-only entries: 47 / 300 (15.7%)

### v2 reference front boundary
- PB-NSGA region: Z1 ∈ [$9.50M, $11.06M], Z2 ∈ [114,693, 128,154]
- MILP-AWS region: Z1 ∈ [$11.08M, $17.84M], Z2 ∈ [67,859, 109,923]
- Crossover point: Z1 ≈ $11.08M, Z2 ≈ 109,923 (first MILP point strictly dominates PB-NSGA in Z2)

### Tam_Ky fill ratio comparison (all-5-hub solutions)
- MILP-AWS: consistently 25–44%
- PB-NSGA: consistently 78–100%
- Inventory cost differential at same Z2: ~36% excess by PB-NSGA

---

## 7. Recommendation

Do not re-run or modify the solver or PB-NSGA algorithm. The findings are correct as-is. The appropriate response is:

1. **If the paper submission uses v2 data**: revise the Exp 1 conclusions section to accurately scope PB-NSGA's strengths (low-Z1 coverage, speed, front richness) and acknowledge its limitation in the Z2-optimal region relative to MILP-AWS on heterogeneous-capacity instances.

2. **If the paper submission uses v1 data**: these findings are supplementary and need not appear in the submitted version, but are worth preserving for a journal extension.

3. **Do not frame this as a dataset bug**: both the higher demand and the tighter accessibility are intentional and geographically justified design decisions in v2.
