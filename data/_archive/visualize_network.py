"""
visualize_network.py
====================
Visualises the disaster relief network topology for a selected solution
from a solver output JSON combined with the instance JSON.

Shows two maps side-by-side:
  Left:  Scenario S1 (Mild)   — road-heavy, multiple reactive hubs
  Right: Scenario S3 (Extreme) — water/air reliance, consolidated transshipment

Usage:
  python data/visualize_network.py \\
      --instance data/central_vietnam_small_drnd.json \\
      --result   results/CV_small_seed0.json \\
      --out      results/figures/network_vis.pdf
"""

import os
import sys
import json
import math
import argparse

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.lines import Line2D
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("[Warning] matplotlib not installed.")

# ---------------------------------------------------------------------------
# Colour / style palette
# ---------------------------------------------------------------------------
COLOR_DEMAND  = "#4E79A7"   # blue — demand nodes
COLOR_HUB_P   = "#F28E2B"   # orange — proactive hub (x_k=1)
COLOR_HUB_R   = "#E15759"   # red — reactive hub (y_ks=1)
COLOR_HUB_IN  = "#BAB0AC"   # grey — inactive hub
COLOR_ORIGIN  = "#76B7B2"   # teal — origin nodes
MODE_COLORS   = {0: "#D4A017", 1: "#4E79A7", 2: "#9C755F"}  # road/water/air
MODE_LABELS   = {0: "Road", 1: "Water", 2: "Air"}
MODE_STYLES   = {0: "-", 1: "--", 2: ":"}


# ---------------------------------------------------------------------------
# Helper: decode a solution chromosome for scenario s
# ---------------------------------------------------------------------------
def decode_solution(sol, inst, scenario_idx):
    """
    Reconstruct z_iks (demand assignments) from the solution's X, R, W
    by re-running a simplified decode for visualization purposes.
    """
    num_H = inst["dimensions"]["num_H"]
    num_I = inst["dimensions"]["num_I"]
    num_J = inst["dimensions"]["num_J"]
    num_M = inst["dimensions"]["num_M"]

    demand_idx = inst["nodes"]["demand_indices"]
    hub_idx    = inst["nodes"]["hub_indices"]
    origin_idx = inst["nodes"]["origin_indices"]

    X = sol["X"]
    R = sol["R"]
    W = sol["W"]
    sc = inst["scenarios"][scenario_idx]

    # Active hubs
    chi = inst["global_params"]["chi"]
    active = []
    for ki, k in enumerate(hub_idx):
        if sc["risk"][k] <= chi:
            active.append(ki)

    # Demand assignments (greedy priority — same as decoder)
    z_ik = {}
    hub_cap = {ki: R[ki] * inst["hub_params"]["capacity"][str(k)]
               for ki, k in enumerate(hub_idx)}

    for ii, i in enumerate(demand_idx):
        D = float(sc["demand"].get(str(i), 0))
        best_ki = None; best_score = -1e18
        for ki in active:
            k = hub_idx[ki]
            reachable = any(sc["accessibility"][m][k][i] for m in range(num_M))
            if not reachable:
                continue
            min_t = min(
                inst["transport"]["time"][m][k][i]
                for m in range(num_M) if sc["accessibility"][m][k][i]
            ) if reachable else 1e9
            score = W[0] * (D) - W[1] * min_t + W[2] * hub_cap.get(ki, 0)
            if score > best_score:
                best_score = score; best_ki = ki
        if best_ki is not None:
            z_ik[ii] = best_ki
            hub_cap[best_ki] -= float(inst["global_params"]["gamma"]) * D

    # Origin assignments
    z_jk = {}
    for jj, j in enumerate(origin_idx):
        deficit = {ki: -hub_cap.get(ki, 0) for ki in active}
        best_ki = max(active, key=lambda ki: deficit.get(ki, 0)) if active else None
        z_jk[jj] = best_ki

    return active, X, z_ik, z_jk


# ---------------------------------------------------------------------------
# Draw one scenario's network on axes ax
# ---------------------------------------------------------------------------
def draw_network(ax, inst, sol, scenario_idx, title=""):
    if not HAS_MPL:
        return

    coords  = inst["nodes"]["coords"]
    di      = inst["nodes"]["demand_indices"]
    hi      = inst["nodes"]["hub_indices"]
    ji      = inst["nodes"]["origin_indices"]
    sc      = inst["scenarios"][scenario_idx]
    num_M   = inst["dimensions"]["num_M"]

    active_ki, X, z_ik, z_jk = decode_solution(sol, inst, scenario_idx)
    active_set = set(active_ki)

    # Draw demand nodes
    for ii, i in enumerate(di):
        ax.scatter(coords[i][1], coords[i][0], s=50, c=COLOR_DEMAND, zorder=3,
                   marker='o', edgecolors='white', linewidths=0.5)

    # Draw hub nodes
    for ki, k in enumerate(hi):
        if ki not in active_set:
            color = COLOR_HUB_IN; marker = 's'; sz = 80
        elif X[ki]:
            color = COLOR_HUB_P; marker = 's'; sz = 130  # proactive
        else:
            color = COLOR_HUB_R; marker = 'D'; sz = 110  # reactive

        ax.scatter(coords[k][1], coords[k][0], s=sz, c=color, zorder=5,
                   marker=marker, edgecolors='black', linewidths=0.8)
        ax.annotate(f"H{ki}", (coords[k][1], coords[k][0]),
                    fontsize=6, ha='center', va='bottom', zorder=6)

    # Draw origin nodes
    for jj, j in enumerate(ji):
        ax.scatter(coords[j][1], coords[j][0], s=100, c=COLOR_ORIGIN, zorder=3,
                   marker='^', edgecolors='black', linewidths=0.8)

    # Draw demand → hub arcs
    for ii, ki in z_ik.items():
        i = di[ii]; k = hi[ki]
        # Choose best accessible mode
        best_m = min(
            (m for m in range(num_M) if sc["accessibility"][m][i][k]),
            key=lambda m: inst["transport"]["time"][m][i][k],
            default=0
        )
        ax.plot([coords[i][1], coords[k][1]], [coords[i][0], coords[k][0]],
                linestyle=MODE_STYLES[best_m], color=MODE_COLORS[best_m],
                linewidth=0.6, alpha=0.6, zorder=2)

    # Draw origin → hub arcs
    for jj, ki in z_jk.items():
        if ki is None:
            continue
        j = ji[jj]; k = hi[ki]
        ax.plot([coords[j][1], coords[k][1]], [coords[j][0], coords[k][0]],
                linestyle='-', color='#59A14F', linewidth=1.0, alpha=0.7, zorder=2)

    ax.set_title(title, fontsize=10, fontweight='bold')
    ax.set_xlabel("Longitude", fontsize=8)
    ax.set_ylabel("Latitude", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(True, alpha=0.2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", required=True, help="Path to DRND instance JSON")
    parser.add_argument("--result",   required=True, help="Path to solver output JSON")
    parser.add_argument("--out",      default="results/figures/network_vis.pdf")
    args = parser.parse_args()

    with open(args.instance) as f:
        inst = json.load(f)
    with open(args.result) as f:
        result = json.load(f)

    pareto = result.get("pareto_front", [])
    if not pareto:
        print("No Pareto solutions found in result file.")
        return

    # Pick the "knee point" solution: minimizes distance to ideal (normalised)
    z1s = [s["Z1"] for s in pareto]; z2s = [s["Z2"] for s in pareto]
    min_z1, max_z1 = min(z1s), max(z1s)
    min_z2, max_z2 = min(z2s), max(z2s)
    rng1 = max_z1 - min_z1 + 1e-9; rng2 = max_z2 - min_z2 + 1e-9
    knee_sol = min(pareto, key=lambda s: math.hypot(
        (s["Z1"] - min_z1) / rng1, (s["Z2"] - min_z2) / rng2
    ))
    print(f"Selected knee solution: Z1={knee_sol['Z1']:.2f}, Z2={knee_sol['Z2']:.2f}")

    if not HAS_MPL:
        print("matplotlib not available. Install with: pip install matplotlib")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    num_S = inst["dimensions"]["num_S"]

    draw_network(axes[0], inst, knee_sol, 0, title="Scenario S1 — Mild Flood")
    draw_network(axes[1], inst, knee_sol, min(2, num_S - 1), title="Scenario S3 — Extreme Flood")

    # Shared legend
    legend_elems = [
        mpatches.Patch(color=COLOR_DEMAND,  label="Demand node"),
        mpatches.Patch(color=COLOR_HUB_P,   label="Proactive hub (x=1)"),
        mpatches.Patch(color=COLOR_HUB_R,   label="Reactive hub (y=1)"),
        mpatches.Patch(color=COLOR_HUB_IN,  label="Inactive hub"),
        mpatches.Patch(color=COLOR_ORIGIN,  label="Origin"),
        Line2D([0],[0], color=MODE_COLORS[0], ls=MODE_STYLES[0], label="Road link"),
        Line2D([0],[0], color=MODE_COLORS[1], ls=MODE_STYLES[1], label="Water link"),
        Line2D([0],[0], color=MODE_COLORS[2], ls=MODE_STYLES[2], label="Air link"),
        Line2D([0],[0], color='#59A14F', ls='-', label="Origin supply"),
    ]
    fig.legend(handles=legend_elems, loc='lower center', ncol=5, fontsize=8,
               bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("Network Topology — Knee-Point Solution\n(Central Vietnam DRND)",
                 fontsize=13, fontweight='bold')
    fig.tight_layout(rect=[0, 0.06, 1, 1])

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    fig.savefig(args.out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"[Output] Network visualization saved: {args.out}")


if __name__ == "__main__":
    main()
