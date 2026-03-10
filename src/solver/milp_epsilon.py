import argparse
import json
import time

from milp_aws_baseline import build_and_solve_milp, load_instance


def update_front(points):
    """Keep unique non-dominated points sorted by Z1."""
    pts = sorted(points, key=lambda x: x["Z1"])
    unique = []
    for p in pts:
        if not unique:
            unique.append(p)
            continue
        if abs(p["Z1"] - unique[-1]["Z1"]) > 1e-3 or abs(p["Z2"] - unique[-1]["Z2"]) > 1e-3:
            unique.append(p)

    filtered = []
    for i, s1 in enumerate(unique):
        dominated = False
        for j, s2 in enumerate(unique):
            if i == j:
                continue
            if s2["Z1"] <= s1["Z1"] + 1e-5 and s2["Z2"] <= s1["Z2"] + 1e-5:
                if s2["Z1"] < s1["Z1"] - 1e-5 or s2["Z2"] < s1["Z2"] - 1e-5:
                    dominated = True
                    break
        if not dominated:
            filtered.append(s1)
    return filtered


def run_epsilon(inst, epsilon_steps=20, time_limit=600, eps_tol=1e-4):
    """
    Epsilon-constraint front generation:
    1) Compute lexicographic anchors.
    2) Sweep Z1 upper-bounds and minimize Z2 for each epsilon.
    """
    print("Step 1: Solving anchor points")

    p1_min_z1 = build_and_solve_milp(inst, w1=1.0, w2=0.0, time_limit_s=time_limit)
    if not p1_min_z1 or p1_min_z1["status"] == "INFEASIBLE":
        return []
    p1 = build_and_solve_milp(inst, eps_z1=p1_min_z1["Z1"] + eps_tol, w1=0.0, w2=1.0, time_limit_s=time_limit)
    if not p1 or p1["status"] == "INFEASIBLE":
        p1 = p1_min_z1

    p2_min_z2 = build_and_solve_milp(inst, w1=0.0, w2=1.0, time_limit_s=time_limit)
    if not p2_min_z2 or p2_min_z2["status"] == "INFEASIBLE":
        return update_front([p1])
    p2 = build_and_solve_milp(inst, eps_z2=p2_min_z2["Z2"] + eps_tol, w1=1.0, w2=0.0, time_limit_s=time_limit)
    if not p2 or p2["status"] == "INFEASIBLE":
        p2 = p2_min_z2

    z1_lo = min(p1["Z1"], p2["Z1"])
    z1_hi = max(p1["Z1"], p2["Z1"])
    if z1_hi - z1_lo <= 1e-6:
        return update_front([p1, p2])

    front = [p1, p2]

    print(f"Step 2: Epsilon sweep over Z1 with {epsilon_steps} intervals")
    for t in range(epsilon_steps + 1):
        eps_z1 = z1_lo + (z1_hi - z1_lo) * (t / float(epsilon_steps))
        sol = build_and_solve_milp(inst, eps_z1=eps_z1 + eps_tol, w1=0.0, w2=1.0, time_limit_s=time_limit)
        if sol and sol["status"] != "INFEASIBLE":
            front.append(sol)

    return update_front(front)


def main():
    parser = argparse.ArgumentParser(description="MILP Epsilon-Constraint Baseline: same MILP model as milp_aws_baseline.")
    parser.add_argument("--instance", required=True, help="Path to the JSON instance file.")
    parser.add_argument("--out", required=True, help="Path to save results JSON.")
    parser.add_argument("--time_limit", type=int, default=300, help="Time limit per solve.")
    parser.add_argument("--epsilon_steps", type=int, default=20, help="Number of epsilon intervals on Z1.")
    args = parser.parse_args()

    inst = load_instance(args.instance)
    t_start = time.time()
    pareto = run_epsilon(inst, epsilon_steps=args.epsilon_steps, time_limit=args.time_limit)
    t_total = time.time() - t_start

    out_data = {
        "meta": {
            "solver": "MILP_EPSILON_Baseline",
            "instance": args.instance,
            "total_elapsed_s": t_total,
            "epsilon_steps": args.epsilon_steps,
        },
        "pareto_front": pareto,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)

    print(f"\\nMILP Epsilon baseline finished. Solutions: {len(pareto)}, Time: {t_total:.2f}s")


if __name__ == "__main__":
    main()
