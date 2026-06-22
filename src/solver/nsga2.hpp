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
#include "local_search_engine.hpp"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <numeric>
#include <set>
#include <sstream>
#include <string>
#include <utility>

// ── Algorithm parameters (defaults, overridable from main) ──────────────────
struct NSGAConfig {
  int pop_size = 200; // ↑ from 100 — better coverage
  int num_gen = 300;  // ↑ from 200 — more refinement time
  double pc = 0.98;   // crossover probability
  // Adaptive mutation: decays linearly from pm_high → pm_low over generations.
  // High early exploration, tight late exploitation.
  double pm_high = 0.40;         // initial mutation rate base
  double pm_low = 0.10;          // final mutation rate base
  // [F2] SBX / polynomial mutation indices for continuous segments.
  // Note: A uses categorical operators (uniform swap + random replacement),
  // so A-segment eta knobs are intentionally disabled.
  // double sbx_eta = 15.0;      // disabled (A segment not using SBX)
  double sbx_eta_rw = 1.5;       // SBX distribution index for R & W segments
  // double pm_eta = 20.0;       // disabled (A segment not using poly mutate)
  double pm_eta_rw = 8.0;        // polynomial mutation index for R & W
  int log_every = 10;            // generations between progress logs
  int seed_iter = 0;             // for set_rolling_seed
  bool use_local_search = false; // true → PB-NSMA; false → plain NSGA-II
  int ls_iters = 5;              // local search perturbations per generation
  // Stagnation-driven selection pressure boost:
  // If the Pareto-front X-configuration set does not grow for
  // stagnation_threshold generations, switch to a 3-way tournament
  // (stronger pressure) and trigger a short W-hypermutation pulse to
  // escape the local basin.
  int stagnation_threshold = 20; // gens without new X-config in rank-1
  int tournament_size = 2;       // base tournament size (binary)
  int hyper_pulse_len = 3;       // number of generations in a hypermutation pulse
  int hyper_pulse_cooldown = 8;  // min generations between pulse starts
  double hyper_w_scale = 2.0;    // W-mutation scale while pulse is active
  // Approach #3 (partial random immigrants), made conservative:
  // - apply only when both stagnation and low diversity are observed
  // - preserve top elites
  // - enforce cooldown to avoid over-disruption
  double immigrant_ratio = 0.02;      // replace ~2% of pop when triggered
  double immigrant_elite_frac = 0.20; // top 20% never replaced
  int immigrant_stag_trigger = 20;    // if <=0, fallback to stagnation_threshold
  int immigrant_cooldown_gen = 8;     // min generations between injections
  int immigrant_low_unique_x = 8;     // low-diversity trigger on unique X count

  // AEGA-style adaptive population control (opt-in).
  // We adapt active population size within [pop_min, pop_max] based on
  // stagnation and genotypic diversity, while preserving the same core loop.
  bool enable_aega_adaptive_pop = false;
  int aega_pop_min = 120;
  int aega_pop_max = 320;
  int aega_pop_step = 30;
  double aega_div_low = 0.08;  // unique-X ratio threshold to expand population
  double aega_div_high = 0.18; // unique-X ratio threshold to shrink population

  // Diversity strategy toggles (non-trivial strategies only).
  // Trivial controls (pm/pc) stay always available regardless of these flags.
  bool enable_stagnation_boost = true;   // tournament boost + W-hypermutation
  bool enable_hypermutation_pulse = false; // pulse+cooldown (Technique #2)
  bool enable_hamming_tiebreak = true;   // Hamming tie-break in elitist select
  bool enable_x_niche_quota = true;      // preserve missing X niches
  bool enable_random_immigrants = true;  // guarded immigrant injection
  bool use_legacy_seeding = false;       // rollback init seeding strategy
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
crossover(const Individual &p1, const Individual &p2, const NSGAConfig &cfg,
          const DRNDInstance &inst) {
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
  // Clamp W[1] (speed weight) — W1>0.4 consistently hurts Z2; good seeds converge
  // to W1<=0.27; bad seeds get trapped at W1=0.55–1.0. Cap at 0.40 prevents the
  // W1-trap while allowing the 0.27–0.40 range that mid-performing seeds benefit from.
  c1.W[1] = std::min(c1.W[1], 0.40);
  c2.W[1] = std::min(c2.W[1], 0.40);

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
  // Idea 2: X-aligned A repair — redirect any A[i] that now points to a closed
  // hub (because the child got a different X from the other parent).
  auto repair_a = [&](Individual &ind) {
    vector<int> open;
    for (int k = 0; k < num_H; k++)
      if (ind.X[k]) open.push_back(k);
    if (open.empty()) return;
    for (int i = 0; i < num_I; i++)
      if (!ind.X[ind.A[i]])
        ind.A[i] = open[(int)rand_int(0, (int)open.size() - 1)];
  };
  repair_a(c1);
  repair_a(c2);
  return {c1, c2};
}

// ── Mutation [F1: segment-specific rates] ───────────────────────────────────
// Each segment gets its own per-gene mutation probability = pm_base / segment_size.
// This ensures X (5 genes) and W (6 genes) are mutated as frequently as A (20 genes)
// in terms of expected mutations per segment per offspring.
// w_scale: multiplier for W-segment mutation (1.0 normally, 2.0 on stagnation).
void mutate(Individual &ind, const NSGAConfig &cfg, const DRNDInstance &inst,
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

  // Collect open hubs once — reused below.
  vector<int> open_hubs;
  open_hubs.reserve(num_H);
  for (int k = 0; k < num_H; k++)
    if (ind.X[k]) open_hubs.push_back(k);

  // Idea 2 in mutation: after X bit-flip, any A[i] pointing to a now-closed
  // hub is immediately redirected to a random open hub.
  if (!open_hubs.empty())
    for (int i = 0; i < num_I; i++)
      if (!ind.X[ind.A[i]])
        ind.A[i] = open_hubs[(int)rand_int(0, (int)open_hubs.size() - 1)];

  // R: polynomial mutation with low η [F2]
  for (int k = 0; k < num_H; k++) {
    if (rand01() < pm_r)
      ind.R[k] = poly_mutate(ind.R[k], cfg.pm_eta_rw);
  }

  // Idea 1: open-hub-biased A mutation.
  // With prob 0.85, replace A[i] with a random *open* hub; otherwise any hub.
  for (int i = 0; i < num_I; i++) {
    if (rand01() < pm_a) {
      if (!open_hubs.empty() && rand01() < 0.85)
        ind.A[i] = open_hubs[(int)rand_int(0, (int)open_hubs.size() - 1)];
      else
        ind.A[i] = (int)rand_int(0, num_H - 1);
    }
  }

  // W: polynomial mutation with low η [F2] + optional hyper-scale (stagnation)
  double pm_w = std::min(pm_w_base * w_scale, 1.0);
  for (int w = 0; w < num_W; w++) {
    if (rand01() < pm_w)
      ind.W[w] = poly_mutate(ind.W[w], cfg.pm_eta_rw);
  }
  // Clamp W[1] (speed weight) — W1>0.4 consistently hurts Z2; good seeds converge
  // naturally to W1<=0.27. Cap prevents W1-trap while allowing beneficial W1<=0.40.
  ind.W[1] = std::min(ind.W[1], 0.40);
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

int count_unique_x_configs(const vector<Individual> &pop) {
  std::set<vector<int>> unique_x;
  for (const auto &ind : pop)
    unique_x.insert(ind.X);
  return (int)unique_x.size();
}


// ── Elitist survival selection
// ────────────────────────────────────────────────
void elitist_select(vector<Individual> &combined, int target_size,
                    const NSGAConfig &cfg) {
  if (cfg.enable_hamming_tiebreak)
    compute_hamming_diversity(combined);
  auto fronts = fast_nondominated_sort(combined);
  vector<Individual> new_pop;
  for (auto &front_idx : fronts) {
    crowding_distance(combined, front_idx);
    if ((int)(new_pop.size() + front_idx.size()) <= target_size) {
      for (int i : front_idx)
        new_pop.push_back(combined[i]);
    } else {
      int remaining = target_size - (int)new_pop.size();
      // Tiebreaker order: rank → crowding distance → (optional) Hamming diversity
      std::sort(all(front_idx), [&](int a, int b) {
        const Individual &ia = combined[a], &ib = combined[b];
        if (ia.rank != ib.rank)
          return ia.rank < ib.rank;
        if (std::abs(ia.crowding - ib.crowding) > 1e-9)
          return ia.crowding > ib.crowding;
        if (cfg.enable_hamming_tiebreak)
          return ia.hamming_diversity > ib.hamming_diversity;
        return false;
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
  if (cfg.enable_x_niche_quota) {
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
  int BASE_POP = cfg.pop_size;
  int cur_pop_size = cfg.pop_size;
  if (cfg.enable_aega_adaptive_pop) {
    cur_pop_size = std::clamp(cfg.pop_size, cfg.aega_pop_min, cfg.aega_pop_max);
  }
  const char *algo_name = cfg.use_local_search ? "PB-NSMA" : "PB-NSGA";
  auto decode_in_place = [&](Individual &ind) { decode(ind, inst); };
  int sample_tick = 0;
  auto sample_individual = [&]() {
    if (cfg.use_legacy_seeding)
      return random_individual(inst);

    Individual ind(inst.num_H, inst.num_I);
    int max_open = std::max(1, inst.num_H * 3 / 5);
    int tier = sample_tick++ % 3;
    int lo = 1, hi = max_open;
    if (tier == 0) {
      hi = std::max(1, max_open / 3);
    } else if (tier == 1) {
      lo = std::max(1, max_open / 3);
      hi = std::max(lo, (2 * max_open) / 3);
    } else {
      lo = std::max(1, (2 * max_open) / 3);
      hi = max_open;
    }
    int n_open = (int)rand_int(lo, hi);

    vector<int> hubs(inst.num_H);
    std::iota(hubs.begin(), hubs.end(), 0);
    shuffle_vec(hubs);
    std::stable_sort(all(hubs), [&](int a, int b) {
      return inst.F_hub[a] < inst.F_hub[b];
    });
    int pool = (tier == 2) ? inst.num_H : std::max(n_open, inst.num_H / 2);
    pool = std::clamp(pool, n_open, inst.num_H);
    std::shuffle(hubs.begin(), hubs.begin() + pool, rng);
    for (int i = 0; i < n_open; i++)
      ind.X[hubs[i]] = 1;

    for (int k = 0; k < inst.num_H; k++) {
      if (ind.X[k]) {
        ind.R[k] = std::clamp(0.45 + 0.5 * rand01(), 0.0, 1.0);
      } else {
        ind.R[k] = 0.25 * rand01();
      }
    }

    vector<int> open;
    open.reserve(inst.num_H);
    for (int k = 0; k < inst.num_H; k++) {
      if (ind.X[k])
        open.push_back(k);
    }
    if (open.empty()) {
      int k = (int)rand_int(0, inst.num_H - 1);
      ind.X[k] = 1;
      open.push_back(k);
    }

    for (int ii = 0; ii < inst.num_I; ii++) {
      int chosen = open[0];
      double best_d = 1e100;
      int abs_i = inst.demand_idx[ii];
      for (int k : open) {
        int abs_h = inst.hub_idx[k];
        double dx = inst.lat[abs_i] - inst.lat[abs_h];
        double dy = inst.lon[abs_i] - inst.lon[abs_h];
        double d2 = dx * dx + dy * dy;
        if (d2 < best_d) {
          best_d = d2;
          chosen = k;
        }
      }
      if (rand01() < 0.20)
        chosen = open[(int)rand_int(0, (int)open.size() - 1)];
      ind.A[ii] = chosen;
    }

    // W[1]=speed weight; empirically, good seeds converge to W[1]<=0.27.
    // All templates now start with W[1]<=0.20 to avoid the W1-trap.
    const vector<vector<double>> w_templates = {
        {0.70, 0.00, 0.90, 0.60, 0.70, 0.45},
        {0.55, 0.20, 0.85, 0.40, 0.65, 0.50},
        {0.80, 0.10, 0.95, 0.75, 0.55, 0.55},
        {0.45, 0.15, 0.80, 0.50, 0.75, 0.40},
    };
    const vector<double> &wt = w_templates[(size_t)(sample_tick % (int)w_templates.size())];
    for (int t = 0; t < (int)ind.W.size(); t++) {
      double noise = 0.10 * (rand01() - 0.5);
      ind.W[t] = std::clamp(wt[t] + noise, 0.0, 1.0);
    }
    return ind;
  };

  // ── Initial population ───────────────────────────────────────────────────
  vector<Individual> pop;
  pop.reserve(std::max(BASE_POP, cfg.aega_pop_max));
  cerr << "[" << algo_name << "] Init pop N=" << cur_pop_size << " gen=" << cfg.num_gen
       << " pm=" << cfg.pm_high << "→" << cfg.pm_low << "\n";
  while ((int)pop.size() < cur_pop_size) {
    Individual ind = sample_individual();
    decode_in_place(ind);
    pop.push_back(ind);
  }
  elitist_select(pop, cur_pop_size, cfg);

  TimeVar t_start = time_now();

  // ── Stagnation tracking ──────────────────────────────────────────────────
  string last_fp = rank1_fingerprint(pop);
  int stag_gens = 0;     // consecutive gens without Pareto-front change
  bool boosting = false; // currently in pressure-boost mode
  int last_imm_gen = -1000000;
  int hyper_pulse_left = 0;
  int hyper_cooldown_left = 0;

  // ── Main loop ─────────────────────────────────────────────────────────────
  for (int gen = 1; gen <= cfg.num_gen; gen++) {
    int immigrants_used = 0;
    int unique_x_count = 0;

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
      hyper_pulse_left = 0;
      hyper_cooldown_left = 0;
    }
    bool w_hyper = false;
    int tourney = cfg.tournament_size;
    if (cfg.enable_stagnation_boost &&
      stag_gens >= cfg.stagnation_threshold) {
      tourney =
          std::min(cfg.tournament_size + 1, 4); // 3-way (or 4 if already 3)
      if (cfg.enable_hypermutation_pulse && hyper_pulse_left == 0 &&
          hyper_cooldown_left == 0) {
        hyper_pulse_left = std::max(1, cfg.hyper_pulse_len);
        hyper_cooldown_left = std::max(0, cfg.hyper_pulse_cooldown);
        cerr << "[Gen " << gen << "] Hypermutation pulse ON for "
             << hyper_pulse_left << " gens (cooldown=" << hyper_cooldown_left
             << ")\n";
      }
      if (!boosting) {
        cerr << "[Gen " << gen
             << "] Stagnation detected — boosting tourney=" << tourney
             << "\n";
        boosting = true;
      }
    }

    if (cfg.enable_hypermutation_pulse && hyper_pulse_left > 0) {
      w_hyper = true;
      --hyper_pulse_left;
    }
    if (hyper_cooldown_left > 0)
      --hyper_cooldown_left;

    // AEGA-like adaptive active population size.
    if (cfg.enable_aega_adaptive_pop) {
      unique_x_count = count_unique_x_configs(pop);
      double div_ratio = (double)unique_x_count / std::max(1, (int)pop.size());
      int next_pop_size = cur_pop_size;
      if (stag_gens >= cfg.stagnation_threshold && div_ratio <= cfg.aega_div_low) {
        next_pop_size = std::min(cfg.aega_pop_max, cur_pop_size + cfg.aega_pop_step);
      } else if (stag_gens == 0 && div_ratio >= cfg.aega_div_high) {
        next_pop_size = std::max(cfg.aega_pop_min, cur_pop_size - cfg.aega_pop_step);
      }
      if (next_pop_size != cur_pop_size) {
        cerr << "[Gen " << gen << "] AEGA pop adapt: " << cur_pop_size
             << " -> " << next_pop_size << " (div=" << std::fixed
             << std::setprecision(3) << div_ratio << std::defaultfloat << ")\n";
        cur_pop_size = next_pop_size;
      }
    }

    // ── Generate offspring ─────────────────────────────────────────────────
    vector<Individual> offspring;
    offspring.reserve(cur_pop_size);
    while ((int)offspring.size() < cur_pop_size) {
      const Individual &p1 = tournament(pop, tourney);
      const Individual &p2 = tournament(pop, tourney);
      Individual c1, c2;
      if (rand01() < cfg.pc) {
        auto [cx1, cx2] = crossover(p1, p2, cfg, inst);
        c1 = cx1;
        c2 = cx2;
      } else {
        c1 = p1;
        c2 = p2;
      }
      // Adaptive mutation — W-hypermutation on stagnation
      double w_scale = w_hyper ? cfg.hyper_w_scale : 1.0;
      // Apply mutation with per-offspring probability proportional to cur_pm
      // (we always mutate now; pm_base is baked into per-gene probability)
      mutate(c1, cfg, inst, cur_pm, w_scale);
      mutate(c2, cfg, inst, cur_pm, w_scale);
      decode_in_place(c1);
      decode_in_place(c2);
      offspring.push_back(c1);
      if ((int)offspring.size() < cur_pop_size)
        offspring.push_back(c2);
    }

    // ── Combine and elitist select ─────────────────────────────────────────
    for (auto &o : offspring)
      pop.push_back(o);
    elitist_select(pop, cur_pop_size, cfg);

    // ── NSMA-style local search (only when use_local_search = true) ─────────
    if (cfg.use_local_search) {
      vector<Individual> ls_children =
          run_local_search_phase(pop, inst, cfg.ls_iters);
      if (!ls_children.empty()) {
        for (auto &c : ls_children)
          pop.push_back(c);
        elitist_select(pop, cur_pop_size, cfg);
      }
    }

    unique_x_count = count_unique_x_configs(pop);

    // ── Partial random immigrants (Approach #3, guarded) ─────────────────
    // Inject only under genuine stagnation + low diversity, with elite shield.
    if (cfg.enable_random_immigrants) {
      int imm_stag_trigger = (cfg.immigrant_stag_trigger > 0)
                                 ? cfg.immigrant_stag_trigger
                                 : cfg.stagnation_threshold;
      bool low_div = (unique_x_count <= cfg.immigrant_low_unique_x);
      bool stag_hit = (stag_gens >= imm_stag_trigger);
      bool cooldown_ok =
          (gen - last_imm_gen >= std::max(1, cfg.immigrant_cooldown_gen));
      int pop_n = (int)pop.size();

      if (cfg.immigrant_ratio > 0.0 && pop_n > 2 && low_div && stag_hit &&
          cooldown_ok) {
        int elite_keep = (int)std::round(cfg.immigrant_elite_frac * pop_n);
        elite_keep = std::clamp(elite_keep, 1, pop_n - 1);

        int target_imm = (int)std::round(cfg.immigrant_ratio * pop_n);
        target_imm = std::clamp(target_imm, 1, pop_n - elite_keep);

        vector<int> idx(pop_n);
        std::iota(idx.begin(), idx.end(), 0);
        // Best first by constrained selection order.
        std::sort(all(idx), [&](int a, int b) {
          return constrained_better(pop[a], pop[b]);
        });

        vector<char> is_elite(pop_n, 0);
        for (int i = 0; i < elite_keep; i++)
          is_elite[idx[i]] = 1;

        vector<int> replaceable;
        replaceable.reserve(pop_n - elite_keep);
        for (int i = 0; i < pop_n; i++)
          if (!is_elite[i])
            replaceable.push_back(i);

        // Worst first among replaceable.
        std::sort(all(replaceable), [&](int a, int b) {
          if (constrained_better(pop[b], pop[a]))
            return true;
          if (constrained_better(pop[a], pop[b]))
            return false;
          return a < b;
        });

        for (int i = 0; i < target_imm; i++) {
          int at = replaceable[i];
          pop[at] = sample_individual();
          decode_in_place(pop[at]);
        }
        immigrants_used = target_imm;
        last_imm_gen = gen;

        // Re-rank after replacements.
        elitist_select(pop, cur_pop_size, cfg);
        unique_x_count = count_unique_x_configs(pop);
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
         << " Feas=" << feas << "/" << cur_pop_size << " pm=" << std::fixed
           << std::setprecision(3) << cur_pm << " stag=" << stag_gens
         << " N=" << cur_pop_size
           << " ux=" << unique_x_count << " imm=" << immigrants_used
           << " hyper=" << (w_hyper ? 1 : 0)
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
         << "/" << cur_pop_size << "\n";
  }

  cerr << "[" << algo_name << "] Done in " << std::fixed << std::setprecision(2)
       << duration_ms(time_now() - t_start) / 1000.0 << "s\n";
  return pop;
}
