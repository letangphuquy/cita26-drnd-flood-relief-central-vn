"""
gui/app.py — Interactive Tkinter GUI for browsing CITA solver outputs.

Layout
------
  ┌─────────────────────────────────────────────────────────────┐
  │  Toolbar  (file/folder, algo filter, navigation, jump-to)   │
  ├────────────────────────────┬────────────────────────────────┤
  │        Map view            │     Pareto scatter view        │
  │   (SolutionMapRenderer)    │        (ParetoPlot)            │
  ├────────────────────────────┼────────────────────────────────┤
  │       Status bar           │      Side-panel controls       │
  └────────────────────────────┴────────────────────────────────┘

Keyboard shortcuts
------------------
  ← / →       prev / next solution
  Ctrl-O      open file
  Ctrl-S      save current map
  Ctrl-F      open folder
  Escape      clear filters / reset to all solutions
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

# ── project imports ──────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from visualizer.solution_loader import (
    NodeInfo, Solution, SolverResult,
    load_instance, load_result, load_results_from_folder,
    merged_pareto_front,
)
from visualizer.pareto_plot import ParetoPlot
from visualizer.map_renderer import SolutionMapRenderer


# ════════════════════════════════════════════════════════════════════════════
# Main application
# ════════════════════════════════════════════════════════════════════════════

class VisualizerApp:
    """Main browsing / visualization GUI."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CITA Solution Browser")
        self.root.geometry("1500x920")
        self.root.minsize(1100, 700)

        # ── State ──────────────────────────────────────────────────────────
        self.node_info: Optional[NodeInfo] = None
        self.renderer: Optional[SolutionMapRenderer] = None

        # All loaded solver results
        self.all_results: List[SolverResult] = []

        # Displayed solutions (filtered by algorithm)
        self.display_solutions: List[Solution] = []
        self.current_idx: int = 0

        # Algorithm filter
        self.algo_filter: tk.StringVar = tk.StringVar(value="All")

        # Display toggles
        self.var_show_labels   = tk.BooleanVar(value=True)
        self.var_show_alloc    = tk.BooleanVar(value=True)
        self.var_show_mode_col = tk.BooleanVar(value=True)
        self.var_show_feasible = tk.BooleanVar(value=True)
        self.var_pf_only       = tk.BooleanVar(value=False)

        # ── Build UI ───────────────────────────────────────────────────────
        self._build_menu()
        self._build_toolbar()
        self._build_main_area()
        self._build_status_bar()

        # ── Keyboard ───────────────────────────────────────────────────────
        self.root.bind("<Left>",      lambda _e: self._prev())
        self.root.bind("<Right>",     lambda _e: self._next())
        self.root.bind("<Control-o>", lambda _e: self._browse_file())
        self.root.bind("<Control-f>", lambda _e: self._browse_folder())
        self.root.bind("<Control-s>", lambda _e: self._save_map())
        self.root.bind("<Escape>",    lambda _e: self._reset_filter())

    # ════════════════════════════════════════════════════════════════════════
    # UI construction
    # ════════════════════════════════════════════════════════════════════════

    def _build_menu(self):
        mb = tk.Menu(self.root)
        self.root.config(menu=mb)

        # File
        fm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="File", menu=fm)
        fm.add_command(label="Open JSON file…",   command=self._browse_file,
                       accelerator="Ctrl-O")
        fm.add_command(label="Open results folder…", command=self._browse_folder,
                       accelerator="Ctrl-F")
        fm.add_separator()
        fm.add_command(label="Load instance JSON…", command=self._browse_instance)
        fm.add_separator()
        fm.add_command(label="Save map image…", command=self._save_map,
                       accelerator="Ctrl-S")
        fm.add_separator()
        fm.add_command(label="Exit", command=self.root.quit)

        # View
        vm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="View", menu=vm)
        vm.add_checkbutton(label="Node labels",
                           variable=self.var_show_labels, command=self._refresh_map)
        vm.add_checkbutton(label="Allocation spokes",
                           variable=self.var_show_alloc, command=self._refresh_map)
        vm.add_checkbutton(label="Colour by transport mode",
                           variable=self.var_show_mode_col, command=self._refresh_map)
        vm.add_separator()
        vm.add_checkbutton(label="Show all_feasible on Pareto plot",
                           variable=self.var_show_feasible,
                           command=self._refresh_pareto)
        vm.add_checkbutton(label="Pareto-front only",
                           variable=self.var_pf_only,
                           command=self._apply_filter)

    def _build_toolbar(self):
        bar = ttk.Frame(self.root)
        bar.pack(side=tk.TOP, fill=tk.X, padx=6, pady=4)

        # ── File section ────────────────────────────────────────────────
        ttk.Label(bar, text="Result:").pack(side=tk.LEFT, padx=(0, 4))
        self.entry_file = ttk.Entry(bar, width=46)
        self.entry_file.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bar, text="Browse File",   command=self._browse_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Browse Folder", command=self._browse_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Load ▶",        command=self._load_from_entry).pack(side=tk.LEFT, padx=(2, 10))

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        # ── Algorithm filter ────────────────────────────────────────────
        ttk.Label(bar, text="Algo:").pack(side=tk.LEFT, padx=(0, 4))
        self.combo_algo = ttk.Combobox(bar, textvariable=self.algo_filter,
                                       width=18, state="readonly")
        self.combo_algo["values"] = ["All"]
        self.combo_algo.pack(side=tk.LEFT, padx=(0, 4))
        self.combo_algo.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter())

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        # ── Navigation ──────────────────────────────────────────────────
        ttk.Button(bar, text="◀ Prev", command=self._prev).pack(side=tk.LEFT, padx=2)
        self.lbl_idx = ttk.Label(bar, text="—  /  —", width=12, anchor=tk.CENTER)
        self.lbl_idx.pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Next ▶", command=self._next).pack(side=tk.LEFT, padx=2)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(bar, text="Jump:").pack(side=tk.LEFT, padx=(0, 3))
        self.entry_jump = ttk.Entry(bar, width=6)
        self.entry_jump.pack(side=tk.LEFT, padx=(0, 3))
        self.entry_jump.bind("<Return>", lambda _e: self._jump())
        ttk.Button(bar, text="Go", command=self._jump).pack(side=tk.LEFT, padx=2)

    def _build_main_area(self):
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=3)

        # ── Left: map figure ────────────────────────────────────────────
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=5)

        self.fig_map = Figure(figsize=(8, 8), dpi=95)
        self.ax_map  = self.fig_map.add_subplot(111)

        self.canvas_map = FigureCanvasTkAgg(self.fig_map, master=left_frame)
        self.canvas_map.draw()

        nav_bar_frame = ttk.Frame(left_frame)
        nav_bar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        NavigationToolbar2Tk(self.canvas_map, nav_bar_frame).update()

        self.canvas_map.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # ── Middle/Right: Pareto figure + control panel ──────────────────
        right_paned = ttk.PanedWindow(paned, orient=tk.VERTICAL)
        paned.add(right_paned, weight=4)

        # Pareto plot frame
        pareto_frame = ttk.Frame(right_paned)
        right_paned.add(pareto_frame, weight=6)

        self.fig_pareto = Figure(figsize=(6, 5), dpi=95)
        self.ax_pareto  = self.fig_pareto.add_subplot(111)

        self.canvas_pareto = FigureCanvasTkAgg(self.fig_pareto, master=pareto_frame)
        self.canvas_pareto.draw()
        self.canvas_pareto.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.pareto_plot = ParetoPlot(self.ax_pareto, on_click=self._on_pareto_click)

        # Control/info panel
        ctrl_frame = ttk.Frame(right_paned)
        right_paned.add(ctrl_frame, weight=4)
        self._build_control_panel(ctrl_frame)

    def _build_control_panel(self, parent: ttk.Frame):
        # ── Quick jump buttons ──────────────────────────────────────────
        jump_frame = ttk.LabelFrame(parent, text="Jump to")
        jump_frame.pack(fill=tk.X, padx=5, pady=4)

        row1 = ttk.Frame(jump_frame)
        row1.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(row1, text="Best Z1", command=lambda: self._jump_best("Z1")).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(row1, text="Best Z2", command=lambda: self._jump_best("Z2")).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        row2 = ttk.Frame(jump_frame)
        row2.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(row2, text="Compromise (min-dist to utopia)",
                   command=self._jump_compromise).pack(fill=tk.X, padx=2)

        # ── Layer toggles ───────────────────────────────────────────────
        layer_frame = ttk.LabelFrame(parent, text="Map layers")
        layer_frame.pack(fill=tk.X, padx=5, pady=4)
        ttk.Checkbutton(layer_frame, text="Node labels",
                        variable=self.var_show_labels,
                        command=self._refresh_map).pack(anchor=tk.W, padx=5, pady=1)
        ttk.Checkbutton(layer_frame, text="Allocation spokes",
                        variable=self.var_show_alloc,
                        command=self._refresh_map).pack(anchor=tk.W, padx=5, pady=1)
        ttk.Checkbutton(layer_frame, text="Colour by transport mode",
                        variable=self.var_show_mode_col,
                        command=self._refresh_map).pack(anchor=tk.W, padx=5, pady=1)

        # ── Solution info ───────────────────────────────────────────────
        info_frame = ttk.LabelFrame(parent, text="Current solution")
        info_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=4)

        self.txt_info = tk.Text(info_frame, height=14, width=38,
                                state=tk.DISABLED, wrap=tk.NONE,
                                font=("Consolas", 9))
        scroll = ttk.Scrollbar(info_frame, command=self.txt_info.yview)
        self.txt_info.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_info.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)

        # ── Save image ──────────────────────────────────────────────────
        save_frame = ttk.LabelFrame(parent, text="Save map")
        save_frame.pack(fill=tk.X, padx=5, pady=4)
        self.entry_save = ttk.Entry(save_frame)
        self.entry_save.insert(0, "solution_map.png")
        self.entry_save.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(save_frame, text="Save (Ctrl+S)",
                   command=self._save_map).pack(fill=tk.X, padx=5, pady=2)

    def _build_status_bar(self):
        self.lbl_status = ttk.Label(self.root, text="Ready.", anchor=tk.W,
                                    relief=tk.SUNKEN)
        self.lbl_status.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=2)

    # ════════════════════════════════════════════════════════════════════════
    # File / folder loading
    # ════════════════════════════════════════════════════════════════════════

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select solver output JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(_REPO_ROOT / "results"),
        )
        if path:
            self.entry_file.delete(0, tk.END)
            self.entry_file.insert(0, path)
            self._load_file(path)

    def _browse_folder(self):
        folder = filedialog.askdirectory(
            title="Select results folder",
            initialdir=str(_REPO_ROOT / "results"),
        )
        if folder:
            self.entry_file.delete(0, tk.END)
            self.entry_file.insert(0, folder)
            self._load_folder(folder)

    def _browse_instance(self):
        path = filedialog.askopenfilename(
            title="Select instance (DRND) JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(_REPO_ROOT / "data"),
        )
        if path:
            self._load_instance(path)

    def _load_from_entry(self):
        path = self.entry_file.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("Error", "Path does not exist.")
            return
        if os.path.isdir(path):
            self._load_folder(path)
        else:
            self._load_file(path)

    def _load_file(self, path: str):
        self._status(f"Loading {os.path.basename(path)}…")
        self.root.update_idletasks()
        try:
            result = load_result(path)
            self.all_results = [result]
            self._auto_load_instance(path)
            self._update_algo_combo()
            self._apply_filter()
            self._status(
                f"Loaded  {len(result.pareto_front)} PF  +  "
                f"{len(result.all_feasible)} all-feasible  "
                f"[{result.solver}]  —  {os.path.basename(path)}"
            )
        except Exception as exc:
            messagebox.showerror("Load error", str(exc))
            self._status(f"Error: {exc}")

    def _load_folder(self, folder: str):
        self._status(f"Scanning {folder}…")
        self.root.update_idletasks()
        try:
            results = load_results_from_folder(folder)
            if not results:
                messagebox.showwarning("Empty folder",
                                       "No valid JSON result files found.")
                return
            self.all_results = results
            self._auto_load_instance(results[0].filepath)
            self._update_algo_combo()
            self._apply_filter()
            total_pf = sum(len(r.pareto_front) for r in results)
            self._status(
                f"Loaded {len(results)} files — "
                f"{total_pf} Pareto solutions total  ·  "
                f"{os.path.basename(folder)}"
            )
        except Exception as exc:
            messagebox.showerror("Load error", str(exc))
            self._status(f"Error: {exc}")

    def _auto_load_instance(self, result_path: str):
        """Try to automatically find the matching instance JSON."""
        instance_path = _guess_instance_path(result_path)
        if instance_path and os.path.exists(instance_path):
            self._load_instance(instance_path)
        else:
            self._status("Instance not found — map view disabled. Use File → Load instance JSON…")

    def _load_instance(self, path: str):
        try:
            self.node_info = load_instance(path)
            self.renderer  = SolutionMapRenderer(self.node_info)
            self._status(f"Instance loaded: {os.path.basename(path)}  "
                         f"({self.node_info.num_nodes} nodes, "
                         f"{len(self.node_info.hub_indices)} hub candidates)")
        except Exception as exc:
            messagebox.showerror("Instance load error", str(exc))

    # ════════════════════════════════════════════════════════════════════════
    # Algorithm filter & solution list management
    # ════════════════════════════════════════════════════════════════════════

    def _update_algo_combo(self):
        solvers = sorted({r.solver for r in self.all_results})
        choices = ["All"] + solvers
        self.combo_algo["values"] = choices
        self.algo_filter.set("All")

    def _apply_filter(self):
        algo = self.algo_filter.get()
        pf_only = self.var_pf_only.get()

        filtered_results = (
            self.all_results
            if algo == "All"
            else [r for r in self.all_results if r.solver == algo]
        )

        sols: List[Solution] = []
        for r in filtered_results:
            if pf_only:
                sols.extend(r.pareto_front)
            else:
                # All feasible, Pareto marked distinctly
                sols.extend(r.all_feasible if r.all_feasible else r.pareto_front)

        self.display_solutions = sols
        self.current_idx = 0
        self._refresh_pareto()
        self._update_nav_label()
        if sols:
            self._show_solution(0)

    def _reset_filter(self):
        self.algo_filter.set("All")
        self.var_pf_only.set(False)
        self._apply_filter()

    # ════════════════════════════════════════════════════════════════════════
    # Navigation
    # ════════════════════════════════════════════════════════════════════════

    def _prev(self):
        if not self.display_solutions:
            return
        self.current_idx = (self.current_idx - 1) % len(self.display_solutions)
        self._show_solution(self.current_idx)

    def _next(self):
        if not self.display_solutions:
            return
        self.current_idx = (self.current_idx + 1) % len(self.display_solutions)
        self._show_solution(self.current_idx)

    def _jump(self):
        try:
            idx = int(self.entry_jump.get().strip()) - 1  # 1-based user input
            if not (0 <= idx < len(self.display_solutions)):
                raise ValueError(f"Out of range 1–{len(self.display_solutions)}")
            self.current_idx = idx
            self._show_solution(idx)
        except ValueError as exc:
            messagebox.showwarning("Invalid index", str(exc))

    def _jump_best(self, objective: str):
        if not self.display_solutions:
            return
        sols = self.display_solutions
        if objective == "Z1":
            idx = min(range(len(sols)), key=lambda i: sols[i].Z1)
        else:
            idx = min(range(len(sols)), key=lambda i: sols[i].Z2)
        self.current_idx = idx
        self._show_solution(idx)

    def _jump_compromise(self):
        """Navigate to the solution closest to the utopia point (normalised)."""
        if not self.display_solutions:
            return
        sols = self.display_solutions
        z1s = [s.Z1 for s in sols]
        z2s = [s.Z2 for s in sols]
        z1_min, z1_rng = min(z1s), max(z1s) - min(z1s) or 1.0
        z2_min, z2_rng = min(z2s), max(z2s) - min(z2s) or 1.0

        def dist(s: Solution) -> float:
            return ((s.Z1 - z1_min) / z1_rng) ** 2 + ((s.Z2 - z2_min) / z2_rng) ** 2

        idx = min(range(len(sols)), key=lambda i: dist(sols[i]))
        self.current_idx = idx
        self._show_solution(idx)

    def _on_pareto_click(self, sol_idx: int):
        """Called when user clicks a scatter point on the Pareto plot."""
        if 0 <= sol_idx < len(self.display_solutions):
            self.current_idx = sol_idx
            self._update_nav_label()
            sol = self.display_solutions[sol_idx]
            self._refresh_map_for(sol)
            self._update_info_panel(sol, sol_idx)

    # ════════════════════════════════════════════════════════════════════════
    # Rendering
    # ════════════════════════════════════════════════════════════════════════

    def _show_solution(self, idx: int):
        if not self.display_solutions:
            return
        sol = self.display_solutions[idx]
        self.current_idx = idx
        self._update_nav_label()
        self._refresh_map_for(sol)
        self._update_info_panel(sol, idx)
        self.pareto_plot.select(idx)
        self.canvas_pareto.draw_idle()

    def _refresh_map_for(self, sol: Solution):
        if self.renderer is None:
            self.ax_map.cla()
            self.ax_map.text(0.5, 0.5, "No instance loaded.\n"
                             "Use  File → Load instance JSON…",
                             ha="center", va="center",
                             transform=self.ax_map.transAxes, fontsize=12)
            self.canvas_map.draw_idle()
            return

        self.renderer.render(
            self.ax_map, sol,
            show_labels=self.var_show_labels.get(),
            show_alloc=self.var_show_alloc.get(),
            show_mode_colour=self.var_show_mode_col.get(),
        )
        self.fig_map.tight_layout()
        self.canvas_map.draw_idle()

    def _refresh_map(self):
        if not self.display_solutions:
            return
        sol = self.display_solutions[self.current_idx]
        self._refresh_map_for(sol)

    def _refresh_pareto(self):
        """Redraw the Pareto scatter from current display_solutions."""
        algo = self.algo_filter.get()

        if not self.all_results:
            self.ax_pareto.cla()
            self.canvas_pareto.draw_idle()
            return

        if algo != "All" and len(self.all_results) > 0:
            # Single-algorithm view: use first matching result for rich scatter
            matching = [r for r in self.all_results if r.solver == algo]
            if matching:
                self.pareto_plot.plot_single(
                    matching[0],
                    show_all_feasible=self.var_show_feasible.get(),
                )
            else:
                self._refresh_pareto_multi()
        else:
            self._refresh_pareto_multi()

        self.fig_pareto.tight_layout()
        self.canvas_pareto.draw_idle()

    def _refresh_pareto_multi(self):
        """Multi-algorithm Pareto scatter."""
        from visualizer.pareto_plot import ParetoPlot
        groups: Dict[str, List[Solution]] = {}
        for r in self.all_results:
            key = f"{r.solver}  s={r.seed}"
            groups.setdefault(key, []).extend(r.pareto_front)
        self.pareto_plot.plot_multi(groups)

    # ════════════════════════════════════════════════════════════════════════
    # Info panel
    # ════════════════════════════════════════════════════════════════════════

    def _update_info_panel(self, sol: Solution, idx: int):
        lines = [
            f"Index  : {idx + 1} / {len(self.display_solutions)}",
            f"Source : {sol.source}",
            f"Rank   : {sol.rank}   CV={sol.CV:.4f}",
            "",
            f"Z1 (cost)      : {sol.Z1:>15,.2f}",
            f"Z2 (depriv.)   : {sol.Z2:>15,.2f}",
            "",
            f"Open hubs ({sol.num_open_hubs}): {sol.open_hubs}",
            "",
            "X (hub config) :",
            f"  {sol.X}",
            "",
            "R (inventory ratio) :",
        ]
        for k, r in enumerate(sol.R):
            lines.append(f"  hub[{k}] = {r:.4f}")
        lines += ["", "A (transport mode per demand) :"]
        mode_names = {0: "road", 1: "water", 2: "air"}
        for i, a in enumerate(sol.A):
            lines.append(f"  demand[{i}] = {a} ({mode_names.get(a, '?')})")

        if self.node_info:
            lines += ["", "Open hub names:"]
            for k in sol.open_hubs:
                if k < len(self.node_info.hub_indices):
                    g = self.node_info.hub_indices[k]
                    name = (self.node_info.names[g]
                            if g < len(self.node_info.names) else f"node {g}")
                    lines.append(f"  [{k}] {name}")

        text = "\n".join(lines)
        self.txt_info.configure(state=tk.NORMAL)
        self.txt_info.delete("1.0", tk.END)
        self.txt_info.insert(tk.END, text)
        self.txt_info.configure(state=tk.DISABLED)

    # ════════════════════════════════════════════════════════════════════════
    # Save
    # ════════════════════════════════════════════════════════════════════════

    def _save_map(self):
        path = self.entry_save.get().strip() or "solution_map.png"
        path = filedialog.asksaveasfilename(
            title="Save map image",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg")],
            initialfile=path,
        )
        if not path:
            return
        try:
            self.fig_map.savefig(path, dpi=150, bbox_inches="tight")
            self._status(f"Map saved → {path}")
        except Exception as exc:
            messagebox.showerror("Save error", str(exc))

    # ════════════════════════════════════════════════════════════════════════
    # Helpers
    # ════════════════════════════════════════════════════════════════════════

    def _update_nav_label(self):
        total = len(self.display_solutions)
        idx   = self.current_idx
        self.lbl_idx.config(text=f"{idx + 1:>4}  /  {total}" if total else "—  /  —")

    def _status(self, msg: str):
        self.lbl_status.config(text=msg)
        self.root.update_idletasks()


# ════════════════════════════════════════════════════════════════════════════
# Instance path inference
# ════════════════════════════════════════════════════════════════════════════

def _guess_instance_path(result_path: str) -> Optional[str]:
    """
    Given a result JSON path, try to find the corresponding instance JSON.

    E.g.  results/exp1/AP10_seed0.json  →  data/benchmark/AP10_seed42_drnd.json
    """
    stem = Path(result_path).stem        # e.g. "AP10_seed0"
    # Extract instance name prefix (AP10, AP20, AP50, TR81, cv_small, ...)
    import re
    m = re.match(r"(AP\d+|TR\d+|cv_\w+)", stem, re.IGNORECASE)
    if not m:
        return None

    prefix = m.group(1)
    repo = _REPO_ROOT

    # Search data/benchmark first, then data/cv, data/hlp
    for data_dir in ["data/benchmark", "data/cv", "data/hlp"]:
        folder = repo / data_dir
        if not folder.exists():
            continue
        # Try exact file name variations
        candidates = [
            folder / f"{prefix}_seed42_drnd.json",
            folder / f"{prefix}_drnd.json",
        ]
        for c in candidates:
            if c.exists():
                return str(c)

        # Glob fallback  (first match wins)
        hits = list(folder.glob(f"{prefix}*.json"))
        if hits:
            return str(hits[0])

    return None
