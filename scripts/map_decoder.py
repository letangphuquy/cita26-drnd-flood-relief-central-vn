def decode_exact(sol, inst, si):
    dims = inst["dimensions"]
    num_H, num_I, num_M, num_J = dims["num_H"], dims["num_I"], dims["num_M"], dims["num_J"]
    sc = inst["scenarios"][si]
    hub_idx = inst["nodes"]["hub_indices"]
    dem_idx = inst["nodes"]["demand_indices"]
    ori_idx = inst["nodes"]["origin_indices"]
    coords = inst["nodes"]["coords"]
    X, R, A, W = sol["X"], sol["R"], sol["A"], sol["W"]
    chi = inst["global_params"]["chi"]
    gamma = inst["global_params"]["gamma"]
    
    # Precompute anchor distances
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
        hub_anchor_order.append([d[1] for d in dists])

    # 1. Planned Hubs
    active = [False]*num_H
    y = [False]*num_H
    inventory = [0.0]*num_H
    kappa = inst["hub_params"]["capacity"]
    for ki in range(num_H):
        k = hub_idx[ki]
        q_ki = R[ki] * kappa[str(k)]
        if X[ki] and sc["risk"][k] <= chi:
            active[ki] = True
            y[ki] = True
            inventory[ki] = q_ki

    if not any(active):
        best_ki, best_r = -1, 1e9
        for ki in range(num_H):
            k = hub_idx[ki]
            if sc["risk"][k] < best_r:
                best_r = sc["risk"][k]
                best_ki = ki
        active[best_ki] = True
        y[best_ki] = True
        inventory[best_ki] = R[best_ki] * kappa[str(hub_idx[best_ki])]

    # 2. Demand Scoring
    raw_urgency = [0.0]*num_I
    raw_isolation = [0.0]*num_I
    raw_dist = [0.0]*num_I
    for ii in range(num_I):
        i = dem_idx[ii]
        D = sc["demand"][str(i)]
        lam = inst["lambda"][ii][si]
        raw_urgency[ii] = lam * D

        n_reach = 0
        min_t = 1e9
        for ki in range(num_H):
            if not active[ki]: continue
            k = hub_idx[ki]
            reachable = False
            for m in range(num_M):
                if sc["accessibility"][m][i][k]:
                    reachable = True
                    min_t = min(min_t, inst["transport"]["time"][m][i][k])
            if reachable: n_reach += 1
        raw_isolation[ii] = 1.0/n_reach if n_reach > 0 else 1.0
        raw_dist[ii] = min_t if min_t < 1e9 else 0.0

    def norm(vec):
        v_max = max(vec) if len(vec) > 0 else 0
        if v_max > 0:
            for idx in range(len(vec)): vec[idx] /= v_max
    
    norm(raw_urgency)
    norm(raw_isolation)
    norm(raw_dist)
    
    demand_score = [0.0]*num_I
    for ii in range(num_I):
        demand_score[ii] = W[0]*raw_urgency[ii] + W[3]*raw_isolation[ii] - W[1]*raw_dist[ii] + (ii * 1e-6)

    demand_order = sorted(range(num_I), key=lambda ii: demand_score[ii], reverse=True)

    # 3. Demand Allocation
    K = max(1, int(math.ceil(W[5] * num_H)))
    assignments = []
    hub_load = [0.0]*num_H
    
    for ii in demand_order:
        i = dem_idx[ii]
        D = sc["demand"][str(i)]
        D_kg = gamma * D
        anchor = A[ii] % num_H
        trial = hub_anchor_order[anchor]
        
        best_ki, best_m, best_t = -1, -1, 1e9
        best_hub_score = -1e18
        
        # Pass 1
        for j in range(K):
            ki = trial[j]
            if not active[ki] and not y[ki]: continue
            k = hub_idx[ki]
            b_m, best_c_t = -1, 1e9
            reachable = False
            for m in [0, 1]:
                if sc["accessibility"][m][i][k]:
                    reachable = True
                    if inst["transport"]["time"][m][i][k] < best_c_t:
                        best_c_t = inst["transport"]["time"][m][i][k]
                        b_m = m
            if b_m == -1 and sc["accessibility"][2][i][k]:
                reachable = True
                best_c_t = inst["transport"]["time"][2][i][k]
                b_m = 2
            
            if not reachable: continue
            residual = inventory[ki] - hub_load[ki]
            if residual <= 0.0: continue
            
            score = W[1] * (1.0 / (best_c_t + 1e-9)) + W[2] * residual + W[4] * (1.0 if X[ki] else 0.0)
            if score > best_hub_score:
                best_hub_score = score
                best_ki = ki
                best_t = best_c_t
                best_m = b_m
        
        # Pass 2
        if best_ki == -1:
            for j in range(K, num_H):
                ki = trial[j]
                if not active[ki] and not y[ki]: continue
                k = hub_idx[ki]
                b_m, best_c_t = -1, 1e9
                reachable = False
                for m in [0, 1]:
                    if sc["accessibility"][m][i][k]:
                        reachable = True
                        if inst["transport"]["time"][m][i][k] < best_c_t:
                            best_c_t = inst["transport"]["time"][m][i][k]
                            b_m = m
                if b_m == -1 and sc["accessibility"][2][i][k]:
                    reachable = True
                    best_c_t = inst["transport"]["time"][2][i][k]
                    b_m = 2
                
                if not reachable: continue
                best_ki, best_t, best_m = ki, best_c_t, b_m
                break
        
        # Pass 3: Forced reactive
        if best_ki == -1:
            for ki in range(num_H):
                if active[ki] or y[ki]: continue
                k = hub_idx[ki]
                if sc["risk"][k] > chi: continue
                
                b_m, best_c_t = -1, 1e9
                reachable = False
                for m in [0, 1]:
                    if sc["accessibility"][m][i][k]:
                        reachable = True
                        if inst["transport"]["time"][m][i][k] < best_c_t:
                            best_c_t = inst["transport"]["time"][m][i][k]
                            b_m = m
                if b_m == -1 and sc["accessibility"][2][i][k]:
                    reachable = True
                    best_c_t = inst["transport"]["time"][2][i][k]
                    b_m = 2
                
                if not reachable: continue
                y[ki] = True
                inventory[ki] = (R[ki] if R[ki] > 0 else 0.5) * kappa[str(k)]
                best_ki, best_t, best_m = ki, best_c_t, b_m
                break
        
        if best_ki != -1:
            assignments.append((ii, best_ki, best_m))
            hub_load[best_ki] += D_kg
            if not X[best_ki] and not y[best_ki]: # should be caught above but just in case
                y[best_ki] = True
                inventory[best_ki] = (R[best_ki] if R[best_ki] > 0 else 0.5) * kappa[str(hub_idx[best_ki])]

    # 4. Origins (Supply to Hubs)
    net_inv = [inventory[ki] - hub_load[ki] for ki in range(num_H)]
    for jj in range(num_J):
        j = ori_idx[jj]
        O = sc["supply"][str(j)]
        best_ki, worst_net = -1, 1e18
        for ki in range(num_H):
            if not active[ki] and not y[ki]: continue
            k = hub_idx[ki]
            reachable = any(sc["accessibility"][m][j][k] for m in range(num_M))
            if not reachable: continue
            if net_inv[ki] < worst_net:
                worst_net = net_inv[ki]
                best_ki = ki
        
        if best_ki == -1:
            for ki in range(num_H):
                if active[ki] or y[ki]:
                    best_ki = ki; break
        
        if best_ki != -1:
            net_inv[best_ki] += O
            
    # 5. Transshipments
    transshipments = []
    for _ in range(num_H * 2):
        src_ki, dst_ki = -1, -1
        max_surplus, max_deficit = 1e-6, 1e-6
        for ki in range(num_H):
            if not active[ki] and not y[ki]: continue
            if net_inv[ki] > max_surplus:
                max_surplus = net_inv[ki]
                src_ki = ki
            if -net_inv[ki] > max_deficit:
                max_deficit = -net_inv[ki]
                dst_ki = ki
        if src_ki == -1 or dst_ki == -1: break
        
        k, h = hub_idx[src_ki], hub_idx[dst_ki]
        cm, best_c = -1, 1e9
        for m in [0, 1]:
            if sc["accessibility"][m][k][h] and inst["transport"]["cost"][m][k][h] < best_c:
                best_c = inst["transport"]["cost"][m][k][h]
                cm = m
        if cm == -1 and sc["accessibility"][2][k][h]:
            cm = 2
            
        if cm == -1: break
        
        flow = min(max_surplus, max_deficit)
        net_inv[src_ki] -= flow
        net_inv[dst_ki] += flow
        transshipments.append((src_ki, dst_ki, cm, flow))

    # Determine Reactive Hubs (activated but not planned)
    reactive_hubs = set([ki for ki in range(num_H) if y[ki] and not X[ki]])
    planned_safe = set([ki for ki in range(num_H) if active[ki]])
    
    return {
        "assignments": assignments,
        "transshipments": transshipments,
        "reactive_hubs": reactive_hubs,
        "planned_safe": planned_safe,
        "hub_load": hub_load,
        "inventory": inventory,
        "y": y
    }
