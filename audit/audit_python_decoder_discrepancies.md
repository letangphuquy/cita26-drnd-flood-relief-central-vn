# Python Postprocessor Audit — Discrepancies vs `decoder.hpp`

> Comparing `visualizer/preprocess_flows.py` (current, committed at `3d6a5b0`)
> against `src/solver/decoder.hpp` (v3).
>
> Severity legend:
> - **CRITICAL** — produces fundamentally different hub/mode assignments
> - **MAJOR** — significantly affects output for most solutions
> - **MODERATE** — affects edge cases or specific solution shapes
> - **MINOR** — cosmetic / visualization-only impact

---

## D1 — Hub Trial Order [CRITICAL]

### C++ (`decoder.hpp` lines 98–117, 264–265)
```cpp
// Pre-computed: hub_anchor_order[ki][j] = j-th closest hub to hub ki
// Trial order for demand ii:
const int anchor = ind.A[ii] % num_H;
const vector<int> &trial_order = hub_anchor_order[anchor];
// trial_order[0] = anchor hub itself (distance 0)
// trial_order[1..] = other hubs in ascending Euclidean distance FROM anchor
```

### Python (`preprocess_flows.py` lines 116–158)
```python
# Iterates active_hubs_global in arbitrary insertion order
for h_global in active_hubs_global:
    for m in (0, 1):
        ...  # finds global minimum C_time across ALL hubs
```

### Discrepancy
Python never reads `solution.A` (the anchor hub indices). It searches all active
hubs for the globally fastest road/water option. C++ searches hubs in
anchor-proximity order within a K-window.

**Impact:** For the knee-point solution with W[5]=0.0 → K=1, Pass 1 checks ONLY
the anchor hub. If anchor not active or reachable, falls to Pass 2 (remaining hubs
in distance order). Python's "globally fastest" will assign to a completely
different hub in many cases — specifically whenever the fastest road hub is NOT the
anchor hub or its nearest neighbor.

---

## D2 — W Weights Not Used Anywhere [CRITICAL]

### C++ — W used in 4 places
```cpp
// Demand score
demand_score[ii] = W[0]*urgency + W[3]*isolation - W[1]*dist;
// Pass-1 window
K = max(1, ceil(W[5] * num_H));
// Hub score
score = W[1]*(1/(best_t+EPS)) + W[2]*max(0,residual) + W[4]*(x[ki]?1:0);
```

### Python
```python
# solution.W is loaded by solution_loader.py (line 150: W=list(raw.get("W") or []))
# but never accessed anywhere in preprocess_flows.py
```

**Impact:** All W effects are lost:
- Demand ordering: always iteration order, not λ·D sort
- Hub scoring: no planned-hub bonus (W[4]=0.418 dominates for knee-point)
- Window depth: always scans all hubs (K effectively = num_H)

---

## D3 — No Demand Priority Sorting [CRITICAL]

### C++ (lines 200–246)
```cpp
// Compute composite score for each demand
demand_score[ii] = W[0]*urgency + W[3]*isolation - W[1]*dist + ii*1e-6;
// Sort demands descending by score BEFORE assignment loop
std::sort(demand_order.begin(), demand_order.end(),
          [&](int a, int b) { return demand_score[a] > demand_score[b]; });
// Process in this priority order
for (int ii : demand_order) { ... }
```

### Python
```python
for d_idx in node_info.demand_indices:  # arbitrary order, no sorting
    ...
```

**Impact:** In C++, high-urgency demands claim best hubs first. Low-urgency demands
may end up with worse hubs (capacity overflow or worse mode). Python assigns in
node-index order — first nodes get first pick regardless of urgency. The resulting
hub assignments can differ substantially, especially when hub capacity matters.

---

## D4 — No 3-Pass Structure / K-Window [CRITICAL]

### C++ — 3 distinct passes
```
Pass 1: trial_order[0..K-1] — scored, capacity-checked, argmax
Pass 2: trial_order[K..num_H-1] — first reachable, no capacity check
Pass 3: all inactive hubs — open reactive hub (risk ≤ χ, reachable)
```

### Python — 2-tier mode-priority search
```python
# "Pass 1": find fastest road/water hub across ALL active hubs
for h_global in active_hubs_global:
    for m in (0, 1): ...

# "Pass 2": find fastest air hub
for h_global in active_hubs_global:
    if acc[2][d][h]: ...
```

**Impact:**
- Python's "Pass 1" is actually a global minimum-C_time scan with no window
- No hub scoring function (no W[1], W[2], W[4])
- No capacity check or capacity-aware selection
- Pass 3 (reactive hub opening) completely absent
- Python iterates road AND water simultaneously; C++ tries them by C_time comparison

---

## D5 — Hub Scoring Function Missing [MAJOR]

### C++ Hub Score (line 298)
```cpp
double score = W[1] * (1.0 / (best_t + EPS))   // speed bonus
             + W[2] * std::max(0.0, residual)    // residual capacity bonus
             + W[4] * (x[ki] ? 1.0 : 0.0);      // planned hub bonus
```

### Python
No hub scoring. Assignment goes to hub with minimum C_time (road/water preferred).

**Impact for knee-point (W = [0.184, 0.0, 0.023, 0.0, 0.418, 0.0]):**
- W[1]=0: speed plays no role in C++ hub scoring either for this solution
- W[4]=0.418: C++ strongly prefers planned hubs (X[k]=1)
- W[2]=0.023: small residual preference
- Net effect: C++ picks the anchor hub (if active, planned) even if a reactive hub
  might have shorter travel time. Python always picks the globally fastest hub.

---

## D6 — No Capacity Tracking [MAJOR]

### C++ (lines 249, 357, 649–669)
```cpp
vector<double> hub_load(num_H, 0.0);
// During assignment:
hub_load[best_ki] += D_kg;          // D_kg = gamma * demand
// residual = inventory[ki] - hub_load[ki]  (decrements per assigned demand)
// Post-MCF capacity check:
if (net_inv[ki] < -EPS) CV penalty
```

### Python
```python
# No hub_load tracking
# No residual computation
# No capacity violation detection
```

**Impact:** Python assigns ALL demands to their "best" hub without checking whether
that hub has sufficient inventory. C++ distributes load across hubs to respect
capacity constraints, potentially sending later-processed demands to sub-optimal
hubs rather than overloading the best one.

---

## D7 — y_ks Semantics Mismatch [MAJOR]

### C++ — y_ks is dynamic
```cpp
vector<bool> y(num_H, false);  // starts empty
// y[ki] = true when reactive hub opened during Pass 3 (or implicitly)
// active hub set = {ki : active[ki] || y[ki]}
```

### Python — y_ks is precomputed (static)
```python
def _derive_y_ks(solution, node_info, scenario, risk_threshold):
    # Returns True only for established (X[k]=1) hubs passing risk filter
    return [solution.X[k] == 1 and risk < risk_threshold for k in hubs]
```

**Impact:**
1. Python never opens reactive hubs (no Pass 3 equivalent).
2. Python's y_ks conflates "planned hub activated" with "reactive hub opened" —
   they have different inventory semantics (planned: q_k > 0; reactive: q = 0).
3. The set of "active" hubs in Python is always `{k: X[k]=1 AND risk < chi}`.
   In C++, this set can grow during the demand assignment loop when Pass 3 triggers.

---

## D8 — Force-Activate Fallback Missing [MODERATE]

### C++ (lines 178–197)
```cpp
if (!any_active) {
    int best_ki = argmin(sc.risk[k] for all k);
    active[best_ki] = true;
    inventory[best_ki] = q[best_ki];  // may be 0 if X[best_ki]=0
}
```

### Python (`_derive_y_ks`)
```python
# If all hubs have X[k]=0 or all risky → returns all False
# Caller gets empty active_hubs_global → all demands assigned hub_idx=-1
```

**Impact:** For infeasible partial solutions (e.g., v2 results with CV>0), Python
may produce `hub_idx=-1` for all demands instead of forcing the safest hub active.
The map then renders all demand nodes as unassigned.

---

## D9 — Inventory Held: Per-Scenario vs Static [MODERATE]

### C++
```cpp
flow_out->inventory_held[si][ki] = inventory[ki];  // per-scenario
// inventory[ki] = q[ki]  for planned active hubs
// inventory[ki] = 0      for reactive hubs (y[ki]=true)
```

### Python
```python
def _derive_inventory_held(solution, node_info, instance_raw):
    # R[k] * capacity[k] for established hubs — SAME for all scenarios
    held.append(cap * r if solution.X[k] == 1 else 0.0)
```

**Impact:** Python shows the same inventory for all 3 scenarios. In C++, hubs
that become reactive in severe/extreme scenarios show 0 inventory (they carry
no pre-positioned stock). Python inflates displayed inventory for those hubs.

---

## D10 — Pass 2 Scope [MODERATE]

### C++ (line 310)
```cpp
for (int j = K; j < num_H; j++) {  // continues trial_order FROM position K
```
Pass 2 is the CONTINUATION of the same trial_order list, starting where Pass 1 stopped.

### Python
```python
# No distinct Pass 1 / Pass 2 windows.
# Conceptually: Python's road/water scan = Pass 1 over ALL hubs
#               Python's air scan = Pass 2 over ALL hubs
# Neither respects the anchor-proximity ordering or the K boundary.
```

**Impact:** Python's "Pass 2" (air scan) starts over from the beginning of all
active hubs, not from position K in anchor-distance order. This can produce a
different hub assignment than C++'s anchor-ordered fallback.

---

## D11 — Transshipment Absent [MINOR for maps]

### C++
Full MCF or greedy origin→hub and hub→hub transshipment flows, recorded in
`flow_out->f_khms[si]`. These update net inventory and accumulate Z1 transport costs.

### Python
```python
"transshipment": []  # always empty
```

**Impact on visualization:** No transshipment lines drawn on map. Z1 values in
flow files use solver's precomputed Z1, not a recomputed value, so the number shown
is correct. Hub net-inventory display is wrong (doesn't reflect origin supply).

---

## D12 — `_best_mode` Helper Is Dead Code [MINOR]

```python
def _best_mode(accessibility, src, dst, c_time=None):  # lines 45-64
    """..."""
    ...
```

This function is defined but **never called** in the current code. The actual
mode logic is inlined in `_derive_demand_assignments` and `_derive_origin_assignments`.
It should either be removed or used.

---

## D13 — Helicopter Cap Constraint Not Checked [MINOR]

### C++ (lines 673–677)
```cpp
double max_heli = 0.15 * act_num_links + 0.999;
if (act_heli_links > max_heli)
    ind.CV += (act_heli_links - max_heli) * 10.0;
```

### Python
Not implemented. No helicopter count tracked.

**Impact on CV:** For solutions where many mountain communes require air, the
helicopter cap constraint may be violated. Python would not detect or penalize
this. For the corrected postprocessor this matters less (it's a constraint on
the optimization, not the visualization).

---

## D14 — Z2 Not Recomputed [MINOR for maps]

Python uses the solver's Z2 from the result JSON for display. The correct Z2
requires knowing omega per demand-hub pair (tau_ks + 2 * min travel time). Since
preprocess_flows.py can compute omega from the assigned hub and C_time, this could
be recomputed — but it requires hub_process_time from the instance, which is not
currently loaded.

---

## Summary Table

| ID | Issue | Severity | Lines (Python) | Lines (C++) |
|---|---|---|---|---|
| D1 | Hub trial order ignores A[ii] | CRITICAL | 116–158 | 264–265, 98–117 |
| D2 | W weights never used | CRITICAL | (none) | 237–239, 255, 298 |
| D3 | No demand priority sorting | CRITICAL | 116 | 243–246 |
| D4 | No 3-pass / K-window structure | CRITICAL | 116–158 | 271–347 |
| D5 | Hub scoring function absent | MAJOR | 125–133 | 298–304 |
| D6 | No capacity tracking | MAJOR | (none) | 249, 357, 649 |
| D7 | y_ks static vs dynamic | MAJOR | 67–86 | 128–129, 340–342 |
| D8 | Force-activate fallback absent | MODERATE | 67–86 | 178–197 |
| D9 | Inventory held: static vs per-scenario | MODERATE | 222–235 | 679–683 |
| D10 | Pass 2 scope / trial_order boundary | MODERATE | 139–152 | 307–323 |
| D11 | Transshipment always empty | MINOR | 261 | 396–641 |
| D12 | `_best_mode` is dead code | MINOR | 45–64 | — |
| D13 | Helicopter cap not checked | MINOR | (none) | 673–677 |
| D14 | Z2 not recomputed | MINOR | (none) | 382–393 |

---

## RFC — Corrected Postprocessor Implementation Plan

### Principle
The postprocessor cannot be a perfect replica of the decoder without:
1. The MCF solver (steps 5–6)
2. Pre-computed `theta[ki][ii][si]` (Daganzo CA cost)
3. Real-time inventory/flow balancing

The goal is a **faithful approximation** that is correct for the decisions
visible in the visualizer (demand→hub assignment and mode). Z1/Z2 come from
the solver JSON, not recomputed.

### Required inputs
From solution JSON: `X`, `R`, `A`, `W` (all available).  
From instance JSON: `accessibility`, `transport.time`, `global_params.chi`,
`hub_params.capacity`, `scenarios[].hub_risk`, `scenarios[].demand`, `nodes`.  
From NodeInfo: `hub_indices`, `demand_indices`, `origin_indices`, `coords`, `names`.

### Step-by-step RFC

#### RFC-1: Pre-compute `hub_anchor_order`
```python
def _hub_anchor_order(node_info: NodeInfo) -> List[List[int]]:
    """hub_anchor_order[ki][j] = local hub index of j-th closest hub to hub ki."""
    num_H = len(node_info.hub_indices)
    coords = node_info.coords
    order = []
    for ki in range(num_H):
        h_i = node_info.hub_indices[ki]
        lat_i, lon_i = coords[h_i]
        dists = []
        for kj in range(num_H):
            h_j = node_info.hub_indices[kj]
            lat_j, lon_j = coords[h_j]
            d2 = (lat_i - lat_j)**2 + (lon_i - lon_j)**2
            dists.append((d2, kj))
        dists.sort()
        order.append([kj for _, kj in dists])
    return order
```

#### RFC-2: Demand priority scoring and sorting
```python
def _demand_priority_order(
    solution: Solution,
    node_info: NodeInfo,
    active_hubs_global: List[int],
    accessibility: List,
    c_time: List,
    scenario: Dict,
) -> List[int]:
    """Return demand local indices sorted by decoder priority score (descending)."""
    W = solution.W
    num_I = len(node_info.demand_indices)
    num_H_active = len(active_hubs_global)
    BIG_M = 1e8
    demands_raw = scenario.get("demand", {})

    urgency, isolation, dist = [], [], []
    for ii, d_global in enumerate(node_info.demand_indices):
        D = float(demands_raw.get(str(d_global), 1.0))
        # lambda[ii][si] not available — use D as proxy (paper: λ·D, λ ≈ 1 baseline)
        urgency.append(D)

        n_reach = 0
        min_t = BIG_M
        for h_global in active_hubs_global:
            for m in range(3):
                if _is_accessible(accessibility, m, d_global, h_global):
                    n_reach += 1
                    if c_time:
                        t = float(c_time[m][d_global][h_global])
                        if t < min_t:
                            min_t = t
                    break  # count hub once
        isolation.append(1.0 / n_reach if n_reach > 0 else 1.0)
        dist.append(min_t if min_t < BIG_M else 0.0)

    def _norm(v):
        mn, mx = min(v), max(v)
        rng = mx - mn
        if rng < 1e-9:
            return [0.5] * len(v)
        return [(x - mn) / rng for x in v]

    u_n = _norm(urgency)
    iso_n = _norm(isolation)
    dist_n = _norm(dist)

    scores = [
        W[0]*u_n[ii] + W[3]*iso_n[ii] - W[1]*dist_n[ii] + ii*1e-9
        for ii in range(num_I)
    ]
    return sorted(range(num_I), key=lambda ii: scores[ii], reverse=True)
```

**Note:** `lambda[ii][si]` is not in the instance JSON (it's computed inside C++ as
`lambda_0 * (1 + r_is)`). Use `demands[i]` as urgency proxy; or add `lambda_0`
from `global_params` and compute `lambda_0 * (1 + node_risk_i)`.

#### RFC-3: Hub scoring function
```python
def _hub_score(W, c_time_val: float, residual: float, is_planned: bool) -> float:
    return (W[1] * (1.0 / (c_time_val + 1e-9))
          + W[2] * max(0.0, residual)
          + W[4] * (1.0 if is_planned else 0.0))
```

#### RFC-4: Corrected `_derive_demand_assignments`
```python
def _derive_demand_assignments_v2(
    solution: Solution,
    node_info: NodeInfo,
    y_ks: List[bool],
    scenario: Dict[str, Any],
    c_time: Optional[List] = None,
    hub_anchor_order: Optional[List[List[int]]] = None,
) -> List[Dict[str, Any]]:
    coords = node_info.coords
    accessibility = scenario.get("accessibility", [])
    W = solution.W or [0.5]*6

    # Active set: planned hubs passing risk filter
    # (reactive hubs not modeled here — no Pass 3 for visualization)
    is_active = list(y_ks)   # bool per local hub index
    active_hubs_local = [k for k, a in enumerate(is_active) if a]

    # Force-activate safest hub if empty (mirrors decoder Step 2 fallback)
    if not active_hubs_local:
        hub_risk = scenario.get("hub_risk", {})
        safest_k = min(
            range(len(node_info.hub_indices)),
            key=lambda k: float(hub_risk.get(str(node_info.hub_indices[k]), 1.0))
        )
        is_active[safest_k] = True
        active_hubs_local = [safest_k]

    # K = max(1, ceil(W[5] * num_H))
    num_H = len(node_info.hub_indices)
    K = max(1, math.ceil(W[5] * num_H))
    BIG_M = 1e8

    # Inventory and load tracking
    hub_params = {}  # would need capacity from instance
    inventory = [0.0] * num_H
    for ki in range(num_H):
        if is_active[ki] and solution.X[ki] == 1:
            # q_k = R_k * kappa_k (capacity needed from instance)
            inventory[ki] = float(solution.R[ki])  # placeholder: normalize later
    hub_load = [0.0] * num_H

    # Demand priority order
    active_hubs_global = [node_info.hub_indices[k] for k in active_hubs_local]
    priority_order = _demand_priority_order(
        solution, node_info, active_hubs_global, accessibility, c_time, scenario
    )

    assignments = [None] * len(node_info.demand_indices)

    for ii in priority_order:
        d_global = node_info.demand_indices[ii]
        anchor = solution.A[ii] % num_H if solution.A and ii < len(solution.A) else 0
        trial_order = hub_anchor_order[anchor] if hub_anchor_order else list(range(num_H))

        best_ki = -1
        best_mode = -1
        best_score = -1e18

        # Pass 1: first K hubs in anchor-proximity order, scored
        for j in range(min(K, num_H)):
            ki = trial_order[j]
            if not is_active[ki]:
                continue
            k_global = node_info.hub_indices[ki]
            b_m, b_t = _best_mode_time_py(accessibility, d_global, k_global, c_time, BIG_M)
            if b_m == -1:
                continue
            residual = inventory[ki] - hub_load[ki]
            # Simplified global surplus check
            has_surplus = any(inventory[kj] - hub_load[kj] > 0 for kj in active_hubs_local)
            if residual <= 0 and not has_surplus:
                continue
            score = _hub_score(W, b_t, residual, solution.X[ki] == 1)
            if score > best_score:
                best_score = score
                best_ki = ki
                best_mode = b_m

        # Pass 2: remaining hubs in anchor-proximity order, first reachable
        if best_ki == -1:
            for j in range(K, num_H):
                ki = trial_order[j]
                if not is_active[ki]:
                    continue
                k_global = node_info.hub_indices[ki]
                b_m, _ = _best_mode_time_py(accessibility, d_global, k_global, c_time, BIG_M)
                if b_m != -1:
                    best_ki = ki
                    best_mode = b_m
                    break

        # Pass 3 omitted for visualization (no reactive hub opening)
        # Fallback: nearest active hub by geometry
        if best_ki == -1 and active_hubs_local:
            best_ki = min(active_hubs_local,
                          key=lambda k: _dist(coords[d_global], coords[node_info.hub_indices[k]]))
            best_mode = 0

        if best_ki >= 0:
            hub_load[best_ki] += 1.0  # unit load (kg not tracked without capacity data)
            assignments[ii] = {
                "demand_idx": d_global,
                "hub_idx": node_info.hub_indices[best_ki],
                "mode": best_mode,
            }
        else:
            assignments[ii] = {"demand_idx": d_global, "hub_idx": -1, "mode": 0}

    return assignments


def _best_mode_time_py(accessibility, src, dst, c_time, BIG_M=1e8):
    """Python equivalent of decoder's best_mode_time."""
    best_mode = -1
    best_time = BIG_M
    for m in (0, 1):
        if _is_accessible(accessibility, m, src, dst):
            t = float(c_time[m][src][dst]) if c_time else float(m)
            if t < best_time:
                best_time = t
                best_mode = m
    if best_mode == -1 and _is_accessible(accessibility, 2, src, dst):
        best_mode = 2
        best_time = float(c_time[2][src][dst]) if c_time else 0.0
    return best_mode, best_time
```

### RFC-5: Open questions requiring data before implementing

1. **`lambda[ii][si]`**: Deprivation sensitivity `λ₀(1+r_is)`. The instance JSON
   stores `global_params.lambda_0` but node risk `r_is` needs to come from
   `scenarios[si].risk[i_global]` (currently stored as `scenario.risk` dict in
   instance JSON). Verify key format.

2. **`kappa[ki]`**: Hub capacity. Stored in `hub_params.capacity[str(h_global)]`.
   Needed to compute inventory = R[ki] * kappa[ki] for capacity tracking.

3. **`gamma`**: Relief items per person (`global_params.gamma`). Needed to convert
   demand D (persons) to D_kg (kg) for capacity tracking.

4. **`hub_process_time[ki][si]`**: `τ_ks` from `scenarios[si].hub_process_time`.
   Needed only for Z2 recomputation (currently not needed for visualization).

5. **Reactive hub costs**: `scenarios[si].hub_reactive_cost[ki]`. Needed only
   if implementing Pass 3 reactive hub opening.

### RFC-6: What NOT to implement (for visualization scope)

- **MCF transshipment**: Requires porting the full MCF solver. Out of scope for
  the visualizer — showing `transshipment: []` is acceptable with a note.
- **Z1/Z2 recomputation**: Use solver's values. Recomputing requires pre-computed
  `theta[ki][ii][si]` (Daganzo CA cost) which is not in the instance JSON.
- **Helicopter cap enforcement**: CV is computed by solver; visualization doesn't
  need to recheck this constraint.

### RFC-7: Expected mode distribution after RFC fix

Based on the decoder's actual W[5]=0.0 → K=1 behavior for the knee-point solution:
- Most demands will be assigned to their anchor hub (A[ii]) if it is active and reachable
- Anchor hubs are geographically designed to serve their region → road connectivity
  between mountain communes and their anchor hub should be higher than to random hubs
- Expected: Air count should DECREASE further (from current 24) because anchor hubs
  are specifically chosen to serve their demand region with road/water access
- The specific value depends on A[ii] values and hub activity in each scenario

### RFC-8: Verification strategy
1. Run `decoder.hpp` via solver binary with `--flow-out` flag (if it exists), or
   add a debug output mode to dump `z_iks`, `z_iks_m`, `y_ks` per scenario.
2. Compare Python postprocessor output against solver's flow output for solution_2.
3. Track: hub assignment per demand, mode per demand, active hub set per scenario.
4. Acceptance criterion: mode distribution within ±5% of solver's actual output.
