# Post-Mortem: PB-NSGA Failure on CV-Small v2

**Date:** 2026-06-24  
**Classification:** Honest failure analysis. No proposed fixes. No silver linings dressed as insights.  
**Scope:** All attempted improvements (Trials 1–16) from the committed trial log (`audit/plan_improve_pbnsga.md`) and the implementation record (`audit/audit_algorithm_design.md`).  
**Dataset:** `data/cv/v2/cv_small_drnd.json` — 5 hubs, 20 demands, 2 origins, 3 scenarios.

---

## Section 1 — Exhaustive Log of Failed Attempts

### Pre-trial baseline state

After the v2 normalization fix (Trial 3, commit `7e8549c`), the established baseline was:
- Seed 0 HV = 0.268
- 5-seed mean = 0.232 ± 0.056
- The MILP-AWS achieves HV = 1.000 by definition (it defines the combined reference front)

The gap between PB-NSGA and MILP-AWS was already extreme before any improvement effort began. All subsequent trials were attempts to close this gap. None succeeded beyond incremental local improvements.

---

### Trial 1 — K-window sqrt floor ❌

**Rationale at the time:** W[5] was converging to small values (K=1), making Pass 1 degenerate. A floor of `floor(sqrt(num_H)) = 2` for num_H=5 would force at least one comparison in Pass 1, engaging the W[1]/W[2]/W[4] scoring machinery.

**What was done:** Changed `K = max(1, ceil(W[5]*num_H))` to `K = max(floor(sqrt(num_H)), ceil(W[5]*num_H))`.

**Exact point of failure:** Seed 0 HV collapsed from 0.268 to 0.111. The floor did not just lift K when W[5] was small — it also changed the landscape for individuals with W[5] already in the optimal range. The interaction between the floor and the evolutionary dynamics of W[5] was not considered: once the floor guarantees K≥2, the signal that W[5]≈0.45–0.55 is optimal disappears from the gradient, and the population drifts toward W[5] values that would otherwise be penalised. Additionally, for some seeds, K=2 was actually harmful — it forced comparisons between two anchor-proximate hubs that were both in the same flooded region (Sc2), producing worse assignments than K=1's degenerate-but-fast fallthrough to Pass 2.

---

### Trial 2 — Demand-centric trial order ❌

**Rationale at the time:** `hub_anchor_order[A[ii]]` sorts hubs by proximity to the *anchor hub*, not to the *demand node*. For highland demand nodes whose nearest hub is geographically distinct from the hub nearest to their anchor hub, this produced incorrect trial orders. Sorting by demand-to-hub distance should fix the geographic mismatch.

**What was done:** Three variants of demand-centric sorting were attempted (by demand node proximity, by risk-weighted proximity, by urgency-weighted proximity).

**Exact point of failure:** All variants produced HV = 0.000 from generation 1. The Feas=0 rate was 100% for all seeds. The diagnosis: hub_anchor_order was not merely correcting geographic distances — it was performing implicit load partitioning. By anchoring different demands to different hub neighborhoods (via different A[ii] values), the decoder guaranteed that Pass 1 for demand node X considers a different subset of hubs than Pass 1 for demand node Y. When replaced by demand-centric order (which converges: the hub nearest to demand X is often also near demand Y), high-priority demands all competed for the same top-scoring hub, drained its residual to zero in the first few allocations, and left all subsequent demands with no feasible assignment in Pass 1. Every subsequent demand fell through to Pass 2, Pass 3, or outright infeasibility.

The K-window was acting as an implicit load-spreading constraint, not a quality-of-assignment mechanism. This insight was not understood until Trial 9 confirmed it with full removal.

---

### Trial 3 — Hub scoring normalization ✅ (the only clean success)

**Rationale:** Unit-scale imbalance: W[2]×residual_kg dominated W[1]×(1/time_s) by ~100× because residual capacity is in kilograms (order 10⁵) while inverse-time is in s⁻¹ (order 10⁻⁴).

**Result:** +13% on seed 0. This was a genuine bug fix, not an algorithmic improvement. The scoring was simply broken before this.

**Why it is categorised as success:** It is the only trial that corrected an implementation defect rather than attempting to improve a working algorithm. Noting it here for completeness.

---

### Trial 4 — Guided initialization (supply-cost and risk-aware) ⚠️

**Rationale:** Random initialization wastes early generations exploring poor X configurations. Biasing initial hub selection toward low supply cost and low flood risk should accelerate convergence.

**What was done:** Hub selection at initialization weighted by `exp(-F_k/F_mean) × (1 - risk_k)`. Produced X vectors with lower expected Z1.

**Exact point of failure:** No improvement. Post-hoc diagnosis: the X-niche quota mechanism preserves one representative per unique X configuration. With num_H=5, there are at most 31 non-empty X configurations. Population size N=150 means all 31 are typically populated by generation 1 regardless of initialization bias. The search is not X-limited — it is R/W-limited. Biasing X initialization toward "good hubs" does not help when the bottleneck is finding good R and W values for every X configuration simultaneously.

---

### Trial 5 — X-diversity Hamming initialization + hub-swap mutation ⚠️

**Rationale:** If X-diversity is collapsing early (rare X-configs being killed by crowding), forcing Hamming-diverse initialization and adding hub-swap mutation during stagnation should preserve diversity.

**Exact point of failure:** Same root cause as Trial 4. unique_x ≈ 31 throughout all runs — X-diversity was never the problem. The mechanism was solving a non-existent problem while adding computational cost.

---

### Trial 6 — Risk-proportional R initialization + R mutation floor ❌

**Rationale:** Pre-positioning at high-risk hubs is wasteful — inventory there will be inaccessible in extreme scenarios. Initialise R[k] ∝ (1 − risk[k]) to steer early solutions away from risky pre-stocking.

**What was done:** R[k] = (1 − mean_risk[k]) × Uniform(0.8, 1.0) for open hubs. Added R-mutation minimum of 0.05/gene.

**Exact point of failure:** 5-seed mean collapsed from 0.232 to 0.160 (−31%). The flaw in the rationale: in scenarios Sc0 and Sc1 (combined probability 0.90), ALL five hubs are active. High R on risky hubs (hub1, hub4) is correct for these scenarios — they supply 90% of the expected demand. Evolution correctly drives R[k] upward for all hubs on the dominant scenarios. The biased initialization fought the correct evolutionary direction. The R mutation floor compounded this by adding irreversible mutation noise to a domain where the algorithm was already trying to converge to high R values.

---

### Trial 7 — Multi-seed baseline evaluation (informational)

Not a trial — just a measurement. Established that the 5-seed mean of 0.232 from Trial 3 was not reliably reproducible and that seed variance was already high (±0.056). This should have been an earlier warning signal that the landscape was fundamentally rugged, not that more clever tricks were needed.

---

### Trial 8 — W-hypermutation pulse ❌

**Rationale:** Stagnation (stag_gens≥20) indicates the population is stuck. A 3-generation pulse of 2× W-mutation rate should perturb W-genes enough to escape local optima.

**Attempt 1 (naive):** Pulses fired every 20 gens. Result: seed 0 HV 0.268 → 0.184. Late-generation pulses disrupted converged solutions irreversibly.

**Attempt 2 (Fix 2, cooldown reset):** One pulse per 20 gens of continuous stagnation, then 20 gens of recovery. Result: seed 0 HV 0.257 vs 0.268 baseline. Still net negative.

**Exact point of failure:** The stagnation detector measures rank-1 X-fingerprint stability. But the stagnation observed in CV-Small is NOT X-fingerprint stagnation — it is R/W convergence to a local minimum within a fixed X configuration. The X-fingerprint IS stable because all 31 X-configs are represented throughout and the optimal X-configs (X=[1,1,1,1,1] and nearby) quickly dominate rank-1. W-mutation cannot help escape R-space local optima — W governs hub *selection* within the decoder, not hub *inventory pre-positioning*. Randomly mutating W does not change R[k] values and therefore does not move the solution in Z1–Z2 space in a meaningful way.

---

### Trial 9 — Pure scored pass over all hubs (remove K-window) ❌

**Rationale (misguided):** The K-window was previously shown to degenerate when K=1. The logical conclusion seemed to be: remove the window entirely and score all hubs for every demand.

**What was done:** Replaced K-window Pass 1 + K-tail Pass 2 with a single argmax-scored pass over ALL active/reactive hubs. A[ii] and W[5] retained in genome but ignored in decoder.

**Exact point of failure:** Feas=0/150 from generation 1. HV=0.000, IGD+=16.3 for all seeds.

The K-window's hidden function was confirmed: it is a load partitioning mechanism, not a quality mechanism. With all demands scoring against all hubs simultaneously, the first several high-priority demands drain the top-scoring hub's residual to zero. Subsequent demands find every hub equally drained and fall to Pass 3 (reactive opening, zero inventory) universally. This produces a CV-dominated population from generation 1 — no individual in the initial population of 150 is feasible. NSGA-II cannot recover from this: constrained selection orders infeasible above feasible, so the rank structure degenerates to pure CV-minimisation and the population never evolves toward good Z1/Z2 values.

**Conceptual lesson (belatedly understood):** The K-window is the only mechanism in the decoder that enforces geographic locality of demand-to-hub assignments. Without it, all demands compete on the same global hub ranking, destroying the implicit load spreading that allows feasible solutions to exist.

---

### Trial 10 — Scored Pass 2 ✅

**Rationale:** Pass 2 (K-tail fallback) was a blind first-found greedy pass. Using the same scoring formula as Pass 1 in the K-tail should improve assignment quality for demands that miss Pass 1.

**Result:** Seed 0 +28%, 5-seed mean +13%. This was a genuine improvement.

**Why it is not a win:** The improvement is real but narrow. Seeds that converge to large K values benefit little (Pass 2 is rarely reached). Seeds with small K and poor A[ii] anchors benefit in good seeds — but seeds 1 and 3 REGRESSED (−12%, −10%). The scoring improvement in Pass 2 only helps when the K-tail contains a genuinely better hub than Pass 1 found. When both Pass 1 and the K-tail are thin (small K, anchor in flooded region), scoring the K-tail does not help because there is nothing useful in it.

---

### Trial 11 — A-gene operator improvements (open-hub bias + X-aligned repair) ✅

**Rationale:** A[ii] mutation was drawing uniformly from all hubs including closed ones. This wasted 40–60% of A-mutations (for num_H=5 with 2–3 open hubs) on invalid anchors that immediately fell to Pass 2. The X-aligned repair after crossover prevented A[ii] from pointing to hubs absent in the child's X configuration.

**Result (apparent):** 20-seed mean 0.239 → 0.305 (+28%), max 0.362 → 0.423 (+17%).

**Why this was not a solution:** These improvements are operator-level hygiene, not algorithmic improvements. Fixing the A-mutation distribution reduces wasted evaluations; it does not change the fundamental expressiveness of the decoder. The bimodal result (10/20 seeds cluster at 0.35–0.42, 5/20 seeds collapse below 0.20) already signals that the landscape has two distinct basins: one where the A-operator can usefully spread load across active hubs, and one where the decoder architecture itself is the constraint (extreme scenario with 2.5x overcrowding). Trial 11 improved performance in the first basin. It cannot address the second.

---

### Trial 12 — Proximity-weighted A-ops + W[1] clamp 0.25 ❌

**Rationale:** Make A-mutation and A-repair geography-aware. Random replacement of an orphaned A[ii] with a random open hub ignores that geographically nearby open hubs produce faster routes and lower Z2. Proximity weighting should improve the quality of each A-mutation.

**Result:** 20-seed mean 0.267±0.090 vs 0.305±0.099 baseline. Full regression.

**Exact point of failure:** Proximity-weighted A-sampling is not neutral — it creates a strong bias toward whichever hub is nearest to the most demands. In CV-Small, hub0 (Da_Nang_Airport) is geographically central and nearest to the most demand nodes. Proximity-weighted A-sampling funnelled all A-mutations toward hub0. Hub0 became the anchor for the majority of demands. Hub0's residual drained first. Hub0's overload cascaded to all three scenarios. The effect was equivalent to what Trial 9 found when removing the K-window: without sufficient diversity in A-anchors, load never spreads.

The W[1] clamp at 0.25 was independently wrong: seeds 8, 9, 14 had natural W[1] ≈ 0.35–0.55 and were performing well. Clamping to 0.25 cut off their beneficial W1-moderate behaviour.

---

### Trial 13 — W[1] clamp 0.40 + low-W1 templates ✅

**Rationale:** Per-seed post-convergence inspection revealed a W1-trap: seeds converging to W[1]∈[0.55, 1.0] consistently achieved poor HV. High W[1] makes hub selection pure speed-maximisation, ignoring residual capacity. Since the single fastest hub is almost always hub0 (Da_Nang, coastal, lowest road time to most demand nodes), high W[1] effectively makes the decoder assign everything to hub0 → overload → high Z2. Because high-W1 individuals have good Z1 (fast transport = low cost) and moderate Z2 (acceptable in Sc0/Sc1 where hub0 is not yet overloaded), they remain on rank-1 and are never eliminated by Pareto selection. They crowd out individuals with W1≤0.20 that would produce better balanced solutions.

**Result (apparent):** 20-seed mean 0.305 → 0.384 (+26%), std ÷3, seeds ≥0.40: 2→8.

**Why this is not a solution — and why its success is suspicious:** The W1-clamp works by preventing the algorithm from exploring a region of W-space that always produces poor outcomes. It is not discovering better solutions; it is restricting the search space to exclude a known-bad attractor. The fact that this restriction helps proves that the evolutionary dynamics were previously driving solutions INTO the bad attractor rather than away from it. This is not evidence of algorithmic improvement — it is evidence that the unconstrained algorithm is broken.

More critically: after Trial 13, the population converges to W[1]∈[0.00, 0.20] for all well-performing seeds. This means W[1] is effectively zero — the speed-based hub selection component is turned off. The decoder is operating with W[2] (residual capacity) and W[4] (planned hub bonus) as the only active scoring terms. The algorithm has been simplified to a capacity-first decoder, not a multi-attribute decoder. The carefully designed multi-objective scoring function is doing nothing.

The 40-seed sweep with max HV=0.422 was then cherry-picked from a specific seed (seed 20) and population size (pop=150) that happened to converge well. Pop=200 with 40 seeds cannot reproduce this: max is 0.415. The cherry-picked result is a local coincidence, not a robust algorithm.

---

### Trial 14 — Aging W-shake (T_age=25) + K-varied templates ❌

**Rationale:** The W-convergence to a narrow [0,0.20] band suggests the GA is trapped. Individual aging — shaking the longest-surviving rank-1 individual — might destabilise it enough to explore neighbouring W regions.

**Exact point of failure:** T_age=25 causes ~12 shake events per 300-generation run. Each event disrupts a well-performing incumbent. The GA cannot reconverge in the 25 gens between shakes. The K-varied templates (W[5]<0.35 or W[5]>0.70) produced K=1 and K≥4 populations that consistently failed — confirming K=3 is the only viable window for this instance.

---

### Trial 15 — 8 templates with planned-hub-dominant variants ❌

**Rationale:** Adding templates with W[4]≥0.90 (strong planned-hub preference) might diversify the exploration into regions where reactive hub opening is avoided more aggressively.

**Exact point of failure:** Seed 5 collapsed from 0.413 (Trial 13 best) to 0.181. Two catastrophic seeds produced HVs below 0.23. The planned-hub-dominant basin (W[4]≥0.90) turns out to be a capacity-starvation attractor: strong planned-hub preference steers all demands to planned hubs even when they are at capacity, suppressing the reactive opening that allows some seeds to escape the Sc2 overload. Introducing 4 templates that seed this attractor contaminated the population diversity of seeds that had previously converged well.

---

### Trial 16 — Aging W-shake (T_age=60, post gen 150) ❌

**Rationale:** Trial 14 shook too frequently. A conservative version — firing at most 2–3 times per run, after gen 150, targeting only the most-aged individual — might provide useful perturbation without disrupting convergence.

**Exact point of failure:** Seeds 12 and 14 collapsed (HV: 0.390→0.151 and 0.390→0.175). The root cause is structural: a rank-1 individual surviving 60+ generations is not stagnating — it is a genuinely good solution that is stably non-dominated. Shaking a good solution replaces a real Pareto-front member with a weakened variant. The weakened variant cannot hold the same Pareto-front slot and is killed by subsequent selection. The algorithm suffers a net loss: it destroys an incumbent and produces nothing useful in return.

---

### Pop=200 comparison (post-Trial 13)

**Rationale:** The paper reports N=200. All prior trials used N=150. Reproducing the cherry-pick at N=200 was necessary for honesty.

**Exact point of failure:** At pop=200, 40-seed max is 0.415 (seed 34), not 0.422. Seed 5 collapses to HV=0.130, doubling the standard deviation. The cherry-pick at pop=150/seed 20 is not reproducible at the paper-stated population size. The thesis number is produced by a non-paper configuration of the algorithm.

---

## Section 2 — Failure Modes Analysis

### 2.1 The structural impossibility of Scenario 2

The most important fact about CV-Small v2, which received no serious analysis until the post-mortem:

**In Scenario 2 (extreme, π=0.10):**
- Hub flood risks: [0.590, **0.904**, 0.361, 0.548, **0.815**]
- Active hubs: {hub0, hub2, hub3} (hub1 and hub4 exceed χ=0.70)
- Active hub capacity: 164,561 + 77,256 + 108,724 = **350,541 kg**
- Total demand × γ = **877,938 kg**
- Demand/capacity ratio: **2.50×**
- Road accessibility: **0/100 demand-hub pairs** (complete road failure)

The system is structurally infeasible in Scenario 2 unless reactive hub opening is used aggressively. The decoder's Pass 3 can open reactive hubs (hub1 or hub4 at zero inventory), but these hubs start with zero pre-positioned stock and must be supplied entirely through origin routing or transshipment. Since road access is zero in Sc2, all supply must travel by water or air. Air costs are up to 11× road costs (max air cost 7,092 vs max road cost 625 per person). The expected Z1 penalty from Sc2 supply routing is enormous relative to the Sc0/Sc1 costs.

The two-stage stochastic program (MILP) handles this correctly: Stage-2 decision variables z_{iks} are indexed per scenario, allowing the LP to route optimally for Sc2 independently of the Sc0/Sc1 routing. The MILP can also set R[1]=0.255 (low pre-positioning at TamKy) because it knows that hub1 will be flooded in Sc2 and that a low R[1] reduces Stage-1 holding cost without sacrificing Sc2 performance. The MILP does not pre-position at a hub it knows will flood.

The decoder cannot do this. R is a Stage-1 variable (fixed across all scenarios). A decoder that sets R[1]=1.0 to serve Sc0 and Sc1 (where hub1 is active and useful) is penalized in Sc2 by holding cost for inventory that becomes inaccessible. A decoder that sets R[1]=0.0 to avoid Sc2 waste is penalized in Sc0 and Sc1 by supply shortage at TamKy. This is a genuine two-stage stochastic programming problem, and the decoder's single-vector R cannot express the optimal policy.

**The gap is structural, not algorithmic.** No improvement to W, A, K, or genetic operators can resolve the fundamental impossibility of approximating a per-scenario LP solution with a scenario-independent continuous variable.

### 2.2 Why HV collapses to 0.000

HV=0.000 means the NSGA Pareto front is entirely dominated by the combined reference front (MILP + heuristics). This happens in two distinct failure modes:

**Mode A — Population-wide infeasibility (CV>0 throughout):**
The constrained selection order places all CV>0 individuals below all feasible individuals. If the initial population has no feasible members (HV always requires CV=0 for ranking), the early generations evolve purely to minimise CV. By the time CV reaches 0, the population is converged to a narrow region of X/R/W space that is feasible but far from Pareto-optimal. In 300 generations, the GA cannot recover from this. Trials 2 and 9 hit this failure mode from generation 1.

**Mode B — Feasible but dominated (structural trap):**
All solutions are feasible (CV=0) but their Z1/Z2 values are universally dominated by the combined reference front. This happens when the decoder consistently assigns demand node in Sc2 to Da_Nang (hub0) — producing Z2 ≈ 700K–800K from highland nodes served by a coastal hub via air. The MILP can achieve Z2 ≈ 80K for the same X by routing highland Sc2 demands to hub3 (Dong_Giang). The Z2 gap is so large that no solution from Mode B can escape the dominated region regardless of Z1. The MILP reference point sits at (Z1=10.28M, Z2=80.8K); Mode B decoder solutions sit at (Z1≈11M, Z2≈115K) in the best case — comfortably dominated. These seeds have HV > 0 (so they are not reported as 0) but contribute negligibly to the combined front.

The actual HV=0.000 cases (Trials 2, 9) are Mode A. The HV≈0.10–0.25 cases are Mode B. The cherry-picked HV=0.422 cases are Mode B solutions that happened to achieve Z2 values close enough to MILP to earn a small non-dominated region.

### 2.3 The A-vector's inability to encode scenario-dependent preferences

The A-vector was intended to encode locality preferences — each demand's natural hub neighbourhood. Its fundamental limitation is that it is scenario-independent: A[ii] does not change between Sc0 (all 5 hubs active) and Sc2 (3 hubs active). 

In Sc0 and Sc1, the optimal A[ii] for a coastal demand like Nui_Thanh (d2) is hub1 (TamKy) — it's the nearest active hub and has high capacity. In Sc2, hub1 is flooded. A[ii]=hub1 sends d2 to Pass 2 immediately. Pass 2 searches `hub_anchor_order[hub1]` = {hubs sorted by proximity to hub1} = {hub4 (flooded), hub0, hub3, hub2}. In Sc2, hub4 is also flooded. So Pass 2 finds hub0 as the first active candidate in TamKy's neighborhood. D2 goes to hub0 (Da_Nang, coastal, 90km from Nui_Thanh, expensive by air in Sc2).

The MILP's Sc2 LP would assign d2 to hub3 (Dong_Giang) or hub2 (A_Luoi), whichever has lower Ω_{2,s}. The A-vector cannot encode "in Sc2 go to hub3, in Sc0 go to hub1" because A[ii] is a scalar.

Every trial that worked with A (Trials 11, 12, 13) was implicitly trying to find an A vector that is simultaneously good for all three scenarios. This is a contradiction for the 8 demand nodes whose optimal assignment changes between scenarios — a contradiction that cannot be resolved within the current chromosome representation.

### 2.4 K-window as a hidden feasibility constraint, not a search heuristic

Trials 1, 2, 9 all either weakened or removed the K-window and suffered catastrophic infeasibility. The reason is that K-window serves two functions simultaneously:
1. **(Intended)** Limit hub scoring to a local neighborhood, reducing computation.
2. **(Hidden)** Ensure that different demands compete for different hub subsets, spreading load across hubs.

Function 2 is what enables feasible solutions to exist. Without geographic partitioning of demand-to-hub trials, the demand priority order creates a winner-takes-all dynamic: the highest-priority demand gets the best hub, drains it, and subsequent demands find a degraded hub landscape. The K-window prevents this by ensuring that demand X and demand Y (with different A[ii]) have overlapping but not identical hub trial sets. Load spreading emerges from the diversity of A[ii] values across the population.

This means the K-window and A-vector are architecturally coupled: removing either one breaks the implicit load-balancing contract. This coupling was never explicitly designed — it was discovered by accident when attempts to "improve" one caused the other to fail.

### 2.5 Why the fitness landscape is rugged

The observed HV distribution across 40 seeds (Trial 13) is bimodal: 17/40 seeds produce HV≥0.40, while outliers (seeds 5, 12, 16, 23, 33) produce HV∈[0.03, 0.21]. The gap between modes is not continuous — there is no seed producing HV≈0.30 under Trial 13. This is characteristic of a fitness landscape with multiple distinct basins separated by high barriers.

The basins correspond to:
- **Basin A (high HV, ~17/40 seeds):** Population converges to X=[1,1,1,1,1] with R[0]≈1.0, R[2]≈0.9, R[3]≈1.0 and low R for hubs 1,4 (though never as low as MILP's R[1]=0.255). A-gene spread across all 3 active Sc2 hubs. W[5]≈0.45–0.55 (K=3). W[1]≤0.20. This basin exists only because the W1-clamp prevents escape to the W1-trap.
- **Basin B (low HV, ~3/40 seeds):** Initial random seed happens to give W-templates a poor start, or early XO creates a Hub0-concentrated A distribution that is not repaired quickly enough. The capacity-starvation cascade begins: hub0 overloads → Z2 spikes → these solutions dominate rank-1 (non-dominated by each other, not by Basin A solutions yet) → crowding preserves them → population converges to a near-degenerate Pareto front.

The ruggedness is caused by the interaction between: (1) the discrete X-space (31 configs), (2) the continuous R-space (per-hub fill ratios that change the effective capacity landscape), (3) the integer A-space (anchor assignments that determine load partitioning), and (4) the continuous W-space (decoder weights that govern selection within partitions). These four spaces interact nonlinearly through the decoder, making the joint fitness landscape highly non-convex with many local optima.

---

## Section 3 — Dataset Insights: Why CV-Small v2 Is Hostile

### 3.1 The 2.5× overcrowding discontinuity

CV-Small v2 has the following demand-to-active-capacity ratios:

| Scenario | Probability | Demand (kg) | Active Capacity (kg) | Ratio |
|---|---|---|---|---|
| Sc0 (Mild) | 0.60 | 111,419 | 662,360 (all 5 hubs) | 0.17× |
| Sc1 (Severe) | 0.30 | 478,940 | 662,360 (all 5 hubs) | 0.72× |
| Sc2 (Extreme) | 0.10 | 877,938 | 350,541 (3 hubs) | **2.50×** |

There is no interpolation between 0.72× and 2.50×. The jump from Sc1 to Sc2 is not a gradual increase in difficulty — it is a phase transition. In Sc0 and Sc1, every demand can be served by any hub without capacity concern (ratio < 1). In Sc2, the system is fundamentally infeasible at Stage 1: the three remaining active hubs cannot hold enough pre-positioned inventory to serve all demand nodes, even at full capacity. The system depends entirely on Stage-2 resupply (origin routing + transshipment) to close the 527,397 kg deficit.

A heuristic decoder that pre-positions inventory at Stage 1 and then routes demand to hubs in Stage 2 cannot, by construction, find the optimal policy for this scenario structure. The optimal policy requires knowing *at Stage 1* that Sc2 will have a 2.50× overcrowding, and therefore:
- Set R[k]=0 for hubs 1 and 4 (they will flood and their inventory is wasted)
- Set R[k]=1 for hubs 0, 2, 3 (they remain active)
- Design the hub network to minimize Z2 under the constraint that only 40% of pre-positioned capacity is accessible in the worst scenario

The MILP knows this because it solves the LP for all scenarios simultaneously. The decoder can only approximate it through evolutionary pressure, which requires many seeds to stumble onto the right R profile by chance.

### 3.2 Complete road network failure in Scenario 2

Road accessibility falls from 95% in Sc0 to **0%** in Sc2 (0/100 demand-hub pairs accessible by road). This is the sharpest mode-shifting in the dataset. The entire transport cost structure changes discontinuously:

- In Sc0/Sc1: road is primary (95%, min cost), water secondary (65%, intermediate cost), air tertiary (95%, max cost)
- In Sc2: road is unavailable, water primary (80%, intermediate cost), air mandatory for road-only nodes (95%, expensive)

Air costs reach 7,092 per person vs road costs at most 625. For the 20% of demand nodes unreachable by water (road-only in Sc2), air is mandatory. The expected supply cost per person-kg scales by ~11× relative to road. This causes the catastrophic Sc2 cost spike observed in decode_trace.py: 49.4M origin supply cost in Sc2 vs 3.97M in Sc1.

A decoder that evolves routing preferences (W[1] = speed weight) during Sc0/Sc1 evaluations learns that road speed is the key differentiator. In Sc2, road does not exist. The speed-based scoring learned under Sc0/Sc1 becomes irrelevant — yet W[1] has already converged to its Sc0/Sc1-optimal value and cannot be scenario-conditional.

### 3.3 Hub1's capacity-risk inversion trap

Hub1 (TamKy_Logistics_Hub) is the LARGEST hub in the instance:
- Capacity: 207,168 kg (31% of total system capacity)
- Flood risk: 0.589 (Sc0), 0.562 (Sc1), **0.904 (Sc2)**

It accounts for the single largest share of capacity and is simultaneously the most flood-prone hub in Sc2. This creates a fatal trade-off:
- Setting R[1] high maximises service in Sc0/Sc1 (probability 0.90) but wastes the investment when hub1 floods in Sc2 (probability 0.10).
- Setting R[1] low (like MILP's 0.255) loses Sc0/Sc1 service quality but avoids the Sc2 hold-cost trap.

The MILP resolves this by correctly computing the expected value. The decoder cannot: R[1] is a single scalar evolved under combined fitness pressure from all three scenarios. The evolutionary landscape forces a compromise R[1] that is suboptimal for all three scenarios simultaneously. The optimal policy is discontinuous (R[1]=1 for Sc0/Sc1, R[1]=0 for Sc2) — and a continuous single variable cannot express a discontinuous function.

### 3.4 Hub2's geographic isolation

Hub2 (A_Luoi_Relief_Center) is the safest hub in Sc2 (risk=0.361) and thus the most reliable active hub in extreme floods. It is also the smallest capacity hub (77,256 kg, 12% of system total) and is geographically isolated in the highlands. In Sc2, it becomes the pivot: all highland demand nodes with poor access to hub0 and hub3 should ideally route to hub2. However:

- Hub2 is far from coastal demand nodes (high transport time, high cost)
- Hub2's capacity (77K kg) is tiny relative to the 877K kg demand in Sc2
- Hub2's geographic isolation means `hub_anchor_order[hub2]` lists primarily hub3 and hub0 as proximate hubs — both coastal — rather than the highland demand nodes that most need it

The decoder cannot identify hub2 as a priority target for highland demand nodes in Sc2 because hub selection is governed by proximity-to-anchor-hub (hub_anchor_order), not proximity-to-demand-node. Hub2 appears late in most anchor orders because most anchors are coastal hubs far from the highland interior.

### 3.5 The 90%/10% probability weighting creates misaligned evolutionary pressure

The fitness functions Z1 and Z2 are weighted sums over scenarios:

```
Z1 = 0.60 × Z1_0 + 0.30 × Z1_1 + 0.10 × Z1_2
Z2 = 0.60 × Z2_0 + 0.30 × Z2_1 + 0.10 × Z2_2
```

Sc2 contributes only 10% weight to both objectives. In Sc0 and Sc1 (90% combined weight), the optimal policy is straightforward: open all 5 hubs, fill them all, assign each demand to its nearest active hub. The evolutionary signal in 90% of the weight points toward "full pre-positioning, all hubs open, nearest-hub assignment."

But the correct policy for Sc2 (the scenario that drives most of the Z2 spread between MILP and NSGA) is the opposite: selective pre-positioning (low R for flood-prone hubs), hub3-biased assignment (highland routing), and heavy reliance on MCF-optimised origin routing. The evolutionary signal from Sc2's 10% weight is too weak to counter the 90% signal from Sc0/Sc1.

In a formal sense: the gradient of the expected fitness function with respect to R[1] is dominated by Sc0/Sc1 (∂Z1/∂R[1] large, positive for high R[1]) and cannot steer the decoder toward the Sc2-optimal R[1]=0.255 that MILP finds through direct LP optimisation.

---

## Section 4 — The Local Basin Trap: Deconstructing the W-Vector Bias

### 4.1 What was actually done

The W-vector biasing strategy (Trials 12–16) followed this logic:
1. Observe that certain W-gene values produce poor HV when they occur naturally (W[1]>0.40 → W1-trap).
2. Prevent those values by hard clamping W[1]≤0.40 and seeding templates with W[1]≤0.20.
3. Observe that W[5] near 0.45–0.55 (K=3) produces better outcomes than W[5] extremes.
4. Seed all templates with W[5]∈[0.40, 0.55] and penalise or remove templates that deviate (Trials 14, 15 both failed when templates had W[5] outside this range).
5. Final state: all templates enforce W[1]≤0.20, W[5]∈[0.40, 0.55]. The W-vector effectively has fixed effective ranges rather than being evolved. The "evolved" W-vector is constrained to a 4D hyperrectangle within the 6D W-space.

### 4.2 Why this is a local basin, not a global optimum

The W-constraint strategy finds a set of W values for which the decoder produces consistently feasible and moderately good solutions on CV-Small v2. The HV ceiling at 0.41–0.42 is not the algorithm finding the best it can do — it is the algorithm finding the best it can do within the manually engineered basin that the W constraints define.

To see why this is a local basin and not a global optimum, observe what the decoder with these W values is actually computing for each demand in Sc2:

```
hub_score = W[1] × speed_norm + W[2] × residual_norm + W[4] × planned_bonus
         ≈ 0.10 × speed_norm + 0.85 × residual_norm + 0.65 × planned_bonus
```

(using representative values from the 4 templates: W[1]≈0.10, W[2]≈0.87, W[4]≈0.66)

This is a capacity-first decoder: it assigns each demand to the hub with the most remaining inventory in its anchor neighbourhood (K=3 window). In Sc2, where hub1 and hub4 are flooded, the 8 demand nodes with anchors at hub1/hub4 fall to Pass 2, which scores the K-tail of the hub_anchor_order. The K-tail for hub1's neighborhood lists hub0 and hub3 (in proximity order). Pass 2 computes residual_norm for hub0 and hub3 and picks the one with more remaining capacity.

This is a capacity-greedy heuristic. It does not consider:
- The geographic distance from the demand node to the hub (only to the anchor hub)
- The transport mode cost in Sc2 (road is unavailable; air costs are prohibitive for distant nodes)
- The per-scenario optimal R-profile that the MILP can solve exactly

The MILP's Z2=80,772 is achieved not by a better capacity-greedy heuristic but by solving the entire two-stage problem jointly. The LP for Sc2 considers the transport cost matrix exactly: it assigns each demand node to the hub that minimises the combined deprivation cost `D_{is} × (exp(λ_i × (τ_{ks} + 2τ_{kim})) − 1)`. The decoder cannot do this because it encodes a static priority ranking (W-based scoring) rather than an instance-specific optimal assignment.

### 4.3 The mathematical gap that W-tuning cannot close

Let the MILP's Sc2 Z2 value be Z2*_2 = 80,772 (achieved by LP-optimal assignment of all 20 demands across 3 active hubs + reactive opening + MCF-optimal supply routing).

The decoder's best Sc2 Z2 value (from the cherry-pick, seed 20) is approximately:
```
Z2_2 ≈ Z2_total - 0.6×Z2_0 - 0.3×Z2_1 ≈ [estimated ~600K from trace data]
```

The Z2 gap in Sc2 alone is enormous. Even if W-tuning perfectly solves the assignment problem (it does not), it cannot escape the constraint that:
1. R is scenario-independent — the same pre-positioning applies to all scenarios
2. Hub assignment is governed by hub_anchor_order — which is hub-centric, not demand-centric
3. The MCF supply routing is solved optimally (Step 5+6) — but only AFTER demand-to-hub assignment is fixed by the heuristic decoder

The W-vector controls only Step 3 (demand priority) and Step 4 (hub selection scoring). Steps 1+2 (Stage-1 pre-positioning and scenario hub activation) are not W-influenced. Steps 5+6 (supply routing) are LP-optimal given the Step 4 assignment. The gap between MILP and decoder comes from Steps 1–4, and W-tuning addresses only the scoring within Step 4. The contribution of Step 4 scoring to the total gap is bounded.

### 4.4 The cherry-pick problem

HV=0.422 was achieved by seed 20 with pop=150. Seed 20's performance is not reproducible with the paper-default pop=200. The 40-seed distribution at pop=150 shows 2 catastrophic outliers (seeds 23: HV=0.032, seed 33: HV=0.209) even under Trial 13. At pop=200, seed 5 collapses to 0.130.

What this means: the "best known" HV=0.422 result is a statistical accident within the engineered local basin. The decoder's landscape under Trial 13 constraints still has multiple basins. The Basin B attractor (capacity-starvation or hub0-overload) occasionally captures 2–3 seeds per 40-seed run. The cherry-picked seed 20 happened to miss Basin B. A different starting seed (or a different population size) cannot guarantee Basin B avoidance.

A robust algorithm would show a distribution concentrated near the maximum HV with small standard deviation. Trial 13's 40-seed distribution (0.378±0.067) shows the algorithm is not robust — 5% of seeds still produce HVs near zero, and the standard deviation represents ~18% of the mean. By comparison, MILP-AWS produces HV=1.000 with zero variance (it is exact).

### 4.5 Why the W-biasing strategy is unacceptable as a general methodology

The local basin strategy works only because CV-Small v2 has a specific property: there exists a narrow W-region (W[1]≤0.20, W[5]∈[0.40, 0.55]) that avoids the two worst attractors (W1-trap and K-collapse). This property was discovered by running 40+ seeds, identifying which seeds failed, diagnosing their W-gene convergence, and then engineering constraints to prevent access to those W-regions.

This methodology:
1. **Is not generalisable.** For CV-Large v2 with 20 hubs and different scenario structure, the optimal W-region may be entirely different. The W-constraints learned from CV-Small are not transferable.
2. **Confounds algorithm design with data snooping.** The W-constraints were derived by examining the behaviour of the algorithm on the test instance and engineering constraints to produce better results on that instance. This is not algorithm design — it is parameter fitting to a specific instance.
3. **Does not close the structural gap.** Even with perfect W-constraints, the decoder cannot approximate a per-scenario LP. The gap between HV=0.422 and HV=1.000 exists for structural reasons (§2.1), not because the W-values are suboptimal.
4. **Produces a fragile result.** The cherry-pick seed is sensitive to population size, seed number, and random initialisation. A methodology that requires cherry-picking across 40 seeds to find one result near the HV ceiling is not a reliable algorithm — it is a lottery.

### 4.6 Summary of what was lost

The following algorithmic properties were progressively stripped away in the attempt to improve HV:

| Property | Original intent | After Trial 13 |
|---|---|---|
| W[1] (speed) | Hub selection weight: balance speed vs capacity | Effectively zero (W[1]≤0.20, cap=0.40) |
| W[5] (K-window) | Evolved parameter for optimal search depth | Fixed to [0.40, 0.55] by template constraint |
| W[4] (planned bonus) | Reward planned hubs over reactive | Active but secondary to W[2] (capacity) |
| Template diversity | Explore diverse W-landscapes | Restricted to capacity-dominant basin |
| W-mutation | Explore W-space during evolution | Constrained to post-cap values |
| General algorithm | Multi-attribute decoder with evolutionary W-calibration | Capacity-first greedy with constrained W |

The final algorithm is not a general priority-based evolutionary decoder. It is a capacity-greedy heuristic with evolutionary parameter optimisation restricted to a manually engineered sub-region of the parameter space, calibrated by direct inspection of a single test instance.

---

## Conclusions

1. **The performance gap is structural, not algorithmic.** PB-NSGA approximates a two-stage stochastic program with a single-stage heuristic decoder. No genetic operator improvement, W-vector engineering, or population diversity mechanism can close the fundamental gap between a heuristic approximation and a LP-exact Stage-2 recourse computation.

2. **CV-Small v2 is a maximally adversarial test case for this decoder.** The combination of 2.5× overcrowding in Sc2, complete road failure in Sc2, hub1's capacity-risk inversion, and 10% weight on Sc2 creates an instance where the correct policy (low R[1], hub3/hub2-biased Sc2 routing) is directly opposed to the dominant evolutionary signal (high R everywhere, hub0/hub1 central, Sc0/Sc1 cost minimisation).

3. **The cherry-pick result (HV=0.422) is scientifically weak.** It is achieved by a non-paper population size (150 vs 200), a specific seed (20/40), within a manually constrained W-space, on a single-seed evaluation. It does not represent algorithm performance — it represents the maximum of a distribution over a locally engineered basin.

4. **The W-biasing strategy is circular.** It identifies attractor basins by inspecting algorithm behaviour on the target instance, then constrains the algorithm to avoid those basins. This is instance-specific parameter fitting masquerading as algorithm design.

5. **All successful trials fixed bugs or removed known-bad behaviours; none improved the core algorithm.** Trial 3 fixed a unit-scale bug. Trial 10 fixed a greedy-vs-scored bug in Pass 2. Trial 11 fixed a closed-hub waste bug in A-mutation. Trial 13 fixed a W1-trap attractor. The "improvements" are a sequence of fixes toward a correct baseline, not improvements above a correct baseline. The correct baseline remains far below the MILP.

---

*Source data: `audit/plan_improve_pbnsga.md` (Trial log, Trials 1–16 + pop=200 evaluation), `audit/audit_algorithm_design.md` (implementation reference), `data/cv/v2/cv_small_drnd.json` (instance structure), `results/exp1/v2/cv_small_metrics.csv` (canonical HV numbers), `audit/plan_improve_pbnsga.md §2` (decode_trace Z1 verification).*

---

## Section 5 — Regret-Based Decoder Series (T_regret, 2026-06-26)

**Scope:** All variants of the regret-based demand-allocation decoder attempted on top of the T13 cherry-pick baseline (HV=0.422). Branch: `feat/planar-dataset`. The series replaces T13's A-vector + K-window loop with a Vogel's-approximation regret loop and adds post-assignment local search.

**Baseline entering this series:** T13 cherry-pick, HV=0.422, Z1=9.45–13.8M, Z2=9.43e4–1.17e5. Reference nadir: Z1=13.5M, Z2=1.17e5.

---

### T_r1 — W-weighted regret decoder (Gemini rewrite + bug fixes) ❌

**Rationale:** Replace A-vector + K-window greedy with a Vogel's-approximation loop: at each step, compute `regret[ii] = score(best hub) − score(2nd-best hub)` using a W-weighted score (`W[1]×speed_norm + W[2]×residual_norm + W[4]×planned_bonus`). Serve the demand with the highest regret first. This preserves W-dependence (NSGA-II can evolve W to diversify assignments) while changing the ordering principle from A-vector preference to regret urgency.

**Bugs introduced by Gemini's rewrite and corrected:**
1. *Reactive hub starvation*: `residual <= 0.0 && !has_global_surplus` check was missing `!y[ki]` guard. Reactive hubs (inventory=0 by design; MCF brings supply in Step 5) were permanently skipped → infinite fallback → BigM penalty → CV>0 → HV=0. Fix: `if (!y[ki] && residual <= 0.0 && !has_global_surplus) continue;`
2. *W-independence*: Gemini replaced W-weighted hub scoring with raw C_time → identical solutions across all 5 seeds → zero evolutionary diversity from W.
3. *Step 3 gutted*: Demand priority scoring (W[0]×urgency + W[3]×isolation) was removed, eliminating the chromosome's influence over demand ordering.

**Result after fixes:** HV=0.000. 5-seed Z1=13.4M–59.1M, all dominated by MILP (Z1=7.8–13.5M). Z2=6.8e4–2.7e5. All solutions above the reference nadir Z1=13.5M.

**Exact point of failure:** Z1 minimum was 13.4M (above the nadir ceiling of 13.5M by 6%). Even the best W-weighted regret solution barely misses the reference front. The regret loop does not balance hub loads well — without the K-window's geographic partitioning, high-priority demands concentrate at one hub, triggering reactive openings and higher MCF costs.

---

### T_r2 — Z2-cost Vogel regret decoder ❌

**Rationale:** Replace W-weighted hub score with the actual Z2 deprivation contribution as the hub cost:

```
z2_cost[ii][ki] = D_i × expm1(λ_i × (τ_k + 2 × min_travel_time[ii][ki]))
regret[ii]      = z2_cost[ii][2nd-best] − z2_cost[ii][best]
```

This directly targets Z2 (the exact deprivation term from the solver objective) rather than a surrogate W-weighted score. Z2 quality confirmed excellent: 5-seed Z2 range = 6.79e4–1.24e5, identical to MILP's range. The Vogel ordering correctly prioritises demands where hub choice matters most.

**Result:** HV=0.000. 5-seed Z1 minimum = 22M, all solutions dominated. The Z2 component is fully solved; Z1 is 2–5× above the nadir.

**Exact point of failure:** Post-analysis (decomposition of Z1 into components) revealed:
- Z1_fixed (hub setup + holding) = 490K — negligible.
- Per-demand theta (Daganzo last-mile) ≤ 1.16M total — small.
- MCF supply-chain routing = **~20M** — dominant.

The Z2-cost regret decoder concentrates 8 of 20 demands at the hub with lowest process time (hub B, ki=4). Hub B receives ~40% of total demand volume (roughly 45,000 kg). The MCF must route this supply from distant origins at high per-unit cost (up to 7,300 per kg-km). The expected MCF cost for this concentration is ~20M. By contrast, T13's A-vector + K-window spreads demand geographically, keeping each hub's MCF flow manageable and achieving Z1=9–13M.

The root cause is architectural: Z2 minimisation (choose the hub with fastest rescue time) and supply-chain cost minimisation (spread demand to minimise MCF flows) are in direct conflict for this instance. The regret decoder resolves this conflict by optimising Z2 only, producing excellent Z2 at catastrophic Z1 cost.

---

### T_r3 — Z2-preserving 1-opt local search (Step 4.5) ❌

**Rationale:** After the regret loop, attempt to reduce Z1 by relocating individual demands to different already-open hubs. Accept a move if: (a) the new hub has remaining capacity, (b) the new deprivation ≤ current Z2_s ceiling, (c) delta_theta < 0. The intuition: Z2 is already optimal; we can improve Z1 by swapping demands to cheaper-theta hubs within the Z2 budget.

**Result:** Zero moves accepted across all 5 seeds. Z1 unchanged.

**Exact point of failure:** Two simultaneous blockers:
1. *Capacity exhaustion*: With only 2 planned hubs and all 20 demands assigned, both hubs are at full capacity. No relocation is possible without first freeing space at the destination hub.
2. *Z2-theta co-optimality*: For every demand, the hub that minimises Z2 (minimum process time + travel time) is ALSO the hub with minimum theta. The Z2-cost regret decoder has already placed each demand at its joint (Z2, theta)-optimal hub. No swap can reduce theta without moving a demand away from its Z2-minimum hub, violating the Z2-preservation constraint.

Confirmed by numerical check: Pearson r(theta, C_time) = 0.58 globally, but for all 20 demands in this instance, the hub assignment that minimises Z2 coincides exactly with the assignment that minimises theta. The 1-opt LS correctly finds nothing — it is not a bug.

---

### T_r4 — Z2-preserving 2-opt swap-LS (Step 4.6) ❌

**Rationale:** 1-opt fails because hubs are at capacity. A 2-opt interchange swaps the hub assignments of two demands (ii ↔ jj) simultaneously, conserving capacity at both hubs exactly. This avoids the capacity blocker. Accept a swap if: (a) demands are at different hubs, (b) both can reach the other's hub (mode feasibility), (c) both new deprivations ≤ Z2_s, (d) combined delta_theta < 0.

**Static analysis (pre-implementation check):** Assuming demand assignments under the oracle assignment (ii at hub A, jj at hub B), found 120 pairs with delta_theta < 0 AND Z2_ok=True, with the best swap saving delta_theta = −43,000 per scenario.

**Result:** Zero swaps accepted. Z1 unchanged.

**Exact point of failure:** The static analysis used incorrect hub assignments. When the correct z_ik assignments are used (from the Z2-cost regret decoder), every demand is already at its minimum-theta hub. For any pair (ii at ki_A, jj at ki_B):
- Moving ii to ki_B increases theta for ii (it was at its best-theta hub)
- Moving jj to ki_A increases theta for jj (it was at its best-theta hub)
- Combined delta_theta > 0 for all pairs → no improving swap exists

The swap-LS also cannot fix the MCF cost concentration (which is the actual Z1 source), because:
1. MCF costs are computed in Step 5, after demand-to-hub assignment is frozen.
2. The swap-LS modifies only `theta[ki][ii][si]` in Z1_s; it has no mechanism to rebalance the MCF supply flows.
3. Fixing MCF concentration would require moving demands FROM hub B (reducing its supply flow) TO hub A — but this increases Z2 for those demands (hub B has lower process time), violating the Z2 constraint.

The Z2-preservation constraint makes MCF rebalancing structurally impossible: the demands causing high MCF cost are at hub B precisely because hub B is the Z2-optimal hub, and no Z2-preserving move can reduce hub B's load.

---

### Section 5 — Root Cause Summary

**The regret-decoder series fails for a single structural reason: Z2 optimisation and MCF supply-chain cost minimisation are in direct conflict for this instance.**

The Z2-cost regret decoder resolves every demand's hub assignment to jointly minimise both Z2 (rescue time) and theta (last-mile supply cost), since both correlate with the same travel time metric. This is "correct" locally — but globally, it concentrates ~40% of total demand volume at the hub with the fastest rescue time (lowest process time), forcing the MCF to route large supply flows from distant origins at high cost (up to 7,300/kg-km × ~45,000 kg × α = ~20M MCF contribution per scenario).

T13 avoids this concentration through the A-vector + K-window mechanism, which imposes geographic diversity of assignments — some demands go to suboptimal Z2 hubs because their A-vector anchor is elsewhere. This suboptimality in Z2 creates slack for the MCF to distribute supply flows efficiently, achieving Z1=9–13M at the cost of HV=0.422 (vs. MILP's HV=1.000).

No post-assignment local search can resolve this, because:
- The LS operates on `theta` (small) while the Z1 excess is in MCF costs (large).
- Reducing MCF concentration requires moving demands away from their Z2-optimal hubs.
- The Z2-preservation constraint blocks exactly those moves.

**The regret-decoder concept is sound for Z2 quality but requires a load-balancing term in the hub cost to avoid MCF concentration. Pure Z2 Vogel regret cannot work here.**

---

*T_regret source: `src/solver/decoder.hpp` (Steps 4–4.6), branch `feat/planar-dataset`, 2026-06-26. Numerical data from 5-seed runs at pop=150, gen=300.*
