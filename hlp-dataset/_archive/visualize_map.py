"""
visualize_map.py — Central Vietnam DRND Network Visualisation
=============================================================
Reads:
  data/central_vietnam_small_drnd.json   — instance (coords + names)
  results/CV_small_seed<N>.json          — solver output (Pareto front)

Picks the knee-point solution (closest to origin of normalised space).
Plots:
  • Demand nodes — small circles, coloured by assigned hub
  • Hub nodes    — large ★ stars (filled = open, hollow = closed)
  • Origin nodes — green triangles
  • Assignment edges demand→hub (light, semi-transparent)
  • Transshipment edge hub→hub if present
  • Cartopy background (Natural Earth) or fallback plain axes

Output:
  paper/figures/cv_network_map.pdf   (also .png for quick preview)

Usage:
  python data/visualize_map.py [--instance path] [--result path]
                               [--seed N] [--out path]
"""

import os, sys, json, argparse, math
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

ROOT = Path(__file__).parent.parent
INST_DEFAULT = ROOT / "data" / "central_vietnam_small_drnd.json"
RES_DIR      = ROOT / "results"
OUT_DIR      = ROOT / "paper" / "figures"

# ── Palette ─────────────────────────────────────────────────────────────────
HUB_COLORS = ["#E63946","#457B9D","#2A9D8F","#E9C46A","#F4A261"]
DEMAND_ALPHA = 0.85
HUB_STAR_SIZE = 350
DEMAND_CIRCLE_SIZE = 70
EDGE_ALPHA = 0.30
MODE_COLORS = {"road": "#555555", "water": "#2196F3", "air": "#9C27B0"}

# ────────────────────────────────────────────────────────────────────────────

def load_instance(path):
    with open(path, "r") as f:
        data = json.load(f)
    return data

def load_result(path):
    with open(path, "r") as f:
        data = json.load(f)
    front = data.get("pareto_front", []) or data.get("all_feasible", [])
    return front

def find_best_result(seed=None):
    """Look for CV small result files, return best one (highest HV or first found)."""
    candidates = sorted(RES_DIR.glob("CV_small*.json"))
    if not candidates:
        return None, None
    if seed is not None:
        for c in candidates:
            if f"seed{seed}" in c.name or f"s{seed}" in c.name:
                return c, load_result(c)
    return candidates[0], load_result(candidates[0])

def knee_point(solutions):
    """Knee point: minimise distance from origin in normalised Z1-Z2 space."""
    z1s = np.array([s["Z1"] for s in solutions])
    z2s = np.array([s["Z2"] for s in solutions])
    z1n = (z1s - z1s.min()) / (z1s.max() - z1s.min() + 1e-9)
    z2n = (z2s - z2s.min()) / (z2s.max() - z2s.min() + 1e-9)
    dist = np.sqrt(z1n**2 + z2n**2)
    return solutions[int(np.argmin(dist))]

def decode_assignment(sol, inst):
    """
    Re-run assignment from the A vector stored in the solution.
    Returns: hub_open[ki], assign[ii] (local hub index for each demand)

    If A is not present, assigns each demand to the nearest open hub.
    """
    num_H = inst["dimensions"]["num_H"]
    num_I = inst["dimensions"]["num_I"]
    hub_indices = inst["nodes"]["hub_indices"]
    demand_indices = inst["nodes"]["demand_indices"]
    coords = inst["nodes"]["coords"]  # list of [lat, lon]

    X = sol.get("X", [1] * num_H)
    A = sol.get("A", None)

    hub_open = [bool(X[ki]) for ki in range(num_H)]
    open_hubs = [ki for ki in range(num_H) if hub_open[ki]]

    if not open_hubs:
        open_hubs = [0]
        hub_open[0] = True

    assign = []
    for ii in range(num_I):
        di = demand_indices[ii]
        dlat, dlon = coords[di]

        if A is not None:
            pref_ki = int(A[ii]) % num_H
        else:
            pref_ki = -1

        # Build candidate order: preferred first, then by distance
        def dist_to_hub(ki):
            hi = hub_indices[ki]
            hlat, hlon = coords[hi]
            return (dlat - hlat) ** 2 + (dlon - hlon) ** 2

        extras = sorted([ki for ki in open_hubs if ki != pref_ki],
                        key=dist_to_hub)
        if pref_ki in open_hubs:
            candidates = [pref_ki] + extras
        else:
            candidates = extras if extras else open_hubs

        assign.append(candidates[0] if candidates else 0)

    return hub_open, assign

# ────────────────────────────────────────────────────────────────────────────

def make_figure(inst, sol, use_cartopy=True):
    coords   = inst["nodes"]["coords"]   # [lat, lon]
    names    = inst["nodes"]["names"]
    dem_idx  = inst["nodes"]["demand_indices"]
    hub_idx  = inst["nodes"]["hub_indices"]
    orig_idx = inst["nodes"]["origin_indices"]
    num_H    = inst["dimensions"]["num_H"]

    hub_open, assign = decode_assignment(sol, inst)

    # lat/lon arrays
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]

    lon_min, lon_max = min(lons) - 0.15, max(lons) + 0.15
    lat_min, lat_max = min(lats) - 0.10, max(lats) + 0.10

    fig = plt.figure(figsize=(10, 9))

    use_cartopy_actual = False
    if use_cartopy:
        try:
            import cartopy.crs as ccrs
            import cartopy.feature as cfeature
            ax = fig.add_subplot(1, 1, 1,
                                 projection=ccrs.PlateCarree())
            ax.set_extent([lon_min, lon_max, lat_min, lat_max],
                          crs=ccrs.PlateCarree())
            ax.add_feature(cfeature.LAND,   facecolor="#F5F5DC", alpha=0.6)
            ax.add_feature(cfeature.OCEAN,  facecolor="#D6EAF8", alpha=0.8)
            ax.add_feature(cfeature.RIVERS, edgecolor="#85C1E9",
                           linewidth=0.8, alpha=0.7)
            ax.add_feature(cfeature.BORDERS,edgecolor="#AAAAAA",
                           linewidth=0.6)
            ax.add_feature(cfeature.COASTLINE, edgecolor="#888888",
                           linewidth=0.8)
            ax.gridlines(draw_labels=True, linewidth=0.4,
                         color="gray", alpha=0.5, linestyle="--")
            transform = ccrs.PlateCarree()
            use_cartopy_actual = True
        except Exception as e:
            print(f"[warn] cartopy failed ({e}), using plain axes")
            use_cartopy = False

    if not use_cartopy:
        ax = fig.add_subplot(1, 1, 1)
        ax.set_xlim(lon_min, lon_max)
        ax.set_ylim(lat_min, lat_max)
        ax.set_facecolor("#EBF5FB")
        ax.set_xlabel("Longitude (°E)", fontsize=10)
        ax.set_ylabel("Latitude (°N)", fontsize=10)
        ax.grid(True, linewidth=0.4, color="gray", alpha=0.4, linestyle="--")
        transform = None

    def scatter(lons_, lats_, **kw):
        if use_cartopy_actual:
            ax.scatter(lons_, lats_, transform=transform, zorder=kw.pop("zorder", 3), **kw)
        else:
            ax.scatter(lons_, lats_, zorder=kw.pop("zorder", 3), **kw)

    def plot_line(lons_, lats_, **kw):
        if use_cartopy_actual:
            ax.plot(lons_, lats_, transform=transform, **kw)
        else:
            ax.plot(lons_, lats_, **kw)

    def annotate(text, lon, lat, **kw):
        if use_cartopy_actual:
            ax.text(lon, lat, text, transform=transform, **kw)
        else:
            ax.text(lon, lat, text, **kw)

    # ── Assignment edges (demand → hub) ───────────────────────────────────
    for ii, ki in enumerate(assign):
        di = dem_idx[ii]
        hi = hub_idx[ki]
        dlat, dlon = coords[di]
        hlat, hlon = coords[hi]
        color = HUB_COLORS[ki % len(HUB_COLORS)]
        plot_line([dlon, hlon], [dlat, hlat],
                  color=color, linewidth=0.7, alpha=EDGE_ALPHA, zorder=1)

    # ── Demand nodes ───────────────────────────────────────────────────────
    for ii, di in enumerate(dem_idx):
        ki = assign[ii]
        dlat, dlon = coords[di]
        color = HUB_COLORS[ki % len(HUB_COLORS)]
        scatter([dlon], [dlat], c=[color], s=DEMAND_CIRCLE_SIZE,
                marker="o", edgecolors="white", linewidths=0.8,
                alpha=DEMAND_ALPHA, zorder=3)
        # Node label (short)
        short = names[di].replace("_", " ").replace(" District","").replace(" City","")
        annotate(short, dlon + 0.01, dlat + 0.01,
                 fontsize=5.5, color="#333333", zorder=5,
                 ha="left", va="bottom")

    # ── Hub nodes ─────────────────────────────────────────────────────────
    for ki, hi in enumerate(hub_idx):
        hlat, hlon = coords[hi]
        color = HUB_COLORS[ki % len(HUB_COLORS)]
        marker = "*" if hub_open[ki] else "P"
        edgecol = "black" if hub_open[ki] else "#666666"
        size = HUB_STAR_SIZE if hub_open[ki] else 150
        scatter([hlon], [hlat], c=[color], s=size,
                marker=marker, edgecolors=edgecol, linewidths=0.9,
                alpha=1.0, zorder=4)
        short = names[hi].replace("_", " ").replace(" Hub","").replace(" Airport","")
        annotate(short, hlon + 0.012, hlat - 0.025,
                 fontsize=6, fontweight="bold", color=color, zorder=5,
                 ha="left", va="top",
                 bbox=dict(boxstyle="round,pad=0.15", fc="white",
                           ec=color, alpha=0.7, linewidth=0.6))

    # ── Origin nodes ──────────────────────────────────────────────────────
    for oi in orig_idx:
        olat, olon = coords[oi]
        scatter([olon], [olat], c=["#2ECC71"], s=160,
                marker="^", edgecolors="#1A7A45", linewidths=1.0,
                alpha=1.0, zorder=4)
        annotate(names[oi].replace("_", " "), olon + 0.012, olat,
                 fontsize=5.5, color="#1A7A45", zorder=5, ha="left")

    # ── Legend ────────────────────────────────────────────────────────────
    legend_elems = []
    for ki in range(num_H):
        lbl = names[hub_idx[ki]].replace("_", " ").replace(" Hub","")
        status = " (open)" if hub_open[ki] else " (closed)"
        legend_elems.append(
            mpatches.Patch(facecolor=HUB_COLORS[ki % len(HUB_COLORS)],
                           edgecolor="black" if hub_open[ki] else "gray",
                           label=lbl + status, alpha=0.9))
    legend_elems += [
        Line2D([0], [0], marker="*", color="w", markerfacecolor="gray",
               markersize=12, label="Open hub ★"),
        Line2D([0], [0], marker="P", color="w", markerfacecolor="gray",
               markeredgecolor="gray", markersize=9, label="Closed hub (+)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="gray",
               markersize=8, label="Demand node"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#2ECC71",
               markeredgecolor="#1A7A45", markersize=9, label="Origin/depot"),
    ]
    ax.legend(handles=legend_elems, loc="lower left",
              fontsize=6.5, framealpha=0.88, edgecolor="#AAAAAA",
              ncol=1, title="Network nodes", title_fontsize=7)

    # ── Title / metadata ──────────────────────────────────────────────────
    z1_str = f"{sol['Z1']:.2e}"
    z2_str = f"{sol['Z2']:.2e}"
    ax.set_title(
        f"Central Vietnam — DRND Knee-Point Solution\n"
        f"$Z_1={z1_str}$ (logistics cost),  $Z_2={z2_str}$ (deprivation cost)",
        fontsize=10, pad=10)

    plt.tight_layout()
    return fig

# ────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", default=str(INST_DEFAULT))
    parser.add_argument("--result",   default=None,
                        help="Solver JSON output. Auto-detected if omitted.")
    parser.add_argument("--seed",     type=int, default=None)
    parser.add_argument("--out",      default=None,
                        help="Output path (without extension). "
                             "Defaults to paper/figures/cv_network_map")
    parser.add_argument("--no-cartopy", action="store_true")
    args = parser.parse_args()

    # --- load instance
    inst = load_instance(args.instance)
    print(f"[map] Loaded instance: {args.instance}")
    print(f"      I={inst['dimensions']['num_I']} "
          f"H={inst['dimensions']['num_H']} "
          f"J={inst['dimensions']['num_J']}")

    # --- load result (or create a dummy "all hubs open" solution)
    sol = None
    result_path = args.result
    if result_path is None:
        rpath, front = find_best_result(seed=args.seed)
        if rpath and front:
            result_path = str(rpath)
            feas = [s for s in front if s.get("CV", 1) == 0]
            pool = feas if feas else front
            sol = knee_point(pool) if len(pool) > 1 else pool[0]
            print(f"[map] Using result: {rpath.name}  ({len(pool)} solutions)")
        else:
            print("[map] No result file found — plotting instance topology only "
                  "(all hubs shown as open).")
            num_H = inst["dimensions"]["num_H"]
            sol = {"Z1": 0, "Z2": 0, "CV": 0,
                   "X": [1]*num_H, "R": [0.5]*num_H,
                   "A": list(range(inst["dimensions"]["num_I"]))}
    else:
        front = load_result(result_path)
        feas  = [s for s in front if s.get("CV", 1) == 0]
        pool  = feas if feas else front
        sol   = knee_point(pool) if len(pool) > 1 else pool[0]
        print(f"[map] Using result: {result_path}  ({len(pool)} solutions)")

    # --- plot
    use_cartopy = not args.no_cartopy
    fig = make_figure(inst, sol, use_cartopy=use_cartopy)

    # --- save
    out_base = args.out or str(OUT_DIR / "cv_network_map")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        path = f"{out_base}.{ext}"
        fig.savefig(path, dpi=200, bbox_inches="tight")
        print(f"[map] Saved: {path}")
    plt.close(fig)

if __name__ == "__main__":
    main()
