# PART 1 - Extension Plans
To-do list
- làm cho processor.py match tuyệt đối với decoder.hpp
- dán query key từ Claude chat xuống để Claude Code aware được và wire up đầy đủ pipeline run thí nghiệm
- Nâng cấp phần “Run Solver”. Thêm button mới “Run Experiments" để chạy full thí nghiệm, và thêm một tab "experiments, statistical figures".
    + exp 1: baseline comparison
    + exp 2: case study analysis (proposed algorithm on the synthetic dataset)
- Verifier: checker để đảm bảo decoder tạo ra solution valid và có giá trị Z1 Z2 derived khớp với của solution output.
- Mở rộng/ nâng cấp UI của DSS: Cho phép view 3 scenario map side-by-side (có thể toggle view mode). Và cho phép swith nhanh giữa Input visualizer và Solution output (or even overlapped display của Input và Solution)
- Input vis: thêm option để view dữ liệu tĩnh (không phụ thuộc scenario): dân số, intrinsic risk, accessibility matrix (explained as Delaunay).
- Dataset Methodology: Cần phải sample thêm nhiều scenarios đa dạng hơn để model không bị overfit cấu hình Hub tối ưu.
- Non-demand nodes: Trong trường hợp Mild, một số hộ dân (demand nodes) ít hoặc thậm chí không bị ảnh hưởng. Vậy thì không cần consider và assign (clutter). Tuy nhiên formulation constraint mỗi demand assign vào exactly one hub. Ta nên resolve điều này như thế nào? Chỉ fix ở layer UI/ report cuối cùng (ignore những node risk thấp — too safe in the scenario — negligble number of demand. This requires to remove max(0.05, formula) calculation của Demand). Hay là phải fix từ algorithm và solver?
- Unsafe supply? Is it modeled?
- Big issue: the demand may have LOWER risk compared to the HUB. Why even bother to transport from the demand to the hub at all?? (chi = 0.7). r_u and r_v >= 0.4 is enough to trigger inundation.
    1. Data: HUB must be stubbornly hardened and strong.
    2. Modeling/ Decision problem

---

NARRATIVE: Mental Model — The full story
. Thiên tai: khốc liệt, dị thường, gây thiệt hại to lớn, không thể đoán trước. Không nằm trong bất cứ kịch bản nào?
—> Nên tăng cường vào khâu Quy hoạch và Chuẩn bị trước thảm hoạ xảy ra. Chủ động và chuẩn bị tối đa cho mọi tình huống có thể.
+ Dẫn nhập: Mô hình hub-and-shelter, và HLP trong một số case study thực tế:
	Động đất Earthquakes tại Iranian và Indonesian —> Phân tích, dựng heatmap, đề xuất chọn điểm đặt trạm
       PhD thesis của cô Sunarin: EMF
	Disaster Relief Network Design
=> Quy hoạch để chọn vị trí xây dựng Rescue Station
TSSP. Two-stage Stochastic Programming.
Stage 1: SP, chạy các kịch bản scenario-based để “train mô hình”, dùng GA tiến hoá để tìm ra cấu hình
tối ưu và robust nhất, cover được nhiều kịch bản khác nhau có thể.
	Drawback: Overrfitting vào probability distribution của Input generator (synthetic dataset)
Stage 2: on-demand, scenario-based. Tận dụng sức mạnh/ sự linh hoạt của Decoder để decode
ra meaningful actionable insights cho mỗi tình huống:
Epicenter rốn lũ trong trường hợp này nằm ở những đâu? Update lại Risk heatmap của scenario-based.
Ưóc lượng demand dựa trên population. Gắn cảm biến mực nước gửi tín hiệu định kỳ/ thụ động 
﻿về trung tâm mà không cần phải đợi đến tín hiệu SOS của ngừoi dân. (caveat: xác nhận/ confirm
﻿or survivorship bias)
Hub nào bị sụp?
Di chuyển cụm dân cư (demand) nào vào Hub nào? Bằng phương tiện (modal) gì?

Out-of-Sample validation

Prior to stage 1: Những gì có thể biết được/ tính toán được:
Đặc trưng vùng miền và risk heatmap, 
Area
Population


# PART 2 - Query keys -- request for experiments figures for paper and THESIS writing

TL;DR: Please review the full experimental setup pipeline already standardized and available for CITA 2026 camera-ready paper (accepted for presentation).

----

Here is a complete inventory of every variable, figure, and data point the passage requires, organized by where it appears in the text, with a proposed query key for your script.

---

## BLOCK 1 — Pareto Front Summary (equity improvement claim)

| Query Key | What it is | Where used |
|---|---|---|
| `Z2_cost_extreme_20seed` | Z2 value at the cost-minimizing extreme of the combined 20-seed ND front | "reducing worst-case deprivation from X..." |
| `Z2_equity_extreme_20seed` | Z2 value at the equity-minimizing extreme of the combined 20-seed ND front | "...to Y" |
| `deprivation_reduction_pct` | `(Z2_cost_extreme - Z2_equity_extreme) / Z2_cost_extreme * 100` | "reduces worst-case deprivation by ~X%" |
| `cost_premium_pct` | `(Z1_equity_extreme - Z1_cost_extreme) / Z1_cost_extreme * 100` on 20-seed front | "at a logistics cost premium of X%" |

---

## BLOCK 2 — Knee-Point Solution Identity

| Query Key | What it is | Where used |
|---|---|---|
| `knee_Z1` | Z1 of the selected knee-point solution (dollars) | "Z1 = $X" |
| `knee_Z2` | Z2 of the selected knee-point solution | "Z2 = Y" |
| `knee_seed` | Which seed the knee-point comes from | Figure caption provenance |
| `knee_solution_index` | Index within that seed's Pareto front | Audit traceability |
| `knee_CV` | Constraint violation of the knee-point (must = 0) | Feasibility confirmation |

---

## BLOCK 3 — First-Stage Hub Decisions

| Query Key | What it is | Where used |
|---|---|---|
| `open_hub_count` | Total number of established hubs (X_k = 1) | "establishes exactly X planned hubs" |
| `open_hub_list` | Ordered list of `{hub_index: k, hub_name: str}` for all established hubs | Named hub list in prose |
| `reactive_hub_count_per_scenario` | Dict `{mild: int, severe: int, extreme: int}` of reactive hubs opened | "zero reactive hubs opened" confirmation |
| `lateral_link_count_per_scenario` | Dict `{mild: int, severe: int, extreme: int}` of lateral transshipment links used | "zero lateral links" confirmation |

---

## BLOCK 4 — Per-Scenario Hub Activity (risk filter output)

For each scenario in `{mild, severe, extreme}`:

| Query Key | What it is | Where used |
|---|---|---|
| `active_hub_count_{scenario}` | Number of established hubs with `r_ks <= chi` (active) | "X active hubs in scenario Y" |
| `inactive_hub_list_{scenario}` | List of `{hub_index: k, hub_name: str}` deactivated by risk | Named hubs that go inactive |
| `active_hub_list_{scenario}` | List of `{hub_index: k, hub_name: str}` that remain active | Named surviving hubs |
| `hub_risk_value_{k}_{scenario}` | Actual `r_ks` value for each hub in each scenario | Risk threshold comparison prose |

---

## BLOCK 5 — Modal Demand Counts (per scenario, knee-point)

| Query Key | What it is | Where used |
|---|---|---|
| `modal_road_{scenario}` | Number of demand nodes assigned via road mode | Road counts 91→91→85 |
| `modal_water_{scenario}` | Number of demand nodes assigned via water mode | Water counts 4→7→7 |
| `modal_air_{scenario}` | Number of demand nodes assigned via air mode | Air counts 5→2→8 |
| `total_demand_nodes` | Total demand node count (sanity check: road+water+air must equal this) | Internal consistency |

---

## BLOCK 6 — Air Mode Hub Attribution (per scenario)

This block is needed to explain *which active hub* provides helicopter service in each scenario and why air counts change non-monotonically.

| Query Key | What it is | Where used |
|---|---|---|
| `air_serving_hub_list_{scenario}` | List of `{hub_index: k, hub_name: str, air_demand_count: int}` — one entry per hub that serves ≥1 air-mode demand node | "Binh Son Warehouse serves 5 nodes; A Sap Helipad continues..." |
| `air_demand_nodes_{scenario}` | List of demand node indices/names served by air in each scenario | Cross-check with map figure |

---

## BLOCK 7 — Per-Hub Inventory Fill (knee-point, for figure labels)

| Query Key | What it is | Where used |
|---|---|---|
| `inv_fill_pct_{k}_{scenario}` | Inventory fill fraction `R_k * kappa_k` as a percentage for each active hub in each scenario | Figure 4-4 hub label annotations (e.g., H9 [59%]) |

---

## BLOCK 8 — Risk Threshold Constant

| Query Key | What it is | Where used |
|---|---|---|
| `chi` | Safety threshold parameter value | "$r_{ks} \leq \chi = X$" inline |

---

## BLOCK 9 — Figure 4-4 Metadata

| Query Key | What it is | Where used |
|---|---|---|
| `fig4_source_file` | Filename of the JSON solution used to render Figure 4-4 | Figure caption / audit trail |
| `fig4_scenario_list` | Ordered list of scenarios shown `[mild, severe, extreme]` | Figure caption |
| `fig4_scenario_probs` | `{mild: 0.60, severe: 0.30, extreme: 0.10}` | Figure caption |

---

## BLOCK 10 — Derived Narrative Assertions (computed, not raw)

These are the claims the prose makes that should be computed by the script and injected as formatted strings, not hardcoded:

| Derived Variable | Formula | Target sentence |
|---|---|---|
| `deprivation_reduction_pct` | Block 1 | "reduces worst-case deprivation by ~{X}%" |
| `cost_premium_pct` | Block 1 | "at a logistics cost premium of {X}%" |
| `hubs_deactivated_severe` | `open_hub_count - active_hub_count_severe` | "three hubs ... are deactivated" |
| `hubs_deactivated_extreme` | `open_hub_count - active_hub_count_extreme` | "four hubs ... are deactivated" |
| `air_delta_mild_to_severe` | `modal_air_severe - modal_air_mild` | directional claim on air in Severe |
| `air_delta_severe_to_extreme` | `modal_air_extreme - modal_air_severe` | "air surges to X nodes" |
| `water_delta_mild_to_severe` | `modal_water_severe - modal_water_mild` | "water absorbs X additional nodes" |
| `compensating_air_hub_extreme` | Hub name with largest `air_demand_count` in Extreme | "Binh Son Warehouse assumes staging responsibility for X nodes" |
| `compensating_air_hub_count_extreme` | That hub's `air_demand_count` in Extreme | Same sentence |

---

## Recommended Script Output Format

The script should produce a single JSON file, for example `narrative_data.json`, with this flat structure so the thesis template can substitute directly:

```json
{
  "Z2_cost_extreme_20seed": 46551,
  "Z2_equity_extreme_20seed": 40585,
  "deprivation_reduction_pct": 12.8,
  "cost_premium_pct": 23.4,
  "knee_Z1_dollars": 4790124,
  "knee_Z1_millions": 4.8,
  "knee_Z2": 41828,
  "knee_CV": 0.0,
  "open_hub_count": 8,
  "open_hub_list": ["Da Nang Airport Hub", "Tam Ky Logistics Hub", "..."],
  "reactive_hub_count": {"mild": 0, "severe": 0, "extreme": 0},
  "lateral_link_count": {"mild": 0, "severe": 0, "extreme": 0},
  "active_hub_count": {"mild": 8, "severe": 5, "extreme": 4},
  "inactive_hub_names": {
    "mild": [],
    "severe": ["Da Nang Airport Hub", "Tam Ky Logistics Hub", "Phuoc Son Helipad"],
    "extreme": ["Da Nang Airport Hub", "Tam Ky Logistics Hub", "Phuoc Son Helipad", "Quang Ngai Port Hub"]
  },
  "modal_road": {"mild": 91, "severe": 91, "extreme": 85},
  "modal_water": {"mild": 4, "severe": 7, "extreme": 7},
  "modal_air": {"mild": 5, "severe": 2, "extreme": 8},
  "total_demand_nodes": 100,
  "air_serving_hubs": {
    "mild": [{"name": "...", "count": 3}, {"name": "...", "count": 2}],
    "severe": [{"name": "A Sap Helipad", "count": 2}],
    "extreme": [{"name": "Binh Son Warehouse", "count": 5}, {"name": "A Sap Helipad", "count": 3}]
  },
  "inv_fill_pct": {
    "mild":    {"H0": 58, "H1": 23, "H3": 46, "H9": 59, "H12": 13, "H14": 7, "H15": 72, "H16": 77},
    "severe":  {"H3": ..., "H9": ..., "H12": ..., "H14": ..., "H15": ...},
    "extreme": {"H3": ..., "H9": ..., "H12": ..., "H14": ...}
  },
  "chi": 0.70,
  "hub_risk_values": {
    "mild":    {"H0": ..., "H1": ..., ...},
    "severe":  {"H0": ..., "H1": ..., ...},
    "extreme": {"H0": ..., "H1": ..., ...}
  },
  "fig4_source_file": "solution_2.json",
  "fig4_scenario_probs": {"mild": 0.60, "severe": 0.30, "extreme": 0.10}
}
```

Once you get this JSON back from the script, I can auto-substitute every value into the passage and produce the final version with zero hardcoded claims.


-----

Reading the chapter carefully before prescribing. Let me map every figure, table, and numerical claim to its data source first, then flag what the dataset upgrade invalidates.

---

## PART A — Complete Figure & Table Inventory

### Figure 4-1 | Combined Pareto Fronts
**What it shows:** Left panel: CV-Small, all algorithms + MILP true front. Right panel: CV-Large power scale, 20 runs per algorithm.

**Experiment that produces it:** Algorithmic benchmark run — CV-Small (20 runs × 4 algorithms + 1 MILP sweep) and CV-Large (20 runs × 3 algorithms).

**Dataset dependency:** 🔴 FULLY AFFECTED. All node coordinates, arc accessibilities, costs, risk values, scenario parameters feed directly into the objective values Z1/Z2. The entire objective-space distribution will shift with the new dataset. The figure must be regenerated from scratch.

**Specific claims in prose tied to this figure that must be re-verified:**

| Claim | Location |
|---|---|
| PB-NSGA CV-Large Z1 ∈ [\$4.3M, \$6.8M] | §4.2.1 body |
| PB-NSGA CV-Large Z2 ∈ [41K, 45K] | §4.2.1 body |
| GWO-HD extends to Z1 = \$26M | §4.2.1 body |
| VNS-TS stranded at Z1 = \$81M, Z2 ≈ 150K | §4.2.1 body |
| VNS-TS failure confined to cost-efficient tail Z1 < 1.5×10⁶ on CV-Small | §4.2.1 body |

---

### Table 4-1 | CV-Small Baseline Comparison
**What it shows:** HV, IGD+, CPU time for Greedy, VNS-TS, GWO-HD, MILP, PB-NSGA on CV-Small.

**Experiment that produces it:** Benchmark run on CV-Small, same as Figure 4-1 left panel.

**Dataset dependency:** 🔴 FULLY AFFECTED. All metric values are relative to the combined reference front, which is constructed from objective space values that depend on the dataset. Even if relative ordering is preserved, absolute HV/IGD+ values will change.

**Derived claims tied to this table:**

| Claim | Formula | Status |
|---|---|---|
| "4× runtime advantage over MILP" | 4.9 / 1.1 = 4.45× | 🔴 Re-verify |
| "50× speedup over VNS-TS" | 60.0 / 1.1 = 54.5× | 🔴 Re-verify |

---

### Table 4-2 | CV-Large Performance + OOS Feasibility
**What it shows:** HV, IGD+, OOS feasibility %, CPU time for VNS-TS, GWO-HD, PB-NSGA on CV-Large.

**Experiment that produces it:** Two separate experiments:
- (A) Standard 20-run benchmark on CV-Large training scenarios
- (B) OOS validation — first-stage decisions (x̂, q̂) re-evaluated on 10 adversarial hold-out scenarios

**Dataset dependency:** 🔴 FULLY AFFECTED for (A). 🔴 ALSO AFFECTED for (B) because the OOS scenarios are drawn from the same upgraded scenario-generation methodology.

**Note:** The OOS experiment requires the hold-out scenario set to be generated and fixed *before* any algorithm runs, then kept completely disjoint from training. If the scenario-generation method is changing, the OOS set must be regenerated under the new method and locked. This is a procedural requirement, not just a data re-run.

**Derived claims:**

| Claim | Formula | Status |
|---|---|---|
| "20.7× runtime advantage over VNS-TS" | 180.6 / 8.7 = 20.76× | 🔴 Re-verify |
| PB-NSGA 100% OOS feasibility | Experiment (B) | 🔴 Re-verify |
| GWO-HD 96.4% OOS feasibility | Experiment (B) | 🔴 Re-verify |
| VNS-TS 97.8% OOS feasibility | Experiment (B) | 🔴 Re-verify |

---

### Figure 4-2 | SAA Scenario-Count Sensitivity
**What it shows:** Z2 standard deviation vs number of scenarios N (3 to 30), 10 replications, exact enumeration on CV-Small.

**Experiment that produces it:** Dedicated SAA sensitivity study — enumerate CV-Small exactly at each N ∈ {3, 5, 10, 15, 20, 30} (or similar grid), 10 random replications each.

**Dataset dependency:** 🔴 FULLY AFFECTED. The flood vulnerability scores, spatial layout, and scenario-generation probability distribution all feed into what constitutes a "mild/severe/extreme draw." If the distribution method changes, the entire sensitivity curve changes. The ±110k and ±30k std-dev values, the peak at N=5, and the equivalence claim ("N=3 achieves stability of N≈10 random draws") all must be re-derived.

**Critical procedural note:** This figure justifies the choice of the three-profile stratified design. If the new dataset uses a different scenario generation method, the justification itself may need to change. The figure and the prose argument must be co-designed with the new method.

**Specific claims:**

| Claim | Status |
|---|---|
| Z2 std dev ±110k at N=3 | 🔴 Re-derive |
| Z2 std dev ±30k at N=30 | 🔴 Re-derive |
| Transient peak at N=5 | 🔴 Re-verify |
| Stratified N=3 ≈ random N≈10 | 🔴 Re-derive |

---

### Figure 4-3 | Interactive Pareto Front UI Screenshot
**What it shows:** Screenshot of the Streamlit DSS interface displaying the Pareto front and KPI panel.

**Experiment that produces it:** No separate experiment — UI screenshot taken from live DSS after loading new results. However, the KPI values visible in the screenshot (Z1 range, Z2 range, selected knee-point) are all dataset-dependent.

**Dataset dependency:** 🟡 SCREENSHOT ITSELF is regenerated trivially. The numbers displayed are 🔴 AFFECTED.

**Claims tied to this figure:**

| Claim | Status |
|---|---|
| "3.5× equity improvement" | ❌ ALREADY KNOWN WRONG — remove |
| "worst-case deprivation ~150,000" | ❌ ALREADY KNOWN WRONG — remove |
| "~43,000 at equity extreme" | 🔴 Re-verify from new front |
| "<25% cost premium" | 🔴 Re-verify |
| Knee-point Z1=\$4.8M, Z2=41,828 | 🔴 Re-verify — this is solution-specific |

---

### Figure 4-4 | Cross-Scenario Knee-Point Network Map
**What it shows:** Three-panel map (Mild / Severe / Extreme) for CV-Large knee-point solution, showing hub activity, demand-hub assignments, modal routing, reactive hub count, lateral link count.

**Experiment that produces it:** Not an independent experiment — it is the visualization of one specific solution from the CV-Large 20-run benchmark. The knee-point must be selected from the new Pareto front after re-running.

**Dataset dependency:** 🔴 FULLY AFFECTED. The geographical layout, hub names, accessibility arcs, and risk values all change with the new dataset. Hub activity per scenario (which hubs go inactive) depends on updated r_ks values.

**Claims currently in text that must be re-verified from new solution JSON:**

| Claim | Query key | Status |
|---|---|---|
| 8 planned hubs established | open\_hub\_count | 🔴 Re-verify |
| All hub names | open\_hub\_list | 🔴 Re-verify |
| 0 reactive hubs all scenarios | reactive\_hub\_count\_{scenario} | 🔴 Re-verify |
| 0 lateral links all scenarios | lateral\_link\_count\_{scenario} | 🔴 Re-verify |
| Active hub count: 8/5/4 | active\_hub\_count\_{scenario} | 🔴 Re-verify |
| Specific inactive hubs in Severe | inactive\_hub\_names\_severe | 🔴 Re-verify |
| Specific inactive hubs in Extreme | inactive\_hub\_names\_extreme | 🔴 Re-verify |
| Modal counts 91/91/85 road, 4/7/7 water, 5/2/8 air | modal\_{mode}\_{scenario} | 🔴 Re-verify |
| Air peaks in Extreme at 8 nodes | modal\_air\_extreme | 🔴 Re-verify |
| Binh Son Warehouse compensates | compensating\_air\_hub\_extreme | 🔴 Re-verify |

---

### Figure 4-5 | Hub Selection Frequency
**What it shows:** Bar chart or ranked list of each hub candidate's Pareto-front selection frequency across all 20 runs (combined front).

**Experiment that produces it:** Post-processing of the 20-run CV-Large benchmark — for each of the 128 (or N) Pareto solutions pooled across seeds, count how often each hub k has X_k = 1.

**Dataset dependency:** 🔴 FULLY AFFECTED. New hub candidates, new risk profiles, new accessibility matrix → completely different selection frequency hierarchy.

**Specific values currently in text:**

| Claim | Status |
|---|---|
| H15 = 100% selection | 🔴 Re-verify |
| H16 = 100% selection | 🔴 Re-verify |
| H14 > 82% selection | 🔴 Re-verify |
| H1 = 67% selection | 🔴 Re-verify |

---

### Figure 4-6 | Risk Profile Heatmap (r_ks)
**What it shows:** Heatmap of flood risk index r_ks for each hub candidate across three scenarios.

**Experiment that produces it:** This is a DATASET property, not an algorithm output. It comes directly from the vulnerability calibration methodology applied to the new dataset.

**Dataset dependency:** 🔴 FULLY AFFECTED — this figure is the dataset itself visualized. With the upgraded dataset methodology, every r_ks value changes.

**Specific values currently in text:**

| Claim | Status |
|---|---|
| H15 risk: mild=0.26, extreme=0.59 | 🔴 Re-derive from new dataset |
| H16 risk: mild=0.38, extreme=0.63 | 🔴 Re-derive from new dataset |
| H1 risk in severe = 0.94 | 🔴 Re-derive from new dataset |
| H14 risk range 0.05–0.13 | 🔴 Re-derive from new dataset |

---

## PART B — Dependency Chain Summary

```
New dataset methodology
    │
    ├── New accessibility matrix (OSRM-validated)
    │       └── affects: arc costs, travel times, modal feasibility
    │
    ├── New vulnerability scores (r_ks per hub per scenario)
    │       └── affects: Figure 4-6, hub activation/deactivation in 4-4
    │
    ├── New scenario generation distribution
    │       └── affects: Figure 4-2 (SAA), scenario probabilities
    │
    └── All above feed into:
            ├── Figure 4-1 (Pareto fronts) → Table 4-1, Table 4-2
            ├── Figure 4-4 (cross-scenario map) → modal counts, hub names
            ├── Figure 4-5 (hub frequency)
            └── Figure 4-6 (risk heatmap)
```

---

## PART C — What Is Stable vs What Must Wait

### ✅ Safe to finalize now (not data-dependent)

- Algorithm description and chromosome encoding
- Problem constants: χ=0.7, α=0.6, γ=3.0 kg/person, λ₀=0.8
- PB-NSGA hyperparameters: N=200, G∈{300,500}, pc=0.98, decay schedule
- Baseline algorithm descriptions (Greedy, VNS-TS, GWO-HD, MILP/AWS)
- Metrics definitions (HV, IGD+, OOS feasibility)
- DSS architecture description (Streamlit-Folium, sub-500ms claim)
- The qualitative argument structure for why PB-NSGA beats VNS-TS (encoder-decoder separation argument)
- The SAA argumentation logic (why stratified > random) — the conclusion is stable even if the specific numbers change

### 🔴 Must be held as `{PLACEHOLDER}` until new results

Everything in Tables 4-1, 4-2, all six figures, and every inline number derived from them, including:
- All HV / IGD+ / CPU time values
- All Z1 / Z2 range claims
- All hub names, risk values, selection frequencies
- All modal counts
- The knee-point coordinates
- The OOS feasibility percentages
- The SAA std-dev values and crossover point

### ❌ Must be deleted regardless of new data

- "3.5× equity improvement" — fabricated from infeasible artifact
- "worst-case deprivation ~150,000" — same source
- "helicopter routes paradoxically disappear in Extreme" — corrected by audit
- "H1, H15 disabled → air collapse" consequence — wrong causal claim
- "all eight hubs remain active" — wrong, contradicted by r_ks filter

---

## PART D — Required Experiments Checklist for Script

```
EXP-1  CV-Small 20-run benchmark (Greedy, VNS-TS, GWO-HD, MILP-AWS, PB-NSGA)
         → produces: Table 4-1, Figure 4-1 left panel

EXP-2  CV-Large 20-run benchmark (VNS-TS, GWO-HD, PB-NSGA)
         → produces: Table 4-2 columns HV/IGD+/Time, Figure 4-1 right panel

EXP-3  OOS validation on fixed 10-scenario hold-out set (same 3 algorithms)
         → produces: Table 4-2 column OOS Feasibility
         DEPENDENCY: hold-out set must be locked before EXP-2 runs

EXP-4  SAA sensitivity study — exact enumeration on CV-Small,
         N ∈ {3,5,10,15,20,30}, 10 replications each
         → produces: Figure 4-2

EXP-5  Knee-point extraction from EXP-2 combined ND front
         + per-scenario solution decoding (hub activity, modal counts,
           reactive hubs, lateral links, air attribution per hub)
         → produces: Figure 4-4, narrative_data.json (from previous session)

EXP-6  Hub selection frequency aggregation across all 20-seed Pareto solutions
         → produces: Figure 4-5

EXP-7  Risk heatmap extraction from new dataset vulnerability calibration
         (no algorithm run needed — pure dataset query)
         → produces: Figure 4-6
```
