// gwo_hd_baseline.cpp
// -----------------------------------------------------------------------------
// Customized Grey Wolf Optimizer baseline (near-faithful to Li et al., 2023)
//
// Reference: Applied Soft Computing 133 (2023) 109925
// "Design of multimodal hub-and-spoke transportation network for emergency
// relief under COVID-19 pandemic: A meta-heuristic approach"
//
// Faithful components implemented:
//   - Basic GWO hierarchy: alpha, beta, delta + omega wolves
//   - Weighted normalized fitness over two objectives
//   - HD-move update (Algorithm 2 style): random [0, HD(X,L)] moves toward L
//   - Customized loop (Algorithm 3 style): for each omega wolf, generate r1/r2/r3
//     against alpha/beta/delta and keep the best
//
// Adaptation for this project:
//   - Wolf chromosome uses project Individual: (X, R, A, W)
//   - Improvement stage focuses on discrete segments X and A
//   - Pareto archive is collected across iterations and weight runs to compete
//     against PB-NSGA in Exp1 evaluator.
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
#include <sstream>

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
  double fitness = 1e100;
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
    const double p = inst.scenarios[si].prob;
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

static void assign_to_nearest_open(Individual &ind, const DRNDInstance &inst) {
  auto oh = open_hubs(ind.X);
  if (oh.empty()) {
    int k0 = 0;
    ind.X[k0] = 1;
    oh.push_back(k0);
  }
  for (int ii = 0; ii < inst.num_I; ++ii) {
    int cur = ind.A[ii];
    if (cur >= 0 && cur < inst.num_H && ind.X[cur])
      continue;

    int d = inst.demand_idx[ii];
    int best = oh[0];
    double best_d2 = 1e100;
    for (int ki : oh) {
      int h = inst.hub_idx[ki];
      double dx = inst.lat[d] - inst.lat[h];
      double dy = inst.lon[d] - inst.lon[h];
      double d2 = dx * dx + dy * dy;
      if (d2 < best_d2) {
        best_d2 = d2;
        best = ki;
      }
    }
    ind.A[ii] = best;
  }
}

static Individual random_feasibleish(const DRNDInstance &inst, std::mt19937 &rng,
                                     const vector<double> &exp_dem) {
  Individual ind(inst.num_H, inst.num_I);

  int max_open = std::max(1, inst.num_H * 3 / 5);
  int n_open = std::uniform_int_distribution<int>(1, max_open)(rng);

  vector<int> hubs(inst.num_H);
  std::iota(hubs.begin(), hubs.end(), 0);
  std::shuffle(hubs.begin(), hubs.end(), rng);
  for (int i = 0; i < n_open; ++i)
    ind.X[hubs[i]] = 1;

  auto oh = open_hubs(ind.X);
  for (int ii = 0; ii < inst.num_I; ++ii)
    ind.A[ii] = oh[std::uniform_int_distribution<int>(0, (int)oh.size() - 1)(rng)];

  reconstruct_R(ind, inst, exp_dem);

  for (auto &w : ind.W)
    w = std::uniform_real_distribution<double>(0.0, 1.0)(rng);

  return ind;
}

static void evaluate(Wolf &w, const DRNDInstance &inst) {
  decode(w.ind, inst);
  w.Z1 = w.ind.Z1;
  w.Z2 = w.ind.Z2;
  w.CV = w.ind.CV;
}

static void update_fitness(vector<Wolf> &pop, double w1, double w2) {
  double min_z1 = 1e100, min_z2 = 1e100;
  for (const auto &w : pop) {
    if (w.CV <= EPS) {
      min_z1 = std::min(min_z1, w.Z1);
      min_z2 = std::min(min_z2, w.Z2);
    }
  }
  if (min_z1 >= 1e99 || min_z2 >= 1e99) {
    for (auto &w : pop)
      w.fitness = 1e100 + w.CV;
    return;
  }

  min_z1 = std::max(min_z1, 1e-9);
  min_z2 = std::max(min_z2, 1e-9);

  for (auto &w : pop) {
    if (w.CV > EPS) {
      w.fitness = 1e100 + w.CV;
    } else {
      w.fitness = w1 * (w.Z1 / min_z1) + w2 * (w.Z2 / min_z2);
    }
  }
}

static inline bool better(const Wolf &a, const Wolf &b) {
  return a.fitness < b.fitness;
}

static int hamming_distance(const vector<int> &x, const vector<int> &l) {
  int d = 0;
  int n = (int)x.size();
  for (int i = 0; i < n; ++i)
    d += (x[i] != l[i]);
  return d;
}

static void hd_move_in_place(vector<int> &x, const vector<int> &l, std::mt19937 &rng) {
  int hd = hamming_distance(x, l);
  if (hd <= 0)
    return;

  int move = std::uniform_int_distribution<int>(0, hd)(rng);
  while (move-- > 0) {
    vector<int> diff;
    diff.reserve(x.size());
    for (int i = 0; i < (int)x.size(); ++i) {
      if (x[i] != l[i])
        diff.push_back(i);
    }
    if (diff.empty())
      break;
    int idx = diff[std::uniform_int_distribution<int>(0, (int)diff.size() - 1)(rng)];
    x[idx] = l[idx];
  }
}

static Wolf best_of_three(const Wolf &r1, const Wolf &r2, const Wolf &r3) {
  const Wolf *best = &r1;
  if (better(r2, *best))
    best = &r2;
  if (better(r3, *best))
    best = &r3;
  return *best;
}

int main(int argc, char *argv[]) {
  if (argc < 2) {
    cerr << "Usage: gwo_hd_baseline <instance.json> [--out path] [--seed N] "
            "[--wolves N] [--iter N] [--time-limit s] [--weights csv]\n";
    return 1;
  }

  string instance_path = argv[1];
  string out_path;
  int seed = 42;
  int wolves_n = 10;      // paper uses 10 wolves in customized GWO
  int max_iter = 180;
  double time_limit = 90.0;
  string weights_csv = "0.6,0.5,0.7,0.4,0.8";

  for (int i = 2; i < argc; ++i) {
    string f = argv[i];
    if (f == "--out" && i + 1 < argc)
      out_path = argv[++i];
    else if (f == "--seed" && i + 1 < argc)
      seed = std::stoi(argv[++i]);
    else if (f == "--wolves" && i + 1 < argc)
      wolves_n = std::max(4, std::stoi(argv[++i]));
    else if (f == "--iter" && i + 1 < argc)
      max_iter = std::max(1, std::stoi(argv[++i]));
    else if (f == "--time-limit" && i + 1 < argc)
      time_limit = std::max(1.0, std::stod(argv[++i]));
    else if (f == "--weights" && i + 1 < argc)
      weights_csv = argv[++i];
  }

  DRNDInstance inst;
  try {
    inst = load_instance(instance_path);
  } catch (const std::exception &e) {
    cerr << "Error loading instance: " << e.what() << "\n";
    return 1;
  }

  vector<double> weights;
  {
    std::stringstream ss(weights_csv);
    string tok;
    while (std::getline(ss, tok, ',')) {
      if (tok.empty())
        continue;
      double w = std::stod(tok);
      if (w > 0.0 && w < 1.0)
        weights.push_back(w);
    }
    if (weights.empty())
      weights = {0.6};
  }

  std::mt19937 rng(seed);
  const auto exp_dem = expected_demand(inst);

  ParetoArchive archive;
  long long eval_count = 0;

  auto t0 = Clock::now();
  std::clock_t c0 = std::clock();

  for (double w1 : weights) {
    double w2 = 1.0 - w1;

    // Construction stage: keep a common base amount-like structure and vary
    // mode-like discrete choices across wolves.
    Individual base = random_feasibleish(inst, rng, exp_dem);

    vector<Wolf> pop;
    pop.reserve(wolves_n);
    for (int i = 0; i < wolves_n; ++i) {
      Wolf w;
      w.ind = base;

      // Vary discrete mode-like part (A) among wolves.
      auto oh = open_hubs(w.ind.X);
      for (int ii = 0; ii < inst.num_I; ++ii)
        w.ind.A[ii] = oh[std::uniform_int_distribution<int>(0, (int)oh.size() - 1)(rng)];

      // Mild diversity in open-hub mask for stronger exploration.
      if (i > 0 && std::uniform_real_distribution<double>(0.0, 1.0)(rng) < 0.4) {
        int k = std::uniform_int_distribution<int>(0, inst.num_H - 1)(rng);
        w.ind.X[k] ^= 1;
        if (std::accumulate(w.ind.X.begin(), w.ind.X.end(), 0) == 0)
          w.ind.X[k] = 1;
      }

      assign_to_nearest_open(w.ind, inst);
      reconstruct_R(w.ind, inst, exp_dem);
      evaluate(w, inst);
      ++eval_count;
      archive.add(w);
      pop.push_back(std::move(w));
    }

    update_fitness(pop, w1, w2);

    int iter = 0;
    while (iter < max_iter) {
      if (Duration(Clock::now() - t0).count() > time_limit)
        break;

      std::sort(pop.begin(), pop.end(), [](const Wolf &a, const Wolf &b) {
        return a.fitness < b.fitness;
      });

      Wolf alpha = pop[0], beta = pop[1], delta = pop[2];

      for (int wi = 3; wi < (int)pop.size(); ++wi) {
        Wolf cur = pop[wi];

        // Algorithm 3 lines 16-20 style for X segment.
        Wolf r1x = cur, r2x = cur, r3x = cur;
        hd_move_in_place(r1x.ind.X, alpha.ind.X, rng);
        hd_move_in_place(r2x.ind.X, beta.ind.X, rng);
        hd_move_in_place(r3x.ind.X, delta.ind.X, rng);
        for (Wolf *rw : {&r1x, &r2x, &r3x}) {
          if (std::accumulate(rw->ind.X.begin(), rw->ind.X.end(), 0) == 0)
            rw->ind.X[std::uniform_int_distribution<int>(0, inst.num_H - 1)(rng)] = 1;
          assign_to_nearest_open(rw->ind, inst);
          reconstruct_R(rw->ind, inst, exp_dem);
          evaluate(*rw, inst);
          ++eval_count;
        }

        // Manual fitness for temporary triplet, using current min-normalization.
        double min_z1 = std::min({r1x.Z1, r2x.Z1, r3x.Z1});
        double min_z2 = std::min({r1x.Z2, r2x.Z2, r3x.Z2});
        min_z1 = std::max(min_z1, 1e-9);
        min_z2 = std::max(min_z2, 1e-9);
        for (Wolf *rw : {&r1x, &r2x, &r3x})
          rw->fitness = (rw->CV > EPS) ? (1e100 + rw->CV)
                                       : (w1 * (rw->Z1 / min_z1) + w2 * (rw->Z2 / min_z2));
        Wolf best_x = best_of_three(r1x, r2x, r3x);

        // Algorithm 3 lines 21 style for A segment.
        Wolf r1a = best_x, r2a = best_x, r3a = best_x;
        hd_move_in_place(r1a.ind.A, alpha.ind.A, rng);
        hd_move_in_place(r2a.ind.A, beta.ind.A, rng);
        hd_move_in_place(r3a.ind.A, delta.ind.A, rng);
        for (Wolf *rw : {&r1a, &r2a, &r3a}) {
          assign_to_nearest_open(rw->ind, inst);
          reconstruct_R(rw->ind, inst, exp_dem);
          evaluate(*rw, inst);
          ++eval_count;
          archive.add(*rw);
        }

        min_z1 = std::min({r1a.Z1, r2a.Z1, r3a.Z1});
        min_z2 = std::min({r1a.Z2, r2a.Z2, r3a.Z2});
        min_z1 = std::max(min_z1, 1e-9);
        min_z2 = std::max(min_z2, 1e-9);
        for (Wolf *rw : {&r1a, &r2a, &r3a})
          rw->fitness = (rw->CV > EPS) ? (1e100 + rw->CV)
                                       : (w1 * (rw->Z1 / min_z1) + w2 * (rw->Z2 / min_z2));

        pop[wi] = best_of_three(r1a, r2a, r3a);
      }

      update_fitness(pop, w1, w2);
      ++iter;
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
  j["meta"]["solver"] = "GWO-HD-Baseline";
  j["meta"]["reference"] =
      "Li et al. (2023) Applied Soft Computing 133:109925 (customized GWO + HD move)";
  j["meta"]["elapsed_s"] = elapsed;
  j["meta"]["cpu_time_s"] = cpu_s;
  j["meta"]["seed"] = seed;
  j["meta"]["wolves"] = wolves_n;
  j["meta"]["iter"] = max_iter;
  j["meta"]["weights"] = weights;
  j["meta"]["evaluations"] = eval_count;
  j["meta"]["pareto_size"] = (int)front.size();

  json jfront = json::array();
  for (const auto &s : front) {
    json x;
    x["Z1"] = s.Z1;
    x["Z2"] = s.Z2;
    x["CV"] = 0.0;
    x["rank"] = 1;
    x["X"] = s.X;
    x["R"] = s.R;
    x["A"] = s.A;
    x["W"] = s.W;
    jfront.push_back(std::move(x));
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

  cerr << "[GWO-HD] Pareto size=" << front.size() << ", evals=" << eval_count
       << ", elapsed=" << elapsed << " s\n";
  return 0;
}
