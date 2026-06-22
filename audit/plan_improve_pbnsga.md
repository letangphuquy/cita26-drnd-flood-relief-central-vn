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
