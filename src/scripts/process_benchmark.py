"""
process_benchmark.py — HLP Benchmark-to-DRND Converter
=======================================================
STATUS: Active (data preparation) — called from run_experiments.bat / .sh when
        regenerating datasets (run_experiments.bat data).

Converts the standard Hub Location Problem (HLP) benchmark datasets (TR81, AP10/
20/25/40/50/100) into the DRND (Disaster Relief Network Design) JSON format
expected by the PB-NSGA-II solver.

Missing DRND fields (risk index, accessibility, demand, Daganzo CA Theta, etc.)
are synthetically generated following the same four-criterion risk scoring
methodology as generate_cv.py, adapted to each benchmark's coordinate space.

OUTPUTS (written to --outdir, default data/hlp-benchmark/):
  AP10_seed<N>_drnd.json  ...  AP100_seed<N>_drnd.json
  TR81_seed<N>_drnd.json

Note: The AP/TR81 benchmark runs are archived (see run_experiments.bat comment).
      These datasets are preserved for potential future comparisons but are not
      part of the current paper's primary narrative.

Usage (canonical, from project root):
  python src/scripts/process_benchmark.py --outdir data/hlp-benchmark   # default seed=42
  python src/scripts/process_benchmark.py --outdir data/hlp-benchmark --seed 7
"""

import math
import json
import random
import os
import argparse

DEFAULT_SEED = 42

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
DISRUPTION_PENALTY = 50.0  # cost multiplier for disrupted road links in Theta (soft penalty)

# Transport mode parameters (consistent with generate_synthetic.py)
MODE_CAP  = [60, 25, 10]        # vehicle capacity per mode (road, water, air)
MODE_COST = [2.0, 5.0, 40.0]   # cost per km per mode
# Mode 0: road  — fast, disrupted;  Mode 1: water — resilient;  Mode 2: air — always
WATER_SPEED = 25.0  # km/h
AIR_SPEED   = 150.0  # km/h
ROAD_SPEED  = 35.0   # km/h

# ---------------------------------------------------------------------------
# Turkish 81-city coordinates [lat, lon] — provincial capital city centers.
# Order matches "Turkish network.txt" city index 1–81.
# ---------------------------------------------------------------------------
TR81_COORDS = [
    [37.00, 35.32],  #  1 ADANA
    [37.76, 38.28],  #  2 ADIYAMAN
    [38.76, 30.54],  #  3 AFYON
    [39.72, 43.06],  #  4 AĞRI
    [40.65, 35.83],  #  5 AMASYA
    [39.93, 32.86],  #  6 ANKARA
    [36.90, 30.70],  #  7 ANTALYA
    [41.18, 41.82],  #  8 ARTVİN
    [37.85, 27.84],  #  9 AYDIN
    [39.65, 27.89],  # 10 BALIKESİR
    [40.15, 29.98],  # 11 BİLECİK
    [38.88, 40.50],  # 12 BİNGÖL
    [38.40, 42.12],  # 13 BİTLİS
    [40.74, 31.61],  # 14 BOLU
    [37.72, 30.29],  # 15 BURDUR
    [40.18, 29.06],  # 16 BURSA
    [40.14, 26.41],  # 17 ÇANAKKALE
    [40.60, 33.62],  # 18 ÇANKIRI
    [40.55, 34.96],  # 19 ÇORUM
    [37.77, 29.09],  # 20 DENİZLİ
    [37.91, 40.22],  # 21 DİYARBAKIR
    [41.68, 26.56],  # 22 EDİRNE
    [38.68, 39.22],  # 23 ELAZIĞ
    [39.75, 39.49],  # 24 ERZİNCAN
    [39.91, 41.27],  # 25 ERZURUM
    [39.78, 30.52],  # 26 ESKİŞEHİR
    [37.07, 37.38],  # 27 GAZİANTEP
    [40.91, 38.39],  # 28 GİRESUN
    [40.46, 39.48],  # 29 GÜMÜŞHANE
    [37.57, 43.74],  # 30 HAKKARİ
    [36.20, 36.16],  # 31 HATAY
    [37.76, 30.55],  # 32 ISPARTA
    [36.80, 34.64],  # 33 İÇEL
    [41.01, 28.96],  # 34 İSTANBUL
    [38.42, 27.14],  # 35 İZMİR
    [40.61, 43.09],  # 36 KARS
    [41.37, 33.78],  # 37 KASTAMONU
    [38.73, 35.49],  # 38 KAYSERİ
    [41.74, 27.22],  # 39 KIRKLARELİ
    [39.14, 34.16],  # 40 KIRŞEHİR
    [40.85, 29.88],  # 41 KOCAELİ
    [37.87, 32.50],  # 42 KONYA
    [39.42, 29.99],  # 43 KÜTAHYA
    [38.35, 38.32],  # 44 MALATYA
    [38.61, 27.43],  # 45 MANİSA
    [37.59, 36.93],  # 46 KAHRAMANMARAŞ
    [37.31, 40.74],  # 47 MARDİN
    [37.22, 28.36],  # 48 MUĞLA
    [38.74, 41.49],  # 49 MUŞ
    [38.62, 34.72],  # 50 NEVŞEHİR
    [37.97, 34.68],  # 51 NİĞDE
    [40.98, 37.88],  # 52 ORDU
    [41.02, 40.52],  # 53 RİZE
    [40.78, 30.40],  # 54 SAKARYA
    [41.29, 36.33],  # 55 SAMSUN
    [37.93, 41.95],  # 56 SİİRT
    [42.02, 35.15],  # 57 SİNOP
    [39.75, 37.02],  # 58 SİVAS
    [40.98, 27.51],  # 59 TEKİRDAĞ
    [40.31, 36.55],  # 60 TOKAT
    [41.00, 39.73],  # 61 TRABZON
    [39.11, 39.55],  # 62 TUNCELİ
    [37.16, 38.79],  # 63 ŞANLIURFA
    [38.68, 29.41],  # 64 UŞAK
    [38.50, 43.37],  # 65 VAN
    [39.82, 34.81],  # 66 YOZGAT
    [41.44, 31.80],  # 67 ZONGULDAK
    [38.37, 34.04],  # 68 AKSARAY
    [40.25, 40.23],  # 69 BAYBURT
    [37.18, 33.22],  # 70 KARAMAN
    [39.85, 33.50],  # 71 KIRIKKALE
    [37.88, 41.13],  # 72 BATMAN
    [37.52, 42.46],  # 73 ŞIRNAK
    [41.63, 32.34],  # 74 BARTIN
    [41.11, 42.70],  # 75 ARDAHAN
    [39.92, 44.05],  # 76 IĞDIR
    [40.65, 29.27],  # 77 YALOVA
    [41.20, 32.63],  # 78 KARABÜK
    [36.72, 37.12],  # 79 KİLİS
    [37.07, 36.25],  # 80 OSMANİYE
    [40.84, 31.16],  # 81 DÜZCE
]

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
# M1 – Hub selection: safety-flow tradeoff
# ---------------------------------------------------------------------------
def select_hubs_by_centrality(W, n, k_hubs):
    """Select k hub candidates balancing flow centrality with disaster safety.

    High-flow nodes are estimated riskier (central nodes bear more disaster
    impact).  Score = total_flow × (1 − risk_proxy) where:
        risk_proxy = BASE_RISK + 0.30 × (flow / max_flow)
    This penalises the very highest-traffic nodes, preferring slightly
    off-peak nodes that retain good connectivity but lower estimated risk.
    """
    total_flow = [sum(W[i][j] + W[j][i] for j in range(n)) for i in range(n)]
    max_flow_val = max(total_flow) if total_flow else 1.0
    hub_score = [
        total_flow[i] * (1.0 - (BASE_RISK + 0.30 * total_flow[i] / max_flow_val))
        for i in range(n)
    ]
    ranked = sorted(range(n), key=lambda i: hub_score[i], reverse=True)
    return sorted(ranked[:k_hubs])

def select_origins(n, hub_indices, k_origins, W):
    """Origins: non-hub nodes with highest total out-flow (major supply sources)."""
    hub_set = set(hub_indices)
    non_hubs = [i for i in range(n) if i not in hub_set]
    out_flow = [sum(W[i]) for i in non_hubs]
    ranked = sorted(zip(non_hubs, out_flow), key=lambda x: -x[1])
    return sorted(x[0] for x in ranked[:k_origins])

# ---------------------------------------------------------------------------
# Generate DRND parameters from distance matrix C and optional coords
# ---------------------------------------------------------------------------
def generate_drnd_params(n, C_raw, W_raw, coords_raw, hub_frac=0.2, origin_frac=0.05, seed=DEFAULT_SEED):
    """
    Build full DRND instance from an n×n cost matrix.

    Parameters
    ----------
    n : int
    C_raw : n×n cost/distance matrix (arbitrary units; normalized internally to km)
    W_raw : n×n flow/demand matrix (used for centrality)
    coords_raw : list of [x,y] or [lat,lon]; None if not available
    hub_frac : fraction of nodes as hub candidates
    origin_frac : fraction of nodes as origins
    seed : RNG seed for full reproducibility

    Returns
    -------
    dict : complete DRND instance dict
    """
    random.seed(seed)

    n_hub    = max(3, int(n * hub_frac))
    n_origin = max(2, int(n * origin_frac))

    # ── Node classification ──────────────────────────────────────────────
    hub_indices    = select_hubs_by_centrality(W_raw, n, n_hub)
    origin_indices = select_origins(n, hub_indices, n_origin, W_raw)
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
    avg_C    = sum(C_raw[i][j] for i in range(n) for j in range(n) if i != j) / max(1, n*(n-1))
    avg_C_km = avg_C * dist_scale  # normalized km average — used for cost-unit consistency
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
    # Fixed cost expressed in km-normalised units so AP and TR81 are on the same scale.
    hub_fixed_cost = {k: avg_C_km * random.uniform(50, 200) for k in hub_indices}
    hub_hold_cost  = {k: random.uniform(0.2, 1.0) for k in hub_indices}

    # ── M2: Area per demand node from nearest-neighbour distance proxy ────
    # Each demand node "owns" a disk of radius ≈ half its nearest-neighbour
    # distance in km.  A = π × (d_nn / 2)²  clamped to [5, 3000] km².
    # Geometrically grounded substitute for uniform random [10, 40].
    area_km2 = {}
    for i in demand_indices:
        candidates = [C_raw[i][j] * dist_scale for j in range(n) if j != i and C_raw[i][j] > 0]
        d_nn_km = min(candidates) if candidates else 10.0
        area_km2[i] = max(5.0, min(3000.0, math.pi * (d_nn_km / 2.0) ** 2))

    # ── Scenarios ────────────────────────────────────────────────────────
    scenarios = []
    for sp_idx, (sp_name, sp_prob, n_ep, sp_beta) in enumerate(SCENARIO_PARAMS):
        sev = SCENARIO_SEV[sp_idx]

        # Epicenters
        ep_nodes = random.sample(list(range(n)), min(n_ep, n))
        # Sigma ≈ 25–35% of avg pairwise distance → decay reaches ~5% at 2σ
        # (using 0.8–1.5 made sigma ≈ network diameter, producing near-uniform risk)
        sigma = avg_C * random.uniform(0.25, 0.35)

        # Risk index for all nodes
        risk = []
        for u in range(n):
            r = BASE_RISK
            for e in ep_nodes:
                d = C_raw[u][e]
                intensity = random.uniform(0.4, 1.0)
                r += intensity * math.exp(-d**2 / (2 * sigma**2))
            risk.append(min(1.0, r))

        # CHI_SAFETY feasibility guard: warn if no hub candidate is safe enough
        safe_hubs = [k for k in hub_indices if risk[k] <= CHI_SAFETY]
        if not safe_hubs:
            print(f"  [WARN] Scenario '{sp_name}': all {len(hub_indices)} hub candidates "
                  f"have risk > chi={CHI_SAFETY:.2f}. Solver may find no feasible hub set.")

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
                    cm = C_all[m][k][i]
                    # Disrupted road (a=0): apply soft penalty instead of hard skip.
                    # Water/air (modes 1,2) are always accessible; road disruption
                    # inflates cost 50× so the solver still has a finite Theta value
                    # and can meaningfully compare disrupted-road vs water/air cost.
                    if sc["accessibility"][m][k][i] == 0:
                        cm = cm * DISRUPTION_PENALTY
                    qm = MODE_CAP[m]
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
            "seed": seed,
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
def process_ap(ap_folder, out_dir, seed=DEFAULT_SEED):
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

        print(f"  [AP{n}] Processing n={n}, seed={seed} ...")
        instance = generate_drnd_params(n, C, W, coords, hub_frac=0.2, origin_frac=0.05, seed=seed)
        instance["meta"]["name"] = f"AP{n}"
        instance["meta"]["description"] = f"AP benchmark (n={n}) extended to DRND format"

        out_path = os.path.join(out_dir, f"AP{n}_seed{seed}_drnd.json")
        with open(out_path, 'w') as f:
            json.dump(instance, f, indent=2)
        print(f"  [AP{n}] Saved: {out_path}  "
              f"(I={instance['dimensions']['num_I']}, "
              f"H={instance['dimensions']['num_H']}, "
              f"J={instance['dimensions']['num_J']})")


# ---------------------------------------------------------------------------
# TR (Turkish) Dataset Processor
# ---------------------------------------------------------------------------
def process_turkish(excel_path, out_dir, seed=DEFAULT_SEED):
    """
    Process Turkish network Excel file.
    Sheets: 'Distance (km)', 'Flow'

    The Excel layout has an extra header row (city names as labels) and an
    extra city-name column, producing an 82×82 frame.  We drop both to get
    the clean 81×81 numeric matrices and extract city names separately.
    Coordinates come from the TR81_COORDS lookup table.
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
    df_flow = pd.read_excel(excel_path, sheet_name='Flow',          index_col=0).fillna(0)

    # The Excel has shape (82, 82):
    #   - Row 0  (index=NaN): city-name header row (strings, not distances)
    #   - Rows 1–81 (index=1.0–81.0): one row per city
    #   - Column 0 ('Unnamed: 1'): city name label for each row
    #   - Columns 1–81: numeric distance/flow values
    #
    # Extract city names from the label column of rows 1–81.
    name_col = df_dist.columns[0]  # 'Unnamed: 1' or similar
    names = df_dist[name_col].iloc[1:].astype(str).str.strip().tolist()  # 81 names

    # Drop the header row and the name column → clean 81×81 numeric matrices
    df_dist_clean = df_dist.iloc[1:, 1:]
    df_flow_clean = df_flow.iloc[1:, 1:]
    n = 81  # always 81 cities

    C = [pd.to_numeric(df_dist_clean.iloc[i], errors='coerce').fillna(0).tolist() for i in range(n)]
    W = [pd.to_numeric(df_flow_clean.iloc[i], errors='coerce').fillna(0).tolist() for i in range(n)]

    # TR81_COORDS is indexed 0–80 matching cities 1–81
    coords = [list(c) for c in TR81_COORDS]

    print(f"  [TR81] Processing n={n}, seed={seed} ...")
    instance = generate_drnd_params(n, C, W, coords, hub_frac=0.15, origin_frac=0.05, seed=seed)
    instance["meta"]["name"] = "TR81"
    instance["meta"]["description"] = "Turkish 81-city network extended to DRND format"
    instance["nodes"]["names"] = names

    out_path = os.path.join(out_dir, f"TR81_seed{seed}_drnd.json")
    with open(out_path, 'w') as f:
        json.dump(instance, f, indent=2)
    print(f"  [TR81] Saved: {out_path}  "
          f"(I={instance['dimensions']['num_I']}, "
          f"H={instance['dimensions']['num_H']}, "
          f"J={instance['dimensions']['num_J']})")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Convert HLP benchmark datasets to DRND JSON format."
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED,
        help=f"Random seed for synthetic parameter generation (default: {DEFAULT_SEED}). "
             "Run with different seeds to assess statistical robustness."
    )
    parser.add_argument(
        "--outdir", type=str, default=None,
        help="Output directory for generated DRND JSON files (default: same as script)."
    )
    args = parser.parse_args()
    seed = args.seed

    script_dir  = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    ap_folder   = os.path.join(project_dir, "hlp-benchmark", "AP")
    tr_excel    = os.path.join(project_dir, "hlp-benchmark", "Turkish network.xls")
    out_dir     = args.outdir if args.outdir else script_dir
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 60)
    print(f"Processing benchmark datasets → DRND JSON format  (seed={seed})")
    print("=" * 60)

    process_ap(ap_folder, out_dir, seed=seed)
    process_turkish(tr_excel, out_dir, seed=seed)

    print("\nDone.")


if __name__ == "__main__":
    main()
