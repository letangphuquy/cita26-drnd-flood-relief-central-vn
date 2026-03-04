"""
process_benchmark.py
====================
Converts standard Hub Location Problem (HLP) benchmark datasets (TR81, AP)
into the DRND (Disaster Relief Network Design) JSON format expected by the
PB-NSGA-II solver.

Missing DRND parameters (risk index, accessibility, demand, Daganzo CA Theta,
etc.) are synthetically generated following the same methodology as
generate_synthetic.py, but adapted to the benchmark's coordinate space.

OUTPUTS (to data/ folder):
  data/TR81_drnd.json
  data/AP10_drnd.json
  data/AP20_drnd.json
  data/AP25_drnd.json
  data/AP40_drnd.json
  data/AP50_drnd.json
  data/AP100_drnd.json

Benchmark hub selection: top-K nodes by out-degree centrality in the flow matrix.
"""

import math
import json
import random
import os

SEED = 42
random.seed(SEED)

# ---------------------------------------------------------------------------
# Shared DRND parameters (same as generate_synthetic.py)
# ---------------------------------------------------------------------------
NUM_MODES   = 3
NUM_SCENARIOS = 3
ALPHA_ECON  = 0.6
CHI_SAFETY  = 0.7    # max acceptable hub risk
GAMMA_CONV  = 3.0
DAGANZO_PHI = 0.57
ETA         = 5
LAMBDA0     = 0.8
BASE_RISK   = 0.08
BIG_M       = 1e9

SCENARIO_PARAMS = [
    ("mild",    0.60, 1, 0.20),  # (name, prob, n_epicenters, disruption_beta)
    ("severe",  0.30, 2, 0.55),
    ("extreme", 0.10, 3, 0.90),
]
SCENARIO_SEV = [1.0, 1.6, 2.5]

# Transport mode parameters (consistent with generate_synthetic.py)
MODE_CAP  = [60, 25, 10]        # vehicle capacity per mode (road, water, air)
MODE_COST = [2.0, 5.0, 40.0]   # cost per km per mode
# Mode 0: road  — fast, disrupted;  Mode 1: water — resilient;  Mode 2: air — always
WATER_SPEED = 25.0  # km/h
AIR_SPEED   = 150.0  # km/h
ROAD_SPEED  = 35.0   # km/h

# ---------------------------------------------------------------------------
# Euclidean distance (for AP/CAB which use Euclidean coordinate space)
# ---------------------------------------------------------------------------
def euclid(x1, y1, x2, y2):
    return math.hypot(x1 - x2, y1 - y2)

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ---------------------------------------------------------------------------
# Select hub candidates: top-K nodes by total out-flow (W matrix)
# ---------------------------------------------------------------------------
def select_hubs_by_centrality(W, n, k_hubs):
    """Select k hub candidates = nodes with highest total flow (origin + destination)."""
    total_flow = [sum(W[i][j] + W[j][i] for j in range(n)) for i in range(n)]
    ranked = sorted(range(n), key=lambda i: total_flow[i], reverse=True)
    return sorted(ranked[:k_hubs])

def select_origins(n, hub_indices, k_origins):
    """Origins: nodes with highest out-degree among non-hub nodes (boundary nodes)."""
    non_hubs = [i for i in range(n) if i not in hub_indices]
    # For benchmarks without geo info, pick from extreme indices (boundary)
    return sorted(non_hubs[:k_origins])

# ---------------------------------------------------------------------------
# Generate DRND parameters from distance matrix C and optional coords
# ---------------------------------------------------------------------------
def generate_drnd_params(n, C_raw, W_raw, coords_raw, hub_frac=0.2, origin_frac=0.05, use_euclidean=True):
    """
    Build full DRND instance from an n×n cost matrix.
    
    Parameters
    ----------
    n : int
    C_raw : n×n cost/distance matrix
    W_raw : n×n flow/demand matrix (used for centrality)
    coords_raw : list of (x,y) or (lat,lon); None if not available
    hub_frac : fraction of nodes as hub candidates
    origin_frac : fraction of nodes as origins
    use_euclidean : True for AP (Euclidean space), False for TR (real coords)
    
    Returns
    -------
    dict : complete DRND instance dict
    """
    n_hub    = max(3, int(n * hub_frac))
    n_origin = max(2, int(n * origin_frac))

    # ── Node classification ──────────────────────────────────────────────
    hub_indices    = select_hubs_by_centrality(W_raw, n, n_hub)
    origin_indices = select_origins(n, hub_indices, n_origin)
    demand_indices = [i for i in range(n) if i not in hub_indices and i not in origin_indices]

    # ── Multi-mode cost and time matrices ────────────────────────────────
    # AP/TR benchmark Euclidean coordinates are NOT in km.
    # Raw max distance can be 8000+ units → travel times 200+ hours → expm1 overflow.
    # Normalize so that the maximum pairwise distance = MAX_KM_SCALE km.
    MAX_KM_SCALE = 500.0  # network spans at most ~500km (Vietnam/Turkey scale)
    max_raw_dist = max(
        (C_raw[i][j] for i in range(n) for j in range(n) if i != j),
        default=1.0
    )
    dist_scale = MAX_KM_SCALE / max(1.0, max_raw_dist)

    C_all = [[[0.0]*n for _ in range(n)] for _ in range(NUM_MODES)]
    T_all = [[[0.0]*n for _ in range(n)] for _ in range(NUM_MODES)]

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            d_km = C_raw[i][j] * dist_scale  # normalized km
            C_all[0][i][j] = d_km * MODE_COST[0]
            C_all[1][i][j] = d_km * MODE_COST[1]
            C_all[2][i][j] = d_km * MODE_COST[2]
            # Time in hours (normalized km ÷ realistic speed)
            T_all[0][i][j] = d_km / ROAD_SPEED
            T_all[1][i][j] = d_km / WATER_SPEED
            T_all[2][i][j] = d_km / AIR_SPEED

    # ── Hub parameters ───────────────────────────────────────────────────
    avg_C = sum(C_raw[i][j] for i in range(n) for j in range(n) if i != j) / max(1, n*(n-1))
    # ── Base population ───────────────────────────────────────────────────
    # Proxy: nodes with more incoming flow have higher "population"
    in_flow = [sum(W_raw[j][i] for j in range(n)) for i in range(n)]
    max_flow = max(in_flow) if max(in_flow) > 0 else 1.0
    base_population = {i: max(100, int(5000 * in_flow[i] / max_flow)) for i in demand_indices}
    # Hub capacity in KG — proportional to total flow-estimated demand × gamma
    # Estimate avg person-based demand for benchmark: use in-flow as proxy
    est_total_persons = sum(max(1.0, in_flow[i] / max(1.0, max_flow)) * 2000 for i in demand_indices)
    est_total_kg = GAMMA_CONV * est_total_persons * 2.5  # worst-case severity
    hub_capacity   = {k: int(est_total_kg / max(1, len(hub_indices)) * random.uniform(2.5, 5.0)) for k in hub_indices}
    hub_fixed_cost = {k: avg_C * random.uniform(50, 200) for k in hub_indices}
    hub_hold_cost  = {k: random.uniform(0.2, 1.0) for k in hub_indices}

    # ── Area per demand node (km²) ────────────────────────────────────────
    area_km2 = {i: random.uniform(10, 40) for i in demand_indices}

    # ── Scenarios ────────────────────────────────────────────────────────
    # Use random epicenters among all nodes
    scenarios = []
    for sp_idx, (sp_name, sp_prob, n_ep, sp_beta) in enumerate(SCENARIO_PARAMS):
        sev = SCENARIO_SEV[sp_idx]

        # Epicenters
        ep_nodes = random.sample(list(range(n)), min(n_ep, n))
        # Sigma in "distance units" — use avg_C as scale
        sigma = avg_C * random.uniform(0.8, 1.5)

        # Risk index for all nodes
        risk = []
        for u in range(n):
            r = BASE_RISK
            for e in ep_nodes:
                d = C_raw[u][e]
                intensity = random.uniform(0.4, 1.0)
                r += intensity * math.exp(-d**2 / (2 * sigma**2))
            risk.append(min(1.0, r))

        # Accessibility
        a = [[[1]*n for _ in range(n)] for _ in range(NUM_MODES)]
        for u in range(n):
            for v in range(n):
                if u == v:
                    for m in range(NUM_MODES):
                        a[m][u][v] = 0
                    continue
                avg_r = (risk[u] + risk[v]) / 2.0
                p_dis = min(1.0, sp_beta * avg_r)
                if random.random() < p_dis:
                    a[0][u][v] = 0
                    a[0][v][u] = 0
                # water, air always 1

        # Demand
        demand = {}
        for i in demand_indices:
            r_is = risk[i]
            pop  = base_population[i]
            d_base = pop * (0.1 + 0.9 * r_is) * sev
            noise  = random.gauss(0, 0.05 * d_base)
            demand[i] = max(10.0, d_base + noise)

        # Supply: cover 1.5-2.5× total demand in kg
        total_demand_kg = GAMMA_CONV * sum(demand.values())
        total_supply_target = total_demand_kg * random.uniform(1.5, 2.5)
        supply = {}
        for j in origin_indices:
            frac = random.uniform(0.8, 1.2)
            supply[j] = max(5000.0, total_supply_target / max(1, len(origin_indices)) * frac)

        hub_reactive_cost = {k: random.uniform(30000, 80000) * (1 + risk[k]) for k in hub_indices}
        hub_process_time  = {k: random.uniform(0.5, 2.0) * (1 + risk[k]) for k in hub_indices}

        scenarios.append({
            "name": sp_name,
            "probability": sp_prob,
            "epicenters": [{"node": e, "intensity": random.uniform(0.4, 1.0)} for e in ep_nodes],
            "risk": risk,
            "hub_risk": {str(k): risk[k] for k in hub_indices},
            "accessibility": a,
            "demand": {str(i): d for i, d in demand.items()},
            "supply": {str(j): s for j, s in supply.items()},
            "hub_reactive_cost": {str(k): v for k, v in hub_reactive_cost.items()},
            "hub_process_time": {str(k): v for k, v in hub_process_time.items()},
        })

    # ── Daganzo Theta matrix ──────────────────────────────────────────────
    C_m_per_unit = 2.5
    Theta = [[[0.0]*NUM_SCENARIOS for _ in range(len(demand_indices))] for _ in range(len(hub_indices))]
    for ki, k in enumerate(hub_indices):
        for ii, i in enumerate(demand_indices):
            for si, sc in enumerate(scenarios):
                D_is = sc["demand"].get(str(i), 0.0)
                A_i  = area_km2[i]
                best = BIG_M
                for m in range(NUM_MODES):
                    if sc["accessibility"][m][k][i] == 0:
                        continue
                    qm = MODE_CAP[m]
                    cm = C_all[m][k][i]
                    trips = max(1, math.ceil(D_is / qm))
                    n_stops = max(1, math.ceil(D_is / ETA))
                    theta = 2.0 * cm * trips + C_m_per_unit * DAGANZO_PHI * math.sqrt(n_stops * A_i)
                    if theta < best:
                        best = theta
                Theta[ki][ii][si] = best

    # ── Lambda ───────────────────────────────────────────────────────────
    Lambda = {}
    for si, sc in enumerate(scenarios):
        for i in demand_indices:
            r_is = sc["risk"][i]
            Lambda[f"{i}_{si}"] = LAMBDA0 * (1.0 + r_is)

    coords_out = coords_raw if coords_raw else [[0.0, 0.0]] * n
    names_out  = [f"Node_{i}" for i in range(n)]

    instance = {
        "meta": {
            "source": "benchmark",
            "seed": SEED,
        },
        "dimensions": {
            "num_I": len(demand_indices),
            "num_H": len(hub_indices),
            "num_J": len(origin_indices),
            "num_S": NUM_SCENARIOS,
            "num_M": NUM_MODES,
        },
        "nodes": {
            "coords": coords_out,
            "names": names_out,
            "demand_indices": demand_indices,
            "hub_indices": hub_indices,
            "origin_indices": origin_indices,
        },
        "global_params": {
            "alpha": ALPHA_ECON,
            "chi": CHI_SAFETY,
            "gamma": GAMMA_CONV,
            "big_M": BIG_M,
            "daganzo_phi": DAGANZO_PHI,
            "daganzo_eta": ETA,
        },
        "hub_params": {
            "capacity":   {str(k): hub_capacity[k]   for k in hub_indices},
            "fixed_cost": {str(k): hub_fixed_cost[k] for k in hub_indices},
            "hold_cost":  {str(k): hub_hold_cost[k]  for k in hub_indices},
        },
        "base_population": {str(i): base_population[i] for i in demand_indices},
        "area_km2":        {str(i): area_km2[i]        for i in demand_indices},
        "transport": {
            "cost": C_all,
            "time": T_all,
        },
        "scenarios": scenarios,
        "theta": Theta,
        "lambda": Lambda,
    }
    return instance


# ---------------------------------------------------------------------------
# AP Dataset Processor
# ---------------------------------------------------------------------------
def process_ap(ap_folder, out_dir):
    """
    Process AP benchmark files.
    AP format:
      Line 1 : n (number of nodes)
      Lines 2..n+1: x y (coordinates, Euclidean)
      Lines n+2..2n+1: n×n flow matrix W
    """
    ap_sizes = ["10.2", "20.3", "25.3", "40.3", "50.3", "100.3"]
    for size_str in ap_sizes:
        n_str = size_str.split('.')[0]
        in_path = os.path.join(ap_folder, size_str)
        if not os.path.exists(in_path):
            print(f"  [AP] Missing: {in_path}, skipping.")
            continue

        with open(in_path, 'r') as f:
            lines = [l.strip() for l in f if l.strip()]

        n = int(lines[0])
        coords = []
        for i in range(1, n + 1):
            parts = lines[i].split()
            coords.append([float(parts[0]), float(parts[1])])

        W = []
        for i in range(n + 1, n + 1 + n):
            row = [float(x) for x in lines[i].split()]
            W.append(row)

        # Euclidean distance matrix
        C = [[0.0]*n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                C[i][j] = euclid(coords[i][0], coords[i][1], coords[j][0], coords[j][1])

        print(f"  [AP{n}] Processing n={n} ...")
        random.seed(SEED)  # reset seed for reproducibility per instance
        instance = generate_drnd_params(n, C, W, coords, hub_frac=0.2, origin_frac=0.05, use_euclidean=True)
        instance["meta"]["name"] = f"AP{n}"
        instance["meta"]["description"] = f"AP benchmark (n={n}) extended to DRND format"

        out_path = os.path.join(out_dir, f"AP{n}_drnd.json")
        with open(out_path, 'w') as f:
            json.dump(instance, f, indent=2)
        print(f"  [AP{n}] Saved: {out_path}  (I={instance['dimensions']['num_I']}, H={instance['dimensions']['num_H']}, J={instance['dimensions']['num_J']})")


# ---------------------------------------------------------------------------
# TR (Turkish) Dataset Processor
# ---------------------------------------------------------------------------
def process_turkish(excel_path, out_dir):
    """
    Process Turkish network Excel file.
    Sheets: 'Distance (km)', 'Flow'
    """
    try:
        import pandas as pd
    except ImportError:
        print("  [TR] pandas not installed. Skipping TR81. Install with: pip install pandas openpyxl")
        return

    if not os.path.exists(excel_path):
        print(f"  [TR] Missing: {excel_path}, skipping.")
        return

    print("  [TR81] Reading Excel ...")
    df_dist = pd.read_excel(excel_path, sheet_name='Distance (km)', index_col=0).fillna(0)
    df_flow = pd.read_excel(excel_path, sheet_name='Flow', index_col=0).fillna(0)

    n = df_dist.shape[0]
    C = [pd.to_numeric(df_dist.iloc[i], errors='coerce').fillna(0).tolist() for i in range(n)]
    W = [pd.to_numeric(df_flow.iloc[i], errors='coerce').fillna(0).tolist() for i in range(n)]
    names = df_dist.index.astype(str).tolist()
    # No coordinates in original TR dataset
    coords = [[0.0, 0.0]] * n

    print(f"  [TR81] Processing n={n} ...")
    random.seed(SEED)
    instance = generate_drnd_params(n, C, W, coords, hub_frac=0.15, origin_frac=0.05, use_euclidean=False)
    instance["meta"]["name"] = "TR81"
    instance["meta"]["description"] = "Turkish 81-city network extended to DRND format"
    instance["nodes"]["names"] = names

    out_path = os.path.join(out_dir, "TR81_drnd.json")
    with open(out_path, 'w') as f:
        json.dump(instance, f, indent=2)
    print(f"  [TR81] Saved: {out_path}  (I={instance['dimensions']['num_I']}, H={instance['dimensions']['num_H']}, J={instance['dimensions']['num_J']})")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    ap_folder   = os.path.join(project_dir, "dataset", "AP")
    tr_excel    = os.path.join(project_dir, "dataset", "Turkish network.xls")
    out_dir     = script_dir   # outputs to data/

    print("=" * 60)
    print("Processing benchmark datasets → DRND JSON format")
    print("=" * 60)

    process_ap(ap_folder, out_dir)
    process_turkish(tr_excel, out_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
