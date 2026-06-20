"""
app.py — Streamlit entry point for the Disaster Relief Decision Support System.

Run from project root:
    streamlit run visualizer/app.py
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from streamlit_folium import st_folium

# ── path setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src" / "visualizer"))

from solution_loader import (
    NodeInfo, Solution, SolverResult,
    load_instance, load_result, deduplicate_solutions,
)
from visualizer.config import PATHS, DATASETS, VERSIONS, get_explorer_config
from visualizer.pareto_view import build_pareto_fig
from visualizer.map_view import build_map
from visualizer.flow_loader import (
    load_solution_flow, load_fallback_flow, flows_available, SolutionFlow,
)
from visualizer.dataset_view import build_dataset_map

# ── constants ─────────────────────────────────────────────────────────────────
_SC_NAMES  = ["Mild", "Severe", "Extreme"]
_SC_PROBS  = [0.60, 0.30, 0.10]
_SC_ICONS  = ["🌊", "⚠️", "🔴"]
_MODE_NAMES = {0: "Road 🚚", 1: "Water 🚤", 2: "Air 🚁"}

_SOLVER_BIN  = _ROOT / "src" / "solver" / ("solver.exe" if sys.platform.startswith("win") else "solver")
_DEFAULT_GEN = {"CV Large": 500, "CV Small": 300}
_INF_SENTINEL = 1e9

_SC_COLORS = ["#0277BD", "#E65100", "#B71C1C"]  # mild=blue, severe=orange, extreme=red


def _scenario_selector(key: str, disabled: bool = False) -> int:
    """Three-button scenario selector. Returns selected scenario index 0/1/2."""
    idx = st.session_state.get("scenario_idx", 0)
    cols = st.columns(3)
    for i, (col, name, prob, icon, color) in enumerate(
        zip(cols, _SC_NAMES, _SC_PROBS, _SC_ICONS, _SC_COLORS)
    ):
        with col:
            if st.button(
                f"{icon} **{name}** — p={prob}",
                key=f"sc_{key}_{i}",
                use_container_width=True,
                type="primary" if idx == i else "secondary",
                disabled=disabled,
            ):
                st.session_state["scenario_idx"] = i
                st.rerun()
    return idx


# ── cached loaders ────────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Loading solver results…")
def _load_result(path: str, mtime: float) -> SolverResult:
    return load_result(path)


@st.cache_data(show_spinner="Loading instance…")
def _load_instance(path: str, mtime: float) -> NodeInfo:
    return load_instance(path)


@st.cache_data(show_spinner="Loading instance JSON…")
def _load_instance_raw(path: str, mtime: float) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_solutions(result: SolverResult, pf_only: bool) -> List[Solution]:
    sols = result.pareto_front if pf_only else (result.all_feasible or result.pareto_front)
    deduped, _ = deduplicate_solutions([s for s in sols if s.CV == 0.0], mode="objective")
    return deduped


def _pick_flow(
    sol_idx: int,
    solution: Solution,
    result: SolverResult,
    scenario_idx: int,
    num_hubs: int,
    flows_dir: Optional[Any] = None,
) -> Optional[Any]:
    def _hub_match(sf: Optional[SolutionFlow]) -> bool:
        return sf is not None and len(sf.X) == num_hubs

    sf = load_solution_flow(sol_idx, flows_dir=flows_dir)
    if not _hub_match(sf):
        sf = None
    if sf is None and sol_idx == 0:
        fb = load_fallback_flow()
        sf = fb if _hub_match(fb) else None
    if sf and scenario_idx < len(sf.scenarios):
        return sf.scenarios[scenario_idx]
    return None


# ── solver pipeline ───────────────────────────────────────────────────────────

def _sanitize_instance_for_solver(instance_path: str) -> Tuple[str, Optional[Path]]:
    with open(instance_path, encoding="utf-8") as f:
        data = json.load(f)
    found = False

    def _clean(obj):
        nonlocal found
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        if isinstance(obj, float) and not math.isfinite(obj):
            found = True
            return math.copysign(_INF_SENTINEL, obj) if obj == obj else _INF_SENTINEL
        return obj

    cleaned = _clean(data)
    if not found:
        return instance_path, None

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(cleaned, tmp, allow_nan=False)
    tmp.close()
    return tmp.name, Path(tmp.name)


def _run_solver_pipeline(
    instance_path: str,
    result_path: Path,
    flows_dir: Path,
    pop: int,
    gen: int,
    seed: int,
    algo: str,
) -> bool:
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with st.status("Running solver pipeline…", expanded=True) as status:
        solver_instance_path, tmp_path = _sanitize_instance_for_solver(instance_path)
        if tmp_path is not None:
            st.write("Sanitizing non-finite values for the solver's strict JSON parser…")
        try:
            st.write(f"PB-NSGA-II: pop={pop}, gen={gen}, seed={seed}, algo={algo}")
            proc = subprocess.run(
                [str(_SOLVER_BIN), solver_instance_path,
                 "--pop", str(pop), "--gen", str(gen),
                 "--seed", str(seed), "--algo", algo,
                 "--out", str(result_path)],
                cwd=_ROOT, capture_output=True, text=True,
            )
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

        if proc.returncode != 0:
            status.update(label="Solver failed", state="error")
            st.error(proc.stderr or "Solver exited with a non-zero status.")
            return False

        st.write("Generating flow/routing data…")
        flows_dir.mkdir(parents=True, exist_ok=True)
        proc2 = subprocess.run(
            [sys.executable, str(_SELF / "preprocess_flows.py"),
             "--result", str(result_path),
             "--instance", instance_path,
             "--out-dir", str(flows_dir),
             "--force"],
            cwd=_ROOT, capture_output=True, text=True,
        )
        if proc2.returncode != 0:
            status.update(label="Flow preprocessing failed", state="error")
            st.error(proc2.stderr or "preprocess_flows.py exited with a non-zero status.")
            return False

        status.update(label="Done", state="complete")
    return True


# ── DSS panels ────────────────────────────────────────────────────────────────

def _render_stage2_panel(
    solution: Solution,
    node_info: NodeInfo,
    inst_raw: Dict[str, Any],
    flow_sc: Optional[Any],
    mild_flow_sc: Optional[Any],
    scenario_idx: int,
    solutions: List[Solution],
    sel_idx: int,
) -> None:
    """D1 — Stage-2 Scenario Response panel."""
    scenarios_raw = inst_raw.get("scenarios", [])
    sc = scenarios_raw[scenario_idx] if scenario_idx < len(scenarios_raw) else {}
    hub_risk_dict = sc.get("hub_risk", {})
    chi = float(inst_raw.get("global_params", {}).get("chi", 0.70))

    # Hub safety status
    active_names, inactive_items = [], []
    for k in solution.open_hubs:
        h_idx = node_info.hub_indices[k]
        r_val = float(hub_risk_dict.get(str(h_idx), 0.0))
        name  = node_info.names[h_idx] if h_idx < len(node_info.names) else f"Hub {k}"
        if r_val <= chi:
            active_names.append(name)
        else:
            inactive_items.append((name, r_val))

    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("Active hubs", f"{len(active_names)} / {solution.num_open_hubs}")
    with c2:
        if inactive_items:
            for name, r_val in inactive_items:
                st.warning(f"⚠️ **{name}** flooded (r={r_val:.2f} > χ={chi})", icon=None)
        else:
            st.success(f"All {solution.num_open_hubs} hubs operational this scenario.")

    # Chi threshold justification (collapsed)
    with st.expander(f"ℹ️ Why χ = {chi}?", expanded=False):
        st.caption(
            f"χ = {chi}: Hubs are purpose-built hardened evacuation shelters. "
            f"A hub remains operationally viable when its local flood risk index r ≤ {chi} — "
            "analogous to real-world shelter siting criteria (Bangladesh MCS, Japan 指定避難所, "
            "Vietnam Nhà tránh lũ) which require facilities to be above predicted inundation level. "
            "Hubs exceeding this threshold are themselves overwhelmed and cannot receive evacuees. "
            "See `audit/doc_rescue_hub_precedents.md` for full citations."
        )

    st.divider()

    # Reactive hubs (y_ks active but not planned)
    if flow_sc is not None and flow_sc.y_ks:
        reactive_ks = [
            k for k, active in enumerate(flow_sc.y_ks)
            if active and k < len(solution.X) and solution.X[k] == 0
        ]
        if reactive_ks:
            r_names = [
                node_info.names[node_info.hub_indices[k]]
                if k < len(node_info.hub_indices) and node_info.hub_indices[k] < len(node_info.names)
                else f"Hub {k}"
                for k in reactive_ks
            ]
            st.warning(
                f"⚡ **{len(reactive_ks)} reactive hub(s) opened:** {', '.join(r_names)}",
                icon=None,
            )
        else:
            st.caption("ⓘ No reactive hubs opened this scenario.")

    st.divider()

    # Mode counts
    if flow_sc is not None:
        import pandas as pd  # noqa: PLC0415
        from collections import defaultdict  # noqa: PLC0415

        da_modes = [a.mode for a in flow_sc.demand_assignments]
        curr_counts = {0: da_modes.count(0), 1: da_modes.count(1), 2: da_modes.count(2)}
        total = sum(curr_counts.values())

        st.write(f"**{total} communes assigned — rescue dispatch modes:**")
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("🚚 Road",  curr_counts[0])
        mc2.metric("🚤 Water", curr_counts[1])
        mc3.metric("🚁 Air",   curr_counts[2])

        # vs Mild delta
        if scenario_idx > 0 and mild_flow_sc is not None:
            mild_modes = [a.mode for a in mild_flow_sc.demand_assignments]
            mild_counts = {0: mild_modes.count(0), 1: mild_modes.count(1), 2: mild_modes.count(2)}
            deltas = {m: curr_counts[m] - mild_counts[m] for m in (0, 1, 2)}
            changed = [f"{'+' if d>0 else ''}{d} {_MODE_NAMES[m]}"
                       for m, d in deltas.items() if d != 0]
            if changed:
                st.caption(f"vs Mild: {' · '.join(changed)} — communes rerouted due to flooding")

        st.caption("ⓘ Mode counts are postprocessor estimates; MCF lateral flows not shown")

        # Per-hub commune breakdown
        hub_communes: dict = defaultdict(lambda: {0: 0, 1: 0, 2: 0})
        for asgn in flow_sc.demand_assignments:
            if asgn.hub_idx >= 0:
                hub_communes[asgn.hub_idx][asgn.mode] += 1

        if hub_communes:
            st.divider()
            st.write("**Commune assignments per hub:**")
            hub_rows = []
            air_hubs = []
            for h_idx, modes in sorted(hub_communes.items(), key=lambda x: -sum(x[1].values())):
                name = node_info.names[h_idx] if h_idx < len(node_info.names) else f"Node {h_idx}"
                total_h = sum(modes.values())
                hub_rows.append({
                    "Hub": name,
                    "Total": total_h,
                    "🚚 Road": modes[0],
                    "🚤 Water": modes[1],
                    "🚁 Air": modes[2],
                })
                if modes[2] > 0:
                    air_hubs.append((name, modes[2]))
            st.dataframe(pd.DataFrame(hub_rows), hide_index=True, use_container_width=True)

            if air_hubs:
                air_summary = " · ".join(f"**{n}** ({c} communes)" for n, c in air_hubs)
                st.info(f"🚁 Helicopter service provided by: {air_summary}", icon=None)
    else:
        st.info("Detailed mode breakdown requires flow files. Run preprocess_flows.py.", icon="ℹ️")

    # Equity framing
    if len(solutions) > 1:
        st.divider()
        best_z1_sol = min(solutions, key=lambda s: s.Z1)
        best_z2_sol = min(solutions, key=lambda s: s.Z2)
        z2_reduction = (best_z2_sol.Z2 - solution.Z2) / best_z2_sol.Z2 * 100 if best_z2_sol.Z2 > 0 else 0
        cost_premium = (solution.Z1 - best_z1_sol.Z1) / best_z1_sol.Z1 * 100 if best_z1_sol.Z1 > 0 else 0
        st.markdown(
            f"Worst-case deprivation: **{solution.Z2:,.0f}** person-hrs · "
            f"vs lowest-cost: **{z2_reduction:+.1f}%** deprivation, **{cost_premium:+.1f}%** cost"
        )


def _render_stage1_panel(
    solution: Solution,
    node_info: NodeInfo,
    inst_raw: Dict[str, Any],
) -> None:
    """D2 — Stage-1 Pre-Disaster Plan panel."""
    hub_params = inst_raw.get("hub_params", {})
    cap_dict   = hub_params.get("capacity",   {})
    fc_dict    = hub_params.get("fixed_cost", {})
    hc_dict    = hub_params.get("hold_cost",  {})

    rows = []
    total_prestock = 0.0
    total_hold_cost = 0.0
    total_fixed_cost = 0.0

    for k in solution.open_hubs:
        h_idx    = node_info.hub_indices[k]
        name     = node_info.names[h_idx] if h_idx < len(node_info.names) else f"Hub {k}"
        cap      = float(cap_dict.get(str(h_idx), 0))
        fc       = float(fc_dict.get(str(h_idx), 0))
        hc_rate  = float(hc_dict.get(str(h_idx), 0))
        r_k      = solution.R[k] if k < len(solution.R) else 0.0
        prestock = r_k * cap
        hold_cost = hc_rate * prestock  # c_k * q_k — Stage-1 cost (scenario-independent)

        fill_pct = r_k * 100
        bar = "▓" * int(fill_pct / 10) + "░" * (10 - int(fill_pct / 10))

        rows.append({
            "Hub": name,
            "Capacity (kg)": f"{cap:,.0f}",
            "Pre-stock (kg)": f"{prestock:,.0f}",
            "Fill %": f"{fill_pct:.0f}% {bar}",
            "Fixed cost ($)": f"{fc:,.0f}",
            "Hold rate ($/kg)": f"{hc_rate:.3f}",
            "Hold cost ($)": f"{hold_cost:,.0f}",
        })
        total_prestock   += prestock
        total_hold_cost  += hold_cost
        total_fixed_cost += fc

    if rows:
        import pandas as pd  # noqa: PLC0415
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.markdown(
            f'Total cost <b>&#36;{solution.Z1/1e6:.2f}M</b> · '
            f'{solution.num_open_hubs} hubs · '
            f'Pre-stock <b>{total_prestock/1e3:.0f} t</b> · '
            f'Hold cost <b>&#36;{total_hold_cost:,.0f}</b>',
            unsafe_allow_html=True,
        )
    else:
        st.info("No hubs established in this solution.")


def _render_pareto_panel(
    solutions: List[Solution],
    sel_idx: int,
    solution: Solution,
    node_info: NodeInfo,
) -> None:
    """D3 — Pareto Front & Navigation panel."""
    z1s = [s.Z1 for s in solutions]
    z2s = [s.Z2 for s in solutions]
    z1_min, z1_max = min(z1s), max(z1s)
    z2_min, z2_max = min(z2s), max(z2s)
    z1r = z1_max - z1_min or 1.0
    z2r = z2_max - z2_min or 1.0

    # Knee: Tchebycheff on normalised front
    knee_idx = min(
        range(len(solutions)),
        key=lambda i: max((solutions[i].Z1 - z1_min) / z1r, (solutions[i].Z2 - z2_min) / z2r),
    )

    # Trade-off position badge
    is_knee      = (sel_idx == knee_idx)
    cost_premium = (solution.Z1 - z1_min) / z1_min * 100 if z1_min > 0 else 0.0
    z2_reduction = (z2_max - solution.Z2) / (z2_max - z2_min) * 100 if z2r > 0 else 0.0

    badge_colour = "#1976D2" if is_knee else "#555"
    badge_label  = "● Balanced (knee) — recommended" if is_knee else f"◎ Solution {sel_idx+1} of {len(solutions)}"
    st.markdown(
        f"<div style='background:{badge_colour};color:white;padding:6px 12px;"
        f"border-radius:6px;display:inline-block;font-size:12px'>{badge_label}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"Z1 = <b>&#36;{solution.Z1/1e6:.2f}M</b> · Z2 = <b>{solution.Z2:,.0f}</b> · "
        f"{z2_reduction:.1f}% better deprivation vs worst · "
        f"{cost_premium:+.1f}% cost vs cheapest",
        unsafe_allow_html=True,
    )

    st.divider()

    fig = build_pareto_fig(solutions, selected_idx=sel_idx, title="")
    fig.update_layout(dragmode="select")
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    event = st.plotly_chart(fig, on_select="rerun", selection_mode="points",
                            key="pareto_chart", use_container_width=True)
    for _pt in (event.selection.points or []):
        if _pt["curve_number"] == 0 and _pt["point_number"] != sel_idx:
            st.session_state["selected_idx"] = _pt["point_number"]
            st.rerun()

    # Navigation
    qj1, qj2, qj3 = st.columns(3)
    if qj1.button("Best Z1 (cheapest)", use_container_width=True):
        st.session_state["selected_idx"] = int(min(range(len(solutions)), key=lambda i: solutions[i].Z1))
        st.rerun()
    if qj2.button("Best Z2 (fairest)", use_container_width=True):
        st.session_state["selected_idx"] = int(min(range(len(solutions)), key=lambda i: solutions[i].Z2))
        st.rerun()
    if qj3.button("Knee (recommended)", use_container_width=True):
        st.session_state["selected_idx"] = knee_idx
        st.rerun()




# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="DRND Decision Support System",
        page_icon="🗺️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        "<style>"
        "[data-testid='stHeader']{display:none!important}"
        "[data-testid='stMainBlockContainer']{padding-top:0.5rem}"
        "#_dss-sidebar-btn{"
        "position:fixed;top:50px;left:0;z-index:1000000;"
        "display:none;background:rgba(25,118,210,0.85);color:white;"
        "border:none;border-radius:0 6px 6px 0;padding:10px 10px;"
        "cursor:pointer;font-size:18px;line-height:1;"
        "box-shadow:2px 2px 8px rgba(0,0,0,.3);"
        "transition:background 0.15s}"
        "#_dss-sidebar-btn:hover{background:rgba(21,101,192,0.97)}"
        "</style>",
        unsafe_allow_html=True,
    )

    # ── Session defaults ──────────────────────────────────────────────────────
    ss = st.session_state
    ss.setdefault("selected_idx",      0)
    ss.setdefault("dataset",           DATASETS[0])
    ss.setdefault("dataset_version",   "v1")
    ss.setdefault("scenario_idx",      0)
    ss.setdefault("map_mode",          "Single scenario")
    ss.setdefault("min_demand_filter", 0)

    # ── Sidebar Part 1 — Dataset controls (needed before data load) ───────────
    with st.sidebar:
        st.title("🗺️ Relief Network DSS")
        st.caption("MO-IHLNDP · PB-NSGA · Central Vietnam")
        st.divider()

        dataset_name = st.radio(
            "Dataset", DATASETS,
            index=DATASETS.index(ss["dataset"]),
            key="dataset_radio",
        )
        ss["dataset"] = dataset_name

        version_options = VERSIONS
        if ss["dataset_version"] not in version_options:
            ss["dataset_version"] = "v1"
        version_name = st.radio(
            "Dataset version", version_options,
            index=version_options.index(ss["dataset_version"]),
            format_func=lambda v: "v1 — canonical" if v == "v1" else "v2 — planar",
            horizontal=True,
            key="dataset_version_radio",
        )
        ss["dataset_version"] = version_name

    paths = get_explorer_config(dataset_name, version_name)
    dataset_label = f"{dataset_name} ({version_name})"

    # ── Load data ─────────────────────────────────────────────────────────────
    pf_only = True
    try:
        _inst_mtime = Path(paths["instance"]).stat().st_mtime
        result    = (_load_result(paths["result"], Path(paths["result"]).stat().st_mtime)
                     if paths.get("result") else None)
        node_info = _load_instance(paths["instance"], _inst_mtime)
        inst_raw  = _load_instance_raw(paths["instance"], _inst_mtime)
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        st.stop()

    solutions: List[Solution] = []
    sel_idx  = 0
    solution: Optional[Solution] = None
    no_feasible_msg: Optional[str] = None
    if result is not None:
        solutions = _get_solutions(result, pf_only)
        if solutions:
            sel_idx  = min(ss["selected_idx"], len(solutions) - 1)
            solution = solutions[sel_idx]
        else:
            all_sols = result.pareto_front or result.all_feasible
            best_cv  = min((s.CV for s in all_sols), default=0.0)
            no_feasible_msg = (
                f"**{dataset_label}** has no zero-violation (CV=0) solutions — "
                f"best CV found: **{best_cv:,.2f}**. Try a different seed/algo via Run Solver."
            )

    # ── Sidebar Part 2 — Solution controls + mini Pareto + map options ────────
    with st.sidebar:
        st.divider()

        if solutions and len(solutions) > 1:
            _z1s = [s.Z1 for s in solutions]
            _z2s = [s.Z2 for s in solutions]
            _z1r = (max(_z1s) - min(_z1s)) or 1.0
            _z2r = (max(_z2s) - min(_z2s)) or 1.0
            _knee_idx = min(
                range(len(solutions)),
                key=lambda i: max(
                    (solutions[i].Z1 - min(_z1s)) / _z1r,
                    (solutions[i].Z2 - min(_z2s)) / _z2r,
                ),
            )
            st.markdown("**Pareto front** — click to select")
            _sfig = build_pareto_fig(solutions, selected_idx=sel_idx, title="")
            _sfig.update_layout(
                height=180, margin=dict(l=20, r=8, t=4, b=25), showlegend=False,
                dragmode="select",
            )
            _sfig.update_xaxes(fixedrange=True)
            _sfig.update_yaxes(fixedrange=True)
            _sev = st.plotly_chart(
                _sfig, on_select="rerun", selection_mode="points",
                key="pareto_sidebar", use_container_width=True,
            )
            for _pt in (_sev.selection.points or []):
                if _pt["curve_number"] == 0 and _pt["point_number"] != sel_idx:
                    ss["selected_idx"] = _pt["point_number"]
                    st.rerun()
            _qb1, _qb2, _qb3 = st.columns(3)
            if _qb1.button("💰 Z1",  use_container_width=True, help="Cheapest solution"):
                ss["selected_idx"] = int(min(range(len(solutions)), key=lambda i: solutions[i].Z1))
                st.rerun()
            if _qb2.button("⚖️ Z2",  use_container_width=True, help="Lowest deprivation"):
                ss["selected_idx"] = int(min(range(len(solutions)), key=lambda i: solutions[i].Z2))
                st.rerun()
            if _qb3.button("⭐ Knee", use_container_width=True, help="Balanced — recommended"):
                ss["selected_idx"] = _knee_idx
                st.rerun()

        st.divider()
        st.markdown("**Map controls**")
        map_mode = st.radio(
            "View",
            ["Single scenario", "Compare all 3 scenarios"],
            index=["Single scenario", "Compare all 3 scenarios"].index(ss["map_mode"]),
            horizontal=True,
            key="map_mode_radio",
        )
        ss["map_mode"] = map_mode

        min_demand_filter = st.slider(
            "Hide rescue lines < demand (persons)",
            min_value=0, max_value=5000,
            value=ss["min_demand_filter"],
            step=100,
            help="Hides allocation lines from low-demand communes. Demand dots remain on map.",
            key="min_demand_slider",
        )
        ss["min_demand_filter"] = min_demand_filter

    # ── Sidebar Part 3 — Flow status + solver ────────────────────────────────
    with st.sidebar:
        st.divider()
        if paths.get("result"):
            avail = flows_available(flows_dir=paths.get("flows_dir"))
            if avail:
                st.success(f"Flow data: {len(avail)} solution(s) pre-computed")
            else:
                st.info("No per-solution flows found.\n\n```\npython visualizer/preprocess_flows.py\n```")
        else:
            st.info(f"No solver output for **{dataset_label}** yet.")

        st.divider()
        with st.expander("⚙️ Run Solver", expanded=(paths.get("result") is None)):
            st.caption(f"Runs PB-NSGA-II on **{dataset_label}**, then regenerates flow data.")
            c1, c2 = st.columns(2)
            pop  = c1.number_input("--pop",  min_value=10, value=200, step=10)
            gen  = c2.number_input("--gen",  min_value=10, value=_DEFAULT_GEN[dataset_name], step=10)
            c3, c4 = st.columns(2)
            seed = c3.number_input("--seed", min_value=0, value=0, step=1)
            algo = c4.selectbox("--algo", ["nsga2", "nsma"], index=0)

            overwrite_ok = True
            if version_name == "v1":
                st.warning("v1 result already exists. Re-running will overwrite it.")
                overwrite_ok = st.checkbox("Overwrite existing v1 result", value=False)

            if not _SOLVER_BIN.exists():
                st.error(f"Solver binary not found: `{_SOLVER_BIN.relative_to(_ROOT)}`. Run compile.sh first.")
            elif st.button("▶ Run Solver", use_container_width=True,
                           disabled=(version_name == "v1" and not overwrite_ok)):
                p = PATHS[dataset_name][version_name]
                if dataset_name == "CV Large":
                    target_result = p["results"] / f"CV_large_seed{int(seed)}.json"
                else:
                    target_result = p["results"] / f"cv_small_pb_nsga_seed{int(seed)}.json"
                if _run_solver_pipeline(
                    paths["instance"], target_result, p["flows"],
                    int(pop), int(gen), int(seed), algo
                ):
                    st.cache_data.clear()
                    ss["selected_idx"] = 0
                    st.rerun()

    # ── Global tabs ───────────────────────────────────────────────────────────
    tab_sol, tab_ds, tab_exp = st.tabs(["🗺️ Solution", "📊 Input Dataset", "📈 Experiments"])

    # ════════════════════════════════════════════════════════════════════════
    # TAB 1 — Solution Explorer
    # ════════════════════════════════════════════════════════════════════════
    with tab_sol:
        if result is None or solution is None:
            if no_feasible_msg:
                st.warning(no_feasible_msg)
            else:
                st.info(
                    f"**{dataset_label}** has no solver output yet. "
                    "Switch to v1 to explore solutions, or run the solver via the sidebar."
                )
        else:
            num_hubs = len(node_info.hub_indices)

            # sentinel used by FAB JS to locate and hide the carousel when sidebar is open
            st.markdown('<span id="_dss-carousel-sentinel" style="display:none"></span>',
                        unsafe_allow_html=True)

            # ── Solution carousel ─────────────────────────────────────────────
            if len(solutions) > 1:
                _z1s = [s.Z1 for s in solutions]
                _z2s = [s.Z2 for s in solutions]
                _z1r = (max(_z1s) - min(_z1s)) or 1.0
                _z2r = (max(_z2s) - min(_z2s)) or 1.0
                _knee = min(
                    range(len(solutions)),
                    key=lambda i: max(
                        (solutions[i].Z1 - min(_z1s)) / _z1r,
                        (solutions[i].Z2 - min(_z2s)) / _z2r,
                    ),
                )
                _badge = ("⭐ Knee" if sel_idx == _knee else
                          "💰 Best Z1" if sel_idx == _z1s.index(min(_z1s)) else
                          "⚖️ Best Z2" if sel_idx == _z2s.index(min(_z2s)) else "")
                _cc1, _cc2, _cc3 = st.columns([1, 10, 1])
                with _cc1:
                    if st.button("◀", key="car_prev", use_container_width=True):
                        ss["selected_idx"] = (sel_idx - 1) % len(solutions)
                        st.rerun()
                with _cc2:
                    _badge_html = (f' <span style="background:#1976D2;color:white;'
                                   f'padding:1px 7px;border-radius:4px;font-size:11px">{_badge}</span>'
                                   if _badge else "")
                    st.markdown(
                        f'<div style="text-align:center;padding:5px 10px;background:#f0f2f6;'
                        f'border-radius:6px;font-size:13px">'
                        f'<b>Solution {sel_idx + 1} / {len(solutions)}</b>{_badge_html}'
                        f' · Z1 = <b>&#36;{solution.Z1/1e6:.2f}M</b>'
                        f' · Z2 = <b>{solution.Z2:,.0f}</b>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with _cc3:
                    if st.button("▶", key="car_next", use_container_width=True):
                        ss["selected_idx"] = (sel_idx + 1) % len(solutions)
                        st.rerun()

            # ── Scenario selector ─────────────────────────────────────────────
            compare_mode = (map_mode == "Compare all 3 scenarios")
            st.markdown("**Flood scenario**")
            scenario_idx = _scenario_selector("sol", disabled=compare_mode)
            if compare_mode:
                st.caption("All 3 scenarios shown on map — switch to Single to filter.")
            ss["scenario_idx"] = scenario_idx
            sc_label = _SC_NAMES[scenario_idx]

            # Load flows
            flow_sc = _pick_flow(sel_idx, solution, result, scenario_idx,
                                  num_hubs=num_hubs, flows_dir=paths.get("flows_dir"))
            mild_flow_sc = (_pick_flow(sel_idx, solution, result, 0,
                                       num_hubs=num_hubs, flows_dir=paths.get("flows_dir"))
                            if scenario_idx > 0 else flow_sc)

            if flow_sc is None:
                st.info(
                    "Detailed routing unavailable — showing approximate hub placement. "
                    "Run `python visualizer/preprocess_flows.py` to generate full routing.",
                    icon="ℹ️",
                )

            # ── Map ───────────────────────────────────────────────────────────
            st.markdown('<div id="_dss-map-anchor"></div>', unsafe_allow_html=True)
            if map_mode == "Single scenario":
                fmap = build_map(
                    node_info=node_info, solution=solution,
                    scenario_flow=flow_sc, instance_data=inst_raw,
                    scenario_idx=scenario_idx,
                    show_labels=False, show_alloc=True,
                    show_transshipment=True,
                    min_demand_filter=min_demand_filter,
                )
                st_folium(fmap, width="100%", height=620, returned_objects=[],
                          key=f"map_{sel_idx}_{scenario_idx}")
                map_html = fmap._repr_html_()  # type: ignore[attr-defined]
                st.download_button(
                    "Export map as HTML", data=map_html,
                    file_name=f"relief_map_sol{sel_idx+1}_{sc_label.lower()}.html",
                    mime="text/html",
                )
            else:
                cols = st.columns(3)
                for s_idx, (col, sc_name, sc_icon) in enumerate(zip(cols, _SC_NAMES, _SC_ICONS)):
                    with col:
                        st.caption(f"{sc_icon} **{sc_name}** (p={_SC_PROBS[s_idx]})")
                        fsc = _pick_flow(sel_idx, solution, result, s_idx,
                                          num_hubs=num_hubs, flows_dir=paths.get("flows_dir"))
                        fm  = build_map(
                            node_info=node_info, solution=solution,
                            scenario_flow=fsc, instance_data=inst_raw,
                            scenario_idx=s_idx,
                            show_labels=False, show_alloc=True,
                            show_transshipment=True,
                            compact=True,
                            min_demand_filter=min_demand_filter,
                        )
                        st_folium(fm, width="100%", height=420, returned_objects=[],
                                  key=f"map3_{sel_idx}_{s_idx}")

            # ── Stage 2 — Scenario Response ───────────────────────────────────
            st.divider()
            if compare_mode:
                st.subheader("📊 Stage 2 — Scenario Response")
                _s2_tabs = st.tabs([f"{_SC_ICONS[i]} {_SC_NAMES[i]}" for i in range(3)])
                for _s2_idx, _s2_tab in enumerate(_s2_tabs):
                    with _s2_tab:
                        _s2_flow = _pick_flow(
                            sel_idx, solution, result, _s2_idx,
                            num_hubs=num_hubs, flows_dir=paths.get("flows_dir"),
                        )
                        _s2_mild = (
                            _pick_flow(sel_idx, solution, result, 0,
                                       num_hubs=num_hubs, flows_dir=paths.get("flows_dir"))
                            if _s2_idx > 0 else _s2_flow
                        )
                        _render_stage2_panel(
                            solution=solution, node_info=node_info, inst_raw=inst_raw,
                            flow_sc=_s2_flow, mild_flow_sc=_s2_mild,
                            scenario_idx=_s2_idx, solutions=solutions, sel_idx=sel_idx,
                        )
            else:
                st.subheader(f"📊 Stage 2 — Scenario Response ({sc_label})")
                _render_stage2_panel(
                    solution=solution, node_info=node_info, inst_raw=inst_raw,
                    flow_sc=flow_sc, mild_flow_sc=mild_flow_sc,
                    scenario_idx=scenario_idx, solutions=solutions, sel_idx=sel_idx,
                )

            # ── Stage 1 — Pre-Disaster Plan ───────────────────────────────────
            st.divider()
            st.subheader("🏗️ Stage 1 — Pre-Disaster Plan")
            _render_stage1_panel(solution=solution, node_info=node_info, inst_raw=inst_raw)

            # ── Pareto Front & Navigation ─────────────────────────────────────
            st.divider()
            st.markdown('<div id="_dss-pareto-anchor"></div>', unsafe_allow_html=True)
            st.subheader("📈 Pareto Front & Navigation")
            _render_pareto_panel(
                solutions=solutions, sel_idx=sel_idx,
                solution=solution, node_info=node_info,
            )

            # ── Floating scroll FAB ───────────────────────────────────────────
            st.markdown("""
<style>
#_dss-fab {
    position: fixed; bottom: 26px; right: 26px; z-index: 99999;
    background: rgba(25,118,210,0.88); color: white; border: none;
    border-radius: 22px; padding: 9px 18px; font-size: 12px; font-weight: 500;
    cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,.25);
    transition: background 0.15s;
}
#_dss-fab:hover { background: rgba(21,101,192,0.95); }
</style>
<button id="_dss-fab">↓ Pareto</button>
""", unsafe_allow_html=True)
            # Script must live in a components.v1.html iframe so it executes
            # reliably; use window.parent to reach elements in the host page.
            import streamlit.components.v1 as _cv1  # noqa: PLC0415
            _cv1.html("""<script>
(function() {
    function init() {
        var pd = window.parent.document;
        var btn  = pd.getElementById('_dss-fab');
        var main = pd.querySelector('[data-testid="stMain"]');
        if (!btn || !main) { setTimeout(init, 150); return; }
        function nearPareto() {
            var el = pd.getElementById('_dss-pareto-anchor');
            if (!el) return false;
            return el.getBoundingClientRect().top < main.clientHeight * 0.6;
        }
        function update() {
            btn.textContent = nearPareto() ? '↑ Map' : '↓ Pareto';
        }
        btn.onclick = function() {
            var target = nearPareto()
                ? pd.getElementById('_dss-map-anchor')
                : pd.getElementById('_dss-pareto-anchor');
            if (target) target.scrollIntoView({behavior:'smooth', block:'start'});
        };
        main.addEventListener('scroll', update);
        update();
    }
    init();

    // Hide the solution carousel when the sidebar is open — it duplicates the
    // mini-Pareto + nav buttons already in the sidebar.
    // Sentinel is wrapped as: sentinel → stMarkdownContainer → stElementContainer
    // The carousel lives in the immediately following stLayoutWrapper sibling.
    (function carouselVisibility() {
        var pd = window.parent.document;
        function updateCarousel() {
            var sentinel = pd.getElementById('_dss-carousel-sentinel');
            if (!sentinel) return;
            var sidebar = pd.querySelector('[data-testid="stSidebar"]');
            var sidebarOpen = !!(sidebar && sidebar.getAttribute('aria-expanded') !== 'false');
            var ec = sentinel.closest('[data-testid="stElementContainer"]');
            var carouselWrapper = ec && ec.nextElementSibling;
            if (carouselWrapper) {
                carouselWrapper.style.display = sidebarOpen ? 'none' : '';
            }
        }
        setInterval(updateCarousel, 200);
    })();

    // Inject a sidebar re-expand button that appears only when sidebar is collapsed.
    // Streamlit doesn't render a collapsedControl element — it just slides the sidebar
    // off-screen — so we create our own button and show/hide it via a poll.
    (function sidebarBtn() {
        var pd = window.parent.document;
        if (pd.getElementById('_dss-sidebar-btn')) return;
        var sb = pd.createElement('button');
        sb.id = '_dss-sidebar-btn';
        sb.textContent = '❯';
        sb.title = 'Expand sidebar';
        sb.onclick = function() {
            var collapseBtn = pd.querySelector('[data-testid="stBaseButton-headerNoPadding"]');
            if (collapseBtn) collapseBtn.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}));
        };
        pd.body.appendChild(sb);
        function updateSidebar() {
            var sidebar = pd.querySelector('[data-testid="stSidebar"]');
            var b = pd.getElementById('_dss-sidebar-btn');
            if (!b) return;
            b.style.display = (sidebar && sidebar.getAttribute('aria-expanded') === 'false') ? 'block' : 'none';
        }
        setInterval(updateSidebar, 200);
    })();

    // Streamlit overrides clickmode to "event", which prevents single-click
    // from emitting plotly_selected (only drag does). This poller restores
    // "event+select" so point clicks fire plotly_selected → on_select rerun.
    if (!window.__dss_patch_running) {
        window.__dss_patch_running = true;
        (function patch() {
            var pW = window.parent;
            var Plotly = pW.Plotly;
            if (Plotly) {
                pW.document.querySelectorAll('.js-plotly-plot').forEach(function(d) {
                    if (d._fullLayout && d._fullLayout.dragmode === 'select'
                            && d._fullLayout.clickmode !== 'event+select') {
                        Plotly.relayout(d, {clickmode: 'event+select'});
                    }
                });
            }
            setTimeout(patch, 350);
        })();
    }
})();
</script>""", height=0)

    # ════════════════════════════════════════════════════════════════════════
    # TAB 2 — Input Dataset Explorer
    # ════════════════════════════════════════════════════════════════════════
    with tab_ds:
        st.markdown("**Flood scenario**")
        scenario_idx = _scenario_selector("ds")
        ss["scenario_idx"] = scenario_idx
        sc_label = _SC_NAMES[scenario_idx]
        st.caption(f"Dataset: **{dataset_label}** · Scenario: **{sc_label}**  "
                   f"(use the layer control ≡ on the map to toggle overlays)")

        dmap = build_dataset_map(
            node_info=node_info, instance_data=inst_raw, scenario_idx=scenario_idx,
        )
        _dmap_key = f"dmap_{dataset_name}_{version_name}_{scenario_idx}"
        st_folium(dmap, width="100%", height=640, returned_objects=[], key=_dmap_key)

        st.download_button(
            "Export dataset map as HTML",
            data=dmap._repr_html_(),  # type: ignore[attr-defined]
            file_name=f"dataset_{dataset_name.lower().replace(' ','_')}_{version_name}_{sc_label.lower()}.html",
            mime="text/html",
        )

        sc_raw  = inst_raw.get("scenarios", [])
        sc_data = sc_raw[scenario_idx] if scenario_idx < len(sc_raw) else {}
        mild_sc = sc_raw[0] if sc_raw else {}
        num_I   = inst_raw.get("dimensions", {}).get("num_I", len(node_info.demand_indices))

        _dv  = {int(k): float(v) for k, v in sc_data.get("demand", {}).items()}
        _mdv = {int(k): float(v) for k, v in mild_sc.get("demand", {}).items()}
        _rl  = sc_data.get("risk", [])
        _mrl = mild_sc.get("risk", [])

        total_demand = sum(_dv.values())
        mild_total   = sum(_mdv.values())
        avg_risk     = sum(_rl[:num_I]) / num_I if num_I and _rl else 0.0
        mild_avg     = sum(_mrl[:num_I]) / num_I if num_I and _mrl else 0.0

        with st.expander("📊 Scenario KPIs", expanded=True):
            d1, d2, d3 = st.columns(3)
            d1.metric(
                "Total Relief Demand", f"{total_demand:,.0f} units",
                delta=f"{total_demand - mild_total:+,.0f} vs Mild" if scenario_idx > 0 else None,
                delta_color="inverse",
            )
            d2.metric(
                "Avg Node Risk", f"{avg_risk:.3f}",
                delta=f"{avg_risk - mild_avg:+.3f} vs Mild" if scenario_idx > 0 else None,
                delta_color="inverse",
            )
            d3.metric("Flood Epicentres", len(sc_data.get("epicenters", [])))

    # ════════════════════════════════════════════════════════════════════════
    # TAB 3 — Experiments
    # ════════════════════════════════════════════════════════════════════════
    with tab_exp:
        try:
            from visualizer.experiments_view import render as render_experiments  # noqa: PLC0415
            render_experiments(dataset_name, version_name, inst_raw, node_info)
        except ImportError:
            st.info(
                "Experiments view (`visualizer/experiments_view.py`) is not yet available. "
                "It will be added in the next implementation step.",
                icon="🔧",
            )


if __name__ == "__main__":
    main()
