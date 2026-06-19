# Chapter 3.3 — Geospatial Decision Support System (Visualizer Software)

> **Scope note:** This chapter documents the software architecture and rendering techniques of the interactive visualizer located in `visualizer/`. The algorithmic components — specifically the PB-NSGA solver, min-cost flow decoder, and second-stage optimisation logic — are covered in Chapter 3.2 and are deliberately excluded here.

---

## 3.3.1 Software Architecture and State Management

### Overall Design Philosophy

The Decision Support System (DSS) is implemented as a single-page interactive web application using the **Streamlit** framework (`visualizer/app.py`). The architectural guiding principle is a strict decoupling between *heavy offline computation* and *lightweight interactive rendering*, enabling sub-second UI response times despite working with geospatially rich solution data.

**Offline pre-computation layer.** The most computationally expensive operation — deriving per-solution, per-scenario second-stage flow decisions (routing assignments, transshipment volumes, inventory levels) — is executed entirely offline by the script `visualizer/preprocess_flows.py`. Its outputs are serialised as structured JSON files under `results/{exp}/flows/solution_{idx}.json`. The live application never recomputes these flows; it exclusively reads from this pre-built artefact store. This design choice ensures that the interactive layer has O(1) data access cost regardless of the complexity of the underlying optimisation.

**Streamlit reactive model.** Streamlit's execution model re-runs the entire Python script from top to bottom on every user interaction. To prevent redundant I/O on each rerun, all data loading functions are decorated with `@st.cache_data`:

```python
@st.cache_data(show_spinner="Loading solver results…")
def _load_result(path: str) -> SolverResult: ...

@st.cache_data(show_spinner="Loading instance…")
def _load_instance(path: str) -> NodeInfo: ...
```

The `@st.cache_data` decorator memoises the return value against the function arguments, so the solver JSON (which may contain hundreds of solutions across a full Pareto run) is deserialised from disk exactly once per session, regardless of how many times the user switches scenarios or clicks Pareto points.

### Interactive State Management via `st.session_state`

The central challenge in a Streamlit application is maintaining *cross-rerun persistent state* — specifically, tracking which Pareto solution is currently selected so that both the Plotly scatter plot and the Folium map render consistently after any user action.

The application stores the currently selected solution index in `st.session_state["selected_idx"]`. This key-value store persists across Streamlit reruns within the same browser session and acts as the single source of truth for component synchronisation:

```python
# Initialisation (first run only)
if "selected_idx" not in st.session_state:
    st.session_state["selected_idx"] = 0

# Used by both the Pareto chart and the map
sel_idx = min(st.session_state["selected_idx"], len(solutions) - 1)
solution = solutions[sel_idx]
```

Any widget that changes the selection — a Pareto point click, the Prev/Next navigation buttons, or the numeric jump input — writes the new index to `st.session_state["selected_idx"]` and immediately calls `st.rerun()`, causing the entire layout to re-render coherently with the new selection.

### Application Layout

The UI is structured as follows:

- **Sidebar (persistent):** Global controls rendered unconditionally on every page — dataset selector (radio), flood scenario selector (Mild / Severe / Extreme), display toggles (node labels, allocation routes, transshipment flows), and a Pareto front filter checkbox. These controls affect both tabs simultaneously.

- **Tab 1 — Solution Explorer:** The primary interactive view, composed of two sub-regions:
  - *Row 1:* A two-column layout — the Plotly Pareto scatter (3/5 width) alongside a KPI dashboard with `st.metric` cards and quick-jump buttons (2/5 width).
  - *Row 2:* A full-width `st_folium` geospatial map rendered for the currently selected solution and scenario.

- **Tab 2 — Input Dataset Explorer:** A standalone Folium map of the problem instance's physical topology, driven by per-layer checkboxes rendered inline above the map. The map key is computed as a function of all active toggles and the scenario index (`_dmap_key`), forcing a full Folium re-render on any layer change while avoiding stale renders from unchanged state.

### Module Decomposition

| Module | Responsibility |
|---|---|
| `app.py` | Entry point; layout orchestration, session state, data loading, widget wiring |
| `pareto_view.py` | Constructs a `plotly.graph_objects.Figure` for the interactive Pareto scatter |
| `map_view.py` | Constructs a `folium.Map` for a single (solution, scenario) pair |
| `dataset_view.py` | Constructs a `folium.Map` for the raw problem instance topology |
| `flow_loader.py` | Deserialises pre-computed per-solution flow JSON into typed dataclasses |
| `src/visualizer/solution_loader.py` | Deserialises solver output JSON and instance JSON into typed dataclasses (`NodeInfo`, `Solution`, `SolverResult`) |

---

## 3.3.2 Input Data Visualizer — The Baseline Network

### Purpose and Entry Point

The Input Dataset Explorer (`dataset_view.py`, `build_dataset_map()`) renders the raw problem instance *before* any solution is applied. It allows a decision-maker to inspect the geographic distribution of demand, the physical transport network topology, and how each flood scenario alters network accessibility — entirely independently of any algorithmic output.

### Map Construction and Coordinate Handling

The Folium map is centred on the arithmetic mean of all node coordinates:

```python
centre = (sum(lats) / len(lats), sum(lons) / len(lons))
m = folium.Map(location=centre, zoom_start=9, tiles="OpenStreetMap", control_scale=True)
```

All node coordinates are stored in (latitude, longitude) format within the `NodeInfo.coords` list, indexed by global node index. Six independent `folium.FeatureGroup` objects are constructed — one per toggleable layer — and all are unconditionally added to the map. Layer visibility is controlled at the Streamlit level via Python boolean flags rather than Folium's `LayerControl`, preventing a known rendering conflict between `folium.LayerControl` and `streamlit_folium` rerenders. The map is keyed by all active flags in `_dmap_key` to force a clean re-render on any toggle change.

### Layer 1 — Risk Choropleth

Each node is rendered as a `folium.CircleMarker` coloured according to its scenario-specific risk score $r_i \in [0, 1]$. The colour mapping is implemented in `_risk_color()` using the HSL colour model:

```python
def _risk_color(v: float) -> str:
    hue = (1.0 - v) * 0.333   # 0.333 ≈ green; 0 = red
    r, g, b = colorsys.hls_to_rgb(hue, 0.42, 0.88)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
```

This produces a continuous perceptually intuitive gradient: low-risk nodes (near 0) are rendered in green (`#2e7d32`), mid-risk in yellow-amber, and high-risk in red (`#c62828`). Hub candidate nodes are rendered with a larger radius (10 px vs. 7 px) and a heavier dark border (`#555`, weight 1.5) to visually distinguish them from demand nodes even when layers overlap.

### Layer 2 — Demand Volume Heatmap

Demand nodes are rendered as proportional bubbles: the radius scales linearly with normalised demand — `radius = 5 + 15 * norm` — so that the largest demand node occupies a 20 px circle and the smallest a 5 px circle. Colour is mapped through a two-stage piecewise interpolation in `_demand_color()`:

- For $norm \in [0, 0.5)$: linear interpolation from white `(255, 255, 255)` to orange `(255, 136, 0)`.
- For $norm \in [0.5, 1]$: linear interpolation from orange to dark red `(139, 0, 0)`.

Supply origin nodes are rendered as pure-CSS upward triangles (using the CSS zero-width border technique in `_origin_icon()`) in green `#43A047`, annotated with their available supply volume.

### Layer 3 — Flood Epicentres

Each flood epicentre defined in the scenario JSON is rendered as two overlapping Folium primitives:

1. **`folium.Circle`** centred at the epicentre coordinates with `radius = intensity × 35,000` metres, styled with a semi-transparent red fill (opacity 0.08) and a dashed red border (`dash_array="8 4"`, `color="#C62828"`). This encodes the spatial influence zone of the flood event.
2. **`folium.Marker`** at the same coordinates with a custom `folium.DivIcon` rendering a Unicode lightning bolt (`⚡`) in dark red with a white text shadow, serving as a high-visibility centroid indicator.

The tooltip and popup encode intensity and influence radius in kilometres, enabling rapid cross-scenario comparison of flood severity.

### Layer 4 — Accessibility Planar Graph (Topological Network Edges)

This is the most architecturally significant layer of the dataset view. It renders the underlying transport network topology by drawing edges per mode (Road, Water, Air) and colouring them only when the corresponding arc is accessible in the selected scenario.

**Edge set construction.** The system employs two distinct edge-set strategies depending on the transport mode and data availability:

- **Road edges** preferentially use OSRM-validated road arcs stored in the instance JSON under `graph.road_edges`. These arcs are derived from real OpenStreetMap road network data during dataset generation and represent actual navigable road segments between node pairs. When this field is absent (legacy instances), the system falls back to a Delaunay triangulation of all node coordinates.

- **Water and Air edges** always use a Delaunay triangulation, as waterway and aerial routes are not constrained to road infrastructure.

The Delaunay triangulation is computed via `scipy.spatial.Delaunay` applied to the full node coordinate array. A maximum-distance filter of **`DISPLAY_EDGE_KM = 40.0 km`** is applied using the Haversine great-circle formula to discard long-range edges that would otherwise produce a visually indistinct mesh:

```python
def _delaunay_edges(coords) -> Set[Tuple[int, int]]:
    tri = Delaunay(np.array([[c[0], c[1]] for c in coords]))
    edges = set()
    for simplex in tri.simplices:
        for i in range(3):
            for j in range(i+1, 3):
                u, v = simplex[i], simplex[j]
                if _haversine(...) <= DISPLAY_EDGE_KM:
                    edges.add((min(u,v), max(u,v)))
    return edges
```

This threshold of 40 km was calibrated to approximately match district-to-district road segment lengths in Central Vietnam, retaining mountain pass connections while eliminating redundant long-range triangulation arcs.

**Accessibility-conditioned rendering.** For each edge $(u, v)$ in the relevant edge set, the system queries the scenario's three-dimensional accessibility matrix `accessibility[mode][u][v]` — a boolean tensor loaded directly from the instance JSON. Only arcs where `accessibility[mode][u][v] == 1` are drawn as `folium.PolyLine` objects. Blocked arcs are silently omitted (not drawn with dashes), so network disruption manifests visually as the network *thinning* across more severe scenarios. Each accessible edge is coloured by mode: Road in forest green (`#2E7D32`), Water in dark blue (`#0277BD`), Air in purple (`#6A1B9A`).

---

## 3.3.3 Solution Visualizer — Interactive Decision Support

### 3.3.3.1 Interactive Pareto Front (Plotly Scatter)

The Pareto front is rendered in `pareto_view.py` as a `plotly.graph_objects.Figure` containing up to three stacked scatter traces:

1. **Background feasible cloud** (optional, `show_all_feasible=True`): Non-rank-1 feasible solutions rendered as light-blue dots (colour `#90CAF9`, opacity 0.5, size 7). This provides spatial context for how the Pareto front relates to the broader feasible region.

2. **Pareto front trace**: Rank-1 feasible solutions (`s.rank == 1, s.CV == 0.0`) rendered as blue circles (`#2196F3`, size 10) connected by a dotted line (`dash="dot"`). Each marker is annotated with a rich hover template showing Z1, Z2, open hub count, and rank. Crucially, each point encodes its local list index via the `customdata` field:

   ```python
   fig.add_trace(go.Scatter(
       ...
       customdata=[[i] for i in range(len(pf))],
       hovertemplate="%{text}<extra></extra>",
   ))
   ```

3. **Selected solution overlay**: The currently active solution is highlighted by an additional `go.Scatter` trace rendering a single orange-red star marker (`color="#FF5722"`, size 16, `symbol="star"`) with a white border. This trace is redrawn on every rerun, providing a lightweight selection highlight without mutating the base traces.

**Click-to-select integration.** The chart is rendered with `st.plotly_chart(fig, on_select="rerun")`, which activates Streamlit's built-in Plotly selection event listener. When the user clicks a point, Streamlit re-executes the script and provides the click event via the return value:

```python
event = st.plotly_chart(fig, on_select="rerun", key="pareto_chart", ...)
pts = event.selection.points
if pts:
    clicked_idx = int(pts[0].customdata[0])
    if clicked_idx != sel_idx:
        st.session_state["selected_idx"] = clicked_idx
        st.rerun()
```

The `customdata[0]` field recovers the exact list position of the clicked solution, which is written to `st.session_state["selected_idx"]`. A guard condition (`clicked_idx != sel_idx`) prevents infinite rerun loops when the already-selected point is clicked again.

**Supplementary navigation.** In addition to direct point selection, three navigation widgets are provided below the chart: a `◀ Prev` button, a `Next ▶` button (both performing modular index arithmetic for wrap-around), and a `st.number_input` widget for direct index entry. All three paths converge on the same `st.session_state["selected_idx"]` → `st.rerun()` pattern.

### 3.3.3.2 KPI Dashboard

The KPI panel, co-rendered alongside the Pareto chart, provides structured quantitative context for the selected solution via `st.metric` widgets. Three primary metrics are displayed:

- **Z1 (Expected Total Logistics Cost)** in millions, with a delta relative to the minimum-Z1 solution in the current set (`delta_color="inverse"` renders positive deltas in red as higher cost is worse).
- **Z2 (Expected Maximum Deprivation Cost)** in millions, similarly delta-referenced.
- **Open Hubs** as a fraction of the total hub candidate count.

Below these, transport mode usage is decomposed: the `solution.A` vector (transport mode assignment per demand node) is counted to produce three `st.metric` cards for Road, Water, and Air assignment counts.

**Quick-jump actions.** Three single-click buttons implement analytically useful navigation:

- *Best Z1*: `argmin Z1` over all solutions.
- *Best Z2*: `argmin Z2` over all solutions.
- *Compromise*: The solution minimising the normalised Euclidean distance to the ideal point `(min Z1, min Z2)`, computed as:

  ```python
  idx = min(range(len(solutions)),
            key=lambda i: ((solutions[i].Z1 - z1m)/z1r)**2 + ((solutions[i].Z2 - z2m)/z2r)**2)
  ```

  where `z1r = max(Z1) - min(Z1)` and `z2r = max(Z2) - min(Z2)` are range-normalisation factors.

### 3.3.3.3 Geospatial Solution Map (Folium)

The solution map (`map_view.py`, `build_map()`) renders the physical deployment of the selected solution overlaid on an OpenStreetMap tile layer. It is re-keyed on `(sel_idx, scenario_idx)` to force a clean re-render whenever either dimension changes.

**Data source selection.** The rendering pipeline first attempts to load a pre-computed `ScenarioFlow` for the current (solution index, scenario index) pair via `flow_loader.load_solution_flow()`. This object contains the complete second-stage routing result: demand assignments, origin assignments, transshipment arcs, hub activation flags (`y_ks`), and per-hub inventory levels. If no pre-computed flow is available, the system falls back to a geometric heuristic — assigning each demand node to its nearest open hub (by Euclidean coordinate distance) and reading transport modes from the solution's `A` vector.

**Feature groups and layer control.** Five `folium.FeatureGroup` objects structure the map content:

| Feature Group | Visibility Default |
|---|---|
| `fg_hubs` — Hub markers | Always shown |
| `fg_demand` — Demand node circles | Always shown |
| `fg_orig` — Supply origin triangles | Always shown |
| `fg_alloc` — Allocation routes (demand→hub, origin→hub) | Sidebar toggle |
| `fg_trans` — Transshipment flow lines | Sidebar toggle |

A `folium.LayerControl(collapsed=False)` is injected into the map, providing a secondary in-map toggle panel for fine-grained layer visibility without requiring a Streamlit rerun.

**Custom HTML markers for hub states.** Hub candidates are rendered using `folium.DivIcon` with inline CSS rather than standard Leaflet icons, enabling precise visual differentiation across hub states. The icon is a diamond shape achieved by a `rotate(45deg)` CSS transform applied to a square `div`:

```python
def _hub_icon(open_: bool) -> folium.DivIcon:
    colour = _COL_HUB_OPEN if open_ else _COL_HUB_CLOSED   # #FF7043 or #9E9E9E
    size   = 18 if open_ else 12
    border = "2px solid #5D4037" if open_ else "1px solid #555"
    return folium.DivIcon(
        html=(f'<div style="width:{size}px;height:{size}px;'
              f'background:{colour};border:{border};'
              f'transform:rotate(45deg);..."></div>'),
        icon_size=(18, 18), icon_anchor=(9, 9),
    )
```

Three distinct hub states are visually encoded:

- **Open + Active** (open in this solution *and* reactive in this scenario via `y_ks`): Large orange diamond (18 px, `#FF7043`), thick brown border.
- **Open but Inactive** (established in this solution, but the scenario risk exceeded the activation threshold `_RISK_THRESHOLD`): Large grey diamond (18 px, `#9E9E9E`).
- **Closed**: Small grey diamond (12 px, `#9E9E9E`), thin border.

The distinction between Open+Active and Open-but-Inactive is critical for communicating scenario-specific hub behaviour: a hub may be strategically pre-positioned (first-stage decision `X_k = 1`) yet operationally inactive in a particular scenario due to flood damage (second-stage reactive decision `y_k = 0`).

Supply origin nodes are rendered as pure-CSS upward triangles using the zero-width border technique, mirroring the dataset view for visual consistency.

**Differentiated polylines for transport modes.** Allocation routes (demand node → assigned hub, and supply origin → hub) are rendered as `folium.PolyLine` objects with style properties that encode both transport mode and accessibility state:

| Mode | Colour | Dash Array | Weight |
|---|---|---|---|
| Road (0) | `#E53935` (red) | Solid | 1.5 |
| Water/Boat (1) | `#039BE5` (blue) | `[8, 4]` | 1.5 |
| Air/Helicopter (2) | `#7CB342` (green) | `[2, 4]` | 1.5 |
| *Blocked route* | `#EF5350` (blocked red) | Solid | 1.5 |

The accessibility state of each arc is checked against the scenario's accessibility tensor before rendering:

```python
def _is_accessible(mode: int, src: int, dst: int) -> bool:
    try:
        return bool(sc_access[mode][src][dst])
    except (IndexError, TypeError):
        return True
```

When a route is blocked (`accessible == False`), the polyline is drawn in `#EF5350` (a desaturated alarm red) at reduced opacity (0.4 vs. 0.7 for accessible routes), and the demand node circle is simultaneously rendered in the same blocked colour at reduced size (radius 4 vs. 6) and reduced fill opacity (0.5 vs. 0.85). This coordinated visual degradation — affecting both the connecting line and the endpoint marker — communicates scenario-specific network disruption as a cohesive visual signal rather than an isolated line-colour change.

**Flow-proportional transshipment lines.** Inter-hub transshipment flows (hub-to-hub commodity redistribution) are drawn as thick `folium.PolyLine` objects whose stroke width is proportional to the normalised flow volume:

```python
max_flow = max(t.flow for t in scenario_flow.transshipment)
weight   = 2 + 5 * (ts.flow / max_flow)   # range: [2, 7] px
```

Each transshipment arc inherits the same mode colour palette as allocation routes, enabling the decision-maker to immediately distinguish whether inter-hub redistribution uses road, waterway, or aerial transport.

**Fixed-position HTML legend.** A fixed-position legend is injected directly into the Folium map's HTML root via `folium.Element`, positioned at the bottom-left corner. It encodes the current scenario name and the full symbol vocabulary (hub states, supply origin, demand node modes), ensuring the map is self-documenting when exported as a standalone HTML file via the `st.download_button` provided below the map.

---

## Summary of Architectural Decisions

| Design Decision | Technical Rationale |
|---|---|
| `@st.cache_data` on all I/O functions | Eliminates redundant JSON deserialisation on every Streamlit rerun; critical given 100+ solution result files |
| Pre-computed flow JSONs (offline) | Decouples interactive rendering from second-stage optimisation; enables O(1) scenario switching |
| `st.session_state["selected_idx"]` as single source of truth | Guarantees Pareto chart and Folium map always render the same solution, regardless of navigation path |
| `on_select="rerun"` + `customdata` index embedding | Enables direct Plotly click-to-select without a third-party event bridge; index is stored in the plot data itself |
| `folium.DivIcon` with inline CSS for hub markers | Enables three-state visual encoding (active/inactive/closed) with size and colour variation not achievable with standard Leaflet icons |
| `_is_accessible()` accessibility check per arc | Allows identical rendering code to serve all three scenarios by substituting the accessibility tensor at render time |
| Streamlit checkboxes instead of Folium `LayerControl` for dataset view | Avoids `streamlit_folium` re-render conflicts; uses `_dmap_key` hashing to force a clean map rebuild on any toggle |
| OSRM-validated `graph.road_edges` with Delaunay fallback | Ensures road topology reflects real-world navigability; Delaunay fallback maintains backward compatibility with legacy instance files |
