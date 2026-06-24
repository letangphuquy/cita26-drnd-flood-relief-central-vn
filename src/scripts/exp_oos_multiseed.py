"""
exp_oos_multiseed.py — Multi-seed SAA/OOS evaluation for CV-Large PB-NSGA results
==================================================================================
Runs ``evaluate_oos`` over all 20 PB-NSGA seeds (and optionally all baseline
seeds) against both the SAA-100 training set and the OOS-10 adversarial set.

Outputs per seed (written to results/exp2/):
    CV_large_seed{N}_saa_eval.json
    CV_large_seed{N}_oos_eval.json

Then calls exp2_analyze_saa_oos.py --multi-seed to aggregate across seeds.

Usage (from project root):
    python src/scripts/exp_oos_multiseed.py [--seeds 0-19] [--dry-run]
    python src/scripts/exp_oos_multiseed.py --seeds 0-4 --also-baselines
"""

import argparse
import pathlib
import subprocess
import sys

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_seed_range(spec: str):
    """Parse '0-19' or '0,1,2' into a sorted list of ints."""
    result = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            result.extend(range(int(lo), int(hi) + 1))
        else:
            result.append(int(part))
    return sorted(set(result))


def run_eval(evaluator: pathlib.Path, dataset: pathlib.Path,
             front: pathlib.Path, out: pathlib.Path, dry_run: bool):
    """Run evaluate_oos and return True on success."""
    if not front.exists():
        print(f"  [skip] front file not found: {front}")
        return False
    if out.exists():
        print(f"  [cached] {out.name}")
        return True
    cmd = [str(evaluator), str(dataset), str(front), str(out)]
    print(f"  {' '.join(cmd)}")
    if dry_run:
        return True
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [ERROR] {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Multi-seed SAA/OOS evaluation for CV-Large")
    ap.add_argument("--seeds", default="0-19",
                    help="Seed range/list for PB-NSGA (default: 0-19)")
    ap.add_argument("--also-baselines", action="store_true",
                    help="Also evaluate VNS-TS (seeds 0-4) and GWO-HD (seeds 0-19)")
    ap.add_argument("--vns-seeds", default="0-4",
                    help="Seed range for VNS-TS if --also-baselines (default: 0-4)")
    ap.add_argument("--gwo-seeds", default="0-19",
                    help="Seed range for GWO-HD if --also-baselines (default: 0-19)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print commands without executing them")
    ap.add_argument("--skip-aggregate", action="store_true",
                    help="Skip the multi-seed aggregation step at the end")
    # Path arguments — required, no defaults.
    # Legacy paths (do not restore as defaults):
    #   --results-dir: results/exp2
    #   --saa-data:    data/prep/cv_large_saa100.json
    #   --oos-data:    data/prep/cv_large_oos10.json
    ap.add_argument("--results-dir", required=True,
                    help="Directory containing CV-Large PB-NSGA seed result JSONs and output eval files")
    ap.add_argument("--saa-data", required=True,
                    help="Path to SAA-100 evaluation dataset JSON")
    ap.add_argument("--oos-data", required=True,
                    help="Path to OOS-10 adversarial evaluation dataset JSON")
    args = ap.parse_args()

    project = pathlib.Path(__file__).resolve().parents[2]
    solver_dir = project / "src" / "solver"
    res2     = pathlib.Path(args.results_dir)
    saa_data = pathlib.Path(args.saa_data)
    oos_data = pathlib.Path(args.oos_data)

    # Validate prerequisites
    if not evaluator.exists():
        print(f"[Error] evaluate_oos not found at {evaluator}. Compile first.")
        sys.exit(1)
    for ds in (saa_data, oos_data):
        if not ds.exists():
            print(f"[Error] Dataset not found: {ds}")
            sys.exit(1)

    res2.mkdir(parents=True, exist_ok=True)

    # Build list of (front_path, tag_prefix) tuples to evaluate
    tasks = []

    pbnsga_seeds = parse_seed_range(args.seeds)
    for seed in pbnsga_seeds:
        front = res2 / f"cv_large_seed{seed}.json"
        tasks.append((front, f"CV_large_seed{seed}"))

    if args.also_baselines:
        for seed in parse_seed_range(args.vns_seeds):
            front = res2 / f"cv_large_vns_ts_seed{seed}.json"
            tasks.append((front, f"CV_large_vns_ts_seed{seed}"))
        for seed in parse_seed_range(args.gwo_seeds):
            front = res2 / f"cv_large_gwo_hd_seed{seed}.json"
            tasks.append((front, f"CV_large_gwo_hd_seed{seed}"))

    total = len(tasks) * 2
    done = 0
    errors = 0

    print(f"\n[OOS Multi-seed] Evaluating {len(tasks)} fronts × 2 datasets = {total} runs")
    for front, tag in tasks:
        print(f"\n  Front: {front.name}")
        for ds_tag, ds_path in [("saa", saa_data), ("oos", oos_data)]:
            out = res2 / f"{tag}_{ds_tag}_eval.json"
            ok = run_eval(evaluator, ds_path, front, out, args.dry_run)
            if ok:
                done += 1
            else:
                errors += 1

    print(f"\n[OOS Multi-seed] Done: {done}/{total}  Errors: {errors}")

    if args.skip_aggregate or args.dry_run:
        return

    # Run multi-seed aggregation
    analyzer = project / "src" / "scripts" / "exp2_analyze_saa_oos.py"
    python = sys.executable
    cmd = [python, str(analyzer), "--multi-seed",
           "--results-dir", str(res2),
           "--out", str(res2 / "exp2_saa_oos_multiseed_summary.json")]
    print(f"\n[OOS Multi-seed] Aggregating: {' '.join(cmd)}")
    subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()
