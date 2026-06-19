# Algorithm Audit — Paper §2–§3 vs `decoder.hpp`

> Source of truth: `paper/main.tex` (§2 Math Model, §3 Proposed Algorithm) and
> `src/solver/decoder.hpp` (v3, 695 lines).  
> All line references are to `decoder.hpp` unless otherwise noted.

---

## 1. Chromosome Encoding — `C = (X, R, A, W)`

### Paper §3.1

| Segment | Type | Semantics |
|---|---|---|
| **X** | `{0,1}^|H|` | Planned hub establishment |
| **R** | `[0,1]^|H|` | Inventory fill fraction → `q_k = R_k · κ_k` |
| **A** | `{0…|H|-1}^|I|` | **Preferred anchor hub LOCAL index** for each demand `i` |
| **W** | `[0,1]^6` | Six heuristic weights governing the decoder |

### `decoder.hpp` details

```cpp
// Line 264
const int anchor = ind.A[ii] % num_H;   // safe modulo if A out of range
const vector<int> &trial_order = hub_anchor_order[anchor];
```

**A[ii] is unambiguously a hub local index (0…num_H−1), never a transport mode.**
The `% num_H` guard handles any out-of-range chromosome values.

**W weight semantics** (lines 15–21, confirmed by usage):

| Index | Paper symbol | Role in decoder | Usage site |
|---|---|---|---|
| W[0] | w₀ | Demand urgency weight (λ·D) | Step 3 demand score |
| W[1] | w₁ | Hub speed weight (1/τ) | Hub score (Pass 1) AND demand dist penalty |
| W[2] | w₂ | Residual capacity weight | Hub score (Pass 1) |
| W[3] | w₃ | Demand isolation weight (1/n_reach) | Step 3 demand score |
| W[4] | w₄ | Planned hub preference bonus | Hub score (Pass 1) |
| W[5] | w₅ | Pass-1 window depth (fraction of \|H\|) | K = max(1, ⌈W[5]·\|H\|⌉) |

**Knee-point solution (sol[2]) W values:**
```
W = [0.184, 0.000, 0.023, 0.000, 0.418, 0.000]
```
→ K = max(1, ⌈0.0 × 20⌉) = **1** — Pass 1 checks ONLY the anchor hub itself.  
→ W[4]=0.418 dominates hub scoring — planned hubs are strongly preferred.  
→ W[1]=0 — travel time plays NO role in hub scoring for this solution.  
→ W[3]=0 — isolation plays no role in demand sorting for this solution.

---

## 2. Step 1 — Stage-1 Decode & Fixed Costs

### Paper
> "Planned hubs with X_k = 1 and r_ks ≤ χ are activated with pre-positioned
> inventory q_k = R_k · κ_k. If none qualify, the safest hub is forced active."

### `decoder.hpp` (lines 82–197)

```cpp
// q_k = R_k * kappa_k  (only for established hubs)
for (int ki = 0; ki < num_H; ki++) {
    x[ki] = ind.X[ki];
    if (x[ki]) q[ki] = ind.R[ki] * inst.kappa[ki];
}

// Fixed costs: F_hub + holding cost (stage-1, scenario-independent)
Z1_fixed += inst.F_hub[ki] + inst.c_hold[ki] * q[ki];

// Step 2: activate planned hubs passing risk filter
for (int ki = 0; ki < num_H; ki++) {
    int k = inst.hub_idx[ki];
    if (x[ki] && sc.risk[k] <= inst.chi)
        active[ki] = true, inventory[ki] = q[ki];
}

// Force-activate safest hub if all fail
if (!any) {
    best_ki = argmin(sc.risk[k] for k in all hubs);
    active[best_ki] = true;
    inventory[best_ki] = q[best_ki];  // may be 0 if X[best_ki]=0
}
```

**Key details not explicit in paper:**
- `Z1_fixed` is added to `Z1_s` for EVERY scenario (it's amortized inside the scenario loop, not divided by |S|). The final `Z1 += pi_s * Z1_s` makes the expected value correct only because `sum(pi_s) = 1`.
- Force-activate uses `sc.risk[k] < best_r` (strictly less), choosing globally safest hub even if X[k]=0. Inventory at a force-activated non-established hub = 0 (R[ki] * 0 capacity if kappa[ki]=0, or just q[ki]=0 since X[ki]=0).
- `v_ks` (planned-hub availability) in the paper equals `x[ki] && sc.risk[k] <= chi` — i.e., the conjunction of establishment AND risk safety.

---

## 3. Hub Trial Order Pre-Computation

### Paper
> "starting from its anchor π_{A_i}"

### `decoder.hpp` (lines 98–117) — **critical, not fully described in paper**

```cpp
// hub_anchor_order[ki][j] = local index of j-th closest hub to hub ki
// Sorted by squared Euclidean distance (lon, lat space)
for (int ki = 0; ki < num_H; ki++) {
    int hi = inst.hub_idx[ki];   // global node index of hub ki
    for (int kj = 0; kj < num_H; kj++) {
        int hj = inst.hub_idx[kj];
        double dx = inst.lon[hi] - inst.lon[hj];
        double dy = inst.lat[hi] - inst.lat[hj];
        dists.push_back({dx*dx + dy*dy, kj});
    }
    sort(dists);
    hub_anchor_order[ki][j] = dists[j].second;
}
```

**Semantics:** For demand node ii with anchor A[ii]:
- `anchor = A[ii] % num_H`
- `trial_order = hub_anchor_order[anchor]`
- `trial_order[0] = anchor` (distance 0 to itself — always the FIRST hub tried)
- `trial_order[1..] = other hubs in ascending Euclidean distance from anchor hub`

This means: demands assigned to anchor k0 try hubs in order of geographic proximity
to k0, starting with k0 itself. The anchor hub is always the first candidate.

**Distance metric**: squared lon/lat Euclidean distance (no haversine, no cos-lat
correction). This is a sorting proxy only — not used for cost/time computation.

---

## 4. Step 3 — Demand Priority Scoring

### Paper §3 Step 2
> "Score demands by urgency, isolation, proximity; sort descending"

### `decoder.hpp` (lines 200–246)

```cpp
// Raw scores (per demand node)
raw_urgency[ii] = lambda[ii][si] * demand[i]    // λ · D
raw_isolation[ii] = (n_reach > 0) ? 1.0/n_reach : 1.0  // inverse reachable hubs
raw_dist[ii] = (min_t < big_M) ? min_t : 0.0   // min C_time to any active hub

// Each component normalized to [0,1] (normalise_inplace)
// If range ≈ 0: all set to 0.5

// Composite score
demand_score[ii] = W[0]*urgency + W[3]*isolation - W[1]*dist + (ii * 1e-6)
//                  ↑ urgency↑    ↑ isolated↑      ↑ close↑    ↑ tiebreak
```

**Critical details:**
- `raw_dist` uses `C_time`, not Euclidean distance.
- The tiebreaker `ii * 1e-6` ensures stable ordering by original index when scores are equal.
- `n_reach` counts active hubs reachable by ANY mode (loop over all m).
- `min_t` is the minimum C_time over all modes and all active hubs (not just assigned mode).
- `raw_dist` enters the score **negated** (`-W[1]*dist`) — higher dist → lower score (farther from help → lower priority). Note this means isolated and far demands score LOWER, which seems counter-intuitive. The isolation term `+W[3]*isolation` partially counteracts this: isolated nodes (few reachable hubs) score higher.

**Knee-point insight:** W[0]=0.184, W[1]=0, W[3]=0 → score = 0.184 * urgency + ii*1e-6.
Demands are sorted purely by λ·D (vulnerability × demand). Distance and isolation have no effect.

---

## 5. Step 4 — Tiered Hub Assignment (the core)

### Paper §3 Steps 3–3

```
K = max(1, ⌈w₅|H|⌉)
trial ← π_{A_i}
Pass 1: k* ← argmax HubScore over first K active reachable hubs with residual > 0
Pass 2: assign to first active reachable hub (CV permitted)
Pass 3: open nearest safe inactive hub; add F^a_ks; CV^s += 1
```

### `decoder.hpp` (lines 255–393) — full detail

#### K window
```cpp
const int K = std::max(1, (int)std::ceil(ind.W[5] * num_H));  // line 255
```

#### Pass 1 (lines 271–305)
```cpp
for (int j = 0; j < K; j++) {
    int ki = trial_order[j];
    if (!active[ki] && !y[ki]) continue;    // skip inactive (incl. not yet reactive)
    auto [b_m, best_t] = best_mode_time(i, k);
    if (b_m == -1) continue;               // skip unreachable
    
    double residual = inventory[ki] - hub_load[ki];
    
    // Transshipment-aware residual check (key addition vs paper)
    bool has_global_surplus = any(inventory[kj]-hub_load[kj] > EPS for kj active/reactive);
    if (residual <= 0.0 && !has_global_surplus) continue;
    
    double score = W[1]*(1.0/(best_t+EPS)) + W[2]*max(0.0,residual) + W[4]*(x[ki]?1.0:0.0);
    if (score > best_hub_score) { best_hub_score=score; best_ki=ki; chosen_m=b_m; }
}
```

**Pass 1 conditions:**
1. Hub is active OR already opened as reactive (`active[ki] || y[ki]`)
2. Reachable by some mode (best_mode_time returns mode ≠ -1)
3. `residual > 0` OR global surplus exists (allows zero-stock hub if transshipment can cover)
4. Scored by: speed + residual + planned bonus → argmax

#### Pass 2 (lines 307–323)
```cpp
if (best_ki == -1) {  // only if Pass 1 failed
    for (int j = K; j < num_H; j++) {   // continues trial_order from position K
        int ki = trial_order[j];
        if (!active[ki] && !y[ki]) continue;
        auto [b_m, best_t] = best_mode_time(i, k);
        if (b_m == -1) continue;
        best_ki = ki; chosen_m = b_m;
        break;  // first found wins — no scoring, no capacity check
    }
}
```

**Pass 2 key differences from Pass 1:**
- No scoring — first valid hub wins
- No residual check (capacity violation accepted)
- Iterates `trial_order[K..num_H-1]` (NOT all hubs — continues from where Pass 1 stopped)

#### Pass 3 (lines 325–347)
```cpp
if (best_ki == -1) {  // only if both Pass 1 and Pass 2 failed
    for (int ki = 0; ki < num_H; ki++) {   // NOT trial_order — scans all
        if (active[ki] || y[ki]) continue;  // skip already active
        int k = inst.hub_idx[ki];
        if (sc.risk[k] > inst.chi) continue; // safety constraint
        auto [b_m, best_t] = best_mode_time(i, k);
        if (b_m == -1) continue;            // must be reachable
        
        y[ki] = true;
        inventory[ki] = 0.0;  // reactive hubs carry ZERO pre-positioned stock
        Z1_s += sc.hub_reactive_cost[ki];
        best_ki = ki; chosen_m = b_m;
        break;  // first valid reactive hub
    }
}
```

**Pass 3 is NOT "nearest safe hub"** — it's the first safe, unreachable hub in local
index order (0..num_H-1). The paper description "nearest" is imprecise.

#### Still infeasible (lines 349–353)
```cpp
ind.CV += D_kg;         // D_kg = gamma * D (kg equivalent)
Z1_s += inst.big_M;
umax(Z2_s, inst.big_M);
```
CV accumulates infeasibility in WEIGHT (kg), not in demand node count.

#### Post-assignment accounting (lines 355–393)
```cpp
// Hub load update
hub_load[best_ki] += D_kg;  // D_kg = gamma * demand

// Reactive hub cost (if opened implicitly, not via Pass 3)
if (!x[best_ki] && !y[best_ki]) {
    y[best_ki] = true;
    inventory[best_ki] = 0.0;
    Z1_s += sc.hub_reactive_cost[best_ki];
}

// Daganzo CA last-mile cost (pre-computed in inst.theta)
Z1_s += inst.theta[best_ki][ii][si];

// Z2: omega = hub_process_time + 2 * min C_time over ALL modes with acc=1
double min_t = inst.big_M;
for (int m = 0; m < num_M; m++)
    if (sc.acc(m, i, bk))
        umin(min_t, inst.C_time[m][i][bk]);
double omega = sc.hub_process_time[best_ki] + 2.0 * (min_t < big_M ? min_t : 0.0);

// Exponential deprivation (capped at e^20 to prevent overflow)
double exp_arg = std::min(lam * omega, 20.0);
double depriv = D * std::expm1(exp_arg);   // expm1(x) = e^x - 1
umax(Z2_s, depriv);                        // running MAX across demands
```

**Critical Z2 detail:** omega uses min C_time over ALL modes with acc=1 — NOT just
the mode chosen for assignment. A demand node assigned via road uses the
fastest-available mode's time in the deprivation penalty, which may be air (faster
but more expensive).

**Z2_s is per-scenario MAX** (not sum). Then `Z2 += pi_s * Z2_s` → expected max.

---

## 6. `best_mode_time` and `best_mode_cost`

Both follow the same pattern (lines 138–168):

```cpp
// Time-based selector (used for demand/hub assignment)
auto best_mode_time = [&](int from_node, int to_node) -> pair<int, double> {
    int best_mode = -1;
    double best_time = inst.big_M;      // sentinel
    for (int m : {0, 1}) {             // road, water FIRST
        if (sc.acc(m, from_node, to_node) && inst.C_time[m][from][to] < best_time) {
            best_time = inst.C_time[m][from][to];
            best_mode = m;
        }
    }
    if (best_mode == -1 && sc.acc(2, from_node, to_node)) {   // air FALLBACK
        best_time = inst.C_time[2][from][to];
        best_mode = 2;
    }
    return {best_mode, best_time};
};
```

**Key semantics:**
- `acc(m, u, v)` = `a[m][u][v]` (binary adjacency matrix, initialized to 1 then overridden from JSON)
- For road/water: requires BOTH `acc=1` AND `C_time < current_best` (implicitly `< big_M`)
- For air: requires `acc=1` only — no C_time gate (air is fallback of last resort)
- Returns `{-1, big_M}` if pair is completely unreachable by any mode

`best_mode_cost` is identical but uses `inst.C_cost` instead of `inst.C_time` and
is used exclusively for supply routing (Step 5), not demand assignment.

---

## 7. Step 5 — Supply Routing (MCF)

### Paper Step 4
> "Origins supply the most under-supplied active hubs, and surplus is redistributed
> via discounted inter-hub trans-shipment (α). Expected objectives Z1 and Z2 are
> accumulated across all s ∈ S."

### `decoder.hpp` (lines 396–641) — `use_global_balancer=true` path

The MCF network is constructed as:
```
SRC → origin nodes (capacity = O_js, cost=0)
SRC → hub nodes with surplus (capacity = surplus, cost=0)
origin → hub (capacity = O_js, cost = best_mode_COST(j→k))
hub_surplus → hub_deficit (capacity = big_cap, cost = α * best_mode_COST(k→h))
hub_deficit → SNK (capacity = deficit, cost=0)
```

Solved with `min_cost_flow(g, SRC, SNK, total_deficit)`.

**For visualization:** `flow_out->z_jks[si][jj]` = dominant destination hub (largest
flow), `flow_out->z_jks_m[si][jj]` = mode to that hub.

**Legacy greedy path** (`use_global_balancer=false`):
- Each origin → hub with worst (most negative) net_inv, by best_mode_cost
- Then pairwise surplus→deficit transshipment, iterating until no valid pair

---

## 8. Step 6 — Constraint Checking and CV Accumulation

### Capacity violation (lines 649–669)
```cpp
for (int ki = 0; ki < num_H; ki++) {
    if (net_inv[ki] < -EPS) {
        double deficit = -net_inv[ki];
        Z1_s += deficit * inst.c_hold[ki] * 10.0;  // emergency purchase
        
        double max_net_inv = inst.kappa[ki] - inventory[ki] + net_inv[ki];
        if (max_net_inv < -EPS)
            ind.CV += -max_net_inv;  // physical capacity exceeded
    }
}
```

### Helicopter cap (lines 673–677)
```cpp
double max_heli = 0.15 * act_num_links + 0.999;
if (act_heli_links > max_heli)
    ind.CV += (act_heli_links - max_heli) * 10.0;
```

Maximum 15% of all transport links can use air. CV is additive with weight 10.

---

## 9. FlowDetails Output (what the solver stores)

When called with `flow_out != nullptr` (e.g., from a post-solve analysis script):

```cpp
flow_out->z_iks[si][ii]    // local hub index assigned to demand ii in scenario si
flow_out->z_iks_m[si][ii]  // transport mode for that assignment
flow_out->z_jks[si][jj]    // dominant hub index for origin jj
flow_out->z_jks_m[si][jj]  // mode for origin assignment
flow_out->f_khms[si]        // list of {src_ki, dst_ki, mode, flow} transshipment records
flow_out->y_ks[si][ki]      // true if hub ki is reactive in scenario si
flow_out->inventory_held[si][ki]  // inventory at hub ki in scenario si
```

**The result JSON does NOT contain FlowDetails.** The solver stores only
X, R, A, W, Z1, Z2, CV, rank per solution. FlowDetails would need a
separate `--flow-out` run of the solver binary.

---

## 10. The Ly Son Island Issue (Image #1)

The map shows Ly Son island connected by ROAD (red line) to the mainland in the
Mild scenario. Ly Son is an offshore island ~15 km from the Quang Ngai coast with
no road connection — only ferry (water) or helicopter.

**Root cause in data:**
The v1 dataset uses Delaunay triangulation with a 40 km display threshold. Ly Son's
centroid is within 40 km of mainland nodes, so Delaunay included a Ly Son→mainland
edge. The pre-OSRM v1 road graph did not validate drivability (no island detection),
so `acc[0][ly_son][mainland_node] = 1` in some scenarios. OSRM would reject this
(no drivable route to an island), but v1 predates OSRM validation.

**This is a DATA bug, not a postprocessor algorithm bug.** The accessibility matrix
for v1 needs `acc[0][ly_son_idx][*] = 0` (or equivalently `C_time[0][ly_son_idx][*]
= big_M`) for all mainland nodes. The postprocessor correctly follows the data.

**The single water node surrounded by roads:**
One demand node has `acc[0][d][h] = 0` for ALL active hubs but `acc[1][d][h] = 1`
for exactly one hub. This produces one water assignment while neighbors use road. This
is correct behavior — the node may be along a coastal or river area where road
connectivity is blocked to the specific hub candidates.

---

## 11. Summary: What the Paper Omits / Underspecifies

| Detail | Paper says | Decoder does |
|---|---|---|
| A[ii] semantics | "preferred anchor hub" | Local hub index 0…\|H\|-1, `% num_H` guard |
| Trial order | "starting from anchor π_{A_i}" | All hubs sorted by distance FROM anchor hub (hub_anchor_order) |
| Pass 1 residual | "residual > 0" | residual > 0 OR global surplus exists (transshipment-aware) |
| Pass 3 selection | "nearest safe inactive hub" | First (index-order) safe+reachable inactive hub |
| CV unit | "CV += 1" (Algorithm 1) | CV += D_kg = γ·D (weight in kg, not count) |
| Z2 omega | "2 × min_m(τ_kim)" | min over ALL modes with acc=1, including modes not used for assignment |
| W[1] role | "hub travel time" | Used in BOTH demand score (−W[1]·dist) AND hub score (W[1]/time) |
| Pass 2 range | not stated | trial_order[K..num_H−1] only (not all hubs) |
| Force-activate | "safest hub" | Min risk across ALL hub candidates regardless of X[k] |
| Inventory held | implicit | Per-scenario: reactive hubs get 0; output is `inventory[ki]` post-activation |
