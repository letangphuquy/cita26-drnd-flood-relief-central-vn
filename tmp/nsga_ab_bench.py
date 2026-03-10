import csv
import pathlib
import statistics
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOLVER = ROOT / "src" / "solver" / "solver"
INST = ROOT / "data" / "cv" / "cv_small_drnd.json"
RES = ROOT / "results" / "exp1"
OUTDIR = ROOT / "tmp" / "nsga_seeding_ab"
OUTDIR.mkdir(parents=True, exist_ok=True)

modes = [("default", []), ("legacy", ["--legacy-seeding"])]
seeds = [0, 1, 2]
rows = []

for mode, extra in modes:
    for seed in seeds:
        out_json = OUTDIR / f"cv_small_pb_nsga_{mode}_seed{seed}.json"
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
            "120",
            "--aega-max",
            "320",
            "--aega-step",
            "30",
            "--out",
            str(out_json),
        ] + extra
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

        eval_cmd = [
            "python3",
            str(ROOT / "src" / "scripts" / "exp1_evaluate_cv_small.py"),
            "--results-exp1",
            str(RES),
            "--ours",
            str(out_json),
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
                            "mode": mode,
                            "seed": seed,
                            "hv_mean": float(rec["hv_mean"]),
                            "igd_mean": float(rec["igd_mean"]),
                            "wall_s": float(rec["wall_s"]),
                            "cpu_s": float(rec["cpu_s"]),
                        }
                    )
                    break

summary_path = OUTDIR / "summary.csv"
with summary_path.open("w", newline="") as f:
    writer = csv.DictWriter(
        f, fieldnames=["mode", "seed", "hv_mean", "igd_mean", "wall_s", "cpu_s"]
    )
    writer.writeheader()
    writer.writerows(rows)

for mode in ["default", "legacy"]:
    mrows = [r for r in rows if r["mode"] == mode]
    print(
        mode,
        "HV",
        round(statistics.mean(x["hv_mean"] for x in mrows), 6),
        "IGD+",
        round(statistics.mean(x["igd_mean"] for x in mrows), 6),
        "wall",
        round(statistics.mean(x["wall_s"] for x in mrows), 3),
        "cpu",
        round(statistics.mean(x["cpu_s"] for x in mrows), 3),
    )

print("summary_file", summary_path)
