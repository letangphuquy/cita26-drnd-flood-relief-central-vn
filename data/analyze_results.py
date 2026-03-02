"""
analyze_results.py
==================
Parses PB-NSGA-II solver output JSONs and generates:
  - Pareto front scatter plots (Z1 vs Z2)
  - Hypervolume (HV) and IGD+ metrics table
  - Summary CSV of all runs

Usage:
  python data/analyze_results.py results/          # analyze all .json in folder
  python data/analyze_results.py results/CV_small_seed0.json   # single file

Outputs to results/figures/ directory.
"""

import os
import sys
import json
import math
import csv

try:
    import matplotlib
    matplotlib.use('Agg')  # non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("[Warning] matplotlib not installed. Plots will be skipped.")

# ---------------------------------------------------------------------------
# Pareto front metrics
# ---------------------------------------------------------------------------
def hypervolume_2d(pareto, ref_point):
    """
    2D hypervolume indicator.
    ref_point = (ref_z1, ref_z2) — must dominate all solutions.
    """
    if not pareto:
        return 0.0
    # Sort by Z1 ascending
    pts = sorted(pareto, key=lambda p: p[0])
    hv = 0.0
    prev_z2 = ref_point[1]
    for z1, z2 in pts:
        width  = ref_point[0] - z1
        height = prev_z2 - z2
        if width > 0 and height > 0:
            hv += width * height
        prev_z2 = min(prev_z2, z2)
    return hv


def igd_plus(approx_front, true_front):
    """
    IGD+ (modified Inverted Generational Distance).
    Measures quality of approx_front w.r.t. a reference true_front.
    If true_front is unknown, use the combined Pareto of all runs.
    """
    if not true_front or not approx_front:
        return float('inf')
    total = 0.0
    for (rz1, rz2) in true_front:
        best = min(
            math.hypot(max(az1 - rz1, 0), max(az2 - rz2, 0))
            for az1, az2 in approx_front
        )
        total += best ** 2
    return math.sqrt(total / len(true_front))


def load_pareto(path):
    """Load Pareto front from solver output JSON."""
    with open(path) as f:
        data = json.load(f)
    pts = []
    for sol in data.get("pareto_front", []):
        if sol["CV"] == 0:  # only feasible solutions
            pts.append((sol["Z1"], sol["Z2"]))
    return pts, data


def dominant_pareto(all_runs_pts):
    """Compute combined Pareto front from multiple runs (to serve as reference)."""
    all_pts = [p for run in all_runs_pts for p in run]
    nondom = []
    for p in all_pts:
        dominated = False
        for q in all_pts:
            if q[0] <= p[0] and q[1] <= p[1] and (q[0] < p[0] or q[1] < p[1]):
                dominated = True
                break
        if not dominated:
            nondom.append(p)
    return sorted(nondom, key=lambda p: p[0])


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']

def plot_pareto_front(results_dict, out_path, title="Pareto Front"):
    """
    results_dict: {label: [(Z1, Z2), ...], ...}
    """
    if not HAS_MPL:
        return
    fig, ax = plt.subplots(figsize=(7, 5))
    for idx, (label, pts) in enumerate(results_dict.items()):
        if not pts:
            continue
        pts_sorted = sorted(pts, key=lambda p: p[0])
        z1s = [p[0] for p in pts_sorted]
        z2s = [p[1] for p in pts_sorted]
        color = COLORS[idx % len(COLORS)]
        ax.plot(z1s, z2s, 'o-', color=color, label=label, markersize=5, alpha=0.85)

        # Highlight knee point (min distance to ideal)
        if len(pts_sorted) >= 3:
            min_z1 = min(z1s); max_z1 = max(z1s)
            min_z2 = min(z2s); max_z2 = max(z2s)
            range_z1 = max_z1 - min_z1 + 1e-9
            range_z2 = max_z2 - min_z2 + 1e-9
            dists = [math.hypot((z1 - min_z1)/range_z1, (z2 - min_z2)/range_z2)
                     for z1, z2 in pts_sorted]
            knee_idx = dists.index(max(dists))
            ax.scatter([z1s[knee_idx]], [z2s[knee_idx]],
                       marker='*', s=200, color=color, zorder=5,
                       label=f"{label} (knee)")

    ax.set_xlabel("$Z_1$ — Expected Logistics Cost", fontsize=12)
    ax.set_ylabel("$Z_2$ — Expected Max Deprivation Cost", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.legend(fontsize=9, loc='upper right')
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  [Plot] Saved: {out_path}")


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
def analyze_folder(results_dir):
    fig_dir = os.path.join(results_dir, "figures")
    os.makedirs(fig_dir, exist_ok=True)

    all_jsons = [f for f in os.listdir(results_dir) if f.endswith(".json")]
    if not all_jsons:
        print(f"No JSON result files found in {results_dir}")
        return

    summary_rows = []
    # Group by prefix (experiment)
    groups = {}
    for fname in sorted(all_jsons):
        base = fname.replace(".json", "")
        # Group: AP10, AP20, ..., TR81, CV_small, CV_large
        if   base.startswith("AP"):    grp = base[:base.rindex("_")] if "_" in base else base
        elif base.startswith("TR"):    grp = "TR81"
        elif base.startswith("CV"):    grp = "_".join(base.split("_")[:2])
        else:                          grp = "other"
        groups.setdefault(grp, []).append(fname)

    # ── Experiment 1: AP / TR benchmark plots ─────────────────────────────
    bench_summary = {}
    for grp, files in sorted(groups.items()):
        if not grp.startswith("AP") and grp != "TR81":
            continue
        pts_list = []
        for fname in files:
            pts, _ = load_pareto(os.path.join(results_dir, fname))
            pts_list.append(pts)

        all_pts = [p for run in pts_list for p in run]
        combined = dominant_pareto(pts_list) if pts_list else []

        # Reference point = 1.2× the max values
        if all_pts:
            ref = (max(p[0] for p in all_pts) * 1.2,
                   max(p[1] for p in all_pts) * 1.2)
            hv = hypervolume_2d(combined, ref)
        else:
            hv = 0.0

        bench_summary[grp] = {
            "pareto_size": len(combined),
            "hypervolume": hv,
        }
        summary_rows.append({
            "experiment": f"Benchmark ({grp})",
            "files": len(files),
            "pareto_size": len(combined),
            "hypervolume": f"{hv:.4e}",
        })
        print(f"  [{grp}] Pareto pts: {len(combined)}, HV: {hv:.3e}")

        if combined:
            plot_pareto_front(
                {grp: combined},
                os.path.join(fig_dir, f"{grp}_pareto.pdf"),
                title=f"Pareto Front — {grp} Benchmark"
            )

    # ── Experiment 2: Central Vietnam case study ───────────────────────────
    for grp, files in sorted(groups.items()):
        if not grp.startswith("CV"):
            continue
        runs_pts = {}
        for fname in files:
            pts, _ = load_pareto(os.path.join(results_dir, fname))
            seed = fname.split("seed")[-1].replace(".json", "")
            runs_pts[f"Seed {seed}"] = pts

        all_pts_flat = [p for run in runs_pts.values() for p in run]
        combined = dominant_pareto(list(runs_pts.values())) if all_pts_flat else []

        if all_pts_flat:
            ref = (max(p[0] for p in all_pts_flat) * 1.2,
                   max(p[1] for p in all_pts_flat) * 1.2)
            hv_combined = hypervolume_2d(combined, ref)
            hv_per_run = {k: hypervolume_2d(v, ref) for k, v in runs_pts.items()}
        else:
            hv_combined = 0.0; hv_per_run = {}

        # IGD+ across seeds (reference = combined Pareto)
        igd_per_run = {}
        for k, pts in runs_pts.items():
            igd_per_run[k] = igd_plus(pts, combined)

        summary_rows.append({
            "experiment": f"Case Study ({grp})",
            "files": len(files),
            "pareto_size": len(combined),
            "hypervolume": f"{hv_combined:.4e}",
        })
        print(f"  [{grp}] Combined Pareto: {len(combined)} pts, HV: {hv_combined:.3e}")
        for k in runs_pts:
            print(f"    {k}: HV={hv_per_run.get(k,0):.3e}, IGD+={igd_per_run.get(k,0):.4f}")

        if combined or runs_pts:
            plot_dict = {"Combined": combined, **runs_pts} if combined else runs_pts
            plot_pareto_front(
                plot_dict,
                os.path.join(fig_dir, f"{grp}_pareto.pdf"),
                title=f"Pareto Front — Central Vietnam ({grp})"
            )

    # ── Save summary CSV ───────────────────────────────────────────────────
    csv_path = os.path.join(results_dir, "summary.csv")
    if summary_rows:
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
            writer.writeheader()
            writer.writerows(summary_rows)
        print(f"  [Summary] Saved: {csv_path}")

    print(f"\nAnalysis complete. Figures in: {fig_dir}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "results"
    if os.path.isfile(target):
        pts, _ = load_pareto(target)
        print(f"Pareto front: {len(pts)} feasible solutions")
        for z1, z2 in sorted(pts):
            print(f"  Z1={z1:.2f}  Z2={z2:.2f}")
    elif os.path.isdir(target):
        analyze_folder(target)
    else:
        print(f"Path not found: {target}")
