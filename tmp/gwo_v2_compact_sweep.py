#!/usr/bin/env python3
import csv
import itertools
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOLVER = ROOT / "src/solver/gwo_hd_baseline"
SRC = ROOT / "src/solver/gwo_hd_baseline.cpp"
DATA = ROOT / "data/cv/cv_small_drnd.json"
OUT = ROOT / "results/exp1/cv_small_gwo_hd.json"
METRICS = ROOT / "results/exp1/cv_small_metrics.csv"
EVAL = ROOT / "src/scripts/exp1_evaluate_cv_small.py"

PB = ROOT / "results/exp1/cv_small_pb_nsga.json"
BB = ROOT / "results/exp1/cv_small_bb.json"
VNS = ROOT / "results/exp1/cv_small_vns_ts.json"
GREEDY = ROOT / "results/exp1/cv_small_greedy.json"
MILP_AWS = ROOT / "results/exp1/cv_small_milp_aws.json"
MILP_EPS = ROOT / "results/exp1/cv_small_milp_eps.json"


def run(cmd):
    subprocess.run(cmd, check=True)


def read_gwo_metrics(path: Path):
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row["algorithm"] == "GWO-HD":
            return {
                "hv": float(row["hv_mean"]),
                "igd_plus": float(row["igd_mean"]),
                "wall": float(row.get("wall_s", "nan")),
            }
    raise RuntimeError("GWO-HD row not found in metrics")


def main():
    run(["g++", "-O3", "-std=c++17", str(SRC), "-o", str(SOLVER)])

    grid = {
        "wolves": [24, 30],
        "iter": [420, 560],
        "fracA_start": [0.35, 0.45],
        "fracX_start": [0.25, 0.35],
        "accept_worse": [0.03, 0.08],
        "stagnation_limit": [20, 35],
        "keep_ratio": [0.45, 0.60],
    }

    keys = list(grid.keys())
    combos = list(itertools.product(*(grid[k] for k in keys)))

    records = []
    for i, vals in enumerate(combos, start=1):
        cfg = dict(zip(keys, vals))
        cmd = [
            str(SOLVER), str(DATA),
            "--seed", "42",
            "--wolves", str(cfg["wolves"]),
            "--iter", str(cfg["iter"]),
            "--time-limit", "140",
            "--fracA-start", str(cfg["fracA_start"]),
            "--fracA-end", "0.06",
            "--fracX-start", str(cfg["fracX_start"]),
            "--fracX-end", "0.04",
            "--accept-worse", str(cfg["accept_worse"]),
            "--stagnation-limit", str(cfg["stagnation_limit"]),
            "--keep-ratio", str(cfg["keep_ratio"]),
            "--out", str(OUT),
        ]
        run(cmd)

        run([
            "python3", str(EVAL),
            "--results-exp1", str(ROOT / "results/exp1"),
            "--ours", str(PB),
            "--bb", str(BB),
            "--vns-ts", str(VNS),
            "--gwo-hd", str(OUT),
            "--greedy", str(GREEDY),
            "--milp-aws", str(MILP_AWS),
            "--milp-eps", str(MILP_EPS),
        ])
        m = read_gwo_metrics(METRICS)
        rec = {"idx": i, **cfg, **m}
        records.append(rec)
        print(f"[{i:03d}/{len(combos)}] igd+={m['igd_plus']:.6f} hv={m['hv']:.6f} cfg={cfg}")

    records.sort(key=lambda r: (r["igd_plus"], -r["hv"], r["wall"]))

    out_json = ROOT / "tmp/gwo_v2_compact_sweep_results.json"
    out_csv = ROOT / "tmp/gwo_v2_compact_sweep_results.csv"

    with out_json.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)

    print("TOP-10")
    for r in records[:10]:
        print(r)


if __name__ == "__main__":
    main()
