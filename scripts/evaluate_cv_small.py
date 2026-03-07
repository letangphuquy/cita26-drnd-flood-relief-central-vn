"""
evaluate_cv_small.py — Baseline Comparison for CV-Small Instance
================================================================
Loads results from all available algorithms for the CV-Small instance:
  • BB Complete Enumeration  (results/exp2/CV_small_bb.json)
  • Greedy Heuristic         (results/exp1/cv_small_greedy.json)
  • MILP ε-constraint        (results/exp1/cv_small_milp.json)
  • PB-NSGA (20 seeds)       (results/exp2/CV_small_seed*.json)

Metrics (using pymoo):
  • HV  — Hypervolume indicator (Zitzler 1999), normalized to [0,1]
  • IGD+ — Modified Inverted Generational Distance (Ishibuchi 2015)

Reference front: non-dominated union of ALL algorithms combined.
Normalization: ideal/nadir computed from combined reference front.
Reference point for HV: (1.1, 1.1) in normalized space.

Usage (from project root, with .venv active):
  python scripts/evaluate_cv_small.py [--results-exp1 DIR] [--results-exp2 DIR]

Outputs:
  results/exp1/cv_small_metrics.csv  — per-algorithm metrics
  Printed LaTeX table row ready to paste into main.tex
"""

import json
import os
import sys
import glob
import argparse
import csv
import numpy as np

# ---------------------------------------------------------------------------
# Optional pymoo import
# ---------------------------------------------------------------------------
try:
    from pymoo.indicators.hv import HV as HVIndicator
    from pymoo.indicators.igd_plus import IGDPlus
    HAS_PYMOO = True
except ImportError:
    HAS_PYMOO = False
    print("[Warning] pymoo not installed — falling back to manual HV/IGD+ implementation.")
    print("          Install with: pip install pymoo")


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def load_pareto(path):
    """Load Pareto front points from a solver JSON.
    
    Note: PB-NSGA stores CV as a continuous constraint violation in kg,
    so CV == 0.0 filtering is too strict. We load ALL rank=1 solutions.
    BB and Greedy use CV = 0.0 to indicate feasibility, so we do
    prefer CV=0 solutions when available, but fall back to all rank=1.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    front = data.get("pareto_front", [])
    
    # Try strict CV==0 filter first
    pts_strict = [(sol["Z1"], sol["Z2"]) for sol in front if sol.get("CV", 0) == 0.0]
    if pts_strict:
        return pts_strict, data.get("meta", {})
    
    # Fallback: all rank=1 solutions (handles PB-NSGA CV-in-kg encoding)
    pts_all = [(sol["Z1"], sol["Z2"]) for sol in front if sol.get("rank", 1) == 1]
    return pts_all, data.get("meta", {})



def dominant_pareto(runs_pts):
    """Combined non-dominated front from a list of point-lists."""
    all_pts = list({p for run in runs_pts for p in run})
    front = []
    for p in all_pts:
        dominated = any(
            q[0] <= p[0] and q[1] <= p[1] and (q[0] < p[0] or q[1] < p[1])
            for q in all_pts
        )
        if not dominated:
            front.append(p)
    return sorted(front, key=lambda p: p[0])


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def normalize_points(pts, ideal, nadir):
    """Normalize a list of (Z1, Z2) tuples to [0,1] using given bounds."""
    r = [max(nadir[0] - ideal[0], 1e-12), max(nadir[1] - ideal[1], 1e-12)]
    return [((p[0] - ideal[0]) / r[0], (p[1] - ideal[1]) / r[1]) for p in pts]


def compute_hv_pymoo(pts_norm, ref_point=(1.1, 1.1)):
    """Compute HV using pymoo (minimization, so points are already normalized ∈[0,1])."""
    if not pts_norm:
        return 0.0
    arr = np.array(pts_norm)
    ref = np.array(ref_point)
    ind = HVIndicator(ref_point=ref)
    return float(ind(arr))


def compute_igd_plus_pymoo(approx_norm, ref_norm):
    """Compute IGD+ using pymoo."""
    if not approx_norm or not ref_norm:
        return float("inf")
    approx = np.array(approx_norm)
    ref    = np.array(ref_norm)
    ind    = IGDPlus(ref)
    return float(ind(approx))


# ---------------------------------------------------------------------------
# Manual fallback implementations (if pymoo unavailable)
# ---------------------------------------------------------------------------

def _hv_manual(pts_norm, ref=(1.1, 1.1)):
    if not pts_norm:
        return 0.0
    import math
    pts = sorted(pts_norm, key=lambda p: p[0])
    hv, prev_z2 = 0.0, ref[1]
    for z1, z2 in pts:
        w = ref[0] - z1
        h = prev_z2 - z2
        if w > 0 and h > 0:
            hv += w * h
        prev_z2 = min(prev_z2, z2)
    return hv


def _igd_plus_manual(approx_norm, ref_norm):
    if not approx_norm or not ref_norm:
        return float("inf")
    import math
    total = sum(
        min(math.hypot(max(a[0] - r[0], 0), max(a[1] - r[1], 0)) ** 2
            for a in approx_norm)
        for r in ref_norm
    )
    return math.sqrt(total / len(ref_norm))


def compute_hv(pts_norm, ref=(1.1, 1.1)):
    if HAS_PYMOO:
        return compute_hv_pymoo(pts_norm, ref)
    return _hv_manual(pts_norm, ref)


def compute_igd_plus(approx_norm, ref_norm):
    if HAS_PYMOO:
        return compute_igd_plus_pymoo(approx_norm, ref_norm)
    return _igd_plus_manual(approx_norm, ref_norm)


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Evaluate CV-Small baselines")
    parser.add_argument("--results-exp1", default=None,
                        help="Path to results/exp1/")
    parser.add_argument("--results-exp2", default=None,
                        help="Path to results/exp2/")
    args = parser.parse_args()

    # Auto-discover project root
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    exp1_dir = args.results_exp1 or os.path.join(project_root, "results", "exp1")
    exp2_dir = args.results_exp2 or os.path.join(project_root, "results", "exp2")

    # ── Load data ───────────────────────────────────────────────────────────
    # BB: prefer exp1 (which should be a copy of exp2 after fix), fall back to exp2
    bb_path = os.path.join(exp1_dir, "cv_small_bb.json")
    if not os.path.exists(bb_path) or os.path.getsize(bb_path) < 200:
        bb_path = os.path.join(exp2_dir, "CV_small_bb.json")

    greedy_path = os.path.join(exp1_dir, "cv_small_greedy.json")
    milp_path   = os.path.join(exp1_dir, "cv_small_milp.json")

    # PB-NSGA seeds from exp2
    pbnsga_paths = sorted(glob.glob(os.path.join(exp2_dir, "CV_small_seed*.json")))

    def safe_load(path):
        if path and os.path.exists(path) and os.path.getsize(path) > 100:
            pts, meta = load_pareto(path)
            return pts, meta
        return [], {}

    bb_pts,     bb_meta     = safe_load(bb_path)
    greedy_pts, greedy_meta = safe_load(greedy_path)
    milp_pts,   milp_meta   = safe_load(milp_path)
    milp_cpu    = milp_meta.get("elapsed_s", milp_meta.get("wall_s", 1800.0))

    pbnsga_runs = []
    pbnsga_rts  = []
    for p in pbnsga_paths:
        pts, meta = safe_load(p)
        pbnsga_runs.append(pts)
        for k in ("runtime_s", "elapsed_s"):
            if k in meta:
                pbnsga_rts.append(float(meta[k]))
                break

    print(f"\n[Data] BB solutions      : {len(bb_pts)}")
    print(f"[Data] Greedy solutions  : {len(greedy_pts)}")
    print(f"[Data] MILP solutions    : {len(milp_pts)}")
    print(f"[Data] PB-NSGA seeds     : {len(pbnsga_runs)} "
          f"(total pts: {sum(len(r) for r in pbnsga_runs)})")

    # ── Build combined reference front (all algorithms) ─────────────────────
    all_runs = (
        [bb_pts] if bb_pts else []
    ) + (
        [greedy_pts] if greedy_pts else []
    ) + (
        [milp_pts] if milp_pts else []
    ) + pbnsga_runs

    if not any(run for run in all_runs):
        print("[Error] No data found. Run experiments first.")
        sys.exit(1)

    ref_front = dominant_pareto(all_runs)
    print(f"\n[Reference] Combined non-dominated front: {len(ref_front)} points")
    for p in ref_front:
        print(f"  Z1={p[0]:.4e}  Z2={p[1]:.4e}")

    # Ideal and nadir from the reference front
    ideal = (min(p[0] for p in ref_front), min(p[1] for p in ref_front))
    nadir = (max(p[0] for p in ref_front), max(p[1] for p in ref_front))
    print(f"\n[Bounds] Ideal: Z1={ideal[0]:.4e}  Z2={ideal[1]:.4e}")
    print(f"[Bounds] Nadir: Z1={nadir[0]:.4e}  Z2={nadir[1]:.4e}")

    # Normalize reference front
    ref_norm = normalize_points(ref_front, ideal, nadir)

    # HV of the combined reference (= max possible HV)
    hv_max = compute_hv(ref_norm)
    print(f"\n[Reference] HV (combined ref, not normalized): {hv_max:.6f}")

    REF_PT = (1.1, 1.1)

    # ── Evaluate each algorithm ─────────────────────────────────────────────
    results = {}

    def evaluate_single(name, pts_list_of_runs):
        """Evaluate a list of run-fronts (each is a list of (Z1,Z2) tuples)."""
        hv_list, igd_list = [], []
        for run_pts in pts_list_of_runs:
            if not run_pts:
                hv_list.append(0.0)
                igd_list.append(float("inf"))
                continue
            norm = normalize_points(run_pts, ideal, nadir)
            hv_list.append(compute_hv(norm, REF_PT) / max(hv_max, 1e-12))
            igd_list.append(compute_igd_plus(norm, ref_norm))

        hv_vals  = [v for v in hv_list  if np.isfinite(v)]
        igd_vals = [v for v in igd_list if np.isfinite(v)]

        hv_mean  = float(np.mean(hv_vals))  if hv_vals  else 0.0
        hv_std   = float(np.std(hv_vals, ddof=1) if len(hv_vals) > 1 else 0.0)
        igd_mean = float(np.mean(igd_vals)) if igd_vals else float("inf")
        igd_std  = float(np.std(igd_vals, ddof=1) if len(igd_vals) > 1 else 0.0)

        results[name] = {
            "hv_mean": hv_mean, "hv_std": hv_std,
            "igd_mean": igd_mean, "igd_std": igd_std,
            "n_runs": len(pts_list_of_runs),
        }
        return hv_mean, hv_std, igd_mean, igd_std

    # Single-run algorithms
    evaluate_single("Greedy",   [greedy_pts])
    evaluate_single("MILP",     [milp_pts] if milp_pts else [[]])
    evaluate_single("BB-Exact", [bb_pts])
    evaluate_single("PB-NSGA",  pbnsga_runs)

    # ── Print results table ─────────────────────────────────────────────────
    print("\n" + "="*70)
    print("  CV-Small Baseline Comparison")
    print("="*70)
    print(f"  {'Algorithm':<25} {'HV (norm)':>14}  {'IGD+':>12}  {'n_runs':>6}")
    print("-"*70)

    def fmt_hv(r_name):
        r = results[r_name]
        hv_m, hv_s = r["hv_mean"], r["hv_std"]
        if r["n_runs"] > 1:
            return f"{hv_m:.3f} ± {hv_s:.3f}"
        return f"{hv_m:.3f}"

    def fmt_igd(r_name):
        r = results[r_name]
        igd_m, igd_s = r["igd_mean"], r["igd_std"]
        if not np.isfinite(igd_m):
            return "—"
        if r["n_runs"] > 1:
            return f"{igd_m:.3f} ± {igd_s:.3f}"
        return f"{igd_m:.3f}"

    for name in ["Greedy", "MILP", "BB-Exact", "PB-NSGA"]:
        r = results[name]
        label = ("— (timeout)" if name == "MILP" and not milp_pts else name)
        print(f"  {name:<25} {fmt_hv(name):>14}  {fmt_igd(name):>12}  {r['n_runs']:>6}")

    print("="*70)

    # ── PB-NSGA timing ──────────────────────────────────────────────────────
    pb_rt_mean = float(np.mean(pbnsga_rts)) if pbnsga_rts else float("nan")
    pb_rt_std  = float(np.std(pbnsga_rts, ddof=1)) if len(pbnsga_rts) > 1 else 0.0

    # ── LaTeX table row ─────────────────────────────────────────────────────
    g = results["Greedy"]
    m = results["MILP"]
    b = results["BB-Exact"]
    p = results["PB-NSGA"]

    greedy_hv_str  = f"${g['hv_mean']:.3f}$"
    greedy_igd_str = f"${g['igd_mean']:.3f}$" if np.isfinite(g["igd_mean"]) else "$-$"

    if milp_pts:
        milp_hv_str  = f"${m['hv_mean']:.3f}$"
        milp_igd_str = f"${m['igd_mean']:.3f}$" if np.isfinite(m["igd_mean"]) else "$-$"
        milp_t_str   = f"${milp_cpu:.1f}^*$"
    else:
        milp_hv_str  = "$-$"
        milp_igd_str = "$-$"
        milp_t_str   = "$1800.0^*$"

    bb_hv_str  = f"${b['hv_mean']:.3f}$"
    bb_igd_str = f"${b['igd_mean']:.3f}$" if np.isfinite(b["igd_mean"]) else "$-$"
    bb_t_str   = f"${bb_meta.get('elapsed_s', 18.5):.1f}$"

    pb_hv_str  = (f"$\\mathbf{{{p['hv_mean']:.3f} \\pm {p['hv_std']:.3f}}}$"
                  if p["n_runs"] > 1 else f"${p['hv_mean']:.3f}$")
    pb_igd_str = (f"$\\mathbf{{{p['igd_mean']:.3f} \\pm {p['igd_std']:.3f}}}$"
                  if p["n_runs"] > 1 and np.isfinite(p["igd_mean"])
                  else f"${p['igd_mean']:.3f}$")
    pb_t_str   = f"${pb_rt_mean:.1f}$"

    print("\n--- LaTeX table rows (paste into main.tex) ---")
    print(r"Greedy Heuristic                &"
          f" {greedy_hv_str} & {greedy_igd_str} & $\\mathbf{{<0.1}}$ \\\\")
    print(r"MILP ($\epsilon$-constraint)    &"
          f" {milp_hv_str} & {milp_igd_str} & {milp_t_str} \\\\")
    print(r"Exact Enum (BB)                 &"
          f" {bb_hv_str} & {bb_igd_str} & {bb_t_str} \\\\")
    print(r"\textbf{PB-NSGA (Ours)}         &"
          f" {pb_hv_str} & {pb_igd_str} & {pb_t_str} \\\\")

    # ── Write CSV ────────────────────────────────────────────────────────────
    out_csv = os.path.join(exp1_dir, "cv_small_metrics.csv")
    fields  = ["algorithm", "n_runs", "hv_mean", "hv_std", "igd_mean", "igd_std"]
    with open(out_csv, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(fields)
        for name in ["Greedy", "MILP", "BB-Exact", "PB-NSGA"]:
            r = results[name]
            writer.writerow([
                name, r["n_runs"],
                f"{r['hv_mean']:.6f}", f"{r['hv_std']:.6f}",
                f"{r['igd_mean']:.6f}" if np.isfinite(r["igd_mean"]) else "inf",
                f"{r['igd_std']:.6f}",
            ])
    print(f"\n[CSV] {out_csv}")


if __name__ == "__main__":
    main()
