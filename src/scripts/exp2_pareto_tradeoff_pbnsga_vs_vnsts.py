"""
exp2_pareto_tradeoff_pbnsga_vs_vnsts.py
======================================
Builds a two-panel Pareto trade-off comparison:
    - Left: CV-Small (PB-NSGA, VNS-TS, and MILP-based true Pareto front)
    - Right: CV-Large (PB-NSGA vs VNS-TS)

Outputs:
    - exp2_tradeoff_pareto.csv
    - exp2_tradeoff_summary.json
    - exp2_pareto_pbnsga_vs_vnsts.pdf (2-panel figure)
"""

import argparse
import csv
import glob
import json
import math
import os
import re

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


EPS = 1e-9


def load_feasible_points(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    front = data.get("pareto_front", [])

    pts = [(sol["Z1"], sol["Z2"]) for sol in front if float(sol.get("CV", 0.0)) <= EPS]
    if not pts:
        pts = [(sol["Z1"], sol["Z2"]) for sol in front if int(sol.get("rank", 1)) == 1]

    dedup = {}
    for z1, z2 in pts:
        dedup[(round(float(z1), 6), round(float(z2), 6))] = (float(z1), float(z2))
    return list(dedup.values())


def non_dominated(pts):
    out = []
    for p in pts:
        dominated = False
        for q in pts:
            if q is p:
                continue
            if q[0] <= p[0] and q[1] <= p[1] and (q[0] < p[0] or q[1] < p[1]):
                dominated = True
                break
        if not dominated:
            out.append(p)

    dedup = {}
    for z1, z2 in out:
        dedup[(round(z1, 6), round(z2, 6))] = (z1, z2)
    return sorted(dedup.values(), key=lambda x: (x[0], x[1]))


def _must_load(path, label):
    if not os.path.exists(path):
        raise RuntimeError(f"Missing {label} file: {path}")
    return load_feasible_points(path)


def _apply_power_scale(ax, pb_pts, all_pts, target_frac=0.25, n_ticks=7):
    """
    Apply a shifted power transform on both axes so that pb_pts spans
    exactly target_frac of each axis, regardless of the actual data range.

    The exponent p is solved per axis from:
        ((pb_max - data_min) / (data_max - data_min)) ^ p  = target_frac
    => p = log(target_frac) / log((pb_max - data_min) / (data_max - data_min))

    Ticks are placed at n_ticks positions evenly spaced in the transformed
    coordinate, then labelled with their original values.
    """
    z1 = [p[0] for p in all_pts]
    z2 = [p[1] for p in all_pts]
    x_min, x_max = min(z1), max(z1)
    y_min, y_max = min(z2), max(z2)
    pb_x_max = max(p[0] for p in pb_pts)
    pb_y_max = max(p[1] for p in pb_pts)

    def _exponent(mn, pb_mx, mx, frac):
        r = (pb_mx - mn) / (mx - mn)
        if r <= 0 or r >= 1:
            return 1.0
        return math.log(frac) / math.log(r)

    px = _exponent(x_min, pb_x_max, x_max, target_frac)
    py = _exponent(y_min, pb_y_max, y_max, target_frac)

    def _fwd(mn, p):
        def f(v):
            v = np.asarray(v, dtype=float)
            with np.errstate(invalid="ignore"):
                return np.where(v >= mn, (v - mn) ** p, -((mn - v) ** p))
        return f

    def _inv(mn, p):
        def f(t):
            t = np.asarray(t, dtype=float)
            with np.errstate(invalid="ignore"):
                return np.where(t >= 0, mn + t ** (1 / p), mn - ((-t) ** (1 / p)))
        return f

    ax.set_xscale("function", functions=(_fwd(x_min, px), _inv(x_min, px)))
    ax.set_yscale("function", functions=(_fwd(y_min, py), _inv(y_min, py)))

    def _ceil_nice(v):
        """Ceiling to 2 significant figures (1 decimal of leading digit)."""
        if v == 0:
            return 0.0
        mag = 10 ** math.floor(math.log10(abs(v)))  # leading power of 10
        step = mag / 10                              # 1/10th → 2 sig figs
        return math.ceil(v / step) * step

    # Ticks evenly spaced in transformed space → rounded original-value labels
    t_x = np.linspace(0.0, (x_max - x_min) ** px, n_ticks)
    t_y = np.linspace(0.0, (y_max - y_min) ** py, n_ticks)
    x_ticks = np.array([_ceil_nice(x_min + float(t) ** (1 / px)) if t > 0 else x_min
                        for t in t_x])
    y_ticks = np.array([_ceil_nice(y_min + float(t) ** (1 / py)) if t > 0 else y_min
                        for t in t_y])
    ax.set_xticks(x_ticks)
    ax.set_yticks(y_ticks)
    def _fmt_x(v, _):
        m = v / 1e6
        return f"{m:.0f}M" if m == int(m) else f"{m:.1f}M"
    ax.xaxis.set_major_formatter(plt.FuncFormatter(_fmt_x))
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _: f"{v/1e3:.0f}K")
    )
    # Tight limits with a small visual margin
    x_margin = (x_max - x_min) * 0.03
    y_margin = (y_max - y_min) * 0.03
    ax.set_xlim(x_min - x_margin, x_max + x_margin)
    ax.set_ylim(y_min - y_margin, y_max + y_margin)


def plot_tradeoff_two_panel(small_panel, large_panel, out_pdf):
    if not HAS_MPL:
        print("[Warning] matplotlib not available, skipping plot generation.")
        return

    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(12.2, 4.8))

    # Left panel: CV-small
    pb_s = sorted(small_panel["pb"], key=lambda p: p[0])
    vns_s = sorted(small_panel["vns"], key=lambda p: p[0])
    true_s = sorted(small_panel["true"], key=lambda p: p[0])
    if pb_s:
        ax_l.plot([p[0] for p in pb_s], [p[1] for p in pb_s], "-o", color="#1f77b4", lw=1.7, ms=4, label="PB-NSGA")
    if vns_s:
        ax_l.plot([p[0] for p in vns_s], [p[1] for p in vns_s], "-^", color="#ff7f0e", lw=1.7, ms=4, label="VNS-TS")
    if true_s:
        ax_l.plot([p[0] for p in true_s], [p[1] for p in true_s], "--s", color="#2ca02c", lw=1.7, ms=4, label="True Pareto (MILP)")
    ax_l.set_title("(a) CV-Small: PB-NSGA vs VNS-TS vs True Pareto")
    ax_l.set_xlabel("Z1 - Expected Logistics Cost")
    ax_l.set_ylabel("Z2 - Expected Maximum Deprivation")
    ax_l.grid(True, alpha=0.25)
    ax_l.legend(fontsize=8)

    # Right panel: CV-large with auto power-scale
    pb_l = sorted(large_panel["pb"], key=lambda p: p[0])
    vns_l = sorted(large_panel["vns"], key=lambda p: p[0])
    nd_l = sorted(large_panel["combined_nd"], key=lambda p: p[0])
    if pb_l:
        ax_r.plot([p[0] for p in pb_l], [p[1] for p in pb_l], "-o", color="#1f77b4", lw=1.8, ms=4, label="PB-NSGA")
    if vns_l:
        ax_r.plot([p[0] for p in vns_l], [p[1] for p in vns_l], "-^", color="#ff7f0e", lw=1.8, ms=4, label="VNS-TS")
    if nd_l:
        ax_r.scatter([p[0] for p in nd_l], [p[1] for p in nd_l],
                     s=32, facecolors="none", edgecolors="black", linewidths=1.0,
                     label="Combined ND")
    _apply_power_scale(ax_r, pb_pts=pb_l, all_pts=pb_l + vns_l, target_frac=0.25, n_ticks=7)
    ax_r.set_title("(b) CV-Large: PB-NSGA vs VNS-TS")
    ax_r.set_xlabel(r"$Z_1$ - Expected Logistics Cost (power scale)")
    ax_r.set_ylabel(r"$Z_2$ - Max. Deprivation (power scale)")
    ax_r.grid(True, alpha=0.25)
    ax_r.legend(fontsize=8)

    fig.tight_layout()
    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)
    fig.savefig(out_pdf, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"[Plot] {out_pdf}")


def main():
    ap = argparse.ArgumentParser(description="Pareto trade-off comparison: PB-NSGA vs VNS-TS")
    ap.add_argument("--results-exp2", default="results/exp2", help="Directory containing Exp2 result JSONs")
    ap.add_argument("--results-exp1", default="results/exp1", help="Directory containing Exp1 result JSONs")
    ap.add_argument("--out-dir", default="results/exp2", help="Directory for CSV/JSON summary outputs")
    ap.add_argument("--pb-glob", default=None, help="Optional glob override for PB-NSGA result files")
    ap.add_argument("--vns-glob", default=None, help="Optional glob override for VNS-TS result files")
    ap.add_argument("--allow-missing-vns", action="store_true", help="Allow running even if VNS files are missing")
    args = ap.parse_args()

    results_dir = args.results_exp2
    exp1_dir = args.results_exp1
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)

    if args.pb_glob:
        pb_files = sorted(glob.glob(os.path.join(results_dir, args.pb_glob)))
    else:
        pb_files = [
            os.path.join(results_dir, fn)
            for fn in sorted(os.listdir(results_dir))
            if re.match(r"(?i)^cv_large_seed\d+\.json$", fn)
        ]

    if args.vns_glob:
        vns_files = sorted(glob.glob(os.path.join(results_dir, args.vns_glob)))
    else:
        vns_files = [
            os.path.join(results_dir, fn)
            for fn in sorted(os.listdir(results_dir))
            if re.match(r"(?i)^cv_large_vns_ts_seed\d+\.json$", fn)
        ]

    if not pb_files:
        raise RuntimeError("No PB-NSGA CV-large seed files found.")
    if not vns_files and not args.allow_missing_vns:
        raise RuntimeError("No VNS-TS CV-large seed files found. Run VNS-TS stage first.")

    pb_raw = []
    for p in pb_files:
        pb_raw.extend(load_feasible_points(p))

    vns_raw = []
    for p in vns_files:
        vns_raw.extend(load_feasible_points(p))

    pb_nd = non_dominated(pb_raw)
    vns_nd = non_dominated(vns_raw)

    labeled = [("PB-NSGA", z1, z2) for z1, z2 in pb_nd] + [("VNS-TS", z1, z2) for z1, z2 in vns_nd]
    union_nd = non_dominated([(z1, z2) for _, z1, z2 in labeled])
    union_keys = {(round(z1, 6), round(z2, 6)) for z1, z2 in union_nd}

    # CV-small panel data (single-run trade-off + true front from MILP variants)
    pb_small = _must_load(os.path.join(exp1_dir, "cv_small_pb_nsga.json"), "CV-small PB-NSGA")
    vns_small = _must_load(os.path.join(exp1_dir, "cv_small_vns_ts.json"), "CV-small VNS-TS")
    milp_aws_small = _must_load(os.path.join(exp1_dir, "cv_small_milp_aws.json"), "CV-small MILP-AWS")
    milp_eps_small = _must_load(os.path.join(exp1_dir, "cv_small_milp_eps.json"), "CV-small MILP-EPS")
    true_small = non_dominated(milp_aws_small + milp_eps_small)

    csv_path = os.path.join(out_dir, "exp2_tradeoff_pareto.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "algorithm", "Z1", "Z2", "is_combined_nd"])
        for algo, z1, z2 in sorted(labeled, key=lambda x: (x[0], x[1], x[2])):
            key = (round(z1, 6), round(z2, 6))
            w.writerow(["CV-large", algo, f"{z1:.6f}", f"{z2:.6f}", 1 if key in union_keys else 0])
        for z1, z2 in sorted(pb_small, key=lambda p: (p[0], p[1])):
            w.writerow(["CV-small", "PB-NSGA", f"{z1:.6f}", f"{z2:.6f}", ""])
        for z1, z2 in sorted(vns_small, key=lambda p: (p[0], p[1])):
            w.writerow(["CV-small", "VNS-TS", f"{z1:.6f}", f"{z2:.6f}", ""])
        for z1, z2 in sorted(true_small, key=lambda p: (p[0], p[1])):
            w.writerow(["CV-small", "True Pareto (MILP)", f"{z1:.6f}", f"{z2:.6f}", ""])

    summary = {
        "pb_files": len(pb_files),
        "vns_files": len(vns_files),
        "pb_nd_points": len(pb_nd),
        "vns_nd_points": len(vns_nd),
        "combined_nd_points": len(union_nd),
        "cv_small": {
            "pb_points": len(pb_small),
            "vns_points": len(vns_small),
            "true_milp_points": len(true_small),
        },
        "outputs": {
            "csv": csv_path,
            "plot": os.path.join(out_dir, "exp2_pareto_pbnsga_vs_vnsts.pdf"),
        },
    }

    summary_path = os.path.join(out_dir, "exp2_tradeoff_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    plot_tradeoff_two_panel(
        {"pb": pb_small, "vns": vns_small, "true": true_small},
        {"pb": pb_nd, "vns": vns_nd, "combined_nd": union_nd},
        os.path.join(out_dir, "exp2_pareto_pbnsga_vs_vnsts.pdf"),
    )

    print(f"[Saved] {csv_path}")
    print(f"[Saved] {summary_path}")
    print(f"[Info] PB files={len(pb_files)}, VNS files={len(vns_files)}, combined ND={len(union_nd)}")


if __name__ == "__main__":
    main()
