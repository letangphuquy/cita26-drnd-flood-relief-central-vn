"""
analyze_results.py
==================
Post-processes PB-NSGA-II solver output JSONs to support two experiments:

  Experiment 1 — Algorithm Efficiency (HLP benchmarks)
    Input : results/AP{n}_result.json, results/TR81_result.json
    Output: per-instance Pareto plots + summary table (HV, IGD+, size, time)

  Experiment 2 — Case Study: Central Vietnam
    Input : results/CV_{type}_seed{n}.json          (PB-NSGA-II runs)
            results/CV_{type}_nsga2_s{n}.json        (NSGA-II baseline)
            results/CV_{type}_nsma_s{n}.json         (NSMA baseline)
    Output: comparison Pareto plot + summary table (mean ± std over runs)

Result JSON schema expected (solver output):
  {
    "pareto_front": [{"Z1": ..., "Z2": ..., "CV": 0.0, "rank": 1, ...}, ...],
    "meta": {"runtime_s": ..., "instance": ..., "seed": ...}   ← optional
  }

Usage:
  python analyze_results.py                          # default: ../results/
  python analyze_results.py path/to/results/
  python analyze_results.py path/to/single_file.json

Outputs:
  results/figures/<group>_pareto.pdf
  results/summary_exp1.csv   (benchmark efficiency)
  results/summary_exp2.csv   (case study)
"""

import os
import sys
import json
import math
import csv
import statistics
from collections import defaultdict

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("[Warning] matplotlib not available — plots will be skipped.")

# ---------------------------------------------------------------------------
# Pareto / metric helpers
# ---------------------------------------------------------------------------

def load_result(path):
    """
    Load solver output JSON.  Returns (pareto_pts, meta_dict).
    pareto_pts: list of (Z1, Z2) from pareto_front where CV == 0.
    meta_dict:  top-level "meta" sub-dict (may be absent → {}).
    """
    with open(path) as fh:
        data = json.load(fh)
    pts = [
        (sol["Z1"], sol["Z2"])
        for sol in data.get("pareto_front", [])
        if sol.get("CV", 0) == 0
    ]
    return pts, data.get("meta", {})


def dominant_pareto(runs_pts):
    """Combined non-dominated front from a list of Pareto-front point lists."""
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
    """
    Normalize all points to [0,1] using shared min/max across all runs.
    Returns (normalized_pts_list, (z1_min, z1_max, z2_min, z2_max)).
    """
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
    def _norm(p):
        return ((p[0] - z1_min) / rz1, (p[1] - z2_min) / rz2)
    normed = [[_norm(p) for p in run] for run in pts_list]
    return normed, (z1_min, z1_max, z2_min, z2_max)


def hypervolume_2d(pareto, ref=(1.1, 1.1)):
    """
    2D hypervolume indicator (Zitzler 1999).
    ref_point must weakly dominate all points.
    Assumes points already normalized to [0,1].
    cite: Zitzler, E., & Thiele, L. (1999). Multiobjective evolutionary
          algorithms: a comparative case study and the strength Pareto approach.
          IEEE TEC 3(4), 257-271.
    """
    if not pareto:
        return 0.0
    pts = sorted(pareto, key=lambda p: p[0])
    hv, prev_z2 = 0.0, ref[1]
    for z1, z2 in pts:
        width  = ref[0] - z1
        height = prev_z2 - z2
        if width > 0 and height > 0:
            hv += width * height
        prev_z2 = min(prev_z2, z2)
    return hv


def igd_plus(approx, reference):
    """
    IGD+ (Ishibuchi et al. 2015) — modified inverted generational distance.
    cite: Ishibuchi, H. et al. (2015). Modified distance calculation in
          generational distance and inverted generational distance. EMO 2015.
    Both approx and reference must be normalised.
    """
    if not reference or not approx:
        return float('inf')
    total = sum(
        min(math.hypot(max(az1 - rz1, 0), max(az2 - rz2, 0)) ** 2
            for az1, az2 in approx)
        for rz1, rz2 in reference
    )
    return math.sqrt(total / len(reference))


def _mean_std(vals):
    """Return (mean, std) or (val, 0.0) for a single-element list."""
    if not vals:
        return float('nan'), float('nan')
    if len(vals) == 1:
        return vals[0], 0.0
    return statistics.mean(vals), statistics.stdev(vals)


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
ALGO_STYLE = {
    "PB-NSGA-II":           dict(color="#1f77b4", marker="o", lw=1.8),
    "PB-NSGA-II (combined)":dict(color="#1f77b4", marker="o", lw=1.8),
    "BB-Exact (true front)":dict(color="#d62728", marker="D", lw=2.0, ls="-"),
    "BB-Exact":             dict(color="#d62728", marker="D", lw=2.0, ls="-"),
    "NSGA-II":              dict(color="#ff7f0e", marker="s", lw=1.5, ls="--"),
    "NSMA":                 dict(color="#2ca02c", marker="^", lw=1.5, ls=":"),
    "Combined":             dict(color="#d62728", marker="D", lw=2.0, ls="-"),
}
_FALLBACK_COLORS = ["#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]


def plot_pareto(series_dict, out_path, title="Pareto Front",
                xlabel="$Z_1$ — Expected Logistics Cost",
                ylabel="$Z_2$ — Expected Max Deprivation"):
    """
    series_dict: {label: [(Z1,Z2), ...]}
    Draws one line per series; marks knee point with ★.
    """
    if not HAS_MPL:
        return
    fig, ax = plt.subplots(figsize=(7, 5))
    fallback_idx = 0
    for label, pts in series_dict.items():
        if not pts:
            continue
        pts_s = sorted(pts, key=lambda p: p[0])
        z1s = [p[0] for p in pts_s]
        z2s = [p[1] for p in pts_s]
        style = dict(ALGO_STYLE.get(label, {}))
        if not style:
            style = dict(color=_FALLBACK_COLORS[fallback_idx % len(_FALLBACK_COLORS)],
                         marker="o", lw=1.5)
            fallback_idx += 1
        ax.plot(z1s, z2s,
                color=style.get("color", "blue"),
                marker=style.get("marker", "o"),
                linewidth=style.get("lw", 1.5),
                linestyle=style.get("ls", "-"),
                markersize=4, alpha=0.85, label=label)
        # Knee: furthest point from ideal corner in normalised coords
        if len(pts_s) >= 3:
            mn1, mx1 = min(z1s), max(z1s)
            mn2, mx2 = min(z2s), max(z2s)
            r1, r2 = max(mx1 - mn1, 1e-9), max(mx2 - mn2, 1e-9)
            dists = [math.hypot((z1 - mn1)/r1, (z2 - mn2)/r2) for z1, z2 in pts_s]
            ki = dists.index(max(dists))
            ax.scatter([z1s[ki]], [z2s[ki]], marker="*", s=180,
                       color=style.get("color", "blue"), zorder=5)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [Plot] {out_path}")


# ---------------------------------------------------------------------------
# File discovery helpers
# ---------------------------------------------------------------------------

def _parse_filename(fname):
    """
    Returns (group, algo, seed_str) or None if unrecognised.
    Recognised patterns:
      AP{n}_seed{s}.json          → ("AP{n}",    "PB-NSGA-II", "{s}")
      TR81_seed{s}.json           → ("TR81",      "PB-NSGA-II", "{s}")
      AP{n}_bb.json               → ("AP{n}",    "BB-Exact",   "0")
      TR81_bb.json                → ("TR81",      "BB-Exact",   "0")
      AP{n}_result.json           → ("AP{n}",    "PB-NSGA-II", "0")  [legacy]
      TR81_result.json            → ("TR81",      "PB-NSGA-II", "0")  [legacy]
      CV_{type}_seed{n}.json      → ("CV_{type}", "PB-NSGA-II", "{n}")
      CV_{type}_nsga2_s{n}.json   → ("CV_{type}", "NSGA-II",    "{n}")
      CV_{type}_nsma_s{n}.json    → ("CV_{type}", "NSMA",       "{n}")
      CV_{type}_bb.json           → ("CV_{type}", "BB-Exact",   "0")
    """
    base = fname[:-5]  # strip .json

    # ── Benchmark (AP / TR81) ──────────────────────────────────────────────
    # BB-Exact ground truth
    if base.endswith("_bb"):
        prefix = base[:-3]  # e.g. AP10, TR81, CV_small
        if prefix.startswith("AP") or prefix == "TR81":
            return prefix, "BB-Exact", "0"
        if prefix.startswith("CV_"):
            return prefix, "BB-Exact", "0"

    # Multi-seed PB-NSGA-II  AP{n}_seed{s}
    if "_seed" in base:
        parts = base.split("_seed")
        prefix = parts[0]
        seed   = parts[1] if len(parts) > 1 else "0"
        if prefix.startswith("AP") or prefix == "TR81":
            return prefix, "PB-NSGA-II", seed

    # Legacy single-result files
    if base.startswith("AP") and base.endswith("_result"):
        grp = base.replace("_result", "")
        return grp, "PB-NSGA-II", "0"
    if base == "TR81_result":
        return "TR81", "PB-NSGA-II", "0"

    # ── CV case study ──────────────────────────────────────────────────────
    if base.startswith("CV_"):
        parts = base.split("_")
        # CV_small_seed{n} or CV_large_seed{n}
        if len(parts) >= 3 and parts[2].startswith("seed"):
            grp  = "_".join(parts[:2])
            seed = parts[2].replace("seed", "")
            return grp, "PB-NSGA-II", seed
        # CV_small_nsga2_s{n}
        if len(parts) >= 4 and parts[2] == "nsga2":
            grp  = "_".join(parts[:2])
            seed = parts[3].replace("s", "")
            return grp, "NSGA-II", seed
        # CV_small_nsma_s{n}
        if len(parts) >= 4 and parts[2] == "nsma":
            grp  = "_".join(parts[:2])
            seed = parts[3].replace("s", "")
            return grp, "NSMA", seed

    return None   # unrecognised (test.json, summary.csv, …)


def discover_files(results_dir):
    """
    Returns {group: {algo: [(seed_str, path), ...]}}
    separated into benchmark groups (AP*, TR81) and CV groups.
    """
    bench, cv = {}, {}
    for fname in sorted(os.listdir(results_dir)):
        if not fname.endswith(".json"):
            continue
        parsed = _parse_filename(fname)
        if parsed is None:
            continue
        grp, algo, seed = parsed
        path = os.path.join(results_dir, fname)
        target = bench if (grp.startswith("AP") or grp == "TR81") else cv
        target.setdefault(grp, {}).setdefault(algo, []).append((seed, path))
    return bench, cv


# ---------------------------------------------------------------------------
# Experiment 1 — Algorithm Efficiency (benchmarks)
# ---------------------------------------------------------------------------

def exp1_benchmark(bench_groups, fig_dir):
    """
    For each benchmark group, compare PB-NSGA-II against BB-Exact (ground truth).
    - BB-Exact provides the true Pareto front (used as IGD+ reference).
    - PB-NSGA-II: multi-seed mean±std for HV, IGD+ vs BB-Exact, size, runtime.
    - If BB-Exact is absent for a group, falls back to combined PB-NSGA-II front.
    Returns list of summary-row dicts.
    """
    rows = []
    AP_ORDER = ["AP10", "AP20", "AP25", "AP40", "AP50", "AP100", "TR81"]
    ALGO_ORDER = ["BB-Exact", "PB-NSGA-II"]
    sorted_grps = sorted(bench_groups.keys(),
                         key=lambda g: AP_ORDER.index(g) if g in AP_ORDER else 99)

    for grp in sorted_grps:
        algo_data = bench_groups[grp]  # {algo: [(seed, path)]}

        # ── Load per-algo runs ─────────────────────────────────────────────
        algo_runs = {}  # {algo: [pts_list_per_seed]}
        algo_meta = {}
        for algo in ALGO_ORDER:
            if algo not in algo_data:
                continue
            algo_runs[algo] = []
            algo_meta[algo] = []
            for seed, path in sorted(algo_data[algo], key=lambda x: x[0]):
                pts, meta = load_result(path)
                algo_runs[algo].append(pts)
                algo_meta[algo].append(meta)

        if not algo_runs:
            print(f"  [{grp}] No results found — skipping.")
            continue

        # ── Global normalisation bounds (all algos + seeds) ────────────────
        all_runs_flat = [run for runs in algo_runs.values() for run in runs]
        _, bounds = normalize_points(all_runs_flat)

        # ── Reference front for IGD+: BB-Exact if available, else combined PB-NSGA-II ──
        bb_pts = dominant_pareto(algo_runs.get("BB-Exact", []))
        pb_pts_all = algo_runs.get("PB-NSGA-II", [])
        pb_combined = dominant_pareto(pb_pts_all) if pb_pts_all else []

        # Normalise reference
        ref_raw = bb_pts if bb_pts else pb_combined
        ref_norm, _ = normalize_points([ref_raw], bounds=bounds)
        reference_norm = ref_norm[0] if ref_norm else []
        ref_pt = (1.1, 1.1)

        # ── Plot: one line per algo ────────────────────────────────────────
        series_dict = {}
        if bb_pts:
            series_dict["BB-Exact (true front)"] = bb_pts
        if pb_combined:
            series_dict["PB-NSGA-II (combined)"] = pb_combined
        plot_pareto(
            series_dict,
            os.path.join(fig_dir, f"{grp}_pareto.pdf"),
            title=f"Pareto Front — {grp}"
        )

        # ── Metrics for each algo ──────────────────────────────────────────
        for algo in ALGO_ORDER:
            if algo not in algo_runs:
                continue
            runs = algo_runs[algo]
            metas = algo_meta[algo]
            norm_runs, _ = normalize_points(runs, bounds=bounds)

            hv_list, igd_list, size_list, rt_list = [], [], [], []
            for pts, norm_pts, meta in zip(runs, norm_runs, metas):
                hv_list.append(hypervolume_2d(norm_pts, ref_pt))
                igd_list.append(igd_plus(norm_pts, reference_norm))
                size_list.append(len(pts))
                if "elapsed_s" in meta:
                    rt_list.append(float(meta["elapsed_s"]))
                elif "runtime_s" in meta:
                    rt_list.append(float(meta["runtime_s"]))

            hv_mean,   hv_std   = _mean_std(hv_list)
            igd_mean,  igd_std  = _mean_std(igd_list)
            size_mean, size_std = _mean_std([float(s) for s in size_list])
            rt_mean,   rt_std   = _mean_std(rt_list) if rt_list \
                                   else (float('nan'), float('nan'))
            combined_raw = dominant_pareto(runs)

            print(f"  [{grp}] {algo:12s}  runs={len(runs)}  "
                  f"pts(combined)={len(combined_raw)}  "
                  f"HV={hv_mean:.4f}±{hv_std:.4f}  "
                  f"IGD+={igd_mean:.4f}±{igd_std:.4f}"
                  + (f"  rt={rt_mean:.1f}s" if rt_list else ""))

            rows.append({
                "experiment":      "Exp1-Benchmark",
                "instance":        grp,
                "algorithm":       algo,
                "n_runs":          len(runs),
                "pareto_combined": len(combined_raw),
                "pareto_mean":     f"{size_mean:.1f}",
                "pareto_std":      f"{size_std:.1f}",
                "HV_mean":         f"{hv_mean:.6f}",
                "HV_std":          f"{hv_std:.6f}",
                "IGDplus_mean":    f"{igd_mean:.6f}",
                "IGDplus_std":     f"{igd_std:.6f}",
                "runtime_s_mean":  f"{rt_mean:.2f}" if rt_list else "N/A",
                "runtime_s_std":   f"{rt_std:.2f}"  if rt_list else "N/A",
                "igd_ref":         "BB-Exact" if bb_pts else "PB-NSGA-II combined",
            })

    return rows


# ---------------------------------------------------------------------------
# Experiment 2 — Case Study: Central Vietnam
# ---------------------------------------------------------------------------

def exp2_casestudy(cv_groups, fig_dir):
    """
    For each CV group (CV_small, CV_large):
      - Load PB-NSGA-II seeds + comparison algorithms (NSGA-II, NSMA if present)
      - Compute per-algo combined front, per-seed HV/IGD+ → mean ± std
      - Generate comparison Pareto plot
    Returns list of summary-row dicts.
    """
    rows = []
    ALGO_ORDER = ["PB-NSGA-II", "NSGA-II", "NSMA"]

    for grp in sorted(cv_groups.keys()):
        algo_data = cv_groups[grp]  # {algo: [(seed, path)]}

        # Collect per-algo raw Pareto lists (one list per seed)
        algo_runs = {}   # {algo: [pts_seed0, pts_seed1, ...]}
        for algo in ALGO_ORDER:
            if algo not in algo_data:
                continue
            algo_runs[algo] = []
            for seed, path in sorted(algo_data[algo], key=lambda x: x[0]):
                pts, _ = load_result(path)
                algo_runs[algo].append(pts)

        if not algo_runs:
            continue

        # Global normalization bounds: all points from all algos and seeds
        all_pts_flat = [run for runs in algo_runs.values() for run in runs]
        _, bounds = normalize_points(all_pts_flat)

        # Global reference front = combined non-dominated across ALL algos
        all_combined = dominant_pareto(all_pts_flat)
        all_norm, _  = normalize_points(all_pts_flat, bounds=bounds)
        ref_combined_norm = dominant_pareto(all_norm)
        ref_pt = (1.1, 1.1)

        series_for_plot = {}  # combined front per algo for the comparison plot

        for algo in ALGO_ORDER:
            if algo not in algo_runs:
                continue
            runs = algo_runs[algo]
            norm_runs, _ = normalize_points(runs, bounds=bounds)

            hv_list, igd_list, size_list = [], [], []
            for pts, norm_pts in zip(runs, norm_runs):
                hv_list.append(hypervolume_2d(norm_pts, ref_pt))
                igd_list.append(igd_plus(norm_pts, ref_combined_norm))
                size_list.append(len(pts))

            hv_mean,   hv_std   = _mean_std(hv_list)
            igd_mean,  igd_std  = _mean_std(igd_list)
            size_mean, size_std = _mean_std([float(s) for s in size_list])
            n_runs = len(runs)

            combined_raw  = dominant_pareto(runs)
            combined_norm = dominant_pareto(norm_runs)
            hv_combined   = hypervolume_2d(combined_norm, ref_pt)

            series_for_plot[algo] = combined_raw

            print(f"  [{grp}] {algo:12s}  runs={n_runs}  "
                  f"pts(combined)={len(combined_raw)}  "
                  f"HV={hv_mean:.4f}±{hv_std:.4f}  "
                  f"IGD+={igd_mean:.4f}±{igd_std:.4f}")

            rows.append({
                "experiment":      "Exp2-CaseStudy",
                "instance":        grp,
                "algorithm":       algo,
                "n_runs":          n_runs,
                "pareto_combined": len(combined_raw),
                "pareto_mean":     f"{size_mean:.1f}",
                "pareto_std":      f"{size_std:.1f}",
                "HV_mean":         f"{hv_mean:.6f}",
                "HV_std":          f"{hv_std:.6f}",
                "IGDplus_mean":    f"{igd_mean:.6f}",
                "IGDplus_std":     f"{igd_std:.6f}",
                "runtime_s_mean":  "N/A",
                "runtime_s_std":   "N/A",
            })

        # Comparison Pareto plot
        if series_for_plot:
            plot_pareto(
                series_for_plot,
                os.path.join(fig_dir, f"{grp}_pareto.pdf"),
                title=f"Pareto Front Comparison — {grp.replace('_', ' ').title()}"
            )

    return rows


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def analyze_folder(results_dir):
    fig_dir = os.path.join(results_dir, "figures")
    os.makedirs(fig_dir, exist_ok=True)

    bench_groups, cv_groups = discover_files(results_dir)

    if not bench_groups and not cv_groups:
        print(f"No recognised result files in {results_dir}")
        return

    print("\n=== Experiment 1: Algorithm Efficiency (HLP Benchmarks) ===")
    rows_exp1 = exp1_benchmark(bench_groups, fig_dir)

    print("\n=== Experiment 2: Case Study — Central Vietnam ===")
    rows_exp2 = exp2_casestudy(cv_groups, fig_dir)

    # Write separate CSVs for each experiment
    _FIELDS = [
        "experiment", "instance", "algorithm", "n_runs",
        "pareto_combined", "pareto_mean", "pareto_std",
        "HV_mean", "HV_std",
        "IGDplus_mean", "IGDplus_std",
        "runtime_s_mean", "runtime_s_std",
        "igd_ref",
    ]

    def _write_csv(rows, path):
        if not rows:
            return
        with open(path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"  [CSV] {path}")

    _write_csv(rows_exp1, os.path.join(results_dir, "summary_exp1.csv"))
    _write_csv(rows_exp2, os.path.join(results_dir, "summary_exp2.csv"))
    # Legacy combined summary for backwards compatibility
    _write_csv(rows_exp1 + rows_exp2, os.path.join(results_dir, "summary.csv"))

    print(f"\nDone. Figures -> {fig_dir}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"
    )
    if os.path.isfile(target):
        # Quick inspect of a single file
        pts, meta = load_result(target)
        print(f"File: {target}")
        print(f"Pareto front: {len(pts)} feasible solutions")
        print(f"Meta: {meta}")
        for z1, z2 in sorted(pts):
            print(f"  Z1={z1:.4e}  Z2={z2:.4e}")
    elif os.path.isdir(target):
        analyze_folder(target)
    else:
        print(f"Path not found: {target}")
        sys.exit(1)
