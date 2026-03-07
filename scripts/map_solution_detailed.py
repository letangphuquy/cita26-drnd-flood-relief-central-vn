import argparse
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

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

try:
    import contextily as ctx
    HAS_CONTEXTILY = True
except ImportError:
    HAS_CONTEXTILY = False

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# Colors and styles
COL_DEMAND = "#4C72B0"
COL_HUB_OPEN = "#DD8452"
COL_HUB_REACT = "#C44E52"
COL_HUB_CLOSED = "#BBBBBB"
COL_ORIGIN = "#55A868"
ALPHA_RISK = 0.15

MODE_COLORS = {
    0: ("#888888", "-"),  # Truck
    1: ("#4169E1", "--"), # Boat
    2: ("#DAA520", ":")   # Helicopter
}

def draw_scenario(ax, inst, flow_scen, use_mercator=True):
    coords = inst["nodes"]["coords"]
    dem_idx = inst["nodes"]["demand_indices"]
    hub_idx = inst["nodes"]["hub_indices"]
    ori_idx = inst["nodes"]["origin_indices"]
    
    si = flow_scen["scenario"]
    sc = inst["scenarios"][si]
    risks = sc["risk"]
    chi = inst["global_params"]["chi"]
    
    def xy(n):
        lat, lon = coords[n]
        return to_web_mercator(lon, lat) if use_mercator else (lon, lat)

    # Risk overlay
    for i in dem_idx:
        x, y = xy(i)
        r = risks[i]
        color = plt.cm.RdYlGn_r(r)
        ax.scatter(x, y, s=200*r + 40, c=[color], alpha=ALPHA_RISK, zorder=2, linewidths=0)

    # Arcs - Demand
    for da in flow_scen["demand_assignments"]:
        if da["hub_idx"] != -1:
            x0, y0 = xy(da["demand_idx"])
            x1, y1 = xy(da["hub_idx"])
            m = da["mode"]
            c, ls = MODE_COLORS.get(m, ("#000", "-"))
            ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                        arrowprops=dict(arrowstyle="->", color=c, ls=ls, alpha=0.6, lw=1.0),
                        zorder=3)
            
    # Arcs - Origin
    for oa in flow_scen["origin_assignments"]:
        if oa["hub_idx"] != -1:
            x0, y0 = xy(oa["origin_idx"])
            x1, y1 = xy(oa["hub_idx"])
            m = oa["mode"]
            c, ls = MODE_COLORS.get(m, ("#000", "-"))
            ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                        arrowprops=dict(arrowstyle="->", color=c, ls=ls, alpha=0.8, lw=1.5),
                        zorder=4)

    # Arcs - Transshipment
    for tr in flow_scen["transshipment"]:
        x0, y0 = xy(tr["src_hub_idx"])
        x1, y1 = xy(tr["dst_hub_idx"])
        m = tr["mode"]
        c, ls = MODE_COLORS.get(m, ("#000", "-"))
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="->", color=c, ls=ls, alpha=0.9, lw=2.0),
                    zorder=4)

    # Nodes - Demand
    for i in dem_idx:
        x, y = xy(i)
        ax.scatter(x, y, s=30, c=COL_DEMAND, marker="o", edgecolors="white", linewidths=0.5, zorder=5)

    # Nodes - Origins
    for j in ori_idx:
        x, y = xy(j)
        ax.scatter(x, y, s=100, c=COL_ORIGIN, marker="D", edgecolors="black", zorder=6)
        ax.annotate(f"O{ori_idx.index(j)}", (x, y), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=7, zorder=7)

    # Nodes - Hubs
    for ki, h in enumerate(hub_idx):
        x, y = xy(h)
        is_reactive = flow_scen["y_ks"][ki]
        # Check if planned open from inventory_held? Actually, flow data doesn't have X directly.
        # But we can assume if it's not reactive and inventory_held > 0, it's planned.
        # Let's just color reactive vs planned.
        inv = flow_scen["inventory_held"][ki]
        is_planned = inv > 0 and not is_reactive
        
        if is_planned:
            color = COL_HUB_OPEN
            marker = "s"
            size = 150
        elif is_reactive:
            color = COL_HUB_REACT
            marker = "*"
            size = 200
        else:
            color = COL_HUB_CLOSED
            marker = "^"
            size = 60
            
        ax.scatter(x, y, s=size, c=color, marker=marker, edgecolors="black", zorder=7)
        ax.annotate(f"H{ki}", (x, y), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8, fontweight="bold", zorder=8)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", required=True)
    parser.add_argument("--flow", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    inst = load_json(args.instance)
    flow_data = load_json(args.flow)

    fig, axes = plt.subplots(1, 3, figsize=(18, 6), dpi=300)
    titles = ["Scenario 0: Mild", "Scenario 1: Severe", "Scenario 2: Extreme"]
    
    for si in range(3):
        ax = axes[si]
        if si < len(flow_data["scenarios"]):
            f_scen = flow_data["scenarios"][si]
            draw_scenario(ax, inst, f_scen, use_mercator=True)
            
            if HAS_CONTEXTILY:
                try:
                    ctx.add_basemap(ax, source=ctx.providers.CartoDB.Positron, alpha=0.6)
                except Exception as e:
                    pass
            ax.set_title(titles[si], fontsize=14, pad=10)
            ax.axis("off")
            
    # Legends
    legend_elements = [
        Line2D([0], [0], marker='s', color='w', markerfacecolor=COL_HUB_OPEN, markersize=10, label='Planned Hub'),
        Line2D([0], [0], marker='*', color='w', markerfacecolor=COL_HUB_REACT, markersize=14, label='Reactive Hub'),
        Line2D([0], [0], marker='^', color='w', markerfacecolor=COL_HUB_CLOSED, markersize=8, label='Closed Hub'),
        Line2D([0], [0], marker='D', color='w', markerfacecolor=COL_ORIGIN, markersize=8, label='Origin Point'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor=COL_DEMAND, markersize=6, label='Demand Node'),
        Line2D([0], [0], color=MODE_COLORS[0][0], lw=1.5, ls=MODE_COLORS[0][1], label='Mode: Truck'),
        Line2D([0], [0], color=MODE_COLORS[1][0], lw=1.5, ls=MODE_COLORS[1][1], label='Mode: Motorboat'),
        Line2D([0], [0], color=MODE_COLORS[2][0], lw=1.5, ls=MODE_COLORS[2][1], label='Mode: Helicopter')
    ]
    fig.legend(handles=legend_elements, loc='lower center', ncol=8, bbox_to_anchor=(0.5, 0.02), frameon=True)
    plt.tight_layout(rect=[0, 0.08, 1, 1])
    
    # Add text annotation for Z1 and Z2
    z1 = flow_data["meta"]["Z1"]
    z2 = flow_data["meta"]["Z2"]
    fig.suptitle(f"Detailed Flow Mapping — Representative Solution (Z1 = {z1:.1f}, Z2 = {z2:.1f})", fontsize=16, fontweight="bold")
    
    plt.savefig(args.out, format="pdf", bbox_inches="tight")
    print(f"Saved {args.out}")

if __name__ == "__main__":
    main()
