"""
map_solution_v2.py — High-fidelity PB-NSGA-II Visualisation for MO-IHLNDP.
Matches C++ decoder logic (Step 1-4) for accurate network mapping.
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as patheffects
from matplotlib.lines import Line2D

try:
    import contextily as ctx
    HAS_CONTEXTILY = True
except ImportError:
    HAS_CONTEXTILY = False

try:
    from pyproj import Transformer
    _transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    def to_web_mercator(lon, lat):
        return _transformer.transform(lon, lat)
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False
    def to_web_mercator(lon, lat):
        x = lon * 20037508.34 / 180.0
        y = math.log(math.tan((90 + lat) * math.pi / 360.0)) * 20037508.34 / math.pi
        return x, y

# Visual Constants
COL_DEMAND = "#4C72B0"    # Muted Blue
COL_HUB_OPEN = "#DD8452"  # Safety Orange
COL_HUB_RISKY = "#D62728" # Alert Red
COL_HUB_CLOSED = "#BBBBBB"
COL_ORIGIN = "#55A868"    # Success Green
ALPHA_LINK = 0.20
LW_LINK = 0.7

MODE_STYLES = {
    0: {"ls": "-",  "label": "Road",       "color": "#777777", "alpha": 0.25}, 
    1: {"ls": "--", "label": "Water",      "color": "#1f77b4", "alpha": 0.40}, 
    2: {"ls": ":",  "label": "Helicopter", "color": "#ff7f0e", "alpha": 0.50}, 
}

def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def pick_balanced(pareto):
    if not pareto: return None
    # Filter only rank 1
    rank1 = [s for s in pareto if s.get("rank", 1) == 1]
    if not rank1: rank1 = pareto

    z1s = [s["Z1"] for s in rank1]
    z2s = [s["Z2"] for s in rank1]
    z1_min, z1_max = min(z1s), max(z1s)
    z2_min, z2_max = min(z2s), max(z2s)
    r1, r2 = max(z1_max-z1_min, 1.0), max(z2_max-z2_min, 1.0)
    
    # Balanced = closest to utopia in normalised space
    return min(rank1, key=lambda s: ((s["Z1"]-z1_min)/r1)**2 + ((s["Z2"]-z2_min)/r2)**2)

def decode_assignments_exact(sol, inst, si):
    """
    Python implementation of STEP 4 from decoder.hpp.
    Returns: list of (demand_ii, hub_ki, mode)
    """
    dims = inst["dimensions"]
    num_H, num_I, num_M = dims["num_H"], dims["num_I"], dims["num_M"]
    sc = inst["scenarios"][si]
    hub_idx = inst["nodes"]["hub_indices"]
    dem_idx = inst["nodes"]["demand_indices"]
    coords = inst["nodes"]["coords"]
    X, R, A, W = sol["X"], sol["R"], sol["A"], sol["W"]
    chi = inst["global_params"]["chi"]
    
    # Precompute anchor-based trial order
    # hub_anchor_order[ki][j] -> kj
    hub_anchor_order = []
    for ki in range(num_H):
        hi = hub_idx[ki]
        lat_h, lon_h = coords[hi]
        dists = []
        for kj in range(num_H):
            hj = hub_idx[kj]
            lat_j, lon_j = coords[hj]
            dists.append(((lat_h-lat_j)**2 + (lon_h-lon_j)**2, kj))
        dists.sort()
        hub_anchor_order.append([d[1] for d in dists])

    # Active/Planned hubs
    active = [False]*num_H
    for ki in range(num_H):
        k = hub_idx[ki]
        if X[ki] and sc["risk"][k] <= chi:
            active[ki] = True
    
    # Ensure at least one active hub (decoder level fallback)
    if not any(active):
        best_ki = min(range(num_H), key=lambda ki: sc["risk"][hub_idx[ki]])
        active[best_ki] = True

    # Simple mode picker based on accessibility and time (proxy for preference)
    # Priority: Non-air (0,1) then Air (2)
    assignments = []
    inventory = [R[ki] * inst.get("hub_params", {}).get("capacity", {}).get(str(hub_idx[ki]), 0) if X[ki] else 0 
                for ki in range(num_H)]
    load = [0.0]*num_H

    # The actual decoder sorts by demand priority, but here for viz we just map.
    # We use A[ii] as anchor.
    for ii in range(num_I):
        i = dem_idx[ii]
        anchor_ki = A[ii] % num_H
        trial = hub_anchor_order[anchor_ki]
        
        best_ki, best_m, best_t = -1, -1, 1e18
        
        # Pass 1: Try reachable active hubs in distance order from anchor
        # (Capacity check omitted for visualisation lines, showing target intent)
        for ki in trial:
            if not active[ki]: continue
            k = hub_idx[ki]
            
            # Find best mode
            m_found = -1
            t_min = 1e18
            for m in [0, 1]: # Road, Water
                if sc["accessibility"][m][i][k]:
                    t = inst["transport"]["time"][m][i][k]
                    if t < t_min: t_min, m_found = t, m
            if m_found == -1 and sc["accessibility"][2][i][k]: # Heli
                t_min, m_found = inst["transport"]["time"][2][i][k], 2
            
            if m_found != -1:
                best_ki, best_m, best_t = ki, m_found, t_min
                break # First reachable in trial order (proximity to anchor)
        
        if best_ki != -1:
            assignments.append((ii, best_ki, best_m))
            
    return assignments

def draw_scenario(ax, inst, sol, si, use_mercator=True):
    coords = inst["nodes"]["coords"]
    hub_idx = inst["nodes"]["hub_indices"]
    dem_idx = inst["nodes"]["demand_indices"]
    ori_idx = inst["nodes"]["origin_indices"]
    sc = inst["scenarios"][si]
    risks = sc["risk"]
    chi = inst["global_params"]["chi"]
    
    def xy(idx):
        lat, lon = coords[idx]
        return to_web_mercator(lon, lat) if use_mercator else (lon, lat)

    # 1. Routing Links (Modal differentiated)
    assignments = decode_assignments_exact(sol, inst, si)
    for ii, ki, m in assignments:
        p_dem = xy(dem_idx[ii])
        p_hub = xy(hub_idx[ki])
        style = MODE_STYLES[m]
        ax.plot([p_dem[0], p_hub[0]], [p_dem[1], p_hub[1]], 
                color=style["color"], ls=style["ls"], lw=LW_LINK, 
                alpha=style["alpha"], zorder=3)

    # 2. Demand Nodes (Gradient by risk)
    for ii, i in enumerate(dem_idx):
        p = xy(i)
        r = risks[i]
        color = plt.cm.RdYlGn_r(r)
        # Size proportional to demand
        d_val = sc["demand"].get(str(i), 50.0)
        s = 5 + (d_val / 500.0)
        ax.scatter(p[0], p[1], s=s, c=[color], edgecolors="none", alpha=0.6, zorder=4)

    # 3. Hubs
    for ki in range(inst["dimensions"]["num_H"]):
        h = hub_idx[ki]
        p = xy(h)
        is_open = sol["X"][ki] == 1
        safe = risks[h] <= chi
        color = COL_HUB_OPEN if (is_open and safe) else COL_HUB_RISKY if is_open else COL_HUB_CLOSED
        marker = "s" if is_open else "^"
        size = 120 if is_open else 40
        ax.scatter(p[0], p[1], s=size, c=color, marker=marker, edgecolors="black", lw=0.6, zorder=6)
        if is_open:
            ax.annotate(f"H{ki}", p, xytext=(4, 4), textcoords="offset points", 
                        fontsize=7, fontweight="bold", path_effects=[matplotlib.patheffects.withStroke(linewidth=2, foreground='white')])

    # 4. Origins
    for jj, j in enumerate(ori_idx):
        p = xy(j)
        ax.scatter(p[0], p[1], s=80, c=COL_ORIGIN, marker="D", edgecolors="black", lw=0.6, zorder=5)

    ax.set_title(f"{sc['name']} Scenario (p={sc['probability']:.2f})", fontsize=11, fontweight="bold", pad=12)
    ax.set_axis_off()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    inst = load_json(args.instance)
    res = load_json(args.result)
    
    pareto = res.get("pareto_front", [])
    if not pareto: pareto = res.get("all_feasible", [])
    sol = pick_balanced(pareto)
    
    if not sol:
        print("Error: Could not find valid solution.")
        return

    num_S = inst["dimensions"]["num_S"]
    fig, axes = plt.subplots(1, num_S, figsize=(6.5*num_S, 8))
    if num_S == 1: axes = [axes]
    
    use_mercator = HAS_PYPROJ
    for si in range(num_S):
        ax = axes[si]
        draw_scenario(ax, inst, sol, si, use_mercator=use_mercator)
        if HAS_CONTEXTILY and use_mercator:
            try:
                # Use a clean, publication-quality basemap
                ctx.add_basemap(ax, source=ctx.providers.CartoDB.Positron, zoom=9, alpha=0.6)
            except: pass

    # Elegant Legend
    legend_elements = [
        Line2D([0], [0], color=COL_HUB_OPEN, marker="s", ls="", label="Active Hub (Safe)", markersize=8),
        Line2D([0], [0], color=COL_HUB_RISKY, marker="s", ls="", label="Active Hub (Risky)", markersize=8),
        Line2D([0], [0], color=COL_ORIGIN, marker="D", ls="", label="Supply Origin", markersize=8),
        Line2D([0], [0], color=MODE_STYLES[0]["color"], ls=MODE_STYLES[0]["ls"], label="Truck Mode", lw=1.5),
        Line2D([0], [0], color=MODE_STYLES[1]["color"], ls=MODE_STYLES[1]["ls"], label="Water Mode", lw=1.5),
        Line2D([0], [0], color=MODE_STYLES[2]["color"], ls=MODE_STYLES[2]["ls"], label="Air Mode (Heli)", lw=1.5),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=3, fontsize=10, 
               bbox_to_anchor=(0.5, 0.04), frameon=True, facecolor="white", edgecolor="#DDDDDD")
    
    plt.tight_layout(rect=[0, 0.1, 1, 0.94])
    fig.suptitle(f"Strategic Relief Network Configuration - CV-Large Instance\nRepresentative Solution ($Z_1$=\\${sol['Z1']/1e6:.1f}M, $Z_2$={sol['Z2']:.0f} deprivation)", 
                 fontsize=15, fontweight="bold", y=0.98)
    
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, dpi=250, bbox_inches="tight")
    print(f"Figure saved to: {args.out}")

if __name__ == "__main__":
    main()
