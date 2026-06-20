"""
map_view.py — Build a Folium geospatial map for a CITA solution.

build_map(...) → folium.Map
Embed in Streamlit via:  st_folium(m, width="100%", height=600)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import folium
from folium.plugins import MarkerCluster  # noqa: F401 (kept for potential future use)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "visualizer"))
from solution_loader import NodeInfo, Solution, infer_hub_allocations
from visualizer.flow_loader import ScenarioFlow

# ── colour constants ──────────────────────────────────────────────────────────
_MODE_COLOURS  = {0: "#E53935", 1: "#039BE5", 2: "#7CB342"}  # road/water/air
_MODE_NAMES    = {0: "Road", 1: "Water/Boat", 2: "Air/Helicopter"}
_MODE_ICONS    = {0: "🚚", 1: "🚤", 2: "🚁"}
_MODE_DASHES   = {0: None, 1: [8, 4], 2: [2, 4]}

_COL_HUB_OPEN     = "#FF7043"
_COL_HUB_INACTIVE = "#FFB74D"
_COL_HUB_CLOSED   = "#9E9E9E"
_COL_ORIGIN       = "#43A047"
_COL_DEMAND_DEF   = "#4C72B0"
_COL_ALLOC        = "#BBBBBB"
_COL_BLOCKED      = "#EF5350"
_MODE_COLOURS_FADED = {0: "#FFCDD2", 1: "#B3E5FC", 2: "#DCEDC8"}

_SC_NAMES = ["Mild", "Severe", "Extreme"]
_SC_ICONS = ["🌊", "⚠️", "🔴"]


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _hub_icon(state: str) -> folium.DivIcon:
    if state == "active":
        colour, size, border = _COL_HUB_OPEN, 18, "2px solid #5D4037"
    elif state == "inactive":
        colour, size, border = _COL_HUB_INACTIVE, 18, "2px dashed #5D4037"
    else:
        colour, size, border = _COL_HUB_CLOSED, 12, "1px solid #555"
    return folium.DivIcon(
        html=(
            f'<div style="width:{size}px;height:{size}px;'
            f'background:{colour};border:{border};'
            f'transform:rotate(45deg);'
            f'margin-top:{(18-size)//2}px;margin-left:{(18-size)//2}px"></div>'
        ),
        icon_size=(18, 18),
        icon_anchor=(9, 9),
    )


def _origin_icon() -> folium.DivIcon:
    return folium.DivIcon(
        html=(
            '<div style="width:0;height:0;'
            'border-left:9px solid transparent;'
            'border-right:9px solid transparent;'
            'border-bottom:16px solid #43A047;'
            'margin-top:2px"></div>'
        ),
        icon_size=(18, 18),
        icon_anchor=(9, 16),
    )


# ── popup builders ────────────────────────────────────────────────────────────

def _hub_popup_html(
    k: int,
    h_idx: int,
    label: str,
    open_: bool,
    scenario_idx: int,
    chi: float,
    solution: Solution,
    instance_data: Dict[str, Any],
    scenario_flow: Optional[ScenarioFlow],
    node_info: NodeInfo,
) -> str:
    hub_params   = instance_data.get("hub_params", {})
    scenarios_raw = instance_data.get("scenarios", [])
    base_pop     = instance_data.get("base_population", {})

    capacity  = float(hub_params.get("capacity",  {}).get(str(h_idx), 0))
    fc        = float(hub_params.get("fixed_cost", {}).get(str(h_idx), 0))
    hc_rate   = float(hub_params.get("hold_cost",  {}).get(str(h_idx), 0))
    r_k       = solution.R[k] if k < len(solution.R) else 0.0
    prestock  = r_k * capacity
    hold_cost = hc_rate * prestock  # c_k * q_k — Stage-1 cost

    rows: List[str] = [
        f"<b style='font-size:13px'>{label}</b>",
        f"<span style='color:#888;font-size:11px'>H{k} · global node {h_idx}</span>",
        "",
    ]

    if not open_:
        rows.append("❌ <b>Not established (Stage-1)</b>")
        _c = "<br>".join(rows)
        return f'<div style="font-size:11px;line-height:1.5;max-width:280px">{_c}</div>'

    rows += [
        "✅ <b>ESTABLISHED</b>",
        f"Pre-positioned: <b>{prestock:,.0f} kg</b> ({r_k*100:.0f}% of {capacity:,.0f} kg)",
        f"Fixed cost: <b>${fc:,.0f}</b> · Hold cost (Stage-1): <b>${hold_cost:,.0f}</b>",
        "",
        "<b>Flood risk per scenario:</b>",
    ]

    for s_idx, sc_name in enumerate(_SC_NAMES):
        if s_idx >= len(scenarios_raw):
            continue
        hr    = scenarios_raw[s_idx].get("hub_risk", {})
        r_val = float(hr.get(str(h_idx), 0.0))
        safe  = r_val <= chi
        icon  = "✅" if safe else "⚠️"
        note  = "" if safe else f" — <span style='color:#c62828'>INACTIVE (r &gt; χ={chi})</span>"
        cur   = " ◀" if s_idx == scenario_idx else ""
        rows.append(f"  {icon} <b>{sc_name}</b>: r={r_val:.2f}{note}{cur}")

    # Rescue zones served this scenario
    if scenario_flow is not None:
        sc_name = _SC_NAMES[scenario_idx] if scenario_idx < len(_SC_NAMES) else ""
        served  = [a for a in scenario_flow.demand_assignments if a.hub_idx == h_idx]
        if served:
            mode_cnts: Dict[int, int] = {}
            for a in served:
                mode_cnts[a.mode] = mode_cnts.get(a.mode, 0) + 1
            mode_str = " · ".join(
                f"{_MODE_ICONS.get(m,'?')} {_MODE_NAMES.get(m,'?')} ×{cnt}"
                for m, cnt in sorted(mode_cnts.items()) if cnt > 0
            )
            top_a = max(served, key=lambda a: float(base_pop.get(str(a.demand_idx), 0)), default=None)
            top_str = ""
            if top_a:
                top_pop  = int(float(base_pop.get(str(top_a.demand_idx), 0)))
                top_name = (node_info.names[top_a.demand_idx]
                            if top_a.demand_idx < len(node_info.names)
                            else f"Node {top_a.demand_idx}")
                if top_pop > 0:
                    top_str = f"<br>  Highest-demand: {top_name} ({top_pop:,} persons)"
            rows += [
                "",
                f"<b>Rescue zones [{sc_name}]: {len(served)} communes</b>",
                mode_str + top_str,
            ]

    _c = "<br>".join(rows)
    return f'<div style="font-size:11px;line-height:1.5;max-width:280px">{_c}</div>'


def _origin_popup_html(o_idx: int, label: str, instance_data: Dict[str, Any]) -> str:
    scenarios_raw = instance_data.get("scenarios", [])
    rows: List[str] = [
        f"<b style='font-size:13px'>{label}</b>",
        "<span style='color:#888;font-size:11px'>Supply depot · Origin node</span>",
        "",
        "<b>Supply available:</b>",
    ]
    risk_parts: List[str] = []
    for s_idx, sc_name in enumerate(_SC_NAMES):
        if s_idx >= len(scenarios_raw):
            continue
        sc     = scenarios_raw[s_idx]
        supply = float(sc.get("supply", {}).get(str(o_idx), 0.0))
        risk_list = sc.get("risk", [])
        risk   = float(risk_list[o_idx]) if o_idx < len(risk_list) else 0.0
        rows.append(f"  <b>{sc_name}</b>: {supply:,.0f} kg")
        risk_parts.append(f"<b>{sc_name}</b>: {risk:.2f}")
    rows += ["", "<b>Flood risk:</b>", "  " + " · ".join(risk_parts)]
    _c = "<br>".join(rows)
    return f'<div style="font-size:11px;line-height:1.5;max-width:250px">{_c}</div>'


# ── main API ──────────────────────────────────────────────────────────────────

def _demand_popup_html(
    d_idx: int,
    label: str,
    mode: int,
    hub_label: str,
    accessible: bool,
    instance_data: Dict[str, Any],
    scenario_idx: int,
) -> str:
    scenarios_raw = instance_data.get("scenarios", [])
    aux_risk_list = instance_data.get("nodes", {}).get("aux_risk", [])
    sc            = scenarios_raw[scenario_idx] if scenario_idx < len(scenarios_raw) else {}

    sc_risk_list = sc.get("risk", [])
    demand_dict  = sc.get("demand", {})

    sc_risk_v  = float(sc_risk_list[d_idx]) if d_idx < len(sc_risk_list) else 0.0
    aux_risk_v = float(aux_risk_list[d_idx]) if d_idx < len(aux_risk_list) else 0.0
    demand_v   = float(demand_dict.get(str(d_idx), 0.0))

    acc_str = "" if accessible else " <span style='color:#c62828'>(route blocked)</span>"
    rows = [
        f"<b>{label}</b>",
        f"<span style='color:#888'>Demand node #{d_idx}</span>",
        "",
        f"Mode: <b>{_MODE_NAMES.get(mode, '?')} {_MODE_ICONS.get(mode, '')}</b>{acc_str}",
    ]
    if hub_label:
        rows.append(f"→ {hub_label}")
    rows += [
        "",
        f"Demand: <b>{demand_v:,.0f}</b> persons",
        f"Scenario risk: <b>{sc_risk_v:.3f}</b>",
        f"Intrinsic risk (aux): <b>{aux_risk_v:.3f}</b>",
    ]
    _c = "<br>".join(rows)
    return f'<div style="font-size:11px;line-height:1.5;max-width:240px">{_c}</div>'


def build_map(
    node_info: NodeInfo,
    solution: Solution,
    scenario_flow: Optional[ScenarioFlow],
    instance_data: Dict[str, Any],
    scenario_idx: int = 0,
    show_labels: bool = True,
    show_alloc: bool = True,
    show_transshipment: bool = True,
    compact: bool = False,
    min_demand_filter: int = 0,
) -> folium.Map:
    """
    Build and return a Folium map for one solution in one scenario.

    Parameters
    ----------
    node_info      : Parsed node metadata (coords, indices, names).
    solution       : Selected Pareto solution.
    scenario_flow  : Optional pre-computed flow for this scenario.
                     If None, allocation is inferred from X and A vectors.
    instance_data  : Raw loaded instance dict (all scenarios, hub_params, etc.).
    scenario_idx   : Which scenario to render (0=mild, 1=severe, 2=extreme).
    show_labels    : Draw node name labels.
    show_alloc     : Draw demand→hub allocation lines.
    show_transshipment : Draw hub-to-hub flow lines.
    """
    coords     = node_info.coords
    hub_set    = set(node_info.hub_indices)
    origin_set = set(node_info.origin_indices)
    demand_set = set(node_info.demand_indices)

    open_hub_globals = {node_info.hub_indices[k] for k in solution.open_hubs}

    chi = float(instance_data.get("global_params", {}).get("chi", 0.70))

    scenarios_raw = instance_data.get("scenarios", [])
    sc_access: Optional[List] = None
    if scenario_idx < len(scenarios_raw):
        sc_access = scenarios_raw[scenario_idx].get("accessibility")

    def _is_accessible(mode: int, src: int, dst: int) -> bool:
        if sc_access is None:
            return True
        try:
            return bool(sc_access[mode][src][dst])
        except (IndexError, TypeError):
            return True

    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    centre = (sum(lats) / len(lats), sum(lons) / len(lons))

    m = folium.Map(location=centre, zoom_start=9, tiles="OpenStreetMap", control_scale=True)

    fg_hubs   = folium.FeatureGroup(name="Hubs", show=True)
    fg_demand = folium.FeatureGroup(name="Demand nodes", show=True)
    fg_orig   = folium.FeatureGroup(name="Supply origins", show=True)
    fg_alloc  = folium.FeatureGroup(name="Allocation routes", show=show_alloc)
    fg_trans  = folium.FeatureGroup(name="Transshipment flows", show=show_transshipment)

    # ── Demand→hub assignments ────────────────────────────────────────────────
    if scenario_flow is not None:
        da = {a.demand_idx: a for a in scenario_flow.demand_assignments}
        oa = {a.origin_idx: a for a in scenario_flow.origin_assignments}
        active_hubs = {
            node_info.hub_indices[k]
            for k, active in enumerate(scenario_flow.y_ks)
            if active and k < len(node_info.hub_indices)
        }
    else:
        da = {}
        for local_i, d_idx in enumerate(node_info.demand_indices):
            if not open_hub_globals:
                continue
            nearest_h = min(open_hub_globals, key=lambda h: _dist(coords[d_idx], coords[h]))
            mode = solution.A[local_i] if local_i < len(solution.A) else 0
            mode = mode if mode in (0, 1, 2) else 0
            from visualizer.flow_loader import DemandAssignment  # noqa: PLC0415
            da[d_idx] = DemandAssignment(demand_idx=d_idx, hub_idx=nearest_h, mode=mode)
        oa = {}
        active_hubs = open_hub_globals

    # ── Demand filter lookup (for allocation lines only) ──────────────────────
    sc_demand_lookup: Dict[int, float] = {}
    if min_demand_filter > 0:
        _scs = instance_data.get("scenarios", [])
        if scenario_idx < len(_scs):
            sc_demand_lookup = {
                int(k): float(v)
                for k, v in _scs[scenario_idx].get("demand", {}).items()
            }

    # ── Allocation lines ──────────────────────────────────────────────────────
    if show_alloc:
        for d_idx, asgn in da.items():
            if asgn.hub_idx < 0:
                continue
            if min_demand_filter > 0 and sc_demand_lookup.get(d_idx, 0.0) < min_demand_filter:
                continue
            mode       = asgn.mode
            accessible = _is_accessible(mode, d_idx, asgn.hub_idx)
            colour     = _MODE_COLOURS.get(mode, _COL_ALLOC) if accessible else _COL_BLOCKED
            opacity    = 0.7 if accessible else 0.4
            dash       = _MODE_DASHES.get(mode)
            line_kw: dict = dict(color=colour, weight=1.5, opacity=opacity)
            if dash:
                line_kw["dash_array"] = " ".join(map(str, dash))
            folium.PolyLine(
                locations=[coords[d_idx], coords[asgn.hub_idx]],
                tooltip=f"{_MODE_NAMES.get(mode,'?')} {'✓' if accessible else '✗ blocked'}",
                **line_kw,
            ).add_to(fg_alloc)

        for o_idx, asgn in oa.items():
            if asgn.hub_idx < 0:
                continue
            mode = asgn.mode
            folium.PolyLine(
                locations=[coords[o_idx], coords[asgn.hub_idx]],
                color=_MODE_COLOURS.get(mode, _COL_ORIGIN),
                weight=2, opacity=0.6, dash_array="6 3",
                tooltip=f"Supply → Hub  [{_MODE_NAMES.get(mode,'?')}]",
            ).add_to(fg_alloc)

    # ── Transshipment lines ───────────────────────────────────────────────────
    if show_transshipment and scenario_flow:
        max_flow = max((t.flow for t in scenario_flow.transshipment), default=1.0)
        for ts in scenario_flow.transshipment:
            try:
                s_coord = coords[ts.src_hub_idx]
                d_coord = coords[ts.dst_hub_idx]
            except IndexError:
                continue
            weight = 2 + 5 * (ts.flow / max_flow)
            folium.PolyLine(
                locations=[s_coord, d_coord],
                color=_MODE_COLOURS.get(ts.mode, "#9C27B0"),
                weight=weight, opacity=0.8,
                tooltip=f"Transship {ts.flow:,.0f} units [{_MODE_NAMES.get(ts.mode,'?')}]",
            ).add_to(fg_trans)

    # ── Hub markers ───────────────────────────────────────────────────────────
    for k, h_idx in enumerate(node_info.hub_indices):
        lat, lon = coords[h_idx]
        open_    = h_idx in open_hub_globals
        reactive = h_idx in active_hubs if scenario_flow else open_

        hub_state = ("active"   if open_ and reactive else
                     "inactive" if open_ else "closed")
        label = node_info.names[h_idx] if h_idx < len(node_info.names) else f"Hub {k}"

        popup_html = _hub_popup_html(
            k=k, h_idx=h_idx, label=label, open_=open_,
            scenario_idx=scenario_idx, chi=chi,
            solution=solution, instance_data=instance_data,
            scenario_flow=scenario_flow, node_info=node_info,
        )
        folium.Marker(
            location=[lat, lon],
            icon=_hub_icon(hub_state),
            tooltip=f"H{k}: {label}",
            popup=folium.Popup(popup_html, max_width=300),
        ).add_to(fg_hubs)

        if show_labels:
            folium.Marker(
                location=[lat + 0.015, lon],
                icon=folium.DivIcon(
                    html=f'<div style="font-size:9px;color:#444;white-space:nowrap">{label}</div>',
                    icon_size=(120, 14), icon_anchor=(0, 7),
                ),
            ).add_to(fg_hubs)

    # ── Demand node markers ───────────────────────────────────────────────────
    for local_i, d_idx in enumerate(node_info.demand_indices):
        lat, lon = coords[d_idx]
        asgn  = da.get(d_idx)
        mode  = asgn.mode if asgn and asgn.mode in (0, 1, 2) else 0
        colour = _MODE_COLOURS.get(mode, _COL_DEMAND_DEF)
        accessible = _is_accessible(mode, d_idx, asgn.hub_idx) if asgn and asgn.hub_idx >= 0 else True

        name = node_info.names[d_idx] if d_idx < len(node_info.names) else f"Demand {local_i}"
        hub_label = ""
        if asgn and asgn.hub_idx >= 0:
            hub_label = (node_info.names[asgn.hub_idx]
                         if asgn.hub_idx < len(node_info.names) else f"Hub {asgn.hub_idx}")

        popup_d_html = _demand_popup_html(
            d_idx=d_idx, label=name, mode=mode,
            hub_label=hub_label, accessible=accessible,
            instance_data=instance_data, scenario_idx=scenario_idx,
        )
        folium.CircleMarker(
            location=[lat, lon],
            radius=6 if accessible else 4,
            color="white", weight=1,
            fill=True,
            fill_color=colour if accessible else _MODE_COLOURS_FADED.get(mode, _COL_BLOCKED),
            fill_opacity=0.85 if accessible else 0.5,
            tooltip=f"{name} [{_MODE_NAMES.get(mode,'?')}]",
            popup=folium.Popup(popup_d_html, max_width=250),
        ).add_to(fg_demand)

    # ── Origin markers ────────────────────────────────────────────────────────
    for o_idx in node_info.origin_indices:
        lat, lon = coords[o_idx]
        name = node_info.names[o_idx] if o_idx < len(node_info.names) else f"Origin {o_idx}"
        popup_html = _origin_popup_html(o_idx, name, instance_data)
        folium.Marker(
            location=[lat, lon],
            icon=_origin_icon(),
            tooltip=f"Supply depot: {name}",
            popup=folium.Popup(popup_html, max_width=260),
        ).add_to(fg_orig)

    # ── Layer control ─────────────────────────────────────────────────────────
    for fg in (fg_alloc, fg_trans, fg_demand, fg_hubs, fg_orig):
        fg.add_to(m)
    if not compact:
        folium.LayerControl(collapsed=True).add_to(m)

        # ── Legend ────────────────────────────────────────────────────────────
        sc_name = _SC_NAMES[scenario_idx] if scenario_idx < len(_SC_NAMES) else str(scenario_idx)
        legend_html = f"""
        <div style="position:fixed;bottom:20px;left:20px;z-index:1000;
                    background:white;padding:7px 11px;border-radius:7px;
                    border:1px solid #ccc;font-size:11px;box-shadow:2px 2px 5px rgba(0,0,0,.12)">
          <b>Scenario: {sc_name}</b><br>
          <span style="color:{_COL_HUB_OPEN}">&#9670;</span> open+active &nbsp;
          <span style="color:{_COL_HUB_INACTIVE}">&#9670;</span> inactive &nbsp;
          <span style="color:{_COL_HUB_CLOSED}">&#9670;</span> closed<br>
          <span style="color:{_COL_ORIGIN}">&#9650;</span> Supply origin<br>
          <span style="color:{_MODE_COLOURS[0]}">&#9679;</span> Road &nbsp;
          <span style="color:{_MODE_COLOURS[1]}">&#9679;</span> Water &nbsp;
          <span style="color:{_MODE_COLOURS[2]}">&#9679;</span> Air
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

    return m
