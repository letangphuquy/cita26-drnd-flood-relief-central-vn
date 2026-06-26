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

#include "min_cost_flow.hpp"
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
            FlowDetails *flow_out = nullptr,
            bool use_global_balancer = true) {
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

    // Shared transport-mode selectors:
    // 1) Prefer road/water, fallback to air.
    // 2) Return {-1, big_M} if unreachable.
    auto best_mode_time = [&](int from_node, int to_node) -> pair<int, double> {
      int best_mode = -1;
      double best_time = inst.big_M;
      for (int m : {0, 1}) {
        if (sc.acc(m, from_node, to_node) && inst.C_time[m][from_node][to_node] < best_time) {
          best_time = inst.C_time[m][from_node][to_node];
          best_mode = m;
        }
      }
      if (best_mode == -1 && sc.acc(2, from_node, to_node)) {
        best_time = inst.C_time[2][from_node][to_node];
        best_mode = 2;
      }
      return {best_mode, best_time};
    };

    auto best_mode_cost = [&](int from_node, int to_node) -> pair<int, double> {
      int best_mode = -1;
      double best_cost = inst.big_M;
      for (int m : {0, 1}) {
        if (sc.acc(m, from_node, to_node) && inst.C_cost[m][from_node][to_node] < best_cost) {
          best_cost = inst.C_cost[m][from_node][to_node];
          best_mode = m;
        }
      }
      if (best_mode == -1 && sc.acc(2, from_node, to_node)) {
        best_cost = inst.C_cost[2][from_node][to_node];
        best_mode = 2;
      }
      return {best_mode, best_cost};
    };

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

    // ── STEP 3: Demand priority scores (tiebreaker for regret) ──────────
    vector<double> raw_urgency(num_I), raw_isolation(num_I), raw_dist(num_I);
    for (int ii = 0; ii < num_I; ii++) {
      int i = inst.demand_idx[ii];
      double D = sc.demand[i];
      double lam = inst.lambda[ii][si];
      raw_urgency[ii] = lam * D;
      int n_reach = 0;
      double min_t = inst.big_M;
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki]) continue;
        int k = inst.hub_idx[ki];
        bool reachable = false;
        for (int m = 0; m < num_M; m++) {
          if (sc.acc(m, i, k)) { reachable = true; umin(min_t, inst.C_time[m][i][k]); }
        }
        if (reachable) n_reach++;
      }
      raw_isolation[ii] = (n_reach > 0) ? 1.0 / n_reach : 1.0;
      raw_dist[ii]      = (min_t < inst.big_M) ? min_t : 0.0;
    }
    normalise_inplace(raw_urgency);
    normalise_inplace(raw_isolation);
    normalise_inplace(raw_dist);
    vector<double> demand_score(num_I);
    for (int ii = 0; ii < num_I; ii++) {
      demand_score[ii] = ind.W[0] * raw_urgency[ii]
                       + ind.W[3] * raw_isolation[ii]
                       - ind.W[1] * raw_dist[ii]
                       + (ii * 1e-6);
    }

    // ── STEP 4: Regret-based demand allocation (Z2-cost regret) ────────
    // Hub cost for assigning demand ii to hub ki = actual Z2 contribution:
    //   z2_cost[ii][ki] = D * expm1(λ * (τ_k + 2 * min_travel_time[ii][ki]))
    // This is the exact deprivation term accumulated in Step 7, so minimising
    // it directly targets Z2. Regret uses Vogel's approximation:
    //   regret[ii] = z2_cost[ii][2nd_best] − z2_cost[ii][best]
    // Demands with high regret (large cost gap between hubs) are served first.
    // When only 1 hub is reachable, second_z2 = 1e18 → huge regret → instant
    // priority, preventing isolation. R diversifies hub capacities; X diversifies
    // accessibility; demand_score tiebreaks by W[0]*urgency + W[3]*isolation.
    vector<int> z_ik(num_I, -1);
    vector<double> hub_load(num_H, 0.0);

    // min_t[ii][ki]: minimum travel time demand ii → hub ki over ALL modes.
    // Used for Z2 cost computation (mirrors the formula in Step 7).
    vector<vector<double>> min_t(num_I, vector<double>(num_H, inst.big_M));
    for (int ii = 0; ii < num_I; ii++) {
      int i = inst.demand_idx[ii];
      for (int ki = 0; ki < num_H; ki++) {
        int k = inst.hub_idx[ki];
        for (int m = 0; m < num_M; m++)
          if (sc.acc(m, i, k))
            umin(min_t[ii][ki], inst.C_time[m][i][k]);
      }
    }

    // Per-demand deprivation cost (needed by Step 4.5 to track Z2_s after swaps).
    vector<double> depriv_cost(num_I, 0.0);
    // Per-demand mode used (needed by Step 4.5 to maintain act_heli_links).
    vector<int> z_ik_m(num_I, -1);

    vector<bool> assigned(num_I, false);
    int n_assigned = 0;

    while (n_assigned < num_I) {
      int sel_ii = -1, sel_ki = -1, sel_m = -1;
      double best_composite = -1e18;

      for (int ii = 0; ii < num_I; ii++) {
        if (assigned[ii]) continue;
        int i = inst.demand_idx[ii];
        double D   = sc.demand[i];
        double lam = inst.lambda[ii][si];

        double best_z2 = 1e18, second_z2 = 1e18;
        int top_ki = -1, top_m = -1;

        for (int ki = 0; ki < num_H; ki++) {
          if (!active[ki] && !y[ki]) continue;
          int k = inst.hub_idx[ki];
          auto [b_m, bt] = best_mode_time(i, k);
          if (b_m == -1) continue;
          double residual = inventory[ki] - hub_load[ki];
          // Enforce individual hub capacity: skip full planned hubs so demand
          // spills to the next-best hub instead of overloading one hub and
          // forcing MCF to route all supply there from distant origins.
          // Reactive hubs (y[ki]) are always eligible: MCF brings supply in Step 5.
          if (!y[ki] && residual <= 0.0) continue;

          double t_ik  = (min_t[ii][ki] < inst.big_M) ? min_t[ii][ki] : 0.0;
          double omega = sc.hub_process_time[ki] + 2.0 * t_ik;
          double z2    = D * std::expm1(std::min(lam * omega, 20.0));

          if (z2 < best_z2) {
            second_z2 = best_z2;
            best_z2 = z2; top_ki = ki; top_m = b_m;
          } else if (z2 < second_z2) {
            second_z2 = z2;
          }
        }

        if (top_ki == -1) continue;

        // Vogel regret: cost saved by getting best vs 2nd-best hub.
        // When only 1 hub reachable, second_z2 = 1e18 → maximum urgency.
        double regret    = second_z2 - best_z2;
        double composite = regret + 1e-6 * demand_score[ii];

        if (composite > best_composite) {
          best_composite = composite;
          sel_ii = ii; sel_ki = top_ki; sel_m = top_m;
        }
      }

      if (sel_ii == -1) {
        // No demand found a valid hub. Open the first safe inactive hub
        // reachable by any unassigned demand, then retry.
        bool opened = false;
        for (int ii = 0; ii < num_I && !opened; ii++) {
          if (assigned[ii]) continue;
          int i = inst.demand_idx[ii];
          for (int ki = 0; ki < num_H && !opened; ki++) {
            if (active[ki] || y[ki]) continue;
            int k = inst.hub_idx[ki];
            if (sc.risk[k] > inst.chi) continue;
            auto [b_m, bt] = best_mode_time(i, k);
            (void)bt;
            if (b_m == -1) continue;
            y[ki] = true;
            inventory[ki] = 0.0;
            Z1_s += sc.hub_reactive_cost[ki];
            opened = true;
          }
        }
        if (!opened) {
          // Truly infeasible — penalise all remaining demands
          for (int ii = 0; ii < num_I; ii++) {
            if (assigned[ii]) continue;
            int i = inst.demand_idx[ii];
            double D = sc.demand[i];
            double D_kg = inst.gamma * D;
            ind.CV += D_kg;
            Z1_s += inst.big_M;
            umax(Z2_s, inst.big_M);
            assigned[ii] = true;
            n_assigned++;
          }
        }
        continue;
      }

      // Commit: assign sel_ii → sel_ki
      assigned[sel_ii] = true;
      n_assigned++;
      int i = inst.demand_idx[sel_ii];
      double D = sc.demand[i];
      double D_kg = inst.gamma * D;
      z_ik[sel_ii] = sel_ki;
      hub_load[sel_ki] += D_kg;
      act_num_links++;
      if (sel_m == 2) act_heli_links++;

      if (flow_out) {
        flow_out->z_iks[si][sel_ii] = sel_ki;
        flow_out->z_iks_m[si][sel_ii] = sel_m;
      }

      // Reactive hub accounting (forced-active unplanned hub edge case)
      if (!x[sel_ki] && !y[sel_ki]) {
        y[sel_ki] = true;
        inventory[sel_ki] = 0.0;
        Z1_s += sc.hub_reactive_cost[sel_ki];
      }

      // Daganzo CA last-mile cost
      Z1_s += inst.theta[sel_ki][sel_ii][si];

      // Z2 deprivation: Ω = τ_ks + 2 × min travel time over all modes
      int bk = inst.hub_idx[sel_ki];
      double min_t = inst.big_M;
      for (int m = 0; m < num_M; m++)
        if (sc.acc(m, i, bk))
          umin(min_t, inst.C_time[m][i][bk]);
      double omega = sc.hub_process_time[sel_ki] +
                     2.0 * (min_t < inst.big_M ? min_t : 0.0);
      double lam = inst.lambda[sel_ii][si];
      double exp_arg = std::min(lam * omega, 20.0);
      double depriv = D * std::expm1(exp_arg);
      umax(Z2_s, depriv);
      depriv_cost[sel_ii] = depriv;
      z_ik_m[sel_ii] = sel_m;
    } // end regret loop

    // ── STEP 4.5: Z2-preserving Z1 local search ──────────────────────────
    // 1-opt re-assignment: for each demand try relocating to a different
    // already-open hub.  Accept if: the new hub has capacity, the new
    // deprivation ≤ current Z2_s, and delta_theta < 0 (Z1 strictly improves).
    // Skipped for infeasible solutions (CV > 0) — they don't reach the front.
    if (ind.CV < EPS) {
      bool ls_improved = true;
      while (ls_improved) {
        ls_improved = false;
        for (int ii = 0; ii < num_I; ii++) {
          if (z_ik[ii] < 0) continue;
          int i       = inst.demand_idx[ii];
          int cur_ki  = z_ik[ii];
          double D    = sc.demand[i];
          double D_kg = inst.gamma * D;
          double lam  = inst.lambda[ii][si];

          double best_delta = 0.0;   // strict improvement only
          int best_ki_ls = -1, best_m_ls = -1;
          double best_nd = depriv_cost[ii];

          for (int ki = 0; ki < num_H; ki++) {
            if (ki == cur_ki) continue;
            if (!active[ki] && !y[ki]) continue;
            if (inventory[ki] - hub_load[ki] < D_kg - EPS) continue;

            int k = inst.hub_idx[ki];
            auto [b_m, bt_ls] = best_mode_time(i, k);
            (void)bt_ls;
            if (b_m == -1) continue;

            double t_new  = (min_t[ii][ki] < inst.big_M) ? min_t[ii][ki] : 0.0;
            double om_new = sc.hub_process_time[ki] + 2.0 * t_new;
            double nd     = D * std::expm1(std::min(lam * om_new, 20.0));
            if (nd > Z2_s + EPS) continue;   // would worsen deprivation ceiling

            double delta = inst.theta[ki][ii][si] - inst.theta[cur_ki][ii][si];
            if (delta < best_delta) {
              best_delta = delta;
              best_ki_ls = ki; best_m_ls = b_m;
              best_nd    = nd;
            }
          }

          if (best_ki_ls != -1) {
            hub_load[cur_ki]     -= D_kg;
            hub_load[best_ki_ls] += D_kg;
            Z1_s += best_delta;
            if (z_ik_m[ii]  == 2) act_heli_links--;
            if (best_m_ls   == 2) act_heli_links++;
            if (flow_out) {
              flow_out->z_iks[si][ii]   = best_ki_ls;
              flow_out->z_iks_m[si][ii] = best_m_ls;
            }
            depriv_cost[ii] = best_nd;
            z_ik[ii]   = best_ki_ls;
            z_ik_m[ii] = best_m_ls;
            // Z2_s can only decrease — recompute
            Z2_s = *std::max_element(depriv_cost.begin(), depriv_cost.end());
            ls_improved = true;
          }
        }
      }
    } // end Step 4.5

    // ── STEP 4.6: Z2-preserving Z1 swap-LS (2-opt interchange) ──────────
    // Swap the hub assignments of two demands (ii ↔ jj) if:
    //   (a) they are at different hubs,
    //   (b) both can reach the other's hub (mode feasibility),
    //   (c) neither new depriv exceeds the current Z2_s ceiling,
    //   (d) combined delta_theta = (theta_new_ii + theta_new_jj)
    //                            - (theta_old_ii + theta_old_jj) < 0.
    // Capacity is conserved exactly — hubs lose and gain the same kg count
    // only if D_ii == D_jj. For unequal demands we must check capacity too.
    // Steepest-descent: apply the globally best swap per outer iteration.
    if (ind.CV < EPS) {
      bool sw_improved = true;
      while (sw_improved) {
        sw_improved = false;
        double best_delta = 0.0;  // only accept strict improvement
        int best_ii = -1, best_jj = -1;
        int best_m_ii = -1, best_m_jj = -1;
        double best_nd_ii = 0.0, best_nd_jj = 0.0;

        for (int ii = 0; ii < num_I - 1; ii++) {
          if (z_ik[ii] < 0) continue;
          int i_ii   = inst.demand_idx[ii];
          int ki_A   = z_ik[ii];
          double D_ii   = sc.demand[i_ii];
          double Dkg_ii = inst.gamma * D_ii;
          double lam_ii = inst.lambda[ii][si];

          for (int jj = ii + 1; jj < num_I; jj++) {
            if (z_ik[jj] < 0) continue;
            int ki_B = z_ik[jj];
            if (ki_A == ki_B) continue;  // same hub — swap is no-op

            int i_jj   = inst.demand_idx[jj];
            double D_jj   = sc.demand[i_jj];
            double Dkg_jj = inst.gamma * D_jj;
            double lam_jj = inst.lambda[jj][si];

            // Capacity check for unequal demands: after swap, both hubs must fit.
            // Hub A loses Dkg_ii and gains Dkg_jj.
            // Hub B loses Dkg_jj and gains Dkg_ii.
            double resA_post = (inventory[ki_A] - hub_load[ki_A]) + Dkg_ii - Dkg_jj;
            double resB_post = (inventory[ki_B] - hub_load[ki_B]) + Dkg_jj - Dkg_ii;
            if (resA_post < -EPS || resB_post < -EPS) continue;

            // Mode feasibility: ii must reach ki_B, jj must reach ki_A.
            int k_B = inst.hub_idx[ki_B];
            int k_A = inst.hub_idx[ki_A];
            auto [m_ii_new, bt1] = best_mode_time(i_ii, k_B);
            (void)bt1;
            if (m_ii_new == -1) continue;
            auto [m_jj_new, bt2] = best_mode_time(i_jj, k_A);
            (void)bt2;
            if (m_jj_new == -1) continue;

            // Z2 constraint: new depriv for both ≤ current Z2_s.
            double t_ii_B  = (min_t[ii][ki_B] < inst.big_M) ? min_t[ii][ki_B] : 0.0;
            double nd_ii   = D_ii * std::expm1(std::min(lam_ii * (sc.hub_process_time[ki_B] + 2.0 * t_ii_B), 20.0));
            if (nd_ii > Z2_s + EPS) continue;

            double t_jj_A  = (min_t[jj][ki_A] < inst.big_M) ? min_t[jj][ki_A] : 0.0;
            double nd_jj   = D_jj * std::expm1(std::min(lam_jj * (sc.hub_process_time[ki_A] + 2.0 * t_jj_A), 20.0));
            if (nd_jj > Z2_s + EPS) continue;

            // Z1 delta (theta change for both demands).
            double delta = (inst.theta[ki_B][ii][si] - inst.theta[ki_A][ii][si])
                         + (inst.theta[ki_A][jj][si] - inst.theta[ki_B][jj][si]);
            if (delta < best_delta) {
              best_delta  = delta;
              best_ii = ii; best_jj = jj;
              best_m_ii = m_ii_new; best_m_jj = m_jj_new;
              best_nd_ii = nd_ii;   best_nd_jj = nd_jj;
            }
          }
        }

        if (best_ii != -1) {
          int ki_A = z_ik[best_ii], ki_B = z_ik[best_jj];
          double Dkg_ii = inst.gamma * sc.demand[inst.demand_idx[best_ii]];
          double Dkg_jj = inst.gamma * sc.demand[inst.demand_idx[best_jj]];

          hub_load[ki_A] += Dkg_jj - Dkg_ii;  // net change at A
          hub_load[ki_B] += Dkg_ii - Dkg_jj;  // net change at B

          Z1_s += best_delta;
          if (z_ik_m[best_ii] == 2) act_heli_links--;
          if (best_m_ii        == 2) act_heli_links++;
          if (z_ik_m[best_jj] == 2) act_heli_links--;
          if (best_m_jj        == 2) act_heli_links++;
          if (flow_out) {
            flow_out->z_iks[si][best_ii]   = ki_B;
            flow_out->z_iks_m[si][best_ii] = best_m_ii;
            flow_out->z_iks[si][best_jj]   = ki_A;
            flow_out->z_iks_m[si][best_jj] = best_m_jj;
          }
          depriv_cost[best_ii] = best_nd_ii;
          depriv_cost[best_jj] = best_nd_jj;
          z_ik[best_ii]   = ki_B;  z_ik_m[best_ii] = best_m_ii;
          z_ik[best_jj]   = ki_A;  z_ik_m[best_jj] = best_m_jj;
          Z2_s = *std::max_element(depriv_cost.begin(), depriv_cost.end());
          sw_improved = true;
        }
      }
    } // end Step 4.6

    // ── STEP 5+6: Supply balancing (global MCMF or legacy greedy) ─────
    vector<double> net_inv(num_H);
    for (int ki = 0; ki < num_H; ki++)
      net_inv[ki] = inventory[ki] - hub_load[ki];

    if (use_global_balancer) {

      // Precompute best origin->hub and hub->hub movement options.
      vector<vector<double>> o2h_cost(num_J, vector<double>(num_H, inst.big_M));
      vector<vector<int>> o2h_mode(num_J, vector<int>(num_H, -1));
      for (int jj = 0; jj < num_J; jj++) {
        int j = inst.origin_idx[jj];
        for (int ki = 0; ki < num_H; ki++) {
          if (!active[ki] && !y[ki])
            continue;
          int k = inst.hub_idx[ki];
          auto [b_m, b_c] = best_mode_cost(j, k);
          if (b_m != -1) {
            o2h_cost[jj][ki] = b_c;
            o2h_mode[jj][ki] = b_m;
          }
        }
      }

      vector<vector<double>> h2h_cost(num_H, vector<double>(num_H, inst.big_M));
      vector<vector<int>> h2h_mode(num_H, vector<int>(num_H, -1));
      for (int ski = 0; ski < num_H; ski++) {
        if (!active[ski] && !y[ski])
          continue;
        int sk = inst.hub_idx[ski];
        for (int dki = 0; dki < num_H; dki++) {
          if (ski == dki || (!active[dki] && !y[dki]))
            continue;
          int dk = inst.hub_idx[dki];
          auto [b_m, b_c] = best_mode_cost(sk, dk);
          if (b_m != -1) {
            h2h_cost[ski][dki] = inst.alpha * b_c;
            h2h_mode[ski][dki] = b_m;
          }
        }
      }

      int SRC = 0;
      int ORG0 = 1;
      int HUB0 = ORG0 + num_J;
      int SNK = HUB0 + num_H;
      int N = SNK + 1;
      vector<vector<MCFEdge>> g(N);

      auto origin_node = [&](int jj) { return ORG0 + jj; };
      auto hub_node = [&](int ki) { return HUB0 + ki; };

      double total_deficit = 0.0;
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki] && !y[ki])
          continue;
        if (net_inv[ki] > EPS)
          mcf_add_edge(g, SRC, hub_node(ki), net_inv[ki], 0.0);
        else if (net_inv[ki] < -EPS) {
          mcf_add_edge(g, hub_node(ki), SNK, -net_inv[ki], 0.0);
          total_deficit += -net_inv[ki];
        }
      }

      double total_origin_supply = 0.0;
      for (int jj = 0; jj < num_J; jj++) {
        int j = inst.origin_idx[jj];
        double O = sc.supply[j];
        if (O <= EPS)
          continue;
        total_origin_supply += O;
        mcf_add_edge(g, SRC, origin_node(jj), O, 0.0);
        for (int ki = 0; ki < num_H; ki++) {
          if (o2h_mode[jj][ki] == -1)
            continue;
          mcf_add_edge(g, origin_node(jj), hub_node(ki), O, o2h_cost[jj][ki], 1,
                       jj, ki, o2h_mode[jj][ki]);
        }
      }

      double big_cap = total_origin_supply;
      for (int ki = 0; ki < num_H; ki++)
        if (net_inv[ki] > EPS)
          big_cap += net_inv[ki];
      big_cap = std::max(1.0, big_cap);

      for (int ski = 0; ski < num_H; ski++) {
        if (!active[ski] && !y[ski])
          continue;
        for (int dki = 0; dki < num_H; dki++) {
          if (h2h_mode[ski][dki] == -1)
            continue;
          mcf_add_edge(g, hub_node(ski), hub_node(dki), big_cap,
                       h2h_cost[ski][dki], 2, ski, dki, h2h_mode[ski][dki]);
        }
      }

      min_cost_flow(g, SRC, SNK, total_deficit);

      // Fold used transport edges back into objectives, inventory balance and logs.
      vector<double> origin_hub_flow(num_J * num_H, 0.0);
      for (int u = 0; u < N; u++) {
        for (const auto &e : g[u]) {
          if (e.kind == 0)
            continue;
          double used = e.init_cap - e.cap;
          if (used <= EPS)
            continue;

          Z1_s += e.cost * used;
          act_num_links++;
          if (e.mode == 2)
            act_heli_links++;

          if (e.kind == 1) {
            net_inv[e.dst_idx] += used;
            origin_hub_flow[e.src_idx * num_H + e.dst_idx] += used;
          } else if (e.kind == 2) {
            net_inv[e.src_idx] -= used;
            net_inv[e.dst_idx] += used;
            if (flow_out)
              flow_out->f_khms[si].push_back({e.src_idx, e.dst_idx, e.mode, used});
          }
        }
      }

      // Preserve compatibility with single z_jks per origin by storing the
      // dominant destination hub (largest allocated flow).
      if (flow_out) {
        for (int jj = 0; jj < num_J; jj++) {
          int best_ki = -1;
          double best_f = 0.0;
          for (int ki = 0; ki < num_H; ki++) {
            double f = origin_hub_flow[jj * num_H + ki];
            if (f > best_f + EPS) {
              best_f = f;
              best_ki = ki;
            }
          }
          if (best_ki >= 0) {
            flow_out->z_jks[si][jj] = best_ki;
            flow_out->z_jks_m[si][jj] = o2h_mode[jj][best_ki];
          }
        }
      }
    } else {
      // Legacy greedy balancing path: nearest-deficit origin assignment +
      // pairwise surplus->deficit transshipment.
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
          auto [cm, best_c] = best_mode_cost(j, k);
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

      for (int iter = 0; iter < num_H * num_H; iter++) {
        int src_ki = -1, dst_ki = -1;
        double best_pair_score = -1e18;

        for (int ski = 0; ski < num_H; ski++) {
          if ((!active[ski] && !y[ski]) || net_inv[ski] <= EPS)
            continue;
          for (int dki = 0; dki < num_H; dki++) {
            if ((!active[dki] && !y[dki]) || net_inv[dki] >= -EPS)
              continue;
            int sk = inst.hub_idx[ski], dk = inst.hub_idx[dki];
            bool reachable = false;
            for (int m = 0; m < num_M; m++) {
              if (sc.acc(m, sk, dk)) {
                reachable = true;
                break;
              }
            }
            if (!reachable)
              continue;
            double score = net_inv[ski] - net_inv[dki];
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
        auto [cm, best_c] = best_mode_cost(k, h);
        if (cm == -1)
          break;

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

inline void decode_legacy(Individual &ind, const DRNDInstance &inst,
                          FlowDetails *flow_out = nullptr) {
  decode(ind, inst, flow_out, false);
}
