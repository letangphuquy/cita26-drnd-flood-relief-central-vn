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
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <set>
#include <sstream>
#include <string>
#include <utility>

// ── Algorithm parameters (defaults, overridable from main) ──────────────────
struct NSGAConfig {
  int pop_size = 200; // ↑ from 100 — better coverage
  int num_gen = 300;  // ↑ from 200 — more refinement time
  double pc = 0.90;   // crossover probability
  // Adaptive mutation: decays linearly from pm_high → pm_low over generations.
  // High early exploration, tight late exploitation.
  double pm_high = 0.40;         // initial mutation rate base
  double pm_low = 0.10;          // final mutation rate base
  // [F2] SBX distribution indices — lower η → more exploratory offspring.
  // X-space crossover uses uniform XO (not SBX), so sbx_eta only affects A.
  // R and W use separate, lower η to avoid premature convergence.
  double sbx_eta = 15.0;         // SBX distribution index (A segment)
  double sbx_eta_rw = 2.0;       // SBX distribution index for R & W segments
  double pm_eta = 20.0;          // polynomial mutation index (A segment)
  double pm_eta_rw = 5.0;        // polynomial mutation index for R & W
  int log_every = 10;            // generations between progress logs
  int seed_iter = 0;             // for set_rolling_seed
  bool use_local_search = false; // true → PB-NSMA; false → plain NSGA-II
  int ls_iters = 5;              // local search perturbations per generation
  // Stagnation-driven selection pressure boost:
  // If the Pareto-front X-configuration set does not grow for
  // stagnation_threshold generations, switch to a 3-way tournament
  // (stronger pressure) and apply W-hypermutation (double rate on W-weights)
  // for one generation to escape the local basin.
  int stagnation_threshold = 20; // gens without new X-config in rank-1
  int tournament_size = 2;       // base tournament size (binary)
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
  // R segment: SBX with low η (exploratory) [F2]
  for (int k = 0; k < num_H; k++) {
    auto [r1, r2] = sbx_gene(p1.R[k], p2.R[k], cfg.sbx_eta_rw);
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
  // W segment: SBX with low η (exploratory) [F2]
  for (int w = 0; w < (int)p1.W.size(); w++) {
    auto [w1, w2] = sbx_gene(p1.W[w], p2.W[w], cfg.sbx_eta_rw);
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

// ── Mutation [F1: segment-specific rates] ───────────────────────────────────
// Each segment gets its own per-gene mutation probability = pm_base / segment_size.
// This ensures X (5 genes) and W (6 genes) are mutated as frequently as A (20 genes)
// in terms of expected mutations per segment per offspring.
// w_scale: multiplier for W-segment mutation (1.0 normally, 2.0 on stagnation).
void mutate(Individual &ind, const NSGAConfig &cfg,
            double current_pm_base = -1.0, double w_scale = 1.0) {
  int num_H = (int)ind.X.size();
  int num_I = (int)ind.A.size();
  int num_W = (int)ind.W.size();
  double pm_base = (current_pm_base >= 0) ? current_pm_base : cfg.pm_high;

  // [F1] Segment-specific mutation probabilities:
  //   Expected mutations per segment per offspring ≈ pm_base.
  double pm_x = pm_base / std::max(1, num_H); // X: ~pm_base mutations/offspring
  double pm_r = pm_base / std::max(1, num_H); // R: ~pm_base mutations/offspring
  double pm_a = pm_base / std::max(1, num_I); // A: ~pm_base mutations/offspring
  double pm_w_base = pm_base / std::max(1, num_W); // W: ~pm_base mutations/offspring

  // X: bit-flip
  for (int k = 0; k < num_H; k++) {
    if (rand01() < pm_x)
      ind.X[k] ^= 1;
  }
  // Repair: ensure at least 1 open hub
  bool any_open = false;
  for (int k = 0; k < num_H; k++)
    if (ind.X[k]) {
      any_open = true;
      break;
    }
  if (!any_open)
    ind.X[(int)rand_int(0, num_H - 1)] = 1;

  // R: polynomial mutation with low η [F2]
  for (int k = 0; k < num_H; k++) {
    if (rand01() < pm_r)
      ind.R[k] = poly_mutate(ind.R[k], cfg.pm_eta_rw);
  }
  // A: random replacement
  for (int i = 0; i < num_I; i++) {
    if (rand01() < pm_a)
      ind.A[i] = (int)rand_int(0, num_H - 1);
  }
  // W: polynomial mutation with low η [F2] + optional hyper-scale (stagnation)
  double pm_w = std::min(pm_w_base * w_scale, 1.0);
  for (int w = 0; w < num_W; w++) {
    if (rand01() < pm_w)
      ind.W[w] = poly_mutate(ind.W[w], cfg.pm_eta_rw);
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

// ── Tournament selection (size-k, k >= 2)
// ────────────────────────────────────────
// Picks k random candidates and returns the best by constrained dominance.
// k=2 → classic binary tournament; k=3 → stronger selection pressure.
const Individual &tournament(const vector<Individual> &pop, int k = 2) {
  int best = (int)rand_int(0, (int)pop.size() - 1);
  for (int t = 1; t < k; t++) {
    int cand = (int)rand_int(0, (int)pop.size() - 1);
    if (constrained_better(pop[cand], pop[best]))
      best = cand;
  }
  return pop[best];
}

// ── Hamming diversity (Fix D) ────────────────────────────────────────────────
// For each individual, compute its minimum Hamming distance in X-space to
// any other individual in the pool. Used as a tiebreaker in elitist selection
// to prefer genotypically isolated solutions. O(N^2 * |H|).
void compute_hamming_diversity(vector<Individual> &pop) {
  int N = (int)pop.size();
  int num_H = (N > 0) ? (int)pop[0].X.size() : 0;
  for (int i = 0; i < N; i++) {
    int min_h = num_H; // worst case: all bits differ
    for (int j = 0; j < N; j++) {
      if (i == j)
        continue;
      int h = 0;
      for (int k = 0; k < num_H; k++)
        h += (pop[i].X[k] != pop[j].X[k]);
      if (h < min_h)
        min_h = h;
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
        if (ia.rank != ib.rank)
          return ia.rank < ib.rank;
        if (std::abs(ia.crowding - ib.crowding) > 1e-9)
          return ia.crowding > ib.crowding;
        return ia.hamming_diversity > ib.hamming_diversity;
      });
      for (int i = 0; i < remaining; i++)
        new_pop.push_back(combined[front_idx[i]]);
      break;
    }
  }

  // ── [M1] X-Niche Quota Preservation ──────────────────────────────────────
  // Guarantee at least 1 survivor per unique X-config that exists in the
  // combined pool.  Without this, rare X-configs get crowding-killed when
  // Pareto=N (all rank-1), because their Z1/Z2 sits in a dense region.
  // Cost: at most 2^H reserved slots (31 for H=5, ~15% of pop=200).
  {
    // 1. Index new_pop by X-config
    std::map<vector<int>, vector<int>> x_to_idx; // X → indices in new_pop
    for (int i = 0; i < (int)new_pop.size(); i++)
      x_to_idx[new_pop[i].X].push_back(i);

    // 2. Collect X-configs present in *combined* pool but missing from new_pop
    std::set<vector<int>> missing;
    for (const auto &ind : combined) {
      if (x_to_idx.find(ind.X) == x_to_idx.end())
        missing.insert(ind.X);
    }

    // 3. For each missing X-config, find its best representative in combined
    //    and swap it in for the worst member of the most over-represented niche.
    for (const auto &mx : missing) {
      // Find best representative of missing config (lowest rank, then highest crowding)
      int best_src = -1;
      for (int i = 0; i < (int)combined.size(); i++) {
        if (combined[i].X != mx) continue;
        if (best_src < 0 ||
            combined[i].rank < combined[best_src].rank ||
            (combined[i].rank == combined[best_src].rank &&
             combined[i].crowding > combined[best_src].crowding))
          best_src = i;
      }
      if (best_src < 0) continue;

      // Find the most over-represented niche (largest count, > 1 member)
      vector<int> *largest_niche = nullptr;
      for (auto &[xk, idxs] : x_to_idx) {
        if ((int)idxs.size() <= 1) continue;
        if (!largest_niche || (int)idxs.size() > (int)largest_niche->size())
          largest_niche = &idxs;
      }
      if (!largest_niche || largest_niche->empty()) break; // no room

      // Replace the worst member (last after sort = lowest crowding) of that niche
      int victim = largest_niche->back();
      largest_niche->pop_back();
      new_pop[victim] = combined[best_src];
      x_to_idx[mx].push_back(victim);
    }
  }

  combined = std::move(new_pop);
}

// ── Stagnation detection helper
// ──────────────────────────────────────────────
// Returns a fingerprint string of all unique X-configs in rank-1 front.
// Used to detect when the Pareto front has stopped evolving.
string rank1_fingerprint(const vector<Individual> &pop) {
  // Fingerprint the set of unique X-configs in rank-1 front.
  // Using X vectors (not Z1/Z2) so stagnation fires only when hub topology stops changing.
  std::set<vector<int>> configs;
  for (const auto &ind : pop) {
    if (ind.rank != 1)
      continue;
    configs.insert(ind.X);
  }
  string fp;
  for (const auto &xv : configs) {
    for (int b : xv)
      fp += ('0' + b);
    fp += '|';
  }
  return fp;
}

// ── Main loop (NSGA-II or PB-NSMA depending on cfg.use_local_search)
// ───────────────────────────────────────────────────────────────────
vector<Individual> run_nsga2(const DRNDInstance &inst, const NSGAConfig &cfg) {
  set_rolling_seed(cfg.seed_iter);
  int POP = cfg.pop_size;
  const char *algo_name = cfg.use_local_search ? "PB-NSMA" : "PB-NSGA";

  // ── Initial population ───────────────────────────────────────────────────
  vector<Individual> pop;
  pop.reserve(POP);
  cerr << "[" << algo_name << "] Init pop N=" << POP << " gen=" << cfg.num_gen
       << " pm=" << cfg.pm_high << "→" << cfg.pm_low << "\n";
  while ((int)pop.size() < POP) {
    Individual ind = random_individual(inst);
    decode(ind, inst);
    pop.push_back(ind);
  }
  elitist_select(pop, POP);

  TimeVar t_start = time_now();

  // ── Stagnation tracking ──────────────────────────────────────────────────
  string last_fp = rank1_fingerprint(pop);
  int stag_gens = 0;     // consecutive gens without Pareto-front change
  bool boosting = false; // currently in pressure-boost mode

  // ── Main loop ─────────────────────────────────────────────────────────────
  for (int gen = 1; gen <= cfg.num_gen; gen++) {

    // ── Adaptive mutation rate (linear decay pm_high → pm_low) ────────────
    double progress = (double)(gen - 1) / std::max(1, cfg.num_gen - 1);
    double cur_pm = cfg.pm_high - (cfg.pm_high - cfg.pm_low) * progress;

    // ── Stagnation: check & decide tournament size / W-hypermutation ───────
    string cur_fp = rank1_fingerprint(pop);
    if (cur_fp == last_fp) {
      ++stag_gens;
    } else {
      stag_gens = 0;
      last_fp = cur_fp;
      boosting = false;
    }
    bool w_hyper = false;
    int tourney = cfg.tournament_size;
    if (stag_gens >= cfg.stagnation_threshold) {
      tourney =
          std::min(cfg.tournament_size + 1, 4); // 3-way (or 4 if already 3)
      w_hyper = true; // double W mutation this generation
      if (!boosting) {
        cerr << "[Gen " << gen
             << "] Stagnation detected — boosting tourney=" << tourney
             << " W-hypermut on\n";
        boosting = true;
      }
    }

    // ── Generate offspring ─────────────────────────────────────────────────
    vector<Individual> offspring;
    offspring.reserve(POP);
    while ((int)offspring.size() < POP) {
      const Individual &p1 = tournament(pop, tourney);
      const Individual &p2 = tournament(pop, tourney);
      Individual c1, c2;
      if (rand01() < cfg.pc) {
        auto [cx1, cx2] = crossover(p1, p2, cfg);
        c1 = cx1;
        c2 = cx2;
      } else {
        c1 = p1;
        c2 = p2;
      }
      // Adaptive mutation — W-hypermutation on stagnation
      double w_scale = w_hyper ? 2.0 : 1.0;
      // Apply mutation with per-offspring probability proportional to cur_pm
      // (we always mutate now; pm_base is baked into per-gene probability)
      mutate(c1, cfg, cur_pm, w_scale);
      mutate(c2, cfg, cur_pm, w_scale);
      decode(c1, inst);
      decode(c2, inst);
      offspring.push_back(c1);
      if ((int)offspring.size() < POP)
        offspring.push_back(c2);
    }

    // ── Combine and elitist select ─────────────────────────────────────────
    for (auto &o : offspring)
      pop.push_back(o);
    elitist_select(pop, POP);

    // ── NSMA-style local search (only when use_local_search = true) ─────────
    if (cfg.use_local_search) {
      vector<Individual> ls_children;
      for (auto &sol : pop) {
        if (sol.rank != 1)
          continue;
        for (int t = 0; t < cfg.ls_iters; t++) {
          Individual nbr = sol;
          int num_H = (int)nbr.X.size();
          int num_I = (int)nbr.A.size();
          // 33% flip X, 33% nudge A, 33% perturb W
          double r = rand01();
          if (r < 0.33) {
            int k = (int)rand_int(0, num_H - 1);
            nbr.X[k] ^= 1;
            bool any = false;
            for (int kk = 0; kk < num_H; kk++)
              if (nbr.X[kk]) {
                any = true;
                break;
              }
            if (!any)
              nbr.X[(int)rand_int(0, num_H - 1)] = 1;
          } else if (r < 0.66) {
            int ii = (int)rand_int(0, num_I - 1);
            nbr.A[ii] =
                ((nbr.A[ii] + (rand01() < 0.5 ? 1 : -1) + num_H) % num_H);
          } else {
            // Perturb one W weight
            int ww = (int)rand_int(0, (int)nbr.W.size() - 1);
            nbr.W[ww] = poly_mutate(nbr.W[ww], cfg.pm_eta_rw);
          }
          decode(nbr, inst);
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

    // ── Progress logging ───────────────────────────────────────────────────
    if (gen % cfg.log_every == 0 || gen == cfg.num_gen) {
      int r1_cnt = 0, feas = 0;
      double best_z1 = 1e18, best_z2 = 1e18;
      for (auto &ind : pop) {
        if (ind.rank == 1) {
          r1_cnt++;
          umin(best_z1, ind.Z1);
          umin(best_z2, ind.Z2);
        }
        if (ind.CV == 0)
          feas++;
      }
      cerr << "[Gen " << std::setw(4) << gen << "] Pareto=" << r1_cnt
           << " Feas=" << feas << "/" << POP << " pm=" << std::fixed
           << std::setprecision(3) << cur_pm << " stag=" << stag_gens
           << " Z1=" << std::scientific << std::setprecision(3) << best_z1
           << " Z2=" << best_z2 << " " << std::fixed << std::setprecision(1)
           << duration_ms(time_now() - t_start) / 1000.0 << "s\n";
    }
  }

  // ── Log diversity summary at end ──────────────────────────────────────────
  {
    std::set<vector<int>> unique_x;
    for (const auto &ind : pop)
      unique_x.insert(ind.X);
    cerr << "[" << algo_name << "] Final unique X configs: " << unique_x.size()
         << "/" << POP << "\n";
  }

  cerr << "[" << algo_name << "] Done in " << std::fixed << std::setprecision(2)
       << duration_ms(time_now() - t_start) / 1000.0 << "s\n";
  return pop;
}
