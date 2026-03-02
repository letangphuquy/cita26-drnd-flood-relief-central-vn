import os
import random
import math

# Fixed seed
random.seed(42)

# Da Nang as center point
CENTER_LAT = 16.0544
CENTER_LON = 108.2022
RADIUS_KM = 200.0

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0 # Earth radius in km
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def generate_random_point(center_lat, center_lon, radius_km):
    # Random radius in km and angle
    r = radius_km * math.sqrt(random.random())
    theta = random.random() * 2 * math.pi
    
    # Approx conversion from km to degrees (1 deg lat ~ 111km)
    lat_offset = (r * math.cos(theta)) / 111.0
    lon_offset = (r * math.sin(theta)) / (111.0 * math.cos(math.radians(center_lat)))
    
    return center_lat + lat_offset, center_lon + lon_offset

def generate_matrices(num_i, num_h, num_j):
    n = num_i + num_h + num_j
    
    coords = []
    places = []
    
    for i in range(n):
        lat, lon = generate_random_point(CENTER_LAT, CENTER_LON, RADIUS_KM)
        coords.append((lat, lon))
        if i < num_i:
            places.append(f"Demand_{i+1}")
        elif i < num_i + num_h:
            places.append(f"Hub_{i-num_i+1}")
        else:
            places.append(f"External_{i-num_i-num_h+1}")
            
    # Compute Cost Matrix C (Road distance approximation: Euclidean Haversine * 1.3 tortuosity)
    TORTUOSITY = 1.3
    C = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                C[i][j] = haversine(coords[i][0], coords[i][1], coords[j][0], coords[j][1]) * TORTUOSITY

    # Compute Demand Matrix W
    # Flow might be generated among demand nodes or external to demand. We create random flows
    W = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                # 30% chance of having a flow
                if random.random() < 0.3:
                    W[i][j] = random.uniform(10.0, 100.0)
                    
    return n, C, W, coords, places

def write_cpp_input(n, C, W, coords, places, out_path):
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f"Cost Matrix C for {n} nodes\n")
        for i in range(n):
            f.write(" ".join([f"{val:.4f}" for val in C[i]]) + "\n")
            
        f.write(f"Demand Matrix W for {n} nodes\n")
        for i in range(n):
            f.write(" ".join([f"{val:.4f}" for val in W[i]]) + "\n")
            
        f.write(f"Lat Lon Places for {n} nodes\n")
        for i in range(n):
            lat, lon = coords[i]
            place = places[i]
            f.write(f"{lat:.4f} {lon:.4f} {place}\n")

def generate_scenario_arcs(n, disruption_prob, out_path):
    # Generates a binary array representation of available Arcs for a given disruption
    # disruption_prob = % of links disrupted
    arcs = [[1] * n for _ in range(n)]
    for i in range(n):
        arcs[i][i] = 0
        for j in range(i+1, n):
            if random.random() < disruption_prob:
                arcs[i][j] = arcs[j][i] = 0
            else:
                arcs[i][j] = arcs[j][i] = 1
                
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f"Arcs availability for disruption {disruption_prob*100}%\n")
        for i in range(n):
            f.write(" ".join([str(val) for val in arcs[i]]) + "\n")

def run():
    out_folder = '../dataset/synthetic'
    os.makedirs(out_folder, exist_ok=True)
    
    # 1. Scale nhỏ (27 nodes)
    print("Generating Small Scale Synthetic Dataset...")
    n_small, C_small, W_small, coords_small, places_small = generate_matrices(num_i=20, num_h=5, num_j=2)
    base_small = os.path.join(out_folder, "Synthetic_Small_input.txt")
    write_cpp_input(n_small, C_small, W_small, coords_small, places_small, base_small)
    
    generate_scenario_arcs(n_small, 0.05, os.path.join(out_folder, "Arcs_Small_Mild.txt"))
    generate_scenario_arcs(n_small, 0.30, os.path.join(out_folder, "Arcs_Small_Severe.txt"))
    generate_scenario_arcs(n_small, 0.60, os.path.join(out_folder, "Arcs_Small_Extreme.txt"))
    
    # 2. Scale lớn (High resolution, 150 + 30 + 10 = 190 nodes)
    print("Generating High-Resolution Synthetic Dataset...")
    n_high, C_high, W_high, coords_high, places_high = generate_matrices(num_i=150, num_h=30, num_j=10)
    base_high = os.path.join(out_folder, "Synthetic_HighRes_input.txt")
    write_cpp_input(n_high, C_high, W_high, coords_high, places_high, base_high)
    
    generate_scenario_arcs(n_high, 0.05, os.path.join(out_folder, "Arcs_HighRes_Mild.txt"))
    generate_scenario_arcs(n_high, 0.30, os.path.join(out_folder, "Arcs_HighRes_Severe.txt"))
    generate_scenario_arcs(n_high, 0.60, os.path.join(out_folder, "Arcs_HighRes_Extreme.txt"))
    
    print("Synthetic datasets generated successfully inside dataset/synthetic/")

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    run()
