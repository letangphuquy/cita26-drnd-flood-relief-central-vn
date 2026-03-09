# CITA Solution Visualizer — User Guide

A sub-module for browsing and visualizing solver outputs (Pareto fronts, hub maps, solution tables) produced by the MO-IHLNDP/CITA algorithms.

---

## Prerequisites

Install dependencies from the project root (uses the main `requirements.txt`):

```powershell
pip install -r requirements.txt
```

Required packages: `matplotlib`, `numpy`, `tkinter` (stdlib on most Python distros).

---

## Directory Structure

```
src/visualizer/
├── main.py              # CLI entry-point / GUI launcher
├── solution_loader.py   # JSON parsing → dataclasses
├── map_renderer.py      # Per-solution node-map renderer
├── pareto_plot.py       # Pareto scatter / comparison plot
├── gui/
│   ├── app.py           # Tkinter interactive GUI
│   └── __init__.py
└── GUIDE.md             # ← this file
```

---

## Quick Start

All commands are run from the **project root** (`CITA_paper/`).

### Launch the interactive GUI

```powershell
python -m src.visualizer.main
```

A window opens with a file browser. You can also pre-load a file:

```powershell
python -m src.visualizer.main --file results/exp1/out_AP10.json
```

---

## GUI Walkthrough

```
┌─────────────────────────────────────────────────────────┐
│  File: [results/exp1/out_AP10.json      ] [Browse] [Load]│
│  Instance: [data/benchmark/AP10_seed42…] [Browse] [Load] │
├──────────────────┬──────────────────────────────────────┤
│  Solution list   │  Tab 1: Pareto Plot                  │
│  (left panel)    │  Tab 2: Solution Map                 │
│                  │  Tab 3: Solution Details             │
│  ● sol #1  PF    │                                      │
│    Z1=12345  …   │  [Export Map]  [Export Pareto]       │
│  ○ sol #2  PF    │                                      │
└──────────────────┴──────────────────────────────────────┘
```

**Steps:**

1. **Load a result file** — click *Browse* next to "File", select any `*.json` output from `results/`.
2. **Load an instance file** *(optional, needed for map rendering)* — click *Browse* next to "Instance", select the matching `data/benchmark/*.json`. The app attempts **auto-detection** by matching the filename prefix.
3. **Select a solution** from the left panel. It is highlighted in the Pareto plot.
4. Switch to the **Map** tab to see hub placement and demand-node assignments on the geographic layout.
5. Switch to **Details** for the full `X`, `R`, `A`, `W` vectors and objective values.

---

## CLI Mode

Add `--cli` to skip the GUI entirely, useful for scripting or headless servers.

### List all solutions in a file

```powershell
python -m src.visualizer.main --cli `
    --file results/exp1/out_AP10.json `
    --list
```

Output:

```
============================================================
File   : results/exp1/out_AP10.json
Solver : PBNSGA   seed=42
============================================================

Pareto front  (8 solutions)
  Idx               Z1               Z2      CV  rank   hubs
------------------------------------------------------------
    1      1,234,567.0        98,765.0   0.000     1  01101
    2      1,190,000.0       115,200.0   0.000     1  01001
    ...
```

Add `--feasible` to also print the `all_feasible` pool.

### Export a solution map image

```powershell
python -m src.visualizer.main --cli `
    --file results/exp1/out_AP10.json `
    --instance data/benchmark/AP10_seed42_drnd.json `
    --index 2 `
    --out figures/solution_AP10_idx2.png
```

- `--index` is **1-based**.
- Output format is inferred from the file extension (`.png`, `.pdf`, `.svg`).

### Pareto-front comparison across a folder

Generates a single overlay plot for all JSON files found in a folder:

```powershell
python -m src.visualizer.main --cli `
    --folder results/exp1 `
    --compare `
    --out figures/pareto_exp1.pdf
```

Each solver / seed gets a distinct colour automatically.

---

## Result JSON Format (reference)

The loader expects the standard CITA output schema:

```jsonc
{
  "meta": { "solver": "PBNSGA", "seed": 42, "elapsed_s": 123.4 },
  "pareto_front": [
    {
      "Z1": 1234567.0, "Z2": 98765.0, "CV": 0.0,
      "rank": 1, "crowding": 0.85,
      "X": [0,1,1,0,1],        // hub open/close vector
      "R": [0.0, 0.6, 0.4, 0.0, 0.8],  // inventory ratios
      "A": [1,2,1,1,3,...],    // transport-mode per demand node
      "W": [0.3, 0.1, ...]     // decoder weights
    }
  ],
  "all_feasible": [ ... ]
}
```

---

## Instance JSON Format (reference)

Matches the DRND benchmark files under `data/benchmark/`:

```jsonc
{
  "nodes": [
    { "id": 0, "name": "Node A", "x": 10.5, "y": 20.3,
      "type": "demand" },
    ...
  ],
  "hub_candidates": [0, 2, 4],
  "origins": [7]
}
```

If the instance file is unavailable, the GUI/CLI will render the map with **ordinal node indices** and no geographic coordinates.

---

## Keyboard Shortcuts (GUI)

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate solution list |
| `Ctrl+O` | Open result file |
| `Ctrl+I` | Open instance file |
| `Ctrl+E` | Export current view |
| `Ctrl+Q` | Quit |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `No module named 'visualizer'` | Running from wrong directory | Run from `CITA_paper/` root |
| Map shows no coordinates | Instance file not loaded | Load the matching `data/benchmark/*.json` |
| Blank Pareto plot | Result has no `pareto_front` entries | Check `all_feasible` via `--feasible` flag |
| `TclError: no display` (Linux) | Headless environment | Use `--cli` mode |
