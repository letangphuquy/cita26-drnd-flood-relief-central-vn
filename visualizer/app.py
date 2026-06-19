"""
app.py — Streamlit entry point for the Disaster Relief Visualizer.

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
from visualizer.dataset_view import build_dataset_map

# ── preset dataset paths ──────────────────────────────────────────────────────
# Two dataset versions per case study:
#   v1 = canonical dataset (K_n complete graph) — every existing solver result
#        and precomputed flow cache was generated against this instance.
#        The Delaunay edges shown in the Input Visualizer are a UI-rendering
#        fallback only; the underlying data model is K_n with all 8,646 pairs finite.
#   v2 = planar dataset (data/cv/v2/, pure Delaunay) — solved; result auto-detected.
# See data/cv/README.md for details.
_RESULTS_V2 = {
    "CV Large": _ROOT / "results" / "exp2" / "v2" / "CV_large_seed2.json",
    "CV Small": _ROOT / "results" / "exp1" / "v2" / "cv_small_pb_nsga.json",
}
_FLOWS_V2 = {
    "CV Large": _ROOT / "results" / "exp2" / "v2" / "flows",
    "CV Small": _ROOT / "results" / "exp1" / "v2" / "flows",
}

# ── solver invocation ──────────────────────────────────────────────────────
_SOLVER_BIN = _ROOT / "src" / "solver" / ("solver.exe" if sys.platform.startswith("win") else "solver")
_DEFAULT_GEN = {"CV Large": 500, "CV Small": 300}  # README Exp2/Exp1 conventions

# v2 instances encode unreachable transport edges as JSON `Infinity`, which
# Python's json module accepts but the solver's strict nlohmann::json parser
# rejects. Sanitized copies replace these with a large finite cost/time.
_INF_SENTINEL = 1e9

_DATASET_VERSIONS = {
    "CV Large": {
        "v1": {
            "result":    str(_ROOT / "results" / "exp2" / "CV_large_seed0.json"),
            "instance":  str(_ROOT / "data" / "cv" / "v1" / "cv_large_drnd.json"),
            "flows_dir": _ROOT / "results" / "exp2" / "flows",
        },
        "v2": {
            "result":    str(_RESULTS_V2["CV Large"]) if _RESULTS_V2["CV Large"].exists() else None,
            "instance":  str(_ROOT / "data" / "cv" / "v2" / "cv_large_drnd.json"),
            "flows_dir": _FLOWS_V2["CV Large"],
        },
    },
    "CV Small": {
        "v1": {
            "result":    str(_ROOT / "results" / "exp1" / "cv_small_pb_nsga.json"),
            "instance":  str(_ROOT / "data" / "cv" / "v1" / "cv_small_drnd.json"),
            "flows_dir": _ROOT / "results" / "exp1" / "flows",
        },
        "v2": {
            "result":    str(_RESULTS_V2["CV Small"]) if _RESULTS_V2["CV Small"].exists() else None,
            "instance":  str(_ROOT / "data" / "cv" / "v2" / "cv_small_drnd.json"),
            "flows_dir": _FLOWS_V2["CV Small"],
        },
    },
}

_SCENARIO_NAMES = ["Mild", "Severe", "Extreme"]


# ── data loaders (cached) ─────────────────────────────────────────────────────

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


# ── solver pipeline ────────────────────────────────────────────────────────

def _solver_targets(dataset_name: str, version_name: str, paths: Dict[str, Any]) -> Tuple[Path, Path]:
    """Return (result_path, flows_dir) the solver run should write to."""
    if version_name == "v1":
        return Path(paths["result"]), Path(paths["flows_dir"])
    return _RESULTS_V2[dataset_name], _FLOWS_V2[dataset_name]


def _sanitize_instance_for_solver(instance_path: str) -> Tuple[str, Optional[Path]]:
    """Return a JSON path safe to pass to the (strict) solver binary.

    If *instance_path* contains non-finite floats (`Infinity`/`-Infinity`/
    `NaN` — used by v2 instances to mark unreachable transport edges), write
    a sanitized copy with those replaced by ±`_INF_SENTINEL` to a temp file
    and return its path alongside the temp Path (for later cleanup).
    Otherwise return *instance_path* unchanged and `None`.
    """
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
            return math.copysign(_INF_SENTINEL, obj) if obj == obj else _INF_SENTINEL  # NaN -> +sentinel
        return obj

    cleaned = _clean(data)
    if not found:
        return instance_path, None

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(cleaned, tmp, allow_nan=False)
    tmp.close()
    return tmp.name, Path(tmp.name)


def _run_solver_pipeline(instance_path: str, result_path: Path, flows_dir: Path,
                         pop: int, gen: int, seed: int, algo: str) -> bool:
    """Run PB-NSGA-II then preprocess_flows.py, reporting progress via st.status().

    Returns True on success; shows st.error() with stderr on failure.
    """
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with st.status("Running solver pipeline…", expanded=True) as status:
        solver_instance_path, tmp_path = _sanitize_instance_for_solver(instance_path)
        if tmp_path is not None:
            st.write("Sanitizing non-finite values (`Infinity`) for the solver's strict JSON parser…")
        try:
            st.write(f"PB-NSGA-II: pop={pop}, gen={gen}, seed={seed}, algo={algo}")
            proc = subprocess.run(
                [str(_SOLVER_BIN), solver_instance_path, "--pop", str(pop), "--gen", str(gen),
                 "--seed", str(seed), "--algo", algo, "--out", str(result_path)],
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
             "--result", str(result_path), "--instance", instance_path,
             "--out-dir", str(flows_dir), "--force"],
            cwd=_ROOT, capture_output=True, text=True,
        )
        if proc2.returncode != 0:
            status.update(label="Flow preprocessing failed", state="error")
            st.error(proc2.stderr or "preprocess_flows.py exited with a non-zero status.")
            return False

        status.update(label="Done", state="complete")
    return True


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
        st.session_state["dataset"] = list(_DATASET_VERSIONS.keys())[0]
    if "dataset_version" not in st.session_state:
        st.session_state["dataset_version"] = "v1"

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.title("🗺️ Relief Network Visualizer")
        st.caption("MO-IHLNDP · PB-NSGA · Central Vietnam")
        st.divider()

        dataset_name = st.radio(
            "Dataset", list(_DATASET_VERSIONS.keys()),
            index=list(_DATASET_VERSIONS.keys()).index(st.session_state["dataset"]),
            key="dataset_radio",
        )
        st.session_state["dataset"] = dataset_name

        version_options = list(_DATASET_VERSIONS[dataset_name].keys())
        if st.session_state["dataset_version"] not in version_options:
            st.session_state["dataset_version"] = version_options[0]
        if st.session_state.get("dataset_version_radio") not in version_options:
            st.session_state["dataset_version_radio"] = st.session_state["dataset_version"]
        version_name = st.radio(
            "Dataset version",
            version_options,
            index=version_options.index(st.session_state["dataset_version"]),
            format_func=lambda v: "v1 — canonical" if v == "v1" else "v2 — planar",
            horizontal=True,
            key="dataset_version_radio",
        )
        st.session_state["dataset_version"] = version_name
        paths = _DATASET_VERSIONS[dataset_name][version_name]
        dataset_label = f"{dataset_name} ({version_name})"

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

        if paths.get("result"):
            avail = flows_available(flows_dir=paths.get("flows_dir"))
            if avail:
                st.success(f"Flow data: {len(avail)} solution(s) pre-computed")
            else:
                st.info("No per-solution flows found.\n\nRun to generate:\n```\npython visualizer/preprocess_flows.py\n```")
        else:
            st.info(f"No solver output for **{dataset_label}** yet.\n\nSolution Explorer is disabled — see the Input Dataset tab.")

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
                st.warning(
                    "v1 already has a canonical result used by existing figures/flows. "
                    "Re-running will overwrite it."
                )
                overwrite_ok = st.checkbox("Overwrite existing v1 result", value=False)

            if not _SOLVER_BIN.exists():
                st.error(f"Solver binary not found: `{_SOLVER_BIN.relative_to(_ROOT)}`. "
                         "Run `./compile.sh` (or `compile.bat`) first.")
            elif st.button("▶ Run Solver", use_container_width=True,
                            disabled=(version_name == "v1" and not overwrite_ok)):
                target_result, target_flows = _solver_targets(dataset_name, version_name, paths)
                if _run_solver_pipeline(paths["instance"], target_result, target_flows,
                                         int(pop), int(gen), int(seed), algo):
                    st.cache_data.clear()
                    st.session_state["selected_idx"] = 0
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
    sel_idx = 0
    solution: Optional[Solution] = None
    no_feasible_msg: Optional[str] = None
    if result is not None:
        solutions = _get_solutions(result, pf_only)
        if solutions:
            sel_idx = min(st.session_state["selected_idx"], len(solutions) - 1)
            solution = solutions[sel_idx]
        else:
            all_sols = result.pareto_front or result.all_feasible
            best_cv = min((s.CV for s in all_sols), default=0.0)
            no_feasible_msg = (
                f"**{dataset_label}** solver output has no zero-violation (CV=0) "
                f"solutions yet — best constraint violation found: **{best_cv:,.2f}**.\n\n"
                "This means some demand cannot be served under the current "
                "accessibility/capacity data. Try a different `--seed`/`--algo` "
                "via **Run Solver**, or use the **Input Dataset** tab to inspect "
                "this dataset's accessibility layers."
            )

    # ── Header + tabs ─────────────────────────────────────────────────────────
    st.title("Disaster Relief Network — Decision Support System")
    sc_label = _SCENARIO_NAMES[scenario_idx]

    tab1, tab2 = st.tabs(["🗺️ Solution Explorer", "📊 Input Dataset"])

    # ════════════════════════════════════════════════════════════════════════
    # TAB 1 — Solution Explorer
    # ════════════════════════════════════════════════════════════════════════
    with tab1:
        if result is None or solution is None:
            if no_feasible_msg:
                st.warning(no_feasible_msg)
            else:
                st.info(
                    f"**{dataset_label}** has no solver output yet — the "
                    "Solution Explorer is unavailable for this dataset "
                    "version.\n\nSwitch to **v1** to explore solutions, or "
                    "use the **Input Dataset** tab to inspect this dataset's "
                    "geography, road graph, risk and accessibility layers."
                )
        else:
            st.caption(
                f"Dataset: **{dataset_label}** · Solver: **{result.solver}** · "
                f"Scenario: **{sc_label}** · "
                f"Solution {sel_idx + 1} / {len(solutions)}"
            )

            # ── Row 1: Pareto scatter + KPI ───────────────────────────────────
            flow_sc = _pick_flow(sel_idx, solution, result, scenario_idx,
                                 num_hubs=len(node_info.hub_indices),
                                 flows_dir=paths.get("flows_dir"))
            col_pareto, col_kpi = st.columns([3, 2], gap="large")

            with col_pareto:
                st.subheader("Pareto Front")
                fig = build_pareto_fig(solutions, selected_idx=sel_idx, title="")
                event = st.plotly_chart(fig, on_select="rerun", key="pareto_chart",
                                        use_container_width=True)

                try:
                    pts = event.selection.points  # type: ignore[union-attr]
                    if pts:
                        clicked_idx = int(pts[0].customdata[0])  # type: ignore[index]
                        if clicked_idx != sel_idx:
                            st.session_state["selected_idx"] = clicked_idx
                            st.rerun()
                except (AttributeError, TypeError, IndexError):
                    pass

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

                if flow_sc is not None:
                    da_modes = [a.mode for a in flow_sc.demand_assignments]
                    mode_counts = {0: da_modes.count(0), 1: da_modes.count(1), 2: da_modes.count(2)}
                    st.write(f"**Transport modes — {sc_label}**")
                    mc1, mc2, mc3 = st.columns(3)
                    mc1.metric("🚚 Road", mode_counts[0])
                    mc2.metric("🚤 Water", mode_counts[1])
                    mc3.metric("🚁 Air", mode_counts[2])

                st.divider()

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

            # ── Row 2: Map ────────────────────────────────────────────────────
            st.divider()
            st.subheader(f"Geospatial Network Map — Scenario: {sc_label}")

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

            st_folium(fmap, width="100%", height=620, returned_objects=[],
                      key=f"map_{sel_idx}_{scenario_idx}")

            map_html = fmap._repr_html_()  # type: ignore[attr-defined]
            st.download_button(
                label="Export map as HTML",
                data=map_html,
                file_name=f"relief_map_sol{sel_idx+1}_{sc_label.lower()}.html",
                mime="text/html",
            )

    # ════════════════════════════════════════════════════════════════════════
    # TAB 2 — Input Dataset Explorer
    # ════════════════════════════════════════════════════════════════════════
    with tab2:
        sc_raw = inst_raw.get("scenarios", [])
        sc_data = sc_raw[scenario_idx] if scenario_idx < len(sc_raw) else {}
        mild_sc = sc_raw[0] if sc_raw else {}
        num_I   = inst_raw.get("dimensions", {}).get("num_I", len(node_info.demand_indices))

        st.caption(f"Dataset: **{dataset_label}** · Scenario: **{sc_label}**")

        # ── Scenario KPI summary ─────────────────────────────────────────
        demand_vals = {int(k): float(v) for k, v in sc_data.get("demand", {}).items()}
        mild_demand = {int(k): float(v) for k, v in mild_sc.get("demand", {}).items()}
        risk_list   = sc_data.get("risk", [])
        mild_risk   = mild_sc.get("risk", [])

        total_demand = sum(demand_vals.values())
        mild_total   = sum(mild_demand.values())
        avg_risk     = sum(risk_list[:num_I]) / num_I if num_I and risk_list else 0.0
        mild_avg_risk= sum(mild_risk[:num_I]) / num_I if num_I and mild_risk else 0.0

        d1, d2, d3 = st.columns(3)
        d1.metric(
            "Total Relief Demand",
            f"{total_demand:,.0f} units",
            delta=f"{total_demand - mild_total:+,.0f} vs Mild" if scenario_idx > 0 else None,
            delta_color="inverse",
            help="Sum of demand across all demand nodes in this scenario",
        )
        d2.metric(
            "Avg Node Risk",
            f"{avg_risk:.3f}",
            delta=f"{avg_risk - mild_avg_risk:+.3f} vs Mild" if scenario_idx > 0 else None,
            delta_color="inverse",
            help="Mean risk score [0-1] across demand nodes",
        )
        epicenters = sc_data.get("epicenters", [])
        d3.metric(
            "Flood Epicentres",
            len(epicenters),
            help="Number of flood origin points in this scenario",
        )

        # ── Layer toggles ────────────────────────────────────────────────
        st.divider()
        st.write("**Map layers:**")
        t1, t2, t3, t4, t5, t6 = st.columns(6)
        ds_risk  = t1.checkbox("Risk",       value=True,  key="ds_risk")
        ds_dem   = t2.checkbox("Demand",     value=True,  key="ds_dem")
        ds_epi   = t3.checkbox("Epicentres", value=True,  key="ds_epi")
        ds_road  = t4.checkbox("Road",       value=True,  key="ds_road")
        ds_water = t5.checkbox("Water",      value=True,  key="ds_water")
        ds_air   = t6.checkbox("Air",        value=False, key="ds_air")

        # ── Dataset map ──────────────────────────────────────────────────
        dmap = build_dataset_map(
            node_info=node_info,
            instance_data=inst_raw,
            scenario_idx=scenario_idx,
            show_risk=ds_risk,
            show_demand=ds_dem,
            show_epicenters=ds_epi,
            show_road=ds_road,
            show_water=ds_water,
            show_air=ds_air,
        )

        _dmap_key = (f"dmap_{dataset_name}_{version_name}_{scenario_idx}"
                     f"_{ds_risk}_{ds_dem}_{ds_epi}_{ds_road}_{ds_water}_{ds_air}")
        st_folium(dmap, width="100%", height=640, returned_objects=[],
                  key=_dmap_key)

        dmap_html = dmap._repr_html_()  # type: ignore[attr-defined]
        st.download_button(
            label="Export dataset map as HTML",
            data=dmap_html,
            file_name=f"dataset_{dataset_name.lower().replace(' ','_')}_{version_name}_{sc_label.lower()}.html",
            mime="text/html",
        )


if __name__ == "__main__":
    main()
