// decoder.hpp — Priority-Based Heuristic Decoder for MO-IHLNDP
//
// KEY DESIGN — q_k encoding (from thoughts-algorithm.txt):
//   q_k = R_k × (max_total_demand_kg / n_open_hubs)
//   where max_total_demand_kg = γ × max_s{ Σ_i D_{is} }
//   This ensures sum(q_k) covers total demand when all hubs stock R_k ≈ 1.
//   The "ratio-of-total-demand" encoding gives direct, interpretable semantics
//   and guarantees feasibility space is nonempty when R_k are reasonably large.
//   kappa_k acts as an upper bound only (for storage space / facility
//   constraint).
//
// UNIT SYSTEM (consistent throughout):
//   Demand  D_{is}  — persons
//   Supply  O_{js}  — kg of relief items
//   Inventory q_k   — kg of relief items (= demand_person × gamma)
//   Hub load        — kg of relief items consumed
//   Capacity kappa  — kg of relief items (upper bound on stored stock)
//
// 7-STEP DECODER:
//   Step 1. Stage-1: decode x_k, compute q_k in kg
//   Step 2. Reactive hub candidates (risk-safe inactive hubs)
//   Step 3. Priority score for demand nodes
//   Step 4. Demand allocation (z_{iks})
//   Step 5. Origin assignment (z_{jks})
//   Step 6. Greedy transshipment (balance hub inventories)
//   Step 7. Accumulate expected Z1 and Z2
#pragma once

#include "representation.hpp"

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

  // ── STEP 1: Decode Stage-1 variables ─────────────────────────────────
  // NEW encoding (R1.2 fix): q_k = R_k × kappa_k
  //   R_k ∈ [0,1] encodes the FRACTION OF HUB CAPACITY to pre-stock.
  //   Fully decoupled from X: the meaning of R_k is independent of which
  //   other hubs are open or closed. Semantics: R_k=1 → stock hub to its
  //   physical limit; R_k=0 → empty hub.
  //   (Previously q_k = R_k × D̂/n_open was coupled to X via n_open.)
  //
  // We also pre-compute D_hat = γ × max_s{Σ D_is} for use in reactive
  // hub inventory assignment below.
  double max_total_demand_kg = 0.0;
  for (int si = 0; si < num_S; si++) {
    double td = 0.0;
    for (int ii = 0; ii < num_I; ii++)
      td += inst.scenarios[si].demand[inst.demand_idx[ii]];
    umax(max_total_demand_kg, inst.gamma * td);
  }

  // x_k and q_k (in kg)
  vector<int> x(num_H);
  vector<double> q(num_H, 0.0);
  for (int ki = 0; ki < num_H; ki++) {
    x[ki] = ind.X[ki];
    if (x[ki]) {
      // q_k = R_k × kappa_k  (decoupled, reviewer-corrected encoding)
      q[ki] = ind.R[ki] * inst.kappa[ki];
      // kappa already acts as the upper bound by definition — no extra cap
      // needed
    }
  }

  // Fixed phase-1 costs (independent of scenario)
  double Z1_fixed = 0.0;
  for (int ki = 0; ki < num_H; ki++) {
    if (x[ki]) {
      Z1_fixed += inst.F_hub[ki];
      Z1_fixed += inst.c_hold[ki] * q[ki]; // holding cost per kg
    }
  }

  // ── Per-scenario evaluation ───────────────────────────────────────────
  for (int si = 0; si < num_S; si++) {
    const Scenario &sc = inst.scenarios[si];
    const double pi_s = sc.prob;

    double Z1_s = Z1_fixed;
    double Z2_s = 0.0;

    // ── STEP 2: Reactive hub activation (y_ks) ──────────────────────
    // A hub is usable in scenario s iff its risk r_ks ≤ χ.
    // Proactive hubs (x_k=1) are open by default; reactive hubs (x_k=0)
    // get activated only if needed to cover demand shortfalls.
    vector<bool> active(num_H, false);
    for (int ki = 0; ki < num_H; ki++) {
      int k = inst.hub_idx[ki];
      if (x[ki] && sc.risk[k] <= inst.chi) {
        active[ki] = true;
      }
    }
    // Ensure at least one hub is active
    {
      bool any_active = false;
      for (int ki = 0; ki < num_H; ki++)
        if (active[ki]) {
          any_active = true;
          break;
        }
      if (!any_active) {
        // Activate cheapest (lowest risk) hub regardless of x_k
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
      }
    }

    // Working inventory per hub (kg): starts at q[ki] for proactive hubs, 0 for
    // reactive
    vector<double> inventory(num_H, 0.0);
    for (int ki = 0; ki < num_H; ki++)
      if (active[ki])
        inventory[ki] = q[ki];

    vector<bool> y(num_H,
                   false); // reactive activation flags (for cost tracking)

    // ── STEP 3: Priority scoring for demand nodes ────────────────────
    // Score_i = W[0] × λ_{is} × D_{is}  -  W[1] × (travel-time to nearest
    // active hub)
    vector<double> demand_score(num_I, 0.0);
    for (int ii = 0; ii < num_I; ii++) {
      int i = inst.demand_idx[ii];
      double D = sc.demand[i];
      double lam = inst.lambda[ii][si];
      double min_t = inst.big_M;
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki])
          continue;
        int k = inst.hub_idx[ki];
        for (int m = 0; m < num_M; m++)
          if (sc.acc(m, i, k))
            umin(min_t, inst.C_time[m][i][k]);
      }
      demand_score[ii] =
          ind.W[0] * (lam * D) - ind.W[1] * (min_t < inst.big_M ? min_t : 0.0);
    }

    // ── STEP 4: Demand allocation (z_{iks}) ──────────────────────────
    vector<int> demand_order(num_I);
    std::iota(all(demand_order), 0);
    std::sort(all(demand_order),
              [&](int a, int b) { return demand_score[a] > demand_score[b]; });

    vector<int> z_ik(num_I, -1);
    vector<double> hub_load(num_H, 0.0); // kg consumed

    for (int ii : demand_order) {
      int i = inst.demand_idx[ii];
      double D = sc.demand[i];
      double D_kg = inst.gamma * D; // persons → kg

      int best_ki = -1;
      double best_hub_score = -1e18;
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki] && !y[ki])
          continue;
        int k = inst.hub_idx[ki];
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
        double residual_kg = inventory[ki] - hub_load[ki];
        double hub_score =
            ind.W[1] * (1.0 / (best_t + EPS)) + ind.W[2] * residual_kg;
        if (hub_score > best_hub_score) {
          best_hub_score = hub_score;
          best_ki = ki;
        }
      }

      // If no active hub reachable: try activating a safe inactive hub (new
      // reactive)
      if (best_ki == -1) {
        for (int ki = 0; ki < num_H; ki++) {
          if (active[ki] || y[ki])
            continue;
          int k = inst.hub_idx[ki];
          if (sc.risk[k] > inst.chi)
            continue;
          bool reachable = false;
          for (int m = 0; m < num_M; m++)
            if (sc.acc(m, i, k)) {
              reachable = true;
              break;
            }
          if (!reachable)
            continue;
          // Activate this hub reactively — q_k = R_k × kappa_k (decoupled)
          y[ki] = true;
          double q_reactive =
              (ind.R[ki] > 0 ? ind.R[ki] : 0.5) * inst.kappa[ki];
          inventory[ki] = q_reactive;

          Z1_s += sc.hub_reactive_cost[ki];
          best_ki = ki;
          break;
        }
      }

      if (best_ki == -1) {
        // Truly infeasible: dummy hub penalty
        ind.CV += D_kg;
        Z1_s += inst.big_M;
        Z2_s = std::max(Z2_s, inst.big_M);
      } else {
        z_ik[ii] = best_ki;
        hub_load[best_ki] += D_kg;

        if (!x[best_ki] && !y[best_ki]) {
          y[best_ki] = true;
          inventory[best_ki] =
              (ind.R[best_ki] > 0 ? ind.R[best_ki] : 0.5) * inst.kappa[best_ki];
          Z1_s += sc.hub_reactive_cost[best_ki];
        }

        // Daganzo CA last-mile cost
        Z1_s += inst.theta[best_ki][ii][si];

        // Deprivation: Omega_is = tau_ks + min(tau_ikm) back
        double min_t = inst.big_M;
        int k = inst.hub_idx[best_ki];
        for (int m = 0; m < num_M; m++)
          if (sc.acc(m, i, k))
            umin(min_t, inst.C_time[m][i][k]);
        double omega = sc.hub_process_time[best_ki] +
                       2.0 * (min_t < inst.big_M ? min_t : 0.0);
        double lam = inst.lambda[ii][si];
        // Deprivation cost = D_is × (exp(λ × ω) − 1)
        // Cap lam*omega to prevent double overflow (exp(710) = inf).
        // exp(20) ≈ 5e8 still represents extreme unmet deprivation adequately.
        double exp_arg = std::min(lam * omega, 20.0);
        double depriv = D * std::expm1(exp_arg);
        umax(Z2_s, depriv);
      }
    }

    // ── STEP 5: Origin assignment (z_{jks}) ──────────────────────────
    vector<double> net_inv(num_H);
    for (int ki = 0; ki < num_H; ki++)
      net_inv[ki] = inventory[ki] - hub_load[ki];

    for (int jj = 0; jj < num_J; jj++) {
      int j = inst.origin_idx[jj];
      double O = sc.supply[j]; // kg of supply at origin j

      // Assign origin to hub with largest deficit that is reachable
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
        // fallback: any active hub
        for (int ki = 0; ki < num_H; ki++)
          if (active[ki] || y[ki]) {
            best_ki = ki;
            break;
          }
      }
      if (best_ki != -1) {
        int k = inst.hub_idx[best_ki];
        double best_c = inst.best_cost(j, k, si);
        Z1_s += best_c * O;
        net_inv[best_ki] += O;
      }
    }

    // ── STEP 6: Greedy transshipment ──────────────────────────────────
    // Iteratively route goods from max-surplus hub to max-deficit hub.
    for (int iter = 0; iter < num_H * 2; iter++) {
      int src_ki = -1, dst_ki = -1;
      double max_surplus = EPS, max_deficit = EPS;
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
      int k = inst.hub_idx[src_ki];
      int h = inst.hub_idx[dst_ki];
      double best_c = inst.big_M;
      for (int m = 0; m < num_M; m++)
        if (sc.acc(m, k, h))
          umin(best_c, inst.C_cost[m][k][h]);
      if (best_c >= inst.big_M)
        break;
      double flow = std::min(max_surplus, max_deficit);
      Z1_s += inst.alpha * best_c * flow;
      net_inv[src_ki] -= flow;
      net_inv[dst_ki] += flow;
    }

    // Residual deficits → constraint violation
    for (int ki = 0; ki < num_H; ki++)
      if (net_inv[ki] < -EPS)
        ind.CV += -net_inv[ki];

    // ── STEP 7: Accumulate expected objectives ────────────────────────
    ind.Z1 += pi_s * Z1_s;
    ind.Z2 += pi_s * Z2_s;
  }
}
