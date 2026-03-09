"""Analyze PB-NSGA vs MILP AWS results for RCA."""
import json

# Load results
with open("results/exp1/cv_small_pb_nsga.json") as f:
    nsga = json.load(f)
with open("results/exp1/cv_small_milp_aws.json") as f:
    milp = json.load(f)

print("="*70)
print("PB-NSGA Pareto Front")
print("="*70)
for i, s in enumerate(nsga["pareto_front"]):
    print(f"\nSol {i}: Z1={s['Z1']:.2f}  Z2={s['Z2']:.2f}  CV={s['CV']:.4f}")
    print(f"  X = {s['X']}")
    print(f"  R = {[round(r,4) for r in s['R']]}")
    print(f"  A = {s['A']}")
    print(f"  W = {[round(w,4) for w in s['W']]}")

print("\n" + "="*70)
print("MILP AWS Pareto Front")
print("="*70)
for i, s in enumerate(milp["pareto_front"]):
    print(f"\nSol {i}: Z1={s['Z1']:.2f}  Z2={s['Z2']:.2f}")
    for k in s:
        if k not in ('Z1','Z2','CV','rank'):
            v = s[k]
            if isinstance(v, list) and len(v) <= 20:
                print(f"  {k} = {[round(x,4) if isinstance(x,float) else x for x in v]}")
            elif not isinstance(v, list):
                print(f"  {k} = {v}")

# Diversity analysis for R
print("\n" + "="*70)
print("R-Vector Diversity Analysis (PB-NSGA)")
print("="*70)
rs = [s['R'] for s in nsga["pareto_front"]]
for i in range(len(rs[0])):
    vals = [r[i] for r in rs]
    print(f"  R[{i}]: min={min(vals):.4f} max={max(vals):.4f} range={max(vals)-min(vals):.4f}")

# X diversity
print("\nX-Vector Diversity (PB-NSGA):")
xs = [tuple(s['X']) for s in nsga["pareto_front"]]
unique_x = set(xs)
print(f"  Unique X configs: {len(unique_x)} / {len(xs)}")
for ux in unique_x:
    cnt = xs.count(ux)
    print(f"    {list(ux)} appears {cnt} times")

# W diversity
print("\nW-Vector Diversity (PB-NSGA):")
ws = [s['W'] for s in nsga["pareto_front"]]
for i in range(len(ws[0])):
    vals = [w[i] for w in ws]
    print(f"  W[{i}]: min={min(vals):.4f} max={max(vals):.4f} range={max(vals)-min(vals):.4f}")

# All feasible solutions diversity
if "all_feasible" in nsga:
    all_f = nsga["all_feasible"]
    print(f"\nAll feasible solutions: {len(all_f)}")
    all_xs = [tuple(s['X']) for s in all_f]
    unique_all_x = set(all_xs)
    print(f"  Unique X configs in all feasible: {len(unique_all_x)}")
    for ux in sorted(unique_all_x):
        cnt = all_xs.count(ux)
        print(f"    {list(ux)} appears {cnt} times")
    
    all_rs = [s['R'] for s in all_f]
    print(f"\n  R diversity across all {len(all_f)} feasible:")
    for i in range(len(all_rs[0])):
        vals = [r[i] for r in all_rs]
        print(f"    R[{i}]: min={min(vals):.4f} max={max(vals):.4f} range={max(vals)-min(vals):.4f} mean={sum(vals)/len(vals):.4f}")
