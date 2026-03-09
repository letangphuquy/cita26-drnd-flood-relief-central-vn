"""
data_generate_saa_oos.py — SAA & OOS Scenario Generator
========================================================
STATUS: Standalone data-generation utility — NOT part of the main pipeline.

Generates two supplementary evaluation datasets for CV-Large:

  1. SAA set (100 scenarios, seed 2026)
     Scenarios follow the same mild/severe/extreme distribution as the
     main CV-Large instance (60% mild, 30% severe, 10% extreme) but
     sampled independently.  Output: data/cv/cv_large_saa.json

  2. OOS set (1 novel extreme double-typhoon scenario)
     Represents a simultaneous dual-epicentre event not present in the
     training scenarios.  Output: data/cv/cv_large_oos.json

These files are consumed by the C++ solver's --eval-saa / --eval-oos
modes, whose results are then summarised by exp2_analyze_saa_oos.py.

Usage (from project root):
  python src/scripts/data_generate_saa_oos.py
"""

import math
import json
import random
import os

from data_generate_cv import (
    DEMAND_NODES, HUB_NODES, ORIGIN_NODES, NUM_MODES, GAMMA, ALPHA, CHI, LAMBDA0, 
    DAGANZO_ETA, DAGANZO_C_LOC, BIG_M, RISK_WEIGHTS, compute_aux_risk, risk_interval,
    build_transport, _weighted_sample, haversine, gauss, terrain_factor, compute_theta
)

SEED = 2026
random.seed(SEED)

def generate_saa_scenarios(coords, aux_risk, r_intervals, demand_idx, hub_idx, origin_idx, base_pop, num_scenarios=100):
    """Generate num_scenarios random SAA instances."""
    n = len(coords)
    EPI_SIGMA = 85.0
    epi_weights = [aux_risk[i] for i in demand_idx]
    
    scenarios = []
    
    # We will sample combinations of mild/severe/extreme parameters to create a rich SAA distribution
    for s_idx in range(num_scenarios):
        # Stochastically choose the type of scenario
        rand_val = random.random()
        if rand_val < 0.60:
            type_name, n_epi, I_lo, I_hi, sev_mult, beta, phi = "mild", 1, 0.30, 0.60, 1.0, 0.25, 0.57
        elif rand_val < 0.90:
            type_name, n_epi, I_lo, I_hi, sev_mult, beta, phi = "severe", 2, 0.55, 0.85, 1.8, 0.55, 0.70
        else:
            type_name, n_epi, I_lo, I_hi, sev_mult, beta, phi = "extreme", 3, 0.75, 1.00, 2.8, 0.88, 0.85

        name = f"saa_{s_idx:03d}_{type_name}"
        prob = 1.0 / num_scenarios

        chosen_local = _weighted_sample(demand_idx, epi_weights, n_epi)
        epicenters = [
            (coords[demand_idx[ci]][0], coords[demand_idx[ci]][1], random.uniform(I_lo, I_hi))
            for ci in chosen_local
        ]

        raw_exp = []
        for u in range(n):
            ex = sum(inten * gauss(haversine(coords[u][0], coords[u][1], elat, elon), EPI_SIGMA) for elat, elon, inten in epicenters)
            raw_exp.append(min(1.0, ex))

        risk = []
        for u in range(n):
            r_min, r_max = r_intervals[u]
            r_us = max(0.01, min(0.99, r_min + (r_max - r_min) * raw_exp[u] + random.gauss(0, 0.025)))
            risk.append(round(r_us, 4))

        a = [[[1]*n for _ in range(n)] for _ in range(NUM_MODES)]
        for u in range(n):
            for v in range(n):
                if u == v:
                    for m in range(NUM_MODES): a[m][u][v] = 0
                    continue
                if random.random() < min(0.97, beta * (risk[u] + risk[v]) / 2.0):
                    a[0][u][v] = a[0][v][u] = 0

        demand = {}
        total_demand_pers = 0.0
        for i in demand_idx:
            d_val = max(5.0, base_pop[i] * (0.05 + 0.85 * risk[i]) * sev_mult + random.gauss(0, 0.08 * base_pop[i] * (0.05 + 0.85 * risk[i]) * sev_mult))
            demand[str(i)] = round(d_val, 2)
            total_demand_pers += d_val

        total_supply_kg = GAMMA * total_demand_pers * random.uniform(1.8, 2.5)
        supply = {str(j): round(max(5000.0, total_supply_kg / len(origin_idx) * random.uniform(0.7, 1.3)), 2) for j in origin_idx}

        hub_reactive_cost = {str(k): round(random.uniform(30000, 80000) * (1.0 + risk[k]), 2) for k in hub_idx}
        hub_process_time  = {str(k): round(random.uniform(0.4, 1.5) * (1.0 + 0.5 * risk[k]), 4) for k in hub_idx}

        scenarios.append({
            "name": name, "probability": prob, "phi_circuity": phi,
            "epicenters": [{"lat": round(e[0],4), "lon": round(e[1],4), "intensity": round(e[2],4)} for e in epicenters],
            "risk": risk, "hub_risk": {str(k): risk[k] for k in hub_idx},
            "accessibility": a, "demand": demand, "supply": supply,
            "hub_reactive_cost": hub_reactive_cost, "hub_process_time": hub_process_time,
        })
    return scenarios

def generate_oos_scenario(coords, aux_risk, r_intervals, demand_idx, hub_idx, origin_idx, base_pop):
    """Generate 1 novel extreme double-typhoon scenario to test out-of-sample robustness."""
    n = len(coords)
    EPI_SIGMA = 100.0 # larger radius for double typhoon
    
    # Double typhoon definition (force 4 epicenters to mimic two storms hitting simultaneously)
    type_name, n_epi, I_lo, I_hi, sev_mult, beta, phi = "double_typhoon", 4, 0.90, 1.05, 3.5, 0.95, 0.90
    
    epi_weights = [aux_risk[i] for i in demand_idx]
    chosen_local = _weighted_sample(demand_idx, epi_weights, n_epi)
    epicenters = [
        (coords[demand_idx[ci]][0], coords[demand_idx[ci]][1], random.uniform(I_lo, I_hi))
        for ci in chosen_local
    ]

    raw_exp = []
    for u in range(n):
        ex = sum(inten * gauss(haversine(coords[u][0], coords[u][1], elat, elon), EPI_SIGMA) for elat, elon, inten in epicenters)
        raw_exp.append(min(1.0, ex))

    risk = []
    for u in range(n):
        r_min, r_max = r_intervals[u]
        r_us = max(0.01, min(0.99, r_min + (r_max - r_min) * raw_exp[u] + random.gauss(0, 0.05)))
        risk.append(round(r_us, 4))

    a = [[[1]*n for _ in range(n)] for _ in range(NUM_MODES)]
    for u in range(n):
        for v in range(n):
            if u == v:
                for m in range(NUM_MODES): a[m][u][v] = 0
                continue
            if random.random() < min(0.99, beta * (risk[u] + risk[v]) / 2.0):
                a[0][u][v] = a[0][v][u] = 0

    demand = {}
    total_demand_pers = 0.0
    for i in demand_idx:
        d_val = max(5.0, base_pop[i] * (0.05 + 0.85 * risk[i]) * sev_mult + random.gauss(0, 0.1 * base_pop[i] * (0.05 + 0.85 * risk[i]) * sev_mult))
        demand[str(i)] = round(d_val, 2)
        total_demand_pers += d_val

    total_supply_kg = GAMMA * total_demand_pers * random.uniform(1.8, 2.5)
    supply = {str(j): round(max(5000.0, total_supply_kg / len(origin_idx) * random.uniform(0.7, 1.3)), 2) for j in origin_idx}

    hub_reactive_cost = {str(k): round(random.uniform(40000, 100000) * (1.0 + risk[k]), 2) for k in hub_idx}
    hub_process_time  = {str(k): round(random.uniform(0.5, 2.0) * (1.0 + 0.5 * risk[k]), 4) for k in hub_idx}

    return [{
        "name": "oos_double_typhoon", "probability": 1.0, "phi_circuity": phi,
        "epicenters": [{"lat": round(e[0],4), "lon": round(e[1],4), "intensity": round(e[2],4)} for e in epicenters],
        "risk": risk, "hub_risk": {str(k): risk[k] for k in hub_idx},
        "accessibility": a, "demand": demand, "supply": supply,
        "hub_reactive_cost": hub_reactive_cost, "hub_process_time": hub_process_time,
    }]

def build_instance_variant(variant="saa", num_scenarios=100):
    n_I, n_H, n_J = 100, 20, 12 # Always use CV-Large size
    
    demand_pool = DEMAND_NODES[:n_I]
    hub_pool    = HUB_NODES[:n_H]
    origin_pool = ORIGIN_NODES[:n_J]
    all_nodes = demand_pool + hub_pool + origin_pool
    n_total   = len(all_nodes)
    coords    = [(lat, lon) for lat, lon, _ in all_nodes]
    names     = [nm for _, _, nm in all_nodes]

    demand_idx = list(range(n_I))
    hub_idx    = list(range(n_I, n_I + n_H))
    origin_idx = list(range(n_I + n_H, n_total))

    aux_risk    = [compute_aux_risk(lat, lon) for lat, lon in coords]
    r_intervals = [risk_interval(r) for r in aux_risk]

    # Deterministic population to match original CV-Large instance
    random.seed(2026) # Reset seed to match base generation
    base_pop = {}
    for i in demand_idx:
        lat, lon = coords[i]
        coast_f = max(0.15, 1.0 - abs(lon - 108.2) / 1.6)
        pop_base = int(500 + 6500 * coast_f)
        noise    = int(random.gauss(0, 0.12 * pop_base))
        base_pop[i] = max(100, pop_base + noise)

    area_km2 = {}
    for i in demand_idx:
        _, lon = coords[i]
        tf = terrain_factor(lon)
        area_km2[str(i)] = round(random.uniform(8.0, 18.0) * tf, 2)

    C_all, T_all = build_transport(coords)
    
    # Branch behavior based on variant
    if variant == "saa":
        print(f"Generating SAA ensemble with {num_scenarios} scenarios...")
        # change seed so the SAA scenarios are differently drawn but base params are same
        random.seed(9999)
        scenarios = generate_saa_scenarios(coords, aux_risk, r_intervals, demand_idx, hub_idx, origin_idx, base_pop, num_scenarios)
    elif variant == "oos":
        print("Generating OOS Double Typhoon scenario...")
        random.seed(7777)
        scenarios = generate_oos_scenario(coords, aux_risk, r_intervals, demand_idx, hub_idx, origin_idx, base_pop)

    # Note: Hub capacities should strictly match the original CV-Large to remain a valid testing ground. 
    # To do that, we briefly generate the 3 training scenarios using seed 2026 just to set the max capacity, 
    # matching what generate_cv.py would do.
    random.seed(2026)
    from data_generate_cv import generate_scenarios as orig_generate_scenarios
    orig_scens = orig_generate_scenarios(coords, aux_risk, r_intervals, demand_idx, hub_idx, origin_idx, base_pop)
    max_demand_kg = max(GAMMA * sum(float(v) for v in sc["demand"].values()) for sc in orig_scens)
    hub_capacity   = {}
    hub_fixed_cost = {}
    hub_hold_cost  = {}
    for k in hub_idx:
        _, lon = coords[k]
        tf = terrain_factor(lon)
        hub_capacity[str(k)]   = int(max_demand_kg / n_H * random.uniform(3.0, 6.0) * tf)
        hub_fixed_cost[str(k)] = round(random.uniform(60000, 200000) * tf, 2)
        hub_hold_cost[str(k)]  = round(random.uniform(0.2, 0.8), 4)

    Theta = compute_theta(C_all, hub_idx, demand_idx, scenarios, area_km2)

    Lambda = {}
    for si, sc in enumerate(scenarios):
        for i in demand_idx:
            Lambda[f"{i}_{si}"] = round(LAMBDA0 * (1.0 + sc["risk"][i]), 4)

    return {
        "meta": {
            "name": f"CentralVietnam_LARGE_{variant.upper()}",
            "description": f"MO-IHLNDP flood relief - {variant.upper()} Evaluation Set",
            "seed": SEED, "size": "large", "variant": variant
        },
        "dimensions": {
            "num_I": n_I, "num_H": n_H, "num_J": n_J,
            "num_S": len(scenarios), "num_M": NUM_MODES,
        },
        "nodes": {
            "coords": [[lat, lon] for lat, lon in coords], "names": names,
            "demand_indices": demand_idx, "hub_indices": hub_idx, "origin_indices": origin_idx,
            "aux_risk": aux_risk, "risk_intervals": [[r[0], r[1]] for r in r_intervals],
        },
        "global_params": {
            "alpha": ALPHA, "chi": CHI, "gamma": GAMMA,
            "big_M": BIG_M, "daganzo_phi": 0.57, "daganzo_eta": DAGANZO_ETA,
        },
        "hub_params": {
            "capacity": hub_capacity, "fixed_cost": hub_fixed_cost, "hold_cost": hub_hold_cost,
        },
        "base_population": {str(i): base_pop[i] for i in demand_idx},
        "area_km2": area_km2,
        "transport": {"cost": C_all, "time": T_all},
        "scenarios": scenarios, "theta": Theta, "lambda": Lambda,
    }

def main():
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../data_prep")
    os.makedirs(out_dir, exist_ok=True)

    saa_inst = build_instance_variant("saa", 100)
    with open(os.path.join(out_dir, "cv_large_saa100.json"), "w", encoding="utf-8") as f:
        json.dump(saa_inst, f, indent=2, ensure_ascii=False)
    print("Saved SAA 100 instance.")

    oos_inst = build_instance_variant("oos")
    with open(os.path.join(out_dir, "cv_large_oos.json"), "w", encoding="utf-8") as f:
        json.dump(oos_inst, f, indent=2, ensure_ascii=False)
    print("Saved OOS Double Typhoon instance.")

if __name__ == "__main__":
    main()
