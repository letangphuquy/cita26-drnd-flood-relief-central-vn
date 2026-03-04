"""
generate_drnd.py
================
Authoritative DRND (Disaster Relief Network Design) dataset generator
for MO-IHLNDP experiments — Central Vietnam case study.

Region  : Đà Nẵng · Quảng Nam · Thừa Thiên-Huế · Quảng Ngãi
Nodes   : 100 demand + 20 hub + 12 origin (pre-curated, geography-verified)
Output  : data_prep/cv_small_drnd.json   (I=20, H=5,  J=2)
          data_prep/cv_large_drnd.json   (I=100,H=20, J=12)

Methodology (following data-strategy.txt):
  1. Auxiliary risk r^a_u  — static, intrinsic per node; 4-criterion score:
       C1. Topographic    (elevation proxy via longitude)
       C2. Hydrological   (proximity to Vu Gia / Thu Bồn / Perfume rivers)
       C3. Coastal surge  (Gaussian decay from coastline)
       C4. Delta/lowland  (proximity to river delta accumulation zones)
  2. Risk interval [r_min, r_max] per node, width proportional to r^a_u:
       safe zone  (r^a_u=0.1): [0.07, 0.22] — narrow, low ceiling
       risky zone (r^a_u=0.8): [0.21, 0.83] — wide,   high ceiling
  3. Epicenters sampled from demand nodes, weighted by r^a_u
  4. Scenario risk r_{us} drawn from each node's interval via epicenter exposure
  5. Origins: pre-selected external logistics zones (ports, military, border)
  6. Scenario-specific circuity φ in Daganzo CA formula
       mild=0.57 · severe=0.70 · extreme=0.85

References:
  - Barzinpour & Esmaeili (2014) — decision support framework for hub location
  - Noyan et al. (2016) — robust reliable humanitarian relief network design
  - Daganzo (1984) — CA routing formula for last-mile cost
"""

import math
import json
import random
import os

# ============================================================================
# CONFIGURATION
# ============================================================================

SEED = 2026
random.seed(SEED)

EARTH_R    = 6371.0
NUM_MODES  = 3
GAMMA      = 3.0    # kg relief per person
ALPHA      = 0.6    # inter-hub economies-of-scale discount
CHI        = 0.7    # max hub risk threshold χ
LAMBDA0    = 0.8    # base deprivation sensitivity λ₀
DAGANZO_ETA   = 5       # avg group size per distress location
DAGANZO_C_LOC = 2.5     # local routing cost coefficient ($/km)
BIG_M         = 1e9

LON_MOUNTAIN = 107.0    # deep highland (western boundary)
LON_COAST    = 108.8    # coastal plain (eastern boundary)
RIVER_SIGMA  = 18.0     # km — Gaussian decay for hydrological risk
COASTAL_SIGMA = 40.0    # km — Gaussian decay for coastal surge risk

# Scenario: (name, prob, n_epicenters, I_lo, I_hi, sev_mult, beta_road, phi)
SCENARIO_DEFS = [
    ("mild",    0.60, 1, 0.30, 0.60, 1.0, 0.25, 0.57),
    ("severe",  0.30, 2, 0.55, 0.85, 1.8, 0.55, 0.70),
    ("extreme", 0.10, 3, 0.75, 1.00, 2.8, 0.88, 0.85),
]

MODE_PARAMS = {
    0: {"name": "road",  "speed": 35.0,  "cost_per_km": 2.0,  "cap": 60},
    1: {"name": "water", "speed": 25.0,  "cost_per_km": 5.0,  "cap": 25},
    2: {"name": "air",   "speed": 150.0, "cost_per_km": 40.0, "cap": 10},
}

RISK_WEIGHTS = {"topo": 0.25, "hydro": 0.35, "coastal": 0.20, "delta": 0.20}

# ── River system waypoints (lat, lon) ────────────────────────────────────────
# Used for hydrological risk criterion C2.
RIVERS = {
    "vu_gia":   [(15.87,108.29),(15.90,108.05),(15.95,107.82),
                 (16.00,107.62),(16.05,107.42),(16.07,107.30)],
    "thu_bon":  [(15.88,108.40),(15.83,108.22),(15.80,108.02),(15.82,107.87)],
    "perfume":  [(16.47,108.20),(16.45,108.02),(16.43,107.82),(16.40,107.57)],
    "truong_giang": [(15.70,108.38),(15.63,108.45),(15.58,108.52)],
    "tra_bong": [(15.35,108.20),(15.28,107.98),(15.20,107.82)],
}

# ── River delta / lowland accumulation centers (lat, lon, sigma_km) ─────────
DELTA_CENTERS = [
    (15.88, 108.38, 28.0),   # Thu Bồn / Hội An delta
    (16.47, 108.20, 22.0),   # Perfume River / Huế city delta
    (15.58, 108.50, 18.0),   # Tam Kỳ coastal accumulation
    (15.12, 108.48, 16.0),   # Quảng Ngãi coastal plain
    (14.90, 108.55, 14.0),   # Tu Nghia / Son Tinh lowland
]

# ============================================================================
# NODE POOLS  (pre-curated, geography-verified)
# Format: (lat, lon, name)
# Fixes applied vs. v2:
#   - Removed (16.8981, 106.6061, "Huong_Lap_Commune")  → lon 106.6 is in Laos
#   - Fixed   (15.1831, 108.7801, "Minh_Long_District")  → space typo in lon
# ============================================================================

DEMAND_NODES = [
    # ── Quảng Nam province ──────────────────────────────────────────────────
    (15.8732, 108.3341, "Hoi_An_City"),
    (15.9374, 108.3036, "Dien_Ban_District"),
    (15.4300, 108.2073, "Nui_Thanh_District"),
    (15.7562, 108.2461, "Thang_Binh_District"),
    (16.0752, 108.1491, "Dai_Loc_District"),
    (15.9867, 107.9883, "Dong_Giang_District"),
    (16.2114, 108.0243, "Tay_Giang_District"),
    (16.3012, 107.8631, "A_Luoi_District"),
    (15.90, 107.65, "Nam_Giang_District"),
    (16.1004, 107.7321, "A_Vuong_Commune"),
    (15.9421, 108.2631, "Viet_An_Commune"),
    (16.0123, 108.0961, "Que_Son_District"),
    (15.73, 108.12, "Phu_Ninh_District"),
    (15.5600, 108.3600, "Tam_Ky_City"),
    # ── Thừa Thiên-Huế province ────────────────────────────────────────────
    (16.47, 107.52, "Huong_Tra_District"),
    (16.39, 107.60, "Huong_Thuy_District"),
    (16.08, 107.75, "Nam_Dong_District"),
    (16.20, 107.86, "Phu_Loc_District"),
    (16.4001, 107.6521, "A_Luoi_Mountain"),
    (16.2812, 107.5321, "Nam_Dong_Highland"),
    # ── Đà Nẵng city ───────────────────────────────────────────────────────
    (16.0543, 108.2022, "Da_Nang_City"),
    (15.9123, 108.1541, "Cam_Le_District"),
    (16.1232, 108.1982, "Lien_Chieu_District"),
    (16.0012, 108.2401, "Son_Tra_District"),
    (15.8721, 108.0841, "Thanh_Khe_District"),
    (16.2432, 108.0762, "Hoa_Vang_District"),
    # ── Quảng Nam inland / highland ────────────────────────────────────────
    (15.7321, 108.1432, "Phu_Yen_Commune"),
    (15.3200, 107.8341, "Bac_Tra_My"),
    (15.8453, 107.9872, "Nam_Tra_My"),
    (15.6721, 108.0341, "Hiep_Duc_District"),
    (15.5631, 108.2541, "Tien_Phuoc_District"),
    (15.4321, 108.4012, "Nui_Thanh_South"),
    (15.6012, 108.3341, "Tam_Ky_South"),
    # ── Thừa Thiên-Huế coastal / highland ──────────────────────────────────
    (16.5123, 107.6012, "Phu_Loc_West"),
    (16.52, 107.62, "Phu_Vang_District"),
    (16.58, 107.43, "Quang_Dien_District"),
    (16.52, 107.40, "Phong_Dien_District"),
    (16.42, 107.56, "Hue_City_South"),
    (16.4631, 107.4321, "Khe_Tre_Commune"),
    # ── Quảng Nam deep highland ─────────────────────────────────────────────
    (15.7143, 107.8101, "Tra_Don_Commune"),
    (15.5832, 107.9431, "Tra_Nam_Commune"),
    (16.24, 107.94, "Lang_Co_Area"),
    (16.6012, 107.3541, "Truoi_Lake_Area"),
    (15.9432, 107.5932, "Vu_Gia_River_South"),
    (16.1321, 107.4531, "Song_Bung_Lake"),
    (16.2500, 107.2700, "A_Sap_Valley"),           # A Shau/A Sap valley, Thua Thien-Hue
    (15.8123, 107.6321, "Phuoc_Son_District"),
    (15.6831, 107.7851, "Tra_My_Highlands"),
    (16.1900, 107.8600, "Bach_Ma_Forest"),          # Bach Ma NP near east coast, not deep mountains
    (16.3500, 107.3000, "A_Luoi_Valley"),           # A Luoi district western highlands
    # ── Thừa Thiên-Huế north ───────────────────────────────────────────────
    (16.78, 107.22, "Huong_An_Commune"),
    # ── Đà Nẵng wards ──────────────────────────────────────────────────────
    (16.0500, 108.23, "Tho_Quang_Ward"),              # Son Tra peninsula, Da Nang bay side
    (15.9812, 108.1721, "Hoa_Cuong_Ward"),
    (15.8342, 108.0012, "An_Tan_Commune"),
    (16.1891, 107.9341, "Lac_My_Commune"),
    (16.3543, 107.6521, "Hong_Ha_Commune"),
    (16.50, 107.62, "Quang_An_Ward"),
    (16.2231, 107.3041, "Huong_Xuan_Commune"),
    (15.6521, 108.1341, "Tam_Viet_Commune"),
    (15.4832, 108.3031, "Tam_Hiep_Commune"),
    (15.7981, 108.4201, "Binh_Duong_Commune"),
    (16.80, 107.26, "Phu_Dien_Ward"),
    (16.0601, 108.20, "My_Khe_Beach_Area"),
    # ── Far north ───────────────────────────────────────────────────────────
    (16.9321, 107.3012, "A_Dot_Commune"),
    # ── Quảng Ngãi province ─────────────────────────────────────────────────
    (15.4501, 108.5801, "Tam_Quan_Town"),
    (15.2431, 108.4231, "Nuoc_Trong_Reservoir"),
    (15.1241, 108.3121, "Duc_Pho_District"),
    (16.9541, 107.1231, "A_Bat_Commune"),
    (17.0231, 107.2031, "A_La_Commune"),
    (16.8501, 107.2501, "Cao_Ngan_Commune"),
    (15.0541, 108.6541, "Mo_Duc_District"),
    (15.1831, 108.7801, "Minh_Long_District"),   # fixed: was "10 8.7801"
    (15.42, 108.69, "Chu_Lai_Port_Area"),
    (15.4012, 107.8501, "Son_Ha_District"),
    (15.2831, 107.7021, "Son_Tay_District"),
    (15.0001, 107.9231, "Tra_Bong_District"),
    (14.9321, 108.1431, "Nghia_Hanh_District"),
    (14.8541, 108.3201, "Tu_Nghia_District"),
    (15.1200, 108.4801, "Quang_Ngai_City"),
    (14.9012, 108.5601, "Son_Tinh_District"),
    (15.1231, 108.6271, "Binh_Son_District"),
    # ── Remote highland communes ────────────────────────────────────────────
    (15.7200, 107.5500, "Khue_Trung_Valley"),        # western Quang Nam, inside Vietnam
    (16.72, 107.28, "Phu_Thuong_Ward"),
    (15.5501, 108.5401, "Truong_Giang_Commune"),
    (17.07, 107.16, "Son_Qua_Commune"),
    (15.93, 108.28, "Xuan_Ha_Ward"),
    (16.085, 108.20, "Man_Thai_Ward"),
    (15.5601, 107.9151, "Phuoc_Hiep_Commune"),
    (16.1400, 108.0500, "Hoa_Lien_Commune"),         # Hoa Vang district inland, not in sea
    (16.31, 107.82, "Hoa_Tien_Commune"),              # inland of Tam Giang lagoon
    (16.0321, 107.6531, "Zuoih_Commune"),
    (15.8901, 107.4581, "Bha_Le_Commune"),
    (15.8500, 107.6200, "Tra_Vie_Commune"),          # western Quang Nam, inside Vietnam
    (15.7500, 107.7600, "Ca_Dy_Commune"),            # Nam Giang/Tien Phuoc highland area
    (15.5400, 107.8400, "Tra_Bui_Commune"),          # Bac Tra My highland, was way in Laos
    (16.2521, 107.8951, "Ta_Lang_Commune"),
    (16.4012, 107.4081, "Thuong_Quang_Commune"),
    (16.6721, 107.2541, "A_Ngo_Commune"),
    (16.8341, 107.0931, "A_Tuc_Commune"),
    (15.6000, 107.7000, "Ca_Lu_Commune"),            # western Quang Nam, inside Vietnam
]  # 100 nodes

HUB_NODES = [
    # Elevated, safe logistics facilities with road/air access
    (16.0544, 108.2022, "Da_Nang_Airport_Hub"),
    (15.5600, 108.3300, "Tam_Ky_Logistics_Hub"),
    (16.4601, 107.5961, "A_Luoi_Relief_Center"),
    (15.9700, 107.8600, "Dong_Giang_Rescue_Stn"),
    (15.6400, 108.2100, "Thang_Binh_Depot"),
    (15.85, 107.70, "Nam_Giang_Forward_Base"),
    (16.18, 107.80, "Phu_Loc_Staging_Area"),
    (15.4500, 108.4200, "Nui_Thanh_Reserve"),
    (16.25, 107.90, "Lang_Co_Forward_Post"),
    (15.2200, 108.6000, "Binh_Son_Warehouse"),
    (16.9300, 107.2500, "A_Dot_Mountain_Base"),
    (15.0500, 108.4000, "Quang_Ngai_Depot"),
    (16.1500, 107.6200, "A_Sap_Helipad"),
    (15.7800, 108.0500, "Que_Son_Facility"),
    (16.86, 107.24, "Huong_Viet_Depot"),
    (14.8700, 108.7900, "Quang_Ngai_Port_Hub"),
    (15.6200, 107.7200, "Phuoc_Son_Helipad"),
    (17.05, 107.18, "Rao_Trang_Base"),
    (16.2800, 107.5100, "Bac_Tra_My_Depot"),
    (15.4800, 107.7200, "Son_Ha_Hub"),               # Son Ha district center, Quang Ngai
]  # 20 nodes

ORIGIN_NODES = [
    # External supply: ports, military airports, border logistics
    (16.1124, 108.1948, "Hai_Van_Pass_North"),    # QL1A northern entry
    (15.4000, 108.3100, "Dung_Quat_Port"),         # industrial port
    (15.7500, 108.4700, "Chu_Lai_Airport"),         # military/civil airport
    (16.53, 107.70, "Thuan_An_Port"),               # Thuan An inlet, Hue coastal port
    (14.7600, 108.6900, "Sa_Ky_Port"),              # southern port
    (17.1900, 107.0700, "Khe_Sanh_Entry"),          # western highland border entry
    (15.3600, 107.8900, "Tra_Bong_Supply"),         # inland supply depot
    (16.0930, 108.2280, "Da_Nang_Seaport"),          # Tien Sa port, Da Nang (was 108.64 = in sea)
    (16.46, 107.60, "Hue_Train_Station"),           # Hue city railway station
    (15.3800, 109.1000, "Ly_Son_Island_Supply"),    # coastal island depot
    (16.21, 107.96, "Lang_Co_Beach_Base"),          # Lang Co lagoon beach landing
    (14.5700, 108.9800, "Duc_Pho_Harbor"),          # southern harbor
]  # 12 nodes

assert len(DEMAND_NODES) == 100, f"Expected 100 demand nodes, got {len(DEMAND_NODES)}"
assert len(HUB_NODES)    == 20,  f"Expected 20 hub nodes, got {len(HUB_NODES)}"
assert len(ORIGIN_NODES) == 12,  f"Expected 12 origin nodes, got {len(ORIGIN_NODES)}"


# ============================================================================
# GEOGRAPHIC HELPERS
# ============================================================================

def haversine(lat1, lon1, lat2, lon2):
    phi1 = math.radians(lat1); phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return EARTH_R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def gauss(d_km, sigma_km):
    return math.exp(-d_km * d_km / (2.0 * sigma_km * sigma_km))


def terrain_factor(lon):
    """Terrain multiplier [1.0 coastal-flat … 1.8 deep-mountain]."""
    t = max(0.0, min(1.0, (LON_COAST - lon) / (LON_COAST - LON_MOUNTAIN)))
    return 1.0 + 0.8 * t


# ============================================================================
# MULTI-CRITERIA AUXILIARY RISK  r^a_u
# ============================================================================

def _score_topographic(lat, lon):
    """C1: Flood inundation risk from low-elevation coastal proximity."""
    frac = max(0.0, min(1.0, (lon - LON_MOUNTAIN) / (LON_COAST - LON_MOUNTAIN)))
    return frac ** 0.65   # convex: coastal disproportionately higher

def _score_hydrological(lat, lon):
    """C2: Proximity to major river systems (Vu Gia, Thu Bồn, Perfume, ...)."""
    best = 0.0
    for waypoints in RIVERS.values():
        for wlat, wlon in waypoints:
            d = haversine(lat, lon, wlat, wlon)
            s = gauss(d, RIVER_SIGMA)
            if s > best:
                best = s
    return min(1.0, best)

def _score_coastal(lat, lon):
    """C3: Coastal storm-surge and inundation exposure."""
    # Approximate distance to coastline via longitude difference
    d_approx_km = max(0.0, LON_COAST - lon) * 111.0 * math.cos(math.radians(lat))
    return gauss(d_approx_km, COASTAL_SIGMA)

def _score_delta(lat, lon):
    """C4: River delta / low-lying accumulation zone exposure."""
    best = 0.0
    for dlat, dlon, sigma in DELTA_CENTERS:
        d = haversine(lat, lon, dlat, dlon)
        s = gauss(d, sigma)
        if s > best:
            best = s
    return min(1.0, best)


def compute_aux_risk(lat, lon):
    """
    Auxiliary (static, intrinsic) flood risk r^a_u ∈ [0,1].
    Weighted multi-criteria score following Barzinpour & Esmaeili (2014).
    """
    s = (RISK_WEIGHTS["topo"]    * _score_topographic(lat, lon)
       + RISK_WEIGHTS["hydro"]   * _score_hydrological(lat, lon)
       + RISK_WEIGHTS["coastal"] * _score_coastal(lat, lon)
       + RISK_WEIGHTS["delta"]   * _score_delta(lat, lon))
    return round(max(0.0, min(1.0, s)), 4)


def risk_interval(r_aux):
    """
    Risk interval [r_min, r_max] for scenario risk sampling.
    Width and ceiling both scale with r^a_u:
      - Safe (r^a_u=0.10): [0.07, 0.22] — narrow, low ceiling
      - Risky (r^a_u=0.80): [0.21, 0.83] — wide,   high ceiling
    """
    r_min = 0.05 + 0.20 * r_aux
    r_max = r_aux + 0.15 * (1.0 - r_aux)
    return round(r_min, 4), round(r_max, 4)


# ============================================================================
# TRANSPORT MATRICES
# ============================================================================

def build_transport(coords):
    """
    C[m][u][v] ($/trip) and T[m][u][v] (hours) for all 3 modes.
    Road: Haversine × tortuosity × terrain factor.
    Water: follows waterways, minimal terrain effect.
    Air: straight-line, mild weather/terrain headwind factor.
    """
    n = len(coords)
    ROAD_TORTUOSITY = 1.35   # Central Vietnam mountain roads ~35% longer

    C = [[[0.0]*n for _ in range(n)] for _ in range(NUM_MODES)]
    T = [[[0.0]*n for _ in range(n)] for _ in range(NUM_MODES)]

    for u in range(n):
        for v in range(n):
            if u == v:
                continue
            la1, lo1 = coords[u]
            la2, lo2 = coords[v]
            d_hav = haversine(la1, lo1, la2, lo2)
            tf    = terrain_factor((lo1 + lo2) / 2.0)

            # Mode 0 — road (truck): tortuosity + terrain
            d_road = d_hav * ROAD_TORTUOSITY * tf
            C[0][u][v] = d_road * MODE_PARAMS[0]["cost_per_km"]
            T[0][u][v] = d_road / MODE_PARAMS[0]["speed"]

            # Mode 1 — water (motorboat): slight meandering, little terrain effect
            water_tf = 1.0 + 0.12 * (tf - 1.0)
            d_water  = d_hav * 1.15
            C[1][u][v] = d_water * MODE_PARAMS[1]["cost_per_km"] * water_tf
            T[1][u][v] = d_water / MODE_PARAMS[1]["speed"] * water_tf

            # Mode 2 — air (helicopter): straight-line, mild wind/weather factor
            air_tf = 1.0 + 0.25 * (tf - 1.0)
            C[2][u][v] = d_hav * MODE_PARAMS[2]["cost_per_km"] * air_tf
            T[2][u][v] = d_hav / MODE_PARAMS[2]["speed"] * air_tf

    return C, T


# ============================================================================
# SCENARIO GENERATION
# ============================================================================

def _weighted_sample(population, weights, k):
    """Sample k distinct indices from population without replacement, weighted."""
    chosen = []
    pop = list(range(len(population)))
    wts = list(weights)
    for _ in range(min(k, len(pop))):
        total = sum(wts[i] for i in pop)
        if total <= 0:
            break
        r = random.random() * total
        cum = 0.0
        sel = pop[-1]
        for idx in pop:
            cum += wts[idx]
            if r <= cum:
                sel = idx
                break
        chosen.append(sel)
        pop.remove(sel)
    return chosen


def generate_scenarios(coords, aux_risk, r_intervals,
                       demand_idx, hub_idx, origin_idx, base_pop):
    """
    Generate 3 disaster scenarios.

    Epicenter strategy (per data-strategy.txt):
      - Epicenters sampled from demand nodes weighted by r^a_u
      - Surrounding nodes receive exposure via Gaussian decay
      - Scenario risk r_{us} ← r_min_u + (r_max_u - r_min_u) × exposure_u

    Accessibility:
      - Road (m=0): stochastically disrupted ∝ beta × avg_risk
      - Water (m=1) and Air (m=2): always available

    Returns list of scenario dicts compatible with model.hpp.
    """
    n = len(coords)
    EPI_SIGMA = 85.0   # km — epicenter influence radius

    # Probability weights for epicenter sampling
    epi_weights = [aux_risk[i] for i in demand_idx]

    scenarios = []
    for name, prob, n_epi, I_lo, I_hi, sev_mult, beta, phi in SCENARIO_DEFS:

        # -- Epicenters: sampled demand nodes weighted by r^a_u
        chosen_local = _weighted_sample(demand_idx, epi_weights, n_epi)
        epicenters = [
            (coords[demand_idx[ci]][0],
             coords[demand_idx[ci]][1],
             random.uniform(I_lo, I_hi))
            for ci in chosen_local
        ]

        # -- Raw exposure ∈ [0,1] via Gaussian decay from epicenters
        raw_exp = []
        for u in range(n):
            ex = 0.0
            for elat, elon, inten in epicenters:
                d = haversine(coords[u][0], coords[u][1], elat, elon)
                ex += inten * gauss(d, EPI_SIGMA)
            raw_exp.append(min(1.0, ex))

        # -- Scenario risk r_{us}: sample from node's risk interval
        risk = []
        for u in range(n):
            r_min, r_max = r_intervals[u]
            r_us = r_min + (r_max - r_min) * raw_exp[u]
            r_us += random.gauss(0, 0.025)   # small stochastic perturbation
            risk.append(round(max(0.01, min(0.99, r_us)), 4))

        # -- Accessibility a[m][u][v]
        # Initialise fresh 3D list (NOT by list multiplication — avoids aliasing bug)
        a = [[[1]*n for _ in range(n)] for _ in range(NUM_MODES)]
        for u in range(n):
            for v in range(n):
                if u == v:
                    for m in range(NUM_MODES):
                        a[m][u][v] = 0
                    continue
                avg_risk_uv = (risk[u] + risk[v]) / 2.0
                # Road disruption: higher beta and risk → more links broken
                p_road = min(0.97, beta * avg_risk_uv)
                if random.random() < p_road:
                    a[0][u][v] = 0
                    a[0][v][u] = 0
                # Water (m=1) and Air (m=2) remain 1

        # -- Demand D_{is}: risk-driven fraction of base population
        demand = {}
        total_demand_pers = 0.0
        for i in demand_idx:
            r_is   = risk[i]
            frac   = 0.05 + 0.85 * r_is        # 5% baseline + risk-driven
            d_base = base_pop[i] * frac * sev_mult
            noise  = random.gauss(0, 0.08 * d_base)
            d_val  = max(5.0, d_base + noise)
            demand[str(i)] = round(d_val, 2)
            total_demand_pers += d_val

        # -- Supply O_{js}: generous, origins are in safe zones
        total_kg = GAMMA * total_demand_pers
        total_supply_kg = total_kg * random.uniform(1.8, 2.5)
        supply = {}
        for j in origin_idx:
            frac_j = random.uniform(0.7, 1.3)
            supply[str(j)] = round(
                max(5000.0, total_supply_kg / len(origin_idx) * frac_j), 2)

        # -- Hub scenario parameters
        hub_reactive_cost = {}
        hub_process_time  = {}
        for k in hub_idx:
            r_ks = risk[k]
            hub_reactive_cost[str(k)] = round(
                random.uniform(30000, 80000) * (1.0 + r_ks), 2)
            hub_process_time[str(k)] = round(
                random.uniform(0.4, 1.5) * (1.0 + 0.5 * r_ks), 4)

        scenarios.append({
            "name":        name,
            "probability": prob,
            "phi_circuity": phi,     # scenario-specific Daganzo φ
            "epicenters": [
                {"lat": round(e[0], 4), "lon": round(e[1], 4),
                 "intensity": round(e[2], 4)}
                for e in epicenters
            ],
            "risk":      risk,       # LIST indexed by absolute node u — required by model.hpp
            "hub_risk":  {str(k): risk[k] for k in hub_idx},
            "accessibility": a,
            "demand":    demand,
            "supply":    supply,
            "hub_reactive_cost": hub_reactive_cost,
            "hub_process_time":  hub_process_time,
        })

    return scenarios


# ============================================================================
# DAGANZO CA THETA MATRIX  Θ_{k,i,s}
# ============================================================================

def compute_theta(C_all, hub_idx, demand_idx, scenarios, area_km2):
    """
    Pre-compute Theta[ki][ii][si] = min-cost last-mile routing from hub k
    to demand zone i in scenario s, using scenario-specific circuity φ.

    Daganzo CA formula:
      Θ = 2·C_{kim}·⌈D/Q_m⌉ + c_local·φ·√(⌈D/η⌉·A_i)
    """
    num_h = len(hub_idx)
    num_i = len(demand_idx)
    num_s = len(scenarios)
    Theta = [[[0.0]*num_s for _ in range(num_i)] for _ in range(num_h)]

    for ki, k in enumerate(hub_idx):
        for ii, i in enumerate(demand_idx):
            for si, sc in enumerate(scenarios):
                D_is = float(sc["demand"].get(str(i), 0.0))
                A_i  = float(area_km2[str(i)])
                phi  = sc["phi_circuity"]
                best = BIG_M
                for m in range(NUM_MODES):
                    if sc["accessibility"][m][k][i] == 0:
                        continue
                    cap_m  = MODE_PARAMS[m]["cap"]
                    c_km   = C_all[m][k][i]
                    trips  = math.ceil(D_is / cap_m) if cap_m > 0 else 1
                    stops  = math.ceil(D_is / DAGANZO_ETA) if DAGANZO_ETA > 0 else 1
                    theta  = (2.0 * c_km * trips
                              + DAGANZO_C_LOC * phi * math.sqrt(stops * A_i))
                    if theta < best:
                        best = theta
                Theta[ki][ii][si] = round(best, 4)

    return Theta


# ============================================================================
# INSTANCE BUILDER
# ============================================================================

def build_instance(size="small"):
    if size == "small":
        n_I, n_H, n_J = 20, 5, 2
    else:
        n_I, n_H, n_J = 100, 20, 12

    print(f"\n{'='*60}")
    print(f"[{size.upper()}]  I={n_I}  H={n_H}  J={n_J}")
    print("="*60)

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

    # ── Step 1: Auxiliary risk ────────────────────────────────────────────────
    print("  [1] Computing auxiliary risk r^a_u ...")
    aux_risk    = [compute_aux_risk(lat, lon) for lat, lon in coords]
    r_intervals = [risk_interval(r) for r in aux_risk]

    # Print summary stats
    d_risks  = [aux_risk[i] for i in demand_idx]
    h_risks  = [aux_risk[k] for k in hub_idx]
    j_risks  = [aux_risk[j] for j in origin_idx]
    print(f"      demand  r^a_u: min={min(d_risks):.3f}  mean={sum(d_risks)/len(d_risks):.3f}  max={max(d_risks):.3f}")
    print(f"      hub     r^a_u: min={min(h_risks):.3f}  mean={sum(h_risks)/len(h_risks):.3f}  max={max(h_risks):.3f}")
    print(f"      origin  r^a_u: min={min(j_risks):.3f}  mean={sum(j_risks)/len(j_risks):.3f}  max={max(j_risks):.3f}")

    # ── Step 2: Base population per demand node ───────────────────────────────
    print("  [2] Assigning base populations ...")
    base_pop = {}
    for i in demand_idx:
        lat, lon = coords[i]
        coast_f = max(0.15, 1.0 - abs(lon - 108.2) / 1.6)
        pop_base = int(500 + 6500 * coast_f)
        noise    = int(random.gauss(0, 0.12 * pop_base))
        base_pop[i] = max(100, pop_base + noise)

    # ── Step 3: Area per demand node (km²) ───────────────────────────────────
    area_km2 = {}
    for i in demand_idx:
        _, lon = coords[i]
        tf = terrain_factor(lon)
        area_km2[str(i)] = round(random.uniform(8.0, 18.0) * tf, 2)

    # ── Step 4: Transport matrices ────────────────────────────────────────────
    print("  [3] Building transport matrices ...")
    C_all, T_all = build_transport(coords)

    # ── Step 5: Scenarios ─────────────────────────────────────────────────────
    print("  [4] Generating 3 scenarios ...")
    scenarios = generate_scenarios(
        coords, aux_risk, r_intervals,
        demand_idx, hub_idx, origin_idx, base_pop
    )
    for sc in scenarios:
        d_risks_s = [sc["risk"][i] for i in demand_idx]
        total_d   = sum(float(v) for v in sc["demand"].values())
        total_s   = sum(float(v) for v in sc["supply"].values())
        print(f"      [{sc['name']:8s}]  "
              f"risk_mean={sum(d_risks_s)/len(d_risks_s):.3f}  "
              f"demand={GAMMA*total_d:,.0f} kg  "
              f"supply={total_s:,.0f} kg  "
              f"phi={sc['phi_circuity']}")

    # ── Step 6: Hub capacity (calibrated to worst-case demand) ───────────────
    print("  [5] Calibrating hub capacities ...")
    max_demand_kg = max(
        GAMMA * sum(float(v) for v in sc["demand"].values())
        for sc in scenarios
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

    total_kappa = sum(hub_capacity.values())
    print(f"      max_demand={max_demand_kg:,.0f} kg  "
          f"total_kappa={total_kappa:,.0f} kg  "
          f"ratio={total_kappa/max_demand_kg:.1f}x")

    # ── Step 7: Daganzo Theta ─────────────────────────────────────────────────
    print("  [6] Pre-computing Daganzo Theta matrix ...")
    Theta = compute_theta(C_all, hub_idx, demand_idx, scenarios, area_km2)

    # ── Step 8: Lambda (deprivation sensitivity) ──────────────────────────────
    Lambda = {}
    for si, sc in enumerate(scenarios):
        for i in demand_idx:
            r_is = sc["risk"][i]
            Lambda[f"{i}_{si}"] = round(LAMBDA0 * (1.0 + r_is), 4)

    # ── Assemble ──────────────────────────────────────────────────────────────
    instance = {
        "meta": {
            "name":        f"CentralVietnam_{size.upper()}",
            "description": ("MO-IHLNDP flood relief — Vu Gia/Thu Bồn/Huế basin. "
                            "Multi-criteria auxiliary risk + probabilistic scenarios."),
            "seed":         SEED,
            "size":         size,
            "methodology":  "multi-criteria auxiliary risk + risk-interval scenario model",
            "risk_weights": RISK_WEIGHTS,
        },
        "dimensions": {
            "num_I": n_I, "num_H": n_H, "num_J": n_J,
            "num_S": len(scenarios), "num_M": NUM_MODES,
        },
        "nodes": {
            "coords":          [[lat, lon] for lat, lon in coords],
            "names":           names,
            "demand_indices":  demand_idx,
            "hub_indices":     hub_idx,
            "origin_indices":  origin_idx,
            "aux_risk":        aux_risk,           # r^a_u stored as per data-strategy
            "risk_intervals":  [[r[0], r[1]] for r in r_intervals],
        },
        "global_params": {
            "alpha":       ALPHA,
            "chi":         CHI,
            "gamma":       GAMMA,
            "big_M":       BIG_M,
            "daganzo_phi": 0.57,      # reference; per-scenario φ in scenarios[s].phi_circuity
            "daganzo_eta": DAGANZO_ETA,
        },
        "hub_params": {
            "capacity":   hub_capacity,
            "fixed_cost": hub_fixed_cost,
            "hold_cost":  hub_hold_cost,
        },
        "base_population": {str(i): base_pop[i] for i in demand_idx},
        "area_km2":        area_km2,
        "transport": {
            "cost": C_all,
            "time": T_all,
        },
        "scenarios": scenarios,
        "theta":  Theta,
        "lambda": Lambda,
    }
    return instance


# ============================================================================
# MAIN
# ============================================================================

def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    for size in ["small", "large"]:
        inst = build_instance(size)
        fname = f"cv_{size}_drnd.json"
        path  = os.path.join(out_dir, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(inst, f, indent=2, ensure_ascii=False)
        d = inst["dimensions"]
        print(f"\n  Saved: {path}")
        print(f"  I={d['num_I']}  H={d['num_H']}  J={d['num_J']}  "
              f"S={d['num_S']}  M={d['num_M']}")

    print("\nAll done.")


if __name__ == "__main__":
    main()
