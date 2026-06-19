# Implementation Summary for IEEE Manuscript

---

## Part I: Dataset Synthesis Methodology (`src/scripts/data_generate_cv.py`)

### 1.1 Geographic Node Selection

The Central Vietnam case study (dataset identifier `cv_large_drnd.json`) comprises **132 geographically-verified nodes** in four provinces: Đà Nẵng, Quảng Nam, Thừa Thiên-Huế, and Quảng Ngãi. Nodes are partitioned into three disjoint sets:

| Set | Symbol | Count | Selection Rationale |
|---|---|---|---|
| Demand zones | I | 100 | Administrative districts/communes; manually curated to avoid water bodies (reservoirs, lagoons, sea) with coordinate-level corrections documented per node |
| Hub candidates | H | 20 | Elevated logistics facilities: airports, rescue stations, depots with road/air access |
| Supply origins | J | 12 | External logistics entry points: seaports, military airports, border crossings |

A reduced instance (`cv_small_drnd.json`) uses I=20, H=5, J=2 (first 20/5/2 from each pool). All coordinates were individually verified against OpenStreetMap to remove nodes placed inside reservoirs (e.g., Truoi Reservoir), lagoons (Tam Giang, Lang Co, Cau Hai), and the South China Sea. Fixes are documented inline in the source.

### 1.2 Multi-Criteria Auxiliary Risk Score $r^a_u$

Each node receives a static, intrinsic flood risk score $r^a_u \in [0,1]$ computed as a weighted linear combination of four geophysical criteria (following Barzinpour & Esmaeili, 2014):

$$r^a_u = 0.25 \cdot C_1 + 0.35 \cdot C_2 + 0.20 \cdot C_3 + 0.20 \cdot C_4$$

| Criterion | Formula | Physical meaning |
|---|---|---|
| $C_1$ — Topographic | $\left(\frac{\text{lon}_u - 107.0}{108.8 - 107.0}\right)^{0.65}$ | Inundation risk from low elevation; convex-coastal weighting |
| $C_2$ — Hydrological | $\max_{r \in \mathcal{R}, w \in r} \exp\!\left(-d(u,w)^2 / 2\sigma_h^2\right)$, $\sigma_h=18$ km | Proximity to Vu Gia, Thu Bồn, Perfume, Trường Giang, Trà Bồng rivers (waypoint polylines) |
| $C_3$ — Coastal | $\exp\!\left(-d_\text{coast}^2 / 2\sigma_c^2\right)$, $\sigma_c=40$ km | Storm-surge/coastal inundation exposure via longitude proxy |
| $C_4$ — Delta | $\max_{p \in \mathcal{P}} \exp\!\left(-d(u,p)^2 / 2\sigma_p^2\right)$ | Proximity to 5 river-delta accumulation centres (Thu Bồn/Hội An, Perfume/Huế, Tam Kỳ, Quảng Ngãi, Sơn Tịnh) with individual $\sigma_p \in \{14,16,18,22,28\}$ km |

Each node $u$ also receives a **risk interval** $[r_{\min,u},\, r_{\max,u}]$ with width proportional to $r^a_u$:
$$r_{\min,u} = 0.05 + 0.20 \cdot r^a_u \qquad r_{\max,u} = r^a_u + 0.15 \cdot (1 - r^a_u)$$

This encodes epistemic uncertainty: safe highland nodes (e.g., $r^a_u=0.10$) have a narrow band $[0.07, 0.22]$; flood-prone coastal nodes (e.g., $r^a_u=0.80$) have a wide band $[0.21, 0.83]$.

### 1.3 Baseline Road Network Topology: OSRM API Validation

The road network graph $\mathcal{G}_r = (\mathcal{N}, \mathcal{E}_r)$ is constructed in two stages:

**Stage 1 — Delaunay candidate generation.** A Delaunay triangulation is computed over all 132 node coordinates (via `scipy.spatial.Delaunay`). All edges exceeding $\delta_{\max}=80$ km (Haversine) are pruned, yielding a set of geometrically plausible candidate road pairs.

**Stage 2 — OSRM validation.** Each candidate edge $(u,v)$ is queried against the **OSRM public routing API** (`router.project-osrm.org`, driving profile) with a 120 ms inter-request polite delay. An edge is accepted into $\mathcal{E}_r$ only if:
1. OSRM returns a valid route (excludes island nodes or water-barrier crossings),
2. The detour ratio $\rho = d_{\text{OSRM}} / d_{\text{hav}} \in [0.9,\; 1.8]$ (ratio $<0.9$ rejects ferry shortcuts; $>1.8$ rejects excessively winding paths), and
3. The OSRM road distance $d_{\text{OSRM}} \leq 80$ km.

Results are cached to `data/cache/osrm_road_graph_{size}.json` so subsequent runs are instantaneous. The validated graph replaces the prior heuristic that relied solely on Delaunay distance thresholds.

**Transport cost/time matrices.** Three transport modes are modeled:

| Mode | Speed | Cost/km | Vehicle cap |
|---|---|---|---|
| Road ($m=0$) | 35 km/h | \$2.0/km | 60 units |
| Water/boat ($m=1$) | 25 km/h | \$5.0/km | 25 units |
| Air/helicopter ($m=2$) | 150 km/h | \$40.0/km | 10 units |

For **direct road edges** $(u,v) \in \mathcal{E}_r$, the cost is set from the OSRM-reported distance with a mild terrain adjustment: $c_{uv}^{(0)} = d_{\text{OSRM}} \cdot (1 + 0.05(\tau - 1))$, where $\tau \in [1.0, 1.8]$ is a terrain multiplier that scales with the node's distance from the 108.8°E coastline to the 107.0°E western highland boundary. For non-adjacent pairs, costs are propagated via **Dijkstra shortest-path** through the validated road graph. Water and air costs use Haversine distance throughout (with 1.15× and 1.0× multipliers, respectively), and non-adjacent pairs also use Dijkstra through the Delaunay geometry graph.

### 1.4 Flood Scenario Simulation: Three-Level Disruption Model

Three scenarios are defined with fixed probabilities: Mild ($p=0.60$), Severe ($p=0.30$), Extreme ($p=0.10$), following the structure of Noyan et al. (2016).

**Epicenter sampling.** For scenario $s$, $n_s^{\text{epi}} \in \{1,2,3\}$ epicenter locations are sampled **without replacement** from demand nodes, weighted proportionally by $r^a_u$. Each epicenter is assigned a random intensity $I_e \sim \mathcal{U}(I_{\text{lo}}, I_{\text{hi}})$:

| Scenario | $n_\text{epi}$ | $I_{\text{lo}}$ | $I_{\text{hi}}$ |
|---|---|---|---|
| Mild | 1 | 0.30 | 0.60 |
| Severe | 2 | 0.55 | 0.85 |
| Extreme | 3 | 0.75 | 1.00 |

**Scenario risk $r_{us}$.** Each node $u$ receives a raw exposure $e_u = \min(1, \sum_e I_e \cdot \exp(-d(u,e)^2/2\sigma^2))$ using $\sigma=85$ km. The scenario risk is then:
$$r_{us} = r_{\min,u} + (r_{\max,u} - r_{\min,u}) \cdot e_u + \epsilon, \quad \epsilon \sim \mathcal{N}(0, 0.025^2)$$
clipped to $[0.01, 0.99]$.

**Multi-modal accessibility tensor** $a_s[m][u][v] \in \{0,1\}$. This is the core disruption representation. It is populated in two stages:

*Stage 1 — Direct edges:*
- **Road ($m=0$):** For each OSRM-validated edge $(u,v) \in \mathcal{E}_r$, the edge is disrupted with probability $p_{\text{block}} = \min(0.97,\, \beta_s \cdot \bar{r}_{uv})$, where $\bar{r}_{uv} = (r_{us}+r_{vs})/2$ is the mean endpoint risk, and $\beta_s \in \{0.25, 0.55, 0.88\}$ is the scenario disruption intensity.
- **Water ($m=1$):** Delaunay edges are accessible iff *both* endpoints have $r_{us} > 0.30$ (high-flood zones activate water transport).
- **Air ($m=2$):** All Delaunay edges are accessible ($a_s[2][u][v]=1$ always).

*Stage 2 — BFS path-reachability:* A BFS is run from every source node through the accessible direct edges of each mode, extending reachability to non-adjacent node pairs. Critically, BFS writes only to non-direct pairs, preserving the direct-edge values (blocked direct edges stay 0 in the JSON, which the visualizer uses to color disrupted arcs).

**Demand and supply.** Per-scenario demand is $D_{is} = \max(5, \text{pop}_i \cdot (0.05 + 0.85 \cdot r_{is}) \cdot \nu_s + \epsilon)$, where $\nu_s \in \{1.0, 1.8, 2.8\}$ is the scenario severity multiplier. Total supply is set generously at $1.8$–$2.5\times$ total demand in relief weight (at $\gamma=3$ kg/person), distributed across origins with a $\pm30\%$ random perturbation.

**Daganzo last-mile cost $\Theta_{k,i,s}$.** A pre-computed matrix uses the Continuous Approximation (CA) formula (Daganzo, 1984):
$$\Theta_{k,i,s} = \min_{m : a_s[m][k][i]=1} \left( 2 C^{(m)}_{ki} \cdot \left\lceil D_{is}/Q_m \right\rceil + c_{\text{loc}} \cdot \varphi_s \cdot \sqrt{\left\lceil D_{is}/\eta \right\rceil \cdot A_i} \right)$$
where $\varphi_s \in \{0.57, 0.70, 0.85\}$ is the scenario-specific circuity, $\eta=5$ persons/stop, $c_{\text{loc}}=\$2.5$/km, and $A_i$ is the demand zone area (km²). The deprivation sensitivity $\lambda_{is} = \lambda_0 (1 + r_{is})$ with $\lambda_0=0.8$.

---

## Part II: Geospatial DSS Architecture (`visualizer/`)

### 2.1 Software Architecture Pipeline

The DSS follows a **two-phase offline/online pipeline**:

```
OFFLINE (preprocess_flows.py)
─────────────────────────────
Solver output JSON  →  For each Pareto solution:
  1. Derive y_ks (reactive hub activation):
       hub activated iff X[k]=1 AND hub_risk[k] < 0.6
  2. Derive demand→hub assignments:
       Nearest accessible hub using A-vector preferred mode,
       falling back through modes [preferred, air, water, road]
  3. Derive origin→hub assignments:
       Nearest accessible hub across modes
  4. Compute inventory_held[k] = capacity[k] × R[k]
  →  Save  results/exp2/flows/solution_{idx}.json

ONLINE (Streamlit app.py, rendered on user request)
─────────────────────────────────────────────────────
@st.cache_data loads:
  - SolverResult    (pareto_front, all_feasible)
  - NodeInfo        (coords, names, index sets)
  - Instance JSON   (scenarios, accessibility, graph)

Tab 1 – Solution Explorer:
  Pareto scatter (Plotly) → click event → session_state["selected_idx"]
  → build_map() (Folium) → st_folium() render

Tab 2 – Input Dataset Explorer:
  Layer checkboxes → Streamlit re-run → build_dataset_map() (Folium) → st_folium()
```

The offline phase decodes **min-cost flow routing** (greedy heuristic) once per Pareto solution and serializes it. This separates the $O(|I| \cdot |H|)$ assignment computation from the interactive render loop, keeping UI response times sub-second.

### 2.2 Interactive Mapping — Folium Layer Architecture

All maps are `folium.Map` objects (OpenStreetMap tiles, `zoom_start=9`) embedded via `streamlit-folium`'s `st_folium()` with `returned_objects=[]` (no click callbacks from map—selection is driven entirely through Plotly).

**Node markers** use custom `folium.DivIcon` objects rendered as raw HTML/CSS, not image icons:
- **Open hubs:** 18×18 px orange diamond (`transform:rotate(45deg)`) with a brown border
- **Closed/inactive hubs:** 12×12 px grey diamond
- **Supply origins:** CSS-only triangle (zero-width/height borders technique: `border-left: 9px solid transparent; border-bottom: 16px solid #43A047`)
- **Demand nodes:** `folium.CircleMarker` with `fill_color` keyed to transport mode (#E53935 road / #039BE5 water / #7CB342 air); inaccessible nodes rendered at 50% opacity in #EF5350 red

**Edge rendering** uses `folium.PolyLine` with mode-specific dash patterns: road = solid, water = `dash_array="8 4"`, air = `dash_array="2 4"`. **Transshipment flow lines** use a variable `weight = 2 + 5 × (flow / max_flow)` to encode flow volume visually.

**Dataset view** (`build_dataset_map`) draws two distinct edge sets:
- **Road:** reads the OSRM-validated `graph.road_edges` array from the instance JSON (falling back to recomputed Delaunay if absent)
- **Water/Air:** always recomputes Delaunay triangulation at runtime (`scipy.spatial.Delaunay`) with a **display threshold of 40 km** (vs. the 80 km model threshold) — this suppresses the dense triangulation mesh and makes disruption visible as the network thins across scenarios

**Flood epicenter layer:** Each epicenter renders as a `folium.Circle` with `radius = intensity × 35,000 m` (in metres), dashed red border, 8% fill opacity, plus a `folium.DivIcon` lightning-bolt symbol at the center.

**Risk choropleth:** Node colors map risk $r \in [0,1]$ to green→yellow→red via HLS color space: `hue = (1 - r) × 0.333`, then `colorsys.hls_to_rgb(hue, 0.42, 0.88)`. Demand bubble size scales as `radius = 5 + 15 × (demand / max_demand)`.

Layer visibility is **not** managed by Folium's `LayerControl`; instead, Streamlit checkboxes gate whether each `FeatureGroup` is added to the map object. The map key `f"dmap_{dataset}_{scenario_idx}_{flags}"` forces a full re-render on any checkbox toggle, avoiding stale state.

### 2.3 Interactive Pareto Plot — Plotly Click-to-Select

The Pareto scatter (`build_pareto_fig`) uses `plotly.graph_objects.Scatter` with `on_select="rerun"` mode. Each Pareto-front point encodes its list index in `customdata=[[i] for i in range(len(pf))]`. On click, `event.selection.points[0].customdata[0]` extracts the solution index, writes it to `st.session_state["selected_idx"]`, and calls `st.rerun()`, which triggers the map to re-render for the newly selected solution. The selected point is rendered as a separate `go.Scatter` trace with an orange-red star marker (`symbol="star"`, size=16), layered on top of the Pareto-front trace.

The **compromise solution** button applies the normalized L2 distance from the ideal point: $\arg\min_i \left[(\frac{Z1_i - Z1^*}{\Delta Z1})^2 + (\frac{Z2_i - Z2^*}{\Delta Z2})^2\right]$.

---

## Key Parameter Table (for Methods section)

| Parameter | Symbol | Value |
|---|---|---|
| Nodes (large) | $|I|, |H|, |J|$ | 100, 20, 12 |
| Nodes (small) | $|I|, |H|, |J|$ | 20, 5, 2 |
| Scenarios | $|S|$ | 3 (mild/severe/extreme) |
| Transport modes | $|M|$ | 3 (road/water/air) |
| OSRM detour cap | $\rho_{\max}$ | 1.8 |
| Max road edge | $\delta_{\max}$ | 80 km |
| Display edge | — | 40 km |
| Epicenter radius | $\sigma_\text{epi}$ | 85 km |
| Hub risk threshold | $\chi$ | 0.70 (model), 0.60 (DSS activation) |
| Economies of scale | $\alpha$ | 0.60 |
| Random seed | — | 2026 |
