"""
app.py — Streamlit entry point for the Disaster Relief Decision Support System.

Run from project root:
    streamlit run visualizer/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import streamlit as st

# ── path setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src" / "visualizer"))

from solution_loader import Solution, SolverResult  # noqa: E402
from visualizer.config import (  # noqa: E402
    DATASETS, VERSIONS,
    SC_NAMES, SC_PROBS, SC_ICONS,
    ALGO_LABELS, available_algorithms,
    get_explorer_config,
)
from visualizer.loaders import (  # noqa: E402
    cached_load_result, cached_load_instance, cached_load_instance_raw,
    get_solutions,
)
from visualizer.solver_runner import run_preprocess_flows  # noqa: E402
from visualizer.widgets import compute_knee, scenario_selector  # noqa: E402
from visualizer.pareto_view import build_pareto_fig  # noqa: E402
from visualizer.flow_loader import flows_available  # noqa: E402
from visualizer.solution_tab import render_solution_tab  # noqa: E402
from visualizer.dataset_view import build_dataset_map  # noqa: E402
from streamlit_folium import st_folium  # noqa: E402


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
    ss.setdefault("algorithm",         "pb_nsga")
    ss.setdefault("scenario_idx",      0)
    ss.setdefault("map_mode",          "Single scenario")
    ss.setdefault("min_demand_filter", 0)

    # ── Sidebar Part 1 — Dataset controls ────────────────────────────────────
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

        avail_algos = available_algorithms(dataset_name, version_name)
        if ss["algorithm"] not in avail_algos:
            ss["algorithm"] = avail_algos[0] if avail_algos else "pb_nsga"
        if len(avail_algos) > 1:
            algo_name = st.radio(
                "Algorithm",
                avail_algos,
                format_func=lambda a: ALGO_LABELS.get(a, a),
                index=avail_algos.index(ss["algorithm"]),
                horizontal=True,
                key="algorithm_radio",
            )
            ss["algorithm"] = algo_name
        else:
            algo_name = ss["algorithm"]

    paths = get_explorer_config(dataset_name, version_name, algo_name)
    dataset_label = f"{dataset_name} ({version_name}) · {ALGO_LABELS.get(algo_name, algo_name)}"

    # ── Load data ─────────────────────────────────────────────────────────────
    try:
        _inst_mtime = Path(paths["instance"]).stat().st_mtime
        result    = (cached_load_result(paths["result"], Path(paths["result"]).stat().st_mtime)
                     if paths.get("result") else None)
        node_info = cached_load_instance(paths["instance"], _inst_mtime)
        inst_raw  = cached_load_instance_raw(paths["instance"], _inst_mtime)
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        st.stop()

    solutions: List[Solution] = []
    sel_idx   = 0
    solution: Optional[Solution] = None
    no_feasible_msg: Optional[str] = None
    if result is not None:
        solutions = get_solutions(result, pf_only=True)
        if solutions:
            sel_idx  = min(ss["selected_idx"], len(solutions) - 1)
            solution = solutions[sel_idx]
        else:
            all_sols = result.pareto_front or result.all_feasible
            best_cv  = min((s.CV for s in all_sols), default=0.0)
            no_feasible_msg = (
                f"**{dataset_label}** has no zero-violation (CV=0) solutions — "
                f"best CV found: **{best_cv:,.2f}**. Try re-running EXP-1 or EXP-2 from the Experiments tab."
            )

    # ── Sidebar Part 2 — Mini Pareto + map controls ───────────────────────────
    with st.sidebar:
        st.divider()

        if solutions and len(solutions) > 1:
            knee_idx = compute_knee(solutions)
            st.markdown("**Pareto front** — click to select")
            _sfig = build_pareto_fig(solutions, selected_idx=sel_idx, title="")
            _sfig.update_layout(
                height=180, margin=dict(l=20, r=8, t=4, b=25),
                showlegend=False, dragmode="select",
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
                ss["selected_idx"] = knee_idx
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
        if algo_name != "pb_nsga":
            st.caption(
                f"ℹ️ **{ALGO_LABELS.get(algo_name, algo_name)}** flows are "
                "postprocessor estimates — hub/stock decisions (X, R) are exact; "
                "routing lines are approximated."
            )
        if paths.get("result"):
            avail  = flows_available(flows_dir=paths.get("flows_dir"))
            n_sols = len(solutions)
            flows_ok = avail and (n_sols == 0 or len(avail) >= n_sols)

            if not avail:
                st.info("No flow data yet.")
                btn_label = "⚙️ Generate Flows"
            elif not flows_ok:
                st.warning(f"Flow data: **{len(avail)}/{n_sols}** solutions — stale.")
                btn_label = "⚙️ Regenerate Flows"
            else:
                st.success(f"Flow data: {len(avail)} solution(s) pre-computed")
                btn_label = "⚙️ Regenerate Flows"

            if st.button(btn_label, use_container_width=True, key="regen_flows"):
                if run_preprocess_flows(
                    paths["instance"], paths["result"], paths["flows_dir"]
                ):
                    st.cache_data.clear()
                    st.rerun()
        else:
            st.info(f"No solver output for **{dataset_label}** yet.")


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
                    f"No **{ALGO_LABELS.get(algo_name, algo_name)}** result found for "
                    f"**{dataset_name} ({version_name})**. "
                    "Run the experiment from the Experiments tab to generate one."
                )
        else:
            render_solution_tab(
                solutions=solutions,
                sel_idx=sel_idx,
                solution=solution,
                node_info=node_info,
                inst_raw=inst_raw,
                result=result,
                map_mode=map_mode,
                min_demand_filter=min_demand_filter,
                paths=paths,
                num_hubs=len(node_info.hub_indices),
            )

    # ════════════════════════════════════════════════════════════════════════
    # TAB 2 — Input Dataset Explorer
    # ════════════════════════════════════════════════════════════════════════
    with tab_ds:
        st.markdown("**Flood scenario**")
        scenario_idx = scenario_selector("ds")
        ss["scenario_idx"] = scenario_idx
        sc_label = SC_NAMES[scenario_idx]
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
            import importlib
            import visualizer.experiments_tab as _etab
            importlib.reload(_etab)
            _etab.render(dataset_name, version_name, inst_raw, node_info)
        except ImportError:
            st.info(
                "Experiments tab (`visualizer/experiments_tab.py`) is not yet available. "
                "It will be added in the next implementation step.",
                icon="🔧",
            )


if __name__ == "__main__":
    main()
