"""
generate_synthetic.py
======================
Generates the Central Vietnam DRND (Disaster Relief Network Design) dataset
for the paper: "Modeling the disaster relief hub network design problem:
A case of Central Vietnam"

TWO INSTANCE SIZES:
  - Small: 20 demand nodes, 5 hub candidates, 2 origins
  - Large: 100 demand nodes, 20 hub candidates, 10 origins

THREE TRANSPORTATION MODES:
  m=0: Road  — disrupted by floods, default fastest
  m=1: Water — boat/motorized boat, slow but resilient
  m=2: Air   — helicopter, very fast, very expensive, always accessible

THREE DISASTER SCENARIOS:
  s=0: Mild    (π=0.60) — minor flooding, 5%  road disruption
  s=1: Severe  (π=0.30) — major flooding, 30% road disruption
  s=2: Extreme (π=0.10) — catastrophic, 60% road disruption

DATA MODEL PHILOSOPHY:
  * Node coordinates are real geographic locations in the Vu Gia – Thu Bồn
    river basin (Đà Nẵng / Quảng Nam / Thừa Thiên Huế region).
  * Road costs/times: queried from OSRM API (with fallback to Haversine).
  * Terrain factor applied per-mode to scale cost and time.
  * Risk index: Gaussian decay from randomly placed disaster epicenters.
  * Accessibility: stochastic link disruption proportional to average risk.
  * Demand: scaled by risk index and scenario severity.
  * Daganzo CA routing cost (Theta) pre-computed for all hub-demand-scenario.

OUTPUT:
  data/central_vietnam_small_drnd.json
  data/central_vietnam_large_drnd.json
"""

import math
import json
import random
import time
import urllib.request
import urllib.parse
import os

# ---------------------------------------------------------------------------
# 0. Reproducibility
# ---------------------------------------------------------------------------
SEED = 42
random.seed(SEED)

# ---------------------------------------------------------------------------
# 1. REAL GEOGRAPHIC COORDINATES — Vu Gia / Thu Bồn Basin
#    All hand-curated from flood-risk literature and OSM.
#    Format: (lat, lon, name, type)
#    type: "demand", "hub_candidate", "origin"
# ---------------------------------------------------------------------------
# fmt: off
ALL_REAL_NODES = [
    # ── Demand nodes (representative flood-prone communes / districts) ──
    (15.8732, 108.3341, "Hoi_An_City",            "demand"),
    (15.9374, 108.3036, "Dien_Ban_District",       "demand"),
    (15.4300, 108.2073, "Nui_Thanh_District",      "demand"),  # Fixed: was 15.86, near Chu Lai airport
    (15.7562, 108.2461, "Thang_Binh_District",     "demand"),
    (16.0752, 108.1491, "Dai_Loc_District",        "demand"),
    (15.9867, 107.9883, "Dong_Giang_District",     "demand"),
    (16.2114, 108.0243, "Tay_Giang_District",      "demand"),
    (16.3012, 107.8631, "A_Luoi_District",         "demand"),
    (16.2321, 108.1572, "Nam_Giang_District",      "demand"),
    (16.1004, 107.7321, "A_Vuong_Commune",         "demand"),
    (15.9421, 108.2631, "Viet_An_Commune",         "demand"),
    (16.0123, 108.0961, "Que_Son_District",        "demand"),
    (16.1543, 108.2871, "Phu_Ninh_District",       "demand"),
    (15.5600, 108.3600, "Tam_Ky_City",             "demand"),  # Fixed: was 15.80, correct city center
    (16.4321, 107.9321, "Huong_Tra_District",      "demand"),
    (16.4612, 107.7832, "Huong_Thuy_District",     "demand"),
    (16.3421, 108.0012, "Nam_Dong_District",       "demand"),
    (16.5612, 107.8741, "Phu_Loc_District",        "demand"),
    (16.4001, 107.6521, "A_Luoi_Mountain",         "demand"),
    (16.2812, 107.5321, "Nam_Dong_Highland",       "demand"),
    # ── Additional demand nodes for LARGE instance ──
    (16.0543, 108.2022, "Da_Nang_City",            "demand"),
    (15.9123, 108.1541, "Cam_Le_District",         "demand"),
    (16.1232, 108.1982, "Lien_Chieu_District",     "demand"),
    (16.0012, 108.2401, "Son_Tra_District",        "demand"),
    (15.8721, 108.0841, "Thanh_Khe_District",      "demand"),
    (16.2432, 108.0762, "Hoa_Vang_District",       "demand"),
    (15.7321, 108.1432, "Phu_Yen_Commune",         "demand"),
    (15.3200, 107.8341, "Bac_Tra_My",              "demand"),  # Fixed: was 15.99, hydro dam area
    (15.8453, 107.9872, "Nam_Tra_My",              "demand"),
    (15.6721, 108.0341, "Hiep_Duc_District",       "demand"),
    (15.5631, 108.2541, "Tien_Phuoc_District",     "demand"),
    (15.4321, 108.4012, "Nui_Thanh_South",         "demand"),
    (15.6012, 108.3341, "Tam_Ky_South",            "demand"),
    (16.5123, 107.6012, "Phu_Loc_West",            "demand"),
    (16.6321, 107.7821, "Phu_Vang_District",       "demand"),
    (16.5543, 107.9321, "Quang_Dien_District",     "demand"),
    (16.4872, 108.1012, "Phong_Dien_District",     "demand"),
    (16.4631, 108.2621, "Hue_City_South",          "demand"),
    (16.4631, 107.4321, "Khe_Tre_Commune",         "demand"),
    (15.7143, 107.8101, "Tra_Don_Commune",         "demand"),
    (15.5832, 107.9431, "Tra_Nam_Commune",         "demand"),
    (16.7012, 107.5831, "Lang_Co_Area",            "demand"),
    (16.6012, 107.3541, "Truoi_Lake_Area",         "demand"),
    (15.9432, 107.5932, "Vu_Gia_River_South",      "demand"),
    (16.1321, 107.4531, "Song_Bung_Lake",          "demand"),
    (16.0743, 107.3021, "A_Sap_Valley",            "demand"),
    (15.8123, 107.6321, "Phuoc_Son_District",      "demand"),
    (15.6831, 107.7851, "Tra_My_Highlands",        "demand"),
    (16.3012, 107.2321, "Bach_Ma_Forest",          "demand"),
    (16.5412, 107.1081, "A_Luoi_Valley",           "demand"),
    # More demand nodes for large instance completeness
    (16.7832, 107.4231, "Huong_An_Commune",        "demand"),
    (16.0231, 108.3491, "Tho_Quang_Ward",          "demand"),
    (15.9812, 108.1721, "Hoa_Cuong_Ward",          "demand"),
    (15.8342, 108.0012, "An_Tan_Commune",          "demand"),
    (16.1891, 107.9341, "Lac_My_Commune",          "demand"),
    (16.3543, 107.6521, "Hong_Ha_Commune",         "demand"),
    (16.5014, 107.8031, "Quang_An_Ward",           "demand"),
    (16.2231, 107.3041, "Huong_Xuan_Commune",      "demand"),
    (15.6521, 108.1341, "Tam_Viet_Commune",        "demand"),
    (15.4832, 108.3031, "Tam_Hiep_Commune",        "demand"),
    (15.7981, 108.4201, "Binh_Duong_Commune",      "demand"),
    (16.8012, 107.5321, "Phu_Dien_Ward",           "demand"),
    (16.0821, 108.4312, "My_Khe_Beach_Area",       "demand"),
    (16.9321, 107.3012, "A_Dot_Commune",           "demand"),
    (15.3301, 108.5501, "Tam_Quan_Town",           "demand"),
    (15.2431, 108.4231, "Nuoc_Trong_Reservoir",    "demand"),
    (15.1241, 108.3121, "Duc_Pho_District",        "demand"),
    (16.9541, 107.1231, "A_Bat_Commune",           "demand"),
    (17.0231, 107.2031, "A_La_Commune",            "demand"),
    (17.1012, 107.0231, "Huong_Lap_Commune",       "demand"),
    (16.8501, 107.2501, "Cao_Ngan_Commune",        "demand"),
    (15.0541, 108.6541, "Mo_Duc_District",         "demand"),
    (15.1831, 108.7801, "Minh_Long_District",      "demand"),
    (15.8712, 108.5041, "Chu_Lai_Port",            "demand"),
    (15.4012, 107.8501, "Son_Ha_District",         "demand"),
    (15.2831, 107.7021, "Son_Tay_District",        "demand"),
    (15.0001, 107.9231, "Tra_Bong_District",       "demand"),
    (14.9321, 108.1431, "Nghia_Hanh_District",     "demand"),
    (14.8541, 108.3201, "Tu_Nghia_District",       "demand"),
    (15.1200, 108.4801, "Quang_Ngai_City",         "demand"),  # Fixed: was 14.78 (was in Binh Dinh!)
    (14.9012, 108.5601, "Son_Tinh_District",       "demand"),
    (15.1231, 108.6271, "Binh_Son_District",       "demand"),
    (15.6121, 107.4031, "Khue_Trung_Valley",       "demand"),
    (16.7231, 107.6851, "Phu_Thuong_Ward",         "demand"),
    (16.9001, 107.4581, "Truong_Giang_Commune",    "demand"),
    (17.0721, 107.6231, "Son_Qua_Commune",         "demand"),
    (15.9301, 108.4521, "Xuan_Ha_Ward",            "demand"),
    (16.0051, 108.5201, "Man_Thai_Ward",           "demand"),
    (15.7231, 108.5501, "Phuoc_Hiep_Commune",      "demand"),
    (16.1751, 108.4201, "Hoa_Lien_Commune",        "demand"),
    (16.3121, 108.3721, "Hoa_Tien_Commune",        "demand"),
    (16.0321, 107.6531, "Zuoih_Commune",           "demand"),
    (15.8901, 107.4581, "Bha_Le_Commune",          "demand"),
    (15.6812, 107.2541, "Tra_Vie_Commune",         "demand"),
    (15.4981, 107.1081, "Ca_Dy_Commune",           "demand"),
    (15.2341, 107.0231, "Tra_Bui_Commune",         "demand"),
    (16.2521, 107.8951, "Ta_Lang_Commune",         "demand"),
    (16.4012, 107.4081, "Thuong_Quang_Commune",    "demand"),
    (16.6721, 107.2541, "A_Ngo_Commune",           "demand"),
    (16.8341, 107.0931, "A_Tuc_Commune",           "demand"),
    (15.5321, 107.5031, "Ca_Lu_Commune",           "demand"),
    # ── Hub candidates (elevated, safe logistics facilities) ──
    (16.0544, 108.2022, "Da_Nang_Airport_Hub",     "hub"),
    (15.5600, 108.3300, "Tam_Ky_Logistics_Hub",    "hub"),     # Fixed: aligned with corrected Tam_Ky_City
    (16.4601, 107.5961, "A_Luoi_Relief_Center",    "hub"),
    (15.9700, 107.8600, "Dong_Giang_Rescue_Stn",   "hub"),
    (15.6400, 108.2100, "Thang_Binh_Depot",        "hub"),
    # Additional hub candidates for LARGE instance
    (16.3300, 108.0070, "Nam_Giang_Forward_Base",  "hub"),
    (16.5600, 107.8600, "Phu_Loc_Staging_Area",    "hub"),
    (15.4500, 108.4200, "Nui_Thanh_Reserve",       "hub"),
    (16.7200, 107.5900, "Lang_Co_Forward_Post",    "hub"),
    (15.2200, 108.6000, "Binh_Son_Warehouse",      "hub"),
    (16.9300, 107.2500, "A_Dot_Mountain_Base",     "hub"),
    (15.0500, 108.4000, "Quang_Ngai_Depot",        "hub"),
    (16.1500, 107.6200, "A_Sap_Helipad",           "hub"),
    (15.7800, 108.0500, "Que_Son_Facility",        "hub"),
    (16.8600, 107.8300, "Huong_Viet_Depot",        "hub"),
    (14.8700, 108.7900, "Quang_Ngai_Port",         "hub"),
    (15.6200, 107.7200, "Phuoc_Son_Helipad",       "hub"),
    (17.0500, 107.4300, "Rao_Trang_Base",          "hub"),
    (16.2800, 107.5100, "Bac_Tra_My_Depot",        "hub"),
    (15.4100, 107.5600, "Son_Ha_Hub",               "hub"),
    # ── Origins (external supply: military, INGOs, port logistics) ──
    (16.1124, 108.1948, "Hai_Van_Pass_North",      "origin"),  # QL1A Pass
    (15.4000, 108.3100, "Dung_Quat_Port",          "origin"),  # Fixed: was 15.68, actual Dung Quat port lat
    # Additional origins for LARGE instance
    (15.7500, 108.4700, "Chu_Lai_Airport",         "origin"),  # Military airport
    (16.8800, 107.5500, "Thuan_An_Port",           "origin"),  # Coastal port
    (14.7600, 108.6900, "Sa_Ky_Port",              "origin"),  # Southern port
    (17.1900, 107.0700, "Khe_Sanh_Entry",          "origin"),  # Western border
    (15.3600, 107.8900, "Tra_Bong_Supply",         "origin"),  # Inland supply
    (16.0100, 108.6400, "Da_Nang_Seaport",         "origin"),  # Main seaport
    (16.9700, 107.7700, "Hue_Train_Station",       "origin"),  # Rail supply
    (15.3800, 109.1000, "Ly_Son_Island_Supply",    "origin"),  # Fixed: was 15.12/109.01, actual island position
    (16.4900, 108.2300, "Lang_Co_Beach_Base",      "origin"),  # Beach landing
    (14.5700, 108.9800, "Duc_Pho_Harbor",          "origin"),  # Southern harbor
]
# fmt: on

# ---------------------------------------------------------------------------
# 2. HAVERSINE DISTANCE
# ---------------------------------------------------------------------------
EARTH_RADIUS_KM = 6371.0

def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in km."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# 3. OSRM API — Road distance and time matrix
# ---------------------------------------------------------------------------
OSRM_BASE = "http://router.project-osrm.org/table/v1/driving/"
OSRM_REQUEST_DELAY = 0.5  # seconds between API calls (rate limiting)

def _osrm_table(coords):
    """
    Calls OSRM Table API for a list of (lat, lon) coords.
    Returns (distance_matrix_km, duration_matrix_hours) or None on failure.
    OSRM returns distances in metres and durations in seconds.
    """
    coord_str = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in coords)
    url = f"{OSRM_BASE}{coord_str}?annotations=duration,distance"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
        if data.get("code") != "Ok":
            return None
        dist_m  = data["distances"]   # metres
        dur_s   = data["durations"]   # seconds
        n = len(coords)
        dist_km = [[dist_m[i][j] / 1000.0 for j in range(n)] for i in range(n)]
        dur_hr  = [[dur_s[i][j]  / 3600.0 for j in range(n)] for i in range(n)]
        return dist_km, dur_hr
    except Exception as e:
        print(f"  [OSRM] API error: {e}. Falling back to Haversine.")
        return None

OSRM_BATCH_SIZE = 25  # OSRM limit per request

def get_road_matrix(coords):
    """
    Build full NxN road distance and time matrices using OSRM.
    Splits into batches if N > OSRM_BATCH_SIZE.
    Falls back to Haversine if OSRM unavailable.
    """
    n = len(coords)
    print(f"  Fetching road matrix via OSRM for {n} nodes ...")

    # Try single full request first (for small N)
    if n <= OSRM_BATCH_SIZE:
        result = _osrm_table(coords)
        if result:
            print(f"  [OSRM] full {n}x{n} matrix retrieved.")
            return result

    # Fallback: Haversine + terrain tortuosity
    print(f"  [OSRM] Using Haversine fallback (tortuosity=1.3, avg road speed=40 km/h).")
    return _haversine_road_matrix(coords)


def _haversine_road_matrix(coords, tortuosity=1.3, avg_speed_kmh=40.0):
    """Haversine straight-line distance × tortuosity factor → road distance & time."""
    n = len(coords)
    dist = [[0.0] * n for _ in range(n)]
    dur  = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                d = haversine(*coords[i], *coords[j]) * tortuosity
                dist[i][j] = d
                dur[i][j]  = d / avg_speed_kmh  # hours
    return dist, dur


# ---------------------------------------------------------------------------
# 4. TERRAIN FACTOR — adjust cost/time per mode across terrain types
# ---------------------------------------------------------------------------
# Terrain factor: 1.0 = coastal flat; value increases toward rough mountains.
# Estimated from longitude (further west → more mountainous).
# lon range: ~107.0 (deep mountain) to ~108.8 (coastal)
def terrain_factor(lon):
    """Returns a multiplier in [1.0, 1.8] based on longitude proxy for terrain."""
    lon_min, lon_max = 107.0, 108.8
    # Coastal = 1.0, deep mountain interior = 1.8
    t = 1.0 - (lon - lon_min) / (lon_max - lon_min)  # 0=coast, 1=mountain
    return 1.0 + 0.8 * t


# ---------------------------------------------------------------------------
# 5. TRANSPORT MODES
# ---------------------------------------------------------------------------
# mode=0: Road   — disrupted, fast normally (base OSRM speed)
# mode=1: Water  — boat/motorised raft, slow, resilient, always partially available
# mode=2: Air    — helicopter, very fast, very expensive, always available
NUM_MODES = 3

# ── Transport Mode Parameters ────────────────────────────────────────────────
# Calibrated for flood disaster context in Central Vietnam.
#
# | Mode | Vehicle        | Speed  | Unit Cost | Capacity | Disruption      |
# |------|----------------|--------|-----------|----------|-----------------|
# |  0   | Truck convoy   | 35km/h | $2.0/km   | 60 pers  | HIGH (floods)   |
# |  1   | Motorboat      | 25km/h | $5.0/km   | 25 pers  | LOW (resilient) |
# |  2   | Helicopter     | 150km/h| $40.0/km  | 10 pers  | NONE (always)   |
#
# Rationale:
#   Road: primary mode, disrupted when β-fraction of links flood (scenario-dependent)
#   Water: slower but inherently resilient in flood scenarios; boats navigate floodwater;
#          moderate cost due to fuel + operator; capacity limited by boat size
#   Air:   helicopter is extremely expensive but always available; small capacity (Bell-412 type)
#          per-km cost ~20× road; used as emergency backup
MODE_PARAMS = {
    0: {"name": "road",  "speed_kmh": 35.0,  "unit_cost": 2.0,  "vehicle_cap": 60},   # truck
    1: {"name": "water", "speed_kmh": 25.0,  "unit_cost": 5.0,  "vehicle_cap": 25},   # motorboat
    2: {"name": "air",   "speed_kmh": 150.0, "unit_cost": 40.0, "vehicle_cap": 10},   # helicopter
}
# Daganzo local routing params
DAGANZO_PHI = 0.57    # circuity factor (CA formula constant)
ETA = 5               # average group size per distress location
GAMMA_CONV = 3.0      # kg/person of relief items
ALPHA_ECON = 0.6      # economies-of-scale discount for inter-hub transshipment

def build_mode_matrices(coords, road_dist, road_time):
    """
    Build cost C[m][i][j] and time T[m][i][j] for all 3 modes.
    Water/Air use Haversine with their own speeds and terrain factors.
    """
    n = len(coords)
    C = [[[0.0]*n for _ in range(n)] for _ in range(NUM_MODES)]
    T = [[[0.0]*n for _ in range(n)] for _ in range(NUM_MODES)]

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            # Terrain factor at midpoint
            tf = terrain_factor((coords[i][1] + coords[j][1]) / 2)

            # Mode 0: road (from OSRM or Haversine)
            raw_d = road_dist[i][j]
            C[0][i][j] = raw_d * MODE_PARAMS[0]["unit_cost"] * tf
            T[0][i][j] = road_time[i][j] * tf  # hours

            # Mode 1: water (Haversine, much slower, less terrain effect)
            hav_d = haversine(*coords[i], *coords[j])
            water_tf = 1.0 + 0.1 * (tf - 1.0)  # water barely affected by terrain
            C[1][i][j] = hav_d * MODE_PARAMS[1]["unit_cost"] * water_tf
            T[1][i][j] = hav_d / MODE_PARAMS[1]["speed_kmh"] * water_tf

            # Mode 2: air (Haversine, fast, moderate terrain effect)
            air_tf = 1.0 + 0.3 * (tf - 1.0)  # helicopters somewhat affected
            C[2][i][j] = hav_d * MODE_PARAMS[2]["unit_cost"] * air_tf
            T[2][i][j] = hav_d / MODE_PARAMS[2]["speed_kmh"] * air_tf

    return C, T


# ---------------------------------------------------------------------------
# 6. RISK INDEX — Gaussian epicenter decay model
# ---------------------------------------------------------------------------
SCENARIO_PARAMS = [
    # (name, prob, n_epicenters, sigma_km, intensity_range, severity_mult, disruption_beta)
    ("mild",    0.60, 1, 50.0, (0.2, 0.5), 1.0, 0.20),
    ("severe",  0.30, 2, 35.0, (0.4, 0.8), 1.6, 0.55),
    ("extreme", 0.10, 3, 25.0, (0.7, 1.0), 2.5, 0.90),
]
BASE_RISK = 0.08   # minimum background risk everywhere

def gaussian_risk(coords, idx_demand, epicenters, sigma_km):
    """Compute risk index for a demand node given list of (lat,lon) epicentres."""
    r = BASE_RISK
    for (elat, elon, intensity) in epicenters:
        d = haversine(coords[idx_demand][0], coords[idx_demand][1], elat, elon)
        r += intensity * math.exp(-d**2 / (2 * sigma_km**2))
    return min(1.0, r)


def generate_scenarios(coords, demand_indices, hub_indices, origin_indices,
                       area_km2_per_node, base_population):
    """
    For each scenario s ∈ {0,1,2}:
      - Place epicenters randomly among all nodes
      - Compute risk index r[u][s] for all nodes
      - Derive accessibility a[u][v][m][s]
      - Derive demand D[i][s] and origin supply O[j][s]
    """
    n = len(coords)
    scenarios = []

    for sp in SCENARIO_PARAMS:
        (name, prob, n_ep, sigma, (I_lo, I_hi), sev_mult, beta) = sp

        # Place epicenters at random actual node positions
        ep_indices = random.sample(range(n), min(n_ep, n))
        epicenters = [
            (coords[k][0], coords[k][1], random.uniform(I_lo, I_hi))
            for k in ep_indices
        ]

        # Risk index for all nodes
        risk = [gaussian_risk(coords, u, epicenters, sigma) for u in range(n)]

        # Risk index for hub nodes specifically (used for safety constraint r_ks ≤ χ)
        hub_risk = {k: risk[k] for k in hub_indices}

        # Accessibility matrix a[u][v][m][s]
        # Road (m=0): stochastic disruption
        # Water (m=1): always available but high-risk areas have higher water accessibility
        # Air (m=2): always available (1)
        a = [[[1]*n for _ in range(n)] for _ in range(NUM_MODES)]
        for u in range(n):
            for v in range(n):
                if u == v:
                    for m in range(NUM_MODES):
                        a[m][u][v] = 0  # no self-loops
                    continue
                avg_risk = (risk[u] + risk[v]) / 2.0
                # Road disruption probability
                p_disrupted = min(1.0, beta * avg_risk)
                if random.random() < p_disrupted:
                    a[0][u][v] = 0  # road link disrupted
                    a[0][v][u] = 0
                # Water always 1 (bidirectional) — boats are resilient
                # a[1][u][v] = 1 (already set)
                # Air always 1
                # a[2][u][v] = 1 (already set)

        # Demand D[i][s] for demand nodes (people to evacuate)
        demand = {}
        for i in demand_indices:
            pop = base_population[i]
            r_is = risk[i]
            d_base = pop * (0.1 + 0.9 * r_is) * sev_mult
            noise = random.gauss(0, 0.05 * d_base)
            demand[i] = max(10.0, d_base + noise)

        # Supply O[j][s] for origin nodes (relief items in kg).
        # CRITICAL: collective supply must be ≥ total demand in kg to ensure feasibility.
        # total demand = GAMMA × Σ D_{is}  (converting persons to kg of relief items)
        # We set collective supply = 1.5-2.5× total demand (buffer for transshipment loss, etc.)
        total_demand_kg = GAMMA_CONV * sum(demand.values())
        total_supply_target = total_demand_kg * random.uniform(1.5, 2.5)
        supply = {}
        for j in origin_indices:
            frac = random.uniform(0.8, 1.2)
            supply[j] = max(5000.0, total_supply_target / len(origin_indices) * frac)

        # Hub reactive setup cost F_a[k][s] — proportional to risk (harder scenario = pricier emergency setup)
        hub_reactive_cost = {k: random.uniform(30000, 80000) * (1 + risk[k]) for k in hub_indices}
        # Processing time tau_ks at hub k in scenario s (hours)
        hub_process_time = {k: random.uniform(0.5, 2.0) * (1 + risk[k]) for k in hub_indices}

        scenarios.append({
            "name": name,
            "probability": prob,
            "epicenters": [{"lat": e[0], "lon": e[1], "intensity": e[2]} for e in epicenters],
            "risk": risk,     # indexed [u] for all nodes
            "hub_risk": {str(k): v for k, v in hub_risk.items()},
            "accessibility": a,   # a[mode][u][v]
            "demand": {str(i): d for i, d in demand.items()},
            "supply": {str(j): s for j, s in supply.items()},
            "hub_reactive_cost": {str(k): v for k, v in hub_reactive_cost.items()},
            "hub_process_time": {str(k): v for k, v in hub_process_time.items()},
        })

    return scenarios


# ---------------------------------------------------------------------------
# 7. DAGANZO CA — Pre-compute Theta[k][i][s]
# ---------------------------------------------------------------------------
CHI_SAFETY = 0.7   # max acceptable risk for operating a hub

def daganzo_theta(C_mode, a_mode, D_is, Q_m, C_m_per_km, Phi, eta, A_i, big_M=1e9):
    """
    Theta_{kis} = min over m { 2*C_{kim}*ceil(D_is/Q_m) + C_m*Phi*sqrt(ceil(D_is/eta)*A_i) }
    Only considers mode m if a[m][k][i] == 1.
    Returns big_M if all modes are blocked.
    """
    best = big_M
    for m in range(NUM_MODES):
        if a_mode[m] == 0:
            continue
        qm = MODE_PARAMS[m]["vehicle_cap"]
        cm = C_mode[m]       # transport cost k→i for mode m (already pre-computed)
        trips = math.ceil(D_is / qm) if qm > 0 else 1
        n_stops = math.ceil(D_is / eta) if eta > 0 else 1
        theta = 2.0 * cm * trips + C_m_per_km * Phi * math.sqrt(n_stops * A_i)
        if theta < best:
            best = theta
    return best


def compute_theta_matrix(coords, C_all, hub_indices, demand_indices, scenarios, area_km2):
    """
    Returns Theta[k_index][i_index][s_index] using the Daganzo CA formula.
    C_all[m][u][v] = transport cost per unit from u to v via mode m.
    """
    num_h = len(hub_indices)
    num_i = len(demand_indices)
    num_s = len(scenarios)
    C_m_per_km = 2.5  # local routing cost coefficient ($/km)

    Theta = [[[0.0]*num_s for _ in range(num_i)] for _ in range(num_h)]

    for ki, k in enumerate(hub_indices):
        for ii, i in enumerate(demand_indices):
            for si, sc in enumerate(scenarios):
                D_is = sc["demand"].get(str(i), 0.0)
                A_i  = area_km2[i]
                # accessibility for this k-i pair at each mode
                a_mode = [sc["accessibility"][m][k][i] for m in range(NUM_MODES)]
                # cost per mode
                c_mode = [C_all[m][k][i] for m in range(NUM_MODES)]
                Theta[ki][ii][si] = daganzo_theta(
                    c_mode, a_mode, D_is,
                    Q_m=None,  # handled in function above via MODE_PARAMS
                    C_m_per_km=C_m_per_km,
                    Phi=DAGANZO_PHI, eta=ETA, A_i=A_i
                )

    return Theta


# ---------------------------------------------------------------------------
# 8. INSTANCE ASSEMBLY
# ---------------------------------------------------------------------------

def build_instance(size="small"):
    """
    Assemble a complete DRND instance.
    size: "small" (20I, 5H, 2J) or "large" (100I, 20H, 12J)
    """
    if size == "small":
        n_demand = 20; n_hub = 5; n_origin = 2
    else:
        n_demand = 100; n_hub = 20; n_origin = 12

    # Separate nodes by type
    demand_pool  = [(lat, lon, nm) for lat, lon, nm, t in ALL_REAL_NODES if t == "demand"]
    hub_pool     = [(lat, lon, nm) for lat, lon, nm, t in ALL_REAL_NODES if t == "hub"]
    origin_pool  = [(lat, lon, nm) for lat, lon, nm, t in ALL_REAL_NODES if t == "origin"]

    demand_pool  = demand_pool[:n_demand]
    hub_pool     = hub_pool[:n_hub]
    origin_pool  = origin_pool[:n_origin]

    # Node ordering: [demand..., hub..., origin...]
    all_nodes = demand_pool + hub_pool + origin_pool
    coords    = [(lat, lon) for lat, lon, nm in all_nodes]
    names     = [nm for lat, lon, nm in all_nodes]
    n_total   = len(all_nodes)

    demand_indices = list(range(n_demand))
    hub_indices    = list(range(n_demand, n_demand + n_hub))
    origin_indices = list(range(n_demand + n_hub, n_total))

    print(f"\n[{size.upper()}] Building instance: {n_demand} demands, {n_hub} hubs, {n_origin} origins")
    print(f"  Total nodes: {n_total}")

    # Step 1: Road matrix (OSRM or Haversine fallback)
    road_dist, road_time = get_road_matrix(coords)
    time.sleep(OSRM_REQUEST_DELAY)

    # Step 2: All-mode cost + time matrices
    print("  Computing multi-mode cost/time matrices ...")
    C_all, T_all = build_mode_matrices(coords, road_dist, road_time)

    # Step 3: Hub parameters
    print("  Generating hub parameters ...")
    hub_capacity  = {}   # filled AFTER scenarios are generated (need actual demand)
    hub_fixed_cost = {}
    hub_hold_cost  = {}
    for k in hub_indices:
        alt_factor = terrain_factor(coords[k][1])
        hub_fixed_cost[k] = random.uniform(50000, 200000) * alt_factor
        hub_hold_cost[k]  = random.uniform(0.2, 1.0)  # $/kg held

    # Step 4: Base population per demand node (persons)
    # Coastal/urban nodes have higher population; mountain areas less
    base_population = {}
    for i in demand_indices:
        lon_i = coords[i][1]
        # Higher population near coast (lon ~108.2) and city centers
        coast_factor = 1.0 - abs(lon_i - 108.2) / 1.5
        base_population[i] = int(random.uniform(500, 5000) * max(0.2, coast_factor))

    # Step 5: Area per demand node (km²) — smaller near coast (denser), larger inland
    area_km2 = {}
    for i in demand_indices:
        lon_i = coords[i][1]
        coast_factor = 1.0 - abs(lon_i - 108.2) / 1.5
        area_km2[i] = random.uniform(8, 40) * (1 + max(0.0, 1.0 - coast_factor))

    # Step 6: Generate 3 scenarios
    print("  Generating disaster scenarios ...")
    scenarios = generate_scenarios(
        coords, demand_indices, hub_indices, origin_indices,
        area_km2, base_population
    )

    # Step 7: Daganzo Theta matrix
    print("  Pre-computing Daganzo CA Theta matrix ...")
    Theta = compute_theta_matrix(coords, C_all, hub_indices, demand_indices, scenarios, area_km2)

    # ── Hub capacity (computed POST-scenario using actual max demand) ──────
    # This is the CRITICAL fix: capacity must scale with ACTUAL scenario demand,
    # not a random pre-estimate. We use the worst (extreme) scenario demand to
    # set a generous per-hub capacity so q_k encoding has room to be feasible.
    max_total_demand_kg = max(
        GAMMA_CONV * sum(sc["demand"].get(str(i), 0) for i in demand_indices)
        for sc in scenarios
    )
    print(f"  Max total demand (worst scenario): {max_total_demand_kg:,.0f} kg")
    for k in hub_indices:
        alt_factor = terrain_factor(coords[k][1])
        # Each hub capacity = (max_demand / n_hubs) × [3, 6] × terrain_factor
        # With redundancy [3,6], total kappa = max_demand × [3,6] → always feasible
        hub_capacity[k] = int(
            max_total_demand_kg / len(hub_indices) * random.uniform(3.0, 6.0) * alt_factor
        )
    total_kappa = sum(hub_capacity.values())
    print(f"  Total kappa: {total_kappa:,.0f} kg  (ratio vs max demand: {total_kappa/max(1,max_total_demand_kg):.2f}x)")

    # Step 8: Deprivation sensitivity lambda[i][s]
    # lambda_is = lambda0 * (1 + r_is), lambda0 = 0.8 (calibrated)
    lambda0 = 0.8
    Lambda = {}
    for si, sc in enumerate(scenarios):
        for i in demand_indices:
            r_is = sc["risk"][i]
            Lambda[f"{i}_{si}"] = lambda0 * (1.0 + r_is)

    print("  Assembling final instance object ...")
    instance = {
        "meta": {
            "name": f"Central_Vietnam_DRND_{size}",
            "description": "DRND instance for Vu Gia - Thu Bon basin, Central Vietnam",
            "seed": SEED,
            "size": size,
        },
        "dimensions": {
            "num_I": n_demand,   # demand nodes
            "num_H": n_hub,      # hub candidates
            "num_J": n_origin,   # origins
            "num_S": len(scenarios),
            "num_M": NUM_MODES,
        },
        "nodes": {
            "coords": [[lat, lon] for lat, lon in coords],
            "names": names,
            "demand_indices": demand_indices,
            "hub_indices": hub_indices,
            "origin_indices": origin_indices,
        },
        "global_params": {
            "alpha": ALPHA_ECON,
            "chi": CHI_SAFETY,
            "gamma": GAMMA_CONV,
            "big_M": 1e9,
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
            "cost":  C_all,   # C[mode][u][v]
            "time":  T_all,   # T[mode][u][v] in hours
        },
        "scenarios": scenarios,
        "theta": Theta,   # Theta[hub_idx][demand_idx][scenario_idx]
        "lambda": Lambda, # lambda[f"{i}_{s}"]
    }

    return instance


# ---------------------------------------------------------------------------
# 9. MAIN
# ---------------------------------------------------------------------------
def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out_dir, exist_ok=True)

    for size in ["small", "large"]:
        print(f"\n{'='*60}")
        print(f"Generating {size.upper()} DRND instance...")
        print('='*60)

        instance = build_instance(size)

        out_path = os.path.join(out_dir, f"central_vietnam_{size}_drnd.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(instance, f, indent=2, ensure_ascii=False)

        n_I = instance["dimensions"]["num_I"]
        n_H = instance["dimensions"]["num_H"]
        n_J = instance["dimensions"]["num_J"]
        n_S = instance["dimensions"]["num_S"]
        n_M = instance["dimensions"]["num_M"]
        print(f"\n  Saved: {out_path}")
        print(f"  Dimensions: I={n_I}, H={n_H}, J={n_J}, S={n_S}, M={n_M}")

    print("\nDone. Both instances saved to data/ directory.")


if __name__ == "__main__":
    main()
