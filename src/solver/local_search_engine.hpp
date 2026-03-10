// local_search_engine.hpp — Local search phase wiring for PB-NSGA/PB-NSMA
#pragma once

#include "local_search.hpp"

inline Individual inventory_two_pass_repair(const Individual &ind,
                                            const DRNDInstance &inst) {
  // Pass 1: trim structural overstock to observed utilisation.
  Individual repaired = ls_inventory_trim(ind, inst);

  // Pass 2: top-up hubs serving high-priority demand mass.
  FlowDetails flow;
  decode(repaired, inst, &flow);

  vector<double> hub_priority(inst.num_H, 0.0);
  for (int si = 0; si < inst.num_S; si++) {
    const Scenario &sc = inst.scenarios[si];
    for (int ii = 0; ii < inst.num_I; ii++) {
      int ki = flow.z_iks[si][ii];
      if (ki < 0)
        continue;
      int i_abs = inst.demand_idx[ii];
      hub_priority[ki] += sc.prob * inst.lambda[ii][si] * sc.demand[i_abs];
    }
  }

  // Top-up a small number of most critical open hubs.
  vector<int> hubs(inst.num_H);
  std::iota(hubs.begin(), hubs.end(), 0);
  std::sort(hubs.begin(), hubs.end(), [&](int a, int b) {
    return hub_priority[a] > hub_priority[b];
  });

  int top = std::max(1, inst.num_H / 3);
  int boosted = 0;
  for (int ki : hubs) {
    if (boosted >= top)
      break;
    if (!repaired.X[ki])
      continue;
    repaired.R[ki] = std::clamp(repaired.R[ki] + 0.08, 0.0, 1.0);
    boosted++;
  }

  decode(repaired, inst);
  return repaired;
}

// Generate LS neighbours from rank-1 individuals using domain operators
// defined in local_search.hpp. The caller handles survivor selection.
inline vector<Individual>
run_local_search_phase(const vector<Individual> &pop, const DRNDInstance &inst,
                       int ls_iters) {
  vector<Individual> ls_children;
  if (ls_iters <= 0)
    return ls_children;

  for (const auto &sol : pop) {
    if (sol.rank != 1)
      continue;
    for (int t = 0; t < ls_iters; t++) {
      Individual nbr = ls_random_operator(sol, inst);
      nbr = inventory_two_pass_repair(nbr, inst);
      if (!sol.constrained_dominates(nbr))
        ls_children.push_back(std::move(nbr));
    }
  }
  return ls_children;
}
