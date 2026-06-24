# DSS System Audit — Features, UI/UX, and Use Cases

**Date:** 2026-06-23  
**Status:** Living document — update as features land or are revised.  
**Purpose:** Tổng hợp PRD features, UI/UX description, và use cases của DSS. Là nguồn tham khảo chính xác nhất về trạng thái triển khai thực tế so với PRD `audit/prd_proposal_dss.md`.

Launch command: `streamlit run visualizer/app.py` (from project root, inside `.venv`)

---

## 1. System Architecture

```
visualizer/
  app.py              ← Streamlit entry point; sidebar + 3 tabs
  config.py           ← PATHS lookup table; ALGO_LABELS; get_explorer_config()
  solution_tab.py     ← Tab 1: Solution Explorer (map + 3 panels)
  dataset_view.py     ← Tab 2: Input Dataset Explorer (6 Folium layers)
  experiments_tab.py  ← Tab 3: Experiment Pipeline runner + results display
  map_view.py         ← Folium map builder for solution routing
  pareto_view.py      ← Plotly Pareto front figure
  loaders.py          ← Cached JSON loaders (result, instance, flows)
  flow_loader.py      ← Flow file reader; DemandAssignment dataclass
  solver_runner.py    ← preprocess_flows subprocess invocation
  widgets.py          ← compute_knee(); scenario_selector()
  narrative_data.py   ← CLI script: extract narrative_data.json (EXP-7)
  preprocess_flows.py ← Python postprocessor: decoder.hpp replica → flow files
```

**Data trust model (CLAUDE.md §3):**
- *Ground truth:* Solver JSON files (`CV_large_seed*.json`, `cv_small_pb_nsga.json`) — immutable C++ output. All Z1/Z2/CV values from these files.
- *Derived:* Flow JSON files (`flows/solution_*.json`) — Python postprocessor heuristic. Mode assignments and hub assignments are estimates, never solver output. Always labelled "postprocessor estimate" in the UI.

---

## 2. Navigation & Global Controls

### 2.1 Primary navigation

Three tabs at the top of the content area (`st.tabs`):
```
🗺️ Solution    📊 Input Dataset    📈 Experiments
```
One click switches tab with no page scroll required.

> **PRD deviation (D6):** PRD §3.7 specified replacing `st.tabs` with a top-level `st.radio` so the map stays at a fixed vertical position across views. Not implemented — `st.tabs` is retained. In practice the tabs render at the top of the page and switching is one click; the scrolling concern is minor for the current screen height.

### 2.2 Sidebar controls

The sidebar is always visible (expandable; auto-collapses on mobile). A custom JS-injected FAB button (❯) re-expands it when Streamlit collapses the sidebar.

| Control | Values | Effect |
|---|---|---|
| **Dataset** | CV Large / CV Small | Switches instance and result paths |
| **Dataset version** | v1 (canonical) / v2 (planar) | Switches to v2 subdirectory results |
| **Algorithm** | PB-NSGA / MILP-AWS | Shown only when multiple result files exist |
| **Mini Pareto** | Plotly clickable scatter | Click point → selects solution; sidebar renders only when >1 Pareto solution |
| **Quick jump** | 💰 Z1 / ⚖️ Z2 / ⭐ Knee | Jump to cheapest / fairest / balanced solution |
| **Map view** | Single scenario / Compare all 3 | Switches map rendering mode |
| **Hide rescue lines < demand** | 0–5000 persons (slider, step 100) | Hides routing lines below population threshold; demand dots remain |
| **Flow status** | ✅ ready / ⚠️ stale / ℹ️ none | Shows flow file count vs Pareto front count |
| **⚙️ Generate/Regenerate Flows** | button | Runs `preprocess_flows.py` as subprocess with live status |

MILP-AWS result files use a separate flows sub-directory (`flows_milp_aws/`) so PB-NSGA and MILP-AWS flows never overwrite each other.

Path resolution: every path is derived from `config.py::get_explorer_config(dataset, version, algo)` using the `PATHS` lookup table. No hardcoded paths anywhere in the view layer.

---

## 3. Tab 1 — Solution Explorer

**Entry function:** `solution_tab.render_solution_tab()`  
**File:** `visualizer/solution_tab.py`

### 3.1 Layout (top-to-bottom)

```
[Solution carousel: ◀  Solution N / M  · Z1=$X.XXM · Z2=Y  ▶]  (hidden when sidebar open)
[Flood scenario: ● Mild  ○ Severe  ○ Extreme]
[Geospatial Network Map — 620px height, full width]
[Export map as HTML]
── Stage 2 — Scenario Response ──────────────────
── Stage 1 — Pre-Disaster Plan ──────────────────
── Pareto Front & Navigation ────────────────────
[FAB scroll button: ↓ Pareto / ↑ Map]
```

### 3.2 Solution carousel

Shown only when there are ≥2 Pareto solutions. Hidden when the sidebar is open (DOM-patching JS detects sidebar state and toggles display). Features:
- ◀ / ▶ buttons step through solutions sequentially
- Centre badge: `Solution N / M · Z1 · Z2`, with ⭐ Knee / 💰 Best Z1 / ⚖️ Best Z2 inline label
- Knee computed by Tchebycheff min-max on normalised Z1–Z2 space

### 3.3 Scenario selector

Radio buttons: `🌊 Mild` / `⚠️ Severe` / `🔴 Extreme`  
Disabled (greyed out, caption shown) when map mode is "Compare all 3 scenarios".  
Shared between map, Stage 2 panel, and flow loading.

### 3.4 Geospatial Network Map (feature D4/D5)

**Single scenario mode:**  
Full-width interactive Folium map (620px). Built by `map_view.build_map()`.

Map layers and visual encoding:

| Element | Visual | Data source |
|---|---|---|
| Open planned hub | Orange circle + marker, solid border | `solution.X[k]=1`, risk ≤ χ |
| Inactive hub (risk > χ) | Amber circle, dashed border | `hub_risk[str(h_idx)] > chi` |
| Closed hub (X[k]=0) | Grey small circle | `solution.X[k]=0` |
| Origin (supply depot) | Green diamond marker | `node_info.origin_indices` |
| Demand node | Blue circle, radius ∝ demand | `solution.demand_idx` |
| Demand→Hub routing lines | Red (road), Blue (water), Green (air); dashed for water/air | `flow.demand_assignments[].mode` |
| Origin→Hub supply lines | Dashed orange | `flow.origin_assignments[]` |
| Hub→Hub transshipment | Purple dashed | `flow.transshipment[]` (MCF lateral flows) |

When flow files are unavailable: map shows hub/demand/origin markers with `⚠️ approximate placement` caption; routing lines absent.

Hub marker popups (Folium):
```
[Hub name]
Status: ✅ ACTIVE / ⚠️ INACTIVE (r=0.XX > χ=0.70)
Pre-positioned: X,XXX kg (Y% of ZZZ,ZZZ kg capacity)
Flood risk: Mild 0.XX · Severe 0.XX · Extreme 0.XX
```

Origin marker popups:
```
[Origin name]
Supply available: X,XXX kg [scenario s]
Flood risk: Mild 0.XX · Severe 0.XX · Extreme 0.XX
```

Demand nodes with population below the sidebar slider threshold have their routing lines hidden (dots remain).

**Compare all 3 scenarios mode (feature D5):**  
Three maps side-by-side in `st.columns(3)` at 420px height each, one per scenario. Headers: `🌊 Mild (p=0.60)` / `⚠️ Severe (p=0.30)` / `🔴 Extreme (p=0.10)`. Flow files loaded independently per scenario.

**Export:** `Export map as HTML` button serialises the Folium map to a self-contained HTML file with the current scenario and solution encoded in the filename.

> **PRD note (D4):** Hub popup currently shows risk across all 3 scenarios, hub name, and fill %. The "Serving X communes" with per-mode counts in the popup was specified in PRD §3.5 but is not yet in the popup HTML — this level of detail is in the Stage 2 panel instead.

### 3.5 Stage 2 — Scenario Response panel (feature D1)

Rendered by `_render_stage2_panel()` in `solution_tab.py`.

**Hub safety status:**
```
Active hubs: 5 / 8

⚠️ Huế Warehouse flooded (r=0.82 > χ=0.70)
⚠️ Quảng Trị Depot flooded (r=0.74 > χ=0.70)
```
Shows metric `Active hubs: N / M` plus one `st.warning` line per inactive hub with exact risk value and name.  
`ℹ️ Why χ = 0.70?` expander (collapsed): paragraph citing Bangladesh MCS, Japan 指定避難所, Vietnam Nhà tránh lũ as shelter siting precedents.

**Reactive hubs:**  
`⚡ X reactive hub(s) opened: [names]` if any.  
`ⓘ No reactive hubs opened this scenario` if none.  
Derived from `flow.y_ks`: reactive = `y[k]=True` AND `solution.X[k]=0`.

**Demand routing summary:**
```
100 communes assigned — rescue dispatch modes:
🚚 Road     91      🚤 Water    4       🚁 Air      5
vs Mild: +3 Water 🚤 · -3 Road 🚚 — communes rerouted due to flooding
```
Mode delta vs Mild shown for Severe/Extreme scenarios when mild flow file is available.  
`ⓘ Mode counts are postprocessor estimates; MCF lateral flows not shown` caption always present.

**Hub assignments table:**
```
Hub                  Total  🚚 Road  🚤 Water  🚁 Air
Da Nang Airport        42      37        2        3
Tam Ky Logistics       23      22        1        0
...
```
Sortable `st.dataframe`. Air-serving hubs additionally shown as `🚁 Helicopter service: Hub A (3) · Hub B (2)`.

**Trade-off position:**
```
Worst-case deprivation: 41,828 person-hrs · vs lowest-cost: -12.8% deprivation, +23.0% cost
```
Derived from `solution.Z2` vs. `min Z2 across Pareto`, and `solution.Z1` vs. `min Z1 across Pareto`.

**In Compare mode:** Stage 2 panel shows three sub-tabs (🌊 Mild / ⚠️ Severe / 🔴 Extreme), each rendering a full `_render_stage2_panel()`.

> **PRD gap (avg response latency):** PRD §3.2 specified `avg response latency (hrs)` per mode group (Ω_{is} = τ_{ks} + 2τ_{kim}). Not yet implemented. The `τ_ks` values are available at `instance["scenarios"][s]["hub_process_time"]` and `τ_kim` at `instance["transport"]["time"]`. This is the clearest pending feature in D1.

### 3.6 Stage 1 — Pre-Disaster Plan panel (feature D2)

Rendered by `_render_stage1_panel()` in `solution_tab.py`.

Hub establishment table:
```
Hub              Capacity (kg)  Pre-stock (kg)  Fill %         Fixed cost ($)  Hold rate ($/kg)  Hold cost ($)
Tam Kỳ Hub       217,082        178,007         82% ▓▓▓▓▓▓▓▓░░  125,575          0.400             71,203
A Sáp Helipad    158,107         99,607         63% ▓▓▓▓▓▓░░░░   202,593          0.380             37,851
```
All data from Stage-1 fields: `hub_params.capacity/fixed_cost/hold_cost` (keyed by global hub index as string) and `solution.R[k]`.

**Fill % bar:** ASCII `▓`/`░` blocks (10 chars = 100%).  
**Pre-stock:** `R[k] × capacity_k` — Stage-1 decision, scenario-independent.  
**Hold cost:** `hold_rate × R[k] × capacity_k` — the `c_k q_k` term in Z1.

Summary line: `Total cost $X.XXM · N hubs · Pre-stock X t · Hold cost $XXX,XXX`

> **Note:** Fill % uses `R[k]` (Stage-1 ratio), not `flow.inventory_held[k]` (a per-scenario snapshot). This is intentional: Stage-1 holding cost is a pre-disaster fixed charge independent of scenario.

### 3.7 Pareto Front & Navigation panel (feature D3)

Rendered by `_render_pareto_panel()`.

**Trade-off badge:**
```
● Balanced (knee) — recommended
Z1 = $4.79M · Z2 = 41,828 · 12.3% better deprivation vs worst · +23.0% cost vs cheapest
```
Blue badge when selected solution == knee; grey badge otherwise.

**Pareto chart:** Interactive Plotly scatter. Click any point → `on_select="rerun"` updates `session_state["selected_idx"]`. `dragmode="select"` with a JS poller that restores `clickmode="event+select"` after each Streamlit Plotly.react() call (prevents Streamlit from overriding click mode).

**Quick-jump buttons:** `Best Z1 (cheapest)` / `Best Z2 (fairest)` / `Knee (recommended)` — each triggers `st.rerun()` after setting `selected_idx`.

### 3.8 FAB scroll button

Fixed-position button (bottom-right). Label toggles between `↓ Pareto` (when map is in view) and `↑ Map` (when Pareto is in view), detected by checking the bounding rect of `#_dss-pareto-anchor` vs the viewport height.

---

## 4. Tab 2 — Input Dataset Explorer

**Entry function:** `dataset_view.build_dataset_map()` called from `app.py`  
**File:** `visualizer/dataset_view.py`

### 4.1 Layout

```
[Flood scenario: ● Mild  ○ Severe  ○ Extreme]
Dataset: CV Large (v2) · Scenario: Severe  (use the layer control ≡ on the map to toggle overlays)
[Folium map — 640px, full width]
[Export dataset map as HTML]
▼ Scenario KPIs (expanded)
  Total Relief Demand: 1,234,567 units  (+X vs Mild)
  Avg Node Risk: 0.427  (+0.123 vs Mild)
  Flood Epicentres: 3
```

### 4.2 Map layers (six, all toggleable via Folium LayerControl)

| Layer | Toggle label | Data source | Visual |
|---|---|---|---|
| **Risk choropleth** | Risk index | `scenarios[s]["risk"][node_idx]` | Circle marker coloured green→yellow→red |
| **Demand heatmap** | Demand volume | `scenarios[s]["demand"][str(demand_idx)]` | Circle radius ∝ demand, white→orange→dark-red |
| **Flood epicentres** | Flood epicentres | `scenarios[s]["epicenters"]` | Red star marker + influence radius circle (dashed red) |
| **Accessibility** | Accessibility (Delaunay) | `graph["road_edges"]` (v2) or computed Delaunay | Edge coloured by road=solid/water=dashed/air=dotted |
| **Population circles** | Population (static) | `base_population[str(demand_idx)]` | Blue circle radius ∝ population; tooltip: `Node · Pop: X · Area: Y km²` |
| **Intrinsic risk** | Intrinsic risk (static) | `nodes["aux_risk"][node_idx]` | Circle fill white→red; scenario-independent |

**Mutual exclusivity:** "Risk index" and "Intrinsic risk (static)" layers are enforced exclusive via injected JavaScript — activating one deactivates the other.

**Accessibility layer:** In v2 instances, uses actual planar road graph edges (`graph["road_edges"]`); falls back to computed Delaunay triangulation edges for v1 or missing graph key. Edge colour encoding: road (solid green), water (blue dashed), air (grey dotted).

### 4.3 Scenario KPIs expander

- **Total Relief Demand:** sum of `scenarios[s]["demand"]` values across all demand nodes; delta vs Mild shown for Severe/Extreme
- **Avg Node Risk:** mean `scenarios[s]["risk"]` over `num_I` demand nodes; delta vs Mild
- **Flood Epicentres:** count of `scenarios[s]["epicenters"]`

---

## 5. Tab 3 — Experiments

**Entry function:** `experiments_tab.render()` (imported lazily in `app.py`)  
**File:** `visualizer/experiments_tab.py`

### 5.1 EXP pipeline table

Seven experiment rows displayed in a compact table layout:

```
ID      Name                                    Status    Action
EXP-1   CV-Small baseline comparison            ✅ done   [▶ Run]
EXP-2   CV-Large 20-seed PB-NSGA               ⏳ partial [▶ Run]
EXP-3   OOS/SAA multi-seed evaluation          ⏳ partial [▶ Run]
EXP-4   Aggregate analysis (metrics + figures) ⏳ none   [▶ Run]
EXP-5   SAA convergence study                  ✅ done   [▶ Run]
EXP-6   Solution map export                    ⏳ none   [▶ Run]
EXP-7   Extract narrative data                 ⏳ none   [▶ Run]
```

Status icons derived from primary output file mtime vs input mtime:
- ✅ `done` — output file exists and is newer than primary inputs
- ⏳ `partial` — output partially exists (e.g., some but not all 20 seeds)
- `none` — primary output does not exist

Each row is `st.columns([1, 6, 2, 1])`: ID / name+description / status / Run button.

**EXP-1 guard:** For CV Small + v1, the ▶ Run button shows a locked error:
```
🔒 EXP-1 v1 results are canonical and immutable. Switch to v2 in the sidebar to run.
```
No subprocess is spawned. The guard prevents accidental overwrite of canonical results.

### 5.2 Live log streaming

Clicking ▶ Run launches a subprocess and streams stdout/stderr via `st.status()` with a scrolling code block (last 40 lines). Status updates to ✅ complete or ❌ error on exit. After completion, `st.rerun()` refreshes the pipeline table status.

**EXP-2 special handling:** Before running, checks for missing seeds 0–19 in the results directory. Shows count of missing seeds in the description. Solver invoked once per ▶ Run click for the first missing seed (not all 20 at once — avoids ~2-hour blocking run).

Commands built per experiment:

| EXP | Command | Output |
|---|---|---|
| EXP-1 | `bash run_exp1_baselines.sh --instance <inst> --results-dir <res>` | `cv_small_metrics.csv` |
| EXP-2 | `./solver <inst> --pop 200 --gen 500 --seed N --out <res>/CV_large_seedN.json` | `CV_large_seed{0..19}.json` |
| EXP-3 | `exp_oos_multiseed.py --results-dir <res> --saa-data ... --oos-data ...` | `*_saa_eval.json`, `*_oos_eval.json` |
| EXP-4 | `exp2_analyze_case_study.py <res> <res> data/cv/v2 <inst>` | `exp2_metrics.csv`, `*_hub_freq.pdf` |
| EXP-5 | `exp_saa_convergence.py --data-dir ... --results-dir ... --figures-dir ...` | `convergence_summary.csv` |
| EXP-6 | `exp2_map_solution.py --instance <inst> --result <seed_file> --out <pdf>` | `cv_large_map_detailed.pdf` |
| EXP-7 | `narrative_data.py --results <res> --flows <flows> --instance <inst> --out narrative_data.json` | `narrative_data.json` |

All paths are derived from `PATHS[dataset][version]`; no user-visible paths.

### 5.3 Results display (below pipeline table, always visible)

**Table 4-1 — Algorithm comparison (CV-Small):**  
Always rendered regardless of sidebar dataset selection. Resolves path from `PATHS["CV Small"][version]["results"] / "cv_small_metrics.csv"` (dataset-independent). When file exists:
- `st.dataframe(styled)` with pandas styling
- `highlight_max` on `hv_mean` column (green = highest HV, i.e. best algorithm)
- `highlight_min` on `igd_mean`, `wall_s`, `cpu_s` columns (green = lowest, i.e. best)
- Columns: `algorithm, n_runs, hv_mean, hv_std, igd_mean, igd_std, wall_s, cpu_s`

When file absent: `_Table 4-1: run EXP-1 to generate cv_small_metrics.csv_`

**Fig 4-6 — Hub flood risk heatmap:**  
Always rendered (built from instance JSON, no file needed). Plotly `go.Heatmap`:
- Rows = hub names from `node_info.names[hub_global_idx]`
- Columns = ["Mild", "Severe", "Extreme"] with `SC_PROBS` annotations
- Values = `scenarios[s]["hub_risk"][str(hub_global_idx)]`
- Colour scale: green (0) → red (1); horizontal dashed line at χ=0.70 threshold
- Title: `Hub flood risk by scenario (χ = 0.70 threshold)`

**PDF figure gallery (2-column layout, left/right):**  
`pdf2image` is attempted first; if unavailable (not in requirements.txt), falls back to a `⬇ Download` button. Current gallery slots:

| Figure | Path | Left/Right |
|---|---|---|
| Pareto fronts (Fig 4-1) | `results/{exp}/{version}/exp2_pareto_tradeoff.pdf` | Left |
| Solution map 1×3 (Fig 4-4) | `figures/{version}/cv_large_map_detailed.pdf` | Right |
| SAA convergence (Fig 4-2) | `results/saa_convergence/{version}/saa_convergence.pdf` | Left |
| Hub selection frequency (Fig 4-5) | `results/{exp}/{version}/*hub_freq*.pdf` | Right |

**Narrative data viewer:**  
If `narrative_data.json` exists in project root: `st.json(data, expanded=False)` + `⬇ Download narrative_data.json` button. Else: `_Run EXP-7 to generate narrative data._`

---

## 6. Feature Implementation Status

| Feature | PRD ID | Status | Notes |
|---|---|---|---|
| PATHS auto-routing lookup | §1 | ✅ implemented | `config.py`; all paths derived from `PATHS[dataset][version]` |
| Map at top of Solution tab | §3.1 | ✅ implemented | Map renders before Stage 2/1/Pareto panels |
| Stage-2 hub safety panel | D1 | ✅ implemented | Active/inactive hub names, risk values, chi expander |
| Stage-2 mode counts + delta | D1 | ✅ implemented | Road/Water/Air counts + vs-Mild delta |
| Stage-2 avg response latency | D1 | ⏳ not yet | Ω_{is} = τ_{ks} + 2τ_{kim} per mode group; data available in instance |
| Stage-2 hub commune table | D1 | ✅ implemented | Breakdown per hub + helicopter info |
| Stage-2 equity framing | D1 | ✅ implemented | Z2 vs best-Z2/best-Z1 comparison |
| Stage-1 hub establishment table | D2 | ✅ implemented | Capacity, fill %, costs, ASCII bar |
| Stage-1 summary line | D2 | ✅ implemented | Total cost, hubs, prestock, hold cost |
| Pareto front panel | D3 | ✅ implemented | Interactive Plotly, click to select, badge, quick-jump buttons |
| Hub popup drilldown | D4 | ⚡ partial | Risk across 3 scenarios + fill %; "serving X communes" breakdown not in popup (it's in Stage 2 panel) |
| Side-by-side 3-scenario map | D5 | ✅ implemented | 3 columns × 420px maps |
| Top-level radio nav (D6) | D6 | ⏳ deferred | `st.tabs` retained; acceptable UX deviation |
| Static input layers (pop + intrinsic risk) | D7 | ✅ implemented | `dataset_view.py`; 6 Folium layers with LayerControl |
| Robustness badge in Pareto hover | D8 | ⏳ not yet | Would require per-solution hub activity precompute |
| Hide low-demand nodes slider | D9 | ✅ implemented | Sidebar slider 0–5000; hides routing lines only |
| Experiment pipeline tab | §4 | ✅ implemented | 7 EXPs with status icons and live log |
| EXP-1 v1 immutability guard | §4.2 | ✅ implemented | Lock error shown; no subprocess |
| Metrics table always visible | §4.3 | ✅ implemented | Dataset-independent path; shows for CV Large too |
| Table highlight max HV | §4.3 | ✅ implemented | Green on highest hv_mean; green on lowest igd/time |
| Risk heatmap always visible | §4.3 | ✅ implemented | Live Plotly from instance JSON |
| PDF figure gallery | §4.3 | ✅ implemented | 4 figures + pdf2image / download fallback |
| narrative_data.py script | §5 | ✅ implemented | `visualizer/narrative_data.py`; all Block 1–10 keys |
| narrative_data.json viewer | §5 | ✅ implemented | `st.json` + download button in Tab 3 |
| MCF Python decoder | §6 | ⏳ plan only | `audit/doc_mcf_decoder_plan.md`; no code yet |
| Flow file integrity (verify_flows.py) | CLAUDE.md §4 | ✅ | `visualizer/verify_flows.py` exists |
| Algorithm selector (MILP-AWS) | config | ✅ | Separate flows_milp_aws/ directory |
| Carousel (solution prev/next) | — | ✅ | ◀/▶ navigation + auto-hides with sidebar open |
| FAB scroll button | — | ✅ | Map/Pareto scroll toggle |

---

## 7. Use Cases

### UC-1 — Presentation mode (thesis defence / stakeholder demo)

**Actor:** Researcher presenting to a committee or government stakeholders.

**Flow:**
1. Open DSS, select CV Large / v2 from sidebar.
2. Click ⭐ Knee button → best-balanced solution selected automatically.
3. Map renders at top: 8 open hubs (orange), routing lines by mode.
4. Switch to "Compare all 3 scenarios" → 3 side-by-side maps appear.
5. Stage 2 panel: "Active hubs: 5 / 8 · ⚠️ Da Nang Airport flooded (r=0.94)" — audience sees named consequences.
6. Scroll to Pareto panel → click "Best Z2 (fairest)" → map and panels update in real-time.
7. Click "Export map as HTML" → save standalone file for embedded slide.

**Key DSS value:** Audience sees named hubs, scenario consequences, and trade-offs without needing to read JSON or run code.

---

### UC-2 — Thesis evidence extraction

**Actor:** Researcher writing results section.

**Flow:**
1. Tab 3 → select CV Large / v2 → run EXP-2 (20-seed PB-NSGA) if not yet complete.
2. Run EXP-3 (OOS evaluation), EXP-4 (aggregate analysis).
3. Run EXP-7 → `narrative_data.json` generated; viewer shows all Block 1–10 keys.
4. Tab 3 metrics table shows Table 4-1 values (HV, IGD+, CPU) with best algorithm highlighted.
5. PDF figures (Pareto fronts, risk heatmap, hub frequency) available for download.
6. Cross-check: `narrative_data.json::knee_CV == 0.0` assertion passed.

**Key DSS value:** One-click experiment execution with reproducible path routing; no manual file path management.

---

### UC-3 — Algorithm comparison review

**Actor:** Co-author or reviewer verifying paper claims.

**Flow:**
1. Select CV Small / v2 → MILP-AWS algorithm.
2. MILP-AWS Pareto front loads; "postprocessor estimate" caption shown.
3. Switch to PB-NSGA → same instance, different Pareto front.
4. Tab 3 → Table 4-1 displayed → HV 0.925 PB-NSGA vs 0.997 MILP highlighted in green.
5. Select solution #3 on PB-NSGA Pareto → Z1/Z2 labels update.

**Key DSS value:** Separate flows directories prevent cross-algorithm contamination; trust-model labels prevent misreading derived estimates as solver output.

---

### UC-4 — Flow file validation

**Actor:** Developer after modifying `preprocess_flows.py` or `decoder.hpp`.

**Flow:**
1. Sidebar → ⚙️ Regenerate Flows → subprocess runs; live log streams; flows regenerated.
2. Run `verify_flows.py` separately (or from a terminal) — checks all assignments valid, hub activations consistent, mode counts match snapshot.
3. If mode counts change: update `flows_snapshot.json` deliberately and explain in commit message.

**Key DSS value:** Decoder protocol (`CLAUDE.md §4/§5`) enforced through UI affordances that make flow regeneration a deliberate action.

---

### UC-5 — Dataset exploration (new scenario or instance)

**Actor:** Researcher exploring a new dataset version or scenario.

**Flow:**
1. Tab 2 → Input Dataset → select Severe scenario.
2. Layer control: toggle Population circles → blue circles sized by commune population.
3. Toggle Intrinsic risk (static) → nodes coloured by baseline flood susceptibility.
4. Toggle Accessibility → Delaunay planar graph shows road/water/air coverage.
5. KPI expander: Total demand, avg node risk, epicentre count.
6. Toggle v1 → v2 in sidebar → accessibility layer switches from Delaunay triangulation to actual planar road graph edges.

**Key DSS value:** Six independent map layers allow independent inspection of demand, risk, connectivity, and population without switching views.

---

## 8. Known Gaps and Deferred Items

| Gap | Priority | Notes |
|---|---|---|
| Avg response latency per mode (Ω_{is}) | Medium | Data available; `τ_ks` in `instance["scenarios"][s]["hub_process_time"]`; display in Stage 2 panel |
| Hub popup commune list | Low | Already in Stage 2 panel; popup duplication deferred |
| Global top-level radio nav (D6) | Low | `st.tabs` retained; one-click switching is acceptable |
| Robustness badge in Pareto hover (D8) | Low | Per-solution hub activity precompute needed; non-trivial at load time |
| MCF Python decoder (transshipment on map) | Medium | Plan in `audit/doc_mcf_decoder_plan.md`; `flow.transshipment` is always empty with current greedy postprocessor |
| Diverse scenario sampling (D7-original) | Deferred | Out of scope per PRD §Decisions locked |
| Sidebar → inline scenario toggle (D5/D6 overlap) | Deferred | Scenario selector is above map for single-scenario mode |

---

*Cross-references: `audit/prd_proposal_dss.md` (full PRD), `audit/plans_dss_system.md` (Part 1/2 query keys and experiment inventory), `visualizer/README.md` (launch instructions).*
