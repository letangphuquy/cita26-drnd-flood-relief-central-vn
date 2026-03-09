"""
pareto_plot.py — Pareto front scatter plot with solution selection.

Provides ParetoPlot, a Matplotlib-based component that can be embedded
into a Tkinter figure or used standalone.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from .solution_loader import Solution, SolverResult


# ── colour palette ──────────────────────────────────────────────────────────
_ALGO_COLOURS = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52",
    "#8172B2", "#937860", "#DA8BC3", "#8C8C8C",
]

# default colours when no algorithm label is provided
_COL_PF     = "#2196F3"   # blue  — Pareto-optimal
_COL_FEAS   = "#90CAF9"   # light blue — all_feasible (non-Pareto)
_COL_SEL    = "#FF5722"   # orange-red — currently selected
_COL_MARKED = "#9C27B0"   # purple — secondary highlight


class ParetoPlot:
    """
    Pareto scatter plot component.

    Can be driven by a single SolverResult (one algorithm) or a
    dict {algo_label: [Solution, ...]} for multi-algorithm comparison.

    Parameters
    ----------
    ax       : Matplotlib Axes to draw into.
    on_click : Optional callback(solution_idx) called when user clicks a point.
    """

    def __init__(self, ax: plt.Axes, on_click: Optional[Callable[[int], None]] = None):
        self.ax = ax
        self.on_click: Optional[Callable[[int], None]] = on_click

        # Internal state
        self._solutions: List[Solution] = []
        self._scatter_map: Dict[int, int] = {}   # scatter point index → solution index
        self._selected_idx: Optional[int] = None
        self._scatter_obj = None   # matplotlib PathCollection for the main scatter
        self._sel_scatter = None   # highlight scatter

        # Connect pick event once
        if ax.figure is not None:
            ax.figure.canvas.mpl_connect("pick_event", self._on_pick)

    # ── public API ─────────────────────────────────────────────────────────

    def plot_single(self, result: SolverResult, show_all_feasible: bool = True):
        """
        Plot one SolverResult (pareto_front + optional all_feasible).
        """
        self._solutions = []
        self.ax.cla()

        # Plot all_feasible as background if requested
        if show_all_feasible and result.all_feasible:
            feas_sols = [s for s in result.all_feasible if s.CV == 0.0]
            if feas_sols:
                xs = [s.Z1 for s in feas_sols]
                ys = [s.Z2 for s in feas_sols]
                self.ax.scatter(xs, ys, c=_COL_FEAS, s=18, alpha=0.5,
                                label="All feasible", zorder=2)

        # Plot Pareto front with pickable markers
        pf = result.pareto_front
        if pf:
            xs = [s.Z1 for s in pf]
            ys = [s.Z2 for s in pf]
            # Build unified solution list: PF entries come first
            offset = len(self._solutions)
            self._solutions = list(pf)
            self._scatter_obj = self.ax.scatter(
                xs, ys, c=_COL_PF, s=60, zorder=5, picker=6,
                label=f"{result.solver} Pareto ({len(pf)})",
            )
            # Map between scatter index and solutions list index
            self._scatter_map = {i: i for i in range(len(pf))}

        self._style_axes(result.solver)

    def plot_multi(self, groups: Dict[str, List[Solution]]):
        """
        Plot multiple algorithm groups on the same axes.

        Parameters
        ----------
        groups : {algo_label: [Solution, ...]}
                 Solutions in each group should be the Pareto front.
        """
        self._solutions = []
        self._scatter_map = {}
        self.ax.cla()

        colour_it = iter(_ALGO_COLOURS)
        sol_offset = 0

        for label, sols in groups.items():
            if not sols:
                continue
            colour = next(colour_it, "#888888")
            xs = [s.Z1 for s in sols]
            ys = [s.Z2 for s in sols]
            sc = self.ax.scatter(xs, ys, c=colour, s=55, zorder=5,
                                 picker=5, label=label)
            for local_i in range(len(sols)):
                self._scatter_map[sol_offset + local_i] = len(self._solutions) + local_i
            self._solutions.extend(sols)
            sol_offset += len(sols)

        self._style_axes("Multi-algorithm")

    def select(self, solution_idx: int):
        """
        Highlight a specific solution on the plot.

        Parameters
        ----------
        solution_idx : index into self._solutions
        """
        if not (0 <= solution_idx < len(self._solutions)):
            return
        self._selected_idx = solution_idx

        # Remove previous highlight
        if self._sel_scatter is not None:
            try:
                self._sel_scatter.remove()
            except Exception:
                pass
            self._sel_scatter = None

        s = self._solutions[solution_idx]
        self._sel_scatter = self.ax.scatter(
            [s.Z1], [s.Z2],
            c=_COL_SEL, s=120, zorder=10, marker="*",
            label=f"Selected #{solution_idx}",
        )
        self.ax.figure.canvas.draw_idle()

    def get_solution(self, idx: int) -> Optional[Solution]:
        if 0 <= idx < len(self._solutions):
            return self._solutions[idx]
        return None

    @property
    def count(self) -> int:
        return len(self._solutions)

    # ── internals ──────────────────────────────────────────────────────────

    def _on_pick(self, event):
        """Handle matplotlib pick event → fires on_click."""
        if event.artist is not self._scatter_obj:
            return
        indices = event.ind
        if len(indices) == 0:
            return
        scatter_i = int(indices[0])
        sol_i = self._scatter_map.get(scatter_i, scatter_i)
        self.select(sol_i)
        if self.on_click is not None:
            self.on_click(sol_i)

    def _style_axes(self, title: str):
        self.ax.set_xlabel("Z1 — Expected Logistics Cost", fontsize=10)
        self.ax.set_ylabel("Z2 — Expected Deprivation Cost", fontsize=10)
        self.ax.set_title(f"Pareto Front  ·  {title}", fontsize=11, pad=8)
        self.ax.grid(True, linestyle="--", alpha=0.4)
        self.ax.ticklabel_format(style="sci", axis="both", scilimits=(0, 0))
        if self.ax.get_legend_handles_labels()[1]:
            self.ax.legend(fontsize=8, framealpha=0.7)


# ── Stand-alone helper ──────────────────────────────────────────────────────

def plot_pareto_comparison(results: List[SolverResult],
                           output_path: Optional[str] = None,
                           show: bool = True):
    """
    Quick standalone comparison plot of multiple SolverResult objects.

    Parameters
    ----------
    results     : list of loaded solver results
    output_path : if provided, saves to this path (e.g., 'out.pdf')
    show        : display interactive window
    """
    fig, ax = plt.subplots(figsize=(8, 6))
    pp = ParetoPlot(ax)

    groups: Dict[str, List[Solution]] = {}
    for r in results:
        key = f"{r.solver}  (seed={r.seed})"
        groups[key] = r.pareto_front

    pp.plot_multi(groups)

    fig.tight_layout()
    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"[pareto_plot] Saved → {output_path}")
    if show:
        plt.show()

    return fig, ax
