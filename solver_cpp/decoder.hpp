// decoder.hpp — Priority-Based Heuristic Decoder for MO-IHLNDP (v2)
//
// CHANGES FROM v1:
//   - A[ii] is now a rotation OFFSET into the distance-sorted hub list
//     (was: arbitrary preferred hub index, effectively unused)
//   - Tiered hub selection:
//       Pass 1 — first WINDOW_K=3 candidates in rotation, best-scoring
//                among active + reachable + positive residual capacity
//       Pass 2 — remaining candidates, first active + reachable (ignores capacity)
//       W[5] check — proactively open a closer reactive hub if travel time
//                    of best active hub exceeds (1-W[5]) × that time
//   - Demand priority score: all raw components normalised to [0,1] across
//     the demand set; Gaussian noise added for stochastic diversity (Fix A)
//   - Score adds W[3] isolation term (most-constrained-first heuristic)
//   - Hub score adds W[4] planned-hub bonus
//   - hub_order_by_dist pre-computed once before scenario loop
//
// WEIGHT SEMANTICS:
//   W[0]: demand urgency  (λ·D)              — demand sort
//   W[1]: hub speed       (1/τ)              — hub score
//   W[2]: residual capacity                  — hub score
//   W[3]: demand isolation (1/num_reachable) — demand sort
//   W[4]: planned hub preference bonus       — hub score
//   W[5]: reactive eagerness threshold       — proactive reactive check
//
// 7-STEP DECODER (same step numbering as v1):
//   Step 1. Decode x_k, compute q_k = R_k × κ_k; fixed stage-1 costs
//   Step 2. Activate planned hubs for scenario s (risk-safe)
//   Step 3. Compute demand priority scores (normalised + noisy)
//   Step 4. Tiered demand allocation
//   Step 5. Origin assignment (largest-deficit-first)
//   Step 6. Greedy transshipment (surplus→deficit)
//   Step 7. Accumulate expected Z1 and Z2
#pragma once

#include "representation.hpp"

// Stochastic noise magnitude on normalised demand priority scores
static constexpr double DECODER_NOISE_SIGMA = 0.05;
// Pass-1 hub candidate window size
static constexpr int    WINDOW_K            = 3;

// ---------------------------------------------------------------------------
// Normalise a vector to [0,1] in-place; if range≈0 set all to 0.5
// ---------------------------------------------------------------------------
static void normalise_inplace(vector<double> &v) {
  if (v.empty()) return;
  double mn = *std::min_element(all(v));
  double mx = *std::max_element(all(v));
  double rng = mx - mn;
  if (rng < EPS) { std::fill(all(v), 0.5); return; }
  for (auto &x : v) x = (x - mn) / rng;
}

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
  // q_k = R_k × κ_k  (capacity-fraction encoding, fully decoupled from X)
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

  // ── Pre-compute hub order by Euclidean distance for each demand ────────
  // Scenario-independent; built once and reused across all scenarios.
  // hub_order[ii][j] = local hub index of the j-th closest hub to demand ii
  vector<vector<int>> hub_order(num_I, vector<int>(num_H));
  for (int ii = 0; ii < num_I; ii++) {
    int di = inst.demand_idx[ii];
    vector<pair<double, int>> dists;
    dists.reserve(num_H);
    for (int ki = 0; ki < num_H; ki++) {
      int hi = inst.hub_idx[ki];
      double dx = inst.lon[di] - inst.lon[hi];
      double dy = inst.lat[di] - inst.lat[hi];
      dists.push_back({dx * dx + dy * dy, ki});
    }
    std::sort(all(dists));
    for (int j = 0; j < num_H; j++) hub_order[ii][j] = dists[j].second;
  }

  // ── Per-scenario evaluation ────────────────────────────────────────────
  for (int si = 0; si < num_S; si++) {
    const Scenario &sc = inst.scenarios[si];
    const double    pi_s = sc.prob;

    double Z1_s = Z1_fixed;
    double Z2_s = 0.0;

    // ── STEP 2: Activate planned hubs ─────────────────────────────────
    vector<bool>   active(num_H, false);
    vector<bool>   y(num_H, false);
    vector<double> inventory(num_H, 0.0);

    for (int ki = 0; ki < num_H; ki++) {
      int k = inst.hub_idx[ki];
      if (x[ki] && sc.risk[k] <= inst.chi) {
        active[ki]    = true;
        inventory[ki] = q[ki];
      }
    }
    // Guarantee at least one active hub
    {
      bool any = false;
      for (int ki = 0; ki < num_H; ki++) if (active[ki]) { any = true; break; }
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

    // ── STEP 3: Demand priority scores (normalised + stochastic) ──────
    // Raw components
    vector<double> raw_urgency(num_I), raw_isolation(num_I), raw_dist(num_I);
    for (int ii = 0; ii < num_I; ii++) {
      int    i   = inst.demand_idx[ii];
      double D   = sc.demand[i];
      double lam = inst.lambda[ii][si];
      raw_urgency[ii] = lam * D;

      int    n_reach = 0;
      double min_t   = inst.big_M;
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki]) continue;
        int k = inst.hub_idx[ki];
        bool reachable = false;
        for (int m = 0; m < num_M; m++) {
          if (sc.acc(m, i, k)) {
            reachable = true;
            umin(min_t, inst.C_time[m][i][k]);
          }
        }
        if (reachable) n_reach++;
      }
      raw_isolation[ii] = (n_reach > 0) ? 1.0 / n_reach : 1.0;
      raw_dist[ii]      = (min_t < inst.big_M) ? min_t : 0.0;
    }

    // Normalise each component to [0,1]
    normalise_inplace(raw_urgency);
    normalise_inplace(raw_isolation);
    normalise_inplace(raw_dist);

    // Weighted score + Gaussian noise
    vector<double> demand_score(num_I);
    for (int ii = 0; ii < num_I; ii++) {
      demand_score[ii] = ind.W[0] * raw_urgency[ii]
                       + ind.W[3] * raw_isolation[ii]
                       - ind.W[1] * raw_dist[ii]
                       + rand_gauss(DECODER_NOISE_SIGMA);
    }

    // ── STEP 4: Tiered demand allocation ──────────────────────────────
    vector<int>    demand_order(num_I);
    std::iota(all(demand_order), 0);
    std::sort(all(demand_order),
              [&](int a, int b) { return demand_score[a] > demand_score[b]; });

    vector<int>    z_ik(num_I, -1);
    vector<double> hub_load(num_H, 0.0);
    const int      K = std::min(WINDOW_K, num_H);

    for (int ii : demand_order) {
      int    i    = inst.demand_idx[ii];
      double D    = sc.demand[i];
      double D_kg = inst.gamma * D;

      // Build rotation: candidate[j] = hub_order[ii][(A[ii]+j) % |H|]
      int offset = ind.A[ii] % num_H;

      int    best_ki           = -1;
      double best_hub_score    = -1e18;
      double best_travel_time  = inst.big_M;

      // ── Pass 1: first K candidates, best-scoring with positive capacity ──
      for (int j = 0; j < K; j++) {
        int ki = hub_order[ii][(offset + j) % num_H];
        if (!active[ki] && !y[ki]) continue;
        int    k         = inst.hub_idx[ki];
        double best_t    = inst.big_M;
        bool   reachable = false;
        for (int m = 0; m < num_M; m++) {
          if (sc.acc(m, i, k)) { reachable = true; umin(best_t, inst.C_time[m][i][k]); }
        }
        if (!reachable) continue;
        double residual = inventory[ki] - hub_load[ki];
        if (residual <= 0.0) continue; // Pass 1: requires positive residual
        double score = ind.W[1] * (1.0 / (best_t + EPS))
                     + ind.W[2] * residual
                     + ind.W[4] * (x[ki] ? 1.0 : 0.0);
        if (score > best_hub_score) {
          best_hub_score   = score;
          best_ki          = ki;
          best_travel_time = best_t;
        }
      }

      // ── Pass 2: remaining candidates, first active+reachable (ignores capacity) ──
      if (best_ki == -1) {
        for (int j = K; j < num_H; j++) {
          int ki = hub_order[ii][(offset + j) % num_H];
          if (!active[ki] && !y[ki]) continue;
          int    k      = inst.hub_idx[ki];
          double best_t = inst.big_M;
          bool   reachable = false;
          for (int m = 0; m < num_M; m++) {
            if (sc.acc(m, i, k)) { reachable = true; umin(best_t, inst.C_time[m][i][k]); }
          }
          if (!reachable) continue;
          best_ki          = ki;
          best_travel_time = best_t;
          break;
        }
      }

      // ── W[5] proactive reactive check ─────────────────────────────────
      // If best active hub's travel time exceeds (1-W[5])×that time,
      // look for a safe inactive hub that is strictly faster.
      // W[5]≈0: open if ANY faster reactive exists; W[5]≈1: never open proactively.
      if (best_ki != -1 && ind.W[5] < 1.0 - EPS) {
        double threshold_t = (1.0 - ind.W[5]) * best_travel_time;
        int    react_ki    = -1;
        double react_best  = threshold_t; // only improve below threshold

        for (int ki = 0; ki < num_H; ki++) {
          if (active[ki] || y[ki]) continue;
          int k = inst.hub_idx[ki];
          if (sc.risk[k] > inst.chi) continue;
          for (int m = 0; m < num_M; m++) {
            if (sc.acc(m, i, k)) {
              double t = inst.C_time[m][i][k];
              if (t < react_best) { react_best = t; react_ki = ki; }
              break;
            }
          }
        }

        if (react_ki != -1) {
          y[react_ki]         = true;
          inventory[react_ki] = (ind.R[react_ki] > 0 ? ind.R[react_ki] : 0.5)
                                * inst.kappa[react_ki];
          Z1_s               += sc.hub_reactive_cost[react_ki];
          best_ki             = react_ki;
          best_travel_time    = react_best;
        }
      }

      // ── Forced reactive / infeasible ──────────────────────────────────
      if (best_ki == -1) {
        // Try to open any safe inactive hub reachable from i
        for (int ki = 0; ki < num_H; ki++) {
          if (active[ki] || y[ki]) continue;
          int k = inst.hub_idx[ki];
          if (sc.risk[k] > inst.chi) continue;
          bool reachable = false;
          for (int m = 0; m < num_M; m++)
            if (sc.acc(m, i, k)) { reachable = true; break; }
          if (!reachable) continue;
          y[ki]         = true;
          inventory[ki] = (ind.R[ki] > 0 ? ind.R[ki] : 0.5) * inst.kappa[ki];
          Z1_s         += sc.hub_reactive_cost[ki];
          best_ki       = ki;
          double best_t = inst.big_M;
          int    bk     = inst.hub_idx[ki];
          for (int m = 0; m < num_M; m++)
            if (sc.acc(m, i, bk)) umin(best_t, inst.C_time[m][i][bk]);
          best_travel_time = best_t;
          break;
        }
      }

      if (best_ki == -1) {
        // Truly infeasible — BigM penalty
        ind.CV += D_kg;
        Z1_s   += inst.big_M;
        umax(Z2_s, inst.big_M);
      } else {
        z_ik[ii]         = best_ki;
        hub_load[best_ki] += D_kg;

        // Reactive hub cost (if not already accounted for above)
        if (!x[best_ki] && !y[best_ki]) {
          y[best_ki]         = true;
          inventory[best_ki] = (ind.R[best_ki] > 0 ? ind.R[best_ki] : 0.5)
                               * inst.kappa[best_ki];
          Z1_s += sc.hub_reactive_cost[best_ki];
        }

        // Daganzo CA last-mile cost
        Z1_s += inst.theta[best_ki][ii][si];

        // Deprivation: Ω = τ_ks + 2 × min travel time; cap to prevent overflow
        int    bk = inst.hub_idx[best_ki];
        double min_t = inst.big_M;
        for (int m = 0; m < num_M; m++)
          if (sc.acc(m, i, bk)) umin(min_t, inst.C_time[m][i][bk]);
        double omega    = sc.hub_process_time[best_ki]
                        + 2.0 * (min_t < inst.big_M ? min_t : 0.0);
        double lam      = inst.lambda[ii][si];
        double exp_arg  = std::min(lam * omega, 20.0);
        double depriv   = D * std::expm1(exp_arg);
        umax(Z2_s, depriv);
      }
    } // end demand loop

    // ── STEP 5: Origin assignment (largest-deficit-first) ─────────────
    vector<double> net_inv(num_H);
    for (int ki = 0; ki < num_H; ki++)
      net_inv[ki] = inventory[ki] - hub_load[ki];

    for (int jj = 0; jj < num_J; jj++) {
      int    j = inst.origin_idx[jj];
      double O = sc.supply[j];

      int    best_ki  = -1;
      double worst_net = 1e18;
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki] && !y[ki]) continue;
        int  k         = inst.hub_idx[ki];
        bool reachable = false;
        for (int m = 0; m < num_M; m++)
          if (sc.acc(m, j, k)) { reachable = true; break; }
        if (!reachable) continue;
        if (net_inv[ki] < worst_net) { worst_net = net_inv[ki]; best_ki = ki; }
      }
      if (best_ki == -1) {
        for (int ki = 0; ki < num_H; ki++)
          if (active[ki] || y[ki]) { best_ki = ki; break; }
      }
      if (best_ki != -1) {
        int    k      = inst.hub_idx[best_ki];
        double best_c = inst.best_cost(j, k, si);
        Z1_s         += best_c * O;
        net_inv[best_ki] += O;
      }
    }

    // ── STEP 6: Greedy transshipment (surplus → deficit) ──────────────
    for (int iter = 0; iter < num_H * 2; iter++) {
      int    src_ki = -1, dst_ki = -1;
      double max_surplus = EPS, max_deficit = EPS;
      for (int ki = 0; ki < num_H; ki++) {
        if (!active[ki] && !y[ki]) continue;
        if ( net_inv[ki] >  max_surplus) { max_surplus =  net_inv[ki]; src_ki = ki; }
        if (-net_inv[ki] >  max_deficit) { max_deficit = -net_inv[ki]; dst_ki = ki; }
      }
      if (src_ki == -1 || dst_ki == -1) break;
      int    k      = inst.hub_idx[src_ki];
      int    h      = inst.hub_idx[dst_ki];
      double best_c = inst.big_M;
      for (int m = 0; m < num_M; m++)
        if (sc.acc(m, k, h)) umin(best_c, inst.C_cost[m][k][h]);
      if (best_c >= inst.big_M) break;
      double flow = std::min(max_surplus, max_deficit);
      Z1_s           += inst.alpha * best_c * flow;
      net_inv[src_ki] -= flow;
      net_inv[dst_ki] += flow;
    }

    // Residual deficits → CV
    for (int ki = 0; ki < num_H; ki++)
      if (net_inv[ki] < -EPS) ind.CV += -net_inv[ki];

    // ── STEP 7: Accumulate expected objectives ─────────────────────────
    ind.Z1 += pi_s * Z1_s;
    ind.Z2 += pi_s * Z2_s;
  } // end scenario loop
}
