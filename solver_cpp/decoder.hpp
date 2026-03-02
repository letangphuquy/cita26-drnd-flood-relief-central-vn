// decoder.hpp — Priority-Based Heuristic Decoder for MO-IHLNDP
//
// Translates a chromosome (X, R, W) into a full second-stage solution for
// every scenario, then computes Z1 (expected logistics cost) and Z2
// (expected max deprivation cost). Constraint violations are accumulated in CV.
//
// The 7-step decoding procedure:
//   Step 1. Stage-1 instantiation  — decode x_k and q_k
//   Step 2. Reactive hub activation — open y_ks for safe inactive hubs
//   Step 3. Priority scoring        — score each demand node
//   Step 4. Demand allocation       — z_iks via greedy priority assignment
//   Step 5. Origin assignment       — z_jks to hubs with largest deficit
//   Step 6. Greedy trans-shipment   — f_khms to balance flow
//   Step 7. Objective accumulation  — Z1_s, Z2_s then expected values
#pragma once

#include "representation.hpp"

// ---------------------------------------------------------------------------
// Constants / scaling
// ---------------------------------------------------------------------------
static constexpr double LAMBDA0_GLOBAL = 0.8;

// ---------------------------------------------------------------------------
// Decode and evaluate one Individual
// ---------------------------------------------------------------------------
void decode(Individual &ind, const DRNDInstance &inst) {
  const int num_H = inst.num_H;
  const int num_I = inst.num_I;
  const int num_J = inst.num_J;
  const int num_S = inst.num_S;
  const int num_M = inst.num_M;

  ind.Z1 = 0.0;
  ind.Z2 = 0.0;
  ind.CV = 0.0;

  // ── STEP 1: Decode Stage-1 variables ──────────────────────────────────
  // x_k (from X), q_k = R_k * kappa_k * x_k  (satisfies q_k ≤ kappa_k
  // automatically)
  vector<int> x(num_H, 0);
  vector<double> q(num_H, 0.0);
  for (int ki = 0; ki < num_H; ki++) {
    x[ki] = ind.X[ki];
    q[ki] = x[ki] ? ind.R[ki] * inst.kappa[ki] : 0.0;
  }

  // Fixed phase-1 costs (independent of scenario)
  double Z1_fixed = 0.0;
  for (int ki = 0; ki < num_H; ki++) {
    if (x[ki]) {
      Z1_fixed += inst.F_hub[ki];          // hub fixed cost
      Z1_fixed += inst.c_hold[ki] * q[ki]; // holding cost
    }
  }

  // ── Per-scenario evaluation ───────────────────────────────────────────
  for (int si = 0; si < num_S; si++) {
    const Scenario &sc = inst.scenarios[si];
    const double pi_s = sc.prob;

    double Z1_s = Z1_fixed;
    double Z2_s = 0.0;

    // ── STEP 2: Reactive hub activation (y_ks) ──────────────────────
    // A hub is proactive if x_k=1 and its risk r_ks ≤ chi.
    // A hub is reactive if x_k=0 and its risk r_ks ≤ chi.
    // We open ALL safe inactive hubs as reactive candidates first,
    // then at Step 6 we pay their fixed cost only if flow passes through.
    // (We'll track active hubs as a boolean vector)
    vector<bool> active(num_H, false);
    for (int ki = 0; ki < num_H; ki++) {
      int k = inst.hub_idx[ki];
      double r_ks = sc.risk[k];
      if ((x[ki] == 1 || x[ki] == 0) && r_ks <= inst.chi) {
        active[ki] = true; // candidate active hub (proactive or reactive)
      }
    }
    // Ensure at least one hub is active (emergency fallback: force-open safest
    // hub)
    bool any_active = false;
    for (int ki = 0; ki < num_H; ki++)
      if (active[ki]) {
        any_active = true;
        break;
      }
    if (!any_active) {
      // Force the hub with lowest risk
      int best_ki = 0;
      double best_risk = 1e9;
      for (int ki = 0; ki < num_H; ki++) {
        int k = inst.hub_idx[ki];
        if (sc.risk[k] < best_risk) {
          best_risk = sc.risk[k];
          best_ki = ki;
        }
      }
      active[best_ki] = true;
    }

    // Track which hubs actually receive flow (for reactive cost)
    vector<bool> y(num_H, false);    // y_ks
    vector<double> inventory(num_H); // q_k available at start
    for (int ki = 0; ki < num_H; ki++)
      inventory[ki] = q[ki];

    // ── STEP 3: Priority scoring for demand nodes ────────────────────
    // Score_i = W[0] * (lambda_is * D_is) - W[1] * dist_to_nearest_active_hub
    vector<double> demand_score(num_I, 0.0);
    for (int ii = 0; ii < num_I; ii++) {
      int i = inst.demand_idx[ii];
      double D = sc.demand[i];
      double lam = inst.lambda[ii][si];
      // Distance to nearest active hub via any mode
      double min_dist = inst.big_M;
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki])
          continue;
        int k = inst.hub_idx[ki];
        for (int m = 0; m < num_M; m++) {
          if (sc.acc(m, i, k))
            umin(min_dist, inst.C_time[m][i][k]);
        }
      }
      demand_score[ii] = ind.W[0] * (lam * D) -
                         ind.W[1] * (min_dist < inst.big_M ? min_dist : 0.0);
    }

    // ── STEP 4: Demand allocation (z_iks) ────────────────────────────
    // Sort demands descending by score; assign greedily to best feasible hub
    vector<int> demand_order(num_I);
    std::iota(all(demand_order), 0);
    std::sort(all(demand_order),
              [&](int a, int b) { return demand_score[a] > demand_score[b]; });

    vector<int> z_ik(num_I, -1); // z_iks: local hub index assigned to demand ii
    vector<double> hub_load(num_H,
                            0.0); // current load on each hub this scenario

    for (int ii : demand_order) {
      int i = inst.demand_idx[ii];
      double D = sc.demand[i];

      // Score each candidate hub for demand ii
      int best_ki = -1;
      double best_hub_score = -1e18;

      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki])
          continue;
        int k = inst.hub_idx[ki];

        // Must have at least one accessible mode
        bool reachable = false;
        double best_t = inst.big_M;
        for (int m = 0; m < num_M; m++) {
          if (sc.acc(m, i, k)) {
            reachable = true;
            umin(best_t, inst.C_time[m][i][k]);
          }
        }
        if (!reachable)
          continue;

        double residual = inst.kappa[ki] - hub_load[ki];
        // HubScore = W[1]*(1/travel_time) + W[2]*residual_cap
        double hub_score =
            ind.W[1] * (1.0 / (best_t + EPS)) + ind.W[2] * residual;
        if (hub_score > best_hub_score) {
          best_hub_score = hub_score;
          best_ki = ki;
        }
      }

      if (best_ki == -1) {
        // No feasible hub: assign to dummy (big-M penalty)
        ind.CV += D;
        Z1_s += inst.big_M;
        Z2_s = std::max(Z2_s, inst.big_M);
      } else {
        z_ik[ii] = best_ki;
        hub_load[best_ki] += inst.gamma * D; // relief items consumed

        // Theta cost (Daganzo CA last-mile)
        Z1_s += inst.theta[best_ki][ii][si];

        // Mark hub as used (reactive cost will be counted in step 6)
        if (!x[best_ki])
          y[best_ki] = true;

        // Waiting time Omega_is = tau_ks + 2 * min_tau_ikm
        double min_tau_ikm = inst.big_M;
        int k = inst.hub_idx[best_ki];
        for (int m = 0; m < num_M; m++) {
          if (sc.acc(m, i, k))
            umin(min_tau_ikm, inst.C_time[m][i][k]);
        }
        double tau_ks = sc.hub_process_time[best_ki];
        double omega = tau_ks + 2.0 * min_tau_ikm;
        double lam = inst.lambda[ii][si];
        double D_is = sc.demand[i];
        double depriv = D_is * (std::exp(lam * omega) - 1.0);
        umax(Z2_s, depriv); // max deprivation this scenario
      }
    }

    // Add reactive hub setup costs for hubs that are active and not proactive
    for (int ki = 0; ki < num_H; ki++) {
      if (y[ki])
        Z1_s += sc.hub_reactive_cost[ki];
    }

    // ── STEP 5: Origin assignment (z_jks) ────────────────────────────
    // Assign each origin to the hub with the largest supply deficit
    // net_inventory[ki] = q_k - gamma * sum(D_{is} * z_iks)  (so far)
    vector<double> net_inv(num_H);
    for (int ki = 0; ki < num_H; ki++)
      net_inv[ki] = inventory[ki] - hub_load[ki];

    for (int jj = 0; jj < num_J; jj++) {
      int j = inst.origin_idx[jj];
      double O_js = sc.supply[j];

      // Find active hub with max deficit that is reachable from j
      int best_ki = -1;
      double worst_net = 1e18; // most negative = largest deficit
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
        // Assign to any active hub (fallback)
        for (int ki = 0; ki < num_H; ki++) {
          if (active[ki] || y[ki]) {
            best_ki = ki;
            break;
          }
        }
      }

      if (best_ki != -1) {
        int k = inst.hub_idx[best_ki];
        // Cost: best accessible mode from j to k
        double best_cost_jk = inst.best_cost(j, k, si);
        Z1_s += best_cost_jk * O_js;
        net_inv[best_ki] += O_js;
      }
    }

    // ── STEP 6: Greedy trans-shipment (f_khms) ───────────────────────
    // While there are deficit hubs and surplus hubs, route goods from surplus
    // to deficit
    {
      // Identify surplus and deficit hubs
      bool progress = true;
      while (progress) {
        progress = false;
        int src_ki = -1, dst_ki = -1;
        double max_surplus = 0, max_deficit = 0;
        for (int ki = 0; ki < num_H; ki++) {
          if (!active[ki] && !y[ki])
            continue;
          if (net_inv[ki] > max_surplus) {
            max_surplus = net_inv[ki];
            src_ki = ki;
          }
          if (net_inv[ki] < -max_deficit) {
            max_deficit = -net_inv[ki];
            dst_ki = ki;
          }
        }
        if (src_ki == -1 || dst_ki == -1)
          break;
        if (max_surplus < EPS || max_deficit < EPS)
          break;

        int k = inst.hub_idx[src_ki];
        int h = inst.hub_idx[dst_ki];

        // Find best accessible mode for k→h trans-shipment
        double best_c = inst.big_M;
        for (int m = 0; m < num_M; m++) {
          if (sc.acc(m, k, h))
            umin(best_c, inst.C_cost[m][k][h]);
        }
        if (best_c >= inst.big_M)
          break; // no route; stop

        // Ship as much as possible
        double flow = std::min(max_surplus, max_deficit);
        Z1_s += inst.alpha * best_c * flow;
        net_inv[src_ki] -= flow;
        net_inv[dst_ki] += flow;
        progress = true;
      }
    }

    // Residual deficits accumulate as CV
    for (int ki = 0; ki < num_H; ki++) {
      if (net_inv[ki] < -EPS)
        ind.CV += -net_inv[ki];
    }

    // ── STEP 7: Accumulate expected objectives ────────────────────────
    ind.Z1 += pi_s * Z1_s;
    ind.Z2 += pi_s * Z2_s;
  } // end for each scenario
}
