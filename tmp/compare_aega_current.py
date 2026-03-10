import csv
import pathlib
import subprocess

root = pathlib.Path(__file__).resolve().parents[1]
solver = root / "src" / "solver" / "solver"
inst = root / "data" / "cv" / "cv_small_drnd.json"
res = root / "results" / "exp1"


def run(tag: str, aega_min: int, aega_max: int, aega_step: int):
    out = res / f"cv_small_{tag}.json"
    cmd = [
        str(solver),
        str(inst),
        "--pop",
        "200",
        "--gen",
        "300",
        "--seed",
        "0",
        "--pc",
        "0.98",
        "--pm-high",
        "0.40",
        "--pm-low",
        "0.10",
        "--sbx-eta-rw",
        "1.5",
        "--pm-eta-rw",
        "8",
        "--aega-pop",
        "--aega-min",
        str(aega_min),
        "--aega-max",
        str(aega_max),
        "--aega-step",
        str(aega_step),
        "--out",
        str(out),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

    eval_cmd = [
        "python3",
        str(root / "src" / "scripts" / "exp1_evaluate_cv_small.py"),
        "--results-exp1",
        str(res),
        "--ours",
        str(out),
        "--bb",
        str(res / "cv_small_bb.json"),
        "--vns-ts",
        str(res / "cv_small_vns_ts.json"),
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
        for rec in reader:
            if rec["algorithm"] == "PB-NSGA":
                return {
                    "tag": tag,
                    "hv": float(rec["hv_mean"]),
                    "igd": float(rec["igd_mean"]),
                    "wall": float(rec["wall_s"]),
                    "cpu": float(rec["cpu_s"]),
                }
    raise RuntimeError("PB-NSGA row not found in metrics")


base = run("pb_nsga_aega_120_320_30_current", 120, 320, 30)
cand = run("pb_nsga_aega_220_280_10_current", 220, 280, 10)

print("BASE", base)
print("CAND", cand)
print(
    "DELTA cand-base",
    {
        "hv": round(cand["hv"] - base["hv"], 6),
        "igd": round(cand["igd"] - base["igd"], 6),
        "wall": round(cand["wall"] - base["wall"], 3),
        "cpu": round(cand["cpu"] - base["cpu"], 3),
    },
)
