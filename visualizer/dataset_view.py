"""
dataset_view.py — Input Dataset Explorer map for the Streamlit visualiser.

build_dataset_map(...) → folium.Map
Six toggleable layers (all always rendered; Folium LayerControl controls visibility):
  1. Risk choropleth      — nodes coloured green→yellow→red by scenario risk score
  2. Demand heatmap       — demand nodes sized by relief demand volume
  3. Flood epicentres     — location markers + influence circle per scenario
  4. Accessibility        — Delaunay planar graph edges coloured by road/water/air access
  5. Population circles   — demand nodes sized by base_population (static, scenario-independent)
  6. Intrinsic risk layer — demand nodes coloured by aux_risk (static, scenario-independent)

Mutual exclusivity: "Risk index" and "Intrinsic risk (static)" layers are enforced
exclusive via injected JavaScript — only one risk overlay can be active at a time.
"""
from __future__ import annotations

import colorsys
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import folium
import numpy as np
from scipy.spatial import Delaunay


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p)
         * math.sin((lon2 - lon1) * p / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src" / "visualizer"))
from solution_loader import NodeInfo

# ── colour helpers ────────────────────────────────────────────────────────────

def _risk_color(v: float) -> str:
    """Map risk 0→1 to green→yellow→red as a hex colour."""
    v = max(0.0, min(1.0, v))
    hue = (1.0 - v) * 0.333
    r, g, b = colorsys.hls_to_rgb(hue, 0.42, 0.88)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def _demand_color(norm: float) -> str:
    """Map normalised demand 0→1 to white→orange→dark-red."""
    norm = max(0.0, min(1.0, norm))
    if norm < 0.5:
        t = norm * 2
        r, g, b = 255, int(255 - 119 * t), int(255 * (1 - t))
    else:
        t = (norm - 0.5) * 2
        r, g, b = int(255 - 116 * t), int(136 * (1 - t)), 0
    return f"#{r:02x}{g:02x}{b:02x}"


def _pop_color(norm: float) -> str:
    """Map normalised population 0→1 to light-blue→deep-blue."""
    norm = max(0.0, min(1.0, norm))
    r = int(173 * (1 - norm))
    g = int(216 * (1 - norm * 0.5))
    b = 230
    return f"#{r:02x}{g:02x}{b:02x}"


# ── planar graph construction ─────────────────────────────────────────────────

def _delaunay_edges(coords: List[Tuple[float, float]]) -> Set[Tuple[int, int]]:
    pts = np.array([[c[0], c[1]] for c in coords])
    tri = Delaunay(pts)
    edges: Set[Tuple[int, int]] = set()
    for simplex in tri.simplices:
        for i in range(3):
            for j in range(i + 1, 3):
                u, v = int(simplex[i]), int(simplex[j])
                edges.add((min(u, v), max(u, v)))
    return edges


# ── popup builder ─────────────────────────────────────────────────────────────

_POPUP_STYLE = "font-size:11px;line-height:1.5;max-width:220px"

def _demand_node_popup(
    name: str,
    header: str,
    demand: float,
    population: Any,
    sc_risk: float,
    ir_val: float,
) -> str:
    return (
        f'<div style="{_POPUP_STYLE}">'
        f'<b>{name}</b><br>'
        f'<span style="color:#888">{header}</span><br><br>'
        f'Demand: <b>{demand:,.0f}</b> persons<br>'
        f'Population: <b>{population}</b><br>'
        f'Scenario risk: <b>{sc_risk:.3f}</b><br>'
        f'Intrinsic risk: <b>{ir_val:.3f}</b>'
        f'</div>'
    )


# ── origin icon ───────────────────────────────────────────────────────────────

def _origin_icon() -> folium.DivIcon:
    return folium.DivIcon(
        html=(
            '<div style="width:0;height:0;'
            "border-left:8px solid transparent;"
            "border-right:8px solid transparent;"
            'border-bottom:14px solid #43A047;margin-top:3px"></div>'
        ),
        icon_size=(16, 16),
        icon_anchor=(8, 14),
    )


# ── main API ──────────────────────────────────────────────────────────────────

def build_dataset_map(
    node_info: NodeInfo,
    instance_data: Dict[str, Any],
    scenario_idx: int = 0,
    show_risk: bool = True,
    show_demand: bool = True,
    show_epicenters: bool = True,
    show_road: bool = True,
    show_water: bool = True,
    show_air: bool = False,
    show_population: bool = False,
    show_intrinsic_risk: bool = False,
    min_pop_threshold: int = 0,
) -> folium.Map:
    """
    Build a Folium map visualising the raw input dataset for one scenario.

    All six layers are always fully rendered into their FeatureGroups; the
    show_* flags only control *initial* visibility in the Folium LayerControl.
    JavaScript mutual exclusivity ensures only one of Risk index / Intrinsic
    risk (static) is active at a time.
    """
    coords    = node_info.coords
    names     = node_info.names
    scenarios = instance_data.get("scenarios", [])
    sc        = scenarios[scenario_idx] if scenario_idx < len(scenarios) else {}

    risk_vals    = sc.get("risk", [])
    demand_raw   = sc.get("demand", {})
    supply_raw   = sc.get("supply", {})
    accessibility = sc.get("accessibility", [])
    epicenters   = sc.get("epicenters", [])
    base_pop     = instance_data.get("base_population", {})
    aux_risk     = instance_data.get("nodes", {}).get("aux_risk", [])

    demand_vals = {int(k): float(v) for k, v in demand_raw.items()}
    max_demand  = max(demand_vals.values(), default=1.0)

    pop_vals    = {int(k): int(v) for k, v in base_pop.items()}
    max_pop     = max(pop_vals.values(), default=1)

    # ── map centre ────────────────────────────────────────────────────────────
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    centre = (sum(lats) / len(lats), sum(lons) / len(lons))
    m = folium.Map(location=centre, zoom_start=9, tiles="OpenStreetMap", control_scale=True)

    # ── Edge sets per mode ────────────────────────────────────────────────────
    _geom_edges = _delaunay_edges(coords)
    _graph = instance_data.get("graph", {})
    if _graph.get("road_edges"):
        road_edge_set = {(int(e[0]), int(e[1])) for e in _graph["road_edges"]}
    else:
        road_edge_set = _geom_edges

    # ── Feature groups ────────────────────────────────────────────────────────
    # Risk layers grouped together; accessibility at the bottom.
    fg_dem    = folium.FeatureGroup(name="Demand volume",           show=show_demand)
    fg_epi    = folium.FeatureGroup(name="Flood epicentres",        show=show_epicenters)
    fg_risk   = folium.FeatureGroup(name="Risk index",              show=show_risk)
    fg_irisks = folium.FeatureGroup(name="Intrinsic risk (static)", show=show_intrinsic_risk)
    fg_road   = folium.FeatureGroup(name="Road accessibility",      show=show_road)
    fg_water  = folium.FeatureGroup(name="Water accessibility",     show=show_water)
    fg_air    = folium.FeatureGroup(name="Air accessibility",       show=show_air)
    fg_pop    = folium.FeatureGroup(name="Population (static)",     show=show_population)

    hub_set    = set(node_info.hub_indices)
    origin_set = set(node_info.origin_indices)

    # ─────────────────────────────────────────────────────────────────────────
    # All layers are ALWAYS rendered into their FeatureGroups so the Folium
    # LayerControl toggle has real content to show/hide. show=<flag> on each
    # FeatureGroup controls only the initial visibility.
    # ─────────────────────────────────────────────────────────────────────────

    # Layer 1: Scenario risk choropleth
    for idx, (lat, lon) in enumerate(coords):
        risk      = float(risk_vals[idx]) if idx < len(risk_vals) else 0.0
        colour    = _risk_color(risk)
        is_hub    = idx in hub_set
        is_origin = idx in origin_set
        name      = names[idx] if idx < len(names) else f"Node {idx}"

        if is_hub:
            popup_html = (
                f'<div style="{_POPUP_STYLE}">'
                f'<b>{name}</b><br>'
                f'<span style="color:#888">Hub candidate</span><br><br>'
                f'Scenario risk: <b>{risk:.3f}</b>'
                f'</div>'
            )
        elif is_origin:
            popup_html = (
                f'<div style="{_POPUP_STYLE}">'
                f'<b>{name}</b><br>'
                f'<span style="color:#888">Supply origin</span><br><br>'
                f'Scenario risk: <b>{risk:.3f}</b>'
                f'</div>'
            )
        else:
            d_val  = demand_vals.get(idx, 0.0)
            pop_v  = base_pop.get(str(idx), "—")
            ir_v   = float(aux_risk[idx]) if aux_risk and idx < len(aux_risk) else 0.0
            popup_html = _demand_node_popup(name, "Demand node", d_val, pop_v, risk, ir_v)

        folium.CircleMarker(
            location=[lat, lon],
            radius=10 if is_hub else 7,
            color="#555" if is_hub else "white",
            weight=1.5 if is_hub else 0.8,
            fill=True, fill_color=colour, fill_opacity=0.85,
            tooltip=f"{name} | risk={risk:.3f}",
            popup=folium.Popup(popup_html, max_width=230),
        ).add_to(fg_risk)

    # Layer 2: Demand volume heatmap + supply origins
    for local_i, d_idx in enumerate(node_info.demand_indices):
        pop_val   = pop_vals.get(d_idx, 0)
        if pop_val < min_pop_threshold:
            continue
        lat, lon  = coords[d_idx]
        demand    = demand_vals.get(d_idx, 0.0)
        norm      = demand / max_demand
        colour    = _demand_color(norm)
        radius    = 5 + 15 * norm
        name      = names[d_idx] if d_idx < len(names) else f"Demand {local_i}"
        pop       = base_pop.get(str(d_idx), "—")
        ir_val    = float(aux_risk[d_idx]) if aux_risk and d_idx < len(aux_risk) else 0.0
        sc_risk_v = float(risk_vals[d_idx]) if d_idx < len(risk_vals) else 0.0

        folium.CircleMarker(
            location=[lat, lon],
            radius=radius,
            color="white", weight=0.8,
            fill=True, fill_color=colour, fill_opacity=0.80,
            tooltip=f"{name} | demand={demand:,.0f}",
            popup=folium.Popup(
                _demand_node_popup(name, "Demand node", demand, pop, sc_risk_v, ir_val),
                max_width=230,
            ),
        ).add_to(fg_dem)

    for o_idx in node_info.origin_indices:
        lat, lon = coords[o_idx]
        name     = names[o_idx] if o_idx < len(names) else f"Origin {o_idx}"
        supply   = float(supply_raw.get(str(o_idx), 0.0))
        folium.Marker(
            location=[lat, lon],
            icon=_origin_icon(),
            tooltip=f"Supply: {name} | supply={supply:,.0f}",
            popup=folium.Popup(
                f'<div style="{_POPUP_STYLE}">'
                f'<b>{name}</b><br>'
                f'<span style="color:#888">Supply depot · Origin node</span><br><br>'
                f'Supply: <b>{supply:,.0f}</b> units'
                f'</div>',
                max_width=210,
            ),
        ).add_to(fg_dem)

    # Layer 3: Flood epicentres
    for i, epi in enumerate(epicenters):
        elat      = float(epi["lat"])
        elon      = float(epi["lon"])
        intensity = float(epi.get("intensity", 0.5))
        radius_m  = int(intensity * 35_000)
        folium.Circle(
            location=[elat, elon], radius=radius_m,
            color="#C62828", weight=2, dash_array="8 4",
            fill=True, fill_color="#EF5350", fill_opacity=0.08,
            tooltip=f"Epicentre {i+1} | intensity={intensity:.3f}",
        ).add_to(fg_epi)
        folium.Marker(
            location=[elat, elon],
            icon=folium.DivIcon(
                html='<div style="font-size:20px;color:#B71C1C;text-shadow:0 0 4px white;line-height:1">⚡</div>',
                icon_size=(24, 24), icon_anchor=(12, 12),
            ),
            tooltip=f"Epicentre {i+1}: intensity={intensity:.3f}, r={radius_m/1000:.0f} km",
            popup=folium.Popup(
                f'<div style="{_POPUP_STYLE}">'
                f'<b>Flood epicentre {i+1}</b><br><br>'
                f'Intensity: <b>{intensity:.3f}</b><br>'
                f'Influence radius: <b>{radius_m/1000:.0f} km</b>'
                f'</div>',
                max_width=210,
            ),
        ).add_to(fg_epi)

    # Layer 4: Accessibility planar graph (all modes always rendered)
    _MODE_META = [
        (0, "Road",  "#2E7D32", fg_road,  road_edge_set),
        (1, "Water", "#0277BD", fg_water, _geom_edges),
        (2, "Air",   "#6A1B9A", fg_air,   _geom_edges),
    ]
    for mode_idx, mode_name, mode_colour, fg, mode_edges in _MODE_META:
        if not accessibility or mode_idx >= len(accessibility):
            continue
        ac_matrix = accessibility[mode_idx]
        n = len(coords)
        for (u, v) in mode_edges:
            if u >= n or v >= n:
                continue
            try:
                accessible = bool(ac_matrix[u][v])
            except (IndexError, TypeError):
                accessible = True
            if accessible:
                folium.PolyLine(
                    locations=[coords[u], coords[v]],
                    color=mode_colour, weight=2, opacity=0.6,
                    tooltip=f"{names[u] if u<len(names) else u} ↔ "
                            f"{names[v] if v<len(names) else v} [{mode_name}]",
                ).add_to(fg)

    # Layer 5: Population circles (static, scenario-independent)
    for local_i, d_idx in enumerate(node_info.demand_indices):
        pop_val = pop_vals.get(d_idx, 0)
        if pop_val < min_pop_threshold:
            continue
        lat, lon  = coords[d_idx]
        norm      = pop_val / max_pop
        radius    = 5 + 20 * norm
        name      = names[d_idx] if d_idx < len(names) else f"Demand {local_i}"
        colour    = _pop_color(norm)
        sc_risk_v = float(risk_vals[d_idx]) if d_idx < len(risk_vals) else 0.0
        ir_val    = float(aux_risk[d_idx]) if aux_risk and d_idx < len(aux_risk) else 0.0
        demand    = demand_vals.get(d_idx, 0.0)

        folium.CircleMarker(
            location=[lat, lon],
            radius=radius,
            color="white", weight=0.8,
            fill=True, fill_color=colour, fill_opacity=0.75,
            tooltip=f"{name} | pop={pop_val:,}",
            popup=folium.Popup(
                _demand_node_popup(name, f"Static population · {pop_val:,}", demand, pop_val, sc_risk_v, ir_val),
                max_width=230,
            ),
        ).add_to(fg_pop)

    # Layer 6: Intrinsic (aux) risk — static, scenario-independent
    if aux_risk:
        demand_aux = [float(aux_risk[d_idx]) if d_idx < len(aux_risk) else 0.0
                      for d_idx in node_info.demand_indices]
        for local_i, d_idx in enumerate(node_info.demand_indices):
            pop_val = pop_vals.get(d_idx, 0)
            if pop_val < min_pop_threshold:
                continue
            lat, lon  = coords[d_idx]
            ir_val    = demand_aux[local_i]
            colour    = _risk_color(ir_val)
            name      = names[d_idx] if d_idx < len(names) else f"Demand {local_i}"
            sc_risk_v = float(risk_vals[d_idx]) if d_idx < len(risk_vals) else 0.0
            demand    = demand_vals.get(d_idx, 0.0)
            pop_v     = base_pop.get(str(d_idx), "—")

            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color="white", weight=0.8,
                fill=True, fill_color=colour, fill_opacity=0.80,
                tooltip=f"{name} | intrinsic risk={ir_val:.3f}",
                popup=folium.Popup(
                    _demand_node_popup(name, "Intrinsic flood susceptibility", demand, pop_v, sc_risk_v, ir_val),
                    max_width=230,
                ),
            ).add_to(fg_irisks)

    # ── Add all groups ────────────────────────────────────────────────────────
    # Order: most-used layers first (top of LayerControl), accessibility last.
    for fg in (fg_dem, fg_epi, fg_risk, fg_irisks, fg_road, fg_water, fg_air, fg_pop):
        fg.add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)

    # ── Mutual exclusivity: Risk index ↔ Intrinsic risk (static) ─────────────
    # Only one risk overlay should be active at a time. We inject JS that
    # listens for Leaflet's 'overlayadd' event and removes the other risk
    # layer + unchecks its LayerControl checkbox when one is activated.
    map_var   = m.get_name()
    risk_var  = fg_risk.get_name()
    irisk_var = fg_irisks.get_name()
    excl_js = f"""
<script>
(function() {{
    function init() {{
        var map = window['{map_var}'];
        if (!map) {{ setTimeout(init, 50); return; }}
        var rL  = window['{risk_var}'];
        var iL  = window['{irisk_var}'];
        map.on('overlayadd', function(e) {{
            var other = null, otherToken = null;
            if (e.layer === rL)  {{ other = iL;  otherToken = 'Intrinsic'; }}
            if (e.layer === iL)  {{ other = rL;  otherToken = 'Risk index'; }}
            if (!other) return;
            if (map.hasLayer(other)) map.removeLayer(other);
            document.querySelectorAll(
                '.leaflet-control-layers-overlays label'
            ).forEach(function(lbl) {{
                var sp = lbl.querySelector('span');
                if (sp && sp.textContent.indexOf(otherToken) !== -1) {{
                    var cb = lbl.querySelector('input');
                    if (cb && cb.checked) cb.checked = false;
                }}
            }});
        }});
    }}
    init();
}})();
</script>"""
    m.get_root().html.add_child(folium.Element(excl_js))

    # ── Legend ────────────────────────────────────────────────────────────────
    sc_names = ["Mild", "Severe", "Extreme"]
    sc_label = sc_names[scenario_idx] if scenario_idx < len(sc_names) else str(scenario_idx)
    legend_html = f"""
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:10px 14px;border-radius:8px;
                border:1px solid #ccc;font-size:12px;box-shadow:2px 2px 6px rgba(0,0,0,.15)">
      <b>Scenario: {sc_label}</b><br>
      <span style="color:#2E7D32">─</span> Road &nbsp;
      <span style="color:#0277BD">─</span> Water &nbsp;
      <span style="color:#6A1B9A">─</span> Air<br>
      <span style="color:#C62828">⚡</span> Flood epicentre<br>
      <span style="background:linear-gradient(to right,#2e7d32,#f9a825,#c62828);
                   display:inline-block;width:80px;height:10px;vertical-align:middle"></span>
      Risk (low→high)
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    return m
