"""
main.py — CLI entry point for the CITA Solution Visualizer.

Two modes
---------
  GUI (default)
    python -m visualizer.main [--file PATH] [--instance PATH]

  CLI batch export
    python -m visualizer.main --cli --file PATH [--instance PATH]
                              [--index N] [--list] [--out IMAGE]

Usage examples
--------------
  # Launch interactive GUI (opens with a file browser)
  python -m visualizer.main

  # GUI pre-loaded with a result file
  python -m visualizer.main --file results/exp1/AP10_seed0.json

  # CLI: list all solutions in a file
  python -m visualizer.main --cli --file results/exp1/AP10_seed0.json --list

  # CLI: export map for solution index 3 (1-based)
  python -m visualizer.main --cli \\
      --file results/exp1/AP10_seed0.json \\
      --instance data/benchmark/AP10_seed42_drnd.json \\
      --index 3 --out figures/solution_3.png

  # CLI: compare Pareto fronts across a folder
  python -m visualizer.main --cli --folder results/exp1 --compare --out figures/pareto.png
"""
import argparse
import os
import sys
from pathlib import Path

# Ensure src/ is on path when invoked without install
_SRC = Path(__file__).resolve().parent.parent.parent  # …/CITA_paper/src
sys.path.insert(0, str(_SRC))

from visualizer.solution_loader import (
    load_instance, load_result, load_results_from_folder,
)
from visualizer.map_renderer import SolutionMapRenderer
from visualizer.pareto_plot import plot_pareto_comparison


def _cli_list(result, show_feasible: bool = False):
    """Print a table of solutions."""
    pf = result.pareto_front
    feas = result.all_feasible

    print(f"\n{'='*60}")
    print(f"File   : {result.filepath}")
    print(f"Solver : {result.solver}   seed={result.seed}")
    print(f"{'='*60}")

    def _print_table(sols, label):
        if not sols:
            return
        print(f"\n{label}  ({len(sols)} solutions)\n"
              f"{'Idx':>5}  {'Z1':>15}  {'Z2':>15}  {'CV':>6}  "
              f"{'rank':>4}  {'hubs':>5}")
        print("-" * 60)
        for i, s in enumerate(sols):
            hubs = "".join(str(x) for x in s.X)
            print(f"{i+1:>5}  {s.Z1:>15,.1f}  {s.Z2:>15,.1f}  "
                  f"{s.CV:>6.3f}  {s.rank:>4}  {hubs}")

    _print_table(pf, "Pareto front")
    if show_feasible:
        _print_table(feas, "all_feasible")

    print()


def _cli_export_map(result, node_info, index: int, out_path: str):
    """Export map image for a specific solution."""
    sols = result.pareto_front or result.all_feasible
    if not sols:
        print("[error] No solutions found.")
        return
    if not (1 <= index <= len(sols)):
        print(f"[error] Index {index} out of range 1–{len(sols)}")
        return

    sol = sols[index - 1]
    renderer = SolutionMapRenderer(node_info)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    renderer.render_to_file(sol, out_path)


def _cli_compare(folder: str, out_path: str):
    """Comparison Pareto plot across all result files in a folder."""
    results = load_results_from_folder(folder)
    if not results:
        print(f"[error] No JSON result files in {folder}")
        return
    plot_pareto_comparison(results, output_path=out_path, show=False)


def main():
    parser = argparse.ArgumentParser(
        description="CITA Solution Visualizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--file",     "-f", default=None,
                        help="Path to solver output JSON file")
    parser.add_argument("--folder",   "-d", default=None,
                        help="Path to folder containing result JSON files")
    parser.add_argument("--instance", "-i", default=None,
                        help="Path to DRND instance JSON (for map rendering)")
    parser.add_argument("--cli",      action="store_true",
                        help="Run in CLI/batch mode (no GUI)")
    parser.add_argument("--list",     "-l", action="store_true",
                        help="[CLI] List all solutions and exit")
    parser.add_argument("--feasible", action="store_true",
                        help="[CLI --list] Also list all_feasible solutions")
    parser.add_argument("--index",    "-n", type=int, default=1,
                        help="[CLI] 1-based solution index to export (default 1)")
    parser.add_argument("--out",      "-o", default=None,
                        help="[CLI] Output file path for image or Pareto plot")
    parser.add_argument("--compare",  action="store_true",
                        help="[CLI] Produce a Pareto comparison plot for --folder")

    args = parser.parse_args()

    # ── CLI mode ─────────────────────────────────────────────────────────
    if args.cli:
        if args.compare and args.folder:
            out = args.out or "pareto_comparison.pdf"
            _cli_compare(args.folder, out)
            return

        if not args.file:
            parser.error("--cli requires --file (or --folder with --compare)")

        result = load_result(args.file)

        if args.list:
            _cli_list(result, show_feasible=args.feasible)
            return

        # Export map
        if not args.instance:
            # Try to auto-detect
            from visualizer.gui.app import _guess_instance_path
            guessed = _guess_instance_path(args.file)
            if guessed:
                print(f"[info] Auto-detected instance: {guessed}")
                args.instance = guessed
            else:
                print("[error] --instance not provided and could not be auto-detected.")
                sys.exit(1)

        node_info = load_instance(args.instance)
        out = args.out or f"solution_{args.index}.png"
        _cli_export_map(result, node_info, args.index, out)
        return

    # ── GUI mode ──────────────────────────────────────────────────────────
    import tkinter as tk
    from visualizer.gui.app import VisualizerApp

    root = tk.Tk()
    app = VisualizerApp(root)

    # Pre-load if arguments provided
    if args.file and os.path.exists(args.file):
        app.entry_file.insert(0, args.file)
        app._load_file(args.file)
    elif args.folder and os.path.exists(args.folder):
        app.entry_file.insert(0, args.folder)
        app._load_folder(args.folder)

    if args.instance and os.path.exists(args.instance):
        app._load_instance(args.instance)

    root.mainloop()


if __name__ == "__main__":
    main()
