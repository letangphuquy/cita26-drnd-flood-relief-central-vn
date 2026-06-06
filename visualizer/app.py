"""
app.py — Streamlit entry point for the Disaster Relief Visualizer.

Run from project root:
    streamlit run visualizer/app.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from streamlit_folium import st_folium

# ── path setup ───────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))                        # makes `visualizer.*` importable
sys.path.insert(0, str(_ROOT / "src" / "visualizer")) # makes `solution_loader` importable

from solution_loader import (
    NodeInfo, Solution, SolverResult,
    load_instance, load_result, deduplicate_solutions,
)
from visualizer.pareto_view import build_pareto_fig
from visualizer.map_view import build_map
from visualizer.flow_loader import (
    load_solution_flow, load_fallback_flow, flows_available, SolutionFlow,
)

# ── preset dataset paths ──────────────────────────────────────────────────────
_DATASETS = {
    "CV Large (case study)": {
        "result":    str(_ROOT / "results" / "exp2" / "CV_large_seed0.json"),
        "instance":  str(_ROOT / "data" / "cv" / "cv_large_drnd.json"),
        "flows_dir": _ROOT / "results" / "exp2" / "flows",
    },
    "CV Small": {
        "result":    str(_ROOT / "results" / "exp1" / "cv_small_pb_nsga.json"),
        "instance":  str(_ROOT / "data" / "cv" / "cv_small_drnd.json"),
        "flows_dir": _ROOT / "results" / "exp1" / "flows",
    },
}

_SCENARIO_NAMES = ["Mild", "Severe", "Extreme"]


# ── data loaders (cached) ─────────────────────────────────────────────────────

@st.cache_data(show_spinner="Loading solver results…")
def _load_result(path: str) -> SolverResult:
    return load_result(path)


@st.cache_data(show_spinner="Loading instance…")
def _load_instance(path: str) -> NodeInfo:
    return load_instance(path)


@st.cache_data(show_spinner="Loading instance JSON…")
def _load_instance_raw(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_solutions(result: SolverResult, pf_only: bool) -> List[Solution]:
    sols = result.pareto_front if pf_only else (result.all_feasible or result.pareto_front)
    deduped, _ = deduplicate_solutions([s for s in sols if s.CV == 0.0], mode="objective")
    return deduped


def _pick_flow(sol_idx: int, solution: Solution, result: SolverResult,
               scenario_idx: int, num_hubs: int,
               flows_dir: Optional[Any] = None) -> Optional[Any]:
    """Return ScenarioFlow for *sol_idx* + *scenario_idx*, or None.

    Discards any flow whose hub count doesn't match the current dataset so that
    CV_large pre-generated flows are never used for CV_small (and vice versa).
    """
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


# ── Streamlit layout ──────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="Disaster Relief Visualizer",
        page_icon="🗺️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Session state defaults ────────────────────────────────────────────────
    if "selected_idx" not in st.session_state:
        st.session_state["selected_idx"] = 0
    if "dataset" not in st.session_state:
        st.session_state["dataset"] = list(_DATASETS.keys())[0]

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.title("🗺️ Relief Network Visualizer")
        st.caption("MO-IHLNDP · PB-NSGA · Central Vietnam")
        st.divider()

        dataset_name = st.radio(
            "Dataset", list(_DATASETS.keys()),
            index=list(_DATASETS.keys()).index(st.session_state["dataset"]),
            key="dataset_radio",
        )
        st.session_state["dataset"] = dataset_name
        paths = _DATASETS[dataset_name]

        st.divider()

        scenario_idx = st.radio(
            "Flood scenario",
            options=[0, 1, 2],
            format_func=lambda i: _SCENARIO_NAMES[i],
            horizontal=True,
            key="scenario_radio",
        )

        st.divider()

        pf_only = st.checkbox("Pareto front only", value=True)
        show_labels = st.checkbox("Node labels", value=False)
        show_alloc  = st.checkbox("Allocation routes", value=True)
        show_trans  = st.checkbox("Transshipment flows", value=True)

        st.divider()

        avail = flows_available(flows_dir=paths.get("flows_dir"))
        if avail:
            st.success(f"Flow data: {len(avail)} solution(s) pre-computed")
        else:
            st.info("No per-solution flows found.\n\nRun to generate:\n```\npython visualizer/preprocess_flows.py\n```")

    # ── Load data ─────────────────────────────────────────────────────────────
    try:
        result    = _load_result(paths["result"])
        node_info = _load_instance(paths["instance"])
        inst_raw  = _load_instance_raw(paths["instance"])
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        st.stop()

    solutions = _get_solutions(result, pf_only)
    if not solutions:
        st.warning("No feasible solutions loaded.")
        st.stop()

    sel_idx = min(st.session_state["selected_idx"], len(solutions) - 1)
    solution = solutions[sel_idx]

    # ── Header ────────────────────────────────────────────────────────────────
    st.title("Disaster Relief Network — Decision Support System")
    sc_label = _SCENARIO_NAMES[scenario_idx]
    st.caption(
        f"Dataset: **{dataset_name}** · Solver: **{result.solver}** · "
        f"Scenario: **{sc_label}** · "
        f"Solution {sel_idx + 1} / {len(solutions)}"
    )

    # ── Row 1: Pareto scatter + KPI ───────────────────────────────────────────
    col_pareto, col_kpi = st.columns([3, 2], gap="large")

    with col_pareto:
        st.subheader("Pareto Front")
        fig = build_pareto_fig(solutions, selected_idx=sel_idx, title="")
        event = st.plotly_chart(fig, on_select="rerun", key="pareto_chart",
                                use_container_width=True)

        # Handle click → update selected solution
        try:
            pts = event.selection.points  # type: ignore[union-attr]
            if pts:
                clicked_idx = int(pts[0].customdata[0])  # type: ignore[index]
                if clicked_idx != sel_idx:
                    st.session_state["selected_idx"] = clicked_idx
                    st.rerun()
        except (AttributeError, TypeError, IndexError):
            pass

        # Manual navigation
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

    with col_kpi:
        st.subheader("KPI Dashboard")

        # Compute deltas vs best-Z1 and best-Z2 references
        best_z1 = min(s.Z1 for s in solutions)
        best_z2 = min(s.Z2 for s in solutions)
        max_hubs = len(node_info.hub_indices)

        k1, k2, k3 = st.columns(3)
        k1.metric(
            "Z1 — Logistics Cost",
            f"{solution.Z1 / 1e6:.2f} M",
            delta=f"{(solution.Z1 - best_z1) / 1e6:+.2f} M vs best",
            delta_color="inverse",
            help="Expected total logistics cost (lower is better)",
        )
        k2.metric(
            "Z2 — Deprivation Cost",
            f"{solution.Z2 / 1e6:.2f} M",
            delta=f"{(solution.Z2 - best_z2) / 1e6:+.2f} M vs best",
            delta_color="inverse",
            help="Expected max deprivation cost (lower is better)",
        )
        k3.metric(
            "Open Hubs",
            f"{solution.num_open_hubs} / {max_hubs}",
            help="Number of established relief hubs",
        )

        st.divider()

        # Mode breakdown
        modes = [a for a in solution.A if a in (0, 1, 2)]
        if modes:
            mode_counts = {0: modes.count(0), 1: modes.count(1), 2: modes.count(2)}
            st.write("**Transport modes (demand assignments)**")
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("🚚 Road", mode_counts[0])
            mc2.metric("🚤 Water", mode_counts[1])
            mc3.metric("🚁 Air", mode_counts[2])

        st.divider()

        # Solution details expander
        with st.expander("Solution details"):
            open_hub_names = [
                node_info.names[node_info.hub_indices[k]]
                if node_info.hub_indices[k] < len(node_info.names)
                else f"Hub {k}"
                for k in solution.open_hubs
            ]
            st.write(f"**Open hubs ({solution.num_open_hubs}):**")
            for name in open_hub_names:
                st.write(f"  • {name}")
            st.write(f"**Rank:** {solution.rank} &nbsp; **CV:** {solution.CV:.4f}")
            st.write(f"**Crowding distance:** {solution.crowding:.3f}")

        # Quick-jump buttons
        st.write("**Quick-jump:**")
        qj1, qj2, qj3 = st.columns(3)
        if qj1.button("Best Z1", use_container_width=True):
            best_idx = min(range(len(solutions)), key=lambda i: solutions[i].Z1)
            st.session_state["selected_idx"] = best_idx
            st.rerun()
        if qj2.button("Best Z2", use_container_width=True):
            best_idx = min(range(len(solutions)), key=lambda i: solutions[i].Z2)
            st.session_state["selected_idx"] = best_idx
            st.rerun()
        if qj3.button("Compromise", use_container_width=True):
            z1s = [s.Z1 for s in solutions]; z2s = [s.Z2 for s in solutions]
            z1r = max(z1s) - min(z1s) or 1.0; z2r = max(z2s) - min(z2s) or 1.0
            z1m = min(z1s); z2m = min(z2s)
            idx = min(range(len(solutions)),
                      key=lambda i: ((solutions[i].Z1-z1m)/z1r)**2 + ((solutions[i].Z2-z2m)/z2r)**2)
            st.session_state["selected_idx"] = idx
            st.rerun()

    # ── Row 2: Map ────────────────────────────────────────────────────────────
    st.divider()
    st.subheader(f"Geospatial Network Map — Scenario: {sc_label}")

    flow_sc = _pick_flow(sel_idx, solution, result, scenario_idx,
                         num_hubs=len(node_info.hub_indices),
                         flows_dir=paths.get("flows_dir"))
    if flow_sc is None:
        st.info(
            "Detailed routing not available for this solution. "
            "Showing approximate hub placement + A-vector mode assignments. "
            "Run `python visualizer/preprocess_flows.py` to generate full routing.",
            icon="ℹ️",
        )

    fmap = build_map(
        node_info=node_info,
        solution=solution,
        scenario_flow=flow_sc,
        instance_data=inst_raw,
        scenario_idx=scenario_idx,
        show_labels=show_labels,
        show_alloc=show_alloc,
        show_transshipment=show_trans,
    )

    st_folium(fmap, width="100%", height=620, returned_objects=[], key=f"map_{sel_idx}_{scenario_idx}")

    # ── Export button ─────────────────────────────────────────────────────────
    map_html = fmap._repr_html_()  # type: ignore[attr-defined]
    st.download_button(
        label="Export map as HTML",
        data=map_html,
        file_name=f"relief_map_sol{sel_idx+1}_{sc_label.lower()}.html",
        mime="text/html",
    )


if __name__ == "__main__":
    main()
