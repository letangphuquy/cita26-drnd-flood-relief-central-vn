// decoder.hpp — Priority-Based Heuristic Decoder for MO-IHLNDP (v3)
//
// CHANGES FROM v2:
//   - A[ii] is now the INDEX of the preferred anchor hub for demand ii.
//     Hub trial order = all hubs sorted by ascending distance FROM hub_{A[ii]}.
//     (was: rotation offset into a demand-centric distance-sorted list, which
//     produced an unnatural and hard-to-explain rotation semantics.)
//   - W[5] now controls the Pass-1 window depth:
//       K = max(1, ceil(W[5] * num_H))
//     High W[5] → larger window → more planned hubs tried before reactive
//     fallback. Low W[5]  → smaller window → faster fallback to reactive hubs.
//     (was: proactive reactive check threshold, removed for clarity.)
//   - hub_anchor_order[ki][j] pre-computed once: j-th closest hub to hub ki.
//
// WEIGHT SEMANTICS:
//   W[0]: demand urgency  (λ·D)              — demand sort
//   W[1]: hub speed       (1/τ)              — hub score
//   W[2]: residual capacity                  — hub score
//   W[3]: demand isolation (1/num_reachable) — demand sort
//   W[4]: planned hub preference bonus       — hub score
//   W[5]: Pass-1 window depth (fraction of |H|) — planned-hub conservatism
//
// 7-STEP DECODER:
//   Step 1. Decode x_k, compute q_k = R_k × κ_k; fixed stage-1 costs
//   Step 2. Activate planned hubs for scenario s (risk-safe)
//   Step 3. Compute demand priority scores (normalised + noisy)
//   Step 4. Tiered demand allocation (anchor-based proximity order)
//   Step 5. Origin assignment (largest-deficit-first)
//   Step 6. Greedy transshipment (surplus→deficit)
//   Step 7. Accumulate expected Z1 and Z2
#pragma once

#include "representation.hpp"

// Stochastic noise magnitude on normalised demand priority scores
static constexpr double DECODER_NOISE_SIGMA = 0.05;

// ---------------------------------------------------------------------------
// Normalise a vector to [0,1] in-place; if range≈0 set all to 0.5
// ---------------------------------------------------------------------------
static void normalise_inplace(vector<double> &v) {
  if (v.empty())
    return;
  double mn = *std::min_element(all(v));
  double mx = *std::max_element(all(v));
  double rng = mx - mn;
  if (rng < EPS) {
    std::fill(all(v), 0.5);
    return;
  }
  for (auto &x : v)
    x = (x - mn) / rng;
}

// ---------------------------------------------------------------------------
void decode(Individual &ind, const DRNDInstance &inst,
            FlowDetails *flow_out = nullptr) {
  const int num_H = inst.num_H;
  const int num_I = inst.num_I;
  const int num_J = inst.num_J;
  const int num_S = inst.num_S;
  const int num_M = inst.num_M;

  ind.Z1 = 0.0;
  ind.Z2 = 0.0;
  ind.CV = 0.0;

  if (flow_out) {
    flow_out->z_iks.assign(num_S, vector<int>(num_I, -1));
    flow_out->z_iks_m.assign(num_S, vector<int>(num_I, -1));
    flow_out->z_jks.assign(num_S, vector<int>(num_J, -1));
    flow_out->z_jks_m.assign(num_S, vector<int>(num_J, -1));
    flow_out->f_khms.assign(num_S, vector<TransshipmentFlow>());
    flow_out->y_ks.assign(num_S, vector<bool>(num_H, false));
    flow_out->inventory_held.assign(num_S, vector<double>(num_H, 0.0));
  }

  // ── STEP 1: Decode Stage-1 variables ──────────────────────────────────
  // q_k = R_k × κ_k  (capacity-fraction encoding, fully decoupled from X)
  vector<int> x(num_H);
  vector<double> q(num_H, 0.0);
  for (int ki = 0; ki < num_H; ki++) {
    x[ki] = ind.X[ki];
    if (x[ki])
      q[ki] = ind.R[ki] * inst.kappa[ki];
  }

  double Z1_fixed = 0.0;
  for (int ki = 0; ki < num_H; ki++) {
    if (x[ki]) {
      Z1_fixed += inst.F_hub[ki];
      Z1_fixed += inst.c_hold[ki] * q[ki];
    }
  }

  // ── Pre-compute anchor-based hub order ────────────────────────────────
  // hub_anchor_order[ki][j] = local hub index of the j-th closest hub to hub
  // ki. Scenario-independent; built once.  A[ii] selects the anchor hub ki =
  // A[ii], and the trial order for demand ii is
  // hub_anchor_order[ki][0..num_H-1].
  vector<vector<int>> hub_anchor_order(num_H, vector<int>(num_H));
  for (int ki = 0; ki < num_H; ki++) {
    int hi = inst.hub_idx[ki];
    vector<pair<double, int>> dists;
    dists.reserve(num_H);
    for (int kj = 0; kj < num_H; kj++) {
      int hj = inst.hub_idx[kj];
      double dx = inst.lon[hi] - inst.lon[hj];
      double dy = inst.lat[hi] - inst.lat[hj];
      dists.push_back({dx * dx + dy * dy, kj});
    }
    std::sort(all(dists));
    for (int j = 0; j < num_H; j++)
      hub_anchor_order[ki][j] = dists[j].second;
  }

  // ── Per-scenario evaluation ────────────────────────────────────────────
  for (int si = 0; si < num_S; si++) {
    const Scenario &sc = inst.scenarios[si];
    const double pi_s = sc.prob;

    double Z1_s = Z1_fixed;
    double Z2_s = 0.0;

    // ── STEP 2: Activate planned hubs ─────────────────────────────────
    vector<bool> active(num_H, false);
    vector<bool> y(num_H, false);
    vector<double> inventory(num_H, 0.0);

    int act_num_links = 0;
    int act_heli_links = 0;

    for (int ki = 0; ki < num_H; ki++) {
      int k = inst.hub_idx[ki];
      if (x[ki] && sc.risk[k] <= inst.chi) {
        active[ki] = true;
        inventory[ki] = q[ki];
      }
    }
    // Guarantee at least one active hub
    {
      bool any = false;
      for (int ki = 0; ki < num_H; ki++)
        if (active[ki]) {
          any = true;
          break;
        }
      if (!any) {
        int best_ki = 0;
        double best_r = 1e9;
        for (int ki = 0; ki < num_H; ki++) {
          int k = inst.hub_idx[ki];
          if (sc.risk[k] < best_r) {
            best_r = sc.risk[k];
            best_ki = ki;
          }
        }
        active[best_ki] = true;
        inventory[best_ki] = q[best_ki];
      }
    }

    // ── STEP 3: Demand priority scores (normalised + stochastic) ──────
    // Raw components
    vector<double> raw_urgency(num_I), raw_isolation(num_I), raw_dist(num_I);
    for (int ii = 0; ii < num_I; ii++) {
      int i = inst.demand_idx[ii];
      double D = sc.demand[i];
      double lam = inst.lambda[ii][si];
      raw_urgency[ii] = lam * D;

      int n_reach = 0;
      double min_t = inst.big_M;
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki])
          continue;
        int k = inst.hub_idx[ki];
        bool reachable = false;
        for (int m = 0; m < num_M; m++) {
          if (sc.acc(m, i, k)) {
            reachable = true;
            umin(min_t, inst.C_time[m][i][k]);
          }
        }
        if (reachable)
          n_reach++;
      }
      raw_isolation[ii] = (n_reach > 0) ? 1.0 / n_reach : 1.0;
      raw_dist[ii] = (min_t < inst.big_M) ? min_t : 0.0;
    }

    // Normalise each component to [0,1]
    normalise_inplace(raw_urgency);
    normalise_inplace(raw_isolation);
    normalise_inplace(raw_dist);

    // Weighted score + Gaussian noise
    vector<double> demand_score(num_I);
    for (int ii = 0; ii < num_I; ii++) {
      demand_score[ii] = ind.W[0] * raw_urgency[ii] +
                         ind.W[3] * raw_isolation[ii] -
                         ind.W[1] * raw_dist[ii] + (ii * 1e-6);
    }

    // ── STEP 4: Tiered demand allocation ──────────────────────────────
    vector<int> demand_order(num_I);
    std::iota(all(demand_order), 0);
    std::sort(all(demand_order),
              [&](int a, int b) { return demand_score[a] > demand_score[b]; });

    vector<int> z_ik(num_I, -1);
    vector<double> hub_load(num_H, 0.0);

    // W[5] controls the Pass-1 window depth: how many anchor-proximate hubs
    // are evaluated before falling back to the overflow pass.
    // K = max(1, ceil(W[5] * num_H)).  High W[5] → larger window → more
    // planned-hub candidates tried; low W[5] → reactive fallback sooner.
    const int K = std::max(1, (int)std::ceil(ind.W[5] * num_H));

    for (int ii : demand_order) {
      int i = inst.demand_idx[ii];
      double D = sc.demand[i];
      double D_kg = inst.gamma * D;

      // Trial order for demand ii: hubs sorted by ascending distance from
      // anchor hub A[ii].  The anchor hub itself is first (distance = 0).
      const int anchor = ind.A[ii] % num_H;
      const vector<int> &trial_order = hub_anchor_order[anchor];

      int best_ki = -1;
      double best_hub_score = -1e18;
      double best_travel_time = inst.big_M;
      int chosen_m = -1;

      // ── Pass 1: first K candidates in anchor-proximity order ──────────
      // Selects the best-scoring active+reachable hub with positive residual.
      for (int j = 0; j < K; j++) {
        int ki = trial_order[j];
        if (!active[ki] && !y[ki])
          continue;
        int k = inst.hub_idx[ki];
        double best_t = inst.big_M;
        bool reachable = false;
        int b_m = -1;
        // Priority 1: Non-air modes (Road=0, Water=1)
        for (int m : {0, 1}) {
          if (sc.acc(m, i, k)) {
            reachable = true;
            if (inst.C_time[m][i][k] < best_t) {
              best_t = inst.C_time[m][i][k];
              b_m = m;
            }
          }
        }
        // Priority 2: Air mode (Helicopter=2) as last resort
        if (b_m == -1 && sc.acc(2, i, k)) {
          reachable = true;
          best_t = inst.C_time[2][i][k];
          b_m = 2;
        }
        if (!reachable)
          continue;
        double residual = inventory[ki] - hub_load[ki];
        
        // Pass 1: Traditionally requires positive residual capacity.
        // FIX (trans-shipment awareness): Allow hubs with 0 stock (like reactive hubs)
        // to be considered in Pass 1 if there is surplus available elsewhere in the 
        // network that could be trans-shipped here in Step 6.
        bool has_global_surplus = false;
        for (int kj = 0; kj < num_H; kj++) {
          if ((active[kj] || y[kj]) && (inventory[kj] - hub_load[kj] > EPS)) {
            has_global_surplus = true;
            break;
          }
        }

        if (residual <= 0.0 && !has_global_surplus)
            continue; // No stock here and no surplus elsewhere to trans-ship

        double score = ind.W[1] * (1.0 / (best_t + EPS)) + ind.W[2] * std::max(0.0, residual) +
                       ind.W[4] * (x[ki] ? 1.0 : 0.0);
        if (score > best_hub_score) {
          best_hub_score = score;
          best_ki = ki;
          best_travel_time = best_t;
          chosen_m = b_m;
        }
      }

      // ── Pass 2: remaining candidates, first active+reachable ──────────
      // Ignores residual capacity; may incur a constraint violation.
      if (best_ki == -1) {
        for (int j = K; j < num_H; j++) {
          int ki = trial_order[j];
          if (!active[ki] && !y[ki])
            continue;
          int k = inst.hub_idx[ki];
          double best_t = inst.big_M;
          bool reachable = false;
          int b_m = -1;
          // Priority 1
          for (int m : {0, 1}) {
            if (sc.acc(m, i, k)) {
              reachable = true;
              if (inst.C_time[m][i][k] < best_t) {
                best_t = inst.C_time[m][i][k];
                b_m = m;
              }
            }
          }
          // Priority 2
          if (b_m == -1 && sc.acc(2, i, k)) {
            reachable = true;
            best_t = inst.C_time[2][i][k];
            b_m = 2;
          }
          if (!reachable)
            continue;
          best_ki = ki;
          best_travel_time = best_t;
          chosen_m = b_m;
          break;
        }
      }

      // ── Pass 3: Truly infeasible — open a safe inactive hub as reactive ──
      // Only reached when both Pass 1 and Pass 2 found no active/reactive hub.
      if (best_ki == -1) {
          for (int ki = 0; ki < num_H; ki++) {
            if (active[ki] || y[ki])
              continue;
            int k = inst.hub_idx[ki];
            if (sc.risk[k] > inst.chi)
              continue;

            bool reachable = false;
            int b_m = -1;
            double best_t = inst.big_M;
            for (int m : {0, 1}) {
              if (sc.acc(m, i, k)) {
                reachable = true;
                if (inst.C_time[m][i][k] < best_t) {
                  best_t = inst.C_time[m][i][k];
                  b_m = m;
                }
              }
            }
            if (b_m == -1 && sc.acc(2, i, k)) {
              reachable = true;
              best_t = inst.C_time[2][i][k];
              b_m = 2;
            }
            if (!reachable)
              continue;

            y[ki] = true;
            inventory[ki] = 0.0; // Reactive hubs carry zero pre-positioned stock
            Z1_s += sc.hub_reactive_cost[ki];
            best_ki = ki;
            chosen_m = b_m;
            best_travel_time = best_t;
            break;
          }
      }

      if (best_ki == -1) {
        // Truly infeasible — BigM penalty
        ind.CV += D_kg;
        Z1_s += inst.big_M;
        umax(Z2_s, inst.big_M);

      } else {
        z_ik[ii] = best_ki;
        hub_load[best_ki] += D_kg;
        act_num_links++;
        if (chosen_m == 2)
          act_heli_links++;

        if (flow_out) {
          flow_out->z_iks[si][ii] = best_ki;
          flow_out->z_iks_m[si][ii] = chosen_m;
        }

        // Reactive hub cost (if not already accounted for above)
        // NOTE: Reactive hubs are second-stage decisions; they carry ZERO
        // pre-positioned inventory (q_k = 0). Setting inventory from R[best_ki]
        // here was a bug that (a) inflated reactive-hub inventory filling in
        // outputs and (b) masked all net deficits, suppressing transhipment.
        if (!x[best_ki] && !y[best_ki]) {
          y[best_ki] = true;
          inventory[best_ki] = 0.0; // no pre-positioned stock at reactive hub
          Z1_s += sc.hub_reactive_cost[best_ki];
        }

        // Daganzo CA last-mile cost
        Z1_s += inst.theta[best_ki][ii][si];

        // Deprivation: Ω = τ_ks + 2 × min travel time; cap to prevent overflow
        int bk = inst.hub_idx[best_ki];
        double min_t = inst.big_M;
        for (int m = 0; m < num_M; m++)
          if (sc.acc(m, i, bk))
            umin(min_t, inst.C_time[m][i][bk]);
        double omega = sc.hub_process_time[best_ki] +
                       2.0 * (min_t < inst.big_M ? min_t : 0.0);
        double lam = inst.lambda[ii][si];
        double exp_arg = std::min(lam * omega, 20.0);
        double depriv = D * std::expm1(exp_arg);
        umax(Z2_s, depriv);
      }
    } // end demand loop

    // ── STEP 5: Origin assignment (largest-deficit-first) ─────────────
    vector<double> net_inv(num_H);
    for (int ki = 0; ki < num_H; ki++)
      net_inv[ki] = inventory[ki] - hub_load[ki];

    for (int jj = 0; jj < num_J; jj++) {
      int j = inst.origin_idx[jj];
      double O = sc.supply[j];

      int best_ki = -1;
      double worst_net = 1e18;
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki] && !y[ki])
          continue;
        int k = inst.hub_idx[ki];
        bool reachable = false;
        for (int m = 0; m < num_M; m++)
          if (sc.acc(m, j, k)) {
            reachable = true;
            break;
          }
        if (!reachable)
          continue;
        if (net_inv[ki] < worst_net) {
          worst_net = net_inv[ki];
          best_ki = ki;
        }
      }
      if (best_ki == -1) {
        for (int ki = 0; ki < num_H; ki++)
          if (active[ki] || y[ki]) {
            best_ki = ki;
            break;
          }
      }
      if (best_ki != -1) {
        int k = inst.hub_idx[best_ki];

        // Find best mode among non-air first, then fallback to air if necessary
        int cm = -1;
        double best_c = inst.big_M;
        for (int m : {0, 1}) {
          if (sc.acc(m, j, k)) {
            if (inst.C_cost[m][j][k] < best_c) {
              best_c = inst.C_cost[m][j][k];
              cm = m;
            }
          }
        }
        if (cm == -1 && sc.acc(2, j, k)) {
          best_c = inst.C_cost[2][j][k];
          cm = 2;
        }

        if (cm != -1) {
          Z1_s += best_c * O;
          net_inv[best_ki] += O;
          act_num_links++;
          if (cm == 2)
            act_heli_links++;

          if (flow_out) {
            flow_out->z_jks[si][jj] = best_ki;
            flow_out->z_jks_m[si][jj] = cm;
          }
        }
      }
    }

    // ── STEP 6: Greedy transshipment (surplus → deficit) ──────────────
    // Revised greedy loop: repeatedly pick the best reachable (surplus, deficit) pair.
    for (int iter = 0; iter < num_H * num_H; iter++) {
      int src_ki = -1, dst_ki = -1;
      double best_pair_score = -1e18;

      for (int ski = 0; ski < num_H; ski++) {
        if ((!active[ski] && !y[ski]) || net_inv[ski] <= EPS) continue;
        for (int dki = 0; dki < num_H; dki++) {
          if ((!active[dki] && !y[dki]) || net_inv[dki] >= -EPS) continue;

          // Reachability check
          int sk = inst.hub_idx[ski], dk = inst.hub_idx[dki];
          bool reachable = false;
          for (int m = 0; m < num_M; m++) {
            if (sc.acc(m, sk, dk)) { reachable = true; break; }
          }
          if (!reachable) continue;

          double score = net_inv[ski] - net_inv[dki]; // Prioritize large surplus and deficit
          if (score > best_pair_score) {
            best_pair_score = score;
            src_ki = ski;
            dst_ki = dki;
          }
        }
      }

      if (src_ki == -1 || dst_ki == -1)
        break;

      int k = inst.hub_idx[src_ki];
      int h = inst.hub_idx[dst_ki];

      int cm = -1;
      double best_c = inst.big_M;
      for (int m : {0, 1}) {
        if (sc.acc(m, k, h)) {
          if (inst.C_cost[m][k][h] < best_c) {
            best_c = inst.C_cost[m][k][h];
            cm = m;
          }
        }
      }
      if (cm == -1 && sc.acc(2, k, h)) {
        best_c = inst.C_cost[2][k][h];
        cm = 2;
      }

      if (cm == -1) break; // Should not happen due to pre-check

      double flow = std::min(net_inv[src_ki], -net_inv[dst_ki]);
      Z1_s += inst.alpha * best_c * flow;
      net_inv[src_ki] -= flow;
      net_inv[dst_ki] += flow;
      act_num_links++;
      if (cm == 2)
        act_heli_links++;

      if (flow_out) {
        flow_out->f_khms[si].push_back({src_ki, dst_ki, cm, flow});
      }
    }

    // ── Constraints & Penalties ─────────────────────────────────────────

    // 1. Capacity constraint: total load cannot exceed physical capacity +
    // supply
    // 2. Unmet demand penalty: if load > inventory + supply, we must
    // emergency-purchase
    for (int ki = 0; ki < num_H; ki++) {
      if (net_inv[ki] < -EPS) {
        // net_inv = inventory - load + supply
        // -> deficit = load - (inventory + supply)
        double deficit = -net_inv[ki];

        // Z1 penalty: emergency purchase of deficit at 10x holding cost
        Z1_s += deficit * inst.c_hold[ki] * 10.0;

        // CV: mathematical infeasibility if load strictly exceeds max physical
        // capacity + supply
        double max_possible_inv = inst.kappa[ki];
        double total_in = max_possible_inv; // plus supply, but transshipment
                                            // already moved supply around
        // A stricter, correct way to check physical bounds without re-tracing
        // flow: Did the base load + transshipments exceed kappa + incoming
        // supply? Since net_inv[ki] = inventory[ki] - (load +
        // transshipment_net), the max possible net_inv would be kappa - (load +
        // transshipment_net).
        double max_net_inv = inst.kappa[ki] - inventory[ki] + net_inv[ki];
        if (max_net_inv < -EPS) {
          ind.CV += -max_net_inv;
        }
      }
    }

    // Helicopter links constraint → CV
    // Match MILP relaxation: heli_links <= 0.15 * total + 0.999
    double max_heli = 0.15 * act_num_links + 0.999;
    if (act_heli_links > max_heli) {
      ind.CV += (act_heli_links - max_heli) * 10.0;
    }

    if (flow_out) {
      for (int ki = 0; ki < num_H; ki++) {
        flow_out->y_ks[si][ki] = y[ki];
        flow_out->inventory_held[si][ki] = inventory[ki];
      }
    }

    // ── STEP 7: Accumulate expected objectives ─────────────────────────
    ind.Z1 += pi_s * Z1_s;
    ind.Z2 += pi_s * Z2_s;
  } // end scenario loop
}
