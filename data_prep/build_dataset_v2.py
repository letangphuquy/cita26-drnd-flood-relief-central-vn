import math
import json
import random
import os

# 1. DEFINE CONSTANTS
SEED = 2026
random.seed(SEED)
EARTH_RADIUS_KM = 6371.0
NUM_MODES = 3 

# 2. DEFINING REAL NODES IN CENTRAL VIETNAM
# We take the pre-existing coordinate list containing ~100 locations.
# These will conceptually act as our spatial discretization "cells".
# Note: Since the scope focuses on Hue, Da Nang, and Quang Nam.
ALL_REAL_NODES = [
    (15.8732, 108.3341, "Hoi_An_City"),
    (15.9374, 108.3036, "Dien_Ban_District"),
    (15.4300, 108.2073, "Nui_Thanh_District"),
    (15.7562, 108.2461, "Thang_Binh_District"),
    (16.0752, 108.1491, "Dai_Loc_District"),
    (15.9867, 107.9883, "Dong_Giang_District"),
    (16.2114, 108.0243, "Tay_Giang_District"),
    (16.3012, 107.8631, "A_Luoi_District"),
    (16.2321, 108.1572, "Nam_Giang_District"),
    (16.1004, 107.7321, "A_Vuong_Commune"),
    (15.9421, 108.2631, "Viet_An_Commune"),
    (16.0123, 108.0961, "Que_Son_District"),
    (16.1543, 108.2871, "Phu_Ninh_District"),
    (15.5600, 108.3600, "Tam_Ky_City"),
    (16.4321, 107.9321, "Huong_Tra_District"),
    (16.4612, 107.7832, "Huong_Thuy_District"),
    (16.3421, 108.0012, "Nam_Dong_District"),
    (16.5612, 107.8741, "Phu_Loc_District"),
    (16.4001, 107.6521, "A_Luoi_Mountain"),
    (16.2812, 107.5321, "Nam_Dong_Highland"),
    (16.0543, 108.2022, "Da_Nang_City"),
    (15.9123, 108.1541, "Cam_Le_District"),
    (16.1232, 108.1982, "Lien_Chieu_District"),
    (16.0012, 108.2401, "Son_Tra_District"),
    (15.8721, 108.0841, "Thanh_Khe_District"),
    (16.2432, 108.0762, "Hoa_Vang_District"),
    (15.7321, 108.1432, "Phu_Yen_Commune"),
    (15.3200, 107.8341, "Bac_Tra_My"),
    (15.8453, 107.9872, "Nam_Tra_My"),
    (15.6721, 108.0341, "Hiep_Duc_District"),
    (15.5631, 108.2541, "Tien_Phuoc_District"),
    (15.4321, 108.4012, "Nui_Thanh_South"),
    (15.6012, 108.3341, "Tam_Ky_South"),
    (16.5123, 107.6012, "Phu_Loc_West"),
    (16.6321, 107.7821, "Phu_Vang_District"),
    (16.5543, 107.9321, "Quang_Dien_District"),
    (16.4872, 108.1012, "Phong_Dien_District"),
    (16.4631, 108.2621, "Hue_City_South"),
    (16.4631, 107.4321, "Khe_Tre_Commune"),
    (15.7143, 107.8101, "Tra_Don_Commune"),
    (15.5832, 107.9431, "Tra_Nam_Commune"),
    (16.7012, 107.5831, "Lang_Co_Area"),
    (16.6012, 107.3541, "Truoi_Lake_Area"),
    (15.9432, 107.5932, "Vu_Gia_River_South"),
    (16.1321, 107.4531, "Song_Bung_Lake"),
    (16.0743, 107.3021, "A_Sap_Valley"),
    (15.8123, 107.6321, "Phuoc_Son_District"),
    (15.6831, 107.7851, "Tra_My_Highlands"),
    (16.3012, 107.2321, "Bach_Ma_Forest"),
    (16.5412, 107.1081, "A_Luoi_Valley"),
    (16.7832, 107.4231, "Huong_An_Commune"),
    (16.0231, 108.3491, "Tho_Quang_Ward"),
    (15.9812, 108.1721, "Hoa_Cuong_Ward"),
    (15.8342, 108.0012, "An_Tan_Commune"),
    (16.1891, 107.9341, "Lac_My_Commune"),
    (16.3543, 107.6521, "Hong_Ha_Commune"),
    (16.5014, 107.8031, "Quang_An_Ward"),
    (16.2231, 107.3041, "Huong_Xuan_Commune"),
    (15.6521, 108.1341, "Tam_Viet_Commune"),
    (15.4832, 108.3031, "Tam_Hiep_Commune"),
    (15.7981, 108.4201, "Binh_Duong_Commune"),
    (16.8012, 107.5321, "Phu_Dien_Ward"),
    (16.0601, 108.2411, "My_Khe_Beach_Area"),
    (16.9321, 107.3012, "A_Dot_Commune"),
    (15.4501, 108.5801, "Tam_Quan_Town"),
    (15.2431, 108.4231, "Nuoc_Trong_Reservoir"),
    (15.1241, 108.3121, "Duc_Pho_District"),
    (16.9541, 107.1231, "A_Bat_Commune"),
    (17.0231, 107.2031, "A_La_Commune"),
    (16.8981, 106.6061, "Huong_Lap_Commune"),
    (16.8501, 107.2501, "Cao_Ngan_Commune"),
    (15.0541, 108.6541, "Mo_Duc_District"),
    (15.1831, 10 8.7801, "Minh_Long_District"),
    (15.8712, 108.5041, "Chu_Lai_Port"),
    (15.4012, 107.8501, "Son_Ha_District"),
    (15.2831, 107.7021, "Son_Tay_District"),
    (15.0001, 107.9231, "Tra_Bong_District"),
    (14.9321, 108.1431, "Nghia_Hanh_District"),
    (14.8541, 108.3201, "Tu_Nghia_District"),
    (15.1200, 108.4801, "Quang_Ngai_City"), 
    (14.9012, 108.5601, "Son_Tinh_District"),
    (15.1231, 108.6271, "Binh_Son_District"),
    (15.6121, 107.4031, "Khue_Trung_Valley"),
    (16.7231, 107.6851, "Phu_Thuong_Ward"),
    (15.5501, 108.5401, "Truong_Giang_Commune"),
    (17.0721, 107.6231, "Son_Qua_Commune"),
    (15.9301, 108.4521, "Xuan_Ha_Ward"),
    (16.0851, 108.2441, "Man_Thai_Ward"),
    (15.5601, 107.9151, "Phuoc_Hiep_Commune"),
    (16.1751, 108.4201, "Hoa_Lien_Commune"),
    (16.3121, 108.3721, "Hoa_Tien_Commune"),
    (16.0321, 107.6531, "Zuoih_Commune"),
    (15.8901, 107.4581, "Bha_Le_Commune"),
    (15.6812, 107.2541, "Tra_Vie_Commune"),
    (15.4981, 107.1081, "Ca_Dy_Commune"),
    (15.2341, 107.0231, "Tra_Bui_Commune"),
    (16.2521, 107.8951, "Ta_Lang_Commune"),
    (16.4012, 107.4081, "Thuong_Quang_Commune"),
    (16.6721, 107.2541, "A_Ngo_Commune"),
    (16.8341, 107.0931, "A_Tuc_Commune"),
    (15.5321, 107.5031, "Ca_Lu_Commune"),
    (16.0544, 108.2022, "Da_Nang_Airport_Hub"),
    (15.5600, 108.3300, "Tam_Ky_Logistics_Hub"),
    (16.4601, 107.5961, "A_Luoi_Relief_Center"),
    (15.9700, 107.8600, "Dong_Giang_Rescue_Stn"),
    (15.6400, 108.2100, "Thang_Binh_Depot"),
    (16.3300, 108.0070, "Nam_Giang_Forward_Base"),
    (16.5600, 107.8600, "Phu_Loc_Staging_Area"),
    (15.4500, 108.4200, "Nui_Thanh_Reserve"),
    (16.7200, 107.5900, "Lang_Co_Forward_Post"),
    (15.2200, 108.6000, "Binh_Son_Warehouse"),
    (16.9300, 107.2500, "A_Dot_Mountain_Base"),
    (15.0500, 108.4000, "Quang_Ngai_Depot"),
    (16.1500, 107.6200, "A_Sap_Helipad"),
    (15.7800, 108.0500, "Que_Son_Facility"),
    (16.8600, 107.8300, "Huong_Viet_Depot"),
    (14.8700, 108.7900, "Quang_Ngai_Port"),
    (15.6200, 107.7200, "Phuoc_Son_Helipad"),
    (17.0500, 107.4300, "Rao_Trang_Base"),
    (16.2800, 107.5100, "Bac_Tra_My_Depot"),
    (15.4100, 107.5600, "Son_Ha_Hub"),
    (16.1124, 108.1948, "Hai_Van_Pass_North"),
    (15.4000, 108.3100, "Dung_Quat_Port"),
    (15.7500, 108.4700, "Chu_Lai_Airport"),
    (16.8800, 107.5500, "Thuan_An_Port"),
    (14.7600, 108.6900, "Sa_Ky_Port"),
    (17.1900, 107.0700, "Khe_Sanh_Entry"),
    (15.3600, 107.8900, "Tra_Bong_Supply"),
    (16.0100, 108.6400, "Da_Nang_Seaport"),
    (16.9700, 107.7700, "Hue_Train_Station"),
    (15.3800, 109.1000, "Ly_Son_Island_Supply"),
    (16.4900, 108.2300, "Lang_Co_Beach_Base"),
    (14.5700, 108.9800, "Duc_Pho_Harbor")
]

def haversine(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# 3. RISK MODELING AND NODE CLASSIFICATION
def eval_intrinsic_risk(lat, lon):
    """
    Evaluate the inherent flood risk (r^a_u) between 0 and 1.
    Higher values mean more prone to serious floods geographically.
    In Central Vietnam, coastal lowlands (high lon) and river areas
    like Vu Gia-Thu Bon basin are high risk. Mountains (low lon) are lower flood risk.
    """
    min_lon, max_lon = 107.0, 108.8
    normalized_lon = (lon - min_lon) / (max_lon - min_lon)
    normalized_lon = max(0.0, min(1.0, normalized_lon))
    
    # Intrinsic risk is higher towards the coast
    base_risk = 0.2 + (0.8 * normalized_lon) 
    noise = random.uniform(-0.1, 0.1)
    
    risk = base_risk + noise
    return max(0.01, min(0.99, risk))

def categorize_nodes(node_list):
    """
    Dynamically distribute the given set of nodes into Demand (I), Hubs (H), and Origins (J)
    based on their intrinsic risk profile r^a_u
    """
    analyzed_nodes = []
    for lat, lon, nm in node_list:
        rau = eval_intrinsic_risk(lat, lon)
        analyzed_nodes.append({
            "name": nm,
            "lat": lat,
            "lon": lon,
            "rau": rau
        })
    
    # Sort by risk (lowest to highest)
    analyzed_nodes.sort(key=lambda x: x["rau"])
    
    n = len(analyzed_nodes)
    origins = []
    hubs = []
    demands = []
    
    # - 10% safest as Origins (J)
    # - Next 20% + random moderate as Hubs (H)
    # - Rest (~70%) as demands (I)
    
    for i, node in enumerate(analyzed_nodes):
        if i < int(n * 0.1):
            origins.append(node)
        elif i < int(n * 0.3):
            if random.random() < 0.2:
                demands.append(node)
            else:
                hubs.append(node)
        else:
            if random.random() < 0.05 and len(hubs) < int(n * 0.3):
                 hubs.append(node)
            else:
                 demands.append(node)
                 
    # Ensure minimum sizes
    while len(origins) < 2 and demands: origins.append(demands.pop(0))
    while len(hubs) < 5 and demands: hubs.append(demands.pop(0))
    
    return demands, hubs, origins

# 4. TERRAIN DISRUPTION AND MODAL COSTS
MODE_PARAMS = {
    0: {"name": "road",  "speed_kmh": 35.0,  "unit_cost": 2.0,  "vehicle_cap": 60},
    1: {"name": "water", "speed_kmh": 25.0,  "unit_cost": 5.0,  "vehicle_cap": 25},
    2: {"name": "air",   "speed_kmh": 150.0, "unit_cost": 40.0, "vehicle_cap": 10},
}

def terrain_factor(lon):
    """Returns a multiplier [1.0, 1.8] based on lon (proximal to coastal flat = 1.0 vs deep mountains = 1.8)"""
    lon_min, lon_max = 107.0, 108.8
    t = 1.0 - (lon - lon_min) / (lon_max - lon_min)
    return 1.0 + 0.8 * max(0.0, min(1.0, t))

def create_global_distance_matrices(nodes):
    """
    Compute C[m][u][v] and T[m][u][v] among all nodes.
    Use proper integer/float precision mathematically mapping terrain.
    """
    n = len(nodes)
    C = [[[0.0]*n for _ in range(n)] for _ in range(NUM_MODES)]
    T = [[[0.0]*n for _ in range(n)] for _ in range(NUM_MODES)]

    for i in range(n):
        for j in range(n):
            if i == j: continue
            dist = haversine(nodes[i]["lat"], nodes[i]["lon"], nodes[j]["lat"], nodes[j]["lon"])
            
            # Midpoint bounds the terrain factor roughly representing the path
            mid_lon = (nodes[i]["lon"] + nodes[j]["lon"]) / 2.0
            tf = terrain_factor(mid_lon)
            
            # Road (m=0) Cost 
            # uses tortuosity = 1.3 roughly representing curved mountain paths
            d_road = dist * 1.3
            C[0][i][j] = d_road * MODE_PARAMS[0]["unit_cost"] * tf
            T[0][i][j] = d_road / MODE_PARAMS[0]["speed_kmh"] * tf

            # Water (m=1) (inherently less affected by terrain climbs up slopes, but follows river meandering)
            water_tf = 1.0 + 0.1 * (tf - 1.0)
            d_water = dist * 1.1 
            C[1][i][j] = d_water * MODE_PARAMS[1]["unit_cost"] * water_tf
            T[1][i][j] = d_water / MODE_PARAMS[1]["speed_kmh"] * water_tf

            # Air (m=2) (Helicopter straight lines, lightly affected by heavy storms/winds above mountains)
            air_tf = 1.0 + 0.3 * (tf - 1.0)
            C[2][i][j] = dist * MODE_PARAMS[2]["unit_cost"] * air_tf
            T[2][i][j] = dist / MODE_PARAMS[2]["speed_kmh"] * air_tf

    return C, T

# 5. GENERATING INITIAL POPULATION AND BASE DEMAND
def initialize_population_state(demands):
    pop = {}
    area = {}
    for node in demands:
        # Denser near coast
        coast_factor = 1.0 - abs(node["lon"] - 108.2) / 1.5
        pop_estimate = int(random.uniform(500, 5000) * max(0.2, coast_factor))
        area_estimate = random.uniform(8, 40) * (1 + max(0.0, 1.0 - coast_factor))
        
        pop[node["name"]] = pop_estimate
        area[node["name"]] = area_estimate
        
    return pop, area

# 6. SCENARIO DISASTER GENERATOR
DAGANZO_PHI = 0.57    # standard circuity
ETA = 5               # average group size per distress
GAMMA_CONV = 3.0      # kg/person of relief
base_capacity_multiplier = 4.0 # For generating ample safe hub capacity 

SCENARIOS = [
    # name, prob, n_epicenters, impact_radius_km, base_intensity
    ("mild", 0.60, 1, 50.0, 0.4),
    ("severe", 0.30, 2, 40.0, 0.7),
    ("extreme", 0.10, 3, 30.0, 1.0)
]

def create_scenarios(demands, hubs, origins, all_nodes):
    scenarios = []
    
    for s_idx, (name, prob, n_ep, radius, inten) in enumerate(SCENARIOS):
        epicenters = []
        # Sample completely random coordinates within the bounding box of our region
        possible_nodes = all_nodes
        sampled_ep_nodes = random.sample(possible_nodes, min(len(possible_nodes), n_ep))
        
        for ep_node in sampled_ep_nodes:
            epicenters.append({
                "lat": ep_node["lat"],
                "lon": ep_node["lon"],
                "intensity": inten * random.uniform(0.8, 1.2)
            })
            
        scenario_demands = {}
        scenario_risks = {}
        scenario_accessibility = [[[-1]*len(all_nodes)]*len(all_nodes)] # initialized properly later
        
        # We need a quick index for full nodes
        for i, node in enumerate(all_nodes):
            # Compute scenario localized risk mapping
            cur_r = 0.0
            for ep in epicenters:
                dist = haversine(node["lat"], node["lon"], ep["lat"], ep["lon"])
                cur_r += ep["intensity"] * math.exp(- (dist**2) / (2 * radius**2))
            
            # Incorporate intrinsic risk. High intrinsic risk zones react worse to general disasters
            # Moderated risk = combined with standard base intrinsic
            final_risk = min(1.0, max(0.01, cur_r * (1 + node["rau"])))
            scenario_risks[node["name"]] = final_risk
        
        scenarios.append({
            "name": name,
            "probability": prob,
            "epicenters": epicenters,
            "risk": scenario_risks
        })
        
    return scenarios

# 7. ROUTING AND COST (DAGANZO COMPUTATION CA COMPUTATION)
CHI_SAFETY = 0.7 
ALPHA_ECON = 0.6 

def daganzo_theta(c_mode, a_mode, d_is, Q_m, c_m_km, phi, eta, a_i, big_M=1e9):
    """ theta calculation per node Daganzo proxy constraints """
    best = big_M
    for m in range(NUM_MODES):
        if a_mode[m] == 0: continue
        qm = MODE_PARAMS[m]["vehicle_cap"]
        cm = c_mode[m]       # route cost
        trips = math.ceil(d_is / qm) if qm > 0 else 1
        n_stops = math.ceil(d_is / eta) if eta > 0 else 1
        theta = 2.0 * cm * trips + c_m_km * phi * math.sqrt(n_stops * a_i)
        if theta < best: best = theta
    return best

# 8. BUILD FINAL INSTANCE TO JSON
def build_instance(size="small"):
    if size == "small":
        n_demand = 20; n_hub = 5; n_origin = 2
    else:
        n_demand = 100; n_hub = 20; n_origin = 12

    # Parse and categorize directly dynamically eliminating structural limits
    all_demands, all_hubs, all_origins = categorize_nodes(ALL_REAL_NODES)
    
    # Selecting sets depending on instance scale randomly ensures prob distributions hold
    demands = all_demands[:min(len(all_demands), n_demand)]
    hubs = all_hubs[:min(len(all_hubs), n_hub)]
    origins = all_origins[:min(len(all_origins), n_origin)]
    
    selected_nodes = demands + hubs + origins
    
    # 1. Distances and Modes
    C_all, T_all = create_global_distance_matrices(selected_nodes)
    pop, area = initialize_population_state(demands)
    
    scenarios = create_scenarios(demands, hubs, origins, selected_nodes)
    
    # Map scenarios metrics properly determining Dynamic Data demands and Disruption
    scenarios_data = []
    
    for s_idx, sc_info in enumerate(scenarios):
        sc_demand = {}
        sc_supply = {}
        sc_access = [[[1]*len(selected_nodes) for _ in range(len(selected_nodes))] for _ in range(NUM_MODES)]
        
        # Scenarios demand mapping. Total proportional to base population * severity / risk 
        sum_demand_pers = 0
        for i, d in enumerate(demands):
            risk = sc_info["risk"][d["name"]]
            # Modulate according to base scenario risk intensity logic
            sev_mult = SCENARIOS[s_idx][4] # index 4 is inten
            base = pop[d["name"]] * (0.1 + 0.9 * risk) * sev_mult
            noise = random.gauss(0, 0.05 * base)
            final_d = max(10.0, base + noise)
            sc_demand[str(i)] = final_d
            sum_demand_pers += final_d
            
        total_demand_kg = GAMMA_CONV * sum_demand_pers
        total_supply_target = total_demand_kg * random.uniform(1.5, 2.5)
        
        idx_offset_j = len(demands) + len(hubs) # origin start index offset
        for j, o in enumerate(origins):
             sc_supply[str(idx_offset_j + j)] = max(5000.0, (total_supply_target / len(origins)) * random.uniform(0.8, 1.2))
             
        # Scenarios disruption tracking
        for ui, u in enumerate(selected_nodes):
            for vi, v in enumerate(selected_nodes):
                 if ui == vi: 
                     for m in range(NUM_MODES): sc_access[m][ui][vi] = 0
                     continue
                 
                 avg_risk = (sc_info["risk"][u["name"]] + sc_info["risk"][v["name"]]) / 2.0
                 # Only Road breaks apart in flood situations
                 p_disrupt = min(1.0, 0.45 * avg_risk * SCENARIOS[s_idx][4]) # probability
                 if random.random() < p_disrupt:
                     sc_access[0][ui][vi] = 0
                     sc_access[0][vi][ui] = 0
                     
        hub_reactive_cost = {str(len(demands)+ki): random.uniform(30000, 80000) * (1 + sc_info["risk"][h["name"]]) for ki, h in enumerate(hubs)}
        hub_process_time = {str(len(demands)+ki): random.uniform(0.5, 2.0) * (1 + sc_info["risk"][h["name"]]) for ki, h in enumerate(hubs)}
        
        sc_obj = {
            "name": sc_info["name"],
            "probability": sc_info["probability"],
            "epicenters": sc_info["epicenters"],
            "risk": {str(ui): sc_info["risk"][u["name"]] for ui, u in enumerate(selected_nodes)},
            "accessibility": sc_access,
            "demand": sc_demand,
            "supply": sc_supply,
            "hub_reactive_cost": hub_reactive_cost,
            "hub_process_time": hub_process_time
        }
        scenarios_data.append(sc_obj)
        
    # Calculate robust max capacity requirements bounding constraints appropriately according to highest scenarios constraint limit
    max_total_demand_kg = max(sum(GAMMA_CONV * float(d) for d in sc["demand"].values()) for sc in scenarios_data)
    
    hub_cap = {}
    hub_fixed_cost = {}
    hub_hold_cost = {}
    for ki, h in enumerate(hubs):
         idx = len(demands) + ki
         # Construct variables kappa_k bounded over candidates area footprint sizes ensuring overall resilience multipliers
         tf = terrain_factor(h["lon"])
         hub_cap[str(idx)] = int((max_total_demand_kg / len(hubs)) * random.uniform(3.0, 6.0) * tf)
         hub_fixed_cost[str(idx)] = random.uniform(50000, 200000) * tf
         hub_hold_cost[str(idx)] = random.uniform(0.2, 1.0)
         
    # Theta arrays for Daganzo
    Theta = [[[0.0]*len(scenarios_data) for _ in range(len(demands))] for _ in range(len(hubs))]
    for ki, h in enumerate(hubs):
        # actual index in matrix
        mat_ki = len(demands) + ki
        for ii, d in enumerate(demands):
            for si, sc in enumerate(scenarios_data):
                 d_is = sc["demand"].get(str(ii), 0.0)
                 a_i = area[d["name"]]
                 c_mode = [C_all[m][mat_ki][ii] for m in range(NUM_MODES)]
                 a_mode = [sc["accessibility"][m][mat_ki][ii] for m in range(NUM_MODES)]
                 Theta[ki][ii][si] = daganzo_theta(c_mode, a_mode, d_is, None, 2.5, DAGANZO_PHI, ETA, a_i)
                 
    Lambda = {}
    for si, sc in enumerate(scenarios_data):
        for ii, d in enumerate(demands):
            risk_i = sc["risk"][str(ii)]
            Lambda[f"{ii}_{si}"] = 0.8 * (1.0 + risk_i)
            
    # Complete Instance Construction
    instance = {
        "meta": {"name": f"Central_Vietnam_DRND_{size}", "seed": SEED, "size": size},
        "dimensions": {"num_I": len(demands), "num_H": len(hubs), "num_J": len(origins), "num_S": len(scenarios_data), "num_M": NUM_MODES},
        "nodes": {
           "coords": [[n["lat"], n["lon"]] for n in selected_nodes],
           "names": [n["name"] for n in selected_nodes],
           "demand_indices": list(range(len(demands))),
           "hub_indices": list(range(len(demands), len(demands)+len(hubs))),
           "origin_indices": list(range(len(demands)+len(hubs), len(selected_nodes)))
        },
        "global_params": {"alpha": ALPHA_ECON, "chi": CHI_SAFETY, "gamma": GAMMA_CONV, "big_M": 1e9, "daganzo_phi": DAGANZO_PHI, "daganzo_eta": ETA},
        "hub_params": {"capacity": hub_cap, "fixed_cost": hub_fixed_cost, "hold_cost": hub_hold_cost},
        "base_population": {str(ii): pop[d["name"]] for ii, d in enumerate(demands)},
        "area_km2": {str(ii): area[d["name"]] for ii, d in enumerate(demands)},
        "transport": {"cost": C_all, "time": T_all},
        "scenarios": scenarios_data,
        "theta": Theta,
        "lambda": Lambda
    }
    return instance

def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))
    for size in ["small", "large"]:
        print(f"Generating {size.upper()} instance...")
        inst = build_instance(size)
        path = os.path.join(out_dir, f"central_vietnam_{size}_drnd.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(inst, f, indent=2, ensure_ascii=False)
        print(f"Saved: {path}")

if __name__ == "__main__":
    main()


