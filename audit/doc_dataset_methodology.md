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

**Sea-lane override for Ly Son:** after the main water-accessibility model runs, every node within `MAX_EDGE_KM = 80km` of the island gets `a[1][island][v] = 1` (water) and `a[2][island][v] = 1` (air) unconditionally, regardless of flood model outcome. Air is included because helicopter access from an island is physically feasible in all scenarios.

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

Epicenters drawn without replacement from demand nodes. Initial sampling weights:

```
weight[i] = aux_risk[i]² × exp(−d_coast[i] / EPI_COAST_SIGMA)
```

`EPI_COAST_SIGMA = 30 km`. The exponential factor strongly biases toward coastal nodes; squaring `aux_risk` further penalises mountain nodes. High-aux_risk river-valley nodes (e.g. Đông Giang District, ~50km from coast) retain non-negligible weight due to their flood-prone character.

**Within-scenario spatial repulsion:** After each epicenter is drawn, weights of all remaining candidates are decayed by distance to the chosen epicenter:

```
weight[i] *= 1 − exp(−d(i, last_epicenter) / REPULSION_SIGMA)
```

`REPULSION_SIGMA = 30 km`. Nearby candidates (d ≈ 5 km) are suppressed to ~15% of their original weight; candidates at 100 km retain ~96%. This prevents epicenters within a single scenario from clustering in one locality — they spread naturally across the region.

**Between-scenario independence:** Each scenario's draws start from a fresh `random.seed(EPI_BASE_SEED + (si+1)×100)`, so Mild, Severe, and Extreme epicenters are independently sampled.

**Random isolation:** `random.seed(SEED)` / `random.seed(SEED+1)` is called at the very top of `build_instance()` before any scenario draws. Road graph changes do not shift epicenter selection.

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

**CV Large v2 totals (kg):** Mild ≈ 340k, Severe ≈ 2,630k, Extreme ≈ 4,325k.

---

## Hub Capacity κ_k

Hub capacities represent the maximum pre-positioned stock at hub k (kg). They are expressed as multipliers of `per_hub_base = max_demand / n_H`, so the scale stays consistent with actual scenario demand regardless of parameter changes.

### Tier system

Each hub is assigned to one of five tiers based on its name/role:

| Tier | Description | Multiplier range | CV Large capacity range |
|---|---|---|---|
| 1 | Major port / airport / logistics node | 0.9 – 1.5 × base | 195k – 325k kg |
| 2 | Provincial city depot or warehouse | 0.7 – 1.1 × base | 152k – 238k kg |
| 3 | District staging area; road-accessible | 0.5 – 0.9 × base | 108k – 195k kg |
| 4 | Mountain forward base or rescue station | 0.4 – 0.7 × base | 87k – 152k kg |
| 5 | Remote helipad / deep-mountain outpost | 0.3 – 0.5 × base | 65k – 108k kg |

Max/min endpoint ratio = 1.5 / 0.3 = **5×**.

### CV Large tier assignments

| Tier | Hubs |
|---|---|
| 1 | Da_Nang_Airport_Hub, Quang_Ngai_Port_Hub, Tam_Ky_Logistics_Hub |
| 2 | Quang_Ngai_Depot, Binh_Son_Warehouse, Son_Ha_Hub, Nui_Thanh_Reserve |
| 3 | Phu_Loc_Staging_Area, Que_Son_Facility, Lang_Co_Forward_Post, Thang_Binh_Depot, Bac_Tra_My_Depot |
| 4 | A_Luoi_Relief_Center, Dong_Giang_Rescue_Stn, Nam_Giang_Forward_Base, Phuoc_Son_Helipad |
| 5 | A_Dot_Mountain_Base, A_Sap_Helipad, Rao_Trang_Base, Huong_Viet_Depot |

### Design rationale

Total kappa across all 20 hubs ≈ **0.73× max_demand** (sub-unity by design). Individual hub deficits are covered by origin supply nodes and hub-to-hub transshipment flows in the MCF balancer (Step 6 of the decoder). The kappa constraint is a *pre-positioning storage limit*, not a throughput ceiling — goods can be relayed through a hub without consuming capacity.

`terrain_factor` (coastal 1.0 → mountain 1.77) is applied to `hub_fixed_cost` and `hub_hold_cost` (mountain operations are more expensive) but deliberately **not** to capacity (mountain hubs are physically smaller, not larger).

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
| Total hub kappa | 3,145k kg (~0.73× max_demand) |

| Scenario | Mild | Severe | Extreme |
|---|---|---|---|
| n_epicenters | 1 | 2 | 3 |
| Total demand (kg) | 340k | 2,630k | 4,325k |
| Total supply (kg) | 875k | 5,236k | 6,895k |
| risk_mean (demand nodes) | 0.214 | 0.497 | 0.519 |
| Road survival | ≈92% | ≈35% | ≈14% |

**Solver results (seed 0, pop 200, gen 500):** 12 Pareto solutions, Feas=143/200 (71.5%).
Z1 range 38.5M–92.2M, Z2 range 91.4k–111.3k, CV=0 for all.

*Z1 is larger than v1 (~12–16M) for two structural reasons: (1) Delaunay multi-hop
Dijkstra paths accumulate more transport cost than K_n direct pairs; (2) total kappa
(0.73× max_demand) requires the MCF to route significant hub-to-hub transshipment,
adding inter-hub transfer cost.*

---

## Known Limitations

| Issue | Notes |
|---|---|
| `EPI_SIGMA = 85 km` | Not empirically calibrated; inherited from initial design; not validated against historical flood extent maps |
| `EPI_COAST_SIGMA = 30 km` | Heuristic; not derived from typhoon track frequency data for Central Vietnam |
| `RIVER_CORRIDOR_KM = 15 km` | Approximate for Thu Bồn basin; some river-adjacent nodes may be mis-classified if between waypoints |
| `INUNDATION_THRESH = 0.40` | Originally 0.50 (physically motivated); lowered to 0.40 for feasibility — 0.50 left ~25 road-isolated demand nodes in Extreme, exceeding the helicopter cap unconditionally |
| `base_pop` formula | `500 + 6500 × coast_f` is a crude proxy; real commune-level census data was not available |
| Temporal dynamics | Scenarios are peak-flood snapshots; flood rise/fall not modelled |
| Inland epicenter draws | High-aux_risk river-valley nodes (e.g., Đông Giang, ~50km inland) can be drawn as Extreme epicenters due to their inherently high flood susceptibility despite coastal decay |
| Delaunay topology | Without OSRM validation, some Delaunay edges may still follow unrealistic routes (known cases excluded via `_FORBIDDEN_ROAD_PAIRS`; others may exist) |
| BFS asymmetry | If two nodes share a direct Delaunay edge that is blocked in a scenario, BFS will NOT restore reachability between them via an alternative multi-hop route, because `_all_direct` guards all pairs with any direct edge from BFS updates. Pairs without a direct edge correctly get multi-hop reachability via BFS. Having a direct edge is therefore strictly worse than not having one when that edge is blocked. This is a known modeling limitation — paper should note it. |
| Island C_time / accessibility split | Sea-lane override in `generate_scenarios` sets `a[1/2]=1` for island nodes, but `build_transport` Dijkstra overwrites water `C_time` to BIG_M for the same pairs (island excluded from `geo_edges`). Fix applied: haversine water costs are restored for island nodes post-Dijkstra. Without this fix, postprocessor assigns road mode via fallback despite correct accessibility. |

---

## Dataset Version History

Two versions exist. Neither uses OSRM validation.

| Aspect | v1 — canonical | v2 — planar |
|---|---|---|
| File location | `data/cv/v1/` | `data/cv/v2/` |
| Road graph | **Complete graph K_n** — all 8,646 unique pairs have finite C_time; 100% pairs accessible | **Pure Delaunay** — ~342 edges after exclusions; non-adjacent pairs have BIG_M road time |
| Road in UI | Delaunay is a **UI rendering layer only** (`_delaunay_edges(coords)` fallback in `dataset_view.py`); underlying data remains K_n | Pure Delaunay IS the actual graph model (`road_edges` field stored in JSON) |
| Epicenter weights | `aux_risk` (linear) | `aux_risk² × exp(−d_coast/30km)` with within-scenario spatial repulsion (`REPULSION_SIGMA = 30 km`) |
| Demand driver | `risk[i]` (conflates intrinsic + event) | `raw_exp[i]` (event exposure only) |
| Road disruption | `p = min(0.97, beta × avg_risk)` | complementary-power with ALPHA_EPI |
| Water model | single risk threshold 0.30 | river corridor OR inundation 0.40 |
| Hub capacity | `uniform(3, 6) × (max_demand/n_H) × terrain_factor` — mountain hubs over-sized | tier-based multipliers × `(max_demand/n_H)`; 5× max/min spread; total ≈ 0.73× max_demand; terrain_factor on cost only |
| Script | pre-PR `data_generate_cv.py` (K_n loop) | `src/scripts/data_generate_cv.py` |
| Solver status | **Solved** — `results/exp2/CV_large_seed0.json` | **Solved** — `results/exp2/v2/CV_large_seed0.json` |

**Critical note on v1 hub assignments in the UI:**
Because v1 uses K_n (every hub-demand pair has a direct finite road time), hub selection is based on minimum C_time, not road topology. Assignments can appear geographically inconsistent — a distant hub may have lower C_time than a nearby hub due to haversine × tortuosity. The Delaunay edges drawn in the UI are a cosmetic rendering fallback only and do NOT represent the connectivity model. The colored lines on the Solution Explorer map show demand-to-hub **assignments**, not routing paths — routing is not part of the optimization model.

**v1 canonical solver results remain immutable ground truth.** v2 is the instance set validated for paper reporting.
