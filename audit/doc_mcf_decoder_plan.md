# MCF Decoder — Python Implementation Plan

**Status:** Plan-only. Implementation tracked here; code in follow-up PR.  
**Purpose:** Mirror `src/solver/decoder.hpp::best_mode_time()` and the full
Stage-2 MCF in Python to produce accurate mode assignments, enable H2H
transshipment display on the map, and allow verified Z2 re-derivation.

---

## Why This Matters

The current Python postprocessor (`preprocess_flows.py`) uses a greedy
approximation. It correctly mirrors the *mode selection* rule from
`decoder.hpp` (Road/Water first; Air only when neither road nor water hub
is reachable) but cannot capture:

1. **Hub-to-Hub transshipment flows** — the current `transshipment` list is
   always empty. The solver's MCF can route supply through intermediate hubs.
2. **Optimal demand-to-hub assignment** — the greedy assigns by minimum
   `C_time` but does not respect hub capacity constraints jointly; MCF does.
3. **Z2 re-derivation** — without the true assignment, we cannot verify that
   the postprocessor's Z2 matches the solver's Z2 field.

---

## Problem Formulation (Stage-2 fixed-X MCF)

Given a fixed Stage-1 plan (X, R), Stage-2 for scenario s solves:

```
Minimize  Σ_{k,d,m} C_time[m][d][k] · f_{kdm}      (weighted deprivation)
          + Σ_{k,k',m} tau[m][k][k'] · h_{kk'm}     (transshipment cost)

Subject to:
  Σ_{k,m} f_{kdm} = D_{ds}           ∀ demand d     (demand satisfaction)
  Σ_d f_{kdm} ≤ kappa_k · R_k        ∀ hub k        (hub capacity)
  f_{kdm} = 0  if acc[m][d][k] = 0   (accessibility)
  y_ks = 1 if r_{ks} ≤ chi  AND  X_k = 1            (hub activation)
  f_{kdm} = 0  if y_ks = 0           (inactive hub)
  f_{kdm} ≥ 0, h_{kk'm} ≥ 0
```

`C_time[m][d][k]` is the lambda-weighted deprivation cost per unit demand
served (instance field `C_time`, mode × demand × hub tensor).

---

## Algorithm: Min-Cost Flow via OR-Tools

**Library:** `ortools.graph.min_cost_flow` — already in `requirements.txt`.
C++-backed, handles 10k-arc instances in milliseconds.

**Graph construction per scenario:**

```python
from ortools.graph.python import min_cost_flow as mcf_lib

def solve_stage2(instance, solution, scenario_idx, chi):
    # 1. Determine active hubs
    active = {k for k in open_hubs if hub_risk[s][k] <= chi}

    # 2. Build arc lists
    #    Arc encoding:  source=0, origin nodes, hub nodes, demand nodes, sink=last
    #    demand→hub arcs:  supply = D[d][s], cost = C_time[m][d][k] * SCALE
    #    hub capacity arcs: supply = kappa_k * R_k, cost = 0
    #    hub→sink arcs:    carry hub outflow, cost = 0

    smcf = mcf_lib.SimpleMinCostFlow()
    # ... add arcs
    status = smcf.Solve()
    if status != smcf.OPTIMAL:
        raise RuntimeError("MCF infeasible")

    # 3. Extract flows → DemandAssignment, Transshipment lists
    ...
```

Integer cost scaling: OR-Tools requires integer arc costs. Scale
`C_time[m][d][k]` by `1e4` and round to int. Verify total cost matches
solver Z2 within 1% tolerance.

---

## Planned Files

```
visualizer/
  mcf_decoder.py          — solve_stage2(instance, solution, s, chi) → ScenarioFlow
  preprocess_flows_mcf.py — drop-in replacement for preprocess_flows.py
                            using MCF instead of greedy; same CLI args
```

`preprocess_flows_mcf.py` will accept identical CLI args to `preprocess_flows.py`
so the UI can swap between the two without changes to `experiments_view.py`.

---

## Test Plan

1. Run MCF decoder for knee solution, seed 0, Mild scenario (CV-Large v2).
2. Assert `abs(mcf_Z2 - solver_Z2) / solver_Z2 < 0.01` (1% tolerance).
3. Assert every demand node appears exactly once in `demand_assignments`.
4. Assert all assigned hubs have `X[k]=1` and `hub_risk[s][k] ≤ chi`.
5. Assert total assigned demand = `Σ D[d][s]` for the scenario.

Run via: `.venv/bin/python3 -m pytest visualizer/tests/test_mcf_decoder.py`

---

## Open Questions (for implementation phase)

- **Transshipment arcs:** The CV-Large instance likely has no reachable H2H
  links (confirmed by all-zero `transshipment` in postprocessor output). If
  `tau[m][k][k']` is not in the instance JSON, skip these arcs.
- **Demand units:** `D[d][s]` is in persons. `C_time` cost coefficients
  encode per-person deprivation time. Confirm units before scaling.
- **Integer rounding:** If `kappa_k * R_k` is fractional, use `math.floor`
  for hub capacity arcs to stay within solver semantics.

---

## References

- Decoder logic: `src/solver/decoder.hpp::best_mode_time()`
- PRD §6: `audit/prd_proposal_dss.md`
- OR-Tools SimpleMinCostFlow API: `ortools.graph.python.min_cost_flow`
