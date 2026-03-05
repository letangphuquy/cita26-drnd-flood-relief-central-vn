"""
map_solution.py — Visualise a PB-NSGA-II solution on the Central Vietnam map.

Produces two figures:
  1. Solution network map: nodes (demands / hubs / origins) with open-hub
     markers, demand-to-hub arcs, and risk overlay (one panel per scenario).
  2. Pareto front scatter for the same result file.

Usage:
  python map_solution.py
      --instance <cv_small_drnd.json>
      --result   <CV_small_seed0.json>
      --out      <figures/CV_small_map.pdf>   (also writes _pareto.pdf)

Dependencies:  matplotlib, contextily, numpy, json (stdlib)
Optional:      geopandas (for shapefile overlay) — falls back gracefully.
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
from matplotlib.lines import Line2D

# ── Optional contextily for tile background ────────────────────────────────
try:
    import contextily as ctx
    HAS_CONTEXTILY = True
except ImportError:
    HAS_CONTEXTILY = False
    print("[map_solution] contextily not found — using plain background.")

# ── Optional pyproj for CRS transform ─────────────────────────────────────
try:
    from pyproj import Transformer
    _transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    def to_web_mercator(lon, lat):
        return _transformer.transform(lon, lat)
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False
    def to_web_mercator(lon, lat):
        # Approximate Web Mercator
        x = lon * 20037508.34 / 180.0
        y = math.log(math.tan((90 + lat) * math.pi / 360.0)) * 20037508.34 / math.pi
        return x, y


# ═══════════════════════════════════════════════════════════════════════════
# Palette & style constants
# ═══════════════════════════════════════════════════════════════════════════
COL_DEMAND = "#4C72B0"    # blue
COL_HUB_OPEN = "#DD8452"  # orange
COL_HUB_CLOSED = "#BBBBBB"
COL_ORIGIN = "#55A868"    # green
COL_RISK_LOW = "#FFFFFF"
COL_RISK_HIGH = "#D62728"
ALPHA_RISK = 0.18
ARROW_COLOR = "#888888"
ARROW_ALPHA = 0.55


# ═══════════════════════════════════════════════════════════════════════════
# Load data
# ═══════════════════════════════════════════════════════════════════════════
def load_instance(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_result(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_solutions(pareto_front: list) -> dict:
    """Return three representative solutions: min-Z1, balanced, min-Z2."""
    if not pareto_front:
        return {}
    by_z1 = sorted(pareto_front, key=lambda s: s["Z1"])
    by_z2 = sorted(pareto_front, key=lambda s: s["Z2"])
    # Balanced: closest to the utopia point (normalised)
    z1_vals = [s["Z1"] for s in pareto_front]
    z2_vals = [s["Z2"] for s in pareto_front]
    z1_min, z1_max = min(z1_vals), max(z1_vals)
    z2_min, z2_max = min(z2_vals), max(z2_vals)
    rng1 = max(z1_max - z1_min, 1.0)
    rng2 = max(z2_max - z2_min, 1.0)
    balanced = min(pareto_front,
                   key=lambda s: ((s["Z1"] - z1_min) / rng1) ** 2
                                 + ((s["Z2"] - z2_min) / rng2) ** 2)
    return {
        "min_cost":   by_z1[0],
        "balanced":   balanced,
        "min_depriv": by_z2[0],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Decode a solution's demand assignments for ONE scenario
# ═══════════════════════════════════════════════════════════════════════════
def decode_assignments(sol: dict, inst: dict, scenario_idx: int = 0) -> dict:
    """
    Re-run a simplified greedy assignment for visualisation purposes.
    Returns: {demand_local_idx: hub_local_idx}
    """
    dims    = inst["dimensions"]
    num_H   = dims["num_H"]
    num_I   = dims["num_I"]
    coords  = inst["nodes"]["coords"]
    hub_idx = inst["nodes"]["hub_indices"]
    dem_idx = inst["nodes"]["demand_indices"]
    X       = sol["X"]

    # Active hubs: opened AND low enough risk in this scenario
    chi     = inst["global_params"]["chi"]
    risks   = inst["scenarios"][scenario_idx]["risk"]
    active  = [ki for ki in range(num_H)
               if X[ki] == 1 and risks[hub_idx[ki]] <= chi]
    if not active:
        active = [ki for ki in range(num_H) if X[ki] == 1]
    if not active:
        active = list(range(num_H))

    # Assign each demand to its nearest active hub (Euclidean on lat/lon)
    assign = {}
    for ii in range(num_I):
        i   = dem_idx[ii]
        lat_i, lon_i = coords[i]
        best_ki, best_d = active[0], 1e30
        for ki in active:
            h = hub_idx[ki]
            lat_h, lon_h = coords[h]
            d = (lat_i - lat_h) ** 2 + (lon_i - lon_h) ** 2
            if d < best_d:
                best_d, best_ki = d, ki
        assign[ii] = best_ki
    return assign


# ═══════════════════════════════════════════════════════════════════════════
# Draw a single scenario panel
# ═══════════════════════════════════════════════════════════════════════════
def draw_scenario_panel(ax, inst: dict, sol: dict, scenario_idx: int,
                        use_mercator: bool = True):
    """Draw nodes, arcs, and risk overlay for one scenario."""
    dims     = inst["dimensions"]
    num_H    = dims["num_H"]
    coords   = inst["nodes"]["coords"]
    hub_idx  = inst["nodes"]["hub_indices"]
    dem_idx  = inst["nodes"]["demand_indices"]
    ori_idx  = inst["nodes"]["origin_indices"]
    sc       = inst["scenarios"][scenario_idx]
    chi      = inst["global_params"]["chi"]
    risks    = sc["risk"]
    X        = sol["X"]

    def xy(node_abs):
        lat, lon = coords[node_abs]
        if use_mercator:
            return to_web_mercator(lon, lat)
        return lon, lat  # plain geographic coords

    # ── Risk bubble overlay for demand nodes ─────────────────────────────
    for ii, i in enumerate(dem_idx):
        x, y = xy(i)
        r    = risks[i]
        color = plt.cm.RdYlGn_r(r)
        ax.scatter(x, y, s=200 * r + 40, c=[color], alpha=ALPHA_RISK + 0.25,
                   zorder=2, linewidths=0)

    # ── Demand–hub assignment arcs ────────────────────────────────────────
    assign = decode_assignments(sol, inst, scenario_idx)
    for ii, ki in assign.items():
        x0, y0 = xy(dem_idx[ii])
        x1, y1 = xy(hub_idx[ki])
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="->", color=ARROW_COLOR,
                                   alpha=ARROW_ALPHA, lw=0.8),
                    zorder=3)

    # ── Hub nodes ────────────────────────────────────────────────────────
    for ki in range(num_H):
        h      = hub_idx[ki]
        x, y   = xy(h)
        is_open = X[ki] == 1
        safe    = risks[h] <= chi
        marker  = "s" if is_open else "^"
        color   = COL_HUB_OPEN if (is_open and safe) else \
                  "#FF6666" if (is_open and not safe) else COL_HUB_CLOSED
        size    = 180 if is_open else 60
        ax.scatter(x, y, s=size, c=color, marker=marker,
                   edgecolors="black", linewidths=0.7, zorder=5)
        ax.annotate(f"H{ki}", (x, y), textcoords="offset points",
                    xytext=(5, 5), fontsize=6, color="black", zorder=6)

    # ── Demand nodes ─────────────────────────────────────────────────────
    for ii, i in enumerate(dem_idx):
        x, y = xy(i)
        ax.scatter(x, y, s=30, c=COL_DEMAND, marker="o",
                   edgecolors="none", alpha=0.85, zorder=4)

    # ── Origin nodes ─────────────────────────────────────────────────────
    for j in ori_idx:
        x, y = xy(j)
        ax.scatter(x, y, s=100, c=COL_ORIGIN, marker="D",
                   edgecolors="black", linewidths=0.7, zorder=5)

    sc_name = sc.get("name", f"Scenario {scenario_idx}")
    ax.set_title(f"{sc_name}  (π={sc['probability']:.2f})", fontsize=9)
    ax.set_xlabel("Longitude" if not use_mercator else "")
    ax.set_ylabel("Latitude"  if not use_mercator else "")
    ax.tick_params(labelsize=7)


# ═══════════════════════════════════════════════════════════════════════════
# Figure 1: Solution network map (one column per scenario, one row per sol)
# ═══════════════════════════════════════════════════════════════════════════
def make_solution_map(inst: dict, result: dict, out_path: str):
    pareto = result.get("pareto_front", [])
    if not pareto:
        print("[map] No pareto_front in result file.")
        return

    reps = pick_solutions(pareto)
    sol_labels = {
        "min_cost":   "Min Cost",
        "balanced":   "Balanced",
        "min_depriv": "Min Deprivation",
    }
    num_S = inst["dimensions"]["num_S"]
    num_rows = len(reps)
    num_cols = num_S

    use_mercator = HAS_PYPROJ

    fig, axes = plt.subplots(num_rows, num_cols,
                             figsize=(4.5 * num_cols, 4 * num_rows),
                             squeeze=False)
    fig.suptitle("PB-NSGA-II: Representative Solutions on CV-Small Network",
                 fontsize=11, fontweight="bold", y=1.01)

    for row_idx, (key, sol) in enumerate(reps.items()):
        for si in range(num_S):
            ax = axes[row_idx][si]
            draw_scenario_panel(ax, inst, sol, si, use_mercator=use_mercator)

            # Add tile background if available
            if HAS_CONTEXTILY and use_mercator:
                try:
                    ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik,
                                    zoom=9, alpha=0.5)
                except Exception as e:
                    print(f"[map] Tile fetch failed: {e}")

            if si == 0:
                label = sol_labels.get(key, key)
                ax.set_ylabel(
                    f"{label}\nZ1={sol['Z1']:.2e}, Z2={sol['Z2']:.0f}",
                    fontsize=8)

    # ── Legend ────────────────────────────────────────────────────────────
    legend_elements = [
        mpatches.Patch(color=COL_HUB_OPEN, label="Hub (open, safe)"),
        mpatches.Patch(color="#FF6666",     label="Hub (open, risky)"),
        mpatches.Patch(color=COL_HUB_CLOSED, label="Hub (closed)"),
        mpatches.Patch(color=COL_DEMAND,    label="Demand node"),
        mpatches.Patch(color=COL_ORIGIN,    label="Origin / Supply"),
        Line2D([0], [0], color=ARROW_COLOR, marker=">",
               markersize=6, label="Demand assignment"),
    ]
    fig.legend(handles=legend_elements, loc="lower center",
               ncol=3, fontsize=8, bbox_to_anchor=(0.5, -0.02))

    plt.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    print(f"[map] Saved: {out_path}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════
# Figure 2: Pareto front scatter
# ═══════════════════════════════════════════════════════════════════════════
def make_pareto_plot(inst: dict, result: dict, out_path: str):
    pareto = result.get("pareto_front", [])
    if not pareto:
        return

    z1 = [s["Z1"] for s in pareto]
    z2 = [s["Z2"] for s in pareto]

    fig, ax = plt.subplots(figsize=(5, 4))
    ax.scatter(z1, z2, s=40, c="#4C72B0", alpha=0.8, edgecolors="white", linewidths=0.5)

    reps = pick_solutions(pareto)
    rep_colors = {"min_cost": "#DD8452", "balanced": "#55A868", "min_depriv": "#C44E52"}
    rep_labels = {"min_cost": "Min Cost", "balanced": "Balanced", "min_depriv": "Min Deprivation"}
    for key, sol in reps.items():
        ax.scatter(sol["Z1"], sol["Z2"], s=100, c=rep_colors[key],
                   edgecolors="black", linewidths=0.8, zorder=5,
                   label=rep_labels[key])

    ax.set_xlabel("$Z_1$ — Total Expected Cost (\\$)", fontsize=10)
    ax.set_ylabel("$Z_2$ — Max Expected Deprivation", fontsize=10)
    ax.set_title("PB-NSGA-II: Pareto Front (CV-Small)", fontsize=11)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    pareto_path = out_path.replace(".pdf", "_pareto.pdf").replace(".png", "_pareto.png")
    fig.savefig(pareto_path, dpi=180, bbox_inches="tight")
    print(f"[map] Saved Pareto: {pareto_path}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════
def main():
    p = argparse.ArgumentParser(description="Visualise MO-IHLNDP solution on CV map")
    p.add_argument("--instance", required=True,  help="DRND instance JSON")
    p.add_argument("--result",   required=True,  help="Solver result JSON")
    p.add_argument("--out",      required=True,  help="Output PDF/PNG path")
    args = p.parse_args()

    inst   = load_instance(args.instance)
    result = load_result(args.result)

    make_solution_map(inst, result, args.out)
    make_pareto_plot(inst, result, args.out)


if __name__ == "__main__":
    main()
