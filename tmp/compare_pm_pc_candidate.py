import csv
import pathlib
import statistics
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOLVER = ROOT / "src" / "solver" / "solver"
INST = ROOT / "data" / "cv" / "cv_small_drnd.json"
RES = ROOT / "results" / "exp1"
OUTDIR = ROOT / "tmp" / "pm_pc_candidate_check"
OUTDIR.mkdir(parents=True, exist_ok=True)

configs = [
    ("current", "0.98", "0.40", "0.10"),
    ("candidate", "0.95", "0.35", "0.12"),
]
seeds = [0, 1, 2]
rows = []

for name, pc, pmh, pml in configs:
    for seed in seeds:
        out = OUTDIR / f"cv_small_pb_nsga_{name}_seed{seed}.json"
        cmd = [
            str(SOLVER),
            str(INST),
            "--pop",
            "200",
            "--gen",
            "300",
            "--seed",
            str(seed),
            "--pc",
            pc,
            "--pm-high",
            pmh,
            "--pm-low",
            pml,
            "--sbx-eta-rw",
            "1.5",
            "--pm-eta-rw",
            "8",
            "--aega-pop",
            "--aega-min",
            "220",
            "--aega-max",
            "280",
            "--aega-step",
            "10",
            "--out",
            str(out),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

        eval_cmd = [
            "python3",
            str(ROOT / "src" / "scripts" / "exp1_evaluate_cv_small.py"),
            "--results-exp1",
            str(RES),
            "--ours",
            str(out),
            "--bb",
            str(RES / "cv_small_bb.json"),
            "--vns-ts",
            str(RES / "cv_small_vns_ts.json"),
            "--greedy",
            str(RES / "cv_small_greedy.json"),
            "--milp-aws",
            str(RES / "cv_small_milp_aws.json"),
            "--milp-eps",
            str(RES / "cv_small_milp_eps.json"),
        ]
        subprocess.run(eval_cmd, check=True, stdout=subprocess.DEVNULL)

        with (RES / "cv_small_metrics.csv").open(newline="") as f:
            reader = csv.DictReader(f)
            for rec in reader:
                if rec["algorithm"] == "PB-NSGA":
                    rows.append(
                        {
                            "config": name,
                            "seed": seed,
                            "hv": float(rec["hv_mean"]),
                            "igd": float(rec["igd_mean"]),
                            "wall": float(rec["wall_s"]),
                            "cpu": float(rec["cpu_s"]),
                        }
                    )
                    break

summary = OUTDIR / "summary.csv"
with summary.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["config", "seed", "hv", "igd", "wall", "cpu"])
    w.writeheader()
    w.writerows(rows)

for cfg in ["current", "candidate"]:
    r = [x for x in rows if x["config"] == cfg]
    print(
        cfg,
        "hv_avg",
        round(statistics.mean(x["hv"] for x in r), 6),
        "igd_avg",
        round(statistics.mean(x["igd"] for x in r), 6),
        "wall_avg",
        round(statistics.mean(x["wall"] for x in r), 3),
        "cpu_avg",
        round(statistics.mean(x["cpu"] for x in r), 3),
    )

c = [x for x in rows if x["config"] == "candidate"]
b = [x for x in rows if x["config"] == "current"]
print(
    "delta(candidate-current)",
    "hv",
    round(statistics.mean(x["hv"] for x in c) - statistics.mean(x["hv"] for x in b), 6),
    "igd",
    round(statistics.mean(x["igd"] for x in c) - statistics.mean(x["igd"] for x in b), 6),
    "wall",
    round(statistics.mean(x["wall"] for x in c) - statistics.mean(x["wall"] for x in b), 3),
    "cpu",
    round(statistics.mean(x["cpu"] for x in c) - statistics.mean(x["cpu"] for x in b), 3),
)
print("summary_file", summary)
