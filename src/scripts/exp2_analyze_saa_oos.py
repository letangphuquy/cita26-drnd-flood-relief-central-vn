"""exp2_analyze_saa_oos.py - SAA/OOS diagnostic summary (single-seed and multi-seed).

Single-seed mode (original):
    python src/scripts/exp2_analyze_saa_oos.py \
        --saa-eval results/exp2/CV_large_seed0_saa_eval.json \
        --oos-eval results/exp2/CV_large_seed0_oos_eval.json

Multi-seed mode (aggregates all PB-NSGA seeds + optional baselines):
    python src/scripts/exp2_analyze_saa_oos.py \
        --multi-seed \
        --results-dir results/exp2 \
        --out results/exp2/exp2_saa_oos_multiseed_summary.json
"""

import argparse
import json
import math
import os
import pathlib
import re
import random


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _load_evals(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("evaluations", [])


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _bootstrap_ci(values, n_boot=2000, ci=0.95, rng_seed=42):
    """Return (lower, upper) bootstrap percentile CI for the mean."""
    if not values:
        return float("nan"), float("nan")
    rng = random.Random(rng_seed)
    n = len(values)
    boot_means = sorted(
        _mean(rng.choices(values, k=n)) for _ in range(n_boot)
    )
    lo = boot_means[int((1 - ci) / 2 * n_boot)]
    hi = boot_means[int((1 + ci) / 2 * n_boot)]
    return lo, hi


def _seed_stats(evals):
    """Compute per-seed statistics from an evaluations list."""
    cv = [sol["new_CV"] for sol in evals]
    feasible = sum(1 for c in cv if c <= 1e-9)
    feasibility_rate = feasible / max(1, len(cv))
    z2_vals = [sol["new_Z2"] for sol in evals]
    return {
        "n_evaluations": len(evals),
        "feasible_count": feasible,
        "feasibility_rate": round(feasibility_rate, 4),
        "mean_cv": round(_mean(cv), 6),
        "mean_z2": round(_mean(z2_vals), 4),
        "mean_z2_diff_pct": round(
            _mean([
                (sol["new_Z2"] - sol["orig_Z2"]) / max(1.0, sol["orig_Z2"]) * 100.0
                for sol in evals
            ]), 4
        ),
    }


# ---------------------------------------------------------------------------
# Single-seed mode
# ---------------------------------------------------------------------------

def analyze(saa_path, oos_path, out_json=None):
    saa_data = _load_evals(saa_path)
    oos_data = _load_evals(oos_path)

    z1_diffs = [
        (sol["new_Z1"] - sol["orig_Z1"]) / max(1.0, sol["orig_Z1"]) * 100.0
        for sol in saa_data
    ]
    z2_diffs = [
        (sol["new_Z2"] - sol["orig_Z2"]) / max(1.0, sol["orig_Z2"]) * 100.0
        for sol in saa_data
    ]
    cv_saa = [sol["new_CV"] for sol in saa_data]
    cv_oos = [sol["new_CV"] for sol in oos_data]

    summary = {
        "saa": {
            "file": saa_path,
            "n_evaluations": len(saa_data),
            "mean_z1_diff_pct": _mean(z1_diffs),
            "mean_z2_diff_pct": _mean(z2_diffs),
            "mean_cv": _mean(cv_saa),
            "feasible_count": sum(1 for c in cv_saa if c <= 1e-9),
            "feasibility_rate": sum(1 for c in cv_saa if c <= 1e-9) / max(1, len(cv_saa)),
        },
        "oos": {
            "file": oos_path,
            "n_evaluations": len(oos_data),
            "mean_cv": _mean(cv_oos),
            "feasible_count": sum(1 for c in cv_oos if c <= 1e-9),
            "feasibility_rate": sum(1 for c in cv_oos if c <= 1e-9) / max(1, len(cv_oos)),
            "mean_z2": _mean([sol["new_Z2"] for sol in oos_data]),
            "mean_z2_diff_pct": _mean([
                (sol["new_Z2"] - sol["orig_Z2"]) / max(1.0, sol["orig_Z2"]) * 100.0
                for sol in oos_data
            ]),
        },
    }

    print("--- SAA EVALUATION ---")
    print(f"File               : {saa_path}")
    print(f"Mean Z1 difference : {summary['saa']['mean_z1_diff_pct']:.2f}%")
    print(f"Mean Z2 difference : {summary['saa']['mean_z2_diff_pct']:.2f}%")
    print(f"Mean CV in SAA     : {summary['saa']['mean_cv']:.4f}")
    print(f"Feasible solutions : {summary['saa']['feasible_count']} / {summary['saa']['n_evaluations']}")
    print(f"Feasibility rate   : {summary['saa']['feasibility_rate']:.1%}")

    print("\n--- OOS EVALUATION ---")
    print(f"File               : {oos_path}")
    print(f"Mean CV in OOS     : {summary['oos']['mean_cv']:.4f}")
    print(f"Feasible solutions : {summary['oos']['feasible_count']} / {summary['oos']['n_evaluations']}")
    print(f"Feasibility rate   : {summary['oos']['feasibility_rate']:.1%}")
    print(f"Mean Z2 diff (OOS) : {summary['oos']['mean_z2_diff_pct']:.2f}%")

    if out_json:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"\n[Saved] {out_json}")


# ---------------------------------------------------------------------------
# Multi-seed mode
# ---------------------------------------------------------------------------

def discover_eval_files(results_dir):
    """
    Scans results_dir for *_saa_eval.json / *_oos_eval.json pairs.
    Returns dict: {algo_tag: {seed: {"saa": path, "oos": path}}}

    Recognised patterns:
      CV_large_seed{N}_saa_eval.json          -> PB-NSGA seed N
      CV_large_vns_ts_seed{N}_saa_eval.json   -> VNS-TS seed N
      CV_large_gwo_hd_seed{N}_saa_eval.json   -> GWO-HD seed N
    """
    pat = re.compile(
        r"^CV_large(?:_(vns_ts|gwo_hd))?_seed(\d+)_(saa|oos)_eval\.json$",
        re.IGNORECASE,
    )
    algos = {}
    for fname in sorted(os.listdir(results_dir)):
        m = pat.match(fname)
        if not m:
            continue
        algo_tag_raw, seed_s, ds_tag = m.groups()
        algo = "PB-NSGA" if algo_tag_raw is None else algo_tag_raw.upper().replace("_", "-")
        seed = int(seed_s)
        algos.setdefault(algo, {}).setdefault(seed, {})[ds_tag] = os.path.join(results_dir, fname)
    return algos


def analyze_multiseed(results_dir, out_json=None):
    algos = discover_eval_files(results_dir)
    if not algos:
        print(f"[Warning] No *_eval.json files found in {results_dir}")
        return

    report = {}
    for algo, seeds_dict in sorted(algos.items()):
        print(f"\n{'='*60}")
        print(f"Algorithm: {algo}  ({len(seeds_dict)} seeds)")
        print(f"{'='*60}")

        per_seed = {}
        saa_feas_rates, oos_feas_rates = [], []
        oos_z2_diffs = []

        for seed in sorted(seeds_dict.keys()):
            pair = seeds_dict[seed]
            row = {"seed": seed}
            if "saa" in pair:
                evals = _load_evals(pair["saa"])
                stats = _seed_stats(evals)
                row["saa"] = stats
                saa_feas_rates.append(stats["feasibility_rate"])
            if "oos" in pair:
                evals = _load_evals(pair["oos"])
                stats = _seed_stats(evals)
                row["oos"] = stats
                oos_feas_rates.append(stats["feasibility_rate"])
                oos_z2_diffs.append(stats["mean_z2_diff_pct"])
            per_seed[seed] = row

            # Per-seed printout
            saa_fr = row.get("saa", {}).get("feasibility_rate", float("nan"))
            oos_fr = row.get("oos", {}).get("feasibility_rate", float("nan"))
            oos_z2 = row.get("oos", {}).get("mean_z2_diff_pct", float("nan"))
            print(f"  seed {seed:2d}: SAA feas={saa_fr:.1%}  OOS feas={oos_fr:.1%}  OOS ΔZ2={oos_z2:+.1f}%")

        # Aggregate across seeds
        def _agg(vals, label):
            if not vals:
                return {}
            m = _mean(vals)
            s = _std(vals)
            lo, hi = _bootstrap_ci(vals)
            print(f"\n  {label}: mean={m:.4f}  std={s:.4f}  95% CI=[{lo:.4f}, {hi:.4f}]  (n={len(vals)})")
            return {"mean": round(m, 6), "std": round(s, 6), "ci95_lo": round(lo, 6), "ci95_hi": round(hi, 6), "n": len(vals)}

        agg = {}
        agg["saa_feasibility_rate"] = _agg(saa_feas_rates, "SAA feasibility rate")
        agg["oos_feasibility_rate"] = _agg(oos_feas_rates, "OOS feasibility rate")
        agg["oos_z2_diff_pct"]      = _agg(oos_z2_diffs,  "OOS ΔZ2 (%)")

        report[algo] = {"per_seed": per_seed, "aggregate": agg}

    if out_json:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\n[Saved] {out_json}")
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze SAA/OOS evaluation outputs")
    # Single-seed args
    parser.add_argument("--saa-eval", default=None, help="Path to *_saa_eval.json (single-seed mode)")
    parser.add_argument("--oos-eval", default=None, help="Path to *_oos_eval.json (single-seed mode)")
    # Multi-seed args
    parser.add_argument("--multi-seed", action="store_true", help="Aggregate all seeds in --results-dir")
    parser.add_argument("--results-dir", default=None, help="Directory containing *_eval.json files (multi-seed)")
    # Common
    parser.add_argument("--out", default=None, help="Path to write summary JSON")
    args = parser.parse_args()

    if args.multi_seed:
        if not args.results_dir:
            # Default: project root / results / exp2
            _script_dir = os.path.dirname(os.path.abspath(__file__))
            args.results_dir = os.path.join(
                os.path.dirname(os.path.dirname(_script_dir)), "results", "exp2"
            )
        analyze_multiseed(args.results_dir, args.out)
    else:
        if not args.saa_eval or not args.oos_eval:
            parser.error("--saa-eval and --oos-eval are required in single-seed mode")
        analyze(args.saa_eval, args.oos_eval, args.out)

