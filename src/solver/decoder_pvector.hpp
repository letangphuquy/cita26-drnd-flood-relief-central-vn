// decoder_pvector.hpp — Permutation-based decoder for PB-NSGA-II
//
// Chromosome interpretation:
//   X[num_H]  : hub open/close (unchanged)
//   R[num_H]  : inventory ratio (unchanged)
//   A[num_I]  : PERMUTATION — A[j] = demand index processed j-th in Step 4
//               (A is a permutation of [0..num_I-1])
//   W[0]      : λ ∈ [0,1] — hub scoring trade-off:
//               score = λ × speed_norm + (1-λ) × residual_norm
//   W[1..6]   : unused by this decoder
//
// Hub Sinkhole prevention: natural spill-over via capacity exhaustion.
// Demands at the front of the permutation fill the fastest hub first;
// later demands spill to alternatives once the fast hub is full.
// λ controls the speed/capacity balance, replacing the 6-D W-vector trap.
//
// Steps 1, 2, 5, 6, 7 are identical to the heuristic decoder.
#pragma once

#include "decoder.hpp"

inline void decode_pvector(Individual &ind, const DRNDInstance &inst,
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

  // ── STEP 1: Decode Stage-1 variables ────────────────────────────────────
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

  const double lam = std::max(0.0, std::min(1.0, ind.W[0]));

  // ── Per-scenario evaluation ──────────────────────────────────────────────
  for (int si = 0; si < num_S; si++) {
    const Scenario &sc = inst.scenarios[si];
    const double pi_s = sc.prob;

    double Z1_s = Z1_fixed;
    double Z2_s = 0.0;

    // ── STEP 2: Activate planned hubs ────────────────────────────────────
    vector<bool> active(num_H, false);
    vector<bool> y(num_H, false);
    vector<double> inventory(num_H, 0.0);

    int act_num_links = 0;
    int act_heli_links = 0;

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
        if (active[ki]) { any = true; break; }
      if (!any) {
        int best_ki = 0;
        double best_r = 1e9;
        for (int ki = 0; ki < num_H; ki++) {
          int k = inst.hub_idx[ki];
          if (sc.risk[k] < best_r) { best_r = sc.risk[k]; best_ki = ki; }
        }
        active[best_ki] = true;
        inventory[best_ki] = q[best_ki];
      }
    }

    // ── Precompute min travel time per (demand, hub) ──────────────────────
    vector<double> t_min_demand(num_I, inst.big_M);
    for (int ii = 0; ii < num_I; ii++) {
      int i = inst.demand_idx[ii];
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki] && !y[ki]) continue;
        int k = inst.hub_idx[ki];
        auto [bm, bt] = best_mode_time(i, k);
        if (bm != -1) umin(t_min_demand[ii], bt);
      }
    }

    // ── STEP 4: Permutation-order demand allocation ───────────────────────
    // A[j] = demand index to process at step j (A is a permutation of [0..num_I-1])
    vector<int> z_ik(num_I, -1);
    vector<double> hub_load(num_H, 0.0);

    for (int j = 0; j < num_I; j++) {
      int ii = ind.A[j] % num_I;  // guard against invalid permutation entries
      int i  = inst.demand_idx[ii];
      double D    = sc.demand[i];
      double D_kg = inst.gamma * D;

      int best_ki = -1;
      double best_score = -1e18;
      int chosen_m = -1;

      // Single scored pass over all active/reactive hubs.
      // No has_global_surplus guard: over-assignment is allowed; MCF (Steps 5+6)
      // will route extra origin supply to cover the deficit. This prevents BigM
      // infeasibility when all hubs fill under high-λ conditions.
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki] && !y[ki]) continue;
        int k = inst.hub_idx[ki];
        auto [b_m, best_t] = best_mode_time(i, k);
        if (b_m == -1) continue;
        double residual = inventory[ki] - hub_load[ki];

        double speed_norm = (t_min_demand[ii] < inst.big_M)
            ? t_min_demand[ii] / (best_t + EPS) : 1.0;
        // residual_norm: 0 when at capacity, <0 when over-assigned (clamped to 0)
        double residual_norm = (inst.kappa[ki] > EPS)
            ? std::max(0.0, residual) / inst.kappa[ki] : 0.0;
        double score = lam * speed_norm + (1.0 - lam) * residual_norm;
        if (score > best_score) {
          best_score = score;
          best_ki = ki;
          chosen_m = b_m;
        }
      }

      // Reactive hub fallback (same as heuristic Pass 3)
      if (best_ki == -1) {
        for (int ki = 0; ki < num_H; ki++) {
          if (active[ki] || y[ki]) continue;
          int k = inst.hub_idx[ki];
          if (sc.risk[k] > inst.chi) continue;
          auto [b_m, best_t] = best_mode_time(i, k);
          (void)best_t;
          if (b_m == -1) continue;
          y[ki] = true;
          inventory[ki] = 0.0;
          Z1_s += sc.hub_reactive_cost[ki];
          best_ki = ki;
          chosen_m = b_m;
          break;
        }
      }

      if (best_ki == -1) {
        ind.CV += D_kg;
        Z1_s += inst.big_M;
        umax(Z2_s, inst.big_M);
      } else {
        z_ik[ii] = best_ki;
        hub_load[best_ki] += D_kg;
        act_num_links++;
        if (chosen_m == 2) act_heli_links++;
        if (flow_out) {
          flow_out->z_iks[si][ii] = best_ki;
          flow_out->z_iks_m[si][ii] = chosen_m;
        }
        if (!x[best_ki] && !y[best_ki]) {
          y[best_ki] = true;
          inventory[best_ki] = 0.0;
          Z1_s += sc.hub_reactive_cost[best_ki];
        }
        Z1_s += inst.theta[best_ki][ii][si];

        int bk = inst.hub_idx[best_ki];
        double min_t = inst.big_M;
        for (int m = 0; m < num_M; m++)
          if (sc.acc(m, i, bk))
            umin(min_t, inst.C_time[m][i][bk]);
        double omega = sc.hub_process_time[best_ki]
                     + 2.0 * (min_t < inst.big_M ? min_t : 0.0);
        double lam_is = inst.lambda[ii][si];
        double depriv  = D * std::expm1(std::min(lam_is * omega, 20.0));
        umax(Z2_s, depriv);
      }
    }

    // ── STEPS 5+6: Supply balancing (MCF) — identical to heuristic decoder ─
    vector<double> net_inv(num_H);
    for (int ki = 0; ki < num_H; ki++)
      net_inv[ki] = inventory[ki] - hub_load[ki];

    vector<vector<double>> o2h_cost(num_J, vector<double>(num_H, inst.big_M));
    vector<vector<int>>    o2h_mode(num_J, vector<int>(num_H, -1));
    for (int jj = 0; jj < num_J; jj++) {
      int j = inst.origin_idx[jj];
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki] && !y[ki]) continue;
        int k = inst.hub_idx[ki];
        auto [b_m, b_c] = best_mode_cost(j, k);
        if (b_m != -1) { o2h_cost[jj][ki] = b_c; o2h_mode[jj][ki] = b_m; }
      }
    }
    vector<vector<double>> h2h_cost(num_H, vector<double>(num_H, inst.big_M));
    vector<vector<int>>    h2h_mode(num_H, vector<int>(num_H, -1));
    for (int ski = 0; ski < num_H; ski++) {
      if (!active[ski] && !y[ski]) continue;
      int sk = inst.hub_idx[ski];
      for (int dki = 0; dki < num_H; dki++) {
        if (ski == dki || (!active[dki] && !y[dki])) continue;
        int dk = inst.hub_idx[dki];
        auto [b_m, b_c] = best_mode_cost(sk, dk);
        if (b_m != -1) { h2h_cost[ski][dki] = inst.alpha * b_c; h2h_mode[ski][dki] = b_m; }
      }
    }

    int SRC = 0, ORG0 = 1, HUB0 = ORG0 + num_J, SNK = HUB0 + num_H, N = SNK + 1;
    vector<vector<MCFEdge>> g(N);
    auto origin_node = [&](int jj) { return ORG0 + jj; };
    auto hub_node    = [&](int ki)  { return HUB0 + ki;  };

    double total_deficit = 0.0;
    for (int ki = 0; ki < num_H; ki++) {
      if (!active[ki] && !y[ki]) continue;
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
      if (O <= EPS) continue;
      total_origin_supply += O;
      mcf_add_edge(g, SRC, origin_node(jj), O, 0.0);
      for (int ki = 0; ki < num_H; ki++) {
        if (o2h_mode[jj][ki] == -1) continue;
        mcf_add_edge(g, origin_node(jj), hub_node(ki), O, o2h_cost[jj][ki], 1, jj, ki, o2h_mode[jj][ki]);
      }
    }
    double big_cap = total_origin_supply;
    for (int ki = 0; ki < num_H; ki++)
      if (net_inv[ki] > EPS) big_cap += net_inv[ki];
    big_cap = std::max(1.0, big_cap);
    for (int ski = 0; ski < num_H; ski++) {
      if (!active[ski] && !y[ski]) continue;
      for (int dki = 0; dki < num_H; dki++) {
        if (h2h_mode[ski][dki] == -1) continue;
        mcf_add_edge(g, hub_node(ski), hub_node(dki), big_cap, h2h_cost[ski][dki], 2, ski, dki, h2h_mode[ski][dki]);
      }
    }
    min_cost_flow(g, SRC, SNK, total_deficit);

    vector<double> origin_hub_flow(num_J * num_H, 0.0);
    for (int u = 0; u < N; u++) {
      for (const auto &e : g[u]) {
        if (e.kind == 0) continue;
        double used = e.init_cap - e.cap;
        if (used <= EPS) continue;
        Z1_s += e.cost * used;
        act_num_links++;
        if (e.mode == 2) act_heli_links++;
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
    if (flow_out) {
      for (int jj = 0; jj < num_J; jj++) {
        int best_ki = -1; double best_f = 0.0;
        for (int ki = 0; ki < num_H; ki++) {
          double f = origin_hub_flow[jj * num_H + ki];
          if (f > best_f + EPS) { best_f = f; best_ki = ki; }
        }
        if (best_ki >= 0) {
          flow_out->z_jks[si][jj] = best_ki;
          flow_out->z_jks_m[si][jj] = o2h_mode[jj][best_ki];
        }
      }
    }

    // ── Constraints & Penalties ──────────────────────────────────────────
    for (int ki = 0; ki < num_H; ki++) {
      if (net_inv[ki] < -EPS) {
        double deficit = -net_inv[ki];
        Z1_s += deficit * inst.c_hold[ki] * 10.0;
        double max_net_inv = inst.kappa[ki] - inventory[ki] + net_inv[ki];
        if (max_net_inv < -EPS) ind.CV += -max_net_inv;
      }
    }
    double max_heli = 0.15 * act_num_links + 0.999;
    if (act_heli_links > max_heli)
      ind.CV += (act_heli_links - max_heli) * 10.0;

    if (flow_out) {
      for (int ki = 0; ki < num_H; ki++) {
        flow_out->y_ks[si][ki] = y[ki];
        flow_out->inventory_held[si][ki] = inventory[ki];
      }
    }

    // ── STEP 7: Accumulate expected objectives ────────────────────────────
    ind.Z1 += pi_s * Z1_s;
    ind.Z2 += pi_s * Z2_s;
  }
}
