#!/usr/bin/env python3
import csv
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv/bin/python"
DATA = ROOT / "data/cv/cv_small_drnd.json"
RES = ROOT / "results/exp1"
OUT = RES / "cv_small_milp_aws.json"
MET = RES / "cv_small_metrics.csv"
OURS = RES / "cv_small_pb_nsga.json"
GREEDY = RES / "cv_small_greedy.json"
RESULTS = ROOT / "tmp/milp_aws_tune_results.csv"

GRID_N = [4, 6, 8, 10, 12]
GRID_D = [0.03, 0.05, 0.07, 0.09, 0.12, 0.15]
TIME_LIMIT = 30


def run(cmd):
    subprocess.run(cmd, check=True, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def read_milp_metrics():
    with MET.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row["algorithm"].strip().lower() == "milp aws":
            return float(row["hv_mean"]), float(row["igd_mean"])
    raise RuntimeError("MILP AWS row missing in metrics file")


def read_front_stats():
    with OUT.open("r", encoding="utf-8") as f:
        d = json.load(f)
    return len(d.get("pareto_front", [])), float(d.get("meta", {}).get("total_elapsed_s", 0.0))


def main():
    records = []
    for n in GRID_N:
        for d in GRID_D:
            run([
                str(PY),
                "src/solver/milp_aws_baseline.py",
                "--instance", str(DATA),
                "--out", str(OUT),
                "--time_limit", str(TIME_LIMIT),
                "--n_initial", str(n),
                "--delta_j", str(d),
            ])
            run([
                str(PY),
                "src/scripts/exp1_evaluate_cv_small.py",
                "--results-exp1", str(RES),
                "--ours", str(OURS),
                "--greedy", str(GREEDY),
                "--milp", str(OUT),
            ])
            hv, igd = read_milp_metrics()
            points, elapsed = read_front_stats()
            records.append({
                "n_initial": n,
                "delta_j": d,
                "hv": hv,
                "igd": igd,
                "points": points,
                "elapsed_s": elapsed,
            })
            print(f"tested n={n} d={d:.2f} -> HV={hv:.6f} IGD={igd:.6f} points={points} t={elapsed:.2f}s")

    records.sort(key=lambda r: (-r["hv"], r["igd"], -r["points"], r["elapsed_s"]))

    with RESULTS.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["n_initial", "delta_j", "hv", "igd", "points", "elapsed_s"])
        w.writeheader()
        w.writerows(records)

    print("\nTop 8 configurations:")
    for r in records[:8]:
        print(
            f"n={r['n_initial']}, d={r['delta_j']:.2f}, HV={r['hv']:.6f}, "
            f"IGD={r['igd']:.6f}, pts={r['points']}, t={r['elapsed_s']:.2f}s"
        )


if __name__ == "__main__":
    main()
