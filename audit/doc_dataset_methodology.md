# Dataset Generation Methodology — v2 CV Dataset

**Status:** IMPLEMENTED  
**Script:** `src/scripts/data_generate_cv.py`  
**Outputs:** `data/cv/v2/cv_large_drnd.json`, `data/cv/v2/cv_small_drnd.json`  
**Seed:** `SEED = 2026` (small: `seed(2026)`, large: `seed(2027)`)

---

## Node Set

| Type | CV Large | CV Small | Role |
|---|---|---|---|
| Demand (I) | 100 | 20 | Communes, wards, districts requiring relief |
| Hub (H) | 20 | 5 | Pre-positioned logistics hubs |
| Supply origin (J) | 12 | 2 | Depots, ports, airfields |
| **Total** | **132** | **27** | |

Node coordinates are curated from geographic references and fixed — they do not vary across scenarios or versions.

---

## Road Graph

**Method:** Delaunay triangulation on all 132 node coordinates, filtered to edges ≤ 80 km (haversine), minus two exclusion sets.

| Exclusion | Removed | Reason |
|---|---|---|
| `_ISLAND_NODES` | `Ly_Son_Island_Supply` | No road bridge; sea crossing |
| `_FORBIDDEN_ROAD_PAIRS` | `Tho_Quang_Ward ↔ Hai_Van_Pass_North` | Crosses Da Nang Bay (midpoint over open water) |
| | `Son_Tra_District ↔ Hai_Van_Pass_North` | Crosses Da Nang Bay (midpoint over open water) |

**CV Large:** 330 edges after exclusions. **CV Small:** 65 edges.

Road costs use `ROAD_TORTUOSITY = 1.35 × haversine` with per-edge terrain factor. Non-adjacent node pairs get costs via Dijkstra shortest-path through the road graph.

**Sea-lane override for Ly Son:** after the main water-accessibility model runs, every node within `MAX_EDGE_KM = 80km` of the island gets `a[1][island][v] = 1` unconditionally, regardless of flood model outcome.

---

## Auxiliary Risk r^a_u

Static, intrinsic per-node flood susceptibility. Blended from three criteria with equal weights:

| Criterion | Description | Parameters |
|---|---|---|
| C1 Coastal inundation | Gaussian decay from coastline + low-elevation proxy | `COASTAL_SIGMA = 40 km` |
| C2 River hydrology | Gaussian decay from 7 river system waypoints | `RIVER_SIGMA = 18 km` |
| C3 Delta accumulation | Gaussian decay from 5 major delta centers | per-center sigma |

Range [0, 1]: mountain communes ≈ 0.02–0.15; coastal lowland ≈ 0.60–0.89.

Risk interval per node: `r_min = 0.05 + 0.20 × r^a`, `r_max = r^a + 0.15 × (1 − r^a)`.

---

## Coastline Reference Polyline

12 waypoints (N→S), used to compute `_coast_proximity_km(lat, lon)` for epicenter sampling weights. Corrected to verified coastal positions:

```python
COASTLINE = [
    (17.02, 107.10),  # Cửa Tùng, Quảng Trị
    (16.55, 107.64),  # Cửa Thuận An, Huế
    (16.25, 108.03),  # Lăng Cô bay
    (16.19, 108.13),  # Hải Vân pass
    (16.11, 108.26),  # Đà Nẵng Tiên Sa / Sơn Trà
    (15.88, 108.38),  # Cửa Đại, Hội An
    (15.75, 108.45),  # Bình Dương coast (Thăng Bình)
    (15.57, 108.50),  # Tam Thanh coast, Tam Kỳ
    (15.48, 108.68),  # Cửa Kỳ Hà, Núi Thành
    (15.35, 108.82),  # Dung Quất bay
    (15.22, 108.93),  # Sa Kỳ port
    (14.67, 109.06),  # Sa Huỳnh
]
```

---

## Scenario Definitions

| Scenario | Prob | n_epi | Intensity [I_lo, I_hi] | sev_mult | beta_road | phi |
|---|---|---|---|---|---|---|
| Mild | 0.60 | 1 | [0.30, 0.60] | 1.0× | 0.20 | 0.57 |
| Severe | 0.30 | 2 | [0.55, 0.85] | 1.8× | 0.80 | 0.70 |
| Extreme | 0.10 | 3 | [0.75, 1.00] | 2.8× | 1.20 | 0.85 |

---

## Epicenter Sampling

Epicenters drawn without replacement from all 100 demand nodes. Sampling weights:

```
weight[i] = aux_risk[i]² × exp(−d_coast[i] / EPI_COAST_SIGMA)
```

`EPI_COAST_SIGMA = 30 km`. The exponential factor strongly biases toward coastal nodes; squaring `aux_risk` further penalises mountain nodes. High-aux_risk river-valley nodes (e.g. Đông Giang District, ~50km from coast) retain non-negligible weight due to their flood-prone character.

**Random isolation:** `random.seed(SEED)` / `random.seed(SEED+1)` is called at the very top of `build_instance()` before any scenario draws. Road graph changes (different edge counts, future topology revisions) do not shift epicenter selection.

---

## Scenario Risk r_{us}

For scenario s and node u:

```
raw_exp[u] = min(1.0,  Σ_i  intensity_i × gauss(dist(u, epicenter_i),  EPI_SIGMA=85km))
risk[u]    = r_min_u + (r_max_u − r_min_u) × raw_exp[u]
```

`risk[u]` represents combined infrastructure damage and hub vulnerability for this event. It drives road disruption and the hub-risk filter (χ threshold). It does **not** drive demand.

**Note on visual interpretation:** `risk[u]` in Mild will appear lower than Extreme for most nodes (mean 0.26 vs 0.50 in CV Large), but individual nodes near the Mild epicenter may locally exceed their Extreme values because the Mild epicenter happens to coincide with that node's location. The colormap contrast (vivid greens for low-risk nodes in Mild) can make Mild appear visually bold even though aggregate risk is lower.

---

## Demand D_{is}

Driven by epicenter exposure, not scenario risk. This decouples "how hard was this node hit by the event" (demand) from "how intrinsically flood-prone is this node" (risk).

```
frac   = 0.05 + 0.95 × raw_exp[i]           # 5% baseline floor
d_val  = max(5,  base_pop[i] × frac × sev_mult  +  gauss(0, 0.06 × frac))
```

Demand is stored per-node as persons; converted to kg in reporting via `GAMMA = 3.0 kg/person`.

**CV Large v2 totals (kg):** Mild ≈ 652k, Severe ≈ 2,354k, Extreme ≈ 4,349k.

---

## Road Disruption

Complementary-power formula separating epicenter exposure (event signal) from intrinsic fragility (node property):

```
score  = ALPHA_EPI × avg_raw_exp(u,v) + (1 − ALPHA_EPI) × avg_aux_risk(u,v)
p_road = 1 − (1 − score)^beta
```

`ALPHA_EPI = 0.7`. Each road edge is independently Bernoulli-sampled; `a[0][u][v] = 0` if disrupted.

**CV Large v2 road survival:** Mild ≈ 92% (304/330 edges), Severe ≈ 35%, Extreme ≈ 14%.

---

## Water Accessibility

Either condition alone grants water access for an edge `(u, v)`:

1. **River corridor (static):** both `u` and `v` within `RIVER_CORRIDOR_KM = 15 km` of any river waypoint in `RIVERS` (7 systems: Perfume, Thu Bồn, Vu Gia, Trường Giang, Trà Bồng, and others).
2. **Flood inundation (dynamic):** `risk[u] > 0.40` AND `risk[v] > 0.40`.

The static river corridor is scenario-independent (Thu Bồn, Perfume River exist regardless of flood level). The inundation channel activates only in severe/extreme conditions on coastal plains.

**Threshold rationale:** 0.40 (rather than 0.50) is used because Extreme beta_road=1.20 disrupts ~86% of road edges, leaving ~25 demand nodes per scenario road-isolated. With the per-scenario helicopter cap at ≈16 links (15% × 100 + 1), 25 mandatory air links exceeds the cap unconditionally. Threshold 0.40 reduces air-only nodes to ≈9 in Extreme, keeping the instance feasible.

---

## Air Accessibility

`a[2][u][v] = 1` for all edges in `geo_edges` (Delaunay ≤ 80 km + collocated stitch). Not scenario-dependent. Helicopter/light-aircraft routes follow the same geometry graph as water but are always available.

**geo_edges vs road_edges:** The road graph excludes two bay-crossing Delaunay edges (`_FORBIDDEN_ROAD_PAIRS`) but these remain in `geo_edges` (water/air have no bay constraint). The collocated stitch edges (12 demand/hub pairs at identical coordinates) are included in both road and geo graphs so that collocated demand nodes are accessible by all three modes.

---

## CV Large v2 Summary

| Field | Value |
|---|---|
| Road edges (Delaunay after exclusions) | 330 |
| + Collocated stitch | 12 |
| = Total road_edges | 342 |

| Scenario | Mild | Severe | Extreme |
|---|---|---|---|
| Road survival | ≈89% | ≈30% | ≈19% |
| Total demand (kg) | 545k | 2,551k | 4,101k |
| risk_mean (demand nodes) | 0.256 | 0.484 | 0.487 |
| n_epicenters | 1 | 2 | 3 |
| Air-only demand nodes | 0 | 4 | 9 |

**Solver results (seed 0, pop 200, gen 500):** 5 Pareto solutions, Feas=159/200.
Z1 range 12.8M–13.0M, Z2 range 79.6k–94.1k, CV=0 for all.

---

## Known Limitations

| Issue | Notes |
|---|---|
| `EPI_SIGMA = 85 km` | Not empirically calibrated; inherited from initial design; not validated against historical flood extent maps |
| `EPI_COAST_SIGMA = 30 km` | Heuristic; not derived from typhoon track frequency data for Central Vietnam |
| `RIVER_CORRIDOR_KM = 15 km` | Approximate for Thu Bồn basin; some river-adjacent nodes may be mis-classified if between waypoints |
| `INUNDATION_THRESH = 0.50` | Physically motivated (significant inundation depth) but not calibrated to flood depth data |
| `base_pop` formula | `500 + 6500 × coast_f` is a crude proxy; real commune-level census data was not available |
| Temporal dynamics | Scenarios are peak-flood snapshots; flood rise/fall not modelled |
| Inland epicenter draws | High-aux_risk river-valley nodes (e.g., Đông Giang, ~50km inland) can be drawn as Extreme epicenters due to their inherently high flood susceptibility despite coastal decay |
| Delaunay topology | Without OSRM validation, some Delaunay edges may still follow unrealistic routes (known cases excluded via `_FORBIDDEN_ROAD_PAIRS`; others may exist) |

---

## Relationship to v1

| Aspect | v1 | v2 |
|---|---|---|
| Road graph | Complete graph K_n (all pairs) → OSRM-validated Delaunay | Pure Delaunay triangulation, island/bay-crossing exclusions |
| Epicenter weights | `aux_risk` (linear) | `aux_risk² × exp(−d_coast/30km)` |
| Demand driver | `risk[i]` (conflates intrinsic + event) | `raw_exp[i]` (event exposure only) |
| Road disruption | `p = min(0.97, beta × avg_risk)` | complementary-power with ALPHA_EPI |
| Water model | single risk threshold 0.30 | river corridor OR inundation 0.50 |
| Random seeding | Per-scenario seed shift via K_n loop | Isolated seed at `build_instance()` start |

v1 canonical solver results remain immutable ground truth. v2 is the instance set for which new solver runs are performed.
