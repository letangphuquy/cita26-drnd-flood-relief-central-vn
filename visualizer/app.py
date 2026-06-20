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

    # Mode counts
    if flow_sc is not None:
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
    else:
        st.info("Detailed mode breakdown requires flow files. Run preprocess_flows.py.", icon="ℹ️")

    # Equity framing
    if len(solutions) > 1:
        st.divider()
        best_z1_sol = min(solutions, key=lambda s: s.Z1)
        best_z2_sol = min(solutions, key=lambda s: s.Z2)
        z2_reduction = (best_z2_sol.Z2 - solution.Z2) / best_z2_sol.Z2 * 100 if best_z2_sol.Z2 > 0 else 0
        cost_premium = (solution.Z1 - best_z1_sol.Z1) / best_z1_sol.Z1 * 100 if best_z1_sol.Z1 > 0 else 0
        st.caption(
            f"Worst-case deprivation: **{solution.Z2:,.0f}** person-hrs &nbsp;|&nbsp; "
            f"vs lowest-cost plan: **{z2_reduction:+.1f}%** deprivation, **{cost_premium:+.1f}%** cost"
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
        st.caption(
            f"Total logistics cost: **${solution.Z1/1e6:.2f}M** &nbsp;|&nbsp; "
            f"{solution.num_open_hubs} hubs established &nbsp;|&nbsp; "
            f"Total pre-stock: **{total_prestock/1e3:.0f} tonnes** &nbsp;|&nbsp; "
            f"Total hold cost (Stage-1): **${total_hold_cost:,.0f}**"
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
    st.caption(
        f"Z1 = **${solution.Z1/1e6:.2f}M** &nbsp; Z2 = **{solution.Z2:,.0f}** &nbsp; "
        f"| {z2_reduction:.1f}% better deprivation vs worst &nbsp; "
        f"| {cost_premium:+.1f}% cost vs cheapest"
    )

    st.divider()

    fig = build_pareto_fig(solutions, selected_idx=sel_idx, title="")
    event = st.plotly_chart(fig, on_select="rerun", key="pareto_chart", use_container_width=True)
    try:
        pts = event.selection.points  # type: ignore[union-attr]
        if pts:
            clicked_idx = int(pts[0].customdata[0])  # type: ignore[index]
            if clicked_idx != sel_idx:
                st.session_state["selected_idx"] = clicked_idx
                st.rerun()
    except (AttributeError, TypeError, IndexError):
        pass

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

    nav_cols = st.columns([1, 2, 1])
    with nav_cols[0]:
        if st.button("◀ Prev", use_container_width=True):
            st.session_state["selected_idx"] = (sel_idx - 1) % len(solutions)
            st.rerun()
    with nav_cols[1]:
        jump = st.number_input(
            "Jump to solution", min_value=1, max_value=len(solutions),
            value=sel_idx + 1, step=1, label_visibility="collapsed",
        )
        if jump - 1 != sel_idx:
            st.session_state["selected_idx"] = jump - 1
            st.rerun()
    with nav_cols[2]:
        if st.button("Next ▶", use_container_width=True):
            st.session_state["selected_idx"] = (sel_idx + 1) % len(solutions)
            st.rerun()

    with st.expander("Solution details"):
        open_hub_names = [
            node_info.names[node_info.hub_indices[k]]
            if node_info.hub_indices[k] < len(node_info.names) else f"Hub {k}"
            for k in solution.open_hubs
        ]
        st.write(f"**Open hubs ({solution.num_open_hubs}):**")
        for name in open_hub_names:
            st.write(f"  • {name}")
        st.write(f"**Rank:** {solution.rank} &nbsp; **CV:** {solution.CV:.4f}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="DRND Decision Support System",
        page_icon="🗺️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Session defaults ──────────────────────────────────────────────────────
    ss = st.session_state
    ss.setdefault("selected_idx",   0)
    ss.setdefault("dataset",        DATASETS[0])
    ss.setdefault("dataset_version", "v1")
    ss.setdefault("scenario_idx",   0)
    ss.setdefault("view",           "🗺️ Solution")

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.title("🗺️ Relief Network DSS")
        st.caption("MO-IHLNDP · PB-NSGA · Central Vietnam")
        st.divider()

        dataset_name = st.radio(
            "Dataset",
            DATASETS,
            index=DATASETS.index(ss["dataset"]),
            key="dataset_radio",
        )
        ss["dataset"] = dataset_name

        version_options = VERSIONS
        if ss["dataset_version"] not in version_options:
            ss["dataset_version"] = "v1"
        version_name = st.radio(
            "Dataset version",
            version_options,
            index=version_options.index(ss["dataset_version"]),
            format_func=lambda v: "v1 — canonical" if v == "v1" else "v2 — planar",
            horizontal=True,
            key="dataset_version_radio",
        )
        ss["dataset_version"] = version_name

        paths = get_explorer_config(dataset_name, version_name)
        dataset_label = f"{dataset_name} ({version_name})"

        st.divider()
        pf_only     = st.checkbox("Pareto front only",    value=True)
        show_labels = st.checkbox("Node labels",          value=False)
        show_alloc  = st.checkbox("Allocation routes",    value=True)
        show_trans  = st.checkbox("Transshipment flows",  value=True)
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

    # ── Load data ─────────────────────────────────────────────────────────────
    try:
        _inst_mtime = Path(paths["instance"]).stat().st_mtime
        result    = _load_result(paths["result"], Path(paths["result"]).stat().st_mtime) if paths.get("result") else None
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

    # ── Top header + global nav ───────────────────────────────────────────────
    st.title("Disaster Relief Network — Decision Support System")
    st.caption(f"Dataset: **{dataset_label}** · {len(solutions)} feasible solutions loaded")

    view = st.radio(
        "",
        ["🗺️ Solution", "📊 Input Dataset", "📈 Experiments"],
        index=["🗺️ Solution", "📊 Input Dataset", "📈 Experiments"].index(ss.get("view", "🗺️ Solution")),
        horizontal=True,
        label_visibility="collapsed",
        key="global_nav",
    )
    ss["view"] = view

    st.divider()

    # ════════════════════════════════════════════════════════════════════════
    # VIEW 1 — Solution Explorer
    # ════════════════════════════════════════════════════════════════════════
    if view == "🗺️ Solution":
        if result is None or solution is None:
            if no_feasible_msg:
                st.warning(no_feasible_msg)
            else:
                st.info(
                    f"**{dataset_label}** has no solver output yet. "
                    "Switch to v1 to explore solutions, or run the solver via the sidebar."
                )
            st.stop()

        num_hubs = len(node_info.hub_indices)

        # ── Controls above map ────────────────────────────────────────────────
        ctrl1, ctrl2 = st.columns([3, 2])
        with ctrl1:
            scenario_idx = st.radio(
                "Flood scenario",
                options=[0, 1, 2],
                format_func=lambda i: f"{_SC_ICONS[i]} {_SC_NAMES[i]} (p={_SC_PROBS[i]})",
                index=ss.get("scenario_idx", 0),
                horizontal=True,
                key="scenario_radio_sol",
            )
            ss["scenario_idx"] = scenario_idx
        with ctrl2:
            map_mode = st.radio(
                "Map view",
                ["Single scenario", "Compare all 3 scenarios"],
                horizontal=True,
                key="map_mode_radio",
            )

        sc_label = _SC_NAMES[scenario_idx]

        # Load flows
        flow_sc      = _pick_flow(sel_idx, solution, result, scenario_idx,
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

        # ── Map ───────────────────────────────────────────────────────────────
        if map_mode == "Single scenario":
            fmap = build_map(
                node_info=node_info, solution=solution,
                scenario_flow=flow_sc, instance_data=inst_raw,
                scenario_idx=scenario_idx,
                show_labels=show_labels, show_alloc=show_alloc,
                show_transshipment=show_trans,
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
            # D5 — side-by-side 3-scenario map
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
                        show_labels=False, show_alloc=show_alloc,
                        show_transshipment=show_trans,
                    )
                    st_folium(fm, width="100%", height=420, returned_objects=[],
                              key=f"map3_{sel_idx}_{s_idx}")

        # ── Stage-2 Scenario Response (D1) ────────────────────────────────────
        with st.expander(f"📊 Stage 2 — Scenario Response ({sc_label})", expanded=True):
            _render_stage2_panel(
                solution=solution, node_info=node_info, inst_raw=inst_raw,
                flow_sc=flow_sc, mild_flow_sc=mild_flow_sc,
                scenario_idx=scenario_idx, solutions=solutions, sel_idx=sel_idx,
            )

        # ── Stage-1 Pre-Disaster Plan (D2) ───────────────────────────────────
        with st.expander("🏗️ Stage 1 — Pre-Disaster Plan", expanded=False):
            _render_stage1_panel(solution=solution, node_info=node_info, inst_raw=inst_raw)

        # ── Pareto Front & Navigation (D3) ───────────────────────────────────
        with st.expander("📈 Pareto Front & Navigation", expanded=False):
            _render_pareto_panel(solutions=solutions, sel_idx=sel_idx, solution=solution, node_info=node_info)

    # ════════════════════════════════════════════════════════════════════════
    # VIEW 2 — Input Dataset Explorer
    # ════════════════════════════════════════════════════════════════════════
    elif view == "📊 Input Dataset":
        # Scenario toggle above the dataset map
        sc_row1, sc_row2 = st.columns([3, 2])
        with sc_row1:
            scenario_idx = st.radio(
                "Flood scenario",
                options=[0, 1, 2],
                format_func=lambda i: f"{_SC_ICONS[i]} {_SC_NAMES[i]} (p={_SC_PROBS[i]})",
                index=ss.get("scenario_idx", 0),
                horizontal=True,
                key="scenario_radio_ds",
            )
            ss["scenario_idx"] = scenario_idx

        sc_label = _SC_NAMES[scenario_idx]
        st.caption(f"Dataset: **{dataset_label}** · Scenario: **{sc_label}**")

        # Scenario KPI summary
        sc_raw    = inst_raw.get("scenarios", [])
        sc_data   = sc_raw[scenario_idx] if scenario_idx < len(sc_raw) else {}
        mild_sc   = sc_raw[0] if sc_raw else {}
        num_I     = inst_raw.get("dimensions", {}).get("num_I", len(node_info.demand_indices))

        demand_vals = {int(k): float(v) for k, v in sc_data.get("demand", {}).items()}
        mild_demand = {int(k): float(v) for k, v in mild_sc.get("demand", {}).items()}
        risk_list   = sc_data.get("risk", [])
        mild_risk   = mild_sc.get("risk", [])

        total_demand = sum(demand_vals.values())
        mild_total   = sum(mild_demand.values())
        avg_risk     = sum(risk_list[:num_I]) / num_I if num_I and risk_list else 0.0
        mild_avg     = sum(mild_risk[:num_I]) / num_I if num_I and mild_risk else 0.0

        d1, d2, d3 = st.columns(3)
        d1.metric("Total Relief Demand", f"{total_demand:,.0f} units",
                  delta=f"{total_demand - mild_total:+,.0f} vs Mild" if scenario_idx > 0 else None,
                  delta_color="inverse")
        d2.metric("Avg Node Risk", f"{avg_risk:.3f}",
                  delta=f"{avg_risk - mild_avg:+.3f} vs Mild" if scenario_idx > 0 else None,
                  delta_color="inverse")
        epicenters = sc_data.get("epicenters", [])
        d3.metric("Flood Epicentres", len(epicenters))

        # Layer toggles
        st.divider()
        st.write("**Scenario-dependent layers:**")
        t1, t2, t3, t4, t5, t6 = st.columns(6)
        ds_risk  = t1.checkbox("Risk",        value=True,  key="ds_risk")
        ds_dem   = t2.checkbox("Demand",      value=True,  key="ds_dem")
        ds_epi   = t3.checkbox("Epicentres",  value=True,  key="ds_epi")
        ds_road  = t4.checkbox("Road",        value=True,  key="ds_road")
        ds_water = t5.checkbox("Water",       value=True,  key="ds_water")
        ds_air   = t6.checkbox("Air",         value=False, key="ds_air")

        st.write("**Static layers (scenario-independent):**")
        s1, s2, s3 = st.columns([1, 1, 3])
        ds_pop   = s1.checkbox("Population circles",  value=False, key="ds_pop")
        ds_irisk = s2.checkbox("Intrinsic risk",      value=False, key="ds_irisk")
        # D9 — hide low-demand nodes
        min_pop = s3.slider(
            "Hide demand nodes with population <", min_value=0, max_value=5000,
            value=ss.get("min_pop_threshold", 0), step=100, key="min_pop_slider",
        )
        ss["min_pop_threshold"] = min_pop

        dmap = build_dataset_map(
            node_info=node_info, instance_data=inst_raw, scenario_idx=scenario_idx,
            show_risk=ds_risk, show_demand=ds_dem, show_epicenters=ds_epi,
            show_road=ds_road, show_water=ds_water, show_air=ds_air,
            show_population=ds_pop, show_intrinsic_risk=ds_irisk,
            min_pop_threshold=min_pop,
        )
        _dmap_key = (f"dmap_{dataset_name}_{version_name}_{scenario_idx}"
                     f"_{ds_risk}_{ds_dem}_{ds_epi}_{ds_road}_{ds_water}_{ds_air}"
                     f"_{ds_pop}_{ds_irisk}_{min_pop}")
        st_folium(dmap, width="100%", height=640, returned_objects=[], key=_dmap_key)

        st.download_button(
            "Export dataset map as HTML",
            data=dmap._repr_html_(),  # type: ignore[attr-defined]
            file_name=f"dataset_{dataset_name.lower().replace(' ','_')}_{version_name}_{sc_label.lower()}.html",
            mime="text/html",
        )

    # ════════════════════════════════════════════════════════════════════════
    # VIEW 3 — Experiments
    # ════════════════════════════════════════════════════════════════════════
    elif view == "📈 Experiments":
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
