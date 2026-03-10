// gwo_hd_baseline.cpp
// -----------------------------------------------------------------------------
// Customized Grey Wolf Optimizer baseline (root-fixed representation)
//
// Reference backbone:
//   Li et al. (2023), Applied Soft Computing 133:109925.
//   Uses alpha/beta/delta hierarchy + HD-based update toward leaders.
//
// Root fixes for this DRND setting:
//   1) Two-layer representation:
//      - infrastructure layer: X (open hubs)
//      - mode/assignment layer: A (demand->hub assignment)
//      R is reconstructed deterministically after each move.
//   2) Multiobjective leader selection:
//      alpha=min Z1, beta=min Z2, delta=knee solution on rank-1 set.
//   3) Feasibility-aware update/selection via constrained dominance.
//   4) Stagnation rescue: partial omega re-construction.
// -----------------------------------------------------------------------------

#include "decoder.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
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

struct Wolf {
  Individual ind;
  double Z1 = 0.0;
  double Z2 = 0.0;
  double CV = 0.0;
};

struct ParetoArchive {
  vector<Solution> front;

  bool dominated(double z1, double z2) const {
    for (const auto &s : front) {
      if (s.Z1 <= z1 && s.Z2 <= z2 && (s.Z1 < z1 || s.Z2 < z2))
        return true;
    }
    return false;
  }

  void add(const Wolf &w) {
    if (w.CV > EPS)
      return;
    if (dominated(w.Z1, w.Z2))
      return;

    front.erase(std::remove_if(front.begin(), front.end(), [&](const Solution &s) {
                 return w.Z1 <= s.Z1 && w.Z2 <= s.Z2 && (w.Z1 < s.Z1 || w.Z2 < s.Z2);
               }),
               front.end());

    Solution s;
    s.Z1 = w.Z1;
    s.Z2 = w.Z2;
    s.X = w.ind.X;
    s.R = w.ind.R;
    s.A = w.ind.A;
    s.W = w.ind.W;
    front.push_back(std::move(s));
  }
};

static bool constrained_better(const Wolf &a, const Wolf &b) {
  bool fa = (a.CV <= EPS), fb = (b.CV <= EPS);
  if (fa != fb)
    return fa;
  if (!fa)
    return a.CV < b.CV;

  bool a_dom = (a.Z1 <= b.Z1 && a.Z2 <= b.Z2 && (a.Z1 < b.Z1 || a.Z2 < b.Z2));
  bool b_dom = (b.Z1 <= a.Z1 && b.Z2 <= a.Z2 && (b.Z1 < a.Z1 || b.Z2 < a.Z2));
  if (a_dom != b_dom)
    return a_dom;

  return (a.Z1 + 8.0 * a.Z2) < (b.Z1 + 8.0 * b.Z2);
}

static vector<int> open_hubs(const vector<int> &X) {
  vector<int> out;
  for (int k = 0; k < (int)X.size(); ++k)
    if (X[k])
      out.push_back(k);
  return out;
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
    ind.R[ki] = std::clamp(load[ki] / inst.kappa[ki], 0.0, 1.0);
  }
}

static int nearest_open_for_demand(const DRNDInstance &inst, int ii,
                                   const vector<int> &open) {
  int d = inst.demand_idx[ii];
  int best = open[0];
  double best_d2 = 1e100;
  for (int ki : open) {
    int h = inst.hub_idx[ki];
    double dx = inst.lat[d] - inst.lat[h];
    double dy = inst.lon[d] - inst.lon[h];
    double d2 = dx * dx + dy * dy;
    if (d2 < best_d2) {
      best_d2 = d2;
      best = ki;
    }
  }
  return best;
}

static void repair_assignment(Individual &ind, const DRNDInstance &inst) {
  auto open = open_hubs(ind.X);
  if (open.empty()) {
    ind.X[0] = 1;
    open.push_back(0);
  }
  for (int ii = 0; ii < inst.num_I; ++ii) {
    int ki = ind.A[ii];
    if (ki < 0 || ki >= inst.num_H || !ind.X[ki])
      ind.A[ii] = nearest_open_for_demand(inst, ii, open);
  }
}

static Wolf evaluate(Individual ind, const DRNDInstance &inst,
                     const vector<double> &exp_dem) {
  repair_assignment(ind, inst);
  reconstruct_R(ind, inst, exp_dem);
  decode(ind, inst);
  Wolf w;
  w.ind = std::move(ind);
  w.Z1 = w.ind.Z1;
  w.Z2 = w.ind.Z2;
  w.CV = w.ind.CV;
  return w;
}

static Individual random_structure(const DRNDInstance &inst, std::mt19937 &rng,
                                   const vector<double> &exp_dem) {
  Individual ind(inst.num_H, inst.num_I);
  int max_open = std::max(1, inst.num_H * 3 / 5);
  int n_open = std::uniform_int_distribution<int>(1, max_open)(rng);

  vector<int> hubs(inst.num_H);
  std::iota(hubs.begin(), hubs.end(), 0);
  std::shuffle(hubs.begin(), hubs.end(), rng);
  for (int i = 0; i < n_open; ++i)
    ind.X[hubs[i]] = 1;

  auto open = open_hubs(ind.X);
  for (int ii = 0; ii < inst.num_I; ++ii) {
    if (std::uniform_real_distribution<double>(0.0, 1.0)(rng) < 0.75) {
      ind.A[ii] = nearest_open_for_demand(inst, ii, open);
    } else {
      ind.A[ii] = open[std::uniform_int_distribution<int>(0, (int)open.size() - 1)(rng)];
    }
  }

  ind.W = {0.7, 0.7, 0.6, 0.6, 0.5, 0.5};
  reconstruct_R(ind, inst, exp_dem);
  return ind;
}

static vector<int> diff_positions(const vector<int> &a, const vector<int> &b) {
  vector<int> diff;
  for (int i = 0; i < (int)a.size(); ++i)
    if (a[i] != b[i])
      diff.push_back(i);
  return diff;
}

static double sqdist_demand_hub(const DRNDInstance &inst, int ii, int ki) {
  int d = inst.demand_idx[ii];
  int h = inst.hub_idx[ki];
  double dx = inst.lat[d] - inst.lat[h];
  double dy = inst.lon[d] - inst.lon[h];
  return dx * dx + dy * dy;
}

// Problem-specific operator:
// Relieve overloaded hubs by reassigning large expected-demand customers to
// alternative open hubs with lower overload pressure and shorter distance.
static void drnd_capacity_reassign(Individual &ind, const DRNDInstance &inst,
                                   const vector<double> &exp_dem,
                                   std::mt19937 &rng) {
  repair_assignment(ind, inst);
  auto open = open_hubs(ind.X);
  if (open.empty()) {
    ind.X[0] = 1;
    open.push_back(0);
  }

  vector<double> load(inst.num_H, 0.0);
  for (int ii = 0; ii < inst.num_I; ++ii) {
    int ki = ind.A[ii];
    if (ki >= 0 && ki < inst.num_H && ind.X[ki])
      load[ki] += inst.gamma * exp_dem[ii];
  }

  auto overload_ratio = [&](int ki) {
    double cap = std::max(inst.kappa[ki], EPS);
    return load[ki] / cap;
  };

  int over_hub = -1;
  double worst = 1.0;
  for (int ki : open) {
    double r = overload_ratio(ki);
    if (r > worst + 1e-9) {
      worst = r;
      over_hub = ki;
    }
  }
  if (over_hub < 0)
    return;

  vector<int> assigned;
  assigned.reserve(inst.num_I);
  for (int ii = 0; ii < inst.num_I; ++ii)
    if (ind.A[ii] == over_hub)
      assigned.push_back(ii);

  if (assigned.empty())
    return;

  std::shuffle(assigned.begin(), assigned.end(), rng);
  std::sort(assigned.begin(), assigned.end(), [&](int a, int b) {
    return exp_dem[a] > exp_dem[b];
  });

  // If overload is severe, open one relief hub selected by proximity to
  // high-demand customers currently attached to the overloaded hub.
  if (overload_ratio(over_hub) > 1.03) {
    vector<int> closed;
    closed.reserve(inst.num_H);
    for (int ki = 0; ki < inst.num_H; ++ki)
      if (!ind.X[ki])
        closed.push_back(ki);

    if (!closed.empty()) {
      int top_cnt = std::max(1, std::min((int)assigned.size(), 8));
      int best_k = closed[0];
      double best_score = 1e100;
      for (int kc : closed) {
        double geo = 0.0;
        for (int t = 0; t < top_cnt; ++t) {
          int ii = assigned[t];
          geo += exp_dem[ii] * sqdist_demand_hub(inst, ii, kc);
        }
        double cost_penalty = 1e-4 * inst.F_hub[kc];
        double score = geo + cost_penalty;
        if (score < best_score) {
          best_score = score;
          best_k = kc;
        }
      }
      ind.X[best_k] = 1;
      open.push_back(best_k);
      load[best_k] = 0.0;
    }
  }

  int max_moves = std::max(1, (int)assigned.size() / 2);
  int moved = 0;

  for (int ii : assigned) {
    int best_k = over_hub;
    double best_score = 1e100;

    for (int kj : open) {
      if (kj == over_hub)
        continue;

      double dem = inst.gamma * exp_dem[ii];
      double cap_j = std::max(inst.kappa[kj], EPS);
      double cap_o = std::max(inst.kappa[over_hub], EPS);

      double r_j_new = (load[kj] + dem) / cap_j;
      double r_o_new = (load[over_hub] - dem) / cap_o;
      double dist_new = sqdist_demand_hub(inst, ii, kj);

      // Prioritize capacity relief first, then transport distance.
      double score = 50.0 * std::max(0.0, r_j_new - 1.0) +
                     20.0 * std::max(0.0, r_o_new - 1.0) + dist_new;

      if (score < best_score) {
        best_score = score;
        best_k = kj;
      }
    }

    if (best_k != over_hub) {
      double dem = inst.gamma * exp_dem[ii];
      load[over_hub] -= dem;
      load[best_k] += dem;
      ind.A[ii] = best_k;
      ++moved;
      if (moved >= max_moves)
        break;
      if (overload_ratio(over_hub) <= 1.0 + 1e-6)
        break;
    }
  }

  reconstruct_R(ind, inst, exp_dem);
}

static void guided_hd_move(vector<int> &x, const vector<int> &leader,
                           std::mt19937 &rng, double frac) {
  auto diff = diff_positions(x, leader);
  if (diff.empty())
    return;
  int hd = (int)diff.size();
  int max_move = std::max(1, (int)std::round(frac * hd));
  int move = std::uniform_int_distribution<int>(1, max_move)(rng);

  while (move-- > 0 && !diff.empty()) {
    int pos = std::uniform_int_distribution<int>(0, (int)diff.size() - 1)(rng);
    int idx = diff[pos];
    x[idx] = leader[idx];
    diff[pos] = diff.back();
    diff.pop_back();
  }
}

static vector<int> rank1_indices(const vector<Wolf> &pop) {
  vector<int> out;
  for (int i = 0; i < (int)pop.size(); ++i) {
    if (pop[i].CV > EPS)
      continue;
    bool dom = false;
    for (int j = 0; j < (int)pop.size(); ++j) {
      if (i == j || pop[j].CV > EPS)
        continue;
      bool j_dom_i = (pop[j].Z1 <= pop[i].Z1 && pop[j].Z2 <= pop[i].Z2 &&
                      (pop[j].Z1 < pop[i].Z1 || pop[j].Z2 < pop[i].Z2));
      if (j_dom_i) {
        dom = true;
        break;
      }
    }
    if (!dom)
      out.push_back(i);
  }
  return out;
}

static int select_delta_knee(const vector<Wolf> &pop, const vector<int> &r1,
                             int alpha_idx, int beta_idx) {
  if (r1.empty())
    return alpha_idx;

  double z1min = 1e100, z1max = -1e100, z2min = 1e100, z2max = -1e100;
  for (int idx : r1) {
    z1min = std::min(z1min, pop[idx].Z1);
    z1max = std::max(z1max, pop[idx].Z1);
    z2min = std::min(z2min, pop[idx].Z2);
    z2max = std::max(z2max, pop[idx].Z2);
  }

  double r1z = std::max(1e-9, z1max - z1min);
  double r2z = std::max(1e-9, z2max - z2min);

  int best = r1[0];
  double best_score = 1e100;
  for (int idx : r1) {
    if (idx == alpha_idx || idx == beta_idx)
      continue;
    double n1 = (pop[idx].Z1 - z1min) / r1z;
    double n2 = (pop[idx].Z2 - z2min) / r2z;
    double score = std::abs(n1 - n2);
    if (score < best_score) {
      best_score = score;
      best = idx;
    }
  }
  return best;
}

int main(int argc, char *argv[]) {
  if (argc < 2) {
    cerr << "Usage: gwo_hd_baseline <instance.json> [--out path] [--seed N] "
            "[--wolves N] [--iter N] [--time-limit s]\n";
    return 1;
  }

  string instance_path = argv[1];
  string out_path;
  int seed = 42;
  int wolves_n = 30;
  int max_iter = 560;
  double time_limit = 140.0;
  double fracA_start = 0.45;
  double fracA_end = 0.06;
  double fracX_start = 0.35;
  double fracX_end = 0.04;
  double accept_worse_prob = 0.03;
  int stagnation_limit = 20;
  double keep_ratio = 0.45;
  double ps_op_prob = 0.35;

  for (int i = 2; i < argc; ++i) {
    string f = argv[i];
    if (f == "--out" && i + 1 < argc)
      out_path = argv[++i];
    else if (f == "--seed" && i + 1 < argc)
      seed = std::stoi(argv[++i]);
    else if (f == "--wolves" && i + 1 < argc)
      wolves_n = std::max(6, std::stoi(argv[++i]));
    else if (f == "--iter" && i + 1 < argc)
      max_iter = std::max(1, std::stoi(argv[++i]));
    else if (f == "--time-limit" && i + 1 < argc)
      time_limit = std::max(1.0, std::stod(argv[++i]));
    else if (f == "--fracA-start" && i + 1 < argc)
      fracA_start = std::clamp(std::stod(argv[++i]), 0.0, 1.0);
    else if (f == "--fracA-end" && i + 1 < argc)
      fracA_end = std::clamp(std::stod(argv[++i]), 0.0, 1.0);
    else if (f == "--fracX-start" && i + 1 < argc)
      fracX_start = std::clamp(std::stod(argv[++i]), 0.0, 1.0);
    else if (f == "--fracX-end" && i + 1 < argc)
      fracX_end = std::clamp(std::stod(argv[++i]), 0.0, 1.0);
    else if (f == "--accept-worse" && i + 1 < argc)
      accept_worse_prob = std::clamp(std::stod(argv[++i]), 0.0, 0.5);
    else if (f == "--stagnation-limit" && i + 1 < argc)
      stagnation_limit = std::max(5, std::stoi(argv[++i]));
    else if (f == "--keep-ratio" && i + 1 < argc)
      keep_ratio = std::clamp(std::stod(argv[++i]), 0.20, 0.95);
    else if (f == "--ps-op-prob" && i + 1 < argc)
      ps_op_prob = std::clamp(std::stod(argv[++i]), 0.0, 1.0);
  }

  if (fracA_start < fracA_end)
    std::swap(fracA_start, fracA_end);
  if (fracX_start < fracX_end)
    std::swap(fracX_start, fracX_end);

  DRNDInstance inst;
  try {
    inst = load_instance(instance_path);
  } catch (const std::exception &e) {
    cerr << "Error loading instance: " << e.what() << "\n";
    return 1;
  }

  std::mt19937 rng(seed);
  auto exp_dem = expected_demand(inst);

  ParetoArchive archive;
  long long eval_count = 0;

  vector<Wolf> pop;
  pop.reserve(wolves_n);
  for (int i = 0; i < wolves_n; ++i) {
    Wolf w = evaluate(random_structure(inst, rng, exp_dem), inst, exp_dem);
    pop.push_back(w);
    archive.add(w);
    ++eval_count;
  }

  auto t0 = Clock::now();
  std::clock_t c0 = std::clock();

  int best_r1 = (int)rank1_indices(pop).size();
  int stagnation = 0;

  for (int iter = 0; iter < max_iter; ++iter) {
    if (Duration(Clock::now() - t0).count() > time_limit)
      break;

    vector<int> r1 = rank1_indices(pop);
    int alpha_idx = -1, beta_idx = -1;

    if (!r1.empty()) {
      alpha_idx = *std::min_element(r1.begin(), r1.end(), [&](int a, int b) {
        return pop[a].Z1 < pop[b].Z1;
      });
      beta_idx = *std::min_element(r1.begin(), r1.end(), [&](int a, int b) {
        return pop[a].Z2 < pop[b].Z2;
      });
    } else {
      alpha_idx = beta_idx = (int)(std::min_element(pop.begin(), pop.end(),
            [](const Wolf &a, const Wolf &b) { return a.CV < b.CV; }) - pop.begin());
    }

    int delta_idx = select_delta_knee(pop, r1, alpha_idx, beta_idx);

    const Wolf &alpha = pop[alpha_idx];
    const Wolf &beta = pop[beta_idx];
    const Wolf &delta = pop[delta_idx];

    for (int wi = 0; wi < (int)pop.size(); ++wi) {
      if (wi == alpha_idx || wi == beta_idx || wi == delta_idx)
        continue;

      const Wolf &cur = pop[wi];
      vector<Wolf> cand(3);
      const Wolf *leaders[3] = {&alpha, &beta, &delta};

      double progress = (double)iter / std::max(1, max_iter - 1);
      double fracA = std::max(fracA_end, fracA_start - (fracA_start - fracA_end) * progress);
      double fracX = std::max(fracX_end, fracX_start - (fracX_start - fracX_end) * progress);

      for (int ci = 0; ci < 3; ++ci) {
        Individual ind = cur.ind;
        guided_hd_move(ind.A, leaders[ci]->ind.A, rng, fracA);
        guided_hd_move(ind.X, leaders[ci]->ind.X, rng, fracX);

        if (std::uniform_real_distribution<double>(0.0, 1.0)(rng) < ps_op_prob)
          drnd_capacity_reassign(ind, inst, exp_dem, rng);

        if (std::accumulate(ind.X.begin(), ind.X.end(), 0) == 0)
          ind.X[std::uniform_int_distribution<int>(0, inst.num_H - 1)(rng)] = 1;

        cand[ci] = evaluate(std::move(ind), inst, exp_dem);
        archive.add(cand[ci]);
        ++eval_count;
      }

      Wolf best = cand[0];
      if (constrained_better(cand[1], best))
        best = cand[1];
      if (constrained_better(cand[2], best))
        best = cand[2];

      if (constrained_better(best, cur)) {
        pop[wi] = best;
      } else if (std::uniform_real_distribution<double>(0.0, 1.0)(rng) < accept_worse_prob) {
        pop[wi] = best;
      }
    }

    int now_r1 = (int)rank1_indices(pop).size();
    if (now_r1 > best_r1) {
      best_r1 = now_r1;
      stagnation = 0;
    } else {
      ++stagnation;
    }

    if (stagnation >= stagnation_limit) {
      vector<int> idx(pop.size());
      std::iota(idx.begin(), idx.end(), 0);
      std::sort(idx.begin(), idx.end(), [&](int a, int b) {
        return constrained_better(pop[a], pop[b]);
      });

      int keep = std::max(3, (int)std::round(pop.size() * keep_ratio));
      for (int t = keep; t < (int)idx.size(); ++t) {
        int i = idx[t];
        Wolf w = evaluate(random_structure(inst, rng, exp_dem), inst, exp_dem);
        pop[i] = w;
        archive.add(w);
        ++eval_count;
      }
      stagnation = 0;
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

  double elapsed = Duration(Clock::now() - t0).count();
  double cpu_s = 1.0 * (std::clock() - c0) / CLOCKS_PER_SEC;

  json j;
  j["meta"]["solver"] = "GWO-HD-Baseline-v2";
  j["meta"]["reference"] =
      "Li et al. (2023) Applied Soft Computing 133:109925 (customized GWO + HD move)";
  j["meta"]["elapsed_s"] = elapsed;
  j["meta"]["cpu_time_s"] = cpu_s;
  j["meta"]["seed"] = seed;
  j["meta"]["wolves"] = wolves_n;
  j["meta"]["iter"] = max_iter;
  j["meta"]["fracA_start"] = fracA_start;
  j["meta"]["fracA_end"] = fracA_end;
  j["meta"]["fracX_start"] = fracX_start;
  j["meta"]["fracX_end"] = fracX_end;
  j["meta"]["accept_worse_prob"] = accept_worse_prob;
  j["meta"]["stagnation_limit"] = stagnation_limit;
  j["meta"]["keep_ratio"] = keep_ratio;
  j["meta"]["ps_op_prob"] = ps_op_prob;
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

  cerr << "[GWO-HD-v2] Pareto size=" << front.size() << ", evals=" << eval_count
       << ", elapsed=" << elapsed << " s\n";
  return 0;
}
