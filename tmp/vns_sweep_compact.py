import itertools
import json
import re
import subprocess
import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
solver = root / "src/solver/vns_ts_baseline"
inst = root / "data/cv/cv_small_drnd.json"
out = root / "results/exp1/cv_small_vns_ts.json"

eval_cmd_base = [
    "python3",
    "src/scripts/exp1_evaluate_cv_small.py",
    "--milp-aws",
    "results/exp1/cv_small_milp_aws.json",
    "--milp-eps",
    "results/exp1/cv_small_milp_eps.json",
    "--bb",
    "results/exp1/cv_small_bb.json",
    "--greedy",
    "results/exp1/cv_small_greedy.json",
    "--vns-ts",
    "results/exp1/cv_small_vns_ts.json",
    "--ours",
    "results/exp1/cv_small_pb_nsga.json",
]

# Compact grid: 12 configurations
iters = [100, 140]
starts = [6, 10, 14]
tenures = [5, 7]
kmaxs = [3]
seed = 42
time_limit = 60

rows = []
for it, st, tt, km in itertools.product(iters, starts, tenures, kmaxs):
    run_cmd = [
        str(solver),
        str(inst),
        "--seed",
        str(seed),
        "--iter",
        str(it),
        "--time-limit",
        str(time_limit),
        "--tabu-tenure",
        str(tt),
        "--kmax",
        str(km),
        "--starts",
        str(st),
        "--out",
        str(out),
    ]
    rp = subprocess.run(run_cmd, cwd=root, capture_output=True, text=True)
    if rp.returncode != 0:
        rows.append(
            {
                "iter": it,
                "starts": st,
                "tabu": tt,
                "kmax": km,
                "hv": -1.0,
                "igd": float("inf"),
                "wall": float("nan"),
                "status": "solver_fail",
            }
        )
        print(f"FAIL solver: iter={it}, starts={st}, tabu={tt}, kmax={km}")
        continue

    meta = json.load(open(out, "r", encoding="utf-8"))["meta"]
    ep = subprocess.run(eval_cmd_base, cwd=root, capture_output=True, text=True)
    txt = ep.stdout + "\n" + ep.stderr

    m = re.search(r"^\s*VNS-TS\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)", txt, flags=re.M)
    if not m:
        rows.append(
            {
                "iter": it,
                "starts": st,
                "tabu": tt,
                "kmax": km,
                "hv": -1.0,
                "igd": float("inf"),
                "wall": meta.get("elapsed_s", float("nan")),
                "status": "eval_parse_fail",
            }
        )
        print(f"FAIL parse: iter={it}, starts={st}, tabu={tt}, kmax={km}")
        continue

    hv = float(m.group(1))
    igd = float(m.group(2))
    wall = float(m.group(3))
    rows.append(
        {
            "iter": it,
            "starts": st,
            "tabu": tt,
            "kmax": km,
            "hv": hv,
            "igd": igd,
            "wall": wall,
            "status": "ok",
        }
    )
    print(f"iter={it:3d} starts={st:2d} tabu={tt} kmax={km} => HV={hv:.3f} IGD+={igd:.3f} wall={wall:.1f}s")

rows_ok = [r for r in rows if r["status"] == "ok"]
rows_ok.sort(key=lambda r: (-r["hv"], r["igd"], r["wall"]))

csv_path = root / "results/exp1/vns_ts_sweep_compact.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["iter", "starts", "tabu", "kmax", "hv", "igd", "wall", "status"])
    w.writeheader()
    w.writerows(rows)

print("\n=== TOP 5 CONFIGS ===")
for r in rows_ok[:5]:
    print(
        f"iter={r['iter']}, starts={r['starts']}, tabu={r['tabu']}, kmax={r['kmax']} "
        f"| HV={r['hv']:.3f}, IGD+={r['igd']:.3f}, wall={r['wall']:.1f}s"
    )

if rows_ok:
    print("\nBEST_JSON", json.dumps(rows_ok[0]))
print("SWEEP_CSV", csv_path)
