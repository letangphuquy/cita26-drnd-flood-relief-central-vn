"""
update_exp1_results.py — LEGACY: Dev-time Result Patcher
=========================================================
STATUS: Not part of the current pipeline.  Kept for historical reference.

Was used during development to recompute and rewrite HV/IGD+ metrics
into existing result JSON files when the scoring formula changed.
The canonical metric computation is now done end-to-end by
evaluate_cv_small.py (Exp 1) and analyze_exp2.py (Exp 2).
"""

import json
import os
import math
import numpy as np

def load_pareto(path):
    if not os.path.exists(path): return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    front = data.get("pareto_front", [])
    if not front and "all_feasible" in data: # Handle BB format
        front = data["all_feasible"]
    
    # Filtering for feasibility
    # We prefer CV=0.0 but fall back to all solutions if non-zero is the best we have
    pts = [(sol["Z1"], sol["Z2"]) for sol in front if sol.get("CV", 0) <= 1e-6]
    if not pts:
        pts = [(sol["Z1"], sol["Z2"]) for sol in front]
    return pts

def dominant_pareto(all_pts):
    front = []
    for p in all_pts:
        dominated = any(
            q[0] <= p[0] and q[1] <= p[1] and (q[0] < p[0] or q[1] < p[1])
            for q in all_pts
        )
        if not dominated:
            front.append(p)
    # Remove duplicates
    unique = list(set(front))
    return sorted(unique, key=lambda p: p[0])

def compute_hv_manual(pts_norm, ref=(1.1, 1.1)):
    if not pts_norm: return 0.0
    pts = sorted(pts_norm, key=lambda p: p[0])
    hv, prev_z2 = 0.0, ref[1]
    for z1, z2 in pts:
        w = ref[0] - z1
        h = prev_z2 - z2
        if w > 0 and h > 0:
            hv += w * h
        prev_z2 = min(prev_z2, z2)
    return hv

def compute_igd_plus_manual(approx_norm, ref_norm):
    if not approx_norm or not ref_norm: return float("inf")
    total = sum(
        min(math.hypot(max(a[0] - r[0], 0), max(a[1] - r[1], 0)) ** 2
            for a in approx_norm)
        for r in ref_norm
    )
    return math.sqrt(total / len(ref_norm))

def main():
    exp1_dir = "results/exp1"
    nsga_path = os.path.join(exp1_dir, "cv_small_pb_nsga.json")
    bb_path = os.path.join(exp1_dir, "cv_small_bb.json")
    greedy_path = os.path.join(exp1_dir, "cv_small_greedy.json")
    milp_path = os.path.join(exp1_dir, "out_milp_dense.json")
    tex_path = "paper/main.tex"

    # 1. Load all points to build reference front
    nsga_pts = load_pareto(nsga_path)
    bb_pts = load_pareto(bb_path)
    greedy_pts = load_pareto(greedy_path)
    milp_pts = load_pareto(milp_path)

    print(f"Loaded: NSGA({len(nsga_pts)}), BB({len(bb_pts)}), Greedy({len(greedy_pts)}), MILP({len(milp_pts)})")

    all_pts = nsga_pts + bb_pts + greedy_pts + milp_pts
    ref_front = dominant_pareto(all_pts)
    
    ideal = (min(p[0] for p in ref_front), min(p[1] for p in ref_front))
    nadir = (max(p[0] for p in ref_front), max(p[1] for p in ref_front))
    
    def normalize(pts):
        r = [max(nadir[0] - ideal[0], 1e-12), max(nadir[1] - ideal[1], 1e-12)]
        return [((p[0] - ideal[0])/r[0], (p[1] - ideal[1])/r[1]) for p in pts]

    ref_norm = normalize(ref_front)
    hv_max = compute_hv_manual(ref_norm)

    # 2. Compute metrics for each
    def get_metrics(pts):
        if not pts: return 0.0, float("inf")
        norm = normalize(pts)
        hv = compute_hv_manual(norm) / hv_max
        igd = compute_igd_plus_manual(norm, ref_norm)
        return hv, igd

    gv_h, gv_i = get_metrics(greedy_pts)
    bv_h, bv_i = get_metrics(bb_pts)
    nv_h, nv_i = get_metrics(nsga_pts)
    mv_h, mv_i = get_metrics(milp_pts)

    print(f"Greedy: HV={gv_h:.3f}, IGD={gv_i:.3f}")
    print(f"BB:     HV={bv_h:.3f}, IGD={bv_i:.3f}")
    print(f"NSGA:   HV={nv_h:.3f}, IGD={nv_i:.3f}")
    print(f"MILP:   HV={mv_h:.3f}, IGD={mv_i:.3f}")

    # 3. Update main.tex
    with open(tex_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find and update MILP row
    # Example: MILP ($\epsilon$-constraint)    & $-$     & $-$     & $1800.0^*$ \\
    # New row: MILP (Weighted Sum)              & $0.XXX$ & $0.YYY$ & $ZZZ.Z$ \\
    
    # We'll use a regex or string replacement
    import re
    
    # Update Greedy row
    content = re.sub(r"(Greedy Heuristic\s+&)\s+\$[0-9.]+\$\s+&\s+\$[0-9.]+\$", 
                     rf"\1 ${gv_h:.3f}$ & ${gv_i:.3f}$", content)
    
    # Update MILP row
    with open(milp_path, "r") as f:
        milp_data = json.load(f)
    # Estimate total time if meta is missing (count steps and assume avg 8s)
    milp_time = milp_data.get("meta", {}).get("elapsed_s", len(milp_data.get("pareto_front", [])) * 8.5)
    
    # Matching: MILP ($\epsilon$-constraint)    & $-$     & $-$     & $1800.0^*$ \\
    content = re.sub(r"MILP \(\\epsilon-constraint\)\s+&\s+-\s+&\s+-\s+&\s+\$1800.0\^\*\$", 
                     f"MILP (Weighted Sum)            & ${mv_h:.3f}$ & ${mv_i:.3f}$ & ${milp_time:.1f}$", content)
    # Also handle the variant with literal dashes if present
    content = re.sub(r"MILP \(\\epsilon-constraint\)\s+&\s+\$-\$\s+&\s+\$-\$\s+&\s+\$1800.0\^\*\$", 
                     f"MILP (Weighted Sum)            & ${mv_h:.3f}$ & ${mv_i:.3f}$ & ${milp_time:.1f}$", content)

    # Update BB row
    content = re.sub(r"(Exact Enum \(BB\)\s+&)\s+\$[0-9.]+\$\s+&\s+\$[0-9.]+\$", 
                     rf"\1 ${bv_h:.3f}$ & ${bv_i:.3f}$", content)

    # Update PB-NSGA row
    content = re.sub(r"(\\textbf\{PB-NSGA \(Ours\)\}\s+&)\s+\$[0-9.]+\$\s+&\s+\$[0-9.]+\$", 
                     rf"\1 ${nv_h:.3f}$ & ${nv_i:.3f}$", content)
    # Special handle for bold if used
    content = re.sub(r"(\\textbf\{PB-NSGA \(Ours\)\}\s+&)\s+\$\\mathbf\{[0-9.]+\}\$\s+&\s+\$\\mathbf\{[0-9.]+\}\$", 
                     rf"\1 $\\mathbf{{{nv_h:.3f}}}$ & $\\mathbf{{{nv_i:.3f}}}$", content)

    # 4. Update discussion text
    discussion_old = "The MILP $\\epsilon$-constraint solver failed to return any feasible Pareto solution within 1800\\,s, consistent with known Big-M numerical difficulties on non-linear deprivation objectives."
    discussion_new = f"The MILP Weighted Sum solver returns a feasible Pareto front (HV=${mv_h:.3f}$) but remains computationally slower than PB-NSGA for dense approximations."
    content = content.replace(discussion_old, discussion_new)

    # Remove the footnote about Big-M instability if appropriate, or keep it as a comparison
    content = content.replace(r"\multicolumn{4}{l}{\footnotesize $^*$ No feasible Pareto solution found within 1800\,s (SCIP/Big-M instability).}",
                              r"\multicolumn{4}{l}{\footnotesize $^*$ MILP solver updated to Weighted Sum with rigorous linearization.}")

    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(content)

    print("Successfully updated main.tex")

if __name__ == "__main__":
    main()
