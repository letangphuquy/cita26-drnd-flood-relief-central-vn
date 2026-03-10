// local_search.hpp — Local Refinement Operators for PB-NSGA-II
//
// A catalog of neighbourhood operators that perturb an Individual's genotype
// (X, R, A, W) and re-decode.  Each operator targets a specific decision
// variable and applies a domain-aware, problem-specific move.
//
// USAGE:
//   All operators take (Individual&, DRNDInstance&) and return a NEW
//   Individual (the neighbour).  The caller decides acceptance (e.g.
//   non-domination check, Pareto archive, etc.).
//
// ACTIVATION:
//   These operators are NOT wired into the main loop yet.  They will be
//   integrated in a later phase (PB-NSMA local search, or standalone
//   refinement pass).
//
// OPERATOR CATALOG:
//   LS1. Hub Toggle           — flip one planned hub open/close
//   LS2. Inventory Trim       — reduce R[k] to match actual utilisation
//   LS3. Inventory Perturb    — nudge R[k] toward a smarter fill level
//   LS4. Anchor Reassign      — move one demand node to a better anchor hub
//   LS5. Origin Reroute       — swap origin assignment between two hubs
//   LS6. Weight Gradient Step — shift one W[j] in the direction that
//                               locally improves a scalarised objective
//   LS7. Lateral Flow Nudge   — perturb R to create/remove transshipment
//   LS8. Reactive Hub Promote — promote a frequently-used reactive hub to
//                               planned (flip X[k] = 1, set R[k])
#pragma once

#include "decoder.hpp"
#include <numeric>

// ═══════════════════════════════════════════════════════════════════════════
// LS1. Hub Toggle
// ═══════════════════════════════════════════════════════════════════════════
// Flip one planned hub: if open → close (and zero its inventory); if closed
// → open (with a random R).  Maintains the at-least-one invariant.
// Rationale: directly explores adjacent X-configurations.
// ---------------------------------------------------------------------------
Individual ls_hub_toggle(const Individual &ind, const DRNDInstance &inst) {
  Individual nbr = ind;
  int num_H = inst.num_H;

  // Count currently open hubs
  int n_open = 0;
  for (int k = 0; k < num_H; k++)
    if (nbr.X[k])
      n_open++;

  // Pick a random hub
  int k = (int)rand_int(0, num_H - 1);

  if (nbr.X[k] == 1 && n_open > 1) {
    // Close it
    nbr.X[k] = 0;
    nbr.R[k] = 0.0;
  } else if (nbr.X[k] == 0) {
    // Open it with a moderate inventory
    nbr.X[k] = 1;
    nbr.R[k] = 0.3 + 0.4 * rand01(); // [0.3, 0.7]
  }
  // else: only hub open, don't close — return a copy (no-op)

  decode(nbr, inst);
  return nbr;
}

// ═══════════════════════════════════════════════════════════════════════════
// LS2. Inventory Trim
// ═══════════════════════════════════════════════════════════════════════════
// For each open hub, decode the solution to observe actual utilisation, then
// set R[k] = max(actual_utilisation / kappa_k, small_buffer) so we don't
// waste holding cost on unused inventory.
// Rationale: removes inventory overfitting — the #1 reported issue.
// ---------------------------------------------------------------------------
Individual ls_inventory_trim(const Individual &ind, const DRNDInstance &inst) {
  Individual nbr = ind;
  int num_H = inst.num_H;

  // Decode with flow details to observe per-hub load
  FlowDetails flow;
  decode(nbr, inst, &flow);

  // Compute average utilisation across scenarios
  vector<double> avg_load(num_H, 0.0);
  for (int si = 0; si < inst.num_S; si++) {
    const Scenario &sc = inst.scenarios[si];
    // Reconstruct hub_load from assignments
    vector<double> hub_load(num_H, 0.0);
    for (int ii = 0; ii < inst.num_I; ii++) {
      int ki = flow.z_iks[si][ii];
      if (ki < 0)
        continue;
      int i_abs = inst.demand_idx[ii];
      double D_kg = inst.gamma * sc.demand[i_abs];
      hub_load[ki] += D_kg;
    }
    for (int ki = 0; ki < num_H; ki++)
      avg_load[ki] += sc.prob * hub_load[ki];
  }

  // Set R[k] to match average load + 10% buffer, clamped to [0,1]
  for (int ki = 0; ki < num_H; ki++) {
    if (!nbr.X[ki])
      continue;
    double target = avg_load[ki] / std::max(inst.kappa[ki], 1.0);
    target = target * 1.10; // 10% safety buffer
    nbr.R[ki] = std::clamp(target, 0.01, 1.0);
  }

  decode(nbr, inst);
  return nbr;
}

// ═══════════════════════════════════════════════════════════════════════════
// LS3. Inventory Perturb
// ═══════════════════════════════════════════════════════════════════════════
// Pick one open hub and nudge R[k] by a small random delta ∈ [-0.15, +0.15].
// Lighter than LS2 (single-hub perturbation, no flow decode needed).
// Rationale: fine-tune inventory without full recomputation.
// ---------------------------------------------------------------------------
Individual ls_inventory_perturb(const Individual &ind,
                                const DRNDInstance &inst) {
  Individual nbr = ind;
  int num_H = inst.num_H;

  // Collect open hubs
  vector<int> open;
  for (int k = 0; k < num_H; k++)
    if (nbr.X[k])
      open.push_back(k);
  if (open.empty()) {
    decode(nbr, inst);
    return nbr;
  }

  int ki = open[(int)rand_int(0, (int)open.size() - 1)];
  double delta = (rand01() - 0.5) * 0.30; // [-0.15, +0.15]
  nbr.R[ki] = std::clamp(nbr.R[ki] + delta, 0.0, 1.0);

  decode(nbr, inst);
  return nbr;
}

// ═══════════════════════════════════════════════════════════════════════════
// LS4. Anchor Reassign
// ═══════════════════════════════════════════════════════════════════════════
// Pick one demand node and set A[i] to the hub geographically closest to it
// that is currently open.  This directly influences the decoder's trial order
// for that demand.
// Rationale: decoder's demand allocation is anchor-driven; changing A[i] can
// shift assignments, especially for borderline demands between two hubs.
// ---------------------------------------------------------------------------
Individual ls_anchor_reassign(const Individual &ind,
                              const DRNDInstance &inst) {
  Individual nbr = ind;
  int num_H = inst.num_H;
  int num_I = inst.num_I;

  int ii = (int)rand_int(0, num_I - 1);
  int i_abs = inst.demand_idx[ii];

  // Find the closest OPEN hub to demand ii
  int best_ki = nbr.A[ii]; // default: keep current
  double best_dist = 1e18;
  for (int ki = 0; ki < num_H; ki++) {
    if (!nbr.X[ki])
      continue;
    int k = inst.hub_idx[ki];
    double dx = inst.lon[i_abs] - inst.lon[k];
    double dy = inst.lat[i_abs] - inst.lat[k];
    double d = dx * dx + dy * dy;
    if (d < best_dist) {
      best_dist = d;
      best_ki = ki;
    }
  }
  nbr.A[ii] = best_ki;

  decode(nbr, inst);
  return nbr;
}

// ═══════════════════════════════════════════════════════════════════════════
// LS5. Origin Reroute
// ═══════════════════════════════════════════════════════════════════════════
// Decode to observe which hubs have a surplus vs deficit after origins are
// assigned, then adjust R of the deficit hub upward and surplus hub downward,
// simulating a "re-route" of supply flow.
// Rationale: the greedy origin assignment (Step 5) sends supply to the hub
// with the worst net inventory; but changing R can pre-position stock where
// it's actually needed, reducing transshipment cost.
// ---------------------------------------------------------------------------
Individual ls_origin_reroute(const Individual &ind, const DRNDInstance &inst) {
  Individual nbr = ind;
  int num_H = inst.num_H;

  FlowDetails flow;
  decode(nbr, inst, &flow);

  // Find hub with worst average deficit and hub with best average surplus
  vector<double> avg_net(num_H, 0.0);
  for (int si = 0; si < inst.num_S; si++) {
    const Scenario &sc = inst.scenarios[si];
    vector<double> inv(num_H, 0.0);
    vector<double> load(num_H, 0.0);
    for (int ki = 0; ki < num_H; ki++) {
      if (nbr.X[ki])
        inv[ki] = nbr.R[ki] * inst.kappa[ki];
    }
    for (int ii = 0; ii < inst.num_I; ii++) {
      int ki = flow.z_iks[si][ii];
      if (ki < 0)
        continue;
      int i_abs = inst.demand_idx[ii];
      load[ki] += inst.gamma * sc.demand[i_abs];
    }
    for (int ki = 0; ki < num_H; ki++)
      avg_net[ki] += sc.prob * (inv[ki] - load[ki]);
  }

  int deficit_ki = -1, surplus_ki = -1;
  double worst_def = 0.0, best_sur = 0.0;
  for (int ki = 0; ki < num_H; ki++) {
    if (!nbr.X[ki])
      continue;
    if (avg_net[ki] < worst_def) {
      worst_def = avg_net[ki];
      deficit_ki = ki;
    }
    if (avg_net[ki] > best_sur) {
      best_sur = avg_net[ki];
      surplus_ki = ki;
    }
  }

  // Shift: increase deficit hub R, decrease surplus hub R
  double shift = 0.05 + 0.10 * rand01(); // [0.05, 0.15]
  if (deficit_ki >= 0)
    nbr.R[deficit_ki] = std::clamp(nbr.R[deficit_ki] + shift, 0.0, 1.0);
  if (surplus_ki >= 0)
    nbr.R[surplus_ki] = std::clamp(nbr.R[surplus_ki] - shift, 0.0, 1.0);

  decode(nbr, inst);
  return nbr;
}

// ═══════════════════════════════════════════════════════════════════════════
// LS6. Weight Gradient Step
// ═══════════════════════════════════════════════════════════════════════════
// Finite-difference gradient on one W[j]: evaluate W[j] ± ε and step in the
// direction that improves a scalarised objective  f = w1*Z1 + w2*Z2.
// w1, w2 are passed as arguments (caller can vary trade-off).
// Rationale: W controls heuristic priorities inside the decoder; small
// adjustments in W can improve Z1/Z2 without changing X or R.
// ---------------------------------------------------------------------------
Individual ls_weight_gradient(const Individual &ind, const DRNDInstance &inst,
                              double w1 = 0.5, double w2 = 0.5) {
  int num_W = (int)ind.W.size();
  int j = (int)rand_int(0, num_W - 1);
  double eps = 0.05;

  // Evaluate W[j] + eps
  Individual plus = ind;
  plus.W[j] = std::clamp(ind.W[j] + eps, 0.0, 1.0);
  decode(plus, inst);
  double f_plus = w1 * plus.Z1 + w2 * plus.Z2;

  // Evaluate W[j] - eps
  Individual minus = ind;
  minus.W[j] = std::clamp(ind.W[j] - eps, 0.0, 1.0);
  decode(minus, inst);
  double f_minus = w1 * minus.Z1 + w2 * minus.Z2;

  // Return the better one
  return (f_plus < f_minus) ? plus : minus;
}

// ═══════════════════════════════════════════════════════════════════════════
// LS7. Lateral Flow Nudge
// ═══════════════════════════════════════════════════════════════════════════
// Increase R of a hub that currently receives transshipment inflow (it needs
// more pre-positioned stock to avoid expensive inter-hub transport) and
// decrease R of a hub that exports surplus.
// Rationale: directly targets lateral transshipment cost by learning from the
// current flow pattern.
// ---------------------------------------------------------------------------
Individual ls_lateral_flow_nudge(const Individual &ind,
                                 const DRNDInstance &inst) {
  Individual nbr = ind;
  int num_H = inst.num_H;

  FlowDetails flow;
  decode(nbr, inst, &flow);

  // Aggregate net transshipment flow per hub (positive = net importer)
  vector<double> net_trans(num_H, 0.0);
  for (int si = 0; si < inst.num_S; si++) {
    double pi_s = inst.scenarios[si].prob;
    for (const auto &tf : flow.f_khms[si]) {
      net_trans[tf.dst_ki] += pi_s * tf.flow;
      net_trans[tf.src_ki] -= pi_s * tf.flow;
    }
  }

  // Find biggest importer and biggest exporter among open hubs
  int importer = -1, exporter = -1;
  double max_import = 0.0, max_export = 0.0;
  for (int ki = 0; ki < num_H; ki++) {
    if (!nbr.X[ki])
      continue;
    if (net_trans[ki] > max_import) {
      max_import = net_trans[ki];
      importer = ki;
    }
    if (net_trans[ki] < -max_export) {
      max_export = -net_trans[ki];
      exporter = ki;
    }
  }

  double nudge = 0.05 + 0.10 * rand01(); // [0.05, 0.15]
  if (importer >= 0)
    nbr.R[importer] = std::clamp(nbr.R[importer] + nudge, 0.0, 1.0);
  if (exporter >= 0)
    nbr.R[exporter] = std::clamp(nbr.R[exporter] - nudge, 0.0, 1.0);

  decode(nbr, inst);
  return nbr;
}

// ═══════════════════════════════════════════════════════════════════════════
// LS8. Reactive Hub Promote
// ═══════════════════════════════════════════════════════════════════════════
// If a hub is frequently activated as reactive (y_ks=1) across scenarios,
// it's cheaper to open it as planned (saving reactive setup cost per
// scenario). This operator finds the most-used reactive hub and flips it to
// planned with a moderate R.
// Rationale: the greedy decoder opens reactive hubs on-the-fly; promoting
// them to planned saves repeated F^a costs and allows pre-positioning.
// ---------------------------------------------------------------------------
Individual ls_reactive_promote(const Individual &ind,
                               const DRNDInstance &inst) {
  Individual nbr = ind;
  int num_H = inst.num_H;

  FlowDetails flow;
  decode(nbr, inst, &flow);

  // Count how often each closed hub was activated reactively
  vector<double> reactive_freq(num_H, 0.0);
  for (int si = 0; si < inst.num_S; si++) {
    for (int ki = 0; ki < num_H; ki++) {
      if (!nbr.X[ki] && flow.y_ks[si][ki])
        reactive_freq[ki] += inst.scenarios[si].prob;
    }
  }

  // Find the most frequently activated reactive hub
  int best_ki = -1;
  double best_freq = 0.0;
  for (int ki = 0; ki < num_H; ki++) {
    if (nbr.X[ki])
      continue; // already planned
    if (reactive_freq[ki] > best_freq) {
      best_freq = reactive_freq[ki];
      best_ki = ki;
    }
  }

  // Promote if activated in > 30% of weighted scenarios
  if (best_ki >= 0 && best_freq > 0.30) {
    nbr.X[best_ki] = 1;
    nbr.R[best_ki] = 0.3 + 0.4 * rand01(); // moderate initial fill
  }

  decode(nbr, inst);
  return nbr;
}

// ═══════════════════════════════════════════════════════════════════════════
// Dispatcher: apply a random operator
// ═══════════════════════════════════════════════════════════════════════════
// Selects one LS operator uniformly at random and returns the neighbour.
// Useful for a multi-neighbourhood local search (VNS-style shaking).
// ---------------------------------------------------------------------------
Individual ls_random_operator(const Individual &ind,
                              const DRNDInstance &inst) {
  int op = (int)rand_int(0, 7);
  switch (op) {
  case 0:
    return ls_hub_toggle(ind, inst);
  case 1:
    return ls_inventory_trim(ind, inst);
  case 2:
    return ls_inventory_perturb(ind, inst);
  case 3:
    return ls_anchor_reassign(ind, inst);
  case 4:
    return ls_origin_reroute(ind, inst);
  case 5:
    return ls_weight_gradient(ind, inst);
  case 6:
    return ls_lateral_flow_nudge(ind, inst);
  case 7:
    return ls_reactive_promote(ind, inst);
  default:
    return ind;
  }
}
