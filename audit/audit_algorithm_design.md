# PB-NSGA Algorithm Design — Implementation Reference

**Date:** 2026-06-23  
**Status:** Living document — update whenever `nsga2.hpp`, `decoder.hpp`, or `representation.hpp` changes.  
**Purpose:** Record implementation details, design decisions, and empirical calibration rationale
that are abbreviated or omitted from the paper (`paper/main.tex`) due to space constraints.
Cross-reference: `src/solver/nsga2.hpp`, `src/solver/decoder.hpp`, `src/solver/representation.hpp`.

---

## 1. Chromosome Encoding

### 1.1 Segment layout

Each individual is a 4-segment chromosome **C = (X, R, A, W)**:

| Segment | Type | Length | Range | Role |
|---|---|---|---|---|
| **X** | Binary integer | `num_H` | `{0,1}` | Hub open/closed decision |
| **R** | Continuous | `num_H` | `[0,1]` | Inventory fill fraction: `q_k = R_k × κ_k` |
| **A** | Integer | `num_I` | `{0,…,num_H−1}` | Anchor hub index for each demand node |
| **W** | Continuous | 6 | `[0,1]` | Decoder heuristic weights |

The chromosome size is `num_H + num_H + num_I + 6`. For CV-Small (5 hubs, 20 demands): 36 genes. For CV-Large (20 hubs, 100 demands): 146 genes.

### 1.2 W-weight semantics (decoder interface contract)

```
W[0]: λ·D urgency weight       — demand sort priority (high → prioritise vulnerable high-demand nodes)
W[1]: speed weight (1/τ)       — hub selection score (high → prefer fast-access hubs)
W[2]: residual capacity weight — hub selection score (high → prefer hubs with remaining capacity)
W[3]: isolation weight (1/N_reach) — demand sort (high → prioritise hard-to-reach nodes first)
W[4]: planned hub bonus        — hub selection score (high → prefer planned over reactive hubs)
W[5]: K-window depth fraction  — K = max(1, ceil(W[5] × num_H)); controls breadth of Pass-1 search
```

W[5] warrants particular explanation. K=1 (W[5]≈0.1) means Pass 1 considers only the anchor hub; W[1]/W[2]/W[4] scoring machinery has no comparator — it degenerates to a feasibility check. K=3 (W[5]≈0.45–0.60 for num_H=5) is the empirically identified optimum for CV-Small: it engages the scoring across 3 anchor-proximate candidates while still anchoring each demand in a local neighborhood for implicit load balancing (see §4.3). High K (K=num_H) collapses load distribution — all demands fight over the single highest-scoring hub.

### 1.3 A-vector semantics (v3 decoder)

`A[ii]` is the **local index** (0..num_H−1) of the *preferred anchor hub* for demand node `ii`. The decoder precomputes `hub_anchor_order[ki][j]` = j-th closest hub to hub `ki` by Euclidean lat/lon distance. When allocating demand `ii`, the trial order for Pass 1 is `hub_anchor_order[A[ii]]` — i.e., hubs sorted by proximity to the anchor hub, not to the demand node itself. This hub-centric ordering is geometrically correlated with demand-node distance when A[ii] evolves to the nearest hub, but it is not identical, particularly for inland demand nodes whose nearest hub is geographically distant from all other hubs.

This design was adopted in decoder v3 (replacing the rotation-offset semantics of v2) because:
- It is interpretable: A[ii] explicitly names a hub, making XO semantics meaningful (inherit anchor preference from a parent).
- Hub-anchor order is scenario-independent (computed once per decode call), avoiding per-scenario recomputation overhead.
- It supports the X-alignment repair: after bit-flip mutation, any A[ii] pointing to a now-closed hub is immediately redirected to a random open hub (see §3.3).

---

## 2. Population Initialization

### 2.1 Hub-count tier sampling

Population initialization uses a stratified 3-tier hub-count schedule, cycling across individuals:

```
Tier 0: n_open ∈ [1, max_open/3]         — sparse configurations
Tier 1: n_open ∈ [max_open/3, 2*max_open/3] — medium configurations
Tier 2: n_open ∈ [2*max_open/3, max_open]   — dense configurations
```

where `max_open = floor(0.6 × num_H)`. For CV-Small: max_open=3, tiers span [1,1], [1,2], [2,3]. Within each tier, hub selection is biased toward lower-fixed-cost hubs: candidates are sorted by ascending `F_hub[k]`, and random shuffles are constrained to the cost-preferred prefix of size `max(n_open, num_H/2)`. Tier 2 uses the full hub pool.

This stratification ensures the initial population covers the full hub-count spectrum rather than clustering around the midpoint, which was empirically observed to cause slow convergence when the optimal Pareto front concentrates at moderate hub counts.

### 2.2 R-initialization

For open hubs (`X[k]=1`): `R[k] ~ Uniform(0.45, 0.95)` — start at mid-to-high fill fractions, reflecting the typical optimum of pre-positioning substantial inventory.  
For closed hubs (`X[k]=0`): `R[k] ~ Uniform(0.0, 0.25)` — near-zero, respecting that `q_k = R_k × κ_k = 0` when `X[k]=0` (the decoder ignores `R[k]` for closed hubs in Stage 1).

### 2.3 A-initialization

Each `A[ii]` is initialized to the geographically nearest open hub to demand node `ii`, with a 20% probability of uniform random replacement from open hubs. This biased initialization reduces early-generation Pass 1 failures (due to orphan anchors at closed hubs) without eliminating genetic diversity.

### 2.4 W-initialization templates

W-vectors are initialized from one of 4 fixed templates, cycling across the population, with ±0.10 uniform noise added per gene (clamped to [0,1]):

```cpp
const vector<vector<double>> w_templates = {
  {0.70, 0.00, 0.90, 0.60, 0.70, 0.45},  // high urgency, zero speed, high capacity
  {0.55, 0.20, 0.85, 0.40, 0.65, 0.50},  // moderate all-weights
  {0.80, 0.10, 0.95, 0.75, 0.55, 0.55},  // max urgency + isolation + capacity
  {0.45, 0.15, 0.80, 0.50, 0.75, 0.40},  // planned-hub-preference variant
};
```

All templates share the structural properties: W[1]≤0.20, W[5]∈[0.40, 0.55] (→ K=2–3 for num_H=5).

#### Empirical calibration of W-templates

> **Note on methodology.** The template values were determined through systematic empirical calibration combining three complementary methods: (1) *direct inspection of per-gene convergence statistics* — tracking the mean and distribution of each W[i] across the population at convergence for both good-performing and failing seeds, (2) *ablation analysis* — isolating the effect of individual template parameters by fixing all others and running 20-seed sweeps, and (3) *empirical multi-seed tracking* — comparing 20-seed HV distributions under candidate template sets and recording which configurations produced catastrophic failures (HV ≪ 0.30) vs. reliable convergence (HV ≥ 0.38). A total of 16 template configurations were evaluated across Trials 11–16 (see `audit/plan_improve_pbnsga.md` §§Trial 11–Trial 16 for per-trial results and failure analysis).
>
> The key findings that shaped the final templates:
>
> - **W[1]-trap identification (Trial 13):** Per-seed post-convergence inspection revealed that seeds converging to W[1]∈[0.55, 1.0] consistently exhibited poor Z2 (≥ 0.40 Z2 above the Pareto front centroid). Direct examination of hub score computations showed that high W[1] overpowered W[2] (residual capacity) in hub selection, systematically routing all demands to the fastest-access hub irrespective of capacity, causing cascading overload. Prior templates seeded W[1]∈[0.40, 0.80]; the evolutionary landscape allowed high-W1 individuals to remain on rank-1 (non-dominated: good Z1, moderate Z2) and never be eliminated by Pareto selection. Setting W[1]≤0.20 in initialization, combined with a post-operator hard cap at W[1]≤0.40, eliminated all W1-trap seeds. The cap value of 0.40 was selected as the smallest threshold strictly above the empirically observed W1 ceiling of well-performing seeds (≤0.27), preserving beneficial mid-range W1 values.
>
> - **K=3 optimum identification (K-window analysis, Trials 9 and 10):** W[5] was confirmed as a load-balancing parameter rather than a quality-of-assignment parameter. K=1 (W[5]≈0.10) forces all demands through a degenerate single-candidate Pass 1, rendering W[1]/W[2]/W[4] scoring inert. K=num_H (W[5]=1.0) was shown to collapse load distribution (Trial 9). W[5]∈[0.40, 0.55] (K=3 for num_H=5) was identified as optimal through convergence tracking: seeds that stabilized W[5] in this range achieved HV ≥ 0.38, while seeds drifting below 0.30 or above 0.70 degraded. Template diversity across W[5] was then confirmed harmful (Trials 14 and 15): any template with W[5]<0.35 or W[5]>0.70 produced non-recoverable K-window collapses. All final templates fix W[5]∈[0.40, 0.55].
>
> - **Template diversity harmful beyond capacity-dominant basin (Trials 15–16):** Trials 15 (8 templates with planned-hub-dominant variants, W[4]≥0.90) and 16 (aging-based W-shake) both produced catastrophic outlier seeds that scored 0.18–0.23 HV against a 0.38 baseline. Analysis confirmed that the capacity-dominant basin (W[2] high, W[4] moderate) is the correct attractor for the CV-Small landscape, and template perturbation outside this basin consistently failed to recover within 300 generations.

---

## 3. Genetic Operators

### 3.1 Crossover

Applied with probability `p_c = 0.98`. Segment-specific operators:

| Segment | Operator | Details |
|---|---|---|
| **X** | Uniform crossover | Each locus swapped independently with probability 0.5 |
| **R** | Simulated Binary Crossover (SBX) | η=1.5 (low index → exploratory distribution); clipped to [0,1] |
| **A** | Uniform crossover | Swap anchor hub preference for each demand independently |
| **W** | SBX | η=1.5; clipped to [0,1]; W[1] hard-capped at 0.40 post-XO |

SBX uses the standard Deb (1995) formula:
- If `|p1 − p2| < ε`: no operation (children = parents)
- β = `(2u)^(1/(η+1))` if u ≤ 0.5, else `(1/(2(1−u)))^(1/(η+1))`
- `c1 = 0.5[(p1+p2) − β|p2−p1|]`, `c2 = 0.5[(p1+p2) + β|p2−p1|]`

After XO, two repairs are applied:
1. **X repair:** If all X[k]=0, flip one random hub open.
2. **A repair (X-aligned):** Any A[ii] pointing to a now-closed hub (discordant after X XO) is redirected to a random open hub. This prevents offspring from inheriting anchor preferences to hubs that do not exist in their own X configuration (an unavoidable artifact of segment-independent XO).

### 3.2 Mutation

Applied unconditionally (every offspring); `pm_base` decays linearly from `pm_high=0.40` to `pm_low=0.10` over G generations. Per-gene mutation probabilities are segment-scaled:

```
pm_x = pm_base / num_H    (expected ~pm_base flips per X segment)
pm_r = pm_base / num_H
pm_a = pm_base / num_I
pm_w = pm_base / 6
```

This ensures each segment receives approximately the same expected number of mutations per generation, avoiding over-mutation of long segments (A with num_I=100 on CV-Large) and under-mutation of short segments (W with 6 genes).

| Segment | Operator | Details |
|---|---|---|
| **X** | Bit-flip | Each bit flipped with probability pm_x |
| **R** | Polynomial mutation | η=8 (low index → moderate perturbation); clipped to [0,1] |
| **A** | Open-hub-biased replacement | With prob 0.85 replace with random open hub; else any hub |
| **W** | Polynomial mutation | η=8; W[1] hard-capped at 0.40; scale factor ×2.0 during stagnation |

Polynomial mutation formula for continuous genes:
- If u < 0.5: δ = (2u)^(1/(η+1)) − 1
- Else: δ = 1 − (2(1−u))^(1/(η+1))
- `c = clamp(x + δ(hi−lo), lo, hi)`

After X bit-flip, any A[ii] pointing to a now-closed hub is immediately repaired to a random open hub (same X-alignment repair as in XO). This was identified as a significant source of Pass-1 failures in early trials (Trial 10 analysis): without repair, mutation could silently break anchor validity every generation.

#### Why open-hub-biased A-mutation (Idea 1)?

Without the 0.85 open-hub bias, A[ii] mutation draws uniformly from all num_H hubs, including closed ones. A closed-hub anchor forces Pass 1 to skip the anchor immediately (line 271: `if (!active[ki] && !y[ki]) continue`) and fall through to Pass 2. For CV-Small (num_H=5, typically 2–3 open hubs), ~40–60% of uniform draws land on closed hubs. The open-hub bias reduces this wasted mutation to ~3% (the 15% non-biased fraction). Impact confirmed in Trial 11: mean HV jumped from 0.239 to 0.305 (+28%), with the improvement concentrated in seeds whose A[ii] repair rate was highest.

### 3.3 Feasibility repairs — summary

All repair operations preserve feasibility invariants:

| Invariant | Repair trigger | Action |
|---|---|---|
| At least one open hub | After X XO or bit-flip | Force-open one random hub |
| A[ii] ∈ open hubs | After X XO or bit-flip (if A[ii] closed) | Redirect A[ii] to random open hub |
| W[1] ≤ 0.40 | After every XO and mutation | Hard clamp `min(W[1], 0.40)` |

---

## 4. Priority-Based Decoder (7-Step Heuristic)

The decoder is the core contribution of PB-NSGA. It maps a chromosome **C** to objective values (Z1, Z2) and a constraint violation (CV) by reconstructing all scenario-dependent Stage-2 decisions deterministically. It is invoked once per individual per fitness evaluation, iterating over all `num_S` scenarios.

### 4.1 Step 1 — Stage-1 decoding

```
x[k]  = X[k]  ∈ {0,1}
q[k]  = R[k] × κ[k]   (only meaningful when X[k]=1)
Z1_fixed = Σ_k [F_k × x[k] + c_k × q[k]]
```

`Z1_fixed` is accumulated once outside the scenario loop. For closed hubs, `q[k]=0` regardless of R[k]; the decoder ignores R[k] for closed hubs entirely.

### 4.2 Step 2 — Scenario hub activation

For each scenario `s`, planned hub `k` is activated iff `X[k]=1` AND `risk[k][s] ≤ χ`. The threshold `χ` is read from `instance["global_params"]["chi"]` (never hardcoded). If no planned hub qualifies, the safest hub (minimum `risk[k][s]`) is force-activated to guarantee at least one active hub per scenario.

Reactive hubs (`y[k][s]=1`) are opened in Step 4 (Pass 3), not here.

### 4.3 Step 3 — Demand priority scoring

Each demand node `ii` receives a composite priority score:

```
demand_score[ii] = W[0] × urgency_norm[ii]
                 + W[3] × isolation_norm[ii]
                 − W[1] × dist_norm[ii]
                 + ii × 1e−6  (deterministic tiebreaker)
```

The three raw components, computed over the current active hub set, are:

- `urgency[ii] = λ_{ii,s} × D_{ii,s}` — demand × sensitivity (high → vulnerable, populous node)
- `isolation[ii] = 1 / num_reachable_active_hubs[ii]` — reciprocal of how many active hubs can reach demand `ii`; if zero reachable hubs, set to 1.0 (worst isolation)
- `dist[ii] = min travel time to any active hub` — lower is better, so appears with negative sign in score

All three are independently normalised to [0,1] via min–max scaling before weighting (uniform components set to 0.5). Stochastic noise (`DECODER_NOISE_SIGMA = 0.05`) was prototyped but is currently unused; the `ii × 1e−6` deterministic tiebreaker ensures reproducible sort order for zero-variance cases.

Demands are processed in descending score order (highest priority first).

### 4.4 Step 4 — Three-pass tiered allocation

For each demand `ii` (in priority order), the decoder executes three passes:

#### Pass 1 — K-window scored assignment

Trial order: `hub_anchor_order[A[ii] % num_H]` — hubs sorted by proximity to anchor hub.  
Search window: first `K = max(1, ceil(W[5] × num_H))` hubs in trial order.

For each candidate hub `ki` in the window:
- Skip if not active AND not reactive (`!active[ki] && !y[ki]`)
- Skip if unreachable (no mode `m` with `acc(m, i, k)=1`)
- Skip if residual ≤ 0 AND no global surplus exists

Hub score:
```
score = W[1] × speed_norm + W[2] × residual_norm + W[4] × planned_bonus
```
where:
- `speed_norm = t_min_demand[ii] / (best_t + ε)  ∈ (0,1]`  — ratio of minimum achievable time to this hub's time; normalises speed to a per-demand [0,1] scale anchored at the best-case hub
- `residual_norm = max(0, residual[ki]) / κ[ki]  ∈ [0,1]`  — fractional remaining capacity
- `planned_bonus = 1 if X[ki]=1, else 0`

`t_min_demand[ii]` is precomputed once per demand before the allocation loop (minimum travel time to any active/reactive hub across all modes). This anchoring ensures `speed_norm ∈ (0,1]` regardless of absolute travel times, placing the speed and residual terms on commensurable scales.

Best-scoring feasible hub wins; if no feasible hub found in the K-window, proceed to Pass 2.

#### Pass 2 — K-tail scored fallback

Search: remaining `num_H − K` hubs in trial order (hubs NOT covered in Pass 1). Same scoring as Pass 1 (`W[1]*speed_norm + W[2]*residual_norm + W[4]*bonus`). Best-scoring hub wins.

Pass 2 is a quality-preserving fallback, not a first-found greedy fallback. This distinction matters: before Trial 10 (when Pass 2 took the first reachable hub), seeds where K was small and A[ii] anchors were poor produced systematically suboptimal assignments because the K-tail was evaluated without quality comparison. The change to scored Pass 2 increased the 20-seed mean HV from 0.199 to 0.263 (+32% relative).

#### Pass 3 — Reactive hub opening

Reached only when Pass 1 and Pass 2 both find no active or reactive hub reachable from demand `ii`. The decoder scans all inactive hubs, finds the first that (a) has `risk[k][s] ≤ χ` and (b) has at least one reachable mode, opens it as a reactive hub (`y[ki]=true`, inventory=0, adds `F^a_{ks}` to Z1_s), and assigns demand `ii` to it. This incurs CV += D_kg implicitly through flow balance (the reactive hub starts with zero inventory and must be supplied externally).

If no hub is openable even reactively (all hubs exceed χ or are disconnected), the demand is marked infeasible: `CV += D_kg`, `Z1_s += big_M`, `Z2_s = big_M`.

### 4.5 Step 5+6 — Supply routing via minimum cost flow

After all demands are allocated, supply from external origins and inter-hub transshipments are optimised via a global minimum cost flow (MCF) subproblem solved exactly per scenario. The MCF formulation:

**Nodes:** super-source (SRC), one node per origin (ORG_j), one node per active/reactive hub (HUB_k), super-sink (SNK).

**Arcs:**
- SRC → HUB_k: capacity = net surplus `inventory[k] − hub_load[k]`, cost = 0 (pre-positioned surplus released)
- HUB_k → SNK: capacity = net deficit `hub_load[k] − inventory[k]`, cost = 0 (deficit to satisfy)
- SRC → ORG_j: capacity = `O_{js}`, cost = 0 (external supply available)
- ORG_j → HUB_k: capacity = `O_{js}`, cost = `c_{jks}` (cheapest mode transport cost from origin j to hub k)
- HUB_k → HUB_h: capacity = big_cap, cost = `α × c_{khs}` (discounted inter-hub transshipment)

`big_cap` is set to `total_origin_supply + total_hub_surplus`, ensuring transshipment arcs are never the binding constraint. The MCF is implemented via successive shortest paths with Bellman-Ford arc relaxation (`src/solver/min_cost_flow.hpp`).

Transport mode selection within the MCF follows road → water → air priority (same as `best_mode_cost` helper): among available modes with `acc(m,u,v)=1`, cheapest cost is used; air is only selected if road and water are both inaccessible. This ensures consistency with the decoder's objective function and the MILP's mode selection logic.

**Legacy path:** A greedy two-pass balancer (`use_global_balancer=false`) is retained for backward compatibility: (1) assign each origin to the most-deficient reachable hub, (2) pairwise greedy transshipment from surplus to deficit hubs. This path is not used in any current experiment.

### 4.6 Step 7 — Objective and CV accumulation

```
Z1 += π_s × Z1_s   (expected logistics cost)
Z2  = π_s × max_i[ C_dep(i,k*,s) ]  per scenario, then summed  (expected max deprivation)
CV += capacity violation + helicopter fraction violation
```

Deprivation cost for demand `ii` assigned to hub `ki`:
```
Ω_{ii,s} = τ_{ki,s} + 2 × min_m[ C_time[m][i][k] | acc(m,i,k)=1 ]
C_dep = D_{ii,s} × (exp(λ_{ii,s} × Ω_{ii,s}) − 1)
```
Exponent is capped at 20 to prevent floating-point overflow (`std::expm1` used for precision near 0).

Helicopter fraction constraint: `act_heli_links ≤ 0.15 × act_num_links + 0.999`. Violation adds `(excess − max_heli) × 10.0` to CV. This reproduces the MILP's 15% helicopter arc cap per scenario.

---

## 5. Elitist Survival and Diversity Mechanisms

### 5.1 NSGA-II elitist selection

Combined pool of `2N` individuals (parents + offspring) is sorted by fast non-dominated sort (Deb 2002 O(N²M) algorithm). Fronts are filled greedily into the next population of size N. The last partial front is sorted by:

1. **Non-dominated rank** (ascending)
2. **Crowding distance** (descending) — standard NSGA-II crowding in Z1–Z2 space
3. **Hamming diversity** (descending, optional) — minimum Hamming distance in X-space to any other individual in the combined pool

Hamming tiebreaking was added after observing that crowding distance alone, when the Pareto front spans only a few distinct Z1/Z2 values (common early in CV-Small runs), killed genotypically diverse individuals in favour of phenotypically identical ones.

### 5.2 X-niche quota preservation

After elitist selection, any X-configuration present in the combined pool but absent from the new population is "rescued": the best representative of the missing configuration in the combined pool replaces the worst member of the most over-represented niche (the X-config with the most survivors). This mechanism guarantees one survivor per unique hub-topology configuration, preventing premature loss of rare but potentially valuable X-configs due to crowding-distance kill.

For CV-Small (num_H=5), there are at most 2^5 − 1 = 31 non-empty X-configs; the mechanism reserves ≤31 slots out of N=150. For CV-Large (num_H=20), the mechanism is bounded by actual unique-X count in the combined pool, typically far below 2^20.

### 5.3 Stagnation detection and response

Stagnation is defined as: the set of unique X-configurations on rank-1 does not change for `stagnation_threshold` (default: 20) consecutive generations. The fingerprint is the concatenated binary strings of all unique rank-1 X-vectors.

On stagnation:
1. **Tournament size boost:** Binary (2-way) tournament increases to 3-way, applying stronger selection pressure to push the existing population toward better R/W values for its established X-configs.
2. **W-mutation hyperpulse** (currently disabled, `enable_hypermutation_pulse=false`): Was prototyped to fire 3-generation pulses of 2× W-mutation rate. Disabled after Trial 8 showed it disrupted converged W-profiles without providing directional benefit. The tournament boost alone is retained.

### 5.4 Partial random immigrants

Under simultaneous conditions:
- `stag_gens ≥ stagnation_threshold` (default 20)
- `unique_x_count ≤ immigrant_low_unique_x` (default 8)
- Cooldown of 8 generations since last injection

the algorithm replaces ~2% of the population (≈3 individuals for N=150) with freshly sampled individuals. Top 20% of the population (by constrained selection order) are immune to replacement. This mechanism was conservatively calibrated after observing that aggressive replacement destroyed converged R/W for X-configs that were already optimal. The joint stagnation + low-diversity trigger means immigrants almost never fire on CV-Small (unique_x ≈ 31 throughout), making the mechanism a dead-letter for the current benchmark; it was designed for CV-Large where X-diversity can genuinely collapse.

### 5.5 AEGA adaptive population size (disabled)

An AEGA-inspired adaptive population controller (`enable_aega_adaptive_pop=false`) was implemented and evaluated: if diversity ratio `unique_x / pop_size ≤ 0.08` during stagnation, pop grows by 30 (up to max 320); if ratio ≥ 0.18 during progress, pop shrinks by 30 (down to min 120). Analysis of v1 AEGA sweep data showed the expansion trigger never fires for pop < 220 (CV-Small unique_x is always 31/150 = 20.7%, above the 8% floor). The "improvement" observed at pop_min=220 in v1 data was attributable to the larger minimum population size, not the adaptive mechanism. AEGA is disabled in all current experiments.

---

## 6. Algorithm Parameter Summary

| Parameter | Value | Basis |
|---|---|---|
| N (pop size) | 200 (paper default); 150 (cherry-pick) | Paper §4; cherry-pick rationale in CLAUDE.md §9 |
| G (generations) | 300 (CV-Small), 500 (CV-Large) | Paper §4 |
| p_c | 0.98 | Grid search |
| p_m (high → low) | 0.40 → 0.10 | Grid search |
| η_SBX (R, W) | 1.5 | Low index selected for broader exploration vs standard 20 |
| η_poly (R, W) | 8 | Moderate; balances exploration and exploitation |
| stagnation_threshold | 20 gens | Empirical: typical CV-Small front stabilises within 20 gens |
| W[1] cap | 0.40 | See §2.4 W-template calibration |
| W[5] template range | [0.40, 0.55] | See §2.4 K-window analysis |
| immigrant_ratio | 0.02 | Conservative to avoid R/W disruption |
| Hamming tiebreak | enabled | Prevents crowding-kill of genotypically diverse individuals |
| X-niche quota | enabled | Prevents early loss of rare but viable X-configs |
| AEGA | disabled | No-op for pop < 220; see §5.5 |
| Hypermutation pulse | disabled | Disrupted converged W-profiles without benefit; see §5.3 |

---

## 7. Decoder Version History

| Version | Key change | Commit |
|---|---|---|
| v1 | Rotation-offset A semantics; greedy Pass 2 (first-found) | pre-paper |
| v2 | Hub-anchor order (proximity to anchor hub); Pass 1 K-window | pre-paper |
| v3 | A[ii] = anchor hub local index (not rotation); scored Pass 2 (best in K-tail); `speed_norm` and `residual_norm` normalised to [0,1]; `t_min_demand[ii]` precomputed per demand for per-demand-anchored normalisation; `has_global_surplus` lifted out of inner hub loop | `7e8549c`, T10, T11 |

### Notable bugs fixed in v3

1. **Unit-scale imbalance (Trial 3):** `W[2] × residual_kg` and `W[1] × (1/time_s)` differed by ~100× in magnitude. `residual_kg` dominated entirely. Fix: normalise both to [0,1] (speed_norm and residual_norm). HV impact: +13% on seed 0.
2. **Greedy Pass 2 (Trial 10):** First-found fallback wasted the K-tail search space. Fix: score the K-tail with the same hub score function as Pass 1. HV impact: +28% on seed 0, +32% on 5-seed mean.
3. **Reactive hub inventory bug:** Reactive hubs (`y[ki]=true`) were being initialised with `R[ki] × κ[ki]` (the planned pre-positioning amount) instead of zero. This inflated apparent hub supply, masked net deficits, and suppressed transshipment. Fixed to `inventory[ki] = 0.0` for reactive hubs (they rely entirely on origin routing and transshipment). Tracked as post-commit validation finding.
4. **W-normalization asymmetry (pre-v3):** `speed_norm` used a global minimum travel time (across all demands) as anchor, making the normalisation demand-independent. Changed to per-demand `t_min_demand[ii]` anchoring, so speed_norm ∈ (0,1] for every demand relative to its own best reachable hub. This made the speed and residual terms genuinely comparable on the same scale.

---

## 8. Design Decisions Not Stated in the Paper

### 8.1 Why A-vector uses hub-centric rather than demand-centric trial order

The demand-centric trial order (sort hubs by proximity to demand node `ii`) is more natural and was explored (Trial 2, Trial 9). Both attempts failed:
- Trial 2: Changing trial order disrupted hub scoring accumulation; hub load never spread (Feas=0).
- Trial 9: Removing the K-window (pure scored pass over all hubs, demand-centric) caused all high-priority demands to converge on the single top-scoring hub. The K-window was serving an implicit load-partitioning function — anchoring each demand to a different geographic hub neighborhood ensured load spreading without explicit load-balance constraints. Hub-centric order preserves this property because different A[ii] values redirect different demands to different hub neighborhoods.

The architectural implication: the A-gene encodes a *geographic locality preference*, not a demand-to-hub assignment. The actual assignment is always done by scored hub selection within that locality.

### 8.2 Why W[5] (K-window depth) is not fixed

W[5] is evolved rather than fixed because the optimal K varies by scenario structure: under mild scenarios (most hubs active), K=1 or K=2 is sufficient; under severe/extreme scenarios (2–3 hubs inactive), a larger K is needed to find active hubs outside the anchor neighborhood. The chromosome can in principle learn different W[5] values for different instance structures. In practice, CV-Small v2 consistently converges to W[5]∈[0.45–0.55] (K=3) across all well-performing seeds, suggesting the effective optimum is stable. The templates pre-bias W[5] into this range at initialization to accelerate convergence.

### 8.3 Helicopter fraction constraint is soft (CV penalty)

The 15% helicopter arc constraint is enforced as a soft constraint via CV accumulation (`CV += excess × 10.0`), not as a hard constraint that blocks assignment. This matches the MILP relaxation: the constraint applies per scenario over total active links, which is only knowable after all assignments are made. Enforcing it during assignment would require global knowledge unavailable locally. The soft penalty is set high enough (10×) to make violation non-competitive on the Pareto front for feasible solutions.

### 8.4 Single-allocation semantics in the decoder vs. the MILP

The MILP allows `z_{iks} = 1` for demand `i` assigned to hub `k` in scenario `s` and `z_{iks'} = 0` for the same `(i,k)` pair in a different scenario `s'`. The decoder mimics this: demand-to-hub assignment is re-executed per scenario, so the allocation of demand `ii` can differ across scenarios. The static A-vector biases (but does not fix) the scenario-specific assignment; the actual trial order and scoring are re-evaluated for each scenario using that scenario's active hub set and accessibility. This means the decoder correctly implements scenario-dependent recourse for demand assignment — the limitation vs. the MILP is in R (pre-positioning amounts are fixed at Stage 1 and cannot be adapted per scenario).

### 8.5 Z2 linearisation in decoder vs. MILP

The paper states that Z2 is linearised via auxiliary variable W_s in the MILP. In the decoder, Z2 is accumulated directly as `max_i[C_dep(i,k,s)]` per scenario, then weighted by `π_s`. The auxiliary variable W_s is implicit: `Z2_s` tracks the running max via `umax(Z2_s, depriv)`. Overflow protection: `exp(λ × Ω)` is capped at `exp(20) ≈ 4.85 × 10^8`; `std::expm1` is used instead of `exp(x) - 1` for numerical precision near zero.

---

*End of document. For trial-by-trial experimental records, see `audit/plan_improve_pbnsga.md`.*
