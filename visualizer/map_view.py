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
from folium.plugins import MarkerCluster

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "visualizer"))
from solution_loader import NodeInfo, Solution, infer_hub_allocations
from visualizer.flow_loader import ScenarioFlow

# ── colour constants ──────────────────────────────────────────────────────────
_MODE_COLOURS  = {0: "#E53935", 1: "#039BE5", 2: "#7CB342"}  # road/water/air
_MODE_NAMES    = {0: "Road", 1: "Water/Boat", 2: "Air/Helicopter"}
_MODE_DASHES   = {0: None, 1: [8, 4], 2: [2, 4]}              # dash patterns

_COL_HUB_OPEN     = "#FF7043"
_COL_HUB_INACTIVE = "#FFB74D"  # open this scenario, but not reactive/restocked
_COL_HUB_CLOSED   = "#9E9E9E"
_COL_ORIGIN     = "#43A047"
_COL_DEMAND_DEF = "#4C72B0"
_COL_ALLOC      = "#BBBBBB"
_COL_BLOCKED    = "#EF5350"


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _hub_icon(state: str) -> folium.DivIcon:
    """state: 'active' (open + reactive), 'inactive' (open, not reactive
    this scenario), or 'closed'."""
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


def build_map(
    node_info: NodeInfo,
    solution: Solution,
    scenario_flow: Optional[ScenarioFlow],
    instance_data: Dict[str, Any],
    scenario_idx: int = 0,
    show_labels: bool = True,
    show_alloc: bool = True,
    show_transshipment: bool = True,
) -> folium.Map:
    """
    Build and return a Folium map for one solution in one scenario.

    Parameters
    ----------
    node_info      : Parsed node metadata (coords, indices, names).
    solution       : Selected Pareto solution.
    scenario_flow  : Optional pre-computed flow for this scenario.
                     If None, allocation is inferred from X and A vectors.
    instance_data  : Raw loaded instance dict (for scenario accessibility).
    scenario_idx   : Which scenario to render (0=mild, 1=severe, 2=extreme).
    show_labels    : Draw node name labels.
    show_alloc     : Draw demand→hub allocation lines.
    show_transshipment : Draw hub-to-hub flow lines.
    """
    coords = node_info.coords
    hub_set    = set(node_info.hub_indices)
    origin_set = set(node_info.origin_indices)
    demand_set = set(node_info.demand_indices)

    open_hub_globals = {node_info.hub_indices[k] for k in solution.open_hubs}

    # ── Scenario accessibility matrix ─────────────────────────────────────────
    # accessibility[m][u][v] = 1 if route u→v via mode m is usable in scenario s
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

    # ── Map centre & zoom ────────────────────────────────────────────────────
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    centre = (sum(lats) / len(lats), sum(lons) / len(lons))

    m = folium.Map(location=centre, zoom_start=9, tiles="OpenStreetMap",
                   control_scale=True)

    # ── Feature groups (for layer control) ───────────────────────────────────
    fg_hubs   = folium.FeatureGroup(name="Hubs", show=True)
    fg_demand = folium.FeatureGroup(name="Demand nodes", show=True)
    fg_orig   = folium.FeatureGroup(name="Supply origins", show=True)
    fg_alloc  = folium.FeatureGroup(name="Allocation routes", show=show_alloc)
    fg_trans  = folium.FeatureGroup(name="Transshipment flows", show=show_transshipment)

    # ── Determine demand→hub assignments ─────────────────────────────────────
    if scenario_flow is not None:
        da = {a.demand_idx: a for a in scenario_flow.demand_assignments}
        oa = {a.origin_idx: a for a in scenario_flow.origin_assignments}
        active_hubs = {
            node_info.hub_indices[k]
            for k, active in enumerate(scenario_flow.y_ks)
            if active and k < len(node_info.hub_indices)
        }
    else:
        # Fallback: nearest open hub, use A vector for mode
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

    # ── Draw allocation lines ─────────────────────────────────────────────────
    if show_alloc:
        for d_idx, asgn in da.items():
            if asgn.hub_idx < 0:
                continue
            d_coord = coords[d_idx]
            h_coord = coords[asgn.hub_idx]
            mode    = asgn.mode
            accessible = _is_accessible(mode, d_idx, asgn.hub_idx)
            colour = _MODE_COLOURS.get(mode, _COL_ALLOC) if accessible else _COL_BLOCKED
            opacity = 0.7 if accessible else 0.4
            dash = _MODE_DASHES.get(mode)
            line_kw: dict = dict(color=colour, weight=1.5, opacity=opacity)
            if dash:
                line_kw["dash_array"] = " ".join(map(str, dash))
            folium.PolyLine(
                locations=[d_coord, h_coord],
                tooltip=f"{_MODE_NAMES.get(mode,'?')} {'✓' if accessible else '✗ blocked'}",
                **line_kw,
            ).add_to(fg_alloc)

        # Origin → hub lines
        for o_idx, asgn in oa.items():
            if asgn.hub_idx < 0:
                continue
            o_coord = coords[o_idx]
            h_coord = coords[asgn.hub_idx]
            mode    = asgn.mode
            folium.PolyLine(
                locations=[o_coord, h_coord],
                color=_MODE_COLOURS.get(mode, _COL_ORIGIN),
                weight=2, opacity=0.6,
                dash_array="6 3",
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

    # ── Hub markers ──────────────────────────────────────────────────────────
    for k, h_idx in enumerate(node_info.hub_indices):
        lat, lon = coords[h_idx]
        open_ = h_idx in open_hub_globals
        reactive = h_idx in active_hubs if scenario_flow else open_

        inv_info = ""
        if scenario_flow and k < len(scenario_flow.inventory_held):
            inv_info = f"<br>Inventory held: {scenario_flow.inventory_held[k]:,.0f}"

        label = node_info.names[h_idx] if h_idx < len(node_info.names) else f"Hub {k}"
        hub_state = ("active" if open_ and reactive
                      else "inactive" if open_
                      else "closed")
        status = {"active": "Open + Active",
                  "inactive": "Open (inactive this scenario)",
                  "closed": "Closed"}[hub_state]
        popup_html = (
            f"<b>{label}</b><br>"
            f"Hub #{k} (global {h_idx})<br>"
            f"Status: {status}{inv_info}"
        )
        folium.Marker(
            location=[lat, lon],
            icon=_hub_icon(hub_state),
            tooltip=f"Hub {k}: {label}",
            popup=folium.Popup(popup_html, max_width=250),
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
        asgn = da.get(d_idx)
        mode = asgn.mode if asgn and asgn.mode in (0, 1, 2) else 0
        colour = _MODE_COLOURS.get(mode, _COL_DEMAND_DEF)
        accessible = _is_accessible(mode, d_idx, asgn.hub_idx) if asgn and asgn.hub_idx >= 0 else True

        name = node_info.names[d_idx] if d_idx < len(node_info.names) else f"Demand {local_i}"
        hub_name = ""
        if asgn and asgn.hub_idx >= 0:
            hn = node_info.names[asgn.hub_idx] if asgn.hub_idx < len(node_info.names) else str(asgn.hub_idx)
            hub_name = f"<br>→ Hub: {hn}"
        acc_str = "" if accessible else "<br><span style='color:red'>Route blocked in this scenario</span>"

        folium.CircleMarker(
            location=[lat, lon],
            radius=6 if accessible else 4,
            color="white",
            weight=1,
            fill=True,
            fill_color=colour if accessible else _COL_BLOCKED,
            fill_opacity=0.85 if accessible else 0.5,
            tooltip=f"{name} [{_MODE_NAMES.get(mode,'?')}]",
            popup=folium.Popup(
                f"<b>{name}</b><br>Mode: {_MODE_NAMES.get(mode,'?')}{hub_name}{acc_str}",
                max_width=220,
            ),
        ).add_to(fg_demand)

    # ── Origin markers ────────────────────────────────────────────────────────
    for o_idx in node_info.origin_indices:
        lat, lon = coords[o_idx]
        name = node_info.names[o_idx] if o_idx < len(node_info.names) else f"Origin {o_idx}"
        folium.Marker(
            location=[lat, lon],
            icon=_origin_icon(),
            tooltip=f"Supply: {name}",
            popup=folium.Popup(f"<b>{name}</b><br>Supply origin", max_width=180),
        ).add_to(fg_orig)

    # ── Add all groups + layer control ───────────────────────────────────────
    for fg in (fg_alloc, fg_trans, fg_demand, fg_hubs, fg_orig):
        fg.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    # ── Legend ────────────────────────────────────────────────────────────────
    scenario_names = ["Mild", "Severe", "Extreme"]
    sc_name = scenario_names[scenario_idx] if scenario_idx < len(scenario_names) else str(scenario_idx)
    legend_html = f"""
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:10px 14px;border-radius:8px;
                border:1px solid #ccc;font-size:12px;box-shadow:2px 2px 6px rgba(0,0,0,.15)">
      <b>Scenario: {sc_name}</b><br>
      <span style="color:{_COL_HUB_OPEN}">&#9670;</span> Hub (open+active)&nbsp;
      <span style="color:{_COL_HUB_INACTIVE}">&#9670;</span> Hub (open, inactive)&nbsp;
      <span style="color:{_COL_HUB_CLOSED}">&#9670;</span> Hub (closed)<br>
      <span style="color:{_COL_ORIGIN}">&#9650;</span> Supply origin<br>
      <span style="color:{_MODE_COLOURS[0]}">&#9679;</span> Demand — Road&nbsp;
      <span style="color:{_MODE_COLOURS[1]}">&#9679;</span> Water&nbsp;
      <span style="color:{_MODE_COLOURS[2]}">&#9679;</span> Air
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    return m
