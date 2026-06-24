# visualizer/ — DRND Decision Support System

Streamlit web application for exploring solver results from the
Multi-Objective Incomplete Hub Location and Network Design Problem (MO-IHLNDP)
applied to flood-relief logistics in Central Vietnam.

```
streamlit run visualizer/app.py
```

---

## Architecture at a glance

The codebase is split across three distinct layers:

```
┌─────────────────────────────────────────────────────────┐
│  Streamlit UI layer                                     │
│  app.py · solution_tab.py · widgets.py                  │
├─────────────────────────────────────────────────────────┤
│  Rendering / figure-building layer (pure, no st.*)      │
│  map_view.py · dataset_view.py · pareto_view.py         │
├─────────────────────────────────────────────────────────┤
│  Data layer (I/O, parsing, caching)                     │
│  loaders.py · flow_loader.py · solver_runner.py         │
│  preprocess_flows.py · config.py                        │
└─────────────────────────────────────────────────────────┘
```

The rendering layer has **no Streamlit dependency** — functions take data in,
return a `folium.Map` or `plotly.Figure` out. This makes them independently
testable and reusable.

---

## File-by-file reference

### Entry point

| File | Lines | Role |
|---|---|---|
| `app.py` | 325 | Streamlit entry point. Page config, global CSS, session-state defaults, sidebar (dataset picker, mini-Pareto, map controls, solver panel), global tab routing. Delegates Tab 1 entirely to `solution_tab.py`. Tabs 2 and 3 are rendered inline. |

### UI layer

| File | Lines | Role |
|---|---|---|
| `solution_tab.py` | 514 | Tab 1 — Solution Explorer. Solution carousel, scenario selector, map, Stage-2 panel (hub safety / mode counts / commune breakdown), Stage-1 panel (pre-stock table), Pareto Front & Navigation panel. Also owns the FAB scroll button and all DOM-patching JS (carousel hide, sidebar expand button, Plotly clickmode poller). |
| `widgets.py` | 53 | Two shared UI helpers used across multiple tabs: `scenario_selector()` (the three flood-scenario buttons) and `compute_knee()` (Tchebycheff normalisation — feeds the knee badge and Knee button in both the sidebar and Tab 1). |

### Rendering layer

| File | Lines | Role |
|---|---|---|
| `map_view.py` | 459 | `build_map(...)` → `folium.Map`. Renders a solver solution: hub markers (open/closed/flooded), demand-node dots sized by population, rescue allocation lines coloured by transport mode, transshipment arcs, scenario flood-risk overlay. |
| `dataset_view.py` | 459 | `build_dataset_map(...)` → `folium.Map`. Renders the raw instance for Tab 2: demand/risk heat, flood epicentres, road/water/air accessibility layers, Delaunay triangulation of the node network. Counterpart to `map_view.py` for input data rather than solution output. |
| `pareto_view.py` | 107 | `build_pareto_fig(...)` → `plotly.Figure`. Plots the Pareto front as interactive scatter: blue dots for all solutions, red star for the selected point, knee annotation. Used by both the sidebar mini-chart and the main Pareto panel in Tab 1. |

### Data layer

| File | Lines | Role |
|---|---|---|
| `config.py` | 88 | Single source of truth for all paths (instance JSONs, result JSONs, flow dirs) across datasets (CV Large / CV Small) and versions (v1 / v2). Also holds shared UI constants: `SC_NAMES`, `SC_COLORS`, `MODE_NAMES`, `SOLVER_BIN`, `DEFAULT_GEN`. |
| `loaders.py` | 69 | `@st.cache_data` wrappers around `solution_loader.py` (from `src/visualizer/`). Provides `cached_load_result`, `cached_load_instance`, `cached_load_instance_raw`, `get_solutions`, and `pick_flow` (selects the correct `ScenarioFlow` for a given solution/scenario, falling back to the median-solution flow file). |
| `flow_loader.py` | 115 | Data model and JSON parser for flow files. Defines `DemandAssignment`, `OriginAssignment`, `Transshipment`, `ScenarioFlow`, `SolutionFlow` dataclasses. No Streamlit dependency. Reads from `results/exp*/flows/solution_*.json`. |
| `solver_runner.py` | 98 | `run_solver_pipeline(...)`. Sanitises non-finite floats in the instance JSON (the solver's strict parser rejects `Infinity`), invokes the C++ solver binary, then calls `preprocess_flows.py` to regenerate flow files. Triggered from the sidebar "Run Solver" expander. |
| `preprocess_flows.py` | 518 | Standalone script AND library. Derives per-solution per-scenario flow assignments by reimplementing the C++ decoder heuristic (`decoder.hpp` v3): hub activation by risk threshold χ, demand priority sort, two-pass hub trial, mode selection (road/water by min `C_time`; air as last resort). Output is labelled **postprocessor estimate**, not solver ground truth. Run manually after a solver run or called by `solver_runner.py`. |

---

## Two-layer trust model (from CLAUDE.md §3)

The app strictly separates what it calls **ground truth** from what it calls **estimates**:

| Layer | Source | Numbers | Label in UI |
|---|---|---|---|
| Ground truth | `results/exp*/CV_large_seed*.json` — Z1, Z2, CV, X, R, A | Cost, deprivation, hub establishment, inventory ratios | Cited directly in KPIs and paper |
| Derived / visual | `results/exp*/flows/solution_*.json` — mode assignments, hub allocations | Mode counts (Road / Water / Air), commune-to-hub routing | "postprocessor estimate" |

> **Important:** The `A` vector in a solution (`solution.A[i]`) encodes the **anchor hub local index** (0–19), NOT a transport mode. Never read it as a mode.

---

## Data flow

```
Instance JSON                   Solver result JSON
(data/cv/v*/…drnd.json)        (results/exp*/CV_large_seed*.json)
        │                               │
        ▼                               ▼
  loaders.py                      loaders.py
  cached_load_instance()          cached_load_result()
  cached_load_instance_raw()      get_solutions()
        │                               │
        └──────────────┬────────────────┘
                       ▼
               app.py / solution_tab.py
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
     map_view     pareto_view  dataset_view
    (Tab 1 map)  (Pareto chart) (Tab 2 map)
                                    ▲
                       flow_loader.py
                  (results/…/flows/solution_*.json)
                  pre-generated by preprocess_flows.py
```

---

## Running the solver and regenerating flows

```bash
# 1. Run the solver (CV Large, canonical settings)
./src/solver/solver data/cv/v1/cv_large_drnd.json \
    --pop 200 --gen 500 --seed 0 \
    --out results/exp2/CV_large_seed0.json

# 2. Regenerate flow files
./.venv/bin/python3 visualizer/preprocess_flows.py \
    --result results/exp2/CV_large_seed0.json \
    --instance data/cv/v1/cv_large_drnd.json \
    --out-dir results/exp2/flows --force

# 3. Validate flow integrity
./.venv/bin/python3 visualizer/verify_flows.py
```

Or use the **Run Solver** expander in the sidebar — it runs all three steps automatically.
