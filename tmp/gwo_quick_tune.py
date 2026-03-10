import csv
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
exe = root / "src" / "solver" / "gwo_hd_baseline"
inst = root / "data" / "cv" / "cv_small_drnd.json"
res = root / "results" / "exp1"

tests = [
    ("gwo_a", 12, 260, "0.6,0.5,0.7,0.4,0.8"),
    ("gwo_b", 20, 400, "0.6,0.7,0.8,0.9,0.5,0.4"),
    ("gwo_c", 30, 500, "0.6,0.65,0.7,0.75,0.8"),
    ("gwo_d", 24, 450, "0.5,0.55,0.6,0.65,0.7,0.75"),
]

rows = []
for tag, wolves, iters, weights in tests:
    out = res / f"cv_small_{tag}.json"
    run_cmd = [
        str(exe),
        str(inst),
        "--seed",
        "42",
        "--wolves",
        str(wolves),
        "--iter",
        str(iters),
        "--time-limit",
        "180",
        "--weights",
        weights,
        "--out",
        str(out),
    ]
    subprocess.run(run_cmd, check=True, stdout=subprocess.DEVNULL)

    eval_cmd = [
        "python3",
        str(root / "src" / "scripts" / "exp1_evaluate_cv_small.py"),
        "--results-exp1",
        str(res),
        "--ours",
        str(res / "cv_small_pb_nsga.json"),
        "--vns-ts",
        str(out),
        "--bb",
        str(res / "cv_small_bb.json"),
        "--greedy",
        str(res / "cv_small_greedy.json"),
        "--milp-aws",
        str(res / "cv_small_milp_aws.json"),
        "--milp-eps",
        str(res / "cv_small_milp_eps.json"),
    ]
    subprocess.run(eval_cmd, check=True, stdout=subprocess.DEVNULL)

    with (res / "cv_small_metrics.csv").open(newline="") as f:
        reader = csv.DictReader(f)
        pb = None
        gwo = None
        for rec in reader:
            if rec["algorithm"] == "PB-NSGA":
                pb = rec
            elif rec["algorithm"] == "VNS-TS":
                gwo = rec
        rows.append(
            {
                "tag": tag,
                "wolves": wolves,
                "iter": iters,
                "weights": weights,
                "gwo_hv": float(gwo["hv_mean"]),
                "gwo_igd": float(gwo["igd_mean"]),
                "gwo_wall": float(gwo["wall_s"]),
                "pb_hv": float(pb["hv_mean"]),
                "pb_igd": float(pb["igd_mean"]),
            }
        )

out_csv = root / "tmp" / "gwo_quick_tune_summary.csv"
with out_csv.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

rows.sort(key=lambda r: (-r["gwo_hv"], r["gwo_igd"], r["gwo_wall"]))
for r in rows:
    print(r)
print("summary_file", out_csv)
