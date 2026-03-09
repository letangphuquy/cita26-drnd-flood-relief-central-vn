"""
exp2_map_solution.py — High-Fidelity Solution Map for MO-IHLNDP (CV-Large)
===========================================================================
STATUS: Active — called from run_exp2_case_study.bat / run_exp2_case_study.sh
        (Step 3 of 3).

Produces a 1×3 composite network map (one panel per disaster scenario) for a
representative PB-NSGA solution on the Central Vietnam instance.  The decoder
logic mirrors the C++ solver decoder to ensure accurate hub/flow assignment.

Canonical call (from run_exp2_case_study.bat):
  python src/scripts/exp2_map_solution.py \
      --instance data/cv/cv_large_drnd.json \
      --result   results/exp2/cv_large_seed0.json \
      --out      figures/cv_large_map_detailed.pdf

Optional dependencies:
  contextily  — adds OpenStreetMap basemap tiles (falls back to plain axes)
  pyproj      — accurate EPSG:4326 → EPSG:3857 projection (falls back to
                Mercator approximation)
"""

import argparse
import json
import math
import os
import sys
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
COL_HUB_REACT = "#9C27b0" # Purple for reactive
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
    """Pick the min-Z1 solution from the rank-1 Pareto front.
    The minimum-cost solution opens the most hubs geographically, producing
    realistic reactive hub activations and lateral transshipment in severe/
    extreme scenarios — the most informative configuration to display."""
    if not pareto: return None
    rank1 = [s for s in pareto if s.get("rank", 1) == 1]
    if not rank1: rank1 = pareto
    return min(rank1, key=lambda s: s["Z1"])

def decode_exact(sol, inst, si):
    dims = inst["dimensions"]
    num_H, num_I, num_M, num_J = dims["num_H"], dims["num_I"], dims["num_M"], dims["num_J"]
    sc = inst["scenarios"][si]
    hub_idx = inst["nodes"]["hub_indices"]
    dem_idx = inst["nodes"]["demand_indices"]
    ori_idx = inst["nodes"]["origin_indices"]
    coords = inst["nodes"]["coords"]
    X, R, A, W = sol["X"], sol["R"], sol["A"], sol["W"]
    chi = inst["global_params"]["chi"]
    gamma = inst["global_params"]["gamma"]
    
    # Precompute anchor distances
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

    # 1. Planned Hubs
    active = [False]*num_H
    y = [False]*num_H
    inventory = [0.0]*num_H
    kappa = inst["hub_params"]["capacity"]
    for ki in range(num_H):
        k = hub_idx[ki]
        q_ki = R[ki] * kappa[str(k)]
        if X[ki] and sc["risk"][k] <= chi:
            active[ki] = True
            inventory[ki] = q_ki

    if not any(active):
        best_ki, best_r = -1, 1e9
        for ki in range(num_H):
            k = hub_idx[ki]
            if sc["risk"][k] < best_r:
                best_r = sc["risk"][k]
                best_ki = ki
        active[best_ki] = True
        inventory[best_ki] = R[best_ki] * kappa[str(hub_idx[best_ki])]

    # 2. Demand Scoring
    raw_urgency = [0.0]*num_I
    raw_isolation = [0.0]*num_I
    raw_dist = [0.0]*num_I
    for ii in range(num_I):
        i = dem_idx[ii]
        D = sc["demand"][str(i)]
        lam = inst["lambda"][f"{ii}_{si}"]
        raw_urgency[ii] = lam * D

        n_reach = 0
        min_t = 1e9
        for ki in range(num_H):
            if not active[ki]: continue
            k = hub_idx[ki]
            reachable = False
            for m in range(num_M):
                if sc["accessibility"][m][i][k]:
                    reachable = True
                    min_t = min(min_t, inst["transport"]["time"][m][i][k])
            if reachable: n_reach += 1
        raw_isolation[ii] = 1.0/n_reach if n_reach > 0 else 1.0
        raw_dist[ii] = min_t if min_t < 1e9 else 0.0

    def norm(vec):
        v_max = max(vec) if len(vec) > 0 else 0
        if v_max > 0:
            for idx in range(len(vec)): vec[idx] /= v_max
    
    norm(raw_urgency)
    norm(raw_isolation)
    norm(raw_dist)
    
    demand_score = [0.0]*num_I
    for ii in range(num_I):
        demand_score[ii] = W[0]*raw_urgency[ii] + W[3]*raw_isolation[ii] - W[1]*raw_dist[ii] + (ii * 1e-6)

    demand_order = sorted(range(num_I), key=lambda ii: demand_score[ii], reverse=True)

    # 3. Demand Allocation
    K = max(1, int(math.ceil(W[5] * num_H)))
    assignments = []
    hub_load = [0.0]*num_H
    
    for ii in demand_order:
        i = dem_idx[ii]
        D = sc["demand"][str(i)]
        D_kg = gamma * D
        anchor = A[ii] % num_H
        trial = hub_anchor_order[anchor]
        
        best_ki, best_m, best_t = -1, -1, 1e9
        best_hub_score = -1e18
        
        # Pass 1
        for j in range(K):
            if j >= len(trial): break
            ki = trial[j]
            if not active[ki] and not y[ki]: continue
            k = hub_idx[ki]
            b_m, best_c_t = -1, 1e9
            reachable = False
            for m in [0, 1]:
                if sc["accessibility"][m][i][k]:
                    reachable = True
                    if inst["transport"]["time"][m][i][k] < best_c_t:
                        best_c_t = inst["transport"]["time"][m][i][k]
                        b_m = m
            if b_m == -1 and sc["accessibility"][2][i][k]:
                reachable = True
                best_c_t = inst["transport"]["time"][2][i][k]
                b_m = 2
            
            if not reachable: continue
            residual = inventory[ki] - hub_load[ki]

            # Pass 1: Traditionally requires positive residual capacity.
            # FIX (trans-shipment awareness): Allow hubs with 0 stock (like reactive hubs)
            # to be considered in Pass 1 if there is surplus available elsewhere in the 
            # network that could be trans-shipped here in Step 6.
            has_global_surplus = False
            for kj in range(num_H):
                if (active[kj] or y[kj]) and (inventory[kj] - hub_load[kj] > 1e-6):
                    has_global_surplus = True
                    break

            if residual <= 0.0 and not has_global_surplus:
                continue
            
            score = W[1] * (1.0 / (best_c_t + 1e-9)) + W[2] * max(0.0, residual) + W[4] * (1.0 if X[ki] else 0.0)
            if score > best_hub_score:
                best_hub_score = score
                best_ki = ki
                best_t = best_c_t
                best_m = b_m
        
        # Pass 2
        if best_ki == -1:
            for j in range(K, num_H):
                if j >= len(trial): break
                ki = trial[j]
                if not active[ki] and not y[ki]: continue
                k = hub_idx[ki]
                b_m, best_c_t = -1, 1e9
                reachable = False
                for m in [0, 1]:
                    if sc["accessibility"][m][i][k]:
                        reachable = True
                        if inst["transport"]["time"][m][i][k] < best_c_t:
                            best_c_t = inst["transport"]["time"][m][i][k]
                            b_m = m
                if b_m == -1 and sc["accessibility"][2][i][k]:
                    reachable = True
                    best_c_t = inst["transport"]["time"][2][i][k]
                    b_m = 2
                
                if not reachable: continue
                best_ki, best_t, best_m = ki, best_c_t, b_m
                break
        
        # Pass 3: Forced reactive
        if best_ki == -1:
            for ki in range(num_H):
                if active[ki] or y[ki]: continue
                k = hub_idx[ki]
                if sc["risk"][k] > chi: continue
                
                b_m, best_c_t = -1, 1e9
                reachable = False
                for m in [0, 1]:
                    if sc["accessibility"][m][i][k]:
                        reachable = True
                        if inst["transport"]["time"][m][i][k] < best_c_t:
                            best_c_t = inst["transport"]["time"][m][i][k]
                            b_m = m
                if b_m == -1 and sc["accessibility"][2][i][k]:
                    reachable = True
                    best_c_t = inst["transport"]["time"][2][i][k]
                    b_m = 2
                
                if not reachable: continue
                y[ki] = True
                inventory[ki] = 0.0 # FIXED: Reactive hubs have 0 pre-positioned inventory
                best_ki, best_t, best_m = ki, best_c_t, b_m
                break
        
        if best_ki != -1:
            assignments.append((ii, best_ki, best_m))
            hub_load[best_ki] += D_kg
            if not X[best_ki] and not y[best_ki]:
                y[best_ki] = True
                inventory[best_ki] = 0.0 # FIXED: Reactive hubs have 0 pre-positioned inventory

    # 4. Origins (Supply to Hubs)
    net_inv = [inventory[ki] - hub_load[ki] for ki in range(num_H)]
    for jj in range(num_J):
        j = ori_idx[jj]
        O = sc["supply"][str(j)]
        best_ki, worst_net = -1, 1e18
        for ki in range(num_H):
            if not active[ki] and not y[ki]: continue
            k = hub_idx[ki]
            reachable = any(sc["accessibility"][m][j][k] for m in range(num_M))
            if not reachable: continue
            if net_inv[ki] < worst_net:
                worst_net = net_inv[ki]
                best_ki = ki
        
        if best_ki == -1:
            for ki in range(num_H):
                if active[ki] or y[ki]:
                    best_ki = ki; break
        
        if best_ki != -1:
            net_inv[best_ki] += O
            
    # 5. Transshipments
    transshipments = []
    for _ in range(num_H * num_H):
        src_ki, dst_ki = -1, -1
        best_pair_score = -1e18
        for ski in range(num_H):
            if (not active[ski] and not y[ski]) or net_inv[ski] <= 1e-6: continue
            for dki in range(num_H):
                if (not active[dki] and not y[dki]) or net_inv[dki] >= -1e-6: continue
                
                # Reachability check
                sk, dk = hub_idx[ski], hub_idx[dki]
                reachable = any(sc["accessibility"][m][sk][dk] for m in range(num_M))
                if not reachable: continue
                
                score = net_inv[ski] - net_inv[dki]
                if score > best_pair_score:
                    best_pair_score = score
                    src_ki, dst_ki = ski, dki
                    
        if src_ki == -1 or dst_ki == -1: break
        
        k, h = hub_idx[src_ki], hub_idx[dst_ki]
        cm, best_c = -1, 1e9
        for m in [0, 1]:
            if sc["accessibility"][m][k][h]:
                if inst["transport"]["cost"][m][k][h] < best_c:
                    best_c = inst["transport"]["cost"][m][k][h]
                    cm = m
        if cm == -1 and sc["accessibility"][2][k][h]:
            cm = 2
            
        if cm == -1: break
        
        flow = min(net_inv[src_ki], -net_inv[dst_ki])
        net_inv[src_ki] -= flow
        net_inv[dst_ki] += flow
        transshipments.append((src_ki, dst_ki, cm, flow))

    reactive_hubs = set([ki for ki in range(num_H) if y[ki] and not X[ki]])
    
    return {
        "assignments": assignments,
        "transshipments": transshipments,
        "reactive_hubs": reactive_hubs,
        "hub_load": hub_load,
        "inventory": inventory,
        "y": y
    }

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

    dec = decode_exact(sol, inst, si)
    assignments = dec["assignments"]
    transshipments = dec["transshipments"]
    reactive_hubs = dec["reactive_hubs"]
    hub_load = dec["hub_load"]
    inventory = dec["inventory"]
    y_open = dec["y"]

    # 1. Routing Links (Modal differentiated)
    for ii, ki, m in assignments:
        p_dem = xy(dem_idx[ii])
        p_hub = xy(hub_idx[ki])
        style = MODE_STYLES[m]
        ax.plot([p_dem[0], p_hub[0]], [p_dem[1], p_hub[1]], 
                color=style["color"], ls=style["ls"], lw=LW_LINK, 
                alpha=style["alpha"], zorder=3)

    # 1.5 Transshipment flows
    for src_ki, dst_ki, m, flow in transshipments:
        p_src = xy(hub_idx[src_ki])
        p_dst = xy(hub_idx[dst_ki])
        style = MODE_STYLES[m]
        ax.annotate("", xy=p_dst, xytext=p_src,
                    arrowprops=dict(arrowstyle="->", color=style["color"],
                                    ls=style["ls"], lw=2.0, alpha=0.8),
                    zorder=4)

    # 2. Demand Nodes
    for ii, i in enumerate(dem_idx):
        p = xy(i)
        r = risks[i]
        color = plt.cm.RdYlGn_r(r)
        d_val = sc["demand"].get(str(i), 50.0)
        s = 5 + (d_val / 500.0)
        ax.scatter(p[0], p[1], s=s, c=[color], edgecolors="none", alpha=0.9, zorder=5)

    # 3. Hubs
    for ki in range(inst["dimensions"]["num_H"]):
        h = hub_idx[ki]
        p = xy(h)
        is_planned = sol["X"][ki] == 1
        is_reactive = ki in reactive_hubs
        is_open = is_planned or is_reactive
        safe = risks[h] <= chi
        
        if not is_open:
            ax.scatter(p[0], p[1], s=40, c=COL_HUB_CLOSED, marker="^", edgecolors="black", lw=0.6, zorder=6)
            continue
            
        color = COL_HUB_OPEN if safe else COL_HUB_RISKY
        if is_reactive: color = COL_HUB_REACT
        
        # Draw full base
        marker = "H" if is_reactive else "s"
        size = 150
        
        # User requested filling percentage match decision variable R.
        # FIXED: inventory filling should not be present in reactive hubs.
        if is_reactive:
            label_txt = f"H{ki} (R)"
            ax.plot(p[0], p[1], marker=marker, markersize=14, markerfacecolor=color, markeredgecolor="black", markeredgewidth=1.2, zorder=7)
        else:
            R_val = sol["R"][ki]
            fill_pct = int(R_val * 100)
            label_txt = f"H{ki}\n[{fill_pct}%]"
            # Draw with bottom fill
            ax.plot(p[0], p[1], marker=marker, markersize=14, markerfacecolor="white", markeredgecolor="black", markeredgewidth=1.2, zorder=6)
            ax.plot(p[0], p[1], marker=marker, markersize=14, markerfacecolor=color, markeredgecolor="none", fillstyle="bottom", zorder=7)

        ax.annotate(label_txt, p, xytext=(0, 8), textcoords="offset points", 
                    fontsize=7, fontweight="bold", ha="center", va="bottom",
                    path_effects=[matplotlib.patheffects.withStroke(linewidth=2, foreground='white')], zorder=8)

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
                ctx.add_basemap(ax, source=ctx.providers.CartoDB.Positron, zoom=9, alpha=0.6)
            except: pass

    # Elegant Legend
    legend_elements = [
        Line2D([0], [0], color=COL_HUB_OPEN, marker="s", ls="", label="Planned Hub (Safe)", markersize=8),
        Line2D([0], [0], color=COL_HUB_RISKY, marker="s", ls="", label="Planned Hub (Risky)", markersize=8),
        Line2D([0], [0], color=COL_HUB_REACT, marker="H", ls="", label="Reactive Hub", markersize=8),
        Line2D([0], [0], color="black", marker="s", ls="", markerfacecolor="gray", fillstyle="bottom", label="Inv. Fill %", markersize=8),
        Line2D([0], [0], color=COL_ORIGIN, marker="D", ls="", label="Supply Origin", markersize=8),
        Line2D([0], [0], color=plt.cm.RdYlGn_r(0.2), marker="o", ls="", label="Demand (Safe)", markersize=6),
        Line2D([0], [0], color=plt.cm.RdYlGn_r(0.8), marker="o", ls="", label="Demand (Risky)", markersize=8),
        Line2D([0], [0], color=MODE_STYLES[0]["color"], ls=MODE_STYLES[0]["ls"], label="Truck Mode", lw=1.5),
        Line2D([0], [0], color=MODE_STYLES[1]["color"], ls=MODE_STYLES[1]["ls"], label="Water Mode", lw=1.5),
        Line2D([0], [0], color=MODE_STYLES[2]["color"], ls=MODE_STYLES[2]["ls"], label="Air Mode (Heli)", lw=1.5),
        Line2D([0], [0], color="#555555", ls="-", lw=2.0, marker=">", label="Lateral Flow", markersize=6),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=4, fontsize=9, 
               bbox_to_anchor=(0.5, 0.02), frameon=True, facecolor="white", edgecolor="#DDDDDD")
    
    plt.tight_layout(rect=[0, 0.12, 1, 0.94])
    fig.suptitle(f"Strategic Relief Network Configuration - CV-Large Instance\nRepresentative Solution ($Z_1$=\\${sol['Z1']/1e6:.1f}M, $Z_2$={sol['Z2']:.0f} deprivation)", 
                 fontsize=15, fontweight="bold", y=0.98)
    
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, dpi=250, bbox_inches="tight")
    print(f"Figure saved to: {args.out}")

if __name__ == "__main__":
    main()
