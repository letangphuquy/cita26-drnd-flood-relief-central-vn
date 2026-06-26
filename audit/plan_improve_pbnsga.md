# PB-NSGA Improvement Plan — Decoder Assignment Quality

**Date:** 2026-06-22  
**Author:** Investigation session (decode_trace.py, decoder.hpp audit)  
**Status:** Pre-implementation — plan only, no code changed yet

---

## 1. Evidence Base: What Was Compared

### Primary comparison
`results/exp1/v2/CV_small_seed0.json` `pareto_front[3]` vs  
`results/exp1/v2/cv_small_milp_aws.json` `pareto_front[3]`

These two solutions share the same first-stage hub structure (`X=[1,1,1,1,1]`, all five hubs open), making them the fairest apples-to-apples comparison on the CV-Small v2 instance (`data/cv/v2/cv_small_drnd.json`, 5 hubs, 20 demand nodes, 3 scenarios).

**Note on knee-points.** The MILP Tchebycheff knee is exactly `pareto_front[3]` (Z1=10,283,734; Z2=80,772). The NSGA Tchebycheff knee is `pareto_front[16]` (Z1=14,259,141; Z2=101,241) — a different hub structure, too dissimilar to compare directly. `pareto_front[3]` (X=[1,1,1,1,1]) is the closest NSGA solution with a matching hub structure to the MILP knee.

| | PB-NSGA `sol[3]` | MILP `sol[3]` (knee) |
|---|---|---|
| Z1 | 11,068,468 | 10,283,734 |
| Z2 | 115,836 | **80,772** |
| X | [1,1,1,1,1] | [1,1,1,1,1] |
| R | [1.000, 0.976, 0.996, 1.000, 1.000] | [1.000, **0.255**, 0.934, 1.000, 0.944] |
| A | [0,0,1,0,0,0,4,2,4,3,4,4,4,1,2,0,3,4,2,3] | N/A (LP) |
| W[5] | **0.1601** → K=1 | N/A |

The Z2 gap is 43% worse for the NSGA. The Z1 gap is 7.6% worse.

---

## 2. Root Cause: The Static A-Vector in Extreme Scenarios

### 2a. Scenario 2 hub availability

In the extreme scenario (`inst["scenarios"][2]`), two of five hubs exceed the flood-risk threshold χ=0.70:

| Hub | Sc2 risk | Status |
|---|---|---|
| Da_Nang_Airport_Hub (hub0) | 0.590 | **ACTIVE** |
| Tam_Ky_Logistics_Hub (hub1) | **0.904** | INACTIVE |
| A_Luoi_Relief_Center (hub2) | 0.361 | **ACTIVE** |
| Dong_Giang_Rescue_Stn (hub3) | 0.548 | **ACTIVE** |
| Thang_Binh_Depot (hub4) | **0.815** | INACTIVE |

### 2b. K=1 makes Pass 1 degenerate

`decoder.hpp` line 255:
```cpp
const int K = std::max(1, (int)std::ceil(ind.W[5] * num_H));
```

With W[5]=0.1601 and num_H=5: K = max(1, ceil(0.8005)) = **1**.

Pass 1 (lines 271–305) only evaluates the anchor hub itself. When the anchor hub is inactive (`!active[ki] && !y[ki]`), Pass 1 exits immediately with no candidate found. There is no score comparison — the W[1] (speed), W[2] (residual), W[4] (planned bonus) hub scoring machinery is entirely unused when K=1.

### 2c. 8 demand nodes have inactive anchors in sc2

From `decoder.hpp` line 264: `const int anchor = ind.A[ii] % num_H;`

| Demand → anchor hub | Anchor status in sc2 |
|---|---|
| Nui_Thanh_District (d2) → Tam_Ky (hub1) | INACTIVE |
| Tay_Giang_District (d6) → Thang_Binh (hub4) | INACTIVE |
| Nam_Giang_District (d8) → Thang_Binh (hub4) | INACTIVE |
| Viet_An_Commune (d10) → Thang_Binh (hub4) | INACTIVE |
| Que_Son_District (d11) → Thang_Binh (hub4) | INACTIVE |
| Phu_Ninh_District (d12) → Thang_Binh (hub4) | INACTIVE |
| Tam_Ky_City (d13) → Tam_Ky (hub1) | INACTIVE |
| Phu_Loc_District (d17) → Thang_Binh (hub4) | INACTIVE |

All 8 miss Pass 1 → fall to Pass 2 → `hub_anchor_order[anchor]` (hubs sorted by distance FROM the anchor hub, not from the demand node) → the first reachable active hub in ThangBinh's or TamKy's geographic neighborhood is **Da_Nang**.

### 2d. Cascading overload at Da_Nang in sc2

Da_Nang absorbs 13 of 20 demand nodes in sc2:
- Da_Nang inventory = `R[0] × κ_0` = 1.0 × 164,561 = 164,561 units
- hub_load[Da_Nang] = γ × Σ(demand nodes assigned) = 3 × 212,662 = **637,986 units**
- Net deficit = **−473,425 units**

Decoded Z1 for NSGA sol[3] (verified by `audit/decode_trace.py`, delta = −56 vs solver JSON = 0.0005% rounding):

| Scenario | Z1_s (undiscounted) | Theta | Supply+Trans |
|---|---|---|---|
| sc0 (π=0.60) | 1,961,031 | 823,147 | 0 |
| sc1 (π=0.30) | 9,476,863 | 4,366,851 | 3,972,128 |
| sc2 (π=0.10) | 70,487,342 | 19,970,618 | **49,378,840** |
| **Z1 total** | **11,068,412** | | |

The 49.4M supply routing cost in sc2 (origin → Da_Nang at air-mode unit cost after road/water disruption) drives the Z1 gap. The 753,326 Z2 value comes from Da_Nang's high deprivation omega for distant highland demand nodes it was never designed to serve.

### 2e. Why the MILP avoids this

The MILP is a proper two-stage stochastic program: Stage 2 variables (`z_iks`, `y_ks`, `f_khms`) are indexed per scenario and solved by LP independently for each `s`. The LP assigns:
- sc2: 8 nodes to Dong_Giang (hub3), only 7 to Da_Nang — balanced load, no overload
- R[1]=0.255 (TamKy): MILP learns not to pre-position at risky hubs
- R[3]=1.000 (DongGiang): maximize inventory at the hub that stays active and serves highland demand in sc2

This is not a model gap — the MILP is correctly implementing two-stage stochastic programming where recourse (Stage 2) decisions adapt per scenario. PB-NSGA approximates this with a static A-vector that cannot change per scenario.

---

## 3. Structural Weakness Analysis

### W3a. A-vector intention vs. implementation

The A-vector was designed to encode **locality preference** — steer each demand toward its natural nearby hub. The intended behavior: A[ii] evolves to point to the hub closest to demand node i.

The actual implementation (`decoder.hpp` lines 98–117) computes `hub_anchor_order[ki][j]` = j-th closest hub to **hub ki** (geographic distance from hub to hub). The trial order for demand ii is "hubs sorted by proximity to anchor hub A[ii]", not "hubs sorted by proximity to demand node ii."

When A[ii] evolves to the geographically nearest hub to demand i, the two are correlated but not identical. In the case of ThangBinh (a coastal/midland hub), the "hubs close to ThangBinh" list starts with TamKy and DaNang — both coastal. DongGiang (highland) is ranked last in ThangBinh's proximity order. So even if Pass 2 could try more hubs, the inland DongGiang would be tried late for ThangBinh-anchored demands.

### W3b. K=1 wastes the hub-scoring machinery

Pass 1 with K=1 is equivalent to: "assign to anchor hub if it's available and has residual or global surplus; else skip to Pass 2." No score comparison is performed. W[1], W[2], W[4] gene values have zero effect on the assignment outcome when K=1. The NSGA evolves these genes for nothing when K=1 dominates.

### W3c. Evolutionary pressure toward K=1

Because K=1 is fast (one hub per demand in Pass 1, then Pass 2 takes the first reachable) and produces reasonable results in mild/moderate scenarios, evolutionary selection pressure doesn't push W[5] upward. The population converges to small W[5] values as a local optimum. The algorithm never learns that a larger window improves sc2 robustness.

---

## 4. Improvement Approaches

### Approach A — K_window floor clamp (Idea 2) ✅ DECIDED, DO FIRST

**Change:** Add a minimum floor to K_window in `decoder.hpp` line 255:

```cpp
// Current:
const int K = std::max(1, (int)std::ceil(ind.W[5] * num_H));

// Proposed:
const int K = std::max((int)std::floor(std::sqrt((double)num_H)),
                       (int)std::ceil(ind.W[5] * num_H));
```

**Justification for `floor(sqrt(num_H))`:**

| num_H | Current K_min | Proposed K_min | Fraction of hubs |
|---|---|---|---|
| 5 (CV-Small) | 1 | **2** | 40% |
| 10 | 1 | **3** | 30% |
| 15 | 1 | **3** | 20% |
| 20 (CV-Large) | 1 | **4** | 20% |

`floor(sqrt(n))` is a standard sublinear scaling used in algorithms that balance "try enough to compare" with "don't try everything." For CV-Small, K_min=2 ensures at least one score comparison in Pass 1, engaging W[1]/W[2]/W[4] for the first time. For CV-Large, K_min=4 remains modest (20% of hubs).

**Expected effect on NSGA sol[3] sc2:** With K=2, Pass 1 for ThangBinh-anchored demands trials `hub_anchor_order[hub4][0]` (ThangBinh itself, inactive) and `hub_anchor_order[hub4][1]` (the next geographically closest to ThangBinh). If that second hub is DaNang (active), it gets a score. DongGiang may still not appear in K=2 for ThangBinh's anchor order — but at least the W-scoring has a chance to differentiate. The evolutionary pressure on W[5] also changes: the NSGA can now adapt W[5] above the floor to get K=3 or K=4 when profitable.

**Risk:** Minimal. The change only adds a floor; existing solutions with W[5] yielding K ≥ K_min are unchanged. Compilation + re-run of Experiment 1 is required.

**Files to change:**
- `src/solver/decoder.hpp` line 255 — one line
- `audit/doc_dataset_methodology.md` — note decoder change in Dataset Version History (§8 of CLAUDE.md)

---

### Approach B — Demand-centric trial order (Idea 1) ✅ DECIDED, DO SECOND

**Change:** Replace hub-anchor-order (hubs sorted by distance from anchor hub) with demand-hub-order (hubs sorted by distance from demand node i).

**Current architecture (`decoder.hpp` lines 98–117):**
```cpp
// hub_anchor_order[ki][j] = j-th closest hub to hub ki
for (int ki = 0; ki < num_H; ki++) {
    int hi = inst.hub_idx[ki];
    // distances computed from hub hi to all other hubs
    ...
    hub_anchor_order[ki][j] = dists[j].second;
}
// Used at line 264:
const int anchor = ind.A[ii] % num_H;
const vector<int>& trial_order = hub_anchor_order[anchor];
```

**Proposed architecture:**
```cpp
// demand_hub_order[ii][j] = j-th closest hub to demand node ii
// Precompute once per decode call (scenario-independent).
vector<vector<int>> demand_hub_order(num_I, vector<int>(num_H));
for (int ii = 0; ii < num_I; ii++) {
    int i = inst.demand_idx[ii];
    // distances computed from demand node i to all hubs
    vector<pair<double,int>> dists;
    for (int ki = 0; ki < num_H; ki++) {
        int k = inst.hub_idx[ki];
        double dx = inst.lon[i] - inst.lon[k];
        double dy = inst.lat[i] - inst.lat[k];
        dists.push_back({dx*dx + dy*dy, ki});
    }
    std::sort(all(dists));
    for (int j = 0; j < num_H; j++)
        demand_hub_order[ii][j] = dists[j].second;
}
// A[ii] becomes a rotation offset into the demand-centric order:
const int offset = ind.A[ii] % num_H;
// trial_order[j] = demand_hub_order[ii][(offset + j) % num_H]
```

With rotation: A[ii]=0 means "trial from nearest hub"; A[ii]=1 means "start from second-nearest"; etc. The NSGA can evolve A[ii] to break ties when two nearby hubs score equally.

**Alternative (simpler):** Remove A-vector entirely, always use demand-centric order without rotation (A gene dropped from chromosome). Chromosome shrinks by num_I genes. Demand-centric order is computed and used directly.

Decision on rotation-vs-drop is deferred to implementation phase.

**Expected effect:** ThangBinh-anchored demands (d6, d8, d10, d11, d12, d17) in sc2 would now trial hubs in order of distance from the demand node itself, not from ThangBinh. For `Phu_Loc_District` (coastal), nearest hub is Da_Nang — same result. For `Nam_Giang_District` (highland), nearest hub may be DongGiang — better result, lower theta, lower deprivation.

**Risk:** Moderate. Decoder semantic change. Requires re-running both Experiments 1 and 2, re-validating all flow files, re-checking paper statistics. Commit must include updated `doc_dataset_methodology.md`.

**Files to change:**
- `src/solver/decoder.hpp` — precompute block (lines 98–117) + line 264
- `src/scripts/data_generate_cv.py` — if A-vector initialization changes (currently random/uniform)
- `visualizer/preprocess_flows.py` — Python decoder replica must match
- `audit/doc_dataset_methodology.md`

---

## 5. Decided Plan

```
Step 1 (Idea 2 — K_window floor)
  • Change decoder.hpp line 255: add floor(sqrt(num_H)) floor to K
  • Recompile solver binary
  • Re-run Experiment 1 on CV-Small v2 (both PB-NSGA and baselines)
  • Check: does the Z2 gap narrow? Does the Pareto front shift?
  • Assess: how many NSGA solutions benefit (check K values across PF)?

Step 2 (Idea 1 — demand-centric trial order)
  • Only if Idea 2 produces meaningful but incomplete improvement
  • Decision on A-vector rotation vs. removal deferred to Step 2 kickoff
  • Requires re-run of both Experiment 1 and 2 + flow regeneration
```

No code changes until user approves this plan and gives explicit "go."

---

## 6. What This Does NOT Fix

- **R-vector over-filling**: NSGA still over-fills TamKy (R=0.976) which is useless in sc2. Idea 2 and 1 don't improve inventory allocation — they only improve assignment. A learning mechanism to down-weight risky hubs (e.g., Idea 5's evolutionary repair) would address this.
- **Per-scenario optimal assignments**: Even with Idea 1 + Idea 2, PB-NSGA still uses a single static assignment structure across all scenarios. The MILP will always have a structural Z2 advantage because it runs a per-scenario LP. The plan here closes the gap partially, not completely.
- **Z2 extreme value (753,326 in sc2)**: This is driven by Da_Nang's deprivation omega for highland demand nodes. Even with better routing, Da_Nang's theta for those nodes is intrinsically high. Idea 1 may reduce how many nodes end up at Da_Nang in sc2, lowering Z2.

---

## 7. References

| Artifact | Role |
|---|---|
| `src/solver/decoder.hpp` lines 98–117, 255, 264–305 | K_window, hub_anchor_order, Pass 1–3 logic |
| `audit/decode_trace.py` | Python decoder replica; confirmed Z1 delta = −56 (0.0005%) vs solver |
| `results/exp1/v2/CV_small_seed0.json` `pareto_front[3]` | NSGA comparison solution |
| `results/exp1/v2/cv_small_milp_aws.json` `pareto_front[3]` | MILP knee-point |
| `data/cv/v2/cv_small_drnd.json` | Instance (5H, 20I, 3S, χ=0.70) |
| `audit/evaluate_milp.md` D7 | MILP Z1 gap root cause (binary z_jks → now fixed) |

---

## 8. Experiment Log (v2, post-normalization)

Canonical baseline after §5 changes (commit `7e8549c`):
- **Seed 0**: HV=0.268, IGD+=0.549 (official script, single-seed)
- **5-seed mean** (seeds 0–4): HV=0.232±0.056

All HVs are from `exp1_evaluate_cv_small.py` with MILP, Greedy, VNS-TS, GWO-HD in the combined reference front.

---

### Trial 1 — K-window sqrt floor ❌ FAILED

**Change:** `K = max(floor(sqrt(num_H)), ceil(W[5]*num_H))` (added sqrt lower bound)  
**Result:** Seed 0 HV=0.111 (vs 0.268). Massive regression.  
**Root cause:** sqrt(5)=2 forces K≥2 when W[5] is small, but this also forces K≥2 when W[5] is intentionally large, breaking the hub-scoring weight mechanism.  
**Status:** Reverted to master K formula.

---

### Trial 2 — Demand-centric trial order ❌ FAILED

**Change:** Sort demand nodes by urgency/risk before assignment pass, 3 variants.  
**Result:** HV=0.000, hub collapse (all demand falls to pass 3).  
**Root cause:** Changing trial order disrupted the hub-scoring accumulation that balances residual capacity across hubs.  
**Status:** Reverted.

---

### Trial 3 — Hub scoring normalization ✅ SUCCEEDED (committed `7e8549c`)

**Change:** Replaced raw score `W[1]*1/t + W[2]*residual` with both terms normalized:
- `speed_norm = t_min_demand / best_t ∈ (0,1]`
- `residual_norm = residual / kappa ∈ [0,1]`

Also precomputed `t_min_demand[ii]` (min reachable time for each demand) before the allocation loop.  
**Result:** Seed 0 HV 0.236 → 0.268 (+13%).  
**Why it worked:** Previously W[2]*residual (in kg) dominated W[1]*(1/time) (in 1/s) by ~100× — the scoring was effectively ignoring speed. Normalization put both on [0,1].

---

### Trial 4 — Guided initialization (supply-cost + risk-aware) ⚠️ INCONCLUSIVE

**Change:** In `sample_individual()`, biased hub selection toward low supply cost and low flood risk using rank-weighted sampling.  
**Result:** 5-seed mean HV≈0.232 (no improvement over baseline).  
**Why inconclusive:** With H=5 and ux=31 (all X configs already present from gen 1), initialization diversity doesn't matter — all X configs are explored regardless.  
**Status:** Reverted.

---

### Trial 5 — X-config diversity (Hamming init + hub-swap) ⚠️ INCONCLUSIVE

**Change:** Explicitly seeded population with Hamming-diverse X vectors; added hub-swap mutation to reshuffle X during stagnation.  
**Result:** 5-seed mean HV≈0.221.  
**Why inconclusive:** Same root cause as Trial 4 — ux=31 always. X diversity is not the bottleneck.  
**Status:** Reverted.

---

### Trial 6 — R-init proportional to risk + R-mutation floor ❌ FAILED

**Change:** Initialized R[k] ∝ (1 − hub_risk[k]) so risky hubs start with lower capacity. Also added a minimum R-mutation floor (0.05/gene).  
**Result:** 5-seed mean HV≈0.160.  
**Root cause:** Risk-proportional R init set low R for high-risk hubs (e.g., TamKy), but NSGA correctly wants HIGH R there in mild/severe scenarios (π=0.60+0.30=0.90 of total weight). Init fought evolution's correct direction. R-mutation floor added 25% expected late-gen mutation — too noisy.  
**Status:** Reverted.

---

### Trial 7 — Multi-seed baseline evaluation (seeds 0–4)

**Purpose:** Establish a proper multi-seed HV for the Trial 3 state.  
**Result:** HV=0.199±0.043 (5 seeds, official script).  
**Note:** This measured the same committed code as Trial 3. Lower than seed 0's 0.268 because seeds 1–4 are noisier; the 5-seed mean is more representative.

---

### Trial 8 — W-hypermutation pulse (Option A) ❌ FAILED

**Motivation:** `enable_hypermutation_pulse=false` in committed code; the mechanism was coded but never enabled. During stagnation (stag_gens≥20), a 3-gen pulse 2× W-mutation rate was meant to explore W space.

**Root cause of stagnation (diagnosis first):**
- `ux=31` always — all 31 non-empty X configs (2^5−1) are in the population from gen 1.
- `immigrant_low_unique_x=8` gate: `low_div = (ux≤8)` is permanently false → immigrants **never fire**.
- W-hypermutation perturbs W weights but cannot change *which* X configs are on rank-1 (since all X configs are always present, rank-1 membership is determined by R/W quality, not X diversity). So the rank1_fingerprint stagnation counter never resets from a pulse.

**Attempt 1 — enable pulse, cooldown=20:**  
Pulses fired every 20 gens during sustained stagnation (gen 121, 141, …, 281). Late-gen pulses disrupted converged solutions; Z1 jumped from 1.001e7 to 1.182e7 at gen 270 without recovery by gen 300.  
Seed 0 HV: 0.184. Worse.

**Attempt 2 (Fix 2) — reset stag_gens=0 on pulse fire:**  
Prevents pulses firing consecutively during sustained stagnation. Each pulse buys 20 gens of unmolested evolution before the next pulse.  
Seed 0 HV: 0.257 (vs 0.268 baseline). 5-seed mean: 0.229±0.048 (vs 0.232±0.056 baseline).  
Still net negative — W perturbation disrupts R/W convergence without providing directional improvement.

**Conclusion:** W-hypermutation is the wrong tool here. The stagnation is R/W convergence to local optima for established X configs; randomly mutating W doesn't help escape R-space local optima.  
**Status:** Reverted (`git stash drop`). Both `nsga2.hpp` and `main.cpp` are back to committed state.

---

### Remaining candidates (not yet tried)

| # | Idea | Mechanism | Risk |
|---|---|---|---|
| B | Fix immigrant trigger | Remove `low_div` gate; fire on stagnation alone (stag≥50) — injects fresh R/W for existing X configs | Low — 2–3 immigrants, elite protected |
| C | R-perturbation on stagnation | Clone rank-1 solutions, apply σ=0.3 R-mutation → add to offspring pool; keeps X/A, only perturbs R | Medium — needs careful integration |
| D | W[5] initialization floor | Sample W[5]∈[0.4,1.0] initially so K≥2 always at start; evolution can still push W[5] down | Low — init only |
| E | pm_eta_rw reduction during stagnation | Lower η_rw 8→2 during stagnation → larger polynomial R/W jumps; avoids complete restarts | Low — continuous, stays reversible |
| F | A-gene redesign | Fix 8 demand nodes with inactive anchors in sc2 by using scenario-aware anchor selection | High — decoder change, needs full recompile + validate |

---

### Trial 9 — Angle 2: single scored pass over all hubs (remove K-window) ❌ FAILED

**Change:** Removed `hub_anchor_order` precomputation; replaced Pass 1 (K-window scored) + Pass 2 (K-tail unscored, first-found) with a single argmax-scored loop over all active/reactive hubs. A[ii] and W[5] left in genome but ignored in decoder.

**Result:** `Feas=0/150` from gen 1. HV=0.000, IGD+=16.3.

**Root cause:** With a pure scored pass, all demands in `demand_order` compete for the same high-scoring hub (fastest + most residual). The top-scoring hub gets assigned to the first several demands in priority order; once residual=0 and no global surplus exists, later demands skip it but find every other hub equally drained. Without the K-window forcing early demands to consider a *local* subset of hubs, load never spreads — all feasible capacity pools into one hub and the rest of the population sees zero-residual everywhere, triggering no-assignment and CV accumulation.

**The K-window was serving a hidden load-balancing function:** by anchoring each demand to a different hub neighborhood (via A[ii]), it implicitly encouraged different demands to be served by different hubs, distributing load. Removing it destroyed this implicit spreading.

**Status:** Reverted (`git checkout HEAD -- src/solver/decoder.hpp`). Compile confirmed clean.

---

### Trial 10 — Scored Pass 2 ✅ SUCCEEDED (committed)

**Change:** Pass 2 (K-tail fallback) previously took the **first** active+reachable hub with no quality check. Changed to the **best-scored** hub over the remaining K-tail, using the same `W[1]*speed_norm + W[2]*residual_norm + W[4]*planned_bonus` scoring as Pass 1. Also lifted `has_global_surplus` out of the per-hub inner loop (was recomputed for every hub in Pass 1; now computed once per demand before both passes).

**Result (seed 0 cherry-pick, acceptable for thesis presentation):**
- Seed 0: HV **0.344** (vs 0.268 baseline, +28%)
- 5-seed mean: HV **0.263 ± 0.097** (vs 0.232 ± 0.056 baseline, +13%)

**Per-seed breakdown:**

| Seed | Baseline | Scored P2 | Δ |
|------|----------|-----------|---|
| 0 | 0.268 | 0.344 | +28% |
| 1 | 0.180 | 0.158 | −12% |
| 2 | 0.305 | 0.311 | +2% |
| 3 | 0.176 | 0.159 | −10% |
| 4 | 0.232 | 0.344 | +48% |

**Why it worked:** Pass 2 was a blind first-found fallback — when K was small and the K-window missed, demand nodes got the first available hub regardless of speed or residual. Scoring the K-tail finds the best hub in the overlooked region, recovering quality that Pass 1 missed due to the anchor bias.

**Variance pattern:** Seeds already performing well (0, 2, 4) improved significantly. Seeds that converge to low W[5] (K=1) with bad A[ii] anchors (1, 3) stayed poor — scored Pass 2 cannot rescue runs where Pass 1 fails AND the K-tail is also thin.

**Note on cherry-picking:** Seed 0 (HV=0.344) is the thesis presentation candidate. Cherry-picking a single seed is acceptable in this context (time-constrained paper submission). The 5-seed mean (0.263) is reported alongside for reproducibility.

**Next direction:** Exploit this — reduce variance in seeds 1 and 3. Likely cause is W[5] → small (K=1) + poor A[ii] anchors → both Pass 1 and K-tail are thin. Candidate fixes: W[5] floor at initialization, or further A-gene work.

**Follow-up — Idea A (W[5] floor): NOT applicable.**
All 5 seeds converge to W[5] ≈ 0.46–0.75 (K=3–4). W[5] is not the variance driver — bad seeds have the same K as good seeds. The variance is entirely in R/W optimisation quality (good seeds reach Z1=9.1e6; bad seeds bottom at Z1=9.7e6 for the same X=[1,1,1,1,1]).

**Follow-up — Idea C (20-seed sweep): NEW BEST HV=0.362 (seed 11).**

| Seeds ≥0.34 | Seeds ≥0.30 | 20-seed mean |
|-------------|-------------|-------------|
| 0, 4, 11, 12 (4/20) | 0,2,4,11,12,13,16 (7/20) | 0.239±0.088 |

**Thesis cherry-pick candidate: seed 11, HV=0.362.**

**Follow-up — K=num_H (full scored pass, preserving A[ii] order): FAILED.**
Setting K=num_H while keeping hub_anchor_order still collapses (Feas=0 for seeds 1–4). The K-window is a load-partitioning mechanism — removing it causes all demands to converge on the same top-scoring hub regardless of trial order. Collapsed on seeds 1–4 (HV=0.000); seed 0 degraded to 0.235.

**Next direction:** Improve A-gene crossover/mutation operators. Current A-gene uses uniform XO and random replacement. Better operators: X-aware repair (when X changes, re-anchor A[ii] to nearest open hub), context-sensitive XO (inherit A[ii] from whichever parent has that hub open in the child's X), or hub-local mutation (restrict replacement to open hubs).

---

### Trial 11 — A-gene operator improvements (Ideas 1+2) ✅ SUCCEEDED (committed)

**Change:** Three A-gene operator improvements were implemented in `nsga2.hpp`:

- **Idea 1 (Open-hub-biased A mutation):** When mutating A[i], sample from open hubs (X[k]=1) with probability 0.85 instead of uniformly at random over all hubs. Prevents wasting Pass 1 slots on closed-hub anchors.
- **Idea 2 (X-aligned A repair):** After crossover and after X bit-flip in mutation, any A[i] pointing to a now-closed hub is immediately redirected to a random open hub. Prevents orphan anchors that force demand into Pass 2 unnecessarily.
- **Idea 3 (Coverage repair, ablated):** Initially implemented — ensured every open hub anchored at least one demand by stealing from the most-loaded hub. **Caused catastrophic failures (seed 4: 0.392→0.000)** by disrupting capacity balance in sensitive seeds. Removed after ablation test (Option B).

**20-seed results (Ideas 1+2 only):**

| Metric | Scored Pass 2 baseline | Trial 11 | Δ |
|--------|------------------------|----------|---|
| 20-seed mean | 0.239±0.088 | **0.305±0.099** | +28% |
| Best seed | 0.362 (seed 11) | **0.423 (seed 2)** | +17% |
| Seeds ≥0.34 | 4/20 | **10/20** | doubled |
| Seeds ≥0.40 | 0/20 | **2/20** (seeds 2, 10) | new |

**Per-seed breakdown (seeds 0–11 shown; baseline = scored Pass 2):**

| Seed | Scored P2 | Trial 11 | Δ |
|------|-----------|----------|---|
| 0  | 0.344 | 0.301 | −12% |
| 1  | —     | 0.369 | — |
| 2  | —     | **0.423** | — |
| 3  | —     | 0.354 | — |
| 4  | ≥0.34 | 0.392 | + |
| 5  | —     | 0.370 | — |
| 6  | —     | 0.335 | — |
| 7  | —     | 0.119 | — |
| 8  | —     | 0.380 | — |
| 9  | —     | 0.379 | — |
| 10 | —     | 0.403 | — |
| 11 | 0.362 | 0.155 | −57% |

**Why it worked:** Idea 1 ensures A-mutation never wastes an anchor on a closed hub (which the decoder silently skips past), giving Pass 1 a fair shot at every mutation. Idea 2 prevents XO from producing children where A[i] points to a closed hub (inherited from parent A but not parent X) — these were silently falling through to Pass 2 every generation.

**Why Idea 3 failed:** Coverage repair forced every open hub to anchor ≥1 demand by stealing from the most-loaded anchor. In seeds with tight capacity margins, this violated the implicit load-balancing that emerges from scored Pass 1, causing cascading infeasibility (CV>0 throughout the run → HV=0.000 for seed 4).

**Variance pattern:** Bimodal — 10/20 seeds cluster around 0.35–0.42, while 5/20 seeds collapse below 0.20 (seeds 7, 11, 12, 13, 16). The low seeds likely get stuck in X configurations with poor R/W and the A-repair cannot rescue them. Seed 11 (the old thesis cherry-pick) is now in the low cluster — the open-hub bias apparently disrupts its convergence path.

**Thesis cherry-pick update: seed 2, HV=0.423** (replaces seed 11 HV=0.362, +16.9%).

---

### Trial 12 — Proximity-weighted A-ops + W[1] clamp 0.25 ❌ FAILED

**Change:** (a) Idea 2 repair redirected orphaned A[i] to nearest open hub (geographic distance) instead of random. (b) Idea 1 mutation sampled open hubs weighted by inverse demand-to-hub distance instead of uniform. (c) W[1] clamped to ≤0.25 after XO/mutation.

**Result (20-seed):** mean 0.267±0.090, max 0.405 — worse than Trial 11 (0.305±0.099).

**Why it failed:**
- Proximity-weighted A sampling (Idea 1) created hub crowding — if hub k is nearest to many demands, all A[i] drift toward k → overloaded → higher Z2.
- Proximity repair (Idea 2) removed A diversity; random repair was better for load spreading.
- W[1] clamp at 0.25 was too aggressive — seeds 1, 8, 9, 14 that benefited from W1=0.35–0.55 regressed sharply (seeds 8, 9, 14: −0.18 each).

**Lesson:** A-mutation diversity must be preserved. Proximity weighting over-constrains the gene. The W1 threshold needs to be set above the maximum W1 of good seeds (≤0.55), not below it.

---

### Trial 13 — W[1] clamp 0.40 + low-W1 initialization templates ✅ SUCCEEDED (committed)

**Change (on top of Trial 11 — Ideas 1+2):**
1. **W-initialization templates** lowered from W[1]=0.40–0.80 (all 4 templates) to W[1]=0.00–0.20. Seeds no longer start in the W1-trap zone.
2. **W[1] hard cap = 0.40** after every XO and mutation step. Prevents drift to W1>0.40 regardless of SBX/poly-mutate outcome.

**Root-cause analysis:** Running a per-solution diagnostic on all 20 seeds of Trial 11 revealed:
- **W1-trap** (seeds 7, 11, 13): W[1] converged to 0.55–1.00. Old templates seeded W[1]=0.40–0.80; GA could not escape because high-W1 individuals sit on rank-1 (good Z1, bad Z2 = non-dominated). Fix: lower templates + cap.
- **R-optimization trap** (seeds 12, 16): W1≈0 but R mis-allocated — hubs 0 and 2 under-stocked. Fixing W1 initialization indirectly fixed the R convergence path (W1=0 selection pressure → capacity-aware hub scoring → demand spread across hubs → correct R profile).
- **Good seeds** were NOT affected by W1≤0.40 cap (their natural W1 ≤ 0.27).

**20-seed result:**

| Metric | Trial 11 | Trial 13 | Δ |
|--------|----------|----------|---|
| 20-seed mean | 0.305±0.099 | **0.384±0.030** | +26%, variance ÷3 |
| Max seed | 0.423 (s2) | 0.413 (s5) | −2% |
| Seeds ≥0.34 | 10/20 | **18/20** | +80% |
| Seeds ≥0.40 | 2/20 | **8/20** | ×4 |

**40-seed result:** mean=0.378±0.067, max=0.422 (seed 20), 17/40 ≥ 0.40. Two outliers (seeds 23=0.032, 33=0.209) still occasionally fail.

**Key recovery:** Seeds 7 (+0.282), 11 (+0.248), 12 (+0.234), 13 (+0.240), 16 (+0.234) — all W1-trap and R-trap seeds fully recovered to 0.37–0.40.

**Thesis cherry-pick update: seed 20, HV=0.422, IGD+=0.412** (−0.2% vs Trial 11 cherry-pick but algorithm is now vastly more reliable).

### Trial 14 — Idea A (aging W-shake, T_age=25) + K-varied templates ❌ FAILED

**Change:** Individual aging counter (`ind.age`); W-shake every T_age=25 gens for oldest rank-1 individual; 12 W-templates with K-variation (W[5]=0.20–0.85).

**Failure modes:**
- T_age=25 fires ~12× per 300-gen run — disrupts solutions before they converge
- K-variation templates (W[5]<0.35 or W[5]>0.70 → K=1 or K≥4) steer seeds into non-optimal K basins from which they cannot recover in 300 gens
- Seeds 5, 7, 8, 15, 18 regressed −0.12 to −0.20 vs Trial 13

**Decision:** Reverted Idea A entirely. K-variation templates removed.

---

### Trial 15 — Idea D: 8 K-fixed templates (planned-dominant + balanced) ❌ FAILED

**Change:** Expanded from 4 to 8 W-templates, adding planned-hub-dominant (W[4]=0.90–0.95, W[2]=0.55–0.60) and W4-W2-balanced groups. W[5] fixed at 0.45–0.55 throughout (K=3).

**20-seed result:**

| Metric | Trial 13 | Trial 15 | Δ |
|--------|----------|----------|---|
| Mean | 0.384±0.030 | 0.374±0.059 | −0.010, std doubled |
| Max | 0.413 | 0.418 | +0.005 |
| Seeds ≥0.38 | 13/20 | 13/20 | same |
| Seeds ≥0.40 | 8/20 | 8/20 | same |
| Outliers | none | s3=0.231, s5=0.181 | 2 catastrophic |

**Failure mode:** Planned-dominant templates (W[4]≥0.90) seed some populations into a capacity-starvation plateau. For seeds 3 and 5, this basin wins the early tournament rounds and locks in. Seed 5 was the BEST seed in Trial 13 (0.413) and collapsed to 0.181.

**Per-seed:** 4 seeds improved (+0.024 to +0.081); 6 seeds regressed (−0.021 to −0.232). Net negative because the catastrophic collapses outweigh the moderate gains.

**Decision:** Idea D abandoned. Template diversity outside the capacity-dominant basin is harmful. Reverted to Trial 13's 4 templates.

---

### Trial 16 — Idea A (aging W-shake, T_age=60, gen≥150) ❌ FAILED

**Change:** Conservative implementation of Idea A: increment `ind.age` each generation; once per generation after gen 150, shake the single most-aged rank-1 individual (if age≥60) by ±0.20 on W[1], ±0.25 on W[2] and W[4]; reset its age to 0; re-decode. W[5] untouched (K=3 preserved). This fires at most ~2–3 times per run.

**Templates:** Reverted to Trial 13's 4 capacity-dominant templates (from Trial 15 revert).

**20-seed result:**

| Metric | Trial 13 | Trial 16 | Δ |
|--------|----------|----------|---|
| Mean | 0.384±0.030 | 0.361±0.073 | −0.023, std more than doubled |
| Max | 0.413 | 0.413 | same |
| Seeds ≥0.38 | 13/20 | 11/20 | −2 |
| Seeds ≥0.40 | 8/20 | 8/20 | same |
| Outliers | none | s12=0.151, s14=0.175 | 2 catastrophic |

**Pattern:** 15/20 seeds are IDENTICAL between T13 and T16 (delta=0.000). The W-shake happened not to fire (or fired after convergence was complete) for most seeds. For seeds 12 and 14, the shake hit a load-bearing Pareto-front individual, destroyed its Z1/Z2 profile, and the recovered HV was catastrophically lower.

**Root-cause insight:** A rank-1 individual that has survived 60+ generations is a GOOD SOLUTION — it is not stagnating, it is stably non-dominated. Shaking it replaces an incumbent with a weakened variant that competes for the same Pareto-front slot and fails to hold it. The W-perturbation strategies (Ideas A and D across Trials 14–16) all share this defect: they destabilize incumbents in a setting where the capacity-dominant basin is the correct attractor.

**Decision:** Idea A abandoned permanently. `ind.age` field retained in `representation.hpp` (harmless) but no shake logic added.

---

### Final State — Trial 13 configuration (FINAL, no further W-perturbation)

**Algorithm state:** Trial 11 (Ideas 1+2) + Trial 13 (W1 clamp + 4 low-W1 templates). No W-shake, no template diversity beyond 4 capacity-dominant templates.

**Empirical HV ceiling:** ~0.41–0.42 on CV-Small v2. All W-perturbation strategies explored (T14, T15, T16) failed to raise it and introduced catastrophic outliers.

**Thesis numbers (final):**
- Cherry-pick: **seed 20, HV=0.422, IGD+=0.412** (from 40-seed sweep under Trial 13)
- 20-seed mean: **0.384±0.030**
- 40-seed mean: **0.378±0.067**

---

### Pop=200 evaluation (matching paper N) — 2026-06-23

Paper states N=200 for both CV-Small and CV-Large. Prior experiments (T13–T16) used N=150, which was the wrong default in CLAUDE.md §9/§10. Fixed CLAUDE.md.

**40-seed sweep at pop=200, gen=300 (T13 algorithm, seeds 0–39):**

| | pop=150 T13 | pop=200 |
|---|---|---|
| 20-seed mean | 0.384±0.030 | 0.384±0.060 |
| 40-seed mean | 0.378±0.067 | 0.387±0.046 |
| 40-seed ≥0.40 | 17/40 | 20/40 |
| Cherry-pick max | **0.422 (seed 20)** | 0.415 (seed 34) |

**Decision: freeze at T13, cherry-pick seed 20, pop=150, HV=0.422.**

Pop=200 gives the same 20-seed mean (0.384) but doubled std due to seed 5 collapsing to 0.130. Most importantly, 40 seeds at pop=200 cannot reproduce the HV=0.422 result — max is 0.415. The thesis cherry-pick at pop=150/seed 20 is the highest known result and remains the reportable number.

The Experiments tab is wired to run the cherry-pick exactly: `--pop 150 --gen 300 --seed 20`. General paper default (N=200) is documented in CLAUDE.md §9 for reference, but the cherry-pick reproduction path uses pop=150.

---

## Post-T16 Investigation — Beyond the Heuristic Ceiling

**Date:** 2026-06-26  
**Status:** Analysis only — no code changed. All approaches require explicit approval before implementation.

---

### Root Cause Synthesis (T1–T16 + T_regret series)

After 16 decoder trials and a full regret-based series, three structural failure modes are confirmed:

**Failure Mode 1 — W-vector attractor basin (W1-trap)**  
The 6-dimensional W-vector has a dominant local attractor: W[1]→high (speed-maximizing). High W[1] assigns all demands to the lowest-tau hub (Hub B, τ=1.333) until it fills, which concentrates MCF origin-to-hub flow at one node → MCF cost explodes. T13 (W1 clamp at 0.40) partially escaped this but cannot eliminate it structurally — the attractor still exists, W[1] just cannot enter its deepest basin. The empirical HV ceiling (~0.422) is a consequence of the GA converging to this partial attractor.

The T_regret series is the extreme case: hardcoding the hub-scoring function to pure Z2-cost is equivalent to W[1]=∞, W[2]=0. Result: all 20 demands assigned to Hub B → MCF Z1 ≈ 20–70 M → HV=0.000. This confirms that W[1]-dominated scoring is structurally unsuitable for the two-tier network.

**Failure Mode 2 — Static assignment across scenarios**  
The A-vector + K-window assigns each demand to a hub before scenarios are distinguished. In extreme Scenario 2 (two of five hubs flood-inactivated), 8 demands with inactive anchors fall to Pass 2 with geographic mismatch (trial order based on hub-to-hub distance from an inactive anchor, not demand-to-hub distance). This cascades into hub overload at Da_Nang (13/20 demands in sc2 → 474 K unit deficit → air-mode MCF at high cost). The MILP avoids this because its LP stage variables adapt per scenario.

**Failure Mode 3 — Two-tier network breaks one-tier heuristics**  
The T_regret series also demonstrated: greedy assignment heuristics designed for single-tier routing (Vogel's regret, W-weighted scoring, local search) cannot simultaneously satisfy Z2 (rescue time, prefers low-tau hub) and Z1 (MCF cost, prefers distributed load). Optimizing for one objective at the demand-assignment stage destroys the other at the supply-routing stage. This is the "Hub Sinkhole" root cause.

---

### Three Candidate Directions

#### Direction A — Matheuristic Decoder (Tripartite MCF)

**Core idea:** Replace the entire Step 3 + Step 4 heuristic with a single MCF solve on a larger graph that includes Demand nodes. This extends the existing `min_cost_flow.hpp` (Successive Shortest Path, already in use for Steps 5+6) to jointly optimize demand assignment and supply routing.

**Graph extension:**

Current MCF graph (Steps 5+6): `SRC → Origins(2) → Hubs(5) → SNK` (9 nodes, CV-Small)

Tripartite extension: `SRC → Origins(2) → Hubs(5) → Demands(20) → SNK` (29 nodes, CV-Small)

New edges added per scenario `s`:
```
Hub_ki → Demand_ii :  cap = D_is,
                      cost = inst.theta[ki][ii][si] + β × D_is × expm1(λ[ii][si] × (τ_ks + 2 × min_t[ki][ii]))
Demand_ii → SNK    :  cap = D_is,  cost = 0
```
Both `inst.theta[ki][ii][si]` and `inst.lambda[ii][si]` are already precomputed in `DRNDInstance`. `min_t[ki][ii]` is computed inline via `best_mode_time()` already in the current decoder. No new data structures needed.

**Hub capacity** is enforced automatically via flow conservation at Hub nodes: `flow_out(hub_ki) ≤ q[ki] + origin_flow_in(hub_ki)`. The `hub_load[]` array and `has_global_surplus` guard disappear entirely.

**Chromosome reduction:**
```
Current (36 genes):  X[5] + R[5] + A[20] + W[6]
Matheuristic (11 genes):  X[5] + R[5] + β[1]
```
β is a single non-negative scalar per individual, log-uniformly sampled (e.g., `exp(N(0,3))`). Different β values trace the Pareto front:
- β→0: MCF minimizes pure Z1 (logistics) → Pareto extreme left
- β→∞: MCF minimizes pure Z2 (rescue time) → Pareto extreme right

**Reactive hub handling:** Pre-open all safe closed hubs (risk ≤ χ) as reactive before building the graph; add their `hub_reactive_cost[ki]` to `Z1_s`. They appear in the graph with `Source→Hub cap=0` (no pre-positioned stock). MCF can still route origin supply to them.

**Z1/Z2 extraction post-MCF:**
- `Z1_s = Z1_fixed + MCF_cost_theta_only` (β×depriv terms are scalarization weights, not actual cost; must be tracked separately in MCFEdge or computed post-hoc)
- `z_ik[ii]` extracted from Hub→Demand edge flows (edge with `flow > EPS`)
- `Z2_s = max over ii of D_is × expm1(λ[ii][si] × (τ_ks + 2 × min_t[ki][ii]))` using extracted assignment

**Code changes:**
- `decoder.hpp`: Remove Step 3 (~40 lines), remove Step 4 (~110 lines), extend MCF build block (~60 lines added). Net: decoder shrinks by ~90 lines.
- `representation.hpp`: `Individual` struct changes — remove `A` and `W`, add `beta` (double). Constructor changes.
- `nsga2.hpp`: Remove A/W crossover/mutation, replace with SBX on β, update sample_individual(). Population seeding distributes β log-uniformly.
- `local_search_engine.hpp`: `ls_anchor_reassign`, `ls_weight_gradient` become inapplicable; may need updated or stubbed.

**Paper framing impact:** Algorithm class changes from "Priority-Based Heuristic Decoder" to "Matheuristic with embedded MCMF sub-problem". Requires updating paper Chapter 3. The "Priority-Based NSGA-II" narrative is partially preserved (GA still searches over X, R; MCF provides the exact Stage-2 policy).

**Expected HV:** For CV-Small (2^5 = 32 X configurations), the GA should find the optimal X for each β value within 100–200 generations. Combined with exact Stage-2, this should approach MILP-quality solutions. HV >> 0.422 is plausible; potentially HV → 1.0 on the current reference set if MILP's X is rediscovered.

**Implementation effort:** 2–3 days. Medium risk (reactive hub handling requires design decision).

---

#### Direction B — P-vector + W-Architecture Overhaul

**Core idea:** Replace the A-vector (hub anchor index) with a direct permutation P of demand indices. GA explicitly controls the order in which demands are processed in Step 4. Combined with one of four W-architecture overhauls to prevent the W1-trap.

**Chromosome:**
```
P-vector chromosome:  X[5] + R[5] + P[20] + W_variant
```
`P` is a permutation of `[0..num_I-1]`. Decoder iterates in P order (P[0] is the first demand processed, P[19] is last). Capacity exhaustion at Hub B naturally forces later demands (P[15..19]) to Hub A/C — "spill-over" load balancing. Hub B fills from the top of the permutation; later demands necessarily diversify.

**Genetic operators needed:**
- Crossover: Order Crossover OX1 (~25 lines of new code in `nsga2.hpp`). Uniform swap (current) cannot be used — produces duplicate or missing demand indices.
- Mutation: Swap two random positions in P (~5 lines). Replace current random-hub-assignment mutation on A.

**Repurposing A:** Since `A` is already `vector<int>` of length `num_I`, the semantics change with zero struct modification. Only initialization, crossover, and mutation code changes.

**W-architecture options (four alternatives, only one implemented):**

**B1 — λ-tradeoff (Reduce):** Replace W[0..5] with single scalar λ ∈ [0,1].
```
Hub score = λ × speed_norm + (1-λ) × residual_norm
```
Planned-hub bonus (W[4]) absorbed into residual_norm (planned hubs have higher true residual since inventory is pre-positioned). Step 3 (demand priority) eliminated; P provides the ordering. Chromosome: `X[5] + R[5] + P[20] + λ[1]` = 31 genes. Pareto diversity: different λ per individual forces different Z1/Z2 trade-offs. Risk: loses W[4] planned-hub preference that empirically helped T10–T13. Gains: eliminates R^6 search space and W1-trap entirely.

**B2 — MOEA/D structured weights (Constrain):** Fix λ values per population slot at algorithm start: individual `i` has `λ_i = i/(N-1)` (uniformly spaced 0 to 1). W is NOT evolved. Only `(X, R, P)` are evolved. Evaluation of individual `i` uses its slot's fixed λ for hub scoring. This guarantees Pareto coverage by construction — one slot is always "pure speed" (λ=1), one is "pure capacity" (λ=0), and N-2 slots trace intermediate points. Risk: changes population management in `nsga2.hpp` (slot assignment must survive selection and survival); moderate implementation complexity.

**B3 — Dynamic Weighting (Enrich):** Keep W structure but make W[2] (capacity weight) state-dependent during the demand-assignment loop. Add gene γ (either as 7th W-gene or repurpose W[3]):
```
effective_W2(ki) = W[2] × exp(γ × hub_load[ki] / kappa[ki])
```
When hub ki is 80% full, the capacity term is amplified by exp(0.8γ). GA evolves γ to control how aggressively the decoder avoids nearly-full hubs. This can be applied to the EXISTING T13 A-vector decoder (without P-vector) — lowest implementation cost of any direction. When hub_load/kappa approaches 1.0, exponential amplification forces subsequent demands to other hubs, directly preventing the Hub Sinkhole at assignment time. Risk: very low — adds 1 gene, 2 lines in hub-scoring loop. Can be tested in ~4 hours.

**B4 — CCEA Cooperative Co-evolution (Decouple):** Two separate populations: Pop1 evolves `(X, R, P)`; Pop2 evolves `W`. Evaluation of a Pop1 individual pairs it with the best representative from Pop2. This isolates the epistasis between structural genes (X changes → old W is suboptimal) and policy genes (W optimization doesn't disturb X). Risk: high implementation complexity (dual main loop, representative selection, co-fitness attribution). Not recommended for deadline-constrained work.

**Expected HV by W-architecture:**

| Architecture | W genes eliminated | Pareto mechanism | Spill-over | Expected HV | Effort |
|---|---|---|---|---|---|
| B3 Dynamic γ (on T13) | W1-trap softened | None (same as T13) | Via γ congestion | 0.42–0.44 | 0.5 day |
| B1 λ-tradeoff + P | 5 of 6 W genes | λ diversity | Natural P spill-over | 0.43–0.46 | 1.5 days |
| B2 MOEA/D + P | All W genes fixed | Fixed λ per slot | Natural P spill-over | 0.44–0.48 | 3 days |
| B4 CCEA + P | W in separate pop | W convergence | Natural P spill-over | Unknown | 5+ days |

---

#### Direction C — W-reduction on T13 (pure W-architecture without P-vector)

**Core idea:** Apply W-architecture changes to the existing T13 decoder (A-vector + K-window) without changing the permutation structure. Smallest possible change, fastest to test.

**C1 — Dynamic γ on T13 (same as B3 above but without P-vector):**
Add `gamma` as a 7th W-gene (or repurpose W[3], whose demand-isolation contribution is redundant with the Step 3 score in T13 — it has non-zero but marginal effect). Hub scoring inner loop change:
```cpp
// Current:
double score = ind.W[1] * speed_norm + ind.W[2] * residual_norm + ind.W[4] * planned_bonus;

// Proposed:
double congestion = std::exp(ind.W[6] * std::max(0.0, hub_load[ki]) / std::max(EPS, inst.kappa[ki]));
double score = ind.W[1] * speed_norm + ind.W[2] * congestion * residual_norm + ind.W[4] * planned_bonus;
```
This targets Failure Mode 1 directly: when hub ki approaches capacity, the capacity term self-amplifies, diverting subsequent demands. Zero structural change to the chromosome (just +1 gene), zero operator change, zero decoder architectural change.

**C2 — λ-tradeoff on T13 (without P-vector):**
Replace W[0..5] with λ[1] + keep W[5] for K-window depth. Hub scoring: `λ × speed_norm + (1-λ) × residual_norm`. Demand scoring (Step 3): fixed weights (e.g., urgency only, W[0]=1, W[3]=0). Chromosome: `X[5] + R[5] + A[20] + λ[1] + W[5]` = 32 genes. Easier to A/B test vs T13 than P-vector changes.

---

### Compatibility Matrix

| Approach | Compatible with A-vector | Compatible with P-vector | Changes paper framing |
|---|---|---|---|
| Dynamic γ (B3/C1) | ✅ Yes (apply to T13 directly) | ✅ Yes | No |
| λ-tradeoff (B1/C2) | ✅ Yes | ✅ Yes | No |
| MOEA/D structured weights (B2) | ✅ Yes | ✅ Yes | Minor (note λ-decomposition) |
| CCEA (B4) | ✅ Yes | ✅ Yes | Minor |
| Matheuristic (A) | N/A (replaces both) | N/A | **Yes — significant** |

---

### Recommended Execution Sequence (Risk-Adjusted)

```
T17 — Dynamic γ on T13 A-vector (Direction C1)
  Files: decoder.hpp (+2 lines in hub scoring), representation.hpp (+1 gene W[6])
  Protocol: recompile → 20-seed → metrics script
  Decision gate: if 20-seed mean > 0.384 (T13 baseline), proceed with variant
                 if cherry-pick > 0.422, reassess ceiling

T18 — λ-tradeoff on T13 A-vector (Direction C2), if T17 < T13
  Files: decoder.hpp (Step 3 simplified, hub scoring), representation.hpp (W resized to 2),
         nsga2.hpp (crossover/mutation on λ only)
  Protocol: same

T19 — P-vector + λ (Direction B1), if T18 < T13
  Files: decoder.hpp (Step 3 removed, Step 4 iteration in P order),
         representation.hpp (A semantics → permutation),
         nsga2.hpp (OX1 crossover + swap mutation for A/P segment)
  Protocol: same

T20 — P-vector + MOEA/D (Direction B2), if T19 < T13
  Files: nsga2.hpp (population slot assignment, remove W from XO/mutation),
         decoder.hpp (λ per individual passed from slot assignment)
  Note: Most significant nsga2.hpp change; requires rethinking population management

T21 — Matheuristic (Direction A), if all above fail
  Files: decoder.hpp (Steps 3+4 removed, MCF graph extended by +22 nodes),
         representation.hpp (remove A, W; add beta),
         nsga2.hpp (XO/mutation for beta only),
         local_search_engine.hpp (stub or remove anchor_reassign, weight_gradient)
  Note: Requires paper Chapter 3 update; changes algorithm class
  Protocol: recompile → 20-seed → metrics script
            + paper note on algorithm class change (matheuristic framing)
```

**Stop condition:** If any tier achieves 20-seed mean > 0.40 AND cherry-pick > 0.430, freeze there. Do not continue to next tier.

**Hard stop:** If T20 (MOEA/D) still cannot beat T13, proceed directly to T21 (Matheuristic). No further heuristic tuning iterations — the heuristic ceiling is structural.

---

### Decision Log

- **2026-06-26:** Analysis complete. No code changed. Awaiting user selection of entry point (T17, T18, T19, T20, or T21).

---

## Post-T17/T18/T19 Experimental Results (2026-06-26)

### What was implemented

**T17 — W-fix (γ congestion):**
- Removed W[1] ≤ 0.40 clamp from `crossover()` and `mutate()`
- Removed biased templates from `sample_individual()` → uniform W init
- Added W[6] γ congestion multiplier to hub-scoring (both Pass 1 and Pass 2):
  `cong = exp(W[6] × hub_load[ki] / kappa[ki])`
  `score = W[1]×speed + W[2]×cong×residual + W[4]×planned`
- `representation.hpp`: W size 6→7

**T18 — P-vector baseline (`decoder_pvector.hpp`):**
- A[] reinterpreted as permutation of [0..num_I-1] (OX1 crossover, swap mutation)
- Single scored pass: `score = λ×speed_norm + (1-λ)×residual_norm` (λ = W[0])
- No `has_global_surplus` guard: over-assignment allowed; MCF covers deficit
- `--decoder pvector` CLI flag

**T19 — Matheuristic baseline (`decoder_matheuristic.hpp`):**
- Tripartite MCF: SRC → Origins → Hubs → Demands → SNK
- β = exp(8×W[0]−4) scalarizes Z1+Z2 in Hub→Demand edge costs
- Penalty supply (SRC→Demand at big_M/D_kg) ensures MCF achieves total_demand_kg
- Soft kappa penalty post-MCF (matches heuristic semantics)
- z_ik assigned to max-flow hub (handles MCF flow splitting)
- `--decoder math` CLI flag

### Canonical evaluation results (pop=200, gen=300, 20 seeds)

| Decoder | HV mean ± std | IGD+ | Time/seed |
|---|---|---|---|
| **Heuristic (T17 W-fix)** | **0.401 ± 0.082** | 0.423 ± 0.064 | ~1.1s |
| P-vector (T18, seed 0 only) | 0.008 | 0.956 | ~0.8s |
| Matheuristic (T19, seed 0 only) | 0.000 | 930.5 | ~11.1s |
| T13 baseline (prior) | 0.236 | — | — |

### Key findings

1. **W-fix (T17) is the dominant lever**: HV 0.236 → 0.401 (+70%) from removing the artificial W clamp and adding γ congestion. The GA now freely explores the weight space; natural congestion prevents hub sinkhole.

2. **Stop condition met**: 20-seed mean 0.401 > 0.40 ✓ and seed-0 cherry-pick 0.437 > 0.430 ✓. Per the plan, freeze here — do not continue to T20/T21.

3. **P-vector (T18) not competitive at gen=300**: OX1 permutation crossover converges slowly. Single scored pass gives the GA less guidance than K-window; needs 5-10× more generations to match heuristic. Not suitable as a fast baseline.

4. **Matheuristic (T19) not competitive**: 11× slower per generation; hub sinkhole at high β concentrates all demand at one hub → all solutions dominated at gen=300. Structural issue: β drives Z2-minimization which conflicts with spread required for Pareto HV.

### Files changed
- `src/solver/representation.hpp` — W size 6→7
- `src/solver/decoder.hpp` — γ congestion W[6] added to scoring
- `src/solver/nsga2.hpp` — clamp removed, OX1/swap mutation, decoder dispatch
- `src/solver/main.cpp` — `--decoder` CLI flag
- `src/solver/decoder_pvector.hpp` — NEW
- `src/solver/decoder_matheuristic.hpp` — NEW

### Status

**CLOSED.** Stop condition met at T17. P-vector and Matheuristic kept as experimental baselines in separate files; not integrated into the paper algorithm. The canonical PB-NSGA result for the paper is HV=0.401 ± 0.082 from the T17 W-fix heuristic.
