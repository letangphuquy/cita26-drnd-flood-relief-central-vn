// decoder_matheuristic.hpp — Tripartite MCF decoder for PB-NSGA-II
//
// Chromosome interpretation:
//   X[num_H]  : hub open/close (unchanged)
//   R[num_H]  : inventory ratio (unchanged)
//   A[num_I]  : unused (ignored by this decoder)
//   W[0]      : β_raw ∈ [0,1] — mapped to β = exp(8×W[0] - 4) ∈ [0.018, 54.6]
//               β scalarizes Z1 vs Z2: edge cost = θ + β × deprivation
//               β→0 : minimise pure Z1 (logistics)
//               β→∞ : minimise pure Z2 (rescue time)
//   W[1..6]   : unused by this decoder
//
// Architecture:
//   Stage-2 is a single Tripartite Min-Cost Max-Flow solve:
//     SRC → Origins/Inventory → Hubs → Demands → SNK
//   Hub→Demand edges carry scalarized cost (θ + β×depriv)/D_kg.
//   A penalty supply edge (SRC → Demand at big_M cost) guarantees the MCF
//   always achieves total_demand_kg flow; unserved demands are detected from
//   those edges and penalised with BigM.
//   Hub capacity is enforced as a SOFT constraint post-MCF (proportional CV
//   penalty if hub throughput > kappa[ki]), matching the heuristic decoder.
//
// MCFEdge kind codes:
//   0  : internal / structural edge
//   1  : Origin → Hub   (transport cost)
//   2  : Hub → Hub      (transshipment cost, alpha-weighted)
//   3  : Hub → Demand   (θ + β×deprivation scalarized cost)
//   99 : SRC → Demand   (penalty supply — marks unserved demands)
#pragma once

#include "decoder.hpp"

inline void decode_matheuristic(Individual &ind, const DRNDInstance &inst,
                                FlowDetails *flow_out = nullptr) {
  const int num_H = inst.num_H;
  const int num_I = inst.num_I;
  const int num_J = inst.num_J;
  const int num_S = inst.num_S;
  (void)inst.num_M;

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

  const double beta = std::exp(8.0 * std::max(0.0, std::min(1.0, ind.W[0])) - 4.0);

  // ── STEP 1: Decode Stage-1 variables ─────────────────────────────────────
  vector<int>    x(num_H);
  vector<double> q(num_H, 0.0);
  for (int ki = 0; ki < num_H; ki++) {
    x[ki] = ind.X[ki];
    if (x[ki]) q[ki] = ind.R[ki] * inst.kappa[ki];
  }

  double Z1_fixed = 0.0;
  for (int ki = 0; ki < num_H; ki++) {
    if (x[ki]) {
      Z1_fixed += inst.F_hub[ki];
      Z1_fixed += inst.c_hold[ki] * q[ki];
    }
  }

  // ── Per-scenario evaluation ───────────────────────────────────────────────
  for (int si = 0; si < num_S; si++) {
    const Scenario &sc = inst.scenarios[si];
    const double pi_s = sc.prob;

    double Z1_s = Z1_fixed;
    double Z2_s = 0.0;

    // ── STEP 2: Activate planned hubs ─────────────────────────────────────
    vector<bool>   active(num_H, false);
    vector<bool>   y(num_H, false);
    vector<double> inventory(num_H, 0.0);

    int act_num_links = 0;
    int act_heli_links = 0;

    auto best_mode_time = [&](int fn, int tn) -> pair<int, double> {
      int bm = -1; double bt = inst.big_M;
      for (int m : {0, 1})
        if (sc.acc(m, fn, tn) && inst.C_time[m][fn][tn] < bt)
          { bt = inst.C_time[m][fn][tn]; bm = m; }
      if (bm == -1 && sc.acc(2, fn, tn))
        { bt = inst.C_time[2][fn][tn]; bm = 2; }
      return {bm, bt};
    };

    auto best_mode_cost = [&](int fn, int tn) -> pair<int, double> {
      int bm = -1; double bc = inst.big_M;
      for (int m : {0, 1})
        if (sc.acc(m, fn, tn) && inst.C_cost[m][fn][tn] < bc)
          { bc = inst.C_cost[m][fn][tn]; bm = m; }
      if (bm == -1 && sc.acc(2, fn, tn))
        { bc = inst.C_cost[2][fn][tn]; bm = 2; }
      return {bm, bc};
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
      for (int ki = 0; ki < num_H; ki++) if (active[ki]) { any = true; break; }
      if (!any) {
        int bk = 0; double br = 1e9;
        for (int ki = 0; ki < num_H; ki++) {
          int k = inst.hub_idx[ki];
          if (sc.risk[k] < br) { br = sc.risk[k]; bk = ki; }
        }
        active[bk] = true; inventory[bk] = q[bk];
      }
    }

    // Pre-open all safe reactive hubs (0 inventory).
    for (int ki = 0; ki < num_H; ki++) {
      if (!active[ki]) {
        int k = inst.hub_idx[ki];
        if (sc.risk[k] <= inst.chi) { y[ki] = true; inventory[ki] = 0.0; }
      }
    }

    // ── Precompute best travel time per (demand, hub) ──────────────────────
    vector<vector<double>> min_t(num_I, vector<double>(num_H, inst.big_M));
    vector<vector<int>>    min_m(num_I, vector<int>(num_H, -1));
    for (int ii = 0; ii < num_I; ii++) {
      int i = inst.demand_idx[ii];
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki] && !y[ki]) continue;
        int k = inst.hub_idx[ki];
        auto [bm, bt] = best_mode_time(i, k);
        if (bm != -1) { min_t[ii][ki] = bt; min_m[ii][ki] = bm; }
      }
    }

    // ── Build Tripartite MCF graph ─────────────────────────────────────────
    // Nodes: SRC(0) | Origins(1..num_J) | Hubs(num_J+1..num_J+num_H)
    //        | Demands(num_J+num_H+1..num_J+num_H+num_I) | SNK
    int SRC  = 0;
    int ORG0 = 1;
    int HUB0 = ORG0 + num_J;
    int DEM0 = HUB0 + num_H;
    int SNK  = DEM0 + num_I;
    int N    = SNK + 1;
    vector<vector<MCFEdge>> g(N);

    auto origin_node = [&](int jj) { return ORG0 + jj; };
    auto hub_node    = [&](int ki)  { return HUB0 + ki;  };
    auto demand_node = [&](int ii)  { return DEM0 + ii;  };

    // SRC → Hub: pre-positioned inventory (active planned hubs only)
    for (int ki = 0; ki < num_H; ki++) {
      if (!active[ki]) continue;
      if (inventory[ki] > EPS)
        mcf_add_edge(g, SRC, hub_node(ki), inventory[ki], 0.0);
    }

    // SRC → Origin → Hub: supply-chain routing
    double total_origin_supply = 0.0;
    vector<vector<double>> o2h_cost(num_J, vector<double>(num_H, inst.big_M));
    vector<vector<int>>    o2h_mode(num_J, vector<int>(num_H, -1));
    for (int jj = 0; jj < num_J; jj++) {
      int j = inst.origin_idx[jj];
      double O = sc.supply[j];
      if (O <= EPS) continue;
      total_origin_supply += O;
      mcf_add_edge(g, SRC, origin_node(jj), O, 0.0);
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki] && !y[ki]) continue;
        int k = inst.hub_idx[ki];
        auto [bm, bc] = best_mode_cost(j, k);
        if (bm != -1) {
          o2h_cost[jj][ki] = bc;
          o2h_mode[jj][ki] = bm;
          mcf_add_edge(g, origin_node(jj), hub_node(ki), O, bc, 1, jj, ki, bm);
        }
      }
    }

    // Hub → Hub: transshipment
    double big_cap = std::max(1.0, total_origin_supply);
    for (int ski = 0; ski < num_H; ski++) {
      if (!active[ski] && !y[ski]) continue;
      int sk = inst.hub_idx[ski];
      for (int dki = 0; dki < num_H; dki++) {
        if (ski == dki || (!active[dki] && !y[dki])) continue;
        int dk = inst.hub_idx[dki];
        auto [bm, bc] = best_mode_cost(sk, dk);
        if (bm != -1)
          mcf_add_edge(g, hub_node(ski), hub_node(dki), big_cap,
                       inst.alpha * bc, 2, ski, dki, bm);
      }
    }

    // Hub → Demand: scalarized (θ + β×deprivation) cost
    double total_demand_kg = 0.0;
    for (int ii = 0; ii < num_I; ii++) {
      int i = inst.demand_idx[ii];
      double D    = sc.demand[i];
      double D_kg = inst.gamma * D;
      total_demand_kg += D_kg;

      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki] && !y[ki]) continue;
        if (min_m[ii][ki] == -1) continue;

        double tau    = sc.hub_process_time[ki];
        double omega  = tau + 2.0 * (min_t[ii][ki] < inst.big_M ? min_t[ii][ki] : 0.0);
        double lam    = inst.lambda[ii][si];
        double depriv = D * std::expm1(std::min(lam * omega, 20.0));
        double theta_ki  = inst.theta[ki][ii][si];
        double edge_cost = (theta_ki + beta * depriv) / D_kg;

        mcf_add_edge(g, hub_node(ki), demand_node(ii), D_kg, edge_cost, 3, ki, ii, min_m[ii][ki]);
      }

      // Demand → Sink
      mcf_add_edge(g, demand_node(ii), SNK, D_kg, 0.0);

      // Penalty supply: SRC → Demand directly at big_M/D_kg cost.
      // Guarantees MCF achieves total_demand_kg even if real supply is short.
      // Kind=99 flow signals an unserved demand (BigM penalty applied post-MCF).
      mcf_add_edge(g, SRC, demand_node(ii), D_kg,
                   inst.big_M / (D_kg > EPS ? D_kg : 1.0), 99, 0, ii, -1);
    }

    // Solve
    min_cost_flow(g, SRC, SNK, total_demand_kg);

    // ── Extract assignments ────────────────────────────────────────────────
    // Track per-(demand,hub) flow to assign demand to the dominant hub.
    vector<vector<double>> dem_hub_flow(num_I, vector<double>(num_H, 0.0));
    vector<double>         dem_penalty_flow(num_I, 0.0);
    vector<double>         origin_hub_flow(num_J * num_H, 0.0);
    vector<bool>           reactive_charged(num_H, false);
    vector<double>         hub_served_kg(num_H, 0.0);

    for (int u = 0; u < N; u++) {
      for (const auto &e : g[u]) {
        double used = e.init_cap - e.cap;
        if (used <= EPS || e.kind == 0) continue;

        if (e.kind == 1) {
          Z1_s += e.cost * used;
          act_num_links++;
          if (e.mode == 2) act_heli_links++;
          origin_hub_flow[e.src_idx * num_H + e.dst_idx] += used;
        } else if (e.kind == 2) {
          Z1_s += e.cost * used;
          act_num_links++;
          if (e.mode == 2) act_heli_links++;
          if (flow_out)
            flow_out->f_khms[si].push_back({e.src_idx, e.dst_idx, e.mode, used});
        } else if (e.kind == 3) {
          int ki = e.src_idx;
          int ii = e.dst_idx;
          Z1_s += inst.theta[ki][ii][si];
          act_num_links++;
          if (e.mode == 2) act_heli_links++;
          dem_hub_flow[ii][ki] += used;
          hub_served_kg[ki] += used;
          if (!active[ki] && y[ki] && !reactive_charged[ki]) {
            Z1_s += sc.hub_reactive_cost[ki];
            reactive_charged[ki] = true;
          }
        } else if (e.kind == 99) {
          dem_penalty_flow[e.dst_idx] += used;
        }
      }
    }

    // Assign each demand to the hub with the most flow
    vector<int> z_ik(num_I, -1);
    for (int ii = 0; ii < num_I; ii++) {
      int best_ki = -1; double best_f = 0.0;
      for (int ki = 0; ki < num_H; ki++) {
        if (dem_hub_flow[ii][ki] > best_f + EPS) {
          best_f = dem_hub_flow[ii][ki];
          best_ki = ki;
        }
      }
      z_ik[ii] = best_ki;
      if (flow_out && best_ki >= 0) {
        flow_out->z_iks[si][ii] = best_ki;
        flow_out->z_iks_m[si][ii] = min_m[ii][best_ki];
      }
    }

    // Compute Z2 from demand assignments
    for (int ii = 0; ii < num_I; ii++) {
      if (dem_penalty_flow[ii] > EPS || z_ik[ii] == -1) {
        int i = inst.demand_idx[ii];
        double D_kg = inst.gamma * sc.demand[i];
        ind.CV += D_kg;
        Z1_s += inst.big_M;
        umax(Z2_s, inst.big_M);
      } else {
        int ki = z_ik[ii];
        int i  = inst.demand_idx[ii];
        double D = sc.demand[i];
        double mt    = min_t[ii][ki];
        double omega = sc.hub_process_time[ki] + 2.0 * (mt < inst.big_M ? mt : 0.0);
        double lam   = inst.lambda[ii][si];
        double depriv = D * std::expm1(std::min(lam * omega, 20.0));
        umax(Z2_s, depriv);
      }
    }

    // Soft hub capacity constraint: penalise hub throughput > kappa (same as heuristic)
    for (int ki = 0; ki < num_H; ki++) {
      double overflow = hub_served_kg[ki] - inst.kappa[ki];
      if (overflow > EPS) {
        Z1_s += overflow * inst.c_hold[ki] * 10.0;
        ind.CV += overflow;
      }
    }

    // Helicopter fraction constraint
    double max_heli = 0.15 * act_num_links + 0.999;
    if (act_heli_links > max_heli)
      ind.CV += (act_heli_links - max_heli) * 10.0;

    // flow_out: dominant origin→hub assignment
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
