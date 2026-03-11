// vns_ts_baseline.cpp
// -----------------------------------------------------------------------------
// VNS-TS baseline (simplified encoding)
//
// Encoding used in search:
//   - H/X: opened hub set
//   - A  : demand-to-hub assignment
//
// Deterministic reconstruction:
//   - R is reconstructed from assignment load (not directly searched)
//   - W is fixed (not searched)
//
// Operators:
//   1) swap_hub         : close one hub, open one hub
//   2) move_node        : reassign one demand node to another open hub
//   3) path_relink_lite : one-step move toward elite solution
//
// Search framework:
//   - VNS shaking over 3 neighborhoods
//   - TS local search with tabu on move signatures and aspiration
//   - Pareto archive of feasible decoded solutions
// -----------------------------------------------------------------------------

#include "decoder.hpp"

#include <algorithm>
#include <chrono>
#include <ctime>
#include <fstream>
#include <limits>
#include <numeric>
#include <random>
#include <unordered_map>

using Clock = std::chrono::high_resolution_clock;
using Duration = std::chrono::duration<double>;

struct Solution {
  double Z1 = 0.0;
  double Z2 = 0.0;
  vector<int> X;
  vector<double> R;
  vector<int> A;
  vector<double> W;
};

struct Candidate {
  Individual ind;
  double Z1 = 0.0;
  double Z2 = 0.0;
  double CV = 0.0;
  long long move_key = -1;
};

struct EliteEntry {
  Individual ind;
  double Z1 = 0.0;
  double Z2 = 0.0;
};

struct ParetoArchive {
  vector<Solution> front;

  bool is_dominated(double z1, double z2) const {
    for (const auto &s : front) {
      if (s.Z1 <= z1 && s.Z2 <= z2 && (s.Z1 < z1 || s.Z2 < z2))
        return true;
    }
    return false;
  }

  void add(Solution sol) {
    if (is_dominated(sol.Z1, sol.Z2))
      return;
    front.erase(std::remove_if(front.begin(), front.end(), [&](const Solution &s) {
                 return sol.Z1 <= s.Z1 && sol.Z2 <= s.Z2 &&
                        (sol.Z1 < s.Z1 || sol.Z2 < s.Z2);
               }),
               front.end());
    front.push_back(std::move(sol));
  }
};

static vector<int> opened_hubs(const vector<int> &X) {
  vector<int> open_ki;
  for (int ki = 0; ki < (int)X.size(); ++ki)
    if (X[ki])
      open_ki.push_back(ki);
  return open_ki;
}

static vector<double> expected_demand(const DRNDInstance &inst) {
  vector<double> e(inst.num_I, 0.0);
  for (int si = 0; si < inst.num_S; ++si) {
    const double p = inst.scenarios[si].prob;
    for (int ii = 0; ii < inst.num_I; ++ii) {
      int di = inst.demand_idx[ii];
      e[ii] += p * inst.scenarios[si].demand[di];
    }
  }
  return e;
}

static void assign_nearest_open_hub(Individual &ind, const DRNDInstance &inst) {
  auto open_ki = opened_hubs(ind.X);
  if (open_ki.empty()) {
    std::fill(ind.A.begin(), ind.A.end(), 0);
    return;
  }
  for (int ii = 0; ii < inst.num_I; ++ii) {
    int d = inst.demand_idx[ii];
    int best_ki = open_ki[0];
    double best_d2 = std::numeric_limits<double>::infinity();
    for (int ki : open_ki) {
      int h = inst.hub_idx[ki];
      double dx = inst.lat[d] - inst.lat[h];
      double dy = inst.lon[d] - inst.lon[h];
      double d2 = dx * dx + dy * dy;
      if (d2 < best_d2) {
        best_d2 = d2;
        best_ki = ki;
      }
    }
    ind.A[ii] = best_ki;
  }
}

// Assign each demand to the open hub with minimum expected last-mile cost
// (expected theta across scenarios). Paper §4.2: "assign to nearest hub" —
// this adapts that to the actual transport cost structure of our problem.
static void assign_min_cost_hub(Individual &ind, const DRNDInstance &inst) {
  auto open_ki = opened_hubs(ind.X);
  if (open_ki.empty()) {
    std::fill(ind.A.begin(), ind.A.end(), 0);
    return;
  }
  for (int ii = 0; ii < inst.num_I; ++ii) {
    int best_ki = open_ki[0];
    double best_cost = std::numeric_limits<double>::infinity();
    for (int ki : open_ki) {
      double avg_theta = 0.0;
      for (int si = 0; si < inst.num_S; ++si)
        avg_theta += inst.scenarios[si].prob * inst.theta[ki][ii][si];
      if (avg_theta < best_cost) {
        best_cost = avg_theta;
        best_ki = ki;
      }
    }
    ind.A[ii] = best_ki;
  }
}

static void reconstruct_R(Individual &ind, const DRNDInstance &inst,
                          const vector<double> &exp_dem) {
  vector<double> load(inst.num_H, 0.0);
  for (int ii = 0; ii < inst.num_I; ++ii) {
    int ki = ind.A[ii];
    if (ki >= 0 && ki < inst.num_H && ind.X[ki])
      load[ki] += inst.gamma * exp_dem[ii];
  }
  for (int ki = 0; ki < inst.num_H; ++ki) {
    if (!ind.X[ki]) {
      ind.R[ki] = 0.0;
      continue;
    }
    if (inst.kappa[ki] <= EPS) {
      ind.R[ki] = 1.0;
      continue;
    }
    double ratio = load[ki] / inst.kappa[ki];
    ind.R[ki] = std::max(0.0, std::min(1.0, ratio));
  }
}

static void repair_capacity(Individual &ind, const DRNDInstance &inst,
                            const vector<double> &exp_dem,
                            std::mt19937 &rng,
                            int max_moves = 20) {
  auto open_ki = opened_hubs(ind.X);
  if (open_ki.size() <= 1)
    return;

  for (int mv = 0; mv < max_moves; ++mv) {
    vector<double> load(inst.num_H, 0.0);
    for (int ii = 0; ii < inst.num_I; ++ii)
      if (ind.X[ind.A[ii]])
        load[ind.A[ii]] += inst.gamma * exp_dem[ii];

    int over_ki = -1;
    double worst_ratio = 1.0;
    for (int ki : open_ki) {
      if (inst.kappa[ki] <= EPS)
        continue;
      double ratio = load[ki] / inst.kappa[ki];
      if (ratio > worst_ratio + 1e-9) {
        worst_ratio = ratio;
        over_ki = ki;
      }
    }
    if (over_ki < 0)
      break;

    int picked_ii = -1;
    double picked_dem = -1.0;
    for (int ii = 0; ii < inst.num_I; ++ii) {
      if (ind.A[ii] != over_ki)
        continue;
      if (exp_dem[ii] > picked_dem) {
        picked_dem = exp_dem[ii];
        picked_ii = ii;
      }
    }
    if (picked_ii < 0)
      break;

    int d = inst.demand_idx[picked_ii];
    int best_alt = over_ki;
    double best_score = std::numeric_limits<double>::infinity();

    for (int ki : open_ki) {
      if (ki == over_ki)
        continue;
      int h = inst.hub_idx[ki];
      double dx = inst.lat[d] - inst.lat[h];
      double dy = inst.lon[d] - inst.lon[h];
      double dist2 = dx * dx + dy * dy;

      double next_load = load[ki] + inst.gamma * exp_dem[picked_ii];
      double cap_ratio = (inst.kappa[ki] > EPS) ? (next_load / inst.kappa[ki]) : 1e9;
      double cap_penalty = std::max(0.0, cap_ratio - 1.0);
      double score = dist2 + 1e6 * cap_penalty;

      if (score < best_score) {
        best_score = score;
        best_alt = ki;
      }
    }

    if (best_alt == over_ki)
      break;
    ind.A[picked_ii] = best_alt;
  }

  reconstruct_R(ind, inst, exp_dem);
}

static bool evaluate_candidate(Candidate &cand, const DRNDInstance &inst,
                               ParetoArchive *archive = nullptr) {
  decode(cand.ind, inst);
  cand.Z1 = cand.ind.Z1;
  cand.Z2 = cand.ind.Z2;
  cand.CV = cand.ind.CV;

  if (archive && cand.CV <= EPS) {
    Solution s;
    s.Z1 = cand.Z1;
    s.Z2 = cand.Z2;
    s.X = cand.ind.X;
    s.R = cand.ind.R;
    s.A = cand.ind.A;
    s.W = cand.ind.W;
    archive->add(std::move(s));
  }
  return cand.CV <= EPS;
}

static bool better_feasible(double z1a, double z2a, double z1b, double z2b,
                            int mode) {
  if (mode == 0) {
    if (z1a != z1b)
      return z1a < z1b;
    return z2a < z2b;
  }
  if (mode == 1) {
    if (z2a != z2b)
      return z2a < z2b;
    return z1a < z1b;
  }
  double sa = z1a + 10.0 * z2a;
  double sb = z1b + 10.0 * z2b;
  return sa < sb;
}

static bool better_candidate(const Candidate &a, const Candidate &b, int mode) {
  bool fa = (a.CV <= EPS), fb = (b.CV <= EPS);
  if (fa && !fb)
    return true;
  if (!fa && fb)
    return false;
  if (!fa && !fb)
    return a.CV < b.CV;
  return better_feasible(a.Z1, a.Z2, b.Z1, b.Z2, mode);
}

static bool dominates_2d(double a1, double a2, double b1, double b2) {
  return (a1 <= b1 && a2 <= b2 && (a1 < b1 || a2 < b2));
}

static vector<double> sample_w_profile(int mode, std::mt19937 &rng) {
  // mode 0: cost-leaning, mode 1: deprivation-leaning, mode 2: balanced.
  std::uniform_real_distribution<double> u01(0.0, 1.0);
  std::normal_distribution<double> n01(0.0, 1.0);

  vector<double> w(6, 0.5);
  if (mode == 0) {
    w = {0.45, 0.75, 0.70, 0.30, 0.80, 0.80};
  } else if (mode == 1) {
    w = {0.85, 0.35, 0.40, 0.85, 0.20, 0.35};
  } else {
    w = {0.62, 0.55, 0.52, 0.62, 0.55, 0.55};
  }

  for (double &x : w)
    x = std::clamp(x + 0.08 * n01(rng), 0.02, 0.98);

  if (u01(rng) < 0.15) {
    int idx = std::uniform_int_distribution<int>(0, 5)(rng);
    w[idx] = std::clamp(w[idx] + (u01(rng) < 0.5 ? -0.25 : 0.25), 0.02, 0.98);
  }
  return w;
}

static double elite_distance(const EliteEntry &a, const EliteEntry &b) {
  return std::abs(a.Z1 - b.Z1) + 10.0 * std::abs(a.Z2 - b.Z2);
}

static void update_elite_pool(vector<EliteEntry> &elite_pool,
                              const Candidate &cand,
                              int cap = 24,
                              double merge_eps = 1e-6) {
  if (cand.CV > EPS)
    return;

  EliteEntry e{cand.ind, cand.Z1, cand.Z2};

  for (const auto &x : elite_pool) {
    if (std::abs(x.Z1 - e.Z1) <= merge_eps && std::abs(x.Z2 - e.Z2) <= merge_eps)
      return;
  }

  for (const auto &x : elite_pool) {
    if (dominates_2d(x.Z1, x.Z2, e.Z1, e.Z2))
      return;
  }

  elite_pool.erase(std::remove_if(elite_pool.begin(), elite_pool.end(),
                                  [&](const EliteEntry &x) {
                                    return dominates_2d(e.Z1, e.Z2, x.Z1, x.Z2);
                                  }),
                   elite_pool.end());

  elite_pool.push_back(std::move(e));

  while ((int)elite_pool.size() > cap) {
    int drop_i = 0;
    double min_sep = std::numeric_limits<double>::infinity();
    for (int i = 0; i < (int)elite_pool.size(); ++i) {
      double nearest = std::numeric_limits<double>::infinity();
      for (int j = 0; j < (int)elite_pool.size(); ++j) {
        if (i == j)
          continue;
        nearest = std::min(nearest, elite_distance(elite_pool[i], elite_pool[j]));
      }
      if (nearest < min_sep) {
        min_sep = nearest;
        drop_i = i;
      }
    }
    elite_pool.erase(elite_pool.begin() + drop_i);
  }
}

static int hamming_x(const Individual &a, const Individual &b) {
  int d = 0;
  int n = std::min((int)a.X.size(), (int)b.X.size());
  for (int i = 0; i < n; ++i)
    if (a.X[i] != b.X[i])
      ++d;
  return d;
}

static void update_mode_bank(vector<EliteEntry> &bank,
                             const Candidate &cand,
                             int mode,
                             int cap = 8,
                             int min_hamming = 1) {
  if (cand.CV > EPS)
    return;

  EliteEntry e{cand.ind, cand.Z1, cand.Z2};

  for (const auto &x : bank) {
    if (hamming_x(x.ind, e.ind) < min_hamming &&
        std::abs(x.Z1 - e.Z1) < 1e-6 && std::abs(x.Z2 - e.Z2) < 1e-6)
      return;
  }

  bank.push_back(std::move(e));
  std::sort(bank.begin(), bank.end(), [&](const EliteEntry &a, const EliteEntry &b) {
    return better_feasible(a.Z1, a.Z2, b.Z1, b.Z2, mode);
  });

  vector<EliteEntry> kept;
  kept.reserve(std::min(cap, (int)bank.size()));
  for (const auto &x : bank) {
    bool diverse = true;
    for (const auto &y : kept) {
      if (hamming_x(x.ind, y.ind) < min_hamming) {
        diverse = false;
        break;
      }
    }
    if (diverse)
      kept.push_back(x);
    if ((int)kept.size() >= cap)
      break;
  }
  if (kept.empty() && !bank.empty())
    kept.push_back(bank.front());
  bank.swap(kept);
}

static long long key_swap(int close_ki, int open_ki) {
  return (1LL << 60) | ((long long)close_ki << 30) | (long long)open_ki;
}

static long long key_move(int ii, int from_ki, int to_ki) {
  return (2LL << 60) | ((long long)ii << 40) | ((long long)from_ki << 20) |
         (long long)to_ki;
}

static Individual initial_solution(const DRNDInstance &inst, std::mt19937 &rng,
                                   const vector<double> &exp_dem,
                                   int p) {
  Individual ind(inst.num_H, inst.num_I);
  std::fill(ind.X.begin(), ind.X.end(), 0);

  vector<pair<double, int>> hub_rank;
  hub_rank.reserve(inst.num_H);
  for (int ki = 0; ki < inst.num_H; ++ki) {
    int h = inst.hub_idx[ki];
    double score = 0.0;
    for (int ii = 0; ii < inst.num_I; ++ii) {
      int d = inst.demand_idx[ii];
      double dx = inst.lat[d] - inst.lat[h];
      double dy = inst.lon[d] - inst.lon[h];
      double dist = std::sqrt(dx * dx + dy * dy);
      score += exp_dem[ii] / (1.0 + dist);
    }
    hub_rank.push_back({score, ki});
  }
  std::sort(hub_rank.begin(), hub_rank.end(),
            [](const auto &a, const auto &b) { return a.first > b.first; });

  int top_band = std::max(p, std::min(inst.num_H, p + std::max(1, inst.num_H / 3)));
  vector<int> cand;
  for (int i = 0; i < top_band; ++i)
    cand.push_back(hub_rank[i].second);
  std::shuffle(cand.begin(), cand.end(), rng);

  for (int i = 0; i < p && i < (int)cand.size(); ++i)
    ind.X[cand[i]] = 1;
  if (opened_hubs(ind.X).empty())
    ind.X[hub_rank[0].second] = 1;

  assign_nearest_open_hub(ind, inst);
  repair_capacity(ind, inst, exp_dem, rng, 30);

  ind.W = sample_w_profile(2, rng);
  return ind;
}

static vector<Candidate> build_seed_candidates(const DRNDInstance &inst,
                                               const vector<double> &exp_dem,
                                               std::mt19937 &rng,
                                               ParetoArchive &archive,
                                               long long &eval_count) {
  vector<Candidate> seeds;

  if (inst.num_H <= 12) {
    int total = 1 << inst.num_H;
    // Paper §4.2: enumerate all hub configs; §4.3: use multiple assignment
    // strategies and W profiles to build a diverse, high-quality seed pool.
    for (int mask = 1; mask < total; ++mask) {
      // Two assignment strategies × 3 W-mode profiles per hub configuration.
      for (int strat = 0; strat < 2; ++strat) {
        for (int w_mode = 0; w_mode < 3; ++w_mode) {
          Candidate c;
          c.ind = Individual(inst.num_H, inst.num_I);
          for (int ki = 0; ki < inst.num_H; ++ki)
            c.ind.X[ki] = ((mask >> ki) & 1);
          if (strat == 0)
            assign_nearest_open_hub(c.ind, inst);   // distance-based (paper)
          else
            assign_min_cost_hub(c.ind, inst);        // cost-based (new)
          repair_capacity(c.ind, inst, exp_dem, rng, 40);
          c.ind.W = sample_w_profile(w_mode, rng);
          evaluate_candidate(c, inst, &archive);
          ++eval_count;
          if (c.CV <= EPS)
            seeds.push_back(c);
        }
      }
    }
  }

  if (seeds.empty()) {
    int pmax = std::max(1, std::min(inst.num_H, inst.num_H / 2 + 1));
    for (int t = 0; t < 16; ++t) {
      Candidate c;
      int p = std::uniform_int_distribution<int>(1, pmax)(rng);
      c.ind = initial_solution(inst, rng, exp_dem, p);
      evaluate_candidate(c, inst, &archive);
      ++eval_count;
      if (c.CV <= EPS)
        seeds.push_back(c);
    }
  }

  std::sort(seeds.begin(), seeds.end(), [](const Candidate &a, const Candidate &b) {
    if (a.Z1 != b.Z1)
      return a.Z1 < b.Z1;
    return a.Z2 < b.Z2;
  });

  if ((int)seeds.size() > 32)
    seeds.resize(32);
  return seeds;
}

static bool op_swap_hub(const Candidate &base, Candidate &out,
                        const DRNDInstance &inst,
                        const vector<double> &exp_dem,
                        std::mt19937 &rng) {
  auto open = opened_hubs(base.ind.X);
  if (open.empty() || (int)open.size() == inst.num_H)
    return false;

  vector<int> closed;
  for (int ki = 0; ki < inst.num_H; ++ki)
    if (!base.ind.X[ki])
      closed.push_back(ki);
  if (closed.empty())
    return false;

  int close_ki = open[std::uniform_int_distribution<int>(0, (int)open.size() - 1)(rng)];
  int open_ki = closed[std::uniform_int_distribution<int>(0, (int)closed.size() - 1)(rng)];

  out = base;
  out.ind.X[close_ki] = 0;
  out.ind.X[open_ki] = 1;
  assign_nearest_open_hub(out.ind, inst);
  repair_capacity(out.ind, inst, exp_dem, rng, 30);
  out.move_key = key_swap(close_ki, open_ki);
  return true;
}

static bool op_move_node(const Candidate &base, Candidate &out,
                         const DRNDInstance &inst,
                         const vector<double> &exp_dem,
                         int mode,
                         std::mt19937 &rng) {
  auto open = opened_hubs(base.ind.X);
  if ((int)open.size() <= 1)
    return false;

  out = base;

  int picked_ii = std::uniform_int_distribution<int>(0, inst.num_I - 1)(rng);
  int from_ki = out.ind.A[picked_ii];

  int d = inst.demand_idx[picked_ii];
  int best_to = from_ki;
  double best_score = std::numeric_limits<double>::infinity();

  vector<double> load(inst.num_H, 0.0);
  for (int ii = 0; ii < inst.num_I; ++ii) {
    int ki = out.ind.A[ii];
    if (ki >= 0 && ki < inst.num_H && out.ind.X[ki])
      load[ki] += inst.gamma * exp_dem[ii];
  }

  for (int ki : open) {
    if (ki == from_ki)
      continue;
    int h = inst.hub_idx[ki];
    double dx = inst.lat[d] - inst.lat[h];
    double dy = inst.lon[d] - inst.lon[h];
    double dist2 = dx * dx + dy * dy;
    double next_load = load[ki] + inst.gamma * exp_dem[picked_ii];
    double cap_ratio = (inst.kappa[ki] > EPS) ? (next_load / inst.kappa[ki]) : 1e9;
    double cap_penalty = std::max(0.0, cap_ratio - 1.0);
    double urgency = inst.lambda[picked_ii][0] * exp_dem[picked_ii];
    double score = dist2 + 1e5 * cap_penalty;
    if (mode == 1)
      score = 0.55 * dist2 + 0.45 * (1.0 / (urgency + 1e-6)) + 8e4 * cap_penalty;
    else if (mode == 2)
      score = 0.8 * dist2 + 0.2 * (1.0 / (urgency + 1e-6)) + 9e4 * cap_penalty;
    score += std::uniform_real_distribution<double>(0.0, 1e-3)(rng);
    if (score < best_score) {
      best_score = score;
      best_to = ki;
    }
  }
  if (best_to == from_ki)
    return false;

  out.ind.A[picked_ii] = best_to;
  repair_capacity(out.ind, inst, exp_dem, rng, 8);
  out.move_key = key_move(picked_ii, from_ki, best_to);
  return true;
}

static bool op_perturb_rw(const Candidate &base, Candidate &out,
                          const DRNDInstance &inst,
                          const vector<double> &exp_dem,
                          int mode,
                          std::mt19937 &rng) {
  out = base;
  std::normal_distribution<double> n01(0.0, 1.0);
  auto open = opened_hubs(out.ind.X);
  if (open.empty())
    return false;

  int edits = std::max(1, (int)open.size() / 2);
  for (int t = 0; t < edits; ++t) {
    int ki = open[std::uniform_int_distribution<int>(0, (int)open.size() - 1)(rng)];
    out.ind.R[ki] = std::clamp(out.ind.R[ki] + 0.12 * n01(rng), 0.0, 1.0);
  }

  reconstruct_R(out.ind, inst, exp_dem);
  for (int t = 0; t < edits; ++t) {
    int ki = open[std::uniform_int_distribution<int>(0, (int)open.size() - 1)(rng)];
    out.ind.R[ki] = std::clamp(out.ind.R[ki] + 0.08 * n01(rng), 0.0, 1.0);
  }

  vector<double> w_target = sample_w_profile(mode, rng);
  for (int i = 0; i < 6; ++i)
    out.ind.W[i] = std::clamp(0.7 * out.ind.W[i] + 0.3 * w_target[i], 0.02, 0.98);

  out.move_key = (3LL << 60) | std::uniform_int_distribution<int>(0, (1 << 20) - 1)(rng);
  return true;
}

// Directly adjust R (pre-positioning ratio) for one open hub.
// This is the key operator for exploring inventory levels — paper §4.3
// "allocation" neighborhood adapted to our bi-objective stochastic setting.
// NOTE: Does NOT call reconstruct_R, so the chosen R value is preserved.
static bool op_adjust_r(const Candidate &base, Candidate &out,
                         const DRNDInstance &inst, std::mt19937 &rng) {
  auto open = opened_hubs(base.ind.X);
  if (open.empty())
    return false;
  out = base;
  // Discrete R levels to explore; 0.0 means rely entirely on origin supply.
  static const double r_levels[] = {0.0, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0};
  static const int n_levels = 9;
  int ki = open[std::uniform_int_distribution<int>(0, (int)open.size() - 1)(rng)];
  int ri = std::uniform_int_distribution<int>(0, n_levels - 1)(rng);
  out.ind.R[ki] = r_levels[ri];
  out.move_key = (5LL << 60) | ((long long)ki << 30) | ri;
  return true;
}

static bool path_relink_to_target(const Candidate &base, Candidate &out,
                                  const Individual &target,
                                  const DRNDInstance &inst,
                                  const vector<double> &exp_dem,
                                  int mode,
                                  std::mt19937 &rng) {

  Candidate cur = base;
  Candidate best = base;
  evaluate_candidate(cur, inst, nullptr);
  evaluate_candidate(best, inst, nullptr);

  const int max_steps = std::max(3, inst.num_H + inst.num_I / 2);
  bool made_move = false;

  for (int step = 0; step < max_steps; ++step) {
    vector<int> diff_open_close;
    vector<int> diff_open_add;
    for (int ki = 0; ki < inst.num_H; ++ki) {
      if (cur.ind.X[ki] == 1 && target.X[ki] == 0)
        diff_open_close.push_back(ki);
      if (cur.ind.X[ki] == 0 && target.X[ki] == 1)
        diff_open_add.push_back(ki);
    }

    bool step_done = false;
    if (!diff_open_close.empty() && !diff_open_add.empty()) {
      int close_ki = diff_open_close[
          std::uniform_int_distribution<int>(0, (int)diff_open_close.size() - 1)(rng)];
      int open_ki = diff_open_add[
          std::uniform_int_distribution<int>(0, (int)diff_open_add.size() - 1)(rng)];
      cur.ind.X[close_ki] = 0;
      cur.ind.X[open_ki] = 1;
      assign_nearest_open_hub(cur.ind, inst);
      repair_capacity(cur.ind, inst, exp_dem, rng, 20);
      cur.move_key = key_swap(close_ki, open_ki);
      step_done = true;
    } else {
      vector<int> diff_assign;
      for (int ii = 0; ii < inst.num_I; ++ii) {
        if (cur.ind.A[ii] != target.A[ii] && cur.ind.X[target.A[ii]])
          diff_assign.push_back(ii);
      }
      if (!diff_assign.empty()) {
        int ii = diff_assign[
            std::uniform_int_distribution<int>(0, (int)diff_assign.size() - 1)(rng)];
        int from_ki = cur.ind.A[ii];
        int to_ki = target.A[ii];
        cur.ind.A[ii] = to_ki;
        repair_capacity(cur.ind, inst, exp_dem, rng, 10);
        cur.move_key = key_move(ii, from_ki, to_ki);
        step_done = true;
      }
    }

    if (!step_done)
      break;

    made_move = true;
    evaluate_candidate(cur, inst, nullptr);
    if (better_candidate(cur, best, mode))
      best = cur;
  }

  if (!made_move)
    return false;

  out = best;
  return true;
}

static bool op_path_relink_lite(const Candidate &base, Candidate &out,
                                const DRNDInstance &inst,
                                const vector<double> &exp_dem,
                                const vector<EliteEntry> &elite_pool,
                                int mode,
                                std::mt19937 &rng) {
  if (elite_pool.empty())
    return false;

  const Individual &target = elite_pool[
      std::uniform_int_distribution<int>(0, (int)elite_pool.size() - 1)(rng)]
                               .ind;
  return path_relink_to_target(base, out, target, inst, exp_dem, mode, rng);
}

static bool op_mode_bank_relink(const Candidate &base, Candidate &out,
                                const DRNDInstance &inst,
                                const vector<double> &exp_dem,
                                const vector<EliteEntry> &mode_bank,
                                int mode,
                                std::mt19937 &rng) {
  if (mode_bank.empty())
    return false;

  vector<int> cand_idx;
  for (int i = 0; i < (int)mode_bank.size(); ++i) {
    if (hamming_x(base.ind, mode_bank[i].ind) > 0)
      cand_idx.push_back(i);
  }
  if (cand_idx.empty())
    return false;

  int idx = cand_idx[std::uniform_int_distribution<int>(0, (int)cand_idx.size() - 1)(rng)];
  return path_relink_to_target(base, out, mode_bank[idx].ind, inst, exp_dem,
                               mode, rng);
}

static Candidate ts_local_search(
    const Candidate &start, const DRNDInstance &inst,
    const vector<double> &exp_dem, int mode, int tabu_tenure,
    int ls_iter, int nhood_samples,
    std::unordered_map<long long, int> &tabu_until,
    int iter_idx, const Candidate &global_best,
    const vector<EliteEntry> &elite_pool,
    const vector<EliteEntry> &mode_bank,
  bool enable_option3,
    std::mt19937 &rng,
    ParetoArchive &archive, long long &eval_count) {

  Candidate current = start;
  Candidate best_seen = start;

  for (int ls = 0; ls < ls_iter; ++ls) {
    bool found = false;
    Candidate best_nb;

    for (int t = 0; t < nhood_samples; ++t) {
      Candidate cand;
      bool ok = false;
      // op_adjust_r is always available as operator 4 (R-level exploration).
      int which = std::uniform_int_distribution<int>(1, enable_option3 ? 6 : 5)(rng);
      if (which == 1)
        ok = op_swap_hub(current, cand, inst, exp_dem, rng);
      else if (which == 2)
        ok = op_move_node(current, cand, inst, exp_dem, mode, rng);
      else if (which == 3)
        ok = op_path_relink_lite(current, cand, inst, exp_dem, elite_pool, mode,
                                 rng);
      else if (which == 4)
        ok = op_adjust_r(current, cand, inst, rng);
      else if (which == 5 && enable_option3)
        ok = op_mode_bank_relink(current, cand, inst, exp_dem, mode_bank, mode,
                                 rng);
      else
        ok = op_perturb_rw(current, cand, inst, exp_dem, mode, rng);
      if (!ok)
        continue;

      evaluate_candidate(cand, inst, &archive);
      ++eval_count;

      bool tabu = false;
      auto it = tabu_until.find(cand.move_key);
      if (it != tabu_until.end() && it->second > iter_idx)
        tabu = true;

      bool aspiration = better_candidate(cand, global_best, mode);
      if (tabu && !aspiration)
        continue;

      if (!found || better_candidate(cand, best_nb, mode)) {
        best_nb = cand;
        found = true;
      }
    }

    if (!found)
      break;

    current = best_nb;
    tabu_until[current.move_key] = iter_idx + tabu_tenure;

    if (better_candidate(current, best_seen, mode))
      best_seen = current;
  }

  return best_seen;
}

int main(int argc, char *argv[]) {
  if (argc < 2) {
    cerr << "Usage: vns_ts_baseline <instance.json> [--out <path>] [--seed S] "
            "[--iter N] [--time-limit S] [--tabu-tenure T] [--kmax K] [--starts R] "
            "[--enable-option3]\n";
    return 1;
  }

  string inst_path = argv[1];
  string out_path = "";
  int seed = 42;
  int max_iter = 120;
  double time_limit = 60.0;
  int tabu_tenure = 7;
  int kmax = 3;
  int starts = 8;
  bool enable_option3 = false;

  for (int i = 2; i < argc; ++i) {
    string arg = argv[i];
    if (arg == "--out" && i + 1 < argc)
      out_path = argv[++i];
    else if (arg == "--seed" && i + 1 < argc)
      seed = std::stoi(argv[++i]);
    else if (arg == "--iter" && i + 1 < argc)
      max_iter = std::stoi(argv[++i]);
    else if (arg == "--time-limit" && i + 1 < argc)
      time_limit = std::stod(argv[++i]);
    else if (arg == "--tabu-tenure" && i + 1 < argc)
      tabu_tenure = std::stoi(argv[++i]);
    else if (arg == "--kmax" && i + 1 < argc)
      kmax = std::stoi(argv[++i]);
    else if (arg == "--starts" && i + 1 < argc)
      starts = std::max(1, std::stoi(argv[++i]));
    else if (arg == "--enable-option3")
      enable_option3 = true;
  }

  DRNDInstance inst;
  try {
    inst = load_instance(inst_path);
  } catch (const std::exception &e) {
    cerr << "Error loading instance: " << e.what() << "\n";
    return 1;
  }

  std::mt19937 rng(seed);
  ParetoArchive archive;
  const auto exp_dem = expected_demand(inst);

  auto t0 = Clock::now();
  std::clock_t c0 = std::clock();

  long long eval_count = 0;
  vector<int> modes = {0, 1, 2};
  vector<EliteEntry> elite_pool;
  vector<vector<EliteEntry>> mode_banks(3);
  vector<Candidate> seed_pool = build_seed_candidates(inst, exp_dem, rng, archive, eval_count);

  for (int mode : modes) {
    for (int rs = 0; rs < starts; ++rs) {
      if (Duration(Clock::now() - t0).count() > time_limit)
        break;

      Candidate current;
      if (!seed_pool.empty()) {
        current = seed_pool[std::uniform_int_distribution<int>(0, (int)seed_pool.size() - 1)(rng)];
        current.ind.W = sample_w_profile(mode, rng);
        evaluate_candidate(current, inst, &archive);
        ++eval_count;
      } else {
        int pmax = std::max(1, std::min(inst.num_H, inst.num_H / 2 + 1));
        int p = std::uniform_int_distribution<int>(1, pmax)(rng);
        current.ind = initial_solution(inst, rng, exp_dem, p);
        current.ind.W = sample_w_profile(mode, rng);
        evaluate_candidate(current, inst, &archive);
        ++eval_count;
      }
      update_elite_pool(elite_pool, current);
      if (enable_option3)
        update_mode_bank(mode_banks[mode], current, mode);

      Candidate best = current;
      std::unordered_map<long long, int> tabu_until;

      for (int it = 0; it < max_iter; ++it) {
        if (Duration(Clock::now() - t0).count() > time_limit)
          break;

        int k = 1;
        bool moved = false;

        while (k <= std::max(1, kmax)) {
          Candidate shaken;
          bool ok = false;
          if (k == 1)
            ok = op_swap_hub(current, shaken, inst, exp_dem, rng);
          else if (k == 2)
            ok = op_move_node(current, shaken, inst, exp_dem, mode, rng);
          else if (k == 3)
            ok = op_path_relink_lite(current, shaken, inst, exp_dem, elite_pool,
                                     mode, rng);
          else
            ok = op_perturb_rw(current, shaken, inst, exp_dem, mode, rng);

          if (!ok) {
            ++k;
            continue;
          }

          evaluate_candidate(shaken, inst, &archive);
          ++eval_count;
          update_elite_pool(elite_pool, shaken);
          if (enable_option3)
            update_mode_bank(mode_banks[mode], shaken, mode);

          Candidate local_best = ts_local_search(
              shaken, inst, exp_dem, mode, tabu_tenure,
              16, 20, tabu_until, it, best, elite_pool, mode_banks[mode],
              enable_option3, rng,
              archive, eval_count);
            update_elite_pool(elite_pool, local_best);
            if (enable_option3)
              update_mode_bank(mode_banks[mode], local_best, mode);

          if (better_candidate(local_best, current, mode)) {
            current = local_best;
            moved = true;
            if (better_candidate(current, best, mode)) {
              best = current;
              k = 1;
            } else {
              ++k;
            }
          } else {
            // TS accepts non-improving move occasionally to diversify.
            if (std::uniform_real_distribution<double>(0.0, 1.0)(rng) < 0.15) {
              current = local_best;
              moved = true;
            }
            ++k;
          }
        }

        // Paper §4.5: run for T_max or max_iter — do NOT break early.
        // When no move was accepted, diversify via perturbation (VNS restart).
        if (!moved) {
          Candidate perturbed;
          if (op_perturb_rw(current, perturbed, inst, exp_dem, mode, rng)) {
            evaluate_candidate(perturbed, inst, &archive);
            ++eval_count;
            update_elite_pool(elite_pool, perturbed);
            current = perturbed; // force diversification regardless of quality
          }
        }
      }

      update_elite_pool(elite_pool, best);
      if (enable_option3)
        update_mode_bank(mode_banks[mode], best, mode);
    }
  }

  auto front = archive.front;
  std::sort(front.begin(), front.end(), [](const Solution &a, const Solution &b) {
    return a.Z1 < b.Z1 || (a.Z1 == b.Z1 && a.Z2 < b.Z2);
  });
  front.erase(std::unique(front.begin(), front.end(), [](const Solution &a, const Solution &b) {
                return std::abs(a.Z1 - b.Z1) < 1e-6 && std::abs(a.Z2 - b.Z2) < 1e-6;
              }),
              front.end());

  const double elapsed = Duration(Clock::now() - t0).count();
  const double cpu_s = 1.0 * (std::clock() - c0) / CLOCKS_PER_SEC;

  json j;
  j["meta"]["solver"] = "VNS-TS-Baseline";
  j["meta"]["elapsed_s"] = elapsed;
  j["meta"]["cpu_time_s"] = cpu_s;
  j["meta"]["seed"] = seed;
  j["meta"]["iter"] = max_iter;
  j["meta"]["tabu_tenure"] = tabu_tenure;
  j["meta"]["kmax"] = kmax;
  j["meta"]["starts"] = starts;
  j["meta"]["enable_option3"] = enable_option3;
  j["meta"]["evaluations"] = eval_count;
  j["meta"]["pareto_size"] = (int)front.size();

  json jfront = json::array();
  for (const auto &s : front) {
    json js;
    js["Z1"] = s.Z1;
    js["Z2"] = s.Z2;
    js["CV"] = 0.0;
    js["rank"] = 1;
    js["X"] = s.X;
    js["R"] = s.R;
    js["A"] = s.A;
    js["W"] = s.W;
    jfront.push_back(std::move(js));
  }
  j["pareto_front"] = jfront;
  j["all_feasible"] = jfront;

  if (out_path.empty() || out_path == "-") {
    cout << j.dump(2) << "\n";
  } else {
    std::ofstream f(out_path);
    if (!f.is_open()) {
      cerr << "Cannot open output: " << out_path << "\n";
      return 1;
    }
    f << j.dump(2) << "\n";
    cerr << "[Output] " << out_path << "\n";
  }

  cerr << "[VNS-TS] Pareto size=" << front.size() << ", evals=" << eval_count
       << ", elapsed=" << elapsed << " s\n";
  return 0;
}
