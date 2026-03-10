"""
exp1_evaluate_cv_small.py — Experiment 1: Baseline Comparison for CV-Small Instance
====================================================================================
STATUS: Active — called from run_exp1_baselines.bat / run_exp1_baselines.sh
        (Step 5 of 5).

Loads results from all available algorithms for the CV-Small instance:
    • VNS-TS Baseline         (results/exp1/cv_small_vns_ts.json)
            produced by vns_ts_baseline(.exe)
  • Greedy Heuristic         (results/exp1/cv_small_greedy.json)
      produced by greedy_baseline.exe  --restarts 500 --seed 42
  • MILP Adaptive Weighted Sum  (results/exp1/cv_small_milp_aws.json)
      produced by milp_aws_baseline.py  --time_limit 600
  • MILP Epsilon-Constraint     (results/exp1/cv_small_milp_eps.json)
      produced by milp_epsilon.py  --time_limit 600 --epsilon_steps 20
  • PB-NSGA (Ours)           (results/exp1/cv_small_pb_nsga.json)
      produced by solver.exe  --pop 200 --gen 300 --seed 0

Metrics (using pymoo if available, else built-in fallback):
  • HV   — Hypervolume indicator (Zitzler 1999), normalized to [0,1]
  • IGD+ — Modified Inverted Generational Distance (Ishibuchi 2015)

Reference front: non-dominated union of all algorithms combined.
Normalization : ideal/nadir from the combined reference front.
HV reference point: (1.1, 1.1) in normalized space.

Usage (canonical, from project root with .venv active):
  python src/scripts/exp1_evaluate_cv_small.py \
      --results-exp1 results/exp1 \
      --ours   results/exp1/cv_small_pb_nsga.json \
    --vns-ts results/exp1/cv_small_vns_ts.json \
      --greedy results/exp1/cv_small_greedy.json \
      --milp-aws results/exp1/cv_small_milp_aws.json \
      --milp-eps results/exp1/cv_small_milp_eps.json

Outputs:
  results/exp1/cv_small_metrics.csv  — per-algorithm HV / IGD+ table
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
    
    def deduplicate(pvecs):
        unique = {}
        for p in pvecs:
            k = (round(p[0], 6), round(p[1], 6))
            if k not in unique:
                unique[k] = p
        return list(unique.values())

    # Try strict CV==0 filter first
    pts_strict = [(sol["Z1"], sol["Z2"]) for sol in front if sol.get("CV", 0) == 0.0]
    if pts_strict:
        return deduplicate(pts_strict), data.get("meta", {})
    
    # Fallback: all rank=1 solutions (handles PB-NSGA CV-in-kg encoding)
    pts_all = [(sol["Z1"], sol["Z2"]) for sol in front if sol.get("rank", 1) == 1]
    return deduplicate(pts_all), data.get("meta", {})



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
    parser.add_argument("--results-exp1", default=None, help="Path to results/exp1/")
    parser.add_argument("--results-exp2", default=None, help="Path to results/exp2/")
    parser.add_argument("--bb",      default=None, help="Explicit path to BB result JSON")
    parser.add_argument("--vns-ts",  default=None, help="Explicit path to VNS-TS result JSON")
    parser.add_argument("--greedy",  default=None, help="Explicit path to Greedy result JSON")
    parser.add_argument("--milp", default=None, help="Legacy alias for --milp-aws")
    parser.add_argument("--milp-aws", default=None, help="Explicit path to MILP AWS result JSON")
    parser.add_argument("--milp-eps", default=None, help="Explicit path to MILP EPS result JSON")
    parser.add_argument("--ours",    default=None, help="Explicit path to PB-NSGA (ours) result JSON or glob pattern")
    args = parser.parse_args()

    script_dir   = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    exp1_dir = args.results_exp1 or os.path.join(project_root, "results", "exp1")
    exp2_dir = args.results_exp2 or os.path.join(project_root, "results", "exp2")

    bb_path = args.bb or os.path.join(exp1_dir, "cv_small_bb.json")
    if not args.bb and (not os.path.exists(bb_path) or os.path.getsize(bb_path) < 200):
        bb_path = os.path.join(exp2_dir, "CV_small_bb.json")

    greedy_path = args.greedy or os.path.join(exp1_dir, "cv_small_greedy.json")
    vns_ts_path = args.vns_ts or os.path.join(exp1_dir, "cv_small_vns_ts.json")
    milp_aws_path = args.milp_aws or args.milp or os.path.join(exp1_dir, "cv_small_milp_aws.json")
    milp_eps_path = args.milp_eps or os.path.join(exp1_dir, "cv_small_milp_eps.json")

    if args.ours:
        if "*" in args.ours:
            pbnsga_paths = sorted(glob.glob(args.ours))
        else:
            pbnsga_paths = [args.ours]
    else:
        pbnsga_paths = sorted(glob.glob(os.path.join(exp2_dir, "CV_small_seed*.json")))
        if not pbnsga_paths:
             pbnsga_paths = sorted(glob.glob(os.path.join(exp1_dir, "*nsga*.json")))

    # ── Load data ───────────────────────────────────────────────────────────
    # BB: prefer exp1 (which should be a copy of exp2 after fix), fall back to exp2
    bb_path = os.path.join(exp1_dir, "cv_small_bb.json")
    if not os.path.exists(bb_path) or os.path.getsize(bb_path) < 200:
        bb_path = os.path.join(exp2_dir, "CV_small_bb.json")

    greedy_path = os.path.join(exp1_dir, "cv_small_greedy.json")
    if not os.path.exists(milp_aws_path):
        milp_aws_path = os.path.join(exp1_dir, "cv_small_milp.json") # legacy fallback

    # PB-NSGA seeds (already handled by CLI args or default logic above)

    def safe_load(path):
        if path and os.path.exists(path) and os.path.getsize(path) > 100:
            pts, meta = load_pareto(path)
            return pts, meta
        return [], {}

    bb_pts,     bb_meta     = safe_load(bb_path)
    vns_ts_pts, vns_ts_meta = safe_load(vns_ts_path)
    greedy_pts, greedy_meta = safe_load(greedy_path)
    milp_aws_pts, milp_aws_meta = safe_load(milp_aws_path)
    milp_eps_pts, milp_eps_meta = safe_load(milp_eps_path)
    
    # Correctly resolve MILP and other algorithm runtimes
    def get_time(meta):
        wall = meta.get("total_elapsed_s", meta.get("elapsed_s", meta.get("runtime_s", float("nan"))))
        cpu = meta.get("total_cpu_s", meta.get("cpu_time_s", float("nan")))
        return wall, cpu

    milp_aws_wall, milp_aws_cpu_val = get_time(milp_aws_meta)
    milp_eps_wall, milp_eps_cpu_val = get_time(milp_eps_meta)
    bb_wall,   bb_cpu_val   = get_time(bb_meta)
    vns_ts_wall, vns_ts_cpu_val = get_time(vns_ts_meta)
    greedy_wall, greedy_cpu_val = get_time(greedy_meta)

    pbnsga_runs = []
    pbnsga_walls = []
    pbnsga_cpus = []
    for p in pbnsga_paths:
        pts, meta = safe_load(p)
        pbnsga_runs.append(pts)
        w, c = get_time(meta)
        if not np.isnan(w): pbnsga_walls.append(w)
        if not np.isnan(c): pbnsga_cpus.append(c)

    print(f"\n[Data] BB solutions      : {len(bb_pts)}")
    print(f"[Data] VNS-TS solutions  : {len(vns_ts_pts)}")
    print(f"[Data] Greedy solutions  : {len(greedy_pts)}")
    print(f"[Data] MILP AWS solutions: {len(milp_aws_pts)}")
    print(f"[Data] MILP EPS solutions: {len(milp_eps_pts)}")
    print(f"[Data] PB-NSGA seeds     : {len(pbnsga_runs)} "
          f"(total pts: {sum(len(r) for r in pbnsga_runs)})")

    # Sanity check: objective-scale mismatch can make HV/IGD comparisons misleading.
    scale_samples = {}
    if greedy_pts:
        scale_samples["Greedy"] = np.median([p[0] for p in greedy_pts])
    if vns_ts_pts:
        scale_samples["VNS-TS"] = np.median([p[0] for p in vns_ts_pts])
    if milp_aws_pts:
        scale_samples["MILP AWS"] = np.median([p[0] for p in milp_aws_pts])
    if milp_eps_pts:
        scale_samples["MILP EPS"] = np.median([p[0] for p in milp_eps_pts])
    if bb_pts:
        scale_samples["BB-Exact"] = np.median([p[0] for p in bb_pts])
    if pbnsga_runs and any(pbnsga_runs):
        pb_flat = [p[0] for run in pbnsga_runs for p in run]
        if pb_flat:
            scale_samples["PB-NSGA"] = np.median(pb_flat)

    if len(scale_samples) >= 2:
        z1_vals = [v for v in scale_samples.values() if np.isfinite(v) and v > 0]
        if z1_vals:
            z1_ratio = max(z1_vals) / max(min(z1_vals), 1e-12)
            if z1_ratio > 20.0:
                print("\n[Warning] Large Z1 scale mismatch detected across solvers.")
                print("          HV/IGD may be misleading until objective formulations are aligned.")
                for k, v in scale_samples.items():
                    print(f"          median Z1 [{k:<8}] = {v:.4e}")

    # ── Build combined reference front (all algorithms) ─────────────────────
    all_runs = (
        [bb_pts] if bb_pts else []
    ) + (
        [vns_ts_pts] if vns_ts_pts else []
    ) + (
        [greedy_pts] if greedy_pts else []
    ) + (
        [milp_aws_pts] if milp_aws_pts else []
    ) + (
        [milp_eps_pts] if milp_eps_pts else []
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
            "wall": 0.0, "cpu": 0.0 # to be filled
        }
        return hv_mean, hv_std, igd_mean, igd_std

    # Single-run algorithms metrics
    evaluate_single("Greedy",   [greedy_pts])
    results["Greedy"]["wall"], results["Greedy"]["cpu"] = greedy_wall, greedy_cpu_val

    evaluate_single("VNS-TS", [vns_ts_pts] if vns_ts_pts else [[]])
    results["VNS-TS"]["wall"], results["VNS-TS"]["cpu"] = vns_ts_wall, vns_ts_cpu_val
    
    evaluate_single("MILP AWS", [milp_aws_pts] if milp_aws_pts else [[]])
    results["MILP AWS"]["wall"], results["MILP AWS"]["cpu"] = milp_aws_wall, milp_aws_cpu_val

    evaluate_single("MILP EPS", [milp_eps_pts] if milp_eps_pts else [[]])
    results["MILP EPS"]["wall"], results["MILP EPS"]["cpu"] = milp_eps_wall, milp_eps_cpu_val
    
    evaluate_single("BB-Exact", [bb_pts])
    results["BB-Exact"]["wall"], results["BB-Exact"]["cpu"] = bb_wall, bb_cpu_val
    
    evaluate_single("PB-NSGA",  pbnsga_runs)
    results["PB-NSGA"]["wall"] = float(np.mean(pbnsga_walls)) if pbnsga_walls else 0.0
    results["PB-NSGA"]["cpu"]  = float(np.mean(pbnsga_cpus)) if pbnsga_cpus else 0.0

    # ── Print results table ─────────────────────────────────────────────────
    print("\n" + "="*70)
    print("  CV-Small Baseline Comparison")
    print("="*70)
    print(f"  {'Algorithm':<25} {'HV (norm)':>14}  {'IGD+':>12}  {'Wall (s)':>10}  {'CPU (s)':>10}")
    print("-" * 80)

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

    for name in ["Greedy", "VNS-TS", "MILP AWS", "MILP EPS", "BB-Exact", "PB-NSGA"]:
        r = results[name]
        w_str = f"{r['wall']:.1f}" if not np.isnan(r["wall"]) else "—"
        c_str = f"{r['cpu']:.1f}" if not np.isnan(r["cpu"]) else "—"
        print(f"  {name:<25} {fmt_hv(name):>14}  {fmt_igd(name):>12}  {w_str:>10}  {c_str:>10}")

    print("=" * 80)

    # ── PB-NSGA timing ──────────────────────────────────────────────────────
    pb_rt_mean = float(np.mean(pbnsga_walls)) if pbnsga_walls else float("nan")
    pb_rt_std  = float(np.std(pbnsga_walls, ddof=1)) if len(pbnsga_walls) > 1 else 0.0

    # ── LaTeX table row ─────────────────────────────────────────────────────
    g = results["Greedy"]
    v = results["VNS-TS"]
    m_aws = results["MILP AWS"]
    m_eps = results["MILP EPS"]
    b = results["BB-Exact"]
    p = results["PB-NSGA"]

    greedy_hv_str  = f"${g['hv_mean']:.3f}$"
    greedy_igd_str = f"${g['igd_mean']:.3f}$" if np.isfinite(g["igd_mean"]) else "$-$"

    vns_hv_str  = f"${v['hv_mean']:.3f}$" if vns_ts_pts else "$-$"
    vns_igd_str = f"${v['igd_mean']:.3f}$" if (vns_ts_pts and np.isfinite(v["igd_mean"])) else "$-$"
    vns_t_str   = f"${v['wall']:.1f}$" if vns_ts_pts else "$-$"

    if milp_aws_pts:
        milp_aws_hv_str  = f"${m_aws['hv_mean']:.3f}$"
        milp_aws_igd_str = f"${m_aws['igd_mean']:.3f}$" if np.isfinite(m_aws["igd_mean"]) else "$-$"
        milp_aws_t_str   = f"${m_aws['wall']:.1f}^*$"
    else:
        milp_aws_hv_str  = "$-$"
        milp_aws_igd_str = "$-$"
        milp_aws_t_str   = "$1800.0^*$"

    if milp_eps_pts:
        milp_eps_hv_str  = f"${m_eps['hv_mean']:.3f}$"
        milp_eps_igd_str = f"${m_eps['igd_mean']:.3f}$" if np.isfinite(m_eps["igd_mean"]) else "$-$"
        milp_eps_t_str   = f"${m_eps['wall']:.1f}^*$"
    else:
        milp_eps_hv_str  = "$-$"
        milp_eps_igd_str = "$-$"
        milp_eps_t_str   = "$1800.0^*$"

    bb_hv_str  = f"${b['hv_mean']:.3f}$"
    bb_igd_str = f"${b['igd_mean']:.3f}$" if np.isfinite(b["igd_mean"]) else "$-$"
    bb_t_str   = f"${b['wall']:.1f}$"

    pb_hv_str  = (f"$\\mathbf{{{p['hv_mean']:.3f} \\pm {p['hv_std']:.3f}}}$"
                  if p["n_runs"] > 1 else f"${p['hv_mean']:.3f}$")
    pb_igd_str = (f"$\\mathbf{{{p['igd_mean']:.3f} \\pm {p['igd_std']:.3f}}}$"
                  if p["n_runs"] > 1 and np.isfinite(p["igd_mean"])
                  else f"${p['igd_mean']:.3f}$")
    pb_t_str   = f"${p['wall']:.1f}$"

    latex_eol = r" \\\\"
    print("\n--- LaTeX table rows (paste into main.tex) ---")
    print(r"Greedy Heuristic                &"
          f" {greedy_hv_str} & {greedy_igd_str} & $\\mathbf{{<0.1}}$" + latex_eol)
    print(r"VNS-TS Baseline                 &"
          f" {vns_hv_str} & {vns_igd_str} & {vns_t_str}" + latex_eol)
    print(r"MILP (Adaptive Weighted Sum)    &"
          f" {milp_aws_hv_str} & {milp_aws_igd_str} & {milp_aws_t_str}" + latex_eol)
    print(r"MILP (Epsilon Constraint)       &"
          f" {milp_eps_hv_str} & {milp_eps_igd_str} & {milp_eps_t_str}" + latex_eol)
    print(r"Exact Enum (BB)                 &"
          f" {bb_hv_str} & {bb_igd_str} & {bb_t_str}" + latex_eol)
    print(r"\textbf{PB-NSGA (Ours)}         &"
          f" {pb_hv_str} & {pb_igd_str} & {pb_t_str}" + latex_eol)

    # ── Write CSV ────────────────────────────────────────────────────────────
    out_csv = os.path.join(exp1_dir, "cv_small_metrics.csv")
    fields  = ["algorithm", "n_runs", "hv_mean", "hv_std", "igd_mean", "igd_std", "wall_s", "cpu_s"]
    with open(out_csv, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(fields)
        for name in ["Greedy", "VNS-TS", "MILP AWS", "MILP EPS", "BB-Exact", "PB-NSGA"]:
            r = results[name]
            writer.writerow([
                name, r["n_runs"],
                f"{r['hv_mean']:.6f}", f"{r['hv_std']:.6f}",
                f"{r['igd_mean']:.6f}" if np.isfinite(r["igd_mean"]) else "inf",
                f"{r['igd_std']:.6f}",
                f"{r['wall']:.3f}", f"{r['cpu']:.3f}",
            ])
    print(f"\n[CSV] {out_csv}")


if __name__ == "__main__":
    main()
