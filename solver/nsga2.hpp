// nsga2.hpp — NSGA-II core for PB-NSGA-II (Priority-Based NSGA-II)
//
// Implements:
//   - Mixed genetic operators (Uniform XO + SBX for continuous; Bit-flip + Poly
//   Mutation)
//   - Fast non-dominated sort (Deb 2002)
//   - Crowding distance
//   - Tournament selection + elitist survival
//   - Constrained domination (feasible > infeasible)
#pragma once

#include "decoder.hpp"

// ── Algorithm parameters (defaults, overridable from main) ──────────────────
struct NSGAConfig {
  int pop_size = 100;
  int num_gen = 200;
  double pc = 0.90;      // crossover probability
  double pm_base = 0.20; // base mutation prob (actual = pm_base / gene_count)
  double sbx_eta = 20.0; // SBX distribution index
  double pm_eta = 20.0;  // polynomial mutation index
  int log_every = 10;    // generations between progress logs
  int seed_iter = 0;     // for set_rolling_seed
  bool use_local_search = false; // true  → PB-NSMA; false → plain NSGA-II
  int ls_iters = 5;              // local search perturbations per generation
};

// ── Constrained comparison (crowded comparison with CV) ─────────────────────
bool constrained_better(const Individual &a, const Individual &b) {
  if (a.rank != b.rank)
    return a.rank < b.rank;
  return a.crowding > b.crowding;
}

// ── SBX crossover for one double value ──────────────────────────────────────
pair<double, double> sbx_gene(double p1, double p2, double eta, double lo = 0.0,
                              double hi = 1.0) {
  if (std::abs(p1 - p2) < EPS)
    return {p1, p2};
  double u = rand01();
  double beta;
  if (u <= 0.5)
    beta = std::pow(2.0 * u, 1.0 / (eta + 1));
  else
    beta = std::pow(1.0 / (2.0 * (1.0 - u)), 1.0 / (eta + 1));
  double c1 = 0.5 * ((p1 + p2) - beta * std::abs(p2 - p1));
  double c2 = 0.5 * ((p1 + p2) + beta * std::abs(p2 - p1));
  c1 = std::clamp(c1, lo, hi);
  c2 = std::clamp(c2, lo, hi);
  return {c1, c2};
}

// ── Polynomial mutation for one double value ─────────────────────────────────
double poly_mutate(double x, double eta, double lo = 0.0, double hi = 1.0) {
  double u = rand01();
  double delta;
  if (u < 0.5) {
    double tmp = std::pow(2.0 * u, 1.0 / (eta + 1));
    delta = tmp - 1.0;
  } else {
    double tmp = std::pow(2.0 * (1.0 - u), 1.0 / (eta + 1));
    delta = 1.0 - tmp;
  }
  return std::clamp(x + delta * (hi - lo), lo, hi);
}

// ── Crossover ────────────────────────────────────────────────────────────────
pair<Individual, Individual>
crossover(const Individual &p1, const Individual &p2, const NSGAConfig &cfg) {
  Individual c1 = p1, c2 = p2;
  int num_H = (int)p1.X.size();
  int num_I = (int)p1.A.size();

  // X segment: uniform crossover
  for (int k = 0; k < num_H; k++) {
    if (rand01() < 0.5) {
      c1.X[k] = p2.X[k];
      c2.X[k] = p1.X[k];
    }
  }
  // R segment: SBX
  for (int k = 0; k < num_H; k++) {
    auto [r1, r2] = sbx_gene(p1.R[k], p2.R[k], cfg.sbx_eta);
    c1.R[k] = r1;
    c2.R[k] = r2;
  }
  // A segment: uniform crossover (swap preferred hub index)
  for (int i = 0; i < num_I; i++) {
    if (rand01() < 0.5) {
      c1.A[i] = p2.A[i];
      c2.A[i] = p1.A[i];
    }
  }
  // W segment: SBX (all weights)
  for (int w = 0; w < (int)p1.W.size(); w++) {
    auto [w1, w2] = sbx_gene(p1.W[w], p2.W[w], cfg.sbx_eta);
    c1.W[w] = w1;
    c2.W[w] = w2;
  }
  // Repair: ensure at least one open hub
  auto repair = [&](Individual &ind) {
    bool any_open = false;
    for (int k = 0; k < num_H; k++)
      if (ind.X[k]) {
        any_open = true;
        break;
      }
    if (!any_open)
      ind.X[(int)rand_int(0, num_H - 1)] = 1;
  };
  repair(c1);
  repair(c2);
  return {c1, c2};
}

// ── Mutation
// ──────────────────────────────────────────────────────────────────
void mutate(Individual &ind, const NSGAConfig &cfg) {
  int num_H = (int)ind.X.size();
  int num_I = (int)ind.A.size();
  int gene_count = num_H + num_H + num_I + (int)ind.W.size(); // X + R + A + W
  double pm = cfg.pm_base / gene_count;

  // X: bit-flip
  for (int k = 0; k < num_H; k++) {
    if (rand01() < pm)
      ind.X[k] ^= 1;
  }
  // Repair
  bool any_open = false;
  for (int k = 0; k < num_H; k++)
    if (ind.X[k]) {
      any_open = true;
      break;
    }
  if (!any_open)
    ind.X[(int)rand_int(0, num_H - 1)] = 1;

  // R: polynomial mutation
  for (int k = 0; k < num_H; k++) {
    if (rand01() < pm)
      ind.R[k] = poly_mutate(ind.R[k], cfg.pm_eta);
  }
  // A: random replacement (reassign to a random hub)
  for (int i = 0; i < num_I; i++) {
    if (rand01() < pm)
      ind.A[i] = (int)rand_int(0, num_H - 1);
  }
  // W: polynomial mutation (all weights)
  for (int w = 0; w < (int)ind.W.size(); w++) {
    if (rand01() < pm)
      ind.W[w] = poly_mutate(ind.W[w], cfg.pm_eta);
  }
}

// ── Fast non-dominated sort
// ─────────────────────────────────────────────────── Returns fronts[0] =
// Pareto rank 1, fronts[1] = rank 2, ...
vector<vector<int>> fast_nondominated_sort(vector<Individual> &pop) {
  int N = (int)pop.size();
  vector<int> n_dom(N, 0);         // how many dominate me
  vector<vector<int>> dom_list(N); // who I dominate

  for (int i = 0; i < N; i++) {
    for (int j = 0; j < N; j++) {
      if (i == j)
        continue;
      if (pop[i].constrained_dominates(pop[j])) {
        dom_list[i].push_back(j);
      } else if (pop[j].constrained_dominates(pop[i])) {
        n_dom[i]++;
      }
    }
  }

  vector<vector<int>> fronts;
  vector<int> current_front;
  for (int i = 0; i < N; i++) {
    if (n_dom[i] == 0) {
      pop[i].rank = 1;
      current_front.push_back(i);
    }
  }
  int rank = 1;
  while (!current_front.empty()) {
    fronts.push_back(current_front);
    vector<int> next_front;
    for (int i : current_front) {
      for (int j : dom_list[i]) {
        if (--n_dom[j] == 0) {
          pop[j].rank = rank + 1;
          next_front.push_back(j);
        }
      }
    }
    current_front = next_front;
    rank++;
  }
  return fronts;
}

// ── Crowding distance
// ─────────────────────────────────────────────────────────
void crowding_distance(vector<Individual> &pop, vector<int> &front) {
  int sz = (int)front.size();
  if (sz == 0)
    return;
  for (int i : front)
    pop[i].crowding = 0.0;

  // Objective 1: Z1
  std::sort(all(front), [&](int a, int b) { return pop[a].Z1 < pop[b].Z1; });
  pop[front[0]].crowding = pop[front[sz - 1]].crowding = 1e18;
  double range1 = pop[front[sz - 1]].Z1 - pop[front[0]].Z1;
  if (range1 > EPS) {
    for (int i = 1; i + 1 < sz; i++) {
      pop[front[i]].crowding +=
          (pop[front[i + 1]].Z1 - pop[front[i - 1]].Z1) / range1;
    }
  }
  // Objective 2: Z2
  std::sort(all(front), [&](int a, int b) { return pop[a].Z2 < pop[b].Z2; });
  pop[front[0]].crowding = pop[front[sz - 1]].crowding = 1e18;
  double range2 = pop[front[sz - 1]].Z2 - pop[front[0]].Z2;
  if (range2 > EPS) {
    for (int i = 1; i + 1 < sz; i++) {
      pop[front[i]].crowding +=
          (pop[front[i + 1]].Z2 - pop[front[i - 1]].Z2) / range2;
    }
  }
}

// ── Binary tournament selection
// ───────────────────────────────────────────────
const Individual &tournament(const vector<Individual> &pop) {
  int a = (int)rand_int(0, (int)pop.size() - 1);
  int b = (int)rand_int(0, (int)pop.size() - 1);
  return constrained_better(pop[a], pop[b]) ? pop[a] : pop[b];
}

// ── Hamming diversity (Fix D) ────────────────────────────────────────────────
// For each individual, compute its minimum Hamming distance in X-space to
// any other individual in the pool. Used as a tiebreaker in elitist selection
// to prefer genotypically isolated solutions. O(N^2 * |H|).
void compute_hamming_diversity(vector<Individual> &pop) {
  int N     = (int)pop.size();
  int num_H = (N > 0) ? (int)pop[0].X.size() : 0;
  for (int i = 0; i < N; i++) {
    int min_h = num_H; // worst case: all bits differ
    for (int j = 0; j < N; j++) {
      if (i == j) continue;
      int h = 0;
      for (int k = 0; k < num_H; k++)
        h += (pop[i].X[k] != pop[j].X[k]);
      if (h < min_h) min_h = h;
    }
    pop[i].hamming_diversity = min_h;
  }
}

// ── Elitist survival selection
// ────────────────────────────────────────────────
void elitist_select(vector<Individual> &combined, int target_size) {
  compute_hamming_diversity(combined); // Fix D: needed before tiebreaker sort
  auto fronts = fast_nondominated_sort(combined);
  vector<Individual> new_pop;
  for (auto &front_idx : fronts) {
    crowding_distance(combined, front_idx);
    if ((int)(new_pop.size() + front_idx.size()) <= target_size) {
      for (int i : front_idx)
        new_pop.push_back(combined[i]);
    } else {
      int remaining = target_size - (int)new_pop.size();
      // Tiebreaker order: rank → crowding distance → Hamming diversity
      std::sort(all(front_idx), [&](int a, int b) {
        const Individual &ia = combined[a], &ib = combined[b];
        if (ia.rank != ib.rank) return ia.rank < ib.rank;
        if (std::abs(ia.crowding - ib.crowding) > 1e-9)
          return ia.crowding > ib.crowding;
        return ia.hamming_diversity > ib.hamming_diversity;
      });
      for (int i = 0; i < remaining; i++)
        new_pop.push_back(combined[front_idx[i]]);
      break;
    }
  }
  combined = std::move(new_pop);
}

// ── Main loop (NSGA-II or PB-NSMA depending on cfg.use_local_search)
// ───────────────────────────────────────────────────────
vector<Individual> run_nsga2(const DRNDInstance &inst, const NSGAConfig &cfg) {
  set_rolling_seed(cfg.seed_iter);
  int POP = cfg.pop_size;
  const char *algo_name = cfg.use_local_search ? "PB-NSMA" : "NSGA-II";

  // Initial population
  vector<Individual> pop;
  pop.reserve(POP);
  cerr << "[" << algo_name << "] Initialising population (N=" << POP
       << ")...\n";
  while ((int)pop.size() < POP) {
    Individual ind = random_individual(inst);
    decode(ind, inst);
    pop.push_back(ind);
  }
  elitist_select(pop, POP);
  cerr << "[" << algo_name << "] Init done. Starting " << cfg.num_gen
       << " generations.\n";

  TimeVar t_start = time_now();

  for (int gen = 1; gen <= cfg.num_gen; gen++) {
    // Generate offspring
    vector<Individual> offspring;
    offspring.reserve(POP);
    while ((int)offspring.size() < POP) {
      const Individual &p1 = tournament(pop);
      const Individual &p2 = tournament(pop);
      if (rand01() < cfg.pc) {
        auto [c1, c2] = crossover(p1, p2, cfg);
        if (rand01() < cfg.pm_base)
          mutate(c1, cfg);
        if (rand01() < cfg.pm_base)
          mutate(c2, cfg);
        decode(c1, inst);
        decode(c2, inst);
        offspring.push_back(c1);
        offspring.push_back(c2);
      } else {
        Individual c1 = p1, c2 = p2;
        if (rand01() < cfg.pm_base)
          mutate(c1, cfg);
        if (rand01() < cfg.pm_base)
          mutate(c2, cfg);
        decode(c1, inst);
        decode(c2, inst);
        offspring.push_back(c1);
        offspring.push_back(c2);
      }
    }

    // Combine and select
    for (auto &o : offspring)
      pop.push_back(o);
    elitist_select(pop, POP);

    // ── NSMA-style Local Search (active only when use_local_search = true) ──
    // Perturb each Pareto-front (rank-1) solution with n_ls random moves;
    // accept the neighbour if it is not dominated by the original (Pareto-
    // improving). Accepted neighbours are added and the population is
    // re-pruned to maintain size POP.
    if (cfg.use_local_search) {
      vector<Individual> ls_children;
      for (auto &sol : pop) {
        if (sol.rank != 1)
          continue;
        for (int t = 0; t < cfg.ls_iters; t++) {
          Individual nbr = sol;
          int num_H = (int)nbr.X.size();
          int num_I = (int)nbr.A.size();
          // Perturbation: 50% chance flip a random X bit, 50% reassign a random
          // A
          if (rand01() < 0.5) {
            int k = (int)rand_int(0, num_H - 1);
            nbr.X[k] ^= 1;
            // repair: ensure at least 1 open
            bool any = false;
            for (int kk = 0; kk < num_H; kk++)
              if (nbr.X[kk]) {
                any = true;
                break;
              }
            if (!any)
              nbr.X[(int)rand_int(0, num_H - 1)] = 1;
          } else {
            // Perturb rotation offset A[ii] by ±1 step (wraps in {0..|H|-1})
            int ii = (int)rand_int(0, num_I - 1);
            nbr.A[ii] = ((nbr.A[ii] + (rand01() < 0.5 ? 1 : -1) + num_H) % num_H);
          }
          decode(nbr, inst);
          // Accept if nbr is non-dominated by sol (Pareto-improving)
          if (!sol.constrained_dominates(nbr))
            ls_children.push_back(nbr);
        }
      }
      if (!ls_children.empty()) {
        for (auto &c : ls_children)
          pop.push_back(c);
        elitist_select(pop, POP);
      }
    }

    // Logging
    if (gen % cfg.log_every == 0 || gen == cfg.num_gen) {
      int r1_count = 0;
      double best_z1 = 1e18, best_z2 = 1e18;
      int feas = 0;
      for (auto &ind : pop) {
        if (ind.rank == 1)
          r1_count++;
        if (ind.CV == 0)
          feas++;
        if (ind.rank == 1) {
          umin(best_z1, ind.Z1);
          umin(best_z2, ind.Z2);
        }
      }
      cerr << "[Gen " << std::setw(4) << gen << "] Pareto=" << r1_count
           << " Feas=" << feas << "/" << POP << " bestZ1=" << std::scientific
           << std::setprecision(3) << best_z1 << " bestZ2=" << best_z2 << " "
           << std::fixed << std::setprecision(1)
           << duration_ms(time_now() - t_start) / 1000.0 << "s\n";
    }
  }

  cerr << "[" << algo_name << "] Done. Total time: " << std::fixed
       << duration_ms(time_now() - t_start) / 1000.0 << "s\n";
  return pop;
}
