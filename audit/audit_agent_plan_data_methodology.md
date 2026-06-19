# Data Methodology Audit & Implementation Plan — v2 Dataset Rebuild
**Author:** Claude Sonnet 4.6 (agent)
**Date:** 2026-06-17
**Scope:** `src/scripts/data_generate_cv.py` → `data/cv/v2/cv_large_drnd.json`
**Status:** PRE-IMPLEMENTATION — awaiting approval

---

## Context and Motivation

The v2 dataset was intended to improve on v1 by replacing the Delaunay-heuristic road graph
with OSRM-validated driving distances. That calibration was successful. However a secondary
bug was introduced: the random state used for epicenter sampling diverges between v1 and v2
because road-disruption draws (which depend on edge count, which changed with OSRM) happen
*inside* the same scenario loop as epicenter sampling. The consequence is that v2 Severe has
one mountain epicenter and v2 Extreme has all three epicenters in the western highlands — an
implausible flood configuration for Central Vietnam typhoons.

Additionally, the demand model was identified as structurally incorrect: demand is driven by
per-node scenario risk, which conflates intrinsic flood susceptibility (a node property) with
disaster exposure (an event property). A mountain commune with low intrinsic risk still
receives ~1,000 persons demand in Mild because base_population × risk_fraction is not zero.

Four changes are planned. Each is described below with current behaviour, rationale, exact
proposed implementation, risks, and validation criteria.

---

## What Does NOT Change

The following are explicitly preserved to maintain comparability with v1 and to avoid
re-running expensive operations:

| Item | Reason |
|---|---|
| All 132 node coordinates (100 demand, 20 hub, 12 origin) | Curated, geography-verified |
| OSRM road graph (`data/cache/osrm_road_graph_large.json`) | Already validated, API-expensive |
| `SCENARIO_DEFS` (probabilities, n_epicenters, beta_road, phi) | Model design, not calibration |
| `SEED = 2026` | Reproducibility |
| All model parameters (chi, gamma, alpha, lambda_0) | Solver compatibility |
| Hub/origin node pool | Pre-curated |
| Lambda (deprivation sensitivity) formula | Model parameter |
| Theta (Daganzo CA) formula | Model parameter |
| v1 canonical results and flow files | Immutable ground truth |

---

## Change 0 — Fix Random State Divergence (Root Cause Bug)

### Current behaviour

Inside `generate_scenarios`, for each scenario the code:
1. Samples epicenters (`_weighted_sample` → random calls)
2. Assigns epicenter intensity (`random.uniform` per epicenter)
3. Applies road disruption (`random.random()` per road edge)
4. Applies demand noise (`random.gauss` per demand node)
5. Applies supply allocation (`random.uniform` per origin)
6. **Moves to next scenario** — whose epicenters are now sampled with a shifted state

### The problem

Road disruption at step 3 consumes a number of `random.random()` calls equal to the number
of road edges (or node pairs) in the graph. The count differs across every generation of
the script:

| Version | Road graph method | Disruption calls per scenario |
|---|---|---|
| v1 / paper-submit (`d15cbc4`) | **Complete graph K_N** — full `n×(n-1)` double loop | **~17,292** |
| Delaunay intermediate (`fe6d42d`) | Delaunay triangulation, ~3N edges | **~396** |
| v2 / OSRM (`fa41c4b`) | OSRM-validated Delaunay candidates | **~4,029** |

**Correction to earlier analysis:** Delaunay was introduced in this branch (`feat/planar-dataset`)
at commit `fe6d42d`, *after* the v1 canonical data was already committed. The v1 data was
generated with the complete-graph K_N method (all pairs, no Delaunay). The agent previously
and incorrectly stated "v1 used Delaunay with ~7,448 edges" — this was wrong.

The K_N approach consumed 17,292 disruption calls per scenario before Severe's epicenters
were sampled. OSRM consumes 4,029. The difference of **~13,263 calls** per scenario causes
the random state to diverge entirely by Extreme, which is why v2 Extreme lands all three
epicenters in the western mountains.

v1 did not have good epicenters "by design" — the K_N loop happened to advance the random
state past a sequence that then landed on coastal nodes in Severe and Extreme. It was luck
preserved by never regenerating the data after the initial K_N run.

### Proposed fix

Hoist all epicenter sampling out of the scenario loop to happen **before any disruption
draws**. Epicenter positions and intensities are then passed into the loop as fixed inputs.

```python
# ── Hoisted epicenter sampling ──────────────────────────────────────────────
epi_weights = [aux_risk[i] ** 2 for i in epi_candidates]   # see Change 1
all_epicenters = []
for (name, prob, n_epi, I_lo, I_hi, sev_mult, beta, phi) in SCENARIO_DEFS:
    chosen = _weighted_sample(epi_candidates, epi_weights, n_epi)
    epis   = [
        (coords[epi_candidates[c]][0],
         coords[epi_candidates[c]][1],
         random.uniform(I_lo, I_hi))
        for c in chosen
    ]
    all_epicenters.append(epis)

# ── Main scenario loop ───────────────────────────────────────────────────────
for si, (name, prob, n_epi, I_lo, I_hi, sev_mult, beta, phi) in enumerate(SCENARIO_DEFS):
    epicenters = all_epicenters[si]   # use pre-sampled epicenters
    ...
```

### Effect on random state

After this change, the random state at the start of disruption draws is fully determined by:
- 100 `random.gauss` calls (base_pop)
- 100 `random.uniform` calls (area_km2)
- `sum(n_epi for each scenario)` sampling calls (1+2+3=6 for large)
- `sum(n_epi for each scenario)` intensity calls (same 6)

Road edge count no longer affects epicenter selection. Future re-runs with different road
graphs (e.g. v3 with corrected bridge weights) will produce identical epicenters.

### Risks

- This change means v2 epicenters will **not** match v1 epicenters exactly (v1's good
  coastal epicenters were an artefact of the K_N loop advancing the random state by ~17,292
  calls per scenario, which is not reproducible under OSRM's ~4,029 call count).
  This is acceptable — v2 should be self-consistent, not a reproduction of v1.
- The random state post-fix will differ from any previously generated v2 run. All v2
  solver results must be regenerated after this change (they are already infeasible).

### Validation

After regeneration, verify:
```python
for sc in v2['scenarios']:
    for epi in sc['epicenters']:
        assert epi['lon'] >= 107.8, f"Mountain epicenter in {sc['name']}: {epi}"
```
(107.8 is a loose check; the probabilistic model may allow occasional exceptions in Extreme.)

---

## Change 1 — Coastal-Biased Epicenter Sampling via Probabilistic Weight Sharpening

### Current behaviour

```python
epi_weights = [aux_risk[i] for i in demand_idx]
```

`aux_risk` already encodes coastal proximity (topo 25% + coastal 20% + delta 20%) but the
linear weights give a mountain node (aux_risk ≈ 0.10) roughly 1/5 the probability of a
coastal node (aux_risk ≈ 0.55). This is too permissive for Mild events.

### Geographic rationale

Central Vietnam typhoons make landfall exclusively on the coast. Flood RELIEF EPICENTERS
are primarily coastal/delta, but the Annamite chain causes orographic amplification that
creates secondary highland disaster zones (flash floods, landslides). The 2009 Ketsana
and 2020 compound floods both had significant highland components in A Lưới, Tây Giang,
Phước Sơn, and Trà My districts — approximately once every 5–10 years for highland-dominant
events, more frequently (every 2–3 years) for highland-contributing events.

A hard coastal cutoff would be geographically wrong. A probabilistic model with sharp
coastal bias and non-zero mountain probability is the honest representation.

### Proposed fix

Square the weights:

```python
epi_candidates = demand_idx   # full set — no hard cutoff
epi_weights    = [aux_risk[i] ** 2 for i in epi_candidates]
```

**Effect on probability ratios:**

| Node type | aux_risk (approx) | Linear weight | Squared weight |
|---|---|---|---|
| Coastal (Da Nang, Hội An) | 0.55 | 0.55 | 0.30 |
| Mid-valley (P'Rao, Thanh Mỹ) | 0.30 | 0.30 | 0.09 |
| Highland (Tây Giang, A Lưới) | 0.10 | 0.10 | 0.01 |
| Deep mountain (A Tức, Cao Ngạn) | 0.04 | 0.04 | 0.002 |

Coastal vs deep-mountain ratio: 150:1 (squared) vs 14:1 (linear).

**Approximate probability of ≥1 mountain epicenter (lon < 107.8) per scenario:**

| Scenario (n_epi) | Linear weights | Squared weights |
|---|---|---|
| Mild (1) | ~12% | ~2% |
| Severe (2) | ~22% | ~4% |
| Extreme (3) | ~31% | ~6% |

This gives the model a realistic but non-zero chance of demonstrating highland-epicenter
scenarios, consistent with the 2009/2020 historical record.

### Risks

- Squaring is a heuristic amplification; the exponent 2 is not derived from empirical
  typhoon track data. If future validation against historical Central Vietnam events shows
  coastal bias is too strong or too weak, the exponent is a single tuneable parameter.
- `aux_risk` values for the hub/origin nodes are not used for epicenter selection (only
  demand nodes are candidates), so this change has no indirect effects.

### Validation

After regeneration, for each scenario print epicenter coordinates and verify visually
that all or nearly all are in the coastal/lowland zone (lon ≥ 108.0). Accept occasional
mid-valley epicenter in Extreme as scientifically valid.

---

## Change 2 — Epicenter-Driven Demand (Replacing Risk-Driven Demand)

### Current behaviour

```python
r_is   = risk[i]                         # scenario risk for demand node i
frac   = 0.05 + 0.85 * r_is
d_val  = base_pop[i] * frac * sev_mult
```

`risk[i]` is computed as `r_min_i + (r_max_i - r_min_i) * raw_exp[i]`, where `r_min` and
`r_max` are determined by `aux_risk[i]`. This conflates two distinct concepts:

- **Intrinsic flood susceptibility** (how often this location floods historically) →
  correctly drives `r_min`, `r_max`, hub vulnerability, road disruption probability
- **Event-specific disaster impact** (how much of this particular storm reached this node) →
  should drive demand

A mountain commune (A Lưới, aux_risk ≈ 0.10) has a risk interval of approximately
[0.07, 0.22]. Even at maximum epicenter exposure (raw_exp = 1.0), its scenario risk is
capped at 0.22. Combined with base_pop ≈ 3,000, Mild demand = 3000 × (0.05 + 0.85×0.22)
× 1.0 ≈ 711 persons. This is too high when the epicenter is 200km away on the coast.

Meanwhile a coastal commune (aux_risk ≈ 0.55, interval [0.21, 0.83]) far from the
epicenter (raw_exp ≈ 0.05) has risk ≈ 0.25 and demand = 6000 × 0.26 × 1.0 ≈ 1,560 persons.
The coastal commune gets MORE demand than the mountain commune, but both receive implausibly
high demand given the epicenter is elsewhere.

### Proposed fix

Use `raw_exp[i]` — the pure epicenter exposure value — as the demand driver:

```python
# raw_exp[i] already computed above (Gaussian decay from epicenters)
# raw_exp[i] ∈ [0, 1]: 1.0 = at epicenter, ~0.0 = 300km away
frac  = 0.05 + 0.95 * raw_exp[i]        # 5% baseline for all nodes; scales to 100% at epicenter
noise = random.gauss(0, 0.06 * frac)    # slightly tighter noise (was 0.08 × d_base)
d_val = max(5.0, base_pop[i] * (frac + noise) * sev_mult)
```

**Semantic separation after this change:**

| Field | Driver | Meaning |
|---|---|---|
| `risk[u]` | `r_min + (r_max - r_min) × raw_exp[u]` | Infrastructure damage, hub vulnerability |
| `demand[i]` | `base_pop[i] × (0.05 + 0.95 × raw_exp[i])` | Relief need from this event |
| `accessibility[road]` | road disruption ∝ beta × `risk[u]` | Road operability |

**Concrete example — Mild scenario with coastal epicenter at (15.88, 108.40):**

| Node | lon | raw_exp | Old demand | New demand |
|---|---|---|---|---|
| Hội An City | 108.33 | ~0.85 | 2,380 | ~5,700 |
| Tây Giang District | 107.50 | ~0.02 | 1,040 | ~160 |
| A Tức Commune | 107.05 | ~0.005 | 850 | ~40 |

Mountain communes drop to 40–160 persons in Mild — a 5–20× reduction. Coastal communes
near the epicenter increase proportionally. This is the correct qualitative pattern.

### Base population note

`base_pop` is computed with a longitude-biased formula (`coast_f`) that already gives
coastal nodes ~2× the base population of mountain nodes. This is a crude approximation of
real population density (Da Nang: ~1.1M; A Lưới: ~48K). The formula is not changed in this
plan because modifying it would require validation against census data that is not available
to this agent. The existing formula combined with exposure-driven demand gives a defensible
result: mountain communes get ~1/20 the coastal demand in Mild, scaling up appropriately in
Extreme if an orographic epicenter is drawn.

### Risks

- `raw_exp[i]` can be ~0.30–0.50 for nodes near the edge of the Gaussian influence radius
  (EPI_SIGMA = 85km). A coastal node 120km from the epicenter gets `raw_exp ≈ 0.20`, giving
  demand = base_pop × 0.24. This is lower than before and may cause very small demands for
  coastal nodes on the periphery of the storm. The 5% baseline floor prevents zero demand.
- Hub capacity is calibrated to `max_demand_kg` across scenarios. Since demand values change,
  hub capacities will change proportionally. This is expected and correct — capacities should
  match the actual demand served.
- The `noise` term is reduced slightly (0.08 → 0.06 × frac) because the frac value itself
  is now smaller for most nodes, and the absolute noise would otherwise become negligible.
  This is a minor tuning choice, not a model change.

### Validation

After regeneration:
1. Mountain node demand in Mild should be < 300 persons for nodes with lon < 107.8
2. Total demand across all nodes in Mild should be comparable to v1 (within ±30%)
3. The ratio of max coastal demand to max mountain demand should be ≥ 10:1 in Mild

---

## Change 3 — Water Accessibility: River Corridor + Inundation Split Model

### Current behaviour

```python
# For each Delaunay edge (u, v):
water_ok = 1 if (risk[u] > 0.30 and risk[v] > 0.30) else 0
```

This produces:
- v1 Mild: 4,032 accessible pairs (too many — the 0.30 threshold is crossed by many nodes
  due to the Gaussian exposure spreading from the mountain epicenter)
- v2 Mild: 242 pairs (too few — the OSRM epicenter change shifted risk distribution)
- The threshold 0.30 is arbitrary with no physical justification

The deeper problem: this model says "water is only accessible when both nodes are at
significant flood risk." But rivers are ALWAYS navigable regardless of flood level — the
Thu Bồn, Vu Gia, Trường Giang, Trà Bồng, and Perfume River exist in all scenarios. The
current model can eliminate river corridor water access in Mild simply because node risks
happen to fall below 0.30.

### Physical interpretation (the two real cases)

**Case A — River corridor transport (static):**
Motorboats can navigate inland river channels regardless of flood severity. In Central
Vietnam, the Thu Bồn river is navigable from the coast to Thạnh Mỹ (~80km inland). The
Vu Gia is navigable to Đại Lộc. Coastal lagoons (Tam Giang, Cầu Hai) allow water transport
independent of flood depth. This does NOT require elevated flood risk — it is geography.

**Case B — Inundation-enabled transport (dynamic):**
When coastal plains flood above ~0.5m depth, motorboats can cross fields and streets
between nodes that are not river-adjacent. This requires HIGH flood conditions at both
nodes and should scale with scenario severity.

### Proposed fix

Pre-compute static river proximity (once, outside the scenario loop), then combine:

```python
# ── Pre-computed (outside scenario loop) ────────────────────────────────────
RIVER_CORRIDOR_KM = 15.0   # within 15km of a river centreline waypoint

def _river_proximity_km(lat, lon, rivers):
    """Min Haversine distance in km from (lat,lon) to any river waypoint."""
    min_d = float('inf')
    for waypoints in rivers.values():
        for rlat, rlon in waypoints:
            d = haversine(lat, lon, rlat, rlon)
            if d < min_d:
                min_d = d
    return min_d

river_prox = [_river_proximity_km(coords[u][0], coords[u][1], RIVERS)
              for u in range(n)]

# ── Inside scenario loop, replacing the old water rule ──────────────────────
INUNDATION_THRESH = 0.50   # requires significant flood depth at both endpoints

for (u, v) in _edges:
    river_ok   = river_prox[u] < RIVER_CORRIDOR_KM and river_prox[v] < RIVER_CORRIDOR_KM
    flood_ok   = risk[u] > INUNDATION_THRESH and risk[v] > INUNDATION_THRESH
    water_ok   = 1 if (river_ok or flood_ok) else 0
    a[1][u][v] = a[1][v][u] = water_ok
    a[2][u][v] = a[2][v][u] = 1
```

### Expected behaviour per scenario

| Scenario | River corridor nodes | Coastal plains | Highland non-river |
|---|---|---|---|
| Mild | water=1 (static) | mostly water=0 (risk < 0.50) | water=0 |
| Severe | water=1 (static) | partial water=1 (risk climbs) | water=0 |
| Extreme | water=1 (static) | mostly water=1 | water=0 (still low risk) |

The 15km corridor radius covers:
- Thu Bồn / Vu Gia system: nodes in Hội An, Điện Bàn, Đại Lộc, Thạnh Mỹ
- Perfume River: Huế city nodes
- Trường Giang: Tam Kỳ coastal strip
- Trà Bồng: northern Quảng Ngãi communities

The 0.50 inundation threshold is stricter than the current 0.30. At this level, only nodes
that have received substantial epicenter exposure AND have high intrinsic risk (coastal,
low-elevation) will qualify. This correctly restricts flood-induced water to genuine
inundation zones.

### Known limitation: temporal dynamics

The user correctly identified that flood LEVEL changes over time — rising during the event,
then receding. The current static scenario model cannot represent this. A node that is
water-accessible in hour 12 of a flood may not be in hour 48. This plan does not attempt
to model temporal dynamics; scenarios are snapshots at peak flood conditions. This is a
known limitation to be noted in the paper.

### Parameter sensitivity

The two thresholds are tuneable:
- `RIVER_CORRIDOR_KM = 15.0`: tighten to 10km to restrict to main channels; loosen to
  20km to include tributary valleys. 15km is chosen to capture the Thu Bồn basin width.
- `INUNDATION_THRESH = 0.50`: raising to 0.60 would restrict flood water to Extreme only;
  lowering to 0.40 would expand it into more of Severe. 0.50 corresponds roughly to the
  "both nodes are significantly flooded" interpretation.

### Risks

- River proximity computed from the existing `RIVERS` waypoints (7 rivers, ~25 waypoints).
  The waypoint coverage is coarse — some river-adjacent nodes may be misclassified as
  non-river if they are between waypoints. Increasing waypoint density would improve
  accuracy but is out of scope for this plan.
- Changing water accessibility changes the solver's feasible region. Some solutions that
  used water routes in v1 may become infeasible or need rerouting in v2. This is expected
  and correct — v2 should reflect more accurate network topology.

### Validation

After regeneration:
1. For Mild scenario: water-accessible pairs should be ~500–1,500 (river corridor alone).
   Far fewer than v1's 4,032 but far more than v2's current 242.
2. Spot-check: Da Nang (global 20) ↔ Hội An (global 0) should have water=1 in Mild
   (both near Thu Bồn / coastal lagoon system).
3. Spot-check: A Lưới (global 7) ↔ any hub should have water=0 in Mild (mountain,
   no river corridor, low risk).

---

## Implementation Order and Dependencies

```
Change 0 (random isolation) ──┐
Change 1 (epi weights)        ├──► regenerate v2 large + small
Change 2 (demand model)       │        ↓
Change 3 (water model)    ────┘   validate JSON
                                       ↓
                               commit data (JSON only)
                                       ↓
                               run solver (separate task)
```

Changes 0–3 are all in `generate_scenarios()` and the main `build()` function. They should
be implemented together in a single code edit to avoid partial-state intermediate runs.

---

## What This Plan Does NOT Address

The following issues were discussed but are explicitly out of scope for this rebuild:

1. **`base_pop` longitude bias**: The formula `pop_base = 500 + 6500 * coast_f` is a crude
   population proxy. A proper fix requires census data by commune. Noted as limitation.

2. **Temporal flood dynamics**: Scenarios are peak-flood snapshots. Dynamic flood rise/fall
   is not modelled. Noted as limitation.

3. **Dynamic node roles** (low-risk nodes as origins): Requires model restructuring at the
   C++ solver level. Out of scope; noted as future work.

4. **Ly Son island road connectivity**: v1 data bug (Delaunay sea crossing). OSRM already
   fixes this in v2's road graph. No separate action needed.

5. **CV Small dataset**: The same four changes apply to CV Small. The implementation will
   run `build("small")` immediately after `build("large")` using the same modified script.

---

## Honest Uncertainties

This agent is not a domain expert in Central Vietnam hydrology or typhoon meteorology. The
following claims rest on general geographic knowledge and cited historical events, not on
peer-reviewed hydrological modelling:

- The `aux_risk**2` exponent is a heuristic. The value 2 is not derived from empirical
  typhoon track frequency data for Central Vietnam.
- The `EPI_SIGMA = 85km` influence radius is inherited from the existing design; it has not
  been validated against observed flood extent maps.
- The `RIVER_CORRIDOR_KM = 15.0` threshold is a reasonable estimate for the Thu Bồn basin
  width but has not been verified against actual navigability data.
- The `INUNDATION_THRESH = 0.50` is physically motivated but not calibrated to actual flood
  depth data.

These uncertainties should be disclosed in any paper section that describes the data
generation methodology.
