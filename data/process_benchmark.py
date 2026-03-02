import pandas as pd
import numpy as np
import os
import random
import math

# Để đảm bảo tính tái lập (reproducibility)
random.seed(42)

def write_cpp_input(n, C, W, coords, places, out_path):
    with open(out_path, 'w', encoding='utf-8') as f:
        # Message 1
        f.write(f"Cost Matrix C for {n} nodes\n")
        # Phù hợp với mảng C[1..n][1..n]
        for i in range(n):
            f.write(" ".join([f"{val:.4f}" for val in C[i]]) + "\n")
            
        # Message 2
        f.write(f"Demand Matrix W for {n} nodes\n")
        for i in range(n):
            f.write(" ".join([f"{val:.4f}" for val in W[i]]) + "\n")
            
        # Message 3
        f.write(f"Lat Lon Places for {n} nodes\n")
        for i in range(n):
            lat, lon = coords[i]
            place_clean = places[i].replace(' ', '_')
            f.write(f"{lat:.4f} {lon:.4f} {place_clean}\n")

def process_turkish(excel_path='../dataset/Turkish network.xls', output_path='../dataset/TR81_input.txt'):
    print(f"Reading from {excel_path}...")
    if not os.path.exists(excel_path):
        print("Turkish network.xls missing.")
        return
    df_dist = pd.read_excel(excel_path, sheet_name='Distance (km)', index_col=0).fillna(0)
    df_flow = pd.read_excel(excel_path, sheet_name='Flow', index_col=0).fillna(0)
    
    n = df_dist.shape[0]
    
    C = []
    for i in range(n):
        C.append(pd.to_numeric(df_dist.iloc[i], errors='coerce').fillna(0).values)
        
    W = []
    for i in range(n):
        W.append(pd.to_numeric(df_flow.iloc[i], errors='coerce').fillna(0).values)
        
    coords = [(0.0, 0.0) for _ in range(n)]
    places = df_dist.index.astype(str).tolist()
    
    write_cpp_input(n, C, W, coords, places, output_path)
    print(f"Successfully exported Turkish Data to {output_path}")

def process_ap(ap_folder='../dataset/AP', out_folder='../dataset'):
    ap_files = ['10.2', '20.3', '25.3', '40.3', '50.3', '100.3', '200.3']
    for file in ap_files:
        in_path = os.path.join(ap_folder, file)
        out_path = os.path.join(out_folder, f"AP{file.replace('.', '_')}_input.txt")
        if not os.path.exists(in_path): continue
        
        with open(in_path, 'r') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        
        n = int(lines[0])
        coords = []
        for i in range(1, n+1):
            parts = lines[i].split()
            coords.append((float(parts[0]), float(parts[1])))
            
        W = []
        start_w = 1 + n
        for i in range(start_w, start_w + n):
            row = [float(x) for x in lines[i].split()]
            W.append(row)
            
        # AP distances are euclidean
        C = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                C[i][j] = math.hypot(coords[i][0] - coords[j][0], coords[i][1] - coords[j][1])
                
        places = [f"AP_Node_{i+1}" for i in range(n)]
        write_cpp_input(n, C, W, coords, places, out_path)
        print(f"Successfully exported AP Data to {out_path}")

def process_cab(cab_folder='../dataset/CAB', out_folder='../dataset'):
    cab_file = os.path.join(cab_folder, 'CAB25.txt')
    if not os.path.exists(cab_file):
        print("CAB25.txt missing.")
        return
    out_path = os.path.join(out_folder, "CAB25_input.txt")
    with open(cab_file, 'r') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    
    n = int(lines[0])
    
    # matrix 1 is W, matrix 2 is C
    W = []
    for i in range(1, n+1):
        row = [float(x) for x in lines[i].split()]
        W.append(row)
        
    C = []
    for i in range(n+1, 2*n + 1):
        row = [float(x) for x in lines[i].split()]
        C.append(row)
        
    coords = [(0.0, 0.0) for _ in range(n)]
    places = [f"CAB_City_{i+1}" for i in range(n)]
    
    write_cpp_input(n, C, W, coords, places, out_path)
    print(f"Successfully exported CAB Data to {out_path}")

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print("=== Processing Benchmark Datasets ===")
    process_turkish()
    process_ap()
    process_cab()
    print("=== Benchmark processing complete ===")
