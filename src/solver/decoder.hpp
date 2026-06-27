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
//   W[0]: demand urgency (λ·D)                                   — demand sort
//   W[1]: exact deprivation norm depriv_min/depriv_ki           — hub score
//          depriv_ki = D·expm1(min(λ·ω_ki, 20))  ← exact Z2 response surface
//   W[2]: residual capacity (residual_k / κ_k)                  — hub score
//   W[3]: demand isolation (1/num_reachable)                    — demand sort
//   W[4]: planned hub preference bonus                           — hub score
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

  // ── Pre-compute anchor-based hub order ────────────────────────────────
  // hub_anchor_order[ki][j] = local index of the j-th closest hub to hub ki
  // (Euclidean in lat/lon).  A[ii] selects the anchor hub; trial order for
  // demand ii is hub_anchor_order[A[ii] % num_H].
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

    // ── Pre-Step 3: exact deprivation precompute (needed for sort + scoring) ─
    // depriv_min_demand[ii] = min over active hubs of D·expm1(min(λ·ω_ki, 20))
    // This is the unavoidable Z2 contribution of demand ii — U_i in the minimax sense.
    // c_upstream[ki] = cheapest origin→hub replenishment cost (α-scaled) for hub ki.
    vector<double> depriv_min_demand(num_I, inst.big_M);
    for (int ii = 0; ii < num_I; ii++) {
      int i = inst.demand_idx[ii];
      double D   = sc.demand[i];
      double lam = inst.lambda[ii][si];
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki] && !y[ki]) continue;
        int k = inst.hub_idx[ki];
        auto [bm, bt] = best_mode_time(i, k);
        if (bm != -1) {
          double omega_ki  = sc.hub_process_time[ki] + 2.0 * bt;
          double depriv_ki = D * std::expm1(std::min(lam * omega_ki, 20.0));
          umin(depriv_min_demand[ii], depriv_ki);
        }
      }
    }

    // ── STEP 3: Demand priority scores (normalised + stochastic) ──────
    vector<double> raw_urgency(num_I), raw_isolation(num_I), raw_dist(num_I);
    for (int ii = 0; ii < num_I; ii++) {
      int i = inst.demand_idx[ii];
      double D_s = sc.demand[i];
      raw_urgency[ii] = inst.lambda[ii][si] * D_s;  // λ·D urgency (original)

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

    // Weighted score + deterministic index tiebreaker (DECODER_NOISE_SIGMA defined but unused)
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

    for (int ii : demand_order) {
      int i = inst.demand_idx[ii];
      double D   = sc.demand[i];
      double D_kg = inst.gamma * D;
      double lam  = inst.lambda[ii][si];  // hoisted — used in depriv_norm (Pass 1/2) and Z2

      // Anchor hub selects the geographic trial order (T19).
      int anchor = ind.A[ii] % num_H;
      if (anchor < 0) anchor += num_H;
      const int K = std::max(1, (int)std::ceil(ind.W[5] * num_H));
      const auto& trial_order = hub_anchor_order[anchor];

      int best_ki = -1;
      double best_hub_score = -1e18;
      int chosen_m = -1;

      // Lifted once per demand — same answer for every hub in both passes.
      bool has_global_surplus = false;
      for (int kj = 0; kj < num_H; kj++) {
        if ((active[kj] || y[kj]) && (inventory[kj] - hub_load[kj] > EPS)) {
          has_global_surplus = true;
          break;
        }
      }

      // ── Pass 1: K-window around anchor ─────────────────────────────────
      for (int j = 0; j < K; j++) {
        int ki = trial_order[j];
        if (!active[ki] && !y[ki]) continue;
        int k = inst.hub_idx[ki];
        double residual = inventory[ki] - hub_load[ki];
        if (residual <= 0.0 && !has_global_surplus)
          continue;
        auto [b_m, best_t] = best_mode_time(i, k);
        if (b_m == -1) continue;

        double omega_ki   = sc.hub_process_time[ki] + 2.0 * best_t;
        double depriv_ki  = D * std::expm1(std::min(lam * omega_ki, 20.0));
        double depriv_norm = (depriv_min_demand[ii] < inst.big_M)
                           ? depriv_min_demand[ii] / (depriv_ki + EPS) : 1.0;
        double residual_norm = (inst.kappa[ki] > EPS)
                             ? std::max(0.0, residual) / inst.kappa[ki] : 0.0;
        double cong = (inst.kappa[ki] > EPS)
            ? std::exp(ind.W[6] * hub_load[ki] / inst.kappa[ki]) : 1.0;
        double score = ind.W[1] * depriv_norm
                     + ind.W[2] * cong * residual_norm
                     + ind.W[4] * (x[ki] ? 1.0 : 0.0);
        if (score > best_hub_score) {
          best_hub_score = score;
          best_ki = ki;
          chosen_m = b_m;
        }
      }

      // ── Pass 2: remaining hubs outside K-window ─────────────────────────
      if (best_ki == -1) {
        for (int j = K; j < num_H; j++) {
          int ki = trial_order[j];
          if (!active[ki] && !y[ki]) continue;
          int k = inst.hub_idx[ki];
          double residual = inventory[ki] - hub_load[ki];
          if (residual <= 0.0 && !has_global_surplus)
            continue;
          auto [b_m, best_t] = best_mode_time(i, k);
          if (b_m == -1) continue;

          double omega_ki   = sc.hub_process_time[ki] + 2.0 * best_t;
          double depriv_ki  = D * std::expm1(std::min(lam * omega_ki, 20.0));
          double depriv_norm = (depriv_min_demand[ii] < inst.big_M)
                             ? depriv_min_demand[ii] / (depriv_ki + EPS) : 1.0;
          double residual_norm = (inst.kappa[ki] > EPS)
                               ? std::max(0.0, residual) / inst.kappa[ki] : 0.0;
          double cong = (inst.kappa[ki] > EPS)
              ? std::exp(ind.W[6] * hub_load[ki] / inst.kappa[ki]) : 1.0;
          double score = ind.W[1] * depriv_norm
                       + ind.W[2] * cong * residual_norm
                       + ind.W[4] * (x[ki] ? 1.0 : 0.0);
          if (score > best_hub_score) {
            best_hub_score = score;
            best_ki = ki;
            chosen_m = b_m;
          }
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

            auto [b_m, best_t] = best_mode_time(i, k);
            (void)best_t;
            if (b_m == -1)
              continue;

            y[ki] = true;
            inventory[ki] = 0.0; // Reactive hubs carry zero pre-positioned stock
            Z1_s += sc.hub_reactive_cost[ki];
            best_ki = ki;
            chosen_m = b_m;
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
        double depriv = D * std::expm1(std::min(lam * omega, 20.0));  // lam hoisted above
        umax(Z2_s, depriv);
      }
    } // end demand loop

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
