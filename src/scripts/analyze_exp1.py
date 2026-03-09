"""
analyze_exp1.py — Experiment 1: Algorithm Benchmarking
=======================================================
Compares PB-NSGA against complete enumeration (BB exact solver) on
HLP-derived benchmark instances (AP10/20/25/40/50/100, TR81).

Two outputs:
  1. exp1_metrics.csv    — per-instance per-algorithm: HV, IGD+, front size, runtime
  2. exp1_timing.csv     — stress-test table: mean runtime vs. instance size
  3. results/exp1/figures/<group>_pareto.pdf  — Pareto comparison plots

Optimality verification: for AP10/20/25/40 and CV-Small (where BB exact is
available), IGD+ of PB-NSGA vs combined BB+PBNSGA front measures proximity
to the true Pareto front.

Usage:
  python scripts/analyze_exp1.py                   # auto-discovers results/exp1/
  python scripts/analyze_exp1.py <results_dir>
"""

import os
import sys
import json
import math
import csv
import statistics

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("[Warning] matplotlib not available — plots skipped.")


# ---------------------------------------------------------------------------
# Metric helpers (self-contained; no shared module dependency)
# ---------------------------------------------------------------------------

def load_result(path):
    with open(path) as fh:
        data = json.load(fh)
    raw_pts = [
        (sol["Z1"], sol["Z2"])
        for sol in data.get("pareto_front", [])
        if sol.get("CV", 0) == 0
    ]
    # De-duplicate
    unique = {}
    for p in raw_pts:
        k = (round(p[0], 6), round(p[1], 6))
        if k not in unique:
            unique[k] = p
    pts = list(unique.values())
    return pts, data.get("meta", {})


def dominant_pareto(runs_pts):
    all_pts = [p for run in runs_pts for p in run]
    nondom = []
    for p in all_pts:
        if not any(
            q[0] <= p[0] and q[1] <= p[1] and (q[0] < p[0] or q[1] < p[1])
            for q in all_pts
        ):
            nondom.append(p)
    return sorted(set(nondom), key=lambda p: p[0])


def normalize_points(pts_list, bounds=None):
    all_pts = [p for run in pts_list for p in run]
    if not all_pts:
        return pts_list, (0.0, 1.0, 0.0, 1.0)
    if bounds is None:
        z1_min = min(p[0] for p in all_pts)
        z1_max = max(p[0] for p in all_pts)
        z2_min = min(p[1] for p in all_pts)
        z2_max = max(p[1] for p in all_pts)
    else:
        z1_min, z1_max, z2_min, z2_max = bounds
    rz1 = max(z1_max - z1_min, 1e-12)
    rz2 = max(z2_max - z2_min, 1e-12)
    normed = [[(( p[0]-z1_min)/rz1, (p[1]-z2_min)/rz2) for p in run]
              for run in pts_list]
    return normed, (z1_min, z1_max, z2_min, z2_max)


def hypervolume_2d(pareto, ref=(1.1, 1.1)):
    """2D hypervolume indicator (Zitzler & Thiele, 1999)."""
    if not pareto:
        return 0.0
    pts = sorted(pareto, key=lambda p: p[0])
    hv, prev_z2 = 0.0, ref[1]
    for z1, z2 in pts:
        w = ref[0] - z1
        h = prev_z2 - z2
        if w > 0 and h > 0:
            hv += w * h
        prev_z2 = min(prev_z2, z2)
    return hv


def igd_plus(approx, reference):
    """IGD+ (Ishibuchi et al., 2015). Both args must be normalised."""
    if not reference or not approx:
        return float("inf")
    total = sum(
        min(math.hypot(max(az1 - rz1, 0), max(az2 - rz2, 0)) ** 2
            for az1, az2 in approx)
        for rz1, rz2 in reference
    )
    return math.sqrt(total / len(reference))


def _mean_std(vals):
    if not vals:
        return float("nan"), float("nan")
    import numpy as np
    return float(np.mean(vals)), float(np.std(vals, ddof=1) if len(vals) > 1 else 0.0)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

# Instance ordering for stress-test table
_BENCH_ORDER = ["AP10", "AP20", "AP25", "AP40", "AP50", "AP100", "TR81"]

# Approximate number of nodes for each instance (used in timing table)
_INST_SIZE = {
    "AP10": 10, "AP20": 20, "AP25": 25, "AP40": 40,
    "AP50": 50, "AP100": 100, "TR81": 81,
}


def discover_benchmark_files(results_dir):
    """
    Returns {group: {algo: [(seed_str, path)]}} for benchmark instances.
    Recognises:
      AP{n}_seed{s}.json   → (AP{n}, PB-NSGA, s)
      TR81_seed{s}.json    → (TR81,  PB-NSGA, s)
      AP{n}_bb.json        → (AP{n}, BB-Exact, 0)
      TR81_bb.json         → (TR81,  BB-Exact, 0)
      cv_small_milp_aws.json → (cv_small, MILP-AWS, 0)
      cv_small_milp.json    → (cv_small, MILP-Exact, 0)
      cv_small_bb.json      → (cv_small, BB-Exact, 0)
      cv_small_greedy.json  → (cv_small, Greedy, 0)
      cv_small_pb_nsga.json → (cv_small, PB-NSGA, 0)
    """
    groups = {}
    for fname in sorted(os.listdir(results_dir)):
        if not fname.endswith(".json"):
            continue
        base = fname[:-5]
        grp = algo = seed = None

        if "_seed" in base:
            grp, seed = base.split("_seed", 1)
            algo = "PB-NSGA"
        elif base.endswith("_bb"):
            grp, algo, seed = base[:-3], "BB-Exact", "0"
        elif base.endswith("_milp_aws"):
            grp, algo, seed = base[:-9], "MILP-AWS", "0"
        elif base.endswith("_milp"):
            grp, algo, seed = base[:-5], "MILP-Exact", "0"
        elif base.endswith("_aws"):
            grp, algo, seed = base[:-4], "MILP-AWS", "0"
        elif base.endswith("_greedy"):
            grp, algo, seed = base[:-7], "Greedy", "0"
        elif base.endswith("_pb_nsga"):
             grp, algo, seed = base[:-8], "PB-NSGA", "0"
        elif base.endswith("_result"):
             grp, algo, seed = base[:-7], "PB-NSGA", "0"

        if grp is None:
            continue
        
        # Harmonize CV prefix
        if grp.startswith("cv_small"):
            grp = "cv_small"
        elif grp.startswith("cv_large"):
            grp = "cv_large"

        path = os.path.join(results_dir, fname)
        groups.setdefault(grp, {}).setdefault(algo, []).append((seed, path))
    return groups


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

_STYLE = {
    "PB-NSGA":              dict(color="#1f77b4", marker="o", lw=1.8, ls="-"),
    "BB-Exact":             dict(color="#d62728", marker="D", lw=2.0, ls="-"),
    "MILP-AWS":             dict(color="#2ca02c", marker="s", lw=1.8, ls="--"),
    "Greedy":               dict(color="#9467bd", marker="^", lw=1.5, ls=":"),
    "PB-NSGA (combined)":   dict(color="#1f77b4", marker="o", lw=1.8, ls="-"),
}


def plot_pareto_comparison(series_dict, out_path, title):
    if not HAS_MPL or not series_dict:
        return
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for label, pts in series_dict.items():
        if not pts:
            continue
        pts_s = sorted(pts, key=lambda p: p[0])
        z1s = [p[0] for p in pts_s]
        z2s = [p[1] for p in pts_s]
        st = dict(_STYLE.get(label, dict(color="#7f7f7f", marker="o", lw=1.5)))
        ax.plot(z1s, z2s,
                color=st["color"], marker=st["marker"],
                linewidth=st["lw"], linestyle=st.get("ls", "-"),
                markersize=5, alpha=0.85, label=label)
        # Mark knee point (furthest from ideal in normalised space)
        if len(pts_s) >= 3:
            mn1, mx1 = min(z1s), max(z1s)
            mn2, mx2 = min(z2s), max(z2s)
            r1 = max(mx1 - mn1, 1e-9)
            r2 = max(mx2 - mn2, 1e-9)
            dists = [math.hypot((z1 - mn1)/r1, (z2 - mn2)/r2)
                     for z1, z2 in pts_s]
            ki = dists.index(max(dists))
            ax.scatter([z1s[ki]], [z2s[ki]], marker="*", s=180,
                       color=st["color"], zorder=5)

    ax.set_xlabel("$Z_1$ — Expected Logistics Cost", fontsize=11)
    ax.set_ylabel("$Z_2$ — Expected Max Deprivation", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [Plot] {out_path}")


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def run(results_dir, out_dir):
    fig_dir = os.path.join(out_dir, "figures")
    os.makedirs(fig_dir, exist_ok=True)

    groups = discover_benchmark_files(results_dir)
    if not groups:
        print(f"[Exp1] No benchmark result files found in {results_dir}")
        return

    # Filter for relevant groups (primary focus on CV case study)
    relevant_only = True # Set to False to include AP/TR benchmarks
    if relevant_only:
        sorted_grps = [g for g in sorted(groups.keys()) if "cv_" in g.lower()]
        if not sorted_grps:
             sorted_grps = sorted(groups.keys()) # fallback
    else:
        sorted_grps = sorted(groups.keys(),
                             key=lambda g: _BENCH_ORDER.index(g)
                             if g in _BENCH_ORDER else (0 if "small" in g.lower() else 99))

    metrics_rows = []
    timing_rows  = []

    for grp in sorted_grps:
        algo_data = groups[grp]  # {algo: [(seed, path)]}

        # Load runs
        algo_runs = {}
        algo_meta = {}
        for algo in ["BB-Exact", "PB-NSGA", "MILP-Exact", "MILP-AWS", "Greedy"]:
            if algo not in algo_data:
                continue
            algo_runs[algo] = []
            algo_meta[algo] = []
            for seed, path in sorted(algo_data[algo], key=lambda x: x[0]):
                pts, meta = load_result(path)
                algo_runs[algo].append(pts)
                algo_meta[algo].append(meta)

        if not algo_runs:
            continue

        # Global normalisation bounds
        all_runs = [run for runs in algo_runs.values() for run in runs]
        _, bounds = normalize_points(all_runs)

        # Reference front for IGD+: combined non-dominated union of BB and PB-NSGA
        bb_runs  = algo_runs.get("BB-Exact", [])
        pb_runs  = algo_runs.get("PB-NSGA",  [])
        bb_front = dominant_pareto(bb_runs)  if bb_runs  else []
        pb_combined = dominant_pareto(pb_runs) if pb_runs else []

        all_ref = []
        if bb_front:     all_ref.append(bb_front)
        if pb_combined:  all_ref.append(pb_combined)
        ref_raw = dominant_pareto(all_ref) if all_ref else []
        ref_norm, _ = normalize_points([ref_raw], bounds=bounds)
        reference_norm = ref_norm[0] if ref_norm else []

        # Pareto comparison plot
        series = {}
        if bb_front:    series["BB-Exact"]            = bb_front
        if pb_combined: series["PB-NSGA (combined)"]  = pb_combined
        if "MILP-AWS" in algo_runs and algo_runs["MILP-AWS"]:
             series["MILP-AWS"] = dominant_pareto(algo_runs["MILP-AWS"])
        plot_pareto_comparison(
            series,
            os.path.join(fig_dir, f"{grp}_pareto.pdf"),
            title=f"Pareto Front — {grp}"
        )

        # Per-algorithm metrics
        for algo in ["BB-Exact", "PB-NSGA", "MILP-Exact", "MILP-AWS", "Greedy"]:
            if algo not in algo_runs:
                continue
            runs  = algo_runs[algo]
            metas = algo_meta[algo]
            norm_runs, _ = normalize_points(runs, bounds=bounds)
            ref_pt = (1.1, 1.1)

            hv_list, igd_list, size_list, rt_list, cpu_list = [], [], [], [], []
            for pts, norm_pts, meta in zip(runs, norm_runs, metas):
                hv_list.append(hypervolume_2d(norm_pts, ref_pt))
                igd_list.append(igd_plus(norm_pts, reference_norm))
                size_list.append(len(pts))
                # Wall time keys
                for key in ("elapsed_s", "runtime_s", "total_elapsed_s"):
                    if key in meta:
                        rt_list.append(float(meta[key]))
                        break
                # CPU time keys
                for key in ("cpu_time_s", "total_cpu_s"):
                    if key in meta:
                        cpu_list.append(float(meta[key]))
                        break

            hv_m,   hv_s   = _mean_std(hv_list)
            igd_m,  igd_s  = _mean_std(igd_list)
            sz_m,   sz_s   = _mean_std([float(s) for s in size_list])
            rt_m,   rt_s   = _mean_std(rt_list) if rt_list else (float("nan"), float("nan"))
            cpu_m,  cpu_s  = _mean_std(cpu_list) if cpu_list else (float("nan"), float("nan"))

            n_nodes = _INST_SIZE.get(grp, "?")
            print(f"  [{grp}|{n_nodes:3}] {algo:10s}  "
                  f"runs={len(runs)}  "
                  f"HV={hv_m:.4f}±{hv_s:.4f}  "
                  f"IGD+={igd_m:.4f}±{igd_s:.4f}"
                  + (f"  rt={rt_m:.1f}s" if rt_list else "")
                  + (f"  cpu={cpu_m:.1f}s" if cpu_list else ""))

            metrics_rows.append({
                "instance":       grp,
                "n_nodes":        n_nodes,
                "algorithm":      algo,
                "n_runs":         len(runs),
                "pareto_combined": len(dominant_pareto(runs)),
                "pareto_mean":    f"{sz_m:.1f}",
                "pareto_std":     f"{sz_s:.1f}",
                "HV_mean":        f"{hv_m:.6f}",
                "HV_std":         f"{hv_s:.6f}",
                "IGDplus_mean":   f"{igd_m:.6f}",
                "IGDplus_std":    f"{igd_s:.6f}",
                "runtime_s_mean": f"{rt_m:.2f}" if rt_list else "N/A",
                "runtime_s_std":  f"{rt_s:.2f}"  if rt_list else "N/A",
                "cpu_time_s_mean": f"{cpu_m:.2f}" if cpu_list else "N/A",
                "cpu_time_s_std":  f"{cpu_s:.2f}" if cpu_list else "N/A",
            })

            # Timing stress-test row (PB-NSGA only)
            if algo == "PB-NSGA" and rt_list:
                timing_rows.append({
                    "instance":      grp,
                    "n_nodes":       n_nodes,
                    "n_runs":        len(runs),
                    "rt_mean_s":     f"{rt_m:.2f}",
                    "rt_std_s":      f"{rt_s:.2f}",
                    "rt_min_s":      f"{min(rt_list):.2f}",
                    "rt_max_s":      f"{max(rt_list):.2f}",
                })

    # Write metrics CSV
    metrics_path = os.path.join(out_dir, "exp1_metrics.csv")
    _write_csv(metrics_rows, metrics_path, [
        "instance", "n_nodes", "algorithm", "n_runs",
        "pareto_combined", "pareto_mean", "pareto_std",
        "HV_mean", "HV_std", "IGDplus_mean", "IGDplus_std",
        "runtime_s_mean", "runtime_s_std",
        "cpu_time_s_mean", "cpu_time_s_std",
    ])

    # Write timing stress-test CSV (sorted by instance size)
    if timing_rows:
        timing_rows.sort(key=lambda r: int(r["n_nodes"]) if str(r["n_nodes"]).isdigit() else 99)
        timing_path = os.path.join(out_dir, "exp1_timing.csv")
        _write_csv(timing_rows, timing_path, [
            "instance", "n_nodes", "n_runs",
            "rt_mean_s", "rt_std_s", "rt_min_s", "rt_max_s",
        ])

    # Timing bar chart
    if timing_rows and HAS_MPL:
        _plot_timing(timing_rows, os.path.join(fig_dir, "timing_stresstest.pdf"))

    print(f"\n[Exp1] Done. Results -> {out_dir}")


def _write_csv(rows, path, fields):
    if not rows:
        return
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  [CSV] {path}")


def _plot_timing(timing_rows, out_path):
    labels = [r["instance"] for r in timing_rows]
    means  = [float(r["rt_mean_s"]) for r in timing_rows]
    stds   = [float(r["rt_std_s"])  for r in timing_rows]

    fig, ax = plt.subplots(figsize=(7, 4))
    x = range(len(labels))
    ax.bar(x, means, yerr=stds, capsize=4,
           color="#1f77b4", alpha=0.85, edgecolor="white")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("Runtime (seconds)", fontsize=11)
    ax.set_xlabel("Instance", fontsize=11)
    ax.set_title("PB-NSGA: Runtime vs. Instance Size (Stress Test)",
                 fontsize=12, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [Plot] {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Default: look for results in results/exp1/ relative to project root
    _script_dir  = os.path.dirname(os.path.abspath(__file__))
    _project_dir = os.path.dirname(_script_dir)
    _results_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_project_dir, "results", "exp1")
    _out_dir     = sys.argv[2] if len(sys.argv) > 2 else _results_dir
    run(_results_dir, _out_dir)
