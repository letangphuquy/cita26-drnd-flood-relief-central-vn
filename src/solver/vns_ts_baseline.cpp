// vns_ts_baseline.cpp
// -----------------------------------------------------------------------------
// VNS-TS baseline aligned to Sangsawang & Chanta (Comput Optim Appl):
//   - Array solution representation.
//   - Initialization with random p and high-flow-biased hub set.
//   - Three neighborhood structures: intra-cluster, inter-cluster, allocation.
//   - VNS shaking + TS local search with tabu list on (node, hub) allocations.
//   - Stopping by Tmax and/or max iterations.
//
// Problem-specific adaptation:
//   This project solves MO-IHLNDP with decoder-based evaluation. We keep the
//   paper search framework and adapt move operators/feasibility repair to the
//   project representation (X, R, A, W) and constraints.
// -----------------------------------------------------------------------------

#include "decoder.hpp"

#include <algorithm>
#include <chrono>
#include <ctime>
#include <fstream>
#include <limits>
#include <numeric>
#include <random>

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

static void ensure_open_hub(Individual &ind, std::mt19937 &rng) {
  if (!opened_hubs(ind.X).empty())
    return;
  std::uniform_int_distribution<int> ud(0, (int)ind.X.size() - 1);
  ind.X[ud(rng)] = 1;
}

static void assign_nearest_anchors(Individual &ind, const DRNDInstance &inst) {
  auto open_ki = opened_hubs(ind.X);
  if (open_ki.empty()) {
    std::fill(ind.A.begin(), ind.A.end(), 0);
    return;
  }
  for (int ii = 0; ii < inst.num_I; ++ii) {
    int di = inst.demand_idx[ii];
    double best = 1e100;
    int best_ki = open_ki[0];
    for (int ki : open_ki) {
      int hi = inst.hub_idx[ki];
      double dx = inst.lat[di] - inst.lat[hi];
      double dy = inst.lon[di] - inst.lon[hi];
      double d2 = dx * dx + dy * dy;
      if (d2 < best) {
        best = d2;
        best_ki = ki;
      }
    }
    ind.A[ii] = best_ki;
  }
}

static vector<double> expected_demand(const DRNDInstance &inst) {
  vector<double> e(inst.num_I, 0.0);
  for (int si = 0; si < inst.num_S; ++si) {
    double p = inst.scenarios[si].prob;
    for (int ii = 0; ii < inst.num_I; ++ii) {
      int di = inst.demand_idx[ii];
      e[ii] += p * inst.scenarios[si].demand[di];
    }
  }
  return e;
}

static vector<double> flow_score_hubs(const DRNDInstance &inst,
                                      const vector<double> &exp_dem) {
  vector<double> score(inst.num_H, 0.0);
  for (int ki = 0; ki < inst.num_H; ++ki) {
    int h = inst.hub_idx[ki];
    double s = 0.0;
    for (int ii = 0; ii < inst.num_I; ++ii) {
      int d = inst.demand_idx[ii];
      double dx = inst.lat[d] - inst.lat[h];
      double dy = inst.lon[d] - inst.lon[h];
      double dist = std::sqrt(dx * dx + dy * dy);
      s += exp_dem[ii] / (1.0 + dist);
    }
    score[ki] = s;
  }
  return score;
}

static void refresh_R_from_assignments(Individual &ind, const DRNDInstance &inst,
                                       const vector<double> &exp_dem) {
  vector<double> load(inst.num_H, 0.0);
  for (int ii = 0; ii < inst.num_I; ++ii) {
    int ki = ind.A[ii];
    if (0 <= ki && ki < inst.num_H && ind.X[ki])
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
    ratio = std::max(0.0, std::min(1.0, ratio));
    ind.R[ki] = ratio;
  }
}

static void repair_capacity(Individual &ind, const DRNDInstance &inst,
                            const vector<double> &exp_dem, std::mt19937 &rng,
                            int max_moves = 3) {
  auto open_ki = opened_hubs(ind.X);
  if (open_ki.size() <= 1)
    return;

  std::uniform_int_distribution<int> ud(0, (int)open_ki.size() - 1);

  for (int mv = 0; mv < max_moves; ++mv) {
    vector<double> load(inst.num_H, 0.0);
    for (int ii = 0; ii < inst.num_I; ++ii)
      if (ind.X[ind.A[ii]])
        load[ind.A[ii]] += inst.gamma * exp_dem[ii];

    int over = -1;
    double worst_ratio = 1.0;
    for (int ki : open_ki) {
      if (inst.kappa[ki] <= EPS)
        continue;
      double ratio = load[ki] / inst.kappa[ki];
      if (ratio > worst_ratio + 1e-9) {
        worst_ratio = ratio;
        over = ki;
      }
    }
    if (over < 0)
      break;

    vector<int> spokes;
    for (int ii = 0; ii < inst.num_I; ++ii)
      if (ind.A[ii] == over)
        spokes.push_back(ii);
    if (spokes.empty())
      break;

    int ii = spokes[std::uniform_int_distribution<int>(0, (int)spokes.size() - 1)(rng)];
    int best_alt = over;
    double best_dist = std::numeric_limits<double>::infinity();
    int d = inst.demand_idx[ii];
    for (int ki : open_ki) {
      if (ki == over)
        continue;
      int h = inst.hub_idx[ki];
      double dx = inst.lat[d] - inst.lat[h];
      double dy = inst.lon[d] - inst.lon[h];
      double d2 = dx * dx + dy * dy;
      if (d2 < best_dist) {
        best_dist = d2;
        best_alt = ki;
      }
    }
    if (best_alt != over)
      ind.A[ii] = best_alt;
    else
      ind.A[ii] = open_ki[ud(rng)];
  }

  refresh_R_from_assignments(ind, inst, exp_dem);
}

static double scalar_score(const Individual &ind, double lambda) {
  // Simple fixed scaling to keep both objectives active in search.
  const double z2_scale = 5.0;
  return lambda * ind.Z1 + (1.0 - lambda) * (z2_scale * ind.Z2) + 1e6 * ind.CV;
}

static bool eval_candidate(Individual &ind, const DRNDInstance &inst,
                           ParetoArchive &archive) {
  decode(ind, inst);
  if (ind.CV <= EPS) {
    Solution s;
    s.Z1 = ind.Z1;
    s.Z2 = ind.Z2;
    s.X = ind.X;
    s.R = ind.R;
    s.A = ind.A;
    s.W = ind.W;
    archive.add(std::move(s));
    return true;
  }
  return false;
}

static Individual enum_hubset_seed(const DRNDInstance &inst,
                                   const vector<double> &exp_dem,
                                   double lambda,
                                   ParetoArchive &archive,
                                   long long &eval_count,
                                   std::mt19937 &rng) {
  Individual best(inst.num_H, inst.num_I);
  best.CV = std::numeric_limits<double>::infinity();
  double best_sc = std::numeric_limits<double>::infinity();
  bool found = false;

  if (inst.num_H > 20)
    return best;

  const vector<vector<double>> w_presets = {
      {0.8, 0.4, 0.6, 0.6, 0.8, 0.6},
      {0.7, 0.6, 0.5, 0.5, 0.7, 0.5},
      {0.5, 0.5, 0.5, 0.5, 0.5, 0.5},
      {0.3, 0.7, 0.5, 0.7, 0.6, 0.7},
      {0.9, 0.2, 0.4, 0.4, 0.9, 0.4},
  };

  const int total = 1 << inst.num_H;
  for (int mask = 1; mask < total; ++mask) {
    for (const auto &w : w_presets) {
      Individual cand(inst.num_H, inst.num_I);
      for (int ki = 0; ki < inst.num_H; ++ki)
        cand.X[ki] = ((mask >> ki) & 1);

      assign_nearest_anchors(cand, inst);
      repair_capacity(cand, inst, exp_dem, rng, 8);
      cand.W = w;

      eval_candidate(cand, inst, archive);
      ++eval_count;
      if (cand.CV > EPS)
        continue;

      double sc = scalar_score(cand, lambda);
      if (!found || sc + 1e-9 < best_sc) {
        found = true;
        best = cand;
        best_sc = sc;
      }
    }
  }
  return best;
}

static Individual initial_solution(const DRNDInstance &inst, std::mt19937 &rng,
                                   const vector<double> &hub_flow_score,
                                   const vector<double> &exp_dem,
                                   ParetoArchive &archive) {
  std::uniform_int_distribution<int> p_dist(
      1, std::max(1, std::min(inst.num_H, inst.num_H / 2 + 1)));
  std::uniform_real_distribution<double> u01(0.0, 1.0);

  vector<int> hubs(inst.num_H);
  std::iota(hubs.begin(), hubs.end(), 0);
  std::stable_sort(hubs.begin(), hubs.end(), [&](int a, int b) {
    return hub_flow_score[a] > hub_flow_score[b];
  });

  Individual best(inst.num_H, inst.num_I);
  double best_cv = std::numeric_limits<double>::infinity();

  for (int trial = 0; trial < 24; ++trial) {
    Individual ind(inst.num_H, inst.num_I);
    int p = p_dist(rng);

    // Flow-ranked hub set with mild randomization among top candidates.
    int top_band = std::min(inst.num_H, std::max(p, p + inst.num_H / 4));
    vector<int> pick(hubs.begin(), hubs.begin() + top_band);
    std::shuffle(pick.begin(), pick.end(), rng);
    for (int i = 0; i < p; ++i)
      ind.X[pick[i]] = 1;

    ensure_open_hub(ind, rng);
    assign_nearest_anchors(ind, inst);
    repair_capacity(ind, inst, exp_dem, rng, 8);

    ind.W = {0.5 + 0.2 * (u01(rng) - 0.5), 0.5, 0.5,
             0.5 + 0.2 * (u01(rng) - 0.5), 0.5, 0.5};

    eval_candidate(ind, inst, archive);
    if (ind.CV < best_cv) {
      best_cv = ind.CV;
      best = ind;
      if (ind.CV <= EPS)
        break;
    }
  }
  return best;
}

static bool apply_intra_cluster_move(Individual &cand, const DRNDInstance &inst,
                                     std::mt19937 &rng,
                                     const vector<double> &exp_dem) {
  auto open_ki = opened_hubs(cand.X);
  if (open_ki.empty())
    return false;

  int from = open_ki[std::uniform_int_distribution<int>(0, (int)open_ki.size() - 1)(rng)];
  vector<int> cluster;
  for (int ii = 0; ii < inst.num_I; ++ii)
    if (cand.A[ii] == from)
      cluster.push_back(ii);
  if (cluster.empty())
    return false;

  // Problem-specific analogue: replace hub with a nearby closed candidate.
  int best_closed = -1;
  double best_d2 = std::numeric_limits<double>::infinity();
  for (int ki = 0; ki < inst.num_H; ++ki) {
    if (cand.X[ki])
      continue;
    int h = inst.hub_idx[ki];
    double acc = 0.0;
    for (int ii : cluster) {
      int d = inst.demand_idx[ii];
      double dx = inst.lat[d] - inst.lat[h];
      double dy = inst.lon[d] - inst.lon[h];
      acc += dx * dx + dy * dy;
    }
    if (acc < best_d2) {
      best_d2 = acc;
      best_closed = ki;
    }
  }
  if (best_closed < 0)
    return false;

  cand.X[from] = 0;
  cand.X[best_closed] = 1;
  assign_nearest_anchors(cand, inst);
  repair_capacity(cand, inst, exp_dem, rng, 4);
  return true;
}

static bool apply_inter_cluster_move(Individual &cand, const DRNDInstance &inst,
                                     std::mt19937 &rng,
                                     const vector<double> &exp_dem) {
  auto open_ki = opened_hubs(cand.X);
  if (open_ki.empty() || (int)open_ki.size() == inst.num_H)
    return false;

  int from = open_ki[std::uniform_int_distribution<int>(0, (int)open_ki.size() - 1)(rng)];
  vector<int> closed;
  for (int ki = 0; ki < inst.num_H; ++ki)
    if (!cand.X[ki])
      closed.push_back(ki);
  if (closed.empty())
    return false;

  int to = closed[std::uniform_int_distribution<int>(0, (int)closed.size() - 1)(rng)];
  cand.X[from] = 0;
  cand.X[to] = 1;
  assign_nearest_anchors(cand, inst);
  repair_capacity(cand, inst, exp_dem, rng, 4);
  return true;
}

static bool apply_allocation_move(Individual &cand, const DRNDInstance &inst,
                                  std::mt19937 &rng,
                                  const vector<double> &exp_dem,
                                  pair<int, int> *alloc_pair = nullptr) {
  auto open_ki = opened_hubs(cand.X);
  if (open_ki.size() <= 1)
    return false;

  int ii = std::uniform_int_distribution<int>(0, inst.num_I - 1)(rng);
  int cur = cand.A[ii];
  int to = cur;
  for (int tries = 0; tries < 8 && to == cur; ++tries)
    to = open_ki[std::uniform_int_distribution<int>(0, (int)open_ki.size() - 1)(rng)];
  if (to == cur)
    return false;

  cand.A[ii] = to;
  refresh_R_from_assignments(cand, inst, exp_dem);
  repair_capacity(cand, inst, exp_dem, rng, 2);
  if (alloc_pair)
    *alloc_pair = {ii, to};
  return true;
}

static bool shake_by_k(Individual &cand, int k, const DRNDInstance &inst,
                       std::mt19937 &rng, const vector<double> &exp_dem,
                       pair<int, int> *alloc_pair = nullptr) {
  if (k == 1)
    return apply_intra_cluster_move(cand, inst, rng, exp_dem);
  if (k == 2)
    return apply_inter_cluster_move(cand, inst, rng, exp_dem);
  return apply_allocation_move(cand, inst, rng, exp_dem, alloc_pair);
}

static Individual ts_local_search(const Individual &start, const DRNDInstance &inst,
                                  std::mt19937 &rng,
                                  const vector<double> &exp_dem,
                                  vector<vector<int>> &tabu_until,
                                  int iter_idx,
                                  int tabu_tenure,
                                  double lambda,
                                  double best_score,
                                  ParetoArchive &archive,
                                  long long &eval_count,
                                  pair<int, int> *accepted_pair = nullptr) {
  Individual current = start;
  eval_candidate(current, inst, archive);
  ++eval_count;

  Individual best_nb = current;
  double best_nb_sc = std::numeric_limits<double>::infinity();
  pair<int, int> best_pair = {-1, -1};
  bool found_admissible = false;

  for (int nk = 1; nk <= 3; ++nk) {
    for (int s = 0; s < 12; ++s) {
      Individual cand = current;
      pair<int, int> moved = {-1, -1};
      if (!shake_by_k(cand, nk, inst, rng, exp_dem, &moved))
        continue;

      eval_candidate(cand, inst, archive);
      ++eval_count;
      if (cand.CV > EPS)
        continue;
      double sc = scalar_score(cand, lambda);

      bool tabu = false;
      if (moved.first >= 0 && moved.second >= 0)
        tabu = (tabu_until[moved.first][moved.second] > iter_idx);
      bool aspiration = (sc + 1e-9 < best_score);
      if (tabu && !aspiration)
        continue;

      if (!found_admissible || sc + 1e-9 < best_nb_sc) {
        best_nb = cand;
        best_nb_sc = sc;
        best_pair = moved;
        found_admissible = true;
      }
    }
  }

  // If all candidates were tabu and non-aspiring, stay at current.
  if (!found_admissible) {
    best_nb = current;
    best_nb_sc = scalar_score(current, lambda);
    best_pair = {-1, -1};
  }

  if (accepted_pair)
    *accepted_pair = best_pair;

  if (best_pair.first >= 0 && best_pair.second >= 0)
    tabu_until[best_pair.first][best_pair.second] = iter_idx + tabu_tenure;

  return best_nb;
}

int main(int argc, char *argv[]) {
  if (argc < 2) {
    cerr << "Usage: vns_ts_baseline <instance.json> [--out <path>] [--seed S] "
            "[--iter N] [--time-limit S] [--tabu-tenure T] [--kmax K]\n";
    return 1;
  }

  string inst_path = argv[1];
  string out_path = "";
  int seed = 42;
  int max_iter = 100;
  double time_limit = 300.0;
  int tabu_tenure = 7;
  int kmax = 3;
  int starts = 5;

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
  const auto hub_flow_score = flow_score_hubs(inst, exp_dem);

  auto t0 = Clock::now();
  std::clock_t c0 = std::clock();

  vector<double> lambdas = {0.5, 0.8, 0.95, 0.98};
  long long eval_count = 0;

  for (double lambda : lambdas) {
    Individual enum_seed =
        enum_hubset_seed(inst, exp_dem, lambda, archive, eval_count, rng);

    for (int start = 0; start < starts; ++start) {
      if (Duration(Clock::now() - t0).count() > time_limit)
        break;

      Individual current =
          (start == 0 && enum_seed.CV <= EPS)
              ? enum_seed
              : initial_solution(inst, rng, hub_flow_score, exp_dem, archive);
      Individual best = current;

      vector<vector<int>> tabu_until(inst.num_I, vector<int>(inst.num_H, -1));

      for (int it = 0; it < max_iter; ++it) {
        if (Duration(Clock::now() - t0).count() > time_limit)
          break;

        int k = 1;
        bool moved_in_iter = false;

        while (k <= std::max(1, kmax)) {
          if (Duration(Clock::now() - t0).count() > time_limit)
            break;

          Individual shaken = current;
          if (!shake_by_k(shaken, k, inst, rng, exp_dem)) {
            ++k;
            continue;
          }

          pair<int, int> accepted_pair = {-1, -1};
          const double best_score = scalar_score(best, lambda);
          Individual local_best = ts_local_search(
              shaken, inst, rng, exp_dem, tabu_until, it, tabu_tenure, lambda,
              best_score, archive, eval_count, &accepted_pair);

          double cur_sc = scalar_score(current, lambda);
          double loc_sc = scalar_score(local_best, lambda);

          // TS intensification allows non-improving admissible moves to escape
          // local optima; keep best-so-far separately.
          if (local_best.CV <= EPS &&
              loc_sc + 1e-12 < std::numeric_limits<double>::infinity()) {
            current = local_best;
            moved_in_iter = true;
            if (loc_sc + 1e-9 < scalar_score(best, lambda)) {
              best = local_best;
              k = 1;
            } else {
              ++k;
            }
          } else {
            ++k;
          }
        }

        if (!moved_in_iter)
          break;
      }

      eval_candidate(best, inst, archive);
      ++eval_count;
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
