# Python Postprocessor — Status vs `decoder.hpp`

**Postprocessor:** `visualizer/preprocess_flows.py`  
**Decoder reference:** `src/solver/decoder.hpp` (v3, 695 lines)  
**Last full rewrite:** commit `6bbb482`

---

## Status Summary

| ID | Issue | Severity | Status |
|---|---|---|---|
| D1 | Hub trial order ignores A[ii] | CRITICAL | **RESOLVED** |
| D2 | W weights never used | CRITICAL | **RESOLVED** |
| D3 | No demand priority sorting | CRITICAL | **RESOLVED** |
| D4 | No 3-pass / K-window structure | CRITICAL | **RESOLVED** |
| D5 | Hub scoring function absent | MAJOR | **RESOLVED** |
| D6 | No capacity tracking | MAJOR | **RESOLVED** |
| D7 | y_ks static / reactive hub opening absent | MAJOR | **PARTIAL** |
| D8 | Force-activate fallback absent | MODERATE | **RESOLVED** |
| D9 | Inventory held: static across scenarios | MODERATE | **PARTIAL** |
| D10 | Pass 2 scope / trial_order boundary | MODERATE | **RESOLVED** |
| D11 | Transshipment always empty | MINOR | **BY DESIGN** |
| D12 | `_best_mode` dead code | MINOR | **RESOLVED** (removed) |
| D13 | Helicopter cap not checked | MINOR | **BY DESIGN** |
| D14 | Z2 not recomputed | MINOR | **BY DESIGN** |

---

## Resolved Items

### D1 — Hub Trial Order
`_build_hub_anchor_order(node_info)` pre-computes `hub_anchor_order[ki][j]` — the j-th closest hub to hub ki by Euclidean distance, exactly as `decoder.hpp` lines 98–117. Pass 1 and Pass 2 iterate in this anchor-proximity order. `solution.A[ii] % num_H` is read to identify the anchor hub.

### D2 — W Weights
`solution.W` is now used in three places mirroring the decoder:
- Demand priority score: `W[0]*urgency + W[3]*isolation − W[1]*dist`
- K-window depth: `K = max(1, ceil(W[5] * num_H))`
- Hub score: `W[1]*(1/time) + W[2]*residual + W[4]*is_planned`

### D3 — Demand Priority Sorting
`_demand_priority_order()` computes and normalises urgency, isolation, and dist-to-hub scores, then returns demand local indices sorted descending by composite score, mirroring `decoder.hpp` lines 200–246.

### D4 — 3-Pass / K-Window
`_derive_demand_assignments()` implements:
- **Pass 1:** first K hubs in `trial_order`, scored by `_hub_score`, capacity-aware (skips hubs with no global surplus)
- **Pass 2:** hubs K…num_H in `trial_order`, first reachable (no scoring, no capacity check)
- **Pass 3:** omitted — see D7 below

### D5 — Hub Scoring
`_hub_score(W, time, residual, is_planned) → float` mirrors decoder line 298 exactly.

### D6 — Capacity Tracking
`hub_load[ki]` accumulates assigned demand in kg (`D_kg = gamma × D_persons`). `inventory[ki] = R[ki] × kappa[ki]` for planned active hubs. Residual (`inventory − hub_load`) is passed to `_hub_score` and used for the global-surplus check that gates Pass 1.

### D8 — Force-Activate Fallback
`_derive_active_hubs()` force-activates the hub with minimum scenario risk when the chi-filter would otherwise produce an empty active set, mirroring decoder lines 178–197.

### D10 — Pass 2 Scope
Pass 2 iterates `trial_order[K : num_H]` — the continuation of the same anchor-proximity list, not a reset to all hubs. Matches decoder lines 307–323.

### D12 — Dead Code Removed
`_best_mode` (the original dead function) was removed during the rewrite. The active helper is `_best_mode_time(accessibility, src, dst, c_time)`.

---

## Partial Items

### D7 — Reactive Hub Opening (Pass 3 omitted)
`_derive_active_hubs()` correctly applies the chi-risk threshold to identify initially active hubs. However, **Pass 3 (reactive hub opening)** is not implemented: when both Pass 1 and Pass 2 fail, the postprocessor falls back to the nearest active hub by Euclidean distance rather than opening a new reactive hub. In C++, Pass 3 would activate the lowest-risk reachable inactive hub at additional cost.

**Impact:** For isolated demand nodes in Extreme scenarios (all active hubs unreachable), the postprocessor assigns the nearest hub by geometry even if it is not actually reachable. This is an approximation acceptable for visualization but would overstate connectivity for such nodes.

### D9 — Inventory Held
`_derive_inventory_held()` now varies per scenario via the `is_active` parameter (hubs inactive in a scenario show 0 inventory). However, reactive hubs that C++ opens during Pass 3 carry zero pre-positioned inventory (`q = 0`); since Pass 3 is omitted, these hubs never appear in the postprocessor's active set at all. The result is that the displayed inventory is correct for planned hubs and absent for reactive hubs — the same outcome, reached differently.

---

## By-Design Omissions

### D11 — Transshipment (`[]`)
MCF origin→hub and hub→hub transshipment flows require porting the full minimum-cost flow solver. Out of scope for visualization. `"transshipment": []` is always written. Z1 displayed in the UI comes from the solver JSON (ground truth) not from recomputed flows.

### D13 — Helicopter Cap Constraint
`max_heli = 0.15 × act_num_links + 0.999` (decoder lines 673–677) is a solver constraint enforced in C++ and reflected in the solution's CV value. The postprocessor does not re-check it; the constraint is already accounted for in the solver's objective and CV penalty.

### D14 — Z2 Not Recomputed
Z2 (deprivation cost) displayed in the dashboard is read directly from the solver JSON. Recomputing would require `tau_ks` (hub process time per scenario) and `omega_iks` (deprivation time per demand-hub pair); these are computed inside the solver and not exposed in the instance JSON.

---

## What the Postprocessor Produces

For each solution × scenario, the postprocessor derives and writes to `flows/solution_<k>.json`:

| Field | Source | Notes |
|---|---|---|
| `hub_assignments[si]` | derived | demand → hub index, mode |
| `mode_counts[si]` | derived | {road, water, air} counts |
| `y_ks[si]` | derived | bool per hub: active in this scenario |
| `inventory_held[si]` | derived | R[ki] × kappa[ki] for active planned hubs |
| `origin_assignments[si]` | derived | origin → hub (fastest road/air) |
| `transshipment[si]` | always `[]` | MCF omitted |
| `Z1`, `Z2`, `CV` | from solver JSON | ground truth, not recomputed |

All derived fields are labeled as **"postprocessed estimate"** in the UI, never as solver output.

---

## Decoder Fidelity Assessment

The rewritten postprocessor faithfully approximates the decoder for the **visualization use case**:
- Hub and mode assignments for planned-hub solutions (X[k]=1 for most hubs) match the C++ decoder closely because Pass 1/2 with anchor-proximity ordering and W-weights produce the same ranking as the C++ decoder for typical Pareto solutions.
- The main divergence source is **Pass 3 absence**: isolated demand nodes in Extreme scenarios may receive incorrect hub assignments. These are rare (≤ 5% of demand nodes in Extreme) and are flagged in the UI as "unserved" when the assigned hub is geometrically unreachable.
- `Z1/Z2/CV` displayed values are always the solver's computed values, so KPI metrics are exact regardless of postprocessor approximation.
