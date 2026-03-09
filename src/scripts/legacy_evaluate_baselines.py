"""
evaluate_baselines.py — LEGACY: Standalone Pareto / HV / IGD+ Utilities
================================================================================
STATUS: Not part of the current pipeline.
        The canonical Experiment 1 metric computation is done by
        exp1_evaluate_cv_small.py (which uses pymoo when available and
        contains its own self-contained fallback implementations).

This module was an early prototype for computing non-dominated fronts,
hypervolume (HV), and IGD+ from raw solver JSON files.  The HV
calculation here has a known off-by-one in the sweep integration; use
exp1_evaluate_cv_small.py or exp2_analyze_case_study.py for published results.
"""

import json
import glob
import numpy as np

def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def get_solutions(jdata):
    # Depending on format (if it's array of solutions or dict with pareto_front)
    if "pareto_front" in jdata:
        return [(s["Z1"], s["Z2"]) for s in jdata["pareto_front"]]
    else:
        # PB-NSGA output structure fallback?
        # Actually in this codebase it's usually dict with 'pareto_front' list
        return [(s["Z1"], s["Z2"]) for s in jdata.get("pareto_front", [])]

def dominates(s1, s2):
    return (s1[0] <= s2[0] and s1[1] <= s2[1]) and (s1[0] < s2[0] or s1[1] < s2[1])

def get_pareto_front(sols):
    front = []
    for s1 in sols:
        dom = False
        for s2 in front:
            if dominates(s2, s1):
                dom = True
                break
            if dominates(s1, s2):
                 # s1 dominates something in front, we should rebuild front
                 # Actually standard way is:
                 pass
        if dom: continue
        # s1 is not dominated by anything in front
        # filter out things in front that s1 dominates
        front = [s2 for s2 in front if not dominates(s1, s2)]
        front.append(s1)
    return front

def compute_hv(front, ref):
    if not front: return 0.0
    # Keep only points that strictly dominate the reference point
    valid = [p for p in front if p[0] <= ref[0] and p[1] <= ref[1]]
    if not valid: return 0.0
    
    # Sort by Z1 ascending
    sorted_front = sorted(valid, key=lambda x: x[0])
    
    # Filter out dominated points (since we might have pseudo-fronts)
    nd_front = [sorted_front[0]]
    for p in sorted_front[1:]:
        if p[1] < nd_front[-1][1]:
            nd_front.append(p)
            
    hv = 0.0
    prev_z1 = nd_front[0][0]
    for p in nd_front:
        hv += (p[0] - prev_z1) * (ref[1] - p[1])
        prev_z1 = p[0]
        
    width = ref[0] - prev_z1
    height = ref[1] - nd_front[-1][1]
    if width > 0 and height > 0:
        hv += width * height
        
    return hv

def compute_igd_plus(approx, true_front, ref):
    if not approx or not true_front: return 0.0
    _igd = 0.0
    # Normalize
    t_min = [min(x[0] for x in true_front), min(x[1] for x in true_front)]
    t_max = [max(x[0] for x in true_front), max(x[1] for x in true_front)]
    rng = [max(1e-6, t_max[0] - t_min[0]), max(1e-6, t_max[1] - t_min[1])]
    
    for tp in true_front:
        ntp = [(tp[0]-t_min[0])/rng[0], (tp[1]-t_min[1])/rng[1]]
        min_dist = 1e9
        for ap in approx:
            nap = [(ap[0]-t_min[0])/rng[0], (ap[1]-t_min[1])/rng[1]]
            d1 = max(0, nap[0] - ntp[0])
            d2 = max(0, nap[1] - ntp[1])
            d = math.sqrt(d1*d1 + d2*d2)
            if d < min_dist: min_dist = d
        _igd += min_dist
    return _igd / len(true_front)

import math

def main():
    import glob
    import os
    
    pbnsga_files = glob.glob("results/exp1/CV_small_seed*.json")
    if not pbnsga_files:
        pbnsga_files = glob.glob("results/exp2/CV_small_seed*.json")
        
    sols_pbnsga_all = []
    
    for pf in pbnsga_files:
        d = load_json(pf)
        sols_pbnsga_all.extend(get_solutions(d))
        
    def safe_load(path):
        if os.path.exists(path):
             return get_solutions(load_json(path))
        return []
    
    sols_greedy = safe_load("results/exp1/cv_small_greedy.json")
    sols_milp = safe_load("results/exp1/cv_small_milp.json")
    sols_aws = safe_load("results/exp1/cv_small_aws.json")
    sols_bb = safe_load("results/exp1/cv_small_bb.json")
    if not sols_bb:
        sols_bb = safe_load("results/exp2/CV_small_bb.json")
        
    all_combined = sols_pbnsga_all + sols_greedy + sols_milp + sols_aws + sols_bb
    true_front = get_pareto_front(all_combined)
    
    print(f"--- TRUTH ---")
    print(f"Total Reference points: {len(true_front)}")
    
    # IGD+
    ref = [max(x[0] for x in all_combined), max(x[1] for x in all_combined)]
    
    igd_greedy = compute_igd_plus(sols_greedy, true_front, ref)
    igd_milp = compute_igd_plus(sols_milp, true_front, ref)
    igd_aws = compute_igd_plus(sols_aws, true_front, ref)
    igd_bb = compute_igd_plus(sols_bb, true_front, ref)
    
    print(f"IGD+ Greedy: {igd_greedy:.4f} ({len(sols_greedy)} points)")
    print(f"IGD+ MILP: {igd_milp:.4f} ({len(sols_milp)} points)")
    print(f"IGD+ AWS: {igd_aws:.4f} ({len(sols_aws)} points)")
    print(f"IGD+ Exact (BB): {igd_bb:.4f} ({len(sols_bb)} points)")
    
    # Calculate HV with reference point slightly worse than the nadir points
    ref_hv = [max(x[0] for x in true_front) * 1.1, max(x[1] for x in true_front) * 1.1]
    hv_true = compute_hv(true_front, ref_hv)
    
    def norm_hv(sols):
        if not sols: return 0.0
        return compute_hv(get_pareto_front(sols), ref_hv) / (hv_true + 1e-9)
        
    hv_greedy = norm_hv(sols_greedy)
    hv_milp = norm_hv(sols_milp)
    hv_aws = norm_hv(sols_aws)
    hv_bb = norm_hv(sols_bb)
    
    print(f"HV (norm) Greedy: {hv_greedy:.4f}")
    print(f"HV (norm) MILP: {hv_milp:.4f}")
    print(f"HV (norm) AWS: {hv_aws:.4f}")
    print(f"HV (norm) Exact (BB): {hv_bb:.4f}")
    
    igds_pbnsga = []
    hvs_pbnsga = []
    for pf in pbnsga_files:
        s = get_solutions(load_json(pf))
        igds_pbnsga.append(compute_igd_plus(s, true_front, ref))
        hvs_pbnsga.append(norm_hv(s))
    print(f"IGD+ PB-NSGA: {np.mean(igds_pbnsga):.4f} +/- {np.std(igds_pbnsga):.4f} (over {len(pbnsga_files)} seeds)")
    print(f"HV (norm) PB-NSGA: {np.mean(hvs_pbnsga):.4f} +/- {np.std(hvs_pbnsga):.4f} (over {len(pbnsga_files)} seeds)")

if __name__ == "__main__":
    main()
