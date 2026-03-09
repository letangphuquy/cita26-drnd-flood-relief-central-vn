"""
visualizer — Interactive browser and visualizer for CITA/MO-IHLNDP solver outputs.

Sub-modules
-----------
  solution_loader   Load instance JSON + solver output JSON, dataclasses
  pareto_plot       Pareto scatter component (Matplotlib)
  map_renderer      Node-map renderer for one solution (Matplotlib)
  gui.app           Tkinter interactive GUI
  main              CLI entry point (GUI launcher + batch export)

Quick start
-----------
  # Interactive GUI
  python -m visualizer.main

  # GUI pre-loaded with a file
  python -m visualizer.main --file results/exp1/AP10_seed0.json

  # CLI: list solutions
  python -m visualizer.main --cli --file results/exp1/AP10_seed0.json --list

  # CLI: export a solution map
  python -m visualizer.main --cli --file results/exp1/AP10_seed0.json \\
      --instance data/benchmark/AP10_seed42_drnd.json --index 1 --out map.png
"""

from .solution_loader import (
    NodeInfo,
    Solution,
    SolverResult,
    load_instance,
    load_result,
    load_results_from_folder,
    load_results_by_algorithm,
    merged_pareto_front,
    infer_hub_allocations,
)
from .pareto_plot import ParetoPlot, plot_pareto_comparison
from .map_renderer import SolutionMapRenderer

__all__ = [
    # data
    "NodeInfo",
    "Solution",
    "SolverResult",
    "load_instance",
    "load_result",
    "load_results_from_folder",
    "load_results_by_algorithm",
    "merged_pareto_front",
    "infer_hub_allocations",
    # visualisation
    "ParetoPlot",
    "plot_pareto_comparison",
    "SolutionMapRenderer",
]
