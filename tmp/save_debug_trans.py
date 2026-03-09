"""Debug script: trace the Python decoder in map_solution_v2 and check
why transshipments are not being generated."""
import json, math, sys
sys.path.insert(0, "src/scripts")

d = json.load(open("data/cv/cv_large_drnd.json"))
res = json.load(open("results/exp2/CV_large_seed0.json"))

# --- Replicate pick_balanced ---
pareto = res.get("pareto_front", [])
rank1 = [s for s in pareto if s.get("rank", 1) == 1]
z1s = [s["Z1"] for s in rank1]; z2s = [s["Z2"] for s in rank1]
z1_min, z1_max = min(z1s), max(z1s)
z2_min, z2_max = min(z2s), max(z2s)
r1 = max(z1_max - z1_min, 1.0); r2 = max(z2_max - z2_min, 1.0)
sol = min(rank1, key=lambda s: ((s["Z1"]-z1_min)/r1)**2 + ((s["Z2"]-z2_min)/r2)**2)
print(f"Balanced sol: Z1={sol['Z1']:.0f}  Z2={sol['Z2']:.0f}")
print(f"X: {sol['X']}")
print(f"R: {[round(r,2) for r in sol['R']]}")

# --- Full decoder trace for scenario 0 ---
num_H = d["dimensions"]["num_H"]
num_I = d["dimensions"]["num_I"]
num_J = d["dimensions"]["num_J"]
num_M = d["dimensions"]["num_M"]
hub_idx = d["nodes"]["hub_indices"]
dem_idx = d["nodes"]["demand_indices"]
ori_idx = d["nodes"]["origin_indices"]
coords  = d["nodes"]["coords"]
sc      = d["scenarios"][0]
X, R, A, W = sol["X"], sol["R"], sol["A"], sol["W"]
chi     = d["global_params"]["chi"]
gamma   = d["global_params"]["gamma"]
kappa   = d["hub_params"]["capacity"]

# Stage 1: planned hubs
active = [False]*num_H
y      = [False]*num_H
inventory = [0.0]*num_H
for ki in range(num_H):
    k = hub_idx[ki]
    q_ki = R[ki] * kappa[str(k)]
    if X[ki] and sc["risk"][k] <= chi:
        active[ki] = True
        inventory[ki] = q_ki

print(f"\nPlanned hubs active: {[ki for ki in range(num_H) if active[ki]]}")
print(f"Inventories:         {[round(inventory[ki]) for ki in range(num_H)]}")

total_demand_kg = sum(gamma * sc["demand"][str(dem_idx[ii])] for ii in range(num_I))
total_inv       = sum(inventory)
print(f"Total demand kg = {total_demand_kg:.0f}")
print(f"Total inventory = {total_inv:.0f}")
print(f"Surplus/Deficit = {total_inv - total_demand_kg:.0f}")

# The full decoder allocation loop (mirroring map_solution_v2.py)
hub_anchor_order = []
for ki in range(num_H):
    hi = hub_idx[ki]
    lat_h, lon_h = coords[hi]
    dists = []
    for kj in range(num_H):
        hj = hub_idx[kj]
        lat_j, lon_j = coords[hj]
        dists.append(((lat_h-lat_j)**2 + (lon_h-lon_j)**2, kj))
    dists.sort()
    hub_anchor_order.append([d2[1] for d2 in dists])

raw_urgency   = [0.0]*num_I
raw_isolation = [0.0]*num_I
raw_dist      = [0.0]*num_I
for ii in range(num_I):
    i   = dem_idx[ii]
    D   = sc["demand"][str(i)]
    lam = d["lambda"][f"{ii}_{0}"]
    raw_urgency[ii] = lam * D
    n_reach = 0; min_t = 1e9
    for ki in range(num_H):
        if not active[ki]: continue
        k = hub_idx[ki]
        for m in range(num_M):
            if sc["accessibility"][m][i][k]:
                n_reach += 1; break
        for m in range(num_M):
            if sc["accessibility"][m][i][k]:
                min_t = min(min_t, d["transport"]["time"][m][i][k])
    raw_isolation[ii] = 1.0/n_reach if n_reach > 0 else 1.0
    raw_dist[ii]      = min_t if min_t < 1e9 else 0.0

def norm(vec):
    m = max(vec) if vec else 0
    if m > 0:
        for i in range(len(vec)): vec[i] /= m

norm(raw_urgency); norm(raw_isolation); norm(raw_dist)
demand_score = [W[0]*raw_urgency[ii] + W[3]*raw_isolation[ii] - W[1]*raw_dist[ii] + ii*1e-6
                for ii in range(num_I)]
demand_order = sorted(range(num_I), key=lambda ii: demand_score[ii], reverse=True)

K = max(1, int(math.ceil(W[5] * num_H)))
assignments = []
hub_load    = [0.0]*num_H
reactive_opened = []

for ii in demand_order:
    i   = dem_idx[ii]
    D   = sc["demand"][str(i)]
    D_kg = gamma * D
    anchor = A[ii] % num_H
    trial  = hub_anchor_order[anchor]

    best_ki = best_m = -1; best_t = 1e9; best_hub_score = -1e18

    for j in range(K):
        ki = trial[j]
        if not active[ki] and not y[ki]: continue
        k = hub_idx[ki]
        b_m = -1; best_c_t = 1e9; reachable = False
        for m in [0, 1]:
            if sc["accessibility"][m][i][k]:
                reachable = True
                if d["transport"]["time"][m][i][k] < best_c_t:
                    best_c_t = d["transport"]["time"][m][i][k]; b_m = m
        if b_m == -1 and sc["accessibility"][2][i][k]:
            reachable = True; best_c_t = d["transport"]["time"][2][i][k]; b_m = 2
        if not reachable: continue
        residual = inventory[ki] - hub_load[ki]
        has_global_surplus = any((active[kj] or y[kj]) and (inventory[kj]-hub_load[kj]>1e-6)
                                 for kj in range(num_H))
        if residual <= 0.0 and not has_global_surplus: continue
        score = W[1]/(best_c_t+1e-9) + W[2]*max(0.0,residual) + W[4]*(1.0 if X[ki] else 0.0)
        if score > best_hub_score:
            best_hub_score = score; best_ki = ki; best_t = best_c_t; best_m = b_m

    if best_ki == -1:
        for j in range(K, num_H):
            ki = trial[j]
            if not active[ki] and not y[ki]: continue
            k = hub_idx[ki]
            b_m = -1; best_c_t = 1e9; reachable = False
            for m in [0, 1]:
                if sc["accessibility"][m][i][k]:
                    reachable = True
                    if d["transport"]["time"][m][i][k] < best_c_t:
                        best_c_t = d["transport"]["time"][m][i][k]; b_m = m
            if b_m == -1 and sc["accessibility"][2][i][k]:
                reachable = True; best_c_t = d["transport"]["time"][2][i][k]; b_m = 2
            if not reachable: continue
            best_ki, best_t, best_m = ki, best_c_t, b_m; break

    if best_ki == -1:
        for ki in range(num_H):
            if active[ki] or y[ki]: continue
            k = hub_idx[ki]
            if sc["risk"][k] > chi: continue
            b_m = -1; best_c_t = 1e9; reachable = False
            for m in [0, 1]:
                if sc["accessibility"][m][i][k]:
                    reachable = True
                    if d["transport"]["time"][m][i][k] < best_c_t:
                        best_c_t = d["transport"]["time"][m][i][k]; b_m = m
            if b_m == -1 and sc["accessibility"][2][i][k]:
                reachable = True; best_c_t = d["transport"]["time"][2][i][k]; b_m = 2
            if not reachable: continue
            y[ki] = True; inventory[ki] = 0.0
            best_ki, best_t, best_m = ki, best_c_t, b_m; break

    if best_ki != -1:
        assignments.append((ii, best_ki, best_m))
        hub_load[best_ki] += D_kg
        if not X[best_ki] and not y[best_ki]:
            y[best_ki] = True; inventory[best_ki] = 0.0
            reactive_opened.append(best_ki)

print(f"\nReactive hubs opened: {reactive_opened}")
print(f"y (reactive flags): {[ki for ki in range(num_H) if y[ki]]}")

net_inv = [inventory[ki] - hub_load[ki] for ki in range(num_H)]
print(f"\nnet_inv after allocation:")
for ki in range(num_H):
    if active[ki] or y[ki]:
        print(f"  H{ki}: inv={inventory[ki]:.0f}  load={hub_load[ki]:.0f}  net={net_inv[ki]:.0f}  {'DEFICIT' if net_inv[ki]<0 else 'surplus'}")

# Origin step
for jj in range(num_J):
    j = ori_idx[jj]
    O = sc["supply"][str(j)]
    best_ki = -1; worst_net = 1e18
    for ki in range(num_H):
        if not active[ki] and not y[ki]: continue
        k = hub_idx[ki]
        if any(sc["accessibility"][m][j][k] for m in range(num_M)):
            if net_inv[ki] < worst_net:
                worst_net = net_inv[ki]; best_ki = ki
    if best_ki == -1:
        for ki in range(num_H):
            if active[ki] or y[ki]: best_ki = ki; break
    if best_ki != -1:
        net_inv[best_ki] += O

print(f"\nnet_inv after origins:")
for ki in range(num_H):
    if active[ki] or y[ki]:
        print(f"  H{ki}: net={net_inv[ki]:.0f}  {'DEFICIT' if net_inv[ki]<0 else 'surplus'}")

surpluses = [(ki, net_inv[ki]) for ki in range(num_H) if (active[ki] or y[ki]) and net_inv[ki] > 1e-6]
deficits  = [(ki, net_inv[ki]) for ki in range(num_H) if (active[ki] or y[ki]) and net_inv[ki] < -1e-6]
print(f"\nSurplus hubs: {surpluses}")
print(f"Deficit hubs: {deficits}")
print(f"\n=> Transshipments WILL be generated: {len(deficits) > 0 and len(surpluses) > 0}")
