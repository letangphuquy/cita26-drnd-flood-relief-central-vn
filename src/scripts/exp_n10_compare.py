"""
exp_n10_compare.py — N=10 vs N=3 OOS generalization ablation
=============================================================
Evaluates the 20 PB-NSGA seeds trained on N=10 scenarios on both
the SAA-100 and OOS-10 sets, then computes delta feasibility and
delta Z2 gap (N=10 − N=3) with bootstrap CI.

Usage (from project root):
    python src/scripts/exp_n10_compare.py
    python src/scripts/exp_n10_compare.py --n10-results results/exp2/n10 --dry-run

Output:
    results/exp2/n10/exp_n10_oos_multiseed_summary.json
    results/exp2/n10/exp_n10_vs_n3_comparison.json   (delta table with CI)
    Printed comparison table to stdout
"""

import argparse
import json
import math
import os
import pathlib
import random
import subprocess
import sys

_SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parents[1]
sys.path.insert(0, str(_SCRIPT_DIR))

from exp2_analyze_saa_oos import (
    _load_evals, _mean, _std, _bootstrap_ci, _seed_stats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_eval(evaluator, dataset, front, out, dry_run=False):
    if not front.exists():
        print(f"  [skip] front not found: {front}")
        return False
    if out.exists():
        print(f"  [cached] {out.name}")
        return True
    cmd = [str(evaluator), str(dataset), str(front), str(out)]
    print(f"  {' '.join(cmd)}")
    if dry_run:
        return True
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [ERROR] {r.stderr.strip()}", file=sys.stderr)
        return False
    return True


def load_n3_aggregate(n3_summary_path):
    """Load per-algorithm aggregate from the N=3 multi-seed summary."""
    with open(n3_summary_path) as f:
        data = json.load(f)
    return data.get("PB-NSGA", {}).get("aggregate", {})


def bootstrap_delta_ci(vals_a, vals_b, n_boot=4000, ci=0.95, rng_seed=77):
    """
    Bootstrap CI for mean(A) - mean(B).
    Returns (delta_mean, ci_lo, ci_hi).
    """
    if not vals_a or not vals_b:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(rng_seed)
    na, nb = len(vals_a), len(vals_b)
    boot_deltas = sorted(
        _mean(rng.choices(vals_a, k=na)) - _mean(rng.choices(vals_b, k=nb))
        for _ in range(n_boot)
    )
    lo = boot_deltas[int((1 - ci) / 2 * n_boot)]
    hi = boot_deltas[int((1 + ci) / 2 * n_boot)]
    delta = _mean(vals_a) - _mean(vals_b)
    return delta, lo, hi


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="N=10 vs N=3 OOS ablation comparison")
    ap.add_argument("--n10-results", default=None,
                    help="Dir with cv_large_n10_seed{N}.json (default: results/exp2/n10)")
    ap.add_argument("--n3-summary", default=None,
                    help="Multi-seed summary from N=3 run "
                         "(default: results/exp2/exp2_saa_oos_multiseed_summary.json)")
    ap.add_argument("--seeds", default="0-19",
                    help="Seeds to evaluate (default: 0-19)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    solver_dir  = _PROJECT_DIR / "src" / "solver"
    evaluator   = solver_dir / "evaluate_oos"
    saa_data    = _PROJECT_DIR / "data" / "prep" / "cv_large_saa100.json"
    oos_data    = _PROJECT_DIR / "data" / "prep" / "cv_large_oos10.json"

    n10_dir = pathlib.Path(args.n10_results) if args.n10_results else (
        _PROJECT_DIR / "results" / "exp2" / "n10"
    )
    n3_summary_path = pathlib.Path(args.n3_summary) if args.n3_summary else (
        _PROJECT_DIR / "results" / "exp2" / "exp2_saa_oos_multiseed_summary.json"
    )

    # Parse seed range
    seeds = []
    for part in args.seeds.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            seeds.extend(range(int(lo), int(hi) + 1))
        else:
            seeds.append(int(part))
    seeds = sorted(set(seeds))

    # Validate
    for path in (evaluator, saa_data, oos_data):
        if not path.exists():
            print(f"[Error] Not found: {path}")
            sys.exit(1)

    n10_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Run evaluate_oos for each N=10 seed on SAA and OOS ──
    print(f"\n[N10 Compare] Evaluating {len(seeds)} N=10 seeds × 2 datasets")
    errors = 0
    for seed in seeds:
        front = n10_dir / f"cv_large_n10_seed{seed}.json"
        for ds_tag, ds_path in [("saa", saa_data), ("oos", oos_data)]:
            out = n10_dir / f"CV_large_n10_seed{seed}_{ds_tag}_eval.json"
            ok = run_eval(evaluator, ds_path, front, out, args.dry_run)
            if not ok:
                errors += 1

    if errors:
        print(f"[Warning] {errors} evaluation errors — results may be incomplete")

    # ── Step 2: Aggregate N=10 seed stats ──
    print(f"\n[N10 Compare] Aggregating N=10 statistics...")
    saa_feas_rates_n10, oos_feas_rates_n10, oos_z2_diffs_n10 = [], [], []
    per_seed_n10 = {}

    for seed in seeds:
        row = {"seed": seed}
        for ds_tag, feas_list, z2_list in [
            ("saa", saa_feas_rates_n10, None),
            ("oos", oos_feas_rates_n10, oos_z2_diffs_n10),
        ]:
            eval_path = n10_dir / f"CV_large_n10_seed{seed}_{ds_tag}_eval.json"
            if not eval_path.exists():
                continue
            evals = _load_evals(str(eval_path))
            stats = _seed_stats(evals)
            row[ds_tag] = stats
            feas_list.append(stats["feasibility_rate"])
            if z2_list is not None:
                z2_list.append(stats["mean_z2_diff_pct"])
        per_seed_n10[seed] = row

    def _agg(vals, label):
        if not vals:
            return {}
        m = _mean(vals)
        s = _std(vals)
        lo, hi = _bootstrap_ci(vals)
        print(f"  {label}: mean={m:.4f}  std={s:.4f}  95% CI=[{lo:.4f}, {hi:.4f}]  (n={len(vals)})")
        return {"mean": round(m, 6), "std": round(s, 6),
                "ci95_lo": round(lo, 6), "ci95_hi": round(hi, 6), "n": len(vals)}

    print(f"\n  N=10 PB-NSGA ({len(seeds)} seeds):")
    agg_n10 = {
        "saa_feasibility_rate": _agg(saa_feas_rates_n10, "SAA feas rate"),
        "oos_feasibility_rate": _agg(oos_feas_rates_n10, "OOS feas rate"),
        "oos_z2_diff_pct":      _agg(oos_z2_diffs_n10,  "OOS ΔZ2 (%)"),
    }

    n10_summary = {"per_seed": per_seed_n10, "aggregate": agg_n10}
    n10_summary_path = n10_dir / "exp_n10_oos_multiseed_summary.json"
    with open(n10_summary_path, "w") as f:
        json.dump(n10_summary, f, indent=2)
    print(f"\n[Saved] {n10_summary_path}")

    # ── Step 3: Delta comparison vs N=3 ──
    print(f"\n[N10 Compare] Computing deltas vs N=3 PB-NSGA...")

    if not n3_summary_path.exists():
        print(f"[Warning] N=3 summary not found at {n3_summary_path} — skipping delta")
        return

    n3_agg = load_n3_aggregate(n3_summary_path)

    # Extract N=3 per-seed values from summary for bootstrap
    with open(n3_summary_path) as f:
        n3_full = json.load(f)
    n3_seeds = n3_full.get("PB-NSGA", {}).get("per_seed", {})
    n3_oos_feas = [v["oos"]["feasibility_rate"] for v in n3_seeds.values() if "oos" in v]
    n3_oos_z2   = [v["oos"]["mean_z2_diff_pct"] for v in n3_seeds.values() if "oos" in v]

    print(f"\n{'='*68}")
    print(f"{'Metric':<30} {'N=10':>10} {'N=3':>10} {'Δ(10-3)':>10}  95% CI")
    print(f"{'='*68}")

    comparison = {}
    for metric, vals_n10, vals_n3, label in [
        ("oos_feasibility_rate", oos_feas_rates_n10, n3_oos_feas, "OOS Feasibility Rate"),
        ("oos_z2_diff_pct",      oos_z2_diffs_n10,   n3_oos_z2,   "OOS ΔZ2 (%)"),
    ]:
        m10 = _mean(vals_n10) if vals_n10 else float("nan")
        m3  = _mean(vals_n3)  if vals_n3  else float("nan")
        delta, lo, hi = bootstrap_delta_ci(vals_n10, vals_n3)
        print(f"  {label:<28} {m10:>10.4f} {m3:>10.4f} {delta:>+10.4f}  [{lo:+.4f}, {hi:+.4f}]")
        comparison[metric] = {
            "n10_mean": round(m10, 6), "n3_mean": round(m3, 6),
            "delta": round(delta, 6), "ci95_lo": round(lo, 6), "ci95_hi": round(hi, 6),
        }

    print(f"{'='*68}")
    note = ("Note: positive Δ = N=10 higher than N=3. "
            "For feasibility rate, Δ≈0 confirms N=3 already achieves saturation. "
            "For OOS ΔZ2, higher = larger cost penalty under stress scenarios.")
    print(f"\n{note}")

    comp_path = n10_dir / "exp_n10_vs_n3_comparison.json"
    with open(comp_path, "w") as f:
        json.dump({
            "note": note,
            "n10_seeds": len(seeds),
            "n3_seeds": len(n3_oos_feas),
            "metrics": comparison,
        }, f, indent=2)
    print(f"\n[Saved] {comp_path}")


if __name__ == "__main__":
    main()
