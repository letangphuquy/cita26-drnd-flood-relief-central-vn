"""
map_renderer.py — Draw a CITA/MO-IHLNDP solution on a 2-D node map.

Uses only Matplotlib (no external tile servers required).

Node roles
----------
  demand  → blue circle
  hub     → open=orange diamond / closed=grey diamond
  origin  → green triangle-up

Overlays drawn
--------------
  1. Demand → nearest-open-hub allocation lines (light grey)
  2. Hub node markers (emphasised)
  3. Demand node markers coloured by transport mode
  4. Origin node markers
  5. Node labels (optional)
  6. Legend + colour-bar for transport mode
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from .solution_loader import NodeInfo, Solution, infer_hub_allocations


# ── Colour constants ────────────────────────────────────────────────────────
COL_DEMAND       = "#4C72B0"   # demand nodes (no mode highlight)
COL_HUB_OPEN     = "#DD8452"   # open hub
COL_HUB_CLOSED   = "#BBBBBB"   # closed hub
COL_ORIGIN       = "#55A868"   # supply origin
COL_ALLOC        = "#CCCCCC"   # demand→hub spoke lines
COL_BG           = "#F8F9FA"   # axes background

# Transport mode colours  (mode 0=road, 1=water, 2=air)
MODE_COLOURS = {0: "#E53935", 1: "#039BE5", 2: "#7CB342"}
MODE_LABELS  = {0: "road", 1: "water/sea", 2: "air"}


class SolutionMapRenderer:
    """
    Renders one Solution onto a Matplotlib Axes.

    Usage
    -----
    renderer = SolutionMapRenderer(node_info)
    renderer.render(ax, solution, show_labels=True)
    """

    def __init__(self, node_info: NodeInfo, figsize: Tuple[int, int] = (9, 8)):
        self.info = node_info
        self.figsize = figsize

    # ── public API ──────────────────────────────────────────────────────────

    def render(self, ax: plt.Axes, solution: Solution, *,
               show_labels: bool = True,
               show_alloc: bool = True,
               show_mode_colour: bool = True):
        """
        Clear *ax* and draw the solution.

        Parameters
        ----------
        ax              : Matplotlib Axes to draw into (will be cleared).
        solution        : Parsed solution from loader.
        show_labels     : Draw node name labels.
        show_alloc      : Draw spoke lines from demand to hub.
        show_mode_colour: Colour demand nodes by transport mode.
        """
        ax.cla()
        ax.set_facecolor(COL_BG)

        coords = self.info.coords
        demand_set = set(self.info.demand_indices)
        hub_set    = set(self.info.hub_indices)
        origin_set = set(self.info.origin_indices)

        open_hub_globals = {self.info.hub_indices[k]
                            for k in solution.open_hubs}

        # ── 1. Spoke lines ─────────────────────────────────────────────────
        if show_alloc and open_hub_globals:
            pairs = infer_hub_allocations(solution, self.info)
            for d_idx, h_idx in pairs:
                (x0, y0), (x1, y1) = coords[d_idx], coords[h_idx]
                ax.plot([x0, x1], [y0, y1],
                        color=COL_ALLOC, linewidth=0.6, alpha=0.7, zorder=1)

        # ── 2. All nodes: background pass for closed hubs ──────────────────
        for k, h_idx in enumerate(self.info.hub_indices):
            x, y = coords[h_idx]
            if h_idx in open_hub_globals:
                continue  # drawn in pass 4
            ax.scatter(x, y, c=COL_HUB_CLOSED, s=80, marker="D",
                       edgecolors="grey", linewidths=0.6, zorder=3)

        # ── 3. Demand nodes ────────────────────────────────────────────────
        for i, d_idx in enumerate(self.info.demand_indices):
            x, y = coords[d_idx]
            if show_mode_colour and i < len(solution.A):
                mode = solution.A[i]
                colour = MODE_COLOURS.get(mode, COL_DEMAND)
            else:
                colour = COL_DEMAND
            ax.scatter(x, y, c=colour, s=60, marker="o",
                       edgecolors="white", linewidths=0.5, zorder=4)

        # ── 4. Open hubs (on top) ─────────────────────────────────────────
        for h_idx in open_hub_globals:
            x, y = coords[h_idx]
            ax.scatter(x, y, c=COL_HUB_OPEN, s=200, marker="D",
                       edgecolors="#7B3F00", linewidths=1.2, zorder=6)

        # ── 5. Origin nodes ───────────────────────────────────────────────
        for o_idx in self.info.origin_indices:
            x, y = coords[o_idx]
            ax.scatter(x, y, c=COL_ORIGIN, s=90, marker="^",
                       edgecolors="white", linewidths=0.5, zorder=5)

        # ── 6. Labels ─────────────────────────────────────────────────────
        if show_labels:
            for i, (x, y) in enumerate(coords):
                name = self.info.names[i] if i < len(self.info.names) else str(i)
                ax.annotate(name, (x, y), fontsize=6, ha="left", va="bottom",
                            xytext=(3, 3), textcoords="offset points",
                            color="#333333", zorder=7)

        # ── 7. Legend ─────────────────────────────────────────────────────
        legend_handles = [
            mpatches.Patch(color=COL_HUB_OPEN,   label="Hub  (open)"),
            mpatches.Patch(color=COL_HUB_CLOSED, label="Hub  (closed)"),
            mpatches.Patch(color=COL_ORIGIN,     label="Supply origin"),
        ]
        if show_mode_colour:
            for m, col in MODE_COLOURS.items():
                legend_handles.append(
                    mpatches.Patch(color=col, label=f"Demand — {MODE_LABELS[m]}")
                )
        else:
            legend_handles.append(
                mpatches.Patch(color=COL_DEMAND, label="Demand node")
            )

        ax.legend(handles=legend_handles, fontsize=7,
                  loc="lower right", framealpha=0.8)

        # ── 8. Title & axis ───────────────────────────────────────────────
        n_hubs = solution.num_open_hubs
        ax.set_title(
            f"Z1={solution.Z1:,.0f}   Z2={solution.Z2:,.0f}   "
            f"Open hubs: {n_hubs}   CV={solution.CV:.3f}",
            fontsize=9, pad=6,
        )
        ax.set_xlabel("X / Longitude", fontsize=9)
        ax.set_ylabel("Y / Latitude", fontsize=9)
        ax.grid(True, linestyle=":", alpha=0.3)
        ax.margins(0.12)

    # ── convenience: standalone save ────────────────────────────────────────

    def render_to_file(self, solution: Solution, output_path: str, *,
                       show_labels: bool = True,
                       dpi: int = 150):
        """
        Render solution and save directly to a file.
        """
        fig, ax = plt.subplots(figsize=self.figsize)
        self.render(ax, solution, show_labels=show_labels)
        fig.tight_layout()
        fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        print(f"[map_renderer] Saved → {output_path}")
