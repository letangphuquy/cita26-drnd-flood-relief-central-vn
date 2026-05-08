"""
data_generate_n10_training.py — N=10 tier-balanced training instance for ablation
==================================================================================
Generates a CV-Large training instance with exactly N=10 SAA scenarios (one per
profile tier class: 2 mild, 3 moderate, 3 severe, 2 extreme), using the same
scenario-generation machinery as data_generate_saa_oos.py.

Crucially, ALL non-scenario fields (hub_params, transport, base_population,
area_km2, global_params, node coords) are copied verbatim from the canonical
CV-Large baseline (data/cv/cv_large_drnd.json).  Only the following fields
are regenerated/replaced:
    - scenarios (N=10 tier-balanced)
    - dimensions.num_S
    - theta  (recomputed from new scenarios + existing coords/hub_params)
    - lambda (recomputed from new scenarios + existing coords)

The resulting file is written to:
    data/prep/cv_large_n10_training.json

Usage (from project root):
    python src/scripts/data_generate_n10_training.py [--seed 9999] [--out PATH]
"""

import argparse
import json
import math
import os
import pathlib
import random
import sys

# ---------------------------------------------------------------------------
# Resolve project root and add scripts dir to path for sibling imports
# ---------------------------------------------------------------------------
_SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parents[1]
sys.path.insert(0, str(_SCRIPT_DIR))

from data_generate_cv import (
    NUM_MODES, GAMMA, LAMBDA0,
    compute_aux_risk, risk_interval,
    _weighted_sample, haversine, gauss, terrain_factor, compute_theta,
)
from data_generate_saa_oos import _scenario_from_profile

# ---------------------------------------------------------------------------
# N=10 profile bank: 2 mild + 3 moderate + 3 severe + 2 extreme = 10
# (same format as _profile_bank() in data_generate_saa_oos.py)
# ---------------------------------------------------------------------------
N10_PROFILES = [
    # name,              n_epi, I_lo, I_hi, sev_mult, beta,  phi,   risk_noise
    ("mild_a",           1,     0.28, 0.50, 0.95,     0.20,  0.55,  0.020),
    ("mild_b",           1,     0.35, 0.62, 1.05,     0.28,  0.58,  0.025),
    ("moderate_a",       2,     0.30, 0.58, 1.10,     0.32,  0.60,  0.025),
    ("moderate_b",       2,     0.45, 0.70, 1.40,     0.42,  0.64,  0.028),
    ("moderate_c",       2,     0.50, 0.75, 1.55,     0.46,  0.66,  0.028),
    ("severe_a",         2,     0.55, 0.82, 1.65,     0.50,  0.68,  0.030),
    ("severe_b",         2,     0.62, 0.88, 1.85,     0.58,  0.71,  0.030),
    ("severe_c",         3,     0.58, 0.86, 1.95,     0.62,  0.73,  0.035),
    ("extreme_a",        3,     0.76, 0.98, 2.55,     0.82,  0.82,  0.035),
    ("extreme_b",        3,     0.82, 1.02, 2.80,     0.88,  0.85,  0.040),
]


def _compute_lambda(scenarios, demand_idx):
    """Recompute lambda dict from scenario risk vectors."""
    Lambda = {}
    for si, sc in enumerate(scenarios):
        risk = sc["risk"]
        for i in demand_idx:
            Lambda[f"{i}_{si}"] = round(LAMBDA0 * (1.0 + risk[i]), 4)
    return Lambda


def build_n10_training(baseline_path: pathlib.Path, seed: int = 9999) -> dict:
    """
    Load canonical CV-Large baseline and swap in N=10 SAA scenarios.
    Returns the new instance dict (not yet written to disk).
    """
    with open(baseline_path, "r", encoding="utf-8") as f:
        base = json.load(f)

    # ---- Extract geometry/infrastructure from baseline ----
    coords_raw = base["nodes"]["coords"]           # list of [lat, lon]
    coords = [(row[0], row[1]) for row in coords_raw]
    demand_idx  = base["nodes"]["demand_indices"]
    hub_idx     = base["nodes"]["hub_indices"]
    origin_idx  = base["nodes"]["origin_indices"]
    base_pop_raw = base["base_population"]         # {str(i): int}
    base_pop = {int(k): v for k, v in base_pop_raw.items()}
    area_km2    = base["area_km2"]                 # {str(i): float}

    # Recompute aux_risk and r_intervals from coords (deterministic, coord-only)
    aux_risk    = [compute_aux_risk(lat, lon) for lat, lon in coords]
    r_intervals = [risk_interval(r) for r in aux_risk]

    # ---- Generate 10 scenarios (one per profile tier) ----
    random.seed(seed)
    scenarios = []
    for s_idx, profile in enumerate(N10_PROFILES):
        sc = _scenario_from_profile(
            profile,
            s_idx,
            coords,
            aux_risk,
            r_intervals,
            demand_idx,
            hub_idx,
            origin_idx,
            base_pop,
            epi_sigma=85.0,
        )
        # Override name to reflect N10 ablation
        sc["name"] = f"n10_{s_idx:02d}_{profile[0]}"
        scenarios.append(sc)

    prob = 1.0 / len(scenarios)
    for sc in scenarios:
        sc["probability"] = prob

    # ---- Recompute theta and lambda from new scenarios ----
    theta = compute_theta(base["transport"]["cost"], hub_idx, demand_idx, scenarios, area_km2)
    lam   = _compute_lambda(scenarios, demand_idx)

    # ---- Build output instance (deep copy base, replace only scenario fields) ----
    import copy
    out = copy.deepcopy(base)
    out["meta"]["name"]        = "CentralVietnam_LARGE_N10_TRAINING"
    out["meta"]["description"] = "MO-IHLNDP — N=10 tier-balanced ablation training set"
    out["meta"]["seed"]        = seed
    out["meta"]["variant"]     = "n10_training"
    out["meta"]["method"]      = "tier_balanced_n10"
    out["dimensions"]["num_S"] = len(scenarios)
    out["scenarios"]           = scenarios
    out["theta"]               = theta
    out["lambda"]              = lam
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Generate N=10 tier-balanced training instance for PB-NSGA ablation"
    )
    ap.add_argument("--seed", type=int, default=9999,
                    help="RNG seed for scenario generation (default: 9999)")
    ap.add_argument("--baseline", default=None,
                    help="Path to canonical CV-Large baseline JSON "
                         "(default: data/cv/cv_large_drnd.json)")
    ap.add_argument("--out", default=None,
                    help="Output path (default: data/prep/cv_large_n10_training.json)")
    args = ap.parse_args()

    baseline_path = pathlib.Path(args.baseline) if args.baseline else (
        _PROJECT_DIR / "data" / "cv" / "cv_large_drnd.json"
    )
    out_path = pathlib.Path(args.out) if args.out else (
        _PROJECT_DIR / "data" / "prep" / "cv_large_n10_training.json"
    )

    if not baseline_path.exists():
        print(f"[Error] Baseline not found: {baseline_path}")
        sys.exit(1)

    print(f"[N10] Loading baseline: {baseline_path}")
    instance = build_n10_training(baseline_path, seed=args.seed)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(instance, f, indent=2, ensure_ascii=False)
    print(f"[N10] Saved N=10 training instance: {out_path}")
    print(f"      Scenarios : {instance['dimensions']['num_S']}")
    print(f"      Seed      : {args.seed}")


if __name__ == "__main__":
    main()
