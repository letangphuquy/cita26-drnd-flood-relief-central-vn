"""
solution_tab.py — Solution Explorer tab renderer (Tab 1).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
import streamlit.components.v1 as cv1
from streamlit_folium import st_folium

from collections import defaultdict

import pandas as pd

from visualizer.config import SC_NAMES, SC_PROBS, SC_ICONS, MODE_NAMES
from visualizer.loaders import pick_flow
from visualizer.map_view import build_map
from visualizer.widgets import compute_knee, scenario_selector
from visualizer.pareto_view import build_pareto_fig


import sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src" / "visualizer") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src" / "visualizer"))

from solution_loader import NodeInfo, Solution, SolverResult  # noqa: E402

# ── FAB + DOM-patching JS (persists across Streamlit reruns) ─────────────────
_FAB_JS = """<script>
(function () {
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
        function update() { btn.textContent = nearPareto() ? '↑ Map' : '↓ Pareto'; }
        btn.onclick = function () {
            var target = nearPareto()
                ? pd.getElementById('_dss-map-anchor')
                : pd.getElementById('_dss-pareto-anchor');
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        };
        main.addEventListener('scroll', update);
        update();
    }
    init();

    // Hide the solution carousel when the sidebar is open.
    // Sentinel → stMarkdownContainer → stElementContainer; carousel is in the next stLayoutWrapper.
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

    // Inject sidebar re-expand button (Streamlit slides sidebar off-screen instead
    // of rendering a collapsedControl element, so we create our own).
    (function sidebarBtn() {
        var pd = window.parent.document;
        if (pd.getElementById('_dss-sidebar-btn')) return;
        var sb = pd.createElement('button');
        sb.id = '_dss-sidebar-btn';
        sb.textContent = '❯';
        sb.title = 'Expand sidebar';
        sb.onclick = function () {
            var collapseBtn = pd.querySelector('[data-testid="stBaseButton-headerNoPadding"]');
            if (collapseBtn) collapseBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
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

    // Streamlit overrides clickmode to "event" after every Plotly.react() call,
    // which prevents single-click from emitting plotly_selected. This poller
    // restores "event+select" so point clicks fire plotly_selected → on_select rerun.
    if (!window.__dss_patch_running) {
        window.__dss_patch_running = true;
        (function patch() {
            var pW = window.parent;
            var Plotly = pW.Plotly;
            if (Plotly) {
                pW.document.querySelectorAll('.js-plotly-plot').forEach(function (d) {
                    if (d._fullLayout && d._fullLayout.dragmode === 'select'
                            && d._fullLayout.clickmode !== 'event+select') {
                        Plotly.relayout(d, { clickmode: 'event+select' });
                    }
                });
            }
            setTimeout(patch, 350);
        })();
    }
})();
</script>"""

_FAB_CSS = """
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
"""


# ── D1 — Stage-2 Scenario Response ───────────────────────────────────────────

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
    scenarios_raw = inst_raw.get("scenarios", [])
    sc = scenarios_raw[scenario_idx] if scenario_idx < len(scenarios_raw) else {}
    hub_risk_dict = sc.get("hub_risk", {})
    chi = float(inst_raw.get("global_params", {}).get("chi", 0.70))

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
            st.warning(f"⚡ **{len(reactive_ks)} reactive hub(s) opened:** {', '.join(r_names)}", icon=None)
        else:
            st.caption("ⓘ No reactive hubs opened this scenario.")

    st.divider()

    if flow_sc is not None:
        da_modes = [a.mode for a in flow_sc.demand_assignments]
        curr_counts = {0: da_modes.count(0), 1: da_modes.count(1), 2: da_modes.count(2)}
        total = sum(curr_counts.values())

        st.write(f"**{total} communes assigned — rescue dispatch modes:**")
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("🚚 Road",  curr_counts[0])
        mc2.metric("🚤 Water", curr_counts[1])
        mc3.metric("🚁 Air",   curr_counts[2])

        if scenario_idx > 0 and mild_flow_sc is not None:
            mild_modes = [a.mode for a in mild_flow_sc.demand_assignments]
            mild_counts = {0: mild_modes.count(0), 1: mild_modes.count(1), 2: mild_modes.count(2)}
            deltas = {m: curr_counts[m] - mild_counts[m] for m in (0, 1, 2)}
            changed = [f"{'+' if d>0 else ''}{d} {MODE_NAMES[m]}" for m, d in deltas.items() if d != 0]
            if changed:
                st.caption(f"vs Mild: {' · '.join(changed)} — communes rerouted due to flooding")

        st.caption("ⓘ Mode counts are postprocessor estimates; MCF lateral flows not shown")

        hub_communes: dict = defaultdict(lambda: {0: 0, 1: 0, 2: 0})
        for asgn in flow_sc.demand_assignments:
            if asgn.hub_idx >= 0:
                hub_communes[asgn.hub_idx][asgn.mode] += 1

        if hub_communes:
            st.divider()
            st.write("**Commune assignments per hub:**")
            hub_rows, air_hubs = [], []
            for h_idx, modes in sorted(hub_communes.items(), key=lambda x: -sum(x[1].values())):
                name = node_info.names[h_idx] if h_idx < len(node_info.names) else f"Node {h_idx}"
                hub_rows.append({
                    "Hub": name, "Total": sum(modes.values()),
                    "🚚 Road": modes[0], "🚤 Water": modes[1], "🚁 Air": modes[2],
                })
                if modes[2] > 0:
                    air_hubs.append((name, modes[2]))
            st.dataframe(pd.DataFrame(hub_rows), hide_index=True, use_container_width=True)
            if air_hubs:
                st.info(f"🚁 Helicopter service: {' · '.join(f'**{n}** ({c})' for n, c in air_hubs)}", icon=None)
    else:
        st.info("Detailed mode breakdown requires flow files. Run preprocess_flows.py.", icon="ℹ️")

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


# ── D2 — Stage-1 Pre-Disaster Plan ───────────────────────────────────────────

def _render_stage1_panel(
    solution: Solution,
    node_info: NodeInfo,
    inst_raw: Dict[str, Any],
) -> None:
    hub_params = inst_raw.get("hub_params", {})
    cap_dict   = hub_params.get("capacity",   {})
    fc_dict    = hub_params.get("fixed_cost", {})
    hc_dict    = hub_params.get("hold_cost",  {})

    rows, total_prestock, total_hold_cost = [], 0.0, 0.0
    for k in solution.open_hubs:
        h_idx    = node_info.hub_indices[k]
        name     = node_info.names[h_idx] if h_idx < len(node_info.names) else f"Hub {k}"
        cap      = float(cap_dict.get(str(h_idx), 0))
        fc       = float(fc_dict.get(str(h_idx), 0))
        hc_rate  = float(hc_dict.get(str(h_idx), 0))
        r_k      = solution.R[k] if k < len(solution.R) else 0.0
        prestock = r_k * cap
        hold_cost = hc_rate * prestock
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
        total_prestock  += prestock
        total_hold_cost += hold_cost

    if rows:
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


# ── D3 — Pareto Front & Navigation ───────────────────────────────────────────

def _render_pareto_panel(
    solutions: List[Solution],
    sel_idx: int,
    solution: Solution,
    node_info: NodeInfo,
) -> None:
    z1s = [s.Z1 for s in solutions]
    z2s = [s.Z2 for s in solutions]
    z1_min, z1r = min(z1s), (max(z1s) - min(z1s)) or 1.0
    z2_min, z2r = min(z2s), (max(z2s) - min(z2s)) or 1.0
    knee_idx = compute_knee(solutions)

    is_knee      = (sel_idx == knee_idx)
    cost_premium = (solution.Z1 - z1_min) / z1_min * 100 if z1_min > 0 else 0.0
    z2_reduction = (max(z2s) - solution.Z2) / z2r * 100 if z2r > 0 else 0.0

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


def render_solution_tab(
    solutions: List[Solution],
    sel_idx: int,
    solution: Solution,
    node_info: NodeInfo,
    inst_raw: Dict[str, Any],
    result: SolverResult,
    map_mode: str,
    min_demand_filter: int,
    paths: Dict[str, Any],
    num_hubs: int,
) -> None:
    """Render the full Solution Explorer tab content."""
    ss = st.session_state

    # sentinel used by FAB JS to locate and hide the carousel when sidebar is open
    st.markdown('<span id="_dss-carousel-sentinel" style="display:none"></span>',
                unsafe_allow_html=True)

    # ── Solution carousel ─────────────────────────────────────────────────────
    if len(solutions) > 1:
        knee = compute_knee(solutions)
        z1s  = [s.Z1 for s in solutions]
        z2s  = [s.Z2 for s in solutions]
        badge = ("⭐ Knee"    if sel_idx == knee else
                 "💰 Best Z1" if sel_idx == z1s.index(min(z1s)) else
                 "⚖️ Best Z2" if sel_idx == z2s.index(min(z2s)) else "")
        _cc1, _cc2, _cc3 = st.columns([1, 10, 1])
        with _cc1:
            if st.button("◀", key="car_prev", use_container_width=True):
                ss["selected_idx"] = (sel_idx - 1) % len(solutions)
                st.rerun()
        with _cc2:
            badge_html = (f' <span style="background:#1976D2;color:white;'
                          f'padding:1px 7px;border-radius:4px;font-size:11px">{badge}</span>'
                          if badge else "")
            st.markdown(
                f'<div style="text-align:center;padding:5px 10px;background:#f0f2f6;'
                f'border-radius:6px;font-size:13px">'
                f'<b>Solution {sel_idx + 1} / {len(solutions)}</b>{badge_html}'
                f' · Z1 = <b>&#36;{solution.Z1/1e6:.2f}M</b>'
                f' · Z2 = <b>{solution.Z2:,.0f}</b>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with _cc3:
            if st.button("▶", key="car_next", use_container_width=True):
                ss["selected_idx"] = (sel_idx + 1) % len(solutions)
                st.rerun()

    # ── Scenario selector ─────────────────────────────────────────────────────
    compare_mode = (map_mode == "Compare all 3 scenarios")
    st.markdown("**Flood scenario**")
    scenario_idx = scenario_selector("sol", disabled=compare_mode)
    if compare_mode:
        st.caption("All 3 scenarios shown on map — switch to Single to filter.")
    ss["scenario_idx"] = scenario_idx
    sc_label = SC_NAMES[scenario_idx]

    # Load flows
    flow_sc = pick_flow(sel_idx, solution, result, scenario_idx,
                        num_hubs=num_hubs, flows_dir=paths.get("flows_dir"))
    mild_flow_sc = (pick_flow(sel_idx, solution, result, 0,
                              num_hubs=num_hubs, flows_dir=paths.get("flows_dir"))
                    if scenario_idx > 0 else flow_sc)

    if flow_sc is None:
        st.info(
            "Detailed routing unavailable — showing approximate hub placement. "
            "Run `python visualizer/preprocess_flows.py` to generate full routing.",
            icon="ℹ️",
        )

    # ── Map ───────────────────────────────────────────────────────────────────
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
        st.download_button(
            "Export map as HTML", data=fmap._repr_html_(),  # type: ignore[attr-defined]
            file_name=f"relief_map_sol{sel_idx+1}_{sc_label.lower()}.html",
            mime="text/html",
        )
    else:
        cols = st.columns(3)
        for s_idx, (col, sc_name, sc_icon) in enumerate(zip(cols, SC_NAMES, SC_ICONS)):
            with col:
                st.caption(f"{sc_icon} **{sc_name}** (p={SC_PROBS[s_idx]})")
                fsc = pick_flow(sel_idx, solution, result, s_idx,
                                num_hubs=num_hubs, flows_dir=paths.get("flows_dir"))
                fm = build_map(
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

    # ── Stage 2 — Scenario Response ───────────────────────────────────────────
    st.divider()
    if compare_mode:
        st.subheader("📊 Stage 2 — Scenario Response")
        _s2_tabs = st.tabs([f"{SC_ICONS[i]} {SC_NAMES[i]}" for i in range(3)])
        for _s2_idx, _s2_tab in enumerate(_s2_tabs):
            with _s2_tab:
                _s2_flow = pick_flow(sel_idx, solution, result, _s2_idx,
                                     num_hubs=num_hubs, flows_dir=paths.get("flows_dir"))
                _s2_mild = (pick_flow(sel_idx, solution, result, 0,
                                      num_hubs=num_hubs, flows_dir=paths.get("flows_dir"))
                            if _s2_idx > 0 else _s2_flow)
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

    # ── Stage 1 — Pre-Disaster Plan ───────────────────────────────────────────
    st.divider()
    st.subheader("🏗️ Stage 1 — Pre-Disaster Plan")
    _render_stage1_panel(solution=solution, node_info=node_info, inst_raw=inst_raw)

    # ── Pareto Front & Navigation ─────────────────────────────────────────────
    st.divider()
    st.markdown('<div id="_dss-pareto-anchor"></div>', unsafe_allow_html=True)
    st.subheader("📈 Pareto Front & Navigation")
    _render_pareto_panel(
        solutions=solutions, sel_idx=sel_idx,
        solution=solution, node_info=node_info,
    )

    # ── FAB scroll button + DOM helpers (persistent iframe) ───────────────────
    st.markdown(_FAB_CSS, unsafe_allow_html=True)
    cv1.html(_FAB_JS, height=0)
