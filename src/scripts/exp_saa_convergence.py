"""
exp_saa_convergence.py
======================
SAA scenario-count sensitivity analysis for MO-IHLNDP (CV-Small).

For N in {3, 5, 8, 10, 15, 20, 30}:
  1. Generate a CV-Small-scale SAA instance with N balanced scenarios
     (same node pool, hub capacities, and transport matrix as cv_small_drnd.json)
  2. Solve to optimality with bb_solver --mode enum (|H|=5 → 32 configs)
  3. Extract knee-point Z1/Z2 and Pareto HV (normalised against N=30 reference)

Outputs:
  results/saa_convergence/convergence_summary.csv
  figures/saa_convergence.pdf

Usage:
  cd <repo_root>
  python src/scripts/exp_saa_convergence.py [--skip-solve]
"""

import argparse
import json
import math
import os
import random
import subprocess
import sys
import csv

# ── repo root & path helpers ──────────────────────────────────────────────────
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "src", "scripts")
SOLVER_DIR  = os.path.join(REPO_ROOT, "src", "solver")
DATA_DIR    = os.path.join(REPO_ROOT, "data", "prep", "saa_convergence")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "saa_convergence")
FIGURES_DIR = os.path.join(REPO_ROOT, "figures")

os.makedirs(DATA_DIR,    exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(FIGURES_DIR, exist_ok=True)

sys.path.insert(0, SCRIPTS_DIR)
from data_generate_saa_oos import generate_saa_scenarios
from data_generate_cv import (
    DEMAND_NODES, HUB_NODES, ORIGIN_NODES, NUM_MODES, GAMMA, ALPHA, CHI,
    LAMBDA0, DAGANZO_ETA, DAGANZO_C_LOC, BIG_M,
    compute_aux_risk, risk_interval, build_transport, compute_theta, terrain_factor,
)

# ── experiment config ─────────────────────────────────────────────────────────
N_VALUES    = [3, 5, 8, 10, 15, 20, 30]
CV_SMALL    = dict(n_I=20, n_H=5, n_J=2)
BB_SOLVER   = os.path.join(SOLVER_DIR, "bb_solver")
BB_TRIALS   = 300   # sub-problem trials per leaf (H=5 → fast)
BB_TIMELIMIT = 120  # seconds — more than enough for |H|=5


# ── instance builder ──────────────────────────────────────────────────────────

def build_cv_small_saa(num_scenarios: int, seed: int = 2026) -> dict:
    """Build a CV-Small instance with `num_scenarios` balanced SAA scenarios.

    Node pool, transport matrix, hub capacities, and base population are taken
    directly from the original cv_small_drnd.json geometry so the instances are
    directly comparable to the Exp-1 baseline.
    """
    n_I = CV_SMALL["n_I"]
    n_H = CV_SMALL["n_H"]
    n_J = CV_SMALL["n_J"]

    demand_pool = DEMAND_NODES[:n_I]
    hub_pool    = HUB_NODES[:n_H]
    origin_pool = ORIGIN_NODES[:n_J]
    all_nodes   = demand_pool + hub_pool + origin_pool
    n_total     = len(all_nodes)
    coords      = [(lat, lon) for lat, lon, _ in all_nodes]
    names       = [nm for _, _, nm in all_nodes]

    demand_idx = list(range(n_I))
    hub_idx    = list(range(n_I, n_I + n_H))
    origin_idx = list(range(n_I + n_H, n_total))

    aux_risk    = [compute_aux_risk(lat, lon) for lat, lon in coords]
    r_intervals = [risk_interval(r) for r in aux_risk]

    # Deterministic population matching the original cv_small generation seed
    random.seed(2026)
    base_pop = {}
    for i in demand_idx:
        lat, lon = coords[i]
        coast_f  = max(0.15, 1.0 - abs(lon - 108.2) / 1.6)
        pop_base = int(500 + 6500 * coast_f)
        noise    = int(random.gauss(0, 0.12 * pop_base))
        base_pop[i] = max(100, pop_base + noise)

    area_km2 = {}
    for i in demand_idx:
        _, lon = coords[i]
        tf = terrain_factor(lon)
        area_km2[str(i)] = round(random.uniform(8.0, 18.0) * tf, 2)

    C_all, T_all = build_transport(coords)

    # Hub capacities: replicate cv_small generation (seed 2026, same logic)
    # We use the 3-scenario original demand to set capacity, then swap scenarios.
    from data_generate_cv import generate_scenarios as _orig_scenarios
    random.seed(2026)
    orig_scens     = _orig_scenarios(coords, aux_risk, r_intervals,
                                     demand_idx, hub_idx, origin_idx, base_pop)
    max_demand_kg  = max(
        GAMMA * sum(float(v) for v in sc["demand"].values())
        for sc in orig_scens
    )
    hub_capacity   = {}
    hub_fixed_cost = {}
    hub_hold_cost  = {}
    for k in hub_idx:
        _, lon = coords[k]
        tf = terrain_factor(lon)
        hub_capacity[str(k)]   = int(max_demand_kg / n_H * random.uniform(3.0, 6.0) * tf)
        hub_fixed_cost[str(k)] = round(random.uniform(60000, 200000) * tf, 2)
        hub_hold_cost[str(k)]  = round(random.uniform(0.2, 0.8), 4)

    # Generate N SAA scenarios (independent seed so different from hub-cap seed)
    random.seed(seed + 101 + num_scenarios)
    scenarios = generate_saa_scenarios(
        coords, aux_risk, r_intervals,
        demand_idx, hub_idx, origin_idx, base_pop,
        num_scenarios=num_scenarios,
    )

    Theta  = compute_theta(C_all, hub_idx, demand_idx, scenarios, area_km2)
    Lambda = {}
    for si, sc in enumerate(scenarios):
        for i in demand_idx:
            Lambda[f"{i}_{si}"] = round(LAMBDA0 * (1.0 + sc["risk"][i]), 4)

    return {
        "meta": {
            "name": f"CentralVietnam_SMALL_SAA{num_scenarios}",
            "description": "CV-Small SAA convergence instance",
            "seed": seed,
            "size": "small",
            "num_scenarios": num_scenarios,
        },
        "dimensions": {
            "num_I": n_I, "num_H": n_H, "num_J": n_J,
            "num_S": num_scenarios, "num_M": NUM_MODES,
        },
        "nodes": {
            "coords":         [[lat, lon] for lat, lon in coords],
            "names":          names,
            "demand_indices": demand_idx,
            "hub_indices":    hub_idx,
            "origin_indices": origin_idx,
            "aux_risk":       aux_risk,
            "risk_intervals": [[r[0], r[1]] for r in r_intervals],
        },
        "global_params": {
            "alpha": ALPHA, "chi": CHI, "gamma": GAMMA,
            "big_M": BIG_M, "daganzo_phi": 0.57, "daganzo_eta": DAGANZO_ETA,
        },
        "hub_params": {
            "capacity":   hub_capacity,
            "fixed_cost": hub_fixed_cost,
            "hold_cost":  hub_hold_cost,
        },
        "base_population": {str(i): base_pop[i] for i in demand_idx},
        "area_km2":  area_km2,
        "transport": {"cost": C_all, "time": T_all},
        "scenarios": scenarios,
        "theta":     Theta,
        "lambda":    Lambda,
    }


# ── Pareto metric helpers ─────────────────────────────────────────────────────

def _knee_point(front: list[dict]) -> dict:
    """Return the Pareto solution minimising normalised Chebyshev distance to ideal."""
    z1s = [s["Z1"] for s in front]
    z2s = [s["Z2"] for s in front]
    z1_min, z1_max = min(z1s), max(z1s)
    z2_min, z2_max = min(z2s), max(z2s)
    rng1 = z1_max - z1_min or 1.0
    rng2 = z2_max - z2_min or 1.0

    best, best_d = None, float("inf")
    for s in front:
        d = max((s["Z1"] - z1_min) / rng1, (s["Z2"] - z2_min) / rng2)
        if d < best_d:
            best_d, best = d, s
    return best


def _hypervolume_2d(front: list[dict], ref: tuple) -> float:
    """2-D hypervolume dominated by `front` w.r.t. reference point `ref`."""
    pts = sorted([(s["Z1"], s["Z2"]) for s in front], key=lambda p: p[0])
    hv = 0.0
    prev_z2 = ref[1]
    for z1, z2 in pts:
        if z1 < ref[0] and z2 < ref[1]:
            hv += (ref[0] - z1) * (prev_z2 - z2)
            prev_z2 = z2
    return hv


# ── main pipeline ─────────────────────────────────────────────────────────────

def generate_instances():
    paths = {}
    for N in N_VALUES:
        out = os.path.join(DATA_DIR, f"cv_small_saa{N}.json")
        if os.path.exists(out):
            print(f"  [skip] {out} already exists")
        else:
            print(f"  Generating N={N} ...", end=" ", flush=True)
            inst = build_cv_small_saa(N)
            with open(out, "w", encoding="utf-8") as f:
                json.dump(inst, f, separators=(",", ":"))
            print("done")
        paths[N] = out
    return paths


def solve_instances(paths: dict, skip: bool = False) -> dict:
    results = {}
    for N, inst_path in paths.items():
        out_path = os.path.join(RESULTS_DIR, f"saa{N}_bb.json")
        if skip or os.path.exists(out_path):
            print(f"  [skip] solver for N={N}")
        else:
            print(f"  Solving N={N} (enum, H=5) ...", end=" ", flush=True)
            cmd = [
                BB_SOLVER, inst_path,
                "--out", out_path,
                "--mode", "enum",
                "--trials", str(BB_TRIALS),
                "--time-limit", str(BB_TIMELIMIT),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                print(f"ERROR\n{proc.stderr[:400]}")
                continue
            elapsed = json.loads(open(out_path).read()).get("meta", {}).get("elapsed_s", "?")
            print(f"done ({elapsed:.1f}s)" if isinstance(elapsed, float) else "done")
        results[N] = out_path
    return results


def collect_metrics(result_paths: dict) -> list[dict]:
    # Use N=30 Pareto front as reference for HV normalisation
    ref_path = result_paths.get(30)
    ref_front = []
    if ref_path and os.path.exists(ref_path):
        with open(ref_path) as f:
            ref_front = json.load(f).get("pareto_front", [])

    # Reference point: 110% of the worst values across all fronts
    all_z1, all_z2 = [], []
    for N, path in result_paths.items():
        if not os.path.exists(path):
            continue
        front = json.load(open(path)).get("pareto_front", [])
        all_z1 += [s["Z1"] for s in front]
        all_z2 += [s["Z2"] for s in front]
    ref_pt = (max(all_z1) * 1.1, max(all_z2) * 1.1) if all_z1 else (1e12, 1e12)
    hv_ref = _hypervolume_2d(ref_front, ref_pt) if ref_front else 1.0

    rows = []
    for N in N_VALUES:
        path = result_paths.get(N)
        if not path or not os.path.exists(path):
            continue
        front = json.load(open(path)).get("pareto_front", [])
        if not front:
            continue
        knee   = _knee_point(front)
        hv_raw = _hypervolume_2d(front, ref_pt)
        rows.append({
            "N":        N,
            "Z1_knee":  knee["Z1"],
            "Z2_knee":  knee["Z2"],
            "HV_raw":   hv_raw,
            "HV_norm":  hv_raw / hv_ref if hv_ref else 0.0,
            "pareto_size": len(front),
        })
    return rows


def save_csv(rows: list[dict]):
    path = os.path.join(RESULTS_DIR, "convergence_summary.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["N","Z1_knee","Z2_knee","HV_raw","HV_norm","pareto_size"])
        w.writeheader()
        w.writerows(rows)
    print(f"  Saved: {path}")
    return path


def plot_convergence(rows: list[dict]):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
    except ImportError:
        print("  [warn] matplotlib not installed — skipping plot")
        return

    Ns       = [r["N"] for r in rows]
    Z1s      = [r["Z1_knee"] / 1e6 for r in rows]   # millions
    Z2s      = [r["Z2_knee"] / 1e3 for r in rows]   # thousands
    HVs      = [r["HV_norm"] for r in rows]

    fig, axes = plt.subplots(1, 3, figsize=(10, 3.0))
    fig.subplots_adjust(wspace=0.38)

    style = dict(marker="o", markersize=5, linewidth=1.5, color="#2166ac")

    axes[0].plot(Ns, Z1s, **style)
    axes[0].set_xlabel("Number of scenarios $N$")
    axes[0].set_ylabel("Knee-point $Z_1$ (M\$)")
    axes[0].set_title("Expected logistics cost")
    axes[0].xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    axes[1].plot(Ns, Z2s, **style)
    axes[1].set_xlabel("Number of scenarios $N$")
    axes[1].set_ylabel("Knee-point $Z_2$ (k\$)")
    axes[1].set_title("Expected deprivation cost")
    axes[1].xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    axes[2].plot(Ns, HVs, marker="s", markersize=5, linewidth=1.5, color="#d6604d")
    axes[2].set_xlabel("Number of scenarios $N$")
    axes[2].set_ylabel("Normalised HV")
    axes[2].set_title("Pareto front quality (HV)")
    axes[2].set_ylim(0, 1.05)
    axes[2].xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    for ax in axes:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", linestyle="--", alpha=0.4)

    out = os.path.join(FIGURES_DIR, "saa_convergence.pdf")
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-solve", action="store_true",
                        help="Skip bb_solver calls, reuse existing result JSONs")
    args = parser.parse_args()

    print("\n=== Step 1: Generate SAA instances ===")
    inst_paths = generate_instances()

    print("\n=== Step 2: Solve with bb_solver (enum mode) ===")
    result_paths = solve_instances(inst_paths, skip=args.skip_solve)

    print("\n=== Step 3: Collect metrics ===")
    rows = collect_metrics(result_paths)
    for r in rows:
        print(f"  N={r['N']:2d}  Z1={r['Z1_knee']/1e6:.3f}M  "
              f"Z2={r['Z2_knee']/1e3:.1f}k  HV={r['HV_norm']:.3f}  "
              f"|front|={r['pareto_size']}")

    print("\n=== Step 4: Save CSV ===")
    save_csv(rows)

    print("\n=== Step 5: Plot convergence ===")
    plot_convergence(rows)

    print("\nDone.")


if __name__ == "__main__":
    main()
