"""
exp_saa_convergence.py
======================
SAA scenario-count sensitivity analysis for MO-IHLNDP (CV-Small).

Design: replication-based convergence.
  1. Build shared base infrastructure (same geography/hub-params as cv_small_drnd.json).
  2. Generate a master scenario pool of MAX_POOL=50 balanced scenarios once
     (round-robin from 10 profiles → 5 reps each → equal mild/severe/extreme
     coverage). Fixed seed ensures reproducibility.
  3. For each N in N_VALUES, run K_REPS replications:
       - Randomly sub-sample N scenarios from the master pool (without replacement).
       - Build instance, solve to optimality via bb_solver --mode enum (|H|=5 → 32 configs).
       - Record knee-point Z1/Z2 and Pareto HV.
  4. Plot mean ± std across K_REPS for each N → shows stabilisation.

As N grows, the sample average converges to the pool mean, variance shrinks,
and the optimal decision stabilises — demonstrating SAA sufficiency.

Outputs:
  results/saa_convergence/convergence_summary.csv
  figures/saa_convergence.pdf

Usage:
  cd <repo_root>
  python3 src/scripts/exp_saa_convergence.py [--skip-solve]
"""

import argparse
import copy
import csv
import json
import os
import random
import subprocess
import sys

# ── repo root & paths ─────────────────────────────────────────────────────────
REPO_ROOT   = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "src", "scripts")
SOLVER_DIR  = os.path.join(REPO_ROOT, "src", "solver")
# Paths below are set at runtime from CLI args — do not restore as constants.
# Legacy values (for reference only):
#   DATA_DIR    = os.path.join(REPO_ROOT, "data", "prep", "saa_convergence")
#   RESULTS_DIR = os.path.join(REPO_ROOT, "results", "saa_convergence")
#   FIGURES_DIR = os.path.join(REPO_ROOT, "figures")
DATA_DIR:    str = ""  # set in main()
RESULTS_DIR: str = ""  # set in main()
FIGURES_DIR: str = ""  # set in main()

sys.path.insert(0, SCRIPTS_DIR)
from data_generate_saa_oos import generate_saa_scenarios
from data_generate_cv import (
    DEMAND_NODES, HUB_NODES, ORIGIN_NODES, NUM_MODES, GAMMA, ALPHA, CHI,
    LAMBDA0, DAGANZO_ETA, BIG_M,
    compute_aux_risk, risk_interval, build_transport, compute_theta, terrain_factor,
    generate_scenarios as _cv_orig_scenarios,
)

# ── config ────────────────────────────────────────────────────────────────────
N_VALUES  = [3, 5, 8, 10, 15, 20, 30]
MAX_POOL  = 50        # master pool (50 = 5 reps × 10 profiles → balanced)
K_REPS    = 10        # replications per N (random sub-samples from pool)
POOL_SEED = 31415     # fixed seed for master pool generation
CV_SMALL  = dict(n_I=20, n_H=5, n_J=2)

BB_SOLVER    = os.path.join(SOLVER_DIR, "bb_solver")
BB_TRIALS    = 400
BB_TIMELIMIT = 120    # seconds


# ── shared base infrastructure ────────────────────────────────────────────────

def build_base() -> dict:
    """Construct shared geographic & cost infrastructure for CV-Small (seed=2026)."""
    n_I, n_H, n_J = CV_SMALL["n_I"], CV_SMALL["n_H"], CV_SMALL["n_J"]
    all_nodes  = DEMAND_NODES[:n_I] + HUB_NODES[:n_H] + ORIGIN_NODES[:n_J]
    coords     = [(lat, lon) for lat, lon, _ in all_nodes]
    names      = [nm for _, _, nm in all_nodes]
    demand_idx = list(range(n_I))
    hub_idx    = list(range(n_I, n_I + n_H))
    origin_idx = list(range(n_I + n_H, len(all_nodes)))

    aux_risk    = [compute_aux_risk(lat, lon) for lat, lon in coords]
    r_intervals = [risk_interval(r) for r in aux_risk]

    random.seed(2026)
    base_pop = {}
    for i in demand_idx:
        lat, lon = coords[i]
        coast_f = max(0.15, 1.0 - abs(lon - 108.2) / 1.6)
        pop_base = int(500 + 6500 * coast_f)
        base_pop[i] = max(100, pop_base + int(random.gauss(0, 0.12 * pop_base)))

    area_km2 = {str(i): round(random.uniform(8.0, 18.0) * terrain_factor(coords[i][1]), 2)
                for i in demand_idx}

    C_all, T_all = build_transport(coords)

    orig_scens    = _cv_orig_scenarios(coords, aux_risk, r_intervals,
                                       demand_idx, hub_idx, origin_idx, base_pop)
    max_dem_kg    = max(GAMMA * sum(float(v) for v in sc["demand"].values())
                        for sc in orig_scens)
    hub_params = {"capacity": {}, "fixed_cost": {}, "hold_cost": {}}
    for k in hub_idx:
        tf = terrain_factor(coords[k][1])
        hub_params["capacity"][str(k)]   = int(max_dem_kg / n_H * random.uniform(3.0, 6.0) * tf)
        hub_params["fixed_cost"][str(k)] = round(random.uniform(60000, 200000) * tf, 2)
        hub_params["hold_cost"][str(k)]  = round(random.uniform(0.2, 0.8), 4)

    return dict(n_I=n_I, n_H=n_H, n_J=n_J,
                demand_idx=demand_idx, hub_idx=hub_idx, origin_idx=origin_idx,
                coords=coords, names=names,
                aux_risk=aux_risk, r_intervals=r_intervals,
                base_pop=base_pop, area_km2=area_km2,
                C_all=C_all, T_all=T_all, hub_params=hub_params)


def build_master_pool(base: dict) -> list:
    """Generate MAX_POOL balanced scenarios (round-robin × 10 profiles, fixed seed)."""
    random.seed(POOL_SEED)
    return generate_saa_scenarios(
        base["coords"], base["aux_risk"], base["r_intervals"],
        base["demand_idx"], base["hub_idx"], base["origin_idx"],
        base["base_pop"], num_scenarios=MAX_POOL,
    )


# ── instance builder ──────────────────────────────────────────────────────────

def make_instance(base: dict, scenarios: list) -> dict:
    N    = len(scenarios)
    scens = copy.deepcopy(scenarios)
    for sc in scens:
        sc["probability"] = 1.0 / N

    Theta  = compute_theta(base["C_all"], base["hub_idx"],
                           base["demand_idx"], scens, base["area_km2"])
    Lambda = {f"{i}_{si}": round(LAMBDA0 * (1.0 + sc["risk"][i]), 4)
              for si, sc in enumerate(scens)
              for i in base["demand_idx"]}

    return {
        "meta":       {"name": f"CV_SMALL_SAA{N}", "num_scenarios": N},
        "dimensions": {"num_I": base["n_I"], "num_H": base["n_H"],
                       "num_J": base["n_J"], "num_S": N, "num_M": NUM_MODES},
        "nodes": {
            "coords":         [[lat, lon] for lat, lon in base["coords"]],
            "names":          base["names"],
            "demand_indices": base["demand_idx"],
            "hub_indices":    base["hub_idx"],
            "origin_indices": base["origin_idx"],
            "aux_risk":       base["aux_risk"],
            "risk_intervals": [[r[0], r[1]] for r in base["r_intervals"]],
        },
        "global_params": {"alpha": ALPHA, "chi": CHI, "gamma": GAMMA,
                          "big_M": BIG_M, "daganzo_phi": 0.57,
                          "daganzo_eta": DAGANZO_ETA},
        "hub_params":      base["hub_params"],
        "base_population": {str(i): base["base_pop"][i] for i in base["demand_idx"]},
        "area_km2":        base["area_km2"],
        "transport":       {"cost": base["C_all"], "time": base["T_all"]},
        "scenarios":       scens,
        "theta":           Theta,
        "lambda":          Lambda,
    }


# ── solver wrapper ────────────────────────────────────────────────────────────

def solve(inst_path: str, out_path: str) -> bool:
    cmd = [BB_SOLVER, inst_path,
           "--out", out_path,
           "--mode", "enum",
           "--trials", str(BB_TRIALS),
           "--time-limit", str(BB_TIMELIMIT)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode == 0


# ── metrics ───────────────────────────────────────────────────────────────────

def knee_point(front: list) -> dict:
    z1s = [s["Z1"] for s in front]
    z2s = [s["Z2"] for s in front]
    r1 = (max(z1s) - min(z1s)) or 1.0
    r2 = (max(z2s) - min(z2s)) or 1.0
    best, bd = None, float("inf")
    for s in front:
        d = max((s["Z1"] - min(z1s)) / r1, (s["Z2"] - min(z2s)) / r2)
        if d < bd:
            bd, best = d, s
    return best


def hypervolume_2d(front: list, ref: tuple) -> float:
    pts = sorted([(s["Z1"], s["Z2"]) for s in front
                  if s["Z1"] < ref[0] and s["Z2"] < ref[1]], key=lambda p: p[0])
    hv, prev = 0.0, ref[1]
    for z1, z2 in pts:
        hv += (ref[0] - z1) * (prev - z2)
        prev = z2
    return hv


# ── main pipeline ─────────────────────────────────────────────────────────────

def run_all(base: dict, pool: list, skip_solve: bool) -> list:
    """Run K_REPS replications for each N; return list of per-run metric dicts."""
    rng = random.Random(POOL_SEED + 1)   # separate RNG for sub-sampling
    all_runs = []

    for N in N_VALUES:
        print(f"  N={N:2d}: ", end="", flush=True)
        for rep in range(K_REPS):
            label = f"N{N}_rep{rep}"
            inst_path = os.path.join(DATA_DIR,    f"{label}.json")
            out_path  = os.path.join(RESULTS_DIR, f"{label}_bb.json")

            # sub-sample N from the pool
            subset = rng.sample(pool, N)

            if not os.path.exists(inst_path):
                inst = make_instance(base, subset)
                with open(inst_path, "w") as f:
                    json.dump(inst, f, separators=(",", ":"))

            if not (skip_solve or os.path.exists(out_path)):
                ok = solve(inst_path, out_path)
                if not ok:
                    print(f"[ERR rep{rep}] ", end="", flush=True)
                    continue

            if os.path.exists(out_path):
                front = json.load(open(out_path)).get("pareto_front", [])
                if front:
                    k = knee_point(front)
                    all_runs.append({"N": N, "rep": rep,
                                     "Z1": k["Z1"], "Z2": k["Z2"],
                                     "pareto_size": len(front),
                                     "front": front})
            print(".", end="", flush=True)
        print()

    return all_runs


def aggregate(all_runs: list) -> list:
    """Aggregate per-run records into per-N mean ± std rows."""
    import statistics

    # Global reference point for HV: 110 % of worst objective across ALL Pareto
    # front solutions (not just knee points) to avoid truncating extreme solutions.
    all_z1_full = [s["Z1"] for r in all_runs for s in r["front"]]
    all_z2_full = [s["Z2"] for r in all_runs for s in r["front"]]
    ref_pt = (max(all_z1_full) * 1.1, max(all_z2_full) * 1.1) if all_z1_full else (1e12, 1e12)

    # Normalise HV by the mean HV at the largest N
    max_N  = max(N_VALUES)
    hvs_at_max = [hypervolume_2d(r["front"], ref_pt)
                  for r in all_runs if r["N"] == max_N]
    hv_ref = statistics.mean(hvs_at_max) if hvs_at_max else 1.0

    rows = []
    for N in N_VALUES:
        runs_N = [r for r in all_runs if r["N"] == N]
        if not runs_N:
            continue
        z1_vals = [r["Z1"] / 1e6 for r in runs_N]   # millions
        z2_vals = [r["Z2"] / 1e3 for r in runs_N]   # thousands
        hv_vals = [hypervolume_2d(r["front"], ref_pt) / hv_ref for r in runs_N]

        def _s(vals):
            return statistics.stdev(vals) if len(vals) > 1 else 0.0

        rows.append({
            "N":        N,
            "reps":     len(runs_N),
            "Z1_mean":  statistics.mean(z1_vals),
            "Z1_std":   _s(z1_vals),
            "Z2_mean":  statistics.mean(z2_vals),
            "Z2_std":   _s(z2_vals),
            "HV_mean":  statistics.mean(hv_vals),
            "HV_std":   _s(hv_vals),
        })
    return rows


def save_csv(rows: list):
    path = os.path.join(RESULTS_DIR, "convergence_summary.csv")
    fields = ["N","reps","Z1_mean","Z1_std","Z2_mean","Z2_std","HV_mean","HV_std"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"  Saved: {path}")


def plot_convergence(rows: list):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
    except ImportError:
        print("  [warn] matplotlib not available — skipping plot")
        return

    Ns   = [r["N"] for r in rows]
    Z2_m = [r["Z2_mean"] for r in rows]
    Z2_s = [r["Z2_std"]  for r in rows]
    HV_m = [r["HV_mean"] for r in rows]
    HV_s = [r["HV_std"]  for r in rows]

    fig, axes = plt.subplots(1, 2, figsize=(6.5, 2.8))
    fig.subplots_adjust(wspace=0.44)
    blue, red = "#2166ac", "#d6604d"

    def _panel(ax, ys, errs, color, ylabel, title, ylim=None):
        ax.plot(Ns, ys, marker="o", markersize=4.5, linewidth=1.5, color=color)
        lo = [max(0, y - e) for y, e in zip(ys, errs)]
        hi = [y + e for y, e in zip(ys, errs)]
        ax.fill_between(Ns, lo, hi, alpha=0.18, color=color)
        ax.set_xlabel(r"No. of scenarios $|S|$", fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(title, fontsize=9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", linestyle="--", alpha=0.35)
        ax.tick_params(labelsize=8)
        ax.xaxis.set_major_locator(mticker.FixedLocator(Ns))
        if ylim:
            ax.set_ylim(*ylim)

    _panel(axes[0], Z2_m, Z2_s, blue,
           r"Expected deprivation $Z_2$ (k\$)",
           r"Deprivation cost stability ($Z_2$)")
    _panel(axes[1], HV_m, HV_s, red,
           "Normalised HV",
           "Pareto front quality (HV)",
           ylim=(0.3, 1.45))

    out = os.path.join(FIGURES_DIR, "saa_convergence.pdf")
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out}")


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    global DATA_DIR, RESULTS_DIR, FIGURES_DIR

    parser = argparse.ArgumentParser(description="SAA scenario-count sensitivity analysis for MO-IHLNDP")
    parser.add_argument("--skip-solve", action="store_true",
                        help="Skip solver runs; use existing result files only")
    # Path arguments — required, no defaults.
    # Legacy values (do not restore as defaults):
    #   --data-dir:    data/prep/saa_convergence
    #   --results-dir: results/saa_convergence
    #   --figures-dir: figures
    parser.add_argument("--data-dir", required=True,
                        help="Directory for generated SAA instance JSON files")
    parser.add_argument("--results-dir", required=True,
                        help="Directory for solver output and convergence_summary.csv")
    parser.add_argument("--figures-dir", required=True,
                        help="Directory for output figures (saa_convergence.pdf)")
    args = parser.parse_args()

    DATA_DIR    = args.data_dir
    RESULTS_DIR = args.results_dir
    FIGURES_DIR = args.figures_dir
    for d in (DATA_DIR, RESULTS_DIR, FIGURES_DIR):
        os.makedirs(d, exist_ok=True)

    print("\n=== Build shared base (CV-Small geometry, seed=2026) ===")
    base = build_base()
    print(f"  |I|={base['n_I']}  |H|={base['n_H']}  |J|={base['n_J']}")

    print(f"\n=== Generate master pool (N={MAX_POOL}, seed={POOL_SEED}) ===")
    pool = build_master_pool(base)
    print(f"  {len(pool)} scenarios ready (10-profile round-robin, balanced mild/severe/extreme)")

    print(f"\n=== Run {K_REPS} replications × {len(N_VALUES)} N-values ===")
    all_runs = run_all(base, pool, skip_solve=args.skip_solve)
    print(f"  Total valid runs: {len(all_runs)}")

    print("\n=== Aggregate metrics ===")
    summary = aggregate(all_runs)
    for r in summary:
        print(f"  N={r['N']:2d}  Z1={r['Z1_mean']:.3f}±{r['Z1_std']:.3f}M  "
              f"Z2={r['Z2_mean']:.1f}±{r['Z2_std']:.1f}k  "
              f"HV={r['HV_mean']:.3f}±{r['HV_std']:.3f}")

    print("\n=== Save CSV ===")
    save_csv(summary)

    print("\n=== Plot convergence ===")
    plot_convergence(summary)

    print("\nDone.")


if __name__ == "__main__":
    main()
