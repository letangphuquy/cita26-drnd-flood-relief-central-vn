# PRD — Decision Support System v2: Thesis Edition
**Branch:** `feat/decision-support-system`
**Author:** Lê Tăng Phú Quý (with Claude Sonnet 4.6)
**Date:** 2026-06-19
**Status:** PROPOSAL — pending author approval

---

## 0. Scope Clarification

Three concerns in priority order:

1. **DSS dashboard** — the primary deliverable. Make the Streamlit app a
   genuine decision support tool: a manager facing a flood can load it, pick a
   plan, and immediately understand *which hubs to open*, *how much stock to
   pre-position*, *which villages get served by helicopter*, and *what breaks
   under a severe scenario*. This requires richer metrics, clearer framing, and
   better layout — not just new features.

2. **Experiment pipeline integration** — lightweight. Existing scripts
   (`exp1_evaluate_cv_small.py`, `exp2_analyze_case_study.py`, etc.) already
   do the heavy lifting. The DSS just needs config routing (path inputs, output
   destination) and a Tab 3 that runs them via buttons and displays their outputs.

3. **Missing experiments** — fill any gaps needed for full thesis coverage.
   Identified below after auditing what exists.

---

## 1. What Already Exists (do not re-implement)

### Experiment scripts (all working, `src/scripts/`)

| Script | Produces |
|---|---|
| `exp1_evaluate_cv_small.py` | `cv_small_metrics.csv` (HV/IGD+/CPU/LaTeX row) |
| `exp2_analyze_case_study.py` | `exp2_metrics.csv`, `hub_stability.csv`, pareto PDF, hub_freq PDF, hub_heatmap PDF |
| `exp2_pareto_tradeoff.py` | `exp2_pareto_tradeoff.pdf` (two-panel CV-Small + CV-Large) |
| `exp2_map_solution.py` | `cv_large_map_detailed.pdf` (1×3 composite map, OSM tiles) |
| `exp2_analyze_saa_oos.py` | SAA/OOS diagnostic JSON (single- and multi-seed) |
| `exp_oos_multiseed.py` | Per-seed `*_saa_eval.json` / `*_oos_eval.json` |
| `exp_saa_convergence.py` | `saa_convergence.pdf` (N-sensitivity) |
| `data_generate_saa_oos.py` | 100-scenario SAA set + 10-scenario OOS hold-out |

### Results that exist

- **v1 CV-Large:** 20 PB-NSGA seeds + VNS-TS + GWO-HD + all SAA/OOS eval files
- **v1 CV-Small:** PB-NSGA, VNS-TS, GWO-HD, Greedy, MILP-AWS, BB
- **v2 CV-Large:** only `CV_large_seed2.json` (one seed)
- **v2 CV-Small:** only `CV_small_seed0.json` (one seed)
- **Generated figures:** `exp2_pareto_tradeoff.pdf`, `cv_large_map_detailed.pdf`,
  `saa_convergence.pdf`, `*_hub_freq.pdf`, `*_hub_heatmap.pdf`

### Visualizer infrastructure

- `solution_loader.py`: parses X, **R** (pre-positioning ratio, already works),
  A, Z1, Z2, CV, rank; has `load_results_from_folder()`, `deduplicate_solutions()`
- `solution.R[k]` = Stage-1 pre-positioning ratio for hub k (float, not
  per-scenario — it's a Stage-1 decision, fixed before any scenario unfolds)

---

## 2. Missing Experiments for Full Thesis Coverage

### Gap analysis

The thesis paper (from `core-prompts/experiment-new.md` canonical version)
requires:

| Thesis element | Needs | v1 status | v2 status |
|---|---|---|---|
| Table 4-1 (CV-Small metrics) | HV/IGD+/CPU for all 5 algorithms | ✅ `cv_small_metrics.csv` | ❌ re-run needed if v2 |
| Fig 1 left panel (CV-Small Pareto) | Pareto fronts per algorithm | ✅ exists | ❌ |
| Fig 1 right panel (CV-Large Pareto) | 20-seed combined front | ✅ 20 seeds | ❌ only 1 seed |
| Fig 2 (1×3 solution map) | Knee-point solution decoded per scenario | ✅ `cv_large_map_detailed.pdf` | ⚠️ 1 seed only |
| Fig 3 (SAA convergence) | N-sensitivity curve | ✅ `saa_convergence.pdf` | ❌ re-run on v2 CV-Small |
| Table 4-2 / OOS paragraph | Multi-seed OOS feasibility % | ✅ all 20 seeds evaluated | ❌ |
| Hub frequency chart (Fig 4-5) | Selection % across seeds | ✅ in `hub_stability.csv` | ❌ 1 seed meaningless |
| Risk heatmap (Fig 4-6) | r_ks values per hub per scenario | ✅ (dataset property) | ✅ (v2 instance JSON) |
| Narrative numbers (Blocks 1–10) | knee Z1/Z2, modal counts, hub names | ✅ derivable from v1 | ⚠️ derivable from seed2 only |

### Decision required: v1 or v2 for experiments?

**The thesis can take one of two positions:**

**Position A — v1 experiments, v2 as dataset improvement.**
All numerical claims (Table 4-1, 4-2, Figures 1–3, hub frequency) are reported
from v1 results. The v2 dataset is presented as a methodological contribution
(Chapter 3/Dataset section), with the seed2 solution as an illustrative case
study. This is academically defensible since v1 already has 20 seeds.
*No new solver runs needed.*

**Position B — Re-run full suite on v2.**
Re-run 20 seeds × 3 algorithms on v2 CV-Large and v2 CV-Small baselines.
~8 hours compute. All figures regenerated. Cleaner for a thesis: the dataset
you describe is the one you report results on.
*Requires ~8h compute + all downstream analysis re-run.*

> **This is the author's call. State the choice before implementation begins.**
> The DSS features below work either way — they read whichever result files are
> present.

### Missing experiment: `narrative_data.py` (new, regardless of v1 vs v2)

Neither v1 nor v2 has a script that extracts the Block 1–10 query keys into
a single flat JSON for thesis text substitution. This must be written.

### Summary: new experiment work required

| Item | Needed for | Effort | Condition |
|---|---|---|---|
| **`visualizer/narrative_data.py`** | All Block 1–10 thesis numbers | ~1 day | Always needed |
| Re-run v2 CV-Large 20 seeds | All thesis figures on v2 | ~6h compute | Only if Position B |
| Re-run v2 CV-Small baselines | Table 4-1 on v2 | ~2h compute | Only if Position B |
| Re-run OOS/SAA eval on v2 seeds | Table 4-2 OOS column on v2 | ~1h compute | Only if Position B |
| Re-run SAA convergence on v2 | Fig 3 on v2 | ~1h compute | Only if Position B |

---

## 3. DSS Dashboard — Manager-Focused Redesign

This is the primary deliverable. The current app is a technical explorer.
The upgraded app must answer the questions a disaster response coordinator
actually asks when looking at it.

### 3.1 The manager's mental model

The coordinator's decision horizon has two stages:

**Before disaster (Stage 1 — today):**
> "Which X hubs do I build / designate? How much stock do I pre-position at each?"

**During/after disaster (Stage 2 — scenario-dependent):**
> "Given that the flood hit here with this severity — which hubs are still safe?
> Which villages do I send to each hub? By road, boat, or helicopter?
> Am I going to run out of stock at any hub?"

The current UI shows Z1/Z2 numbers and a map, but doesn't frame it this way.
The upgrade must make both stages legible at a glance.

### 3.2 Redesigned Tab 1 layout

```
┌─ Solution Explorer ─────────────────────────────────────────────────────┐
│                                                                          │
│  STAGE 1 DECISION (fixed across all scenarios)                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  Established Hubs: 8 / 20 candidates                             │   │
│  │  [H3] Tam Kỳ Logistics   100%▓▓▓▓▓▓▓▓▓▓  pre-position: 82%    │   │
│  │  [H9] A Sáp Helipad       80%▓▓▓▓▓▓▓▓░░  pre-position: 63%    │   │
│  │  [H14] Đà Nẵng Airport    60%▓▓▓▓▓▓░░░░  pre-position: 47%    │   │
│  │  ...                                                              │   │
│  │  Total logistics cost: $4.79M  ·  [click Pareto to compare]     │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  STAGE 2 RESPONSE  ── Scenario: [● Mild  ○ Severe  ○ Extreme]          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  Active hubs: 8 / 8   Inactive (flooded): 0                      │   │
│  │                                                                    │   │
│  │  Demand served: 100 communes                                      │   │
│  │  🚚 Road: 91   🚤 Boat: 4   🚁 Helicopter: 5                    │   │
│  │                                                                    │   │
│  │  Equity (worst deprivation): 41,828 person-hours                 │   │
│  │  vs best-cost plan:          +2.4% deprivation premium           │   │
│  │  vs best-equity plan:        −$1.1M logistics saving             │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  [Pareto Front]                    [Map]                                │
│  [click point to explore plan]     [scenario response map]              │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Feature D1 — Stage-1 Decision Panel `[P0]`

**What:** A new top section in Tab 1 (above the Pareto scatter) showing the
Stage-1 decision of the selected solution as an **actionable brief**:

- **Hub roster table** with columns:
  | Hub | Location name | Capacity (kg) | Pre-position ratio R[k] | Pre-position qty (kg) |
  — Capacity from `instance["hub_candidates"][k]["capacity"]` (verify field name)
  — Pre-position ratio from `solution.R[k]`
  — Pre-position qty = `R[k] × capacity_k`

- **Visual capacity bar** for each hub: a simple progress bar showing R[k]
  as a fill fraction. Immediately communicates "how full should this hub be?"

- **Logistics cost headline**: `Z1 = $X.XX M`

- **Trade-off position**: brief text showing where this solution sits on the
  Pareto front:
  - "Cost-focused: $X.X M logistics, Y,YYY person-hrs deprivation" (near cost extreme)
  - "Balanced (knee): $X.X M, Y,YYY (recommended)" (at knee point)
  - "Equity-focused: $X.X M, Y,YYY" (near equity extreme)
  Auto-detect position by comparing Z2 to the front's range.

**Data sources (all already available):**
- `solution.X[k]`, `solution.R[k]` — already parsed
- Hub capacity: from instance JSON (field name TBD — see Q1)
- Z1 range: `min/max([s.Z1 for s in solutions])`

### 3.4 Feature D2 — Stage-2 Scenario Response Panel `[P0]`

**What:** The existing KPI section, restructured into a **scenario briefing
card** with clearer managerial framing:

**Hub safety status:**
```
Scenario: Severe  ·  χ = 0.70
Active hubs: 5 / 8     ⚠️ FLOODED: H1 (Huế Warehouse), H15 (Quảng Trị Depot), H16 (Phong Điền)
```
— Hub name, not just index. Flooded hubs highlighted in amber/red.
— Derived from `r_ks > chi` test on instance risk data.

**Demand routing summary:**
```
100 communes served
  🚚 Road:        91  communes  (average travel: X hrs)
  🚤 Boat:         4  communes  (water route active)
  🚁 Helicopter:   5  communes  (air-only accessible)

  ⚠️ 3 communes switch to helicopter this scenario (road blocked)
```
— "Switch" count = communes with different mode from Mild scenario (requires
  comparing two scenario flows — add to F implementation notes).

**Equity metric framed for managers:**
```
Worst-served commune: [name], deprivation index Y,YYY
Best-served commune:  [name], deprivation index Z
Recommended plan saves 12.8% deprivation vs cheapest plan
at a $1.1M logistics cost premium
```
— Block 1 query keys `deprivation_reduction_pct` and `cost_premium_pct` from
  `narrative_data.json` (when available).

### 3.5 Feature D3 — Hub Detail Drilldown `[P0]`

**What:** Click on a hub in the map → sidebar shows a hub detail panel:

```
H9 — A Sáp Helipad
────────────────────────────────────
Stage-1 decision:  ✅ ESTABLISHED
Pre-positioned:    63% capacity (3,150 kg)
Flood risk (Mild):    0.31 — SAFE
Flood risk (Severe):  0.58 — SAFE
Flood risk (Extreme): 0.74 — ⚠️ INACTIVE (r > χ=0.70)

Serves in Mild scenario:
  Demand communes: 12
  Modes: 🚚 Road×9  🚁 Helicopter×3
  Highest-demand commune: Thôn X (2,400 persons)

Serves in Severe scenario:
  Demand communes: 14  (+2 from H1 which flooded)
  Modes: 🚚 Road×11  🚁 Helicopter×3
```

**Implementation:** In `build_map()`, Folium marker `popup` for each open hub.
The popup HTML is built from `flow_sc.demand_assignments` filtered to this hub.
Hub risk values from `inst_raw["scenarios"][s]["risk"][hub_global_idx]`.

This is the biggest "manager insight" feature — turning abstract X_k and mode
vectors into named-location operational orders.

### 3.6 Feature D4 — Side-by-Side 3-Scenario Map `[P1]`

**What:** Toggle above the map:
```
Map view:  ● Single scenario   ○ Compare all three
```
Three Folium maps in `st.columns([1,1,1])` at `height=420`.
Headers: "🌊 Mild (p=0.60)", "⚠️ Severe (p=0.30)", "🔴 Extreme (p=0.10)".

Immediately shows the manager what changes between scenarios — which hubs
go inactive, which routes shift to boat/helicopter — without toggling.

### 3.7 Feature D5 — Scenario Robustness Badge `[P1]`

**What:** For each Pareto solution in the scatter, add a small robustness badge
in the hover tooltip:

```
Z1 = $4.8M  Z2 = 41,828
Hubs active: Mild 8 / Severe 5 / Extreme 4
Modes change: Mild→Severe: +3 boat, -3 road
              Mild→Extreme: +3 air, -6 road
```

This gives the manager a quick robustness read without clicking into the
solution. Requires computing the scenario delta at load time across all
solutions. Cache per solution index.

### 3.8 Feature D6 — Static Input View (Population & Risk) `[P1]`

**What:** In Tab 2 Input Dataset, add:
- **Population circles:** radius ∝ `base_pop`, tooltip shows value. Lets
  managers see which communes are densely populated.
- **Intrinsic risk layer:** heatmap colour overlay on demand nodes showing
  inherent flood susceptibility before any scenario.
- **View mode toggle:** "Static (population + geography)" vs current
  "Scenario-dependent (risk + demand + accessibility)."

Field name verification needed before implementing (see Open Questions).

### 3.9 Feature D7 — Export for Operations `[P2]`

**What:** "Export Decision Brief" button that generates a formatted HTML/PDF
report of the selected solution:

```
FLOOD RELIEF OPERATIONAL BRIEF
Plan: Solution 7 of 23 (Balanced — knee point)
Generated: 2026-06-19

STAGE 1 — Pre-Disaster Preparation
  8 hubs to establish:
  • H9  A Sáp Helipad         Pre-position 3,150 kg (63%)
  • H14 Đà Nẵng Airport Hub   Pre-position 2,800 kg (47%)
  ...

STAGE 2 — Scenario Response Plans
  [Mild scenario] Active: 8/8 hubs ...
  [Severe scenario] Active: 5/8 hubs — H1, H15, H16 inactive ...
  [Extreme scenario] Active: 4/8 hubs — H1, H15, H16, H3 inactive ...
```

Use Python's `jinja2` + `weasyprint` or just produce clean HTML with an
`st.download_button`. Defer if scope tight — not needed for thesis defense
but adds DSS credibility.

---

## 4. Experiments Tab (Lightweight Integration)

Tab 3 "📈 Experiments & Results" is a thin wrapper around existing scripts.
Its job is: **configure paths → run → display outputs**. No analysis
re-implementation.

### 4.1 Config panel

```
Instance path:   [data/cv/v2/cv_large_drnd.json    ] [Browse]
Results dir:     [results/exp2/v2/                 ] [Browse]  ← or results/exp2/ for v1
Flows dir:       [results/exp2/v2/flows            ] [Browse]
Output dir:      [results/exp2/v2/                 ] [Browse]
```
Stored in `st.session_state`. Defaults point to v2 if directory has files,
else fall back to v1.

### 4.2 Pipeline runner

```
Experiment                          Status    Action
──────────────────────────────────────────────────────────────
EXP-1  CV-Small baseline comparison  ✅       [▶ Re-run]
       → exp1_evaluate_cv_small.py
       Output: results/exp1/cv_small_metrics.csv

EXP-2  CV-Large 20-seed suite        ✅ (v1)  [▶ Run on v2]
       → run_exp2_case_study.sh
       20 seeds × 3 algorithms on configured instance

EXP-3  OOS/SAA multi-seed eval       ✅ (v1)  [▶ Run on v2]
       → exp_oos_multiseed.py + exp2_analyze_saa_oos.py

EXP-4  SAA N-sensitivity             ✅       [▶ Re-run]
       → exp_saa_convergence.py

EXP-5  Extract narrative_data.json   ⏳       [▶ Run]
       → narrative_data.py (new — §5)
```

Status = ✅ if primary output file exists (mtime check), ⏳ otherwise.
Each button calls subprocess inside `st.status()` with live log streaming.
"Re-run" always available even when ✅ (allows forced refresh).

### 4.3 Figure display

After pipeline runs, Tab 3 shows:
- **Fig 1 Pareto:** inline PNG from `exp2_pareto_tradeoff.pdf` (via `pdf2image`)
  or fallback download button.
- **Table 4-1:** `st.dataframe` from `cv_small_metrics.csv`, best value green.
- **Fig 2 Map:** inline PNG from `cv_large_map_detailed.pdf`.
- **Fig 3 SAA:** inline PNG from `saa_convergence.pdf`.
- **Fig 4-5 Hub Freq:** inline PNG from `*_hub_freq.pdf`.
- **Fig 4-6 Risk Heatmap:** live Plotly (pure instance data — no file needed).
- **Narrative export:** if `narrative_data.json` exists, show key scalars table
  + download button.

New module: `visualizer/experiments_view.py` — all Tab 3 rendering.

---

## 5. New Script: `narrative_data.py`

This is the only genuinely new analysis code (the rest wires existing scripts).

**Purpose:** Extract every Block 1–10 thesis query key into `narrative_data.json`.

**Reuses:** `solution_loader.load_results_from_folder()`,
`deduplicate_solutions()`, and the already-parsed `solution.R` vector.

**CLI:**
```bash
.venv/bin/python3 visualizer/narrative_data.py \
    --results  results/exp2/v2 \        # or results/exp2 for v1
    --flows    results/exp2/v2/flows \
    --instance data/cv/v2/cv_large_drnd.json \
    --out      narrative_data.json
```

**Key computations:**
- Pool all PB-NSGA JSONs in `--results`, filter `CV == 0`, non-domination
  filter → combined ND front.
- Knee = Tchebycheff (`argmin_i max(Z1_norm[i], Z2_norm[i])`).
- `active_hub_count[s]`: hubs where `X[k]==1 AND r_ks ≤ chi`. Risk from
  `instance["scenarios"][s]["risk"][hub_global_idx[k]]`.
- `inv_fill_pct[k]`: `solution.R[k] * 100` (Stage-1 ratio, already in JSON).
- `hub_selection_frequency[k]`: fraction of combined ND-front solutions with
  `X[k]==1`.
- Modal counts and air attribution: from flow file of the knee solution.
- Validation assertions:
  ```python
  assert knee_CV == 0.0
  assert modal_road[s] + modal_water[s] + modal_air[s] == total_demand_nodes
  ```

**Output schema** (same as `plans_dss_system.md §PART 2`):
```json
{
  "deprivation_reduction_pct": <float>,
  "cost_premium_pct": <float>,
  "knee_Z1": <float>, "knee_Z2": <float>, "knee_seed": <int>, "knee_CV": 0.0,
  "open_hub_count": <int>, "open_hub_list": [...],
  "reactive_hub_count": {"mild":0,"severe":0,"extreme":0},
  "lateral_link_count": {"mild":0,"severe":0,"extreme":0},
  "active_hub_count": {"mild":<int>,"severe":<int>,"extreme":<int>},
  "inactive_hub_names": {"mild":[],"severe":[...],"extreme":[...]},
  "hub_risk_values": {"mild":{...},"severe":{...},"extreme":{...}},
  "modal_road": {...}, "modal_water": {...}, "modal_air": {...},
  "total_demand_nodes": 100,
  "air_serving_hubs": {"mild":[...],"severe":[...],"extreme":[...]},
  "inv_fill_pct": {"H0":<f>, ...},
  "chi": 0.70,
  "hub_selection_frequency": {"H0":<f>, ...},
  "total_solutions_pooled": <int>,
  "seeds_included": [...],
  "dataset_version": "v2",
  "generated_at": "<ISO>"
}
```

---

## 6. Implementation Plan

### 6.1 New files

| File | What | Effort |
|---|---|---|
| `visualizer/narrative_data.py` | §5 extraction script | ~1 day |
| `visualizer/experiments_view.py` | Tab 3 rendering | ~0.5 day |
| `visualizer/verify_solution.py` | Z1 sanity + coverage check | ~0.5 day |

### 6.2 Modified files

| File | Changes | Effort |
|---|---|---|
| `visualizer/app.py` | Add Tab 3; Stage-1 panel (D1); Stage-2 restructure (D2); side-by-side toggle (D4); map popup hook for D3 | ~1 day |
| `visualizer/map_view.py` | Hub popup HTML for D3 drilldown | ~0.5 day |
| `visualizer/dataset_view.py` | Population + intrinsic risk layers (D6) | ~0.5 day |
| `visualizer/pareto_view.py` | Add robustness badge in hover (D5) | ~0.5 day |

### 6.3 Files NOT to modify

- `src/scripts/*.py` — all experiment scripts are correct as-is.
- `visualizer/preprocess_flows.py` — MCF limitation labeled in UI (D2), not fixed.
- `src/solver/decoder.hpp` — out of scope.

### 6.4 Build order

1. **`narrative_data.py`** — resolve Open Questions first; this unblocks D2 narrative numbers.
2. **Stage-1 panel (D1)** — small; just display R[k] and capacity; instant manager value.
3. **Stage-2 restructure (D2)** — hub safety status + mode framing.
4. **Hub popup drilldown (D3)** — biggest impact; requires flow data in `build_map()`.
5. **Tab 3 experiments wrapper (§4)** — display existing PDFs + CSV.
6. **Side-by-side map (D4)**.
7. **Static input layers (D6)** — after Q1/Q2 resolved.
8. **Robustness badge (D5)** — after D4.
9. **Export brief (D7)** — last, P2.

---

## 7. Open Questions (resolve by reading instance JSON before coding)

| # | Question | Blocks |
|---|---|---|
| **Q1** | Field name for hub capacity in instance JSON? Check `instance["hub_candidates"][k]["capacity"]` vs `instance["nodes"]["capacity"]` vs another path. | D1, `narrative_data.py` |
| **Q2** | Field names for `base_pop` and `intrinsic_risk` per node in v2 instance? | D6 |
| **Q3** | Does `flow_sc.demand_assignments` contain the hub index each demand is assigned to? If yes, D3 drilldown is trivial. | D3 |
| **Q4** | Does `flow_sc.origin_assignments` exist? (Needed for Z1 re-derivation in verifier.) | verify_solution.py |
| **Q5** | v1 or v2 for thesis results? (See §2.) | Everything |

**Answer Q1–Q4 in one pass** by running:
```bash
python3 -c "
import json
d = json.load(open('data/cv/v2/cv_large_drnd.json'))
print('top-level keys:', list(d.keys()))
# hub info
hubs = d.get('hub_candidates') or d.get('hubs') or []
if hubs: print('hub[0] keys:', list(hubs[0].keys()) if isinstance(hubs[0], dict) else 'list')
# node info
nodes = d.get('nodes', {})
print('nodes keys:', list(nodes.keys()) if isinstance(nodes, dict) else type(nodes))
"
```

---

## 8. Acceptance Criteria

### DSS (manager usability)
- [ ] Stage-1 panel shows hub list with name, pre-position ratio, and kg qty.
- [ ] Stage-2 panel names flooded hubs explicitly (not just count).
- [ ] Hub popup shows which communes are served + mode breakdown per scenario.
- [ ] Side-by-side 3-scenario map loads without error for any selected solution.
- [ ] All mode count displays carry MCF disclaimer tooltip.

### Thesis evidence pipeline
- [ ] `narrative_data.py` produces valid JSON with all Block 1–10 keys.
- [ ] `knee_CV == 0.0` and modal counts sum to 100.
- [ ] Tab 3 displays `cv_small_metrics.csv` as a styled dataframe.
- [ ] Tab 3 renders at least 3 of the 5 existing PDF figures (inline or download).

### Experiments (if Position B chosen — v2 re-run)
- [ ] 20 seeds run on v2 CV-Large and stored in `results/exp2/v2/`.
- [ ] `exp2_analyze_case_study.py` re-run on v2 results dir, new PDFs committed.
- [ ] OOS/SAA eval re-run on v2 seeds.
- [ ] `narrative_data.py` reads v2 seeds and produces `narrative_data.json`.

### Commit discipline (CLAUDE.md §1)
- [ ] Code `.py` commits separate from result `.json` commits.
- [ ] `doc_dataset_methodology.md` updated only if Q1/Q2 reveal undocumented field names.
