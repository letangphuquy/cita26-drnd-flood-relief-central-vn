#include "decoder.hpp"
#include <algorithm>
#include <chrono>
#include <fstream>
#include <numeric>
#include <random>
#include <set>

using Clock = std::chrono::high_resolution_clock;
using Duration = std::chrono::duration<double>;

// ---------------------------------------------------------------------------
// Greedy Baseline for MO-IHLNDP  (systematic sweep + stochastic restarts)
// ---------------------------------------------------------------------------
// Generates a diverse pool of candidate solutions, then outputs the full
// non-dominated Pareto approximation.
//
// Solution sources:
//   1. Systematic cardinality sweep  — for each k=1..num_H:
//        a) "cheapest-k"  hubs (by fixed cost F_hub)
//        b) "safest-k"    hubs (lowest max-scenario risk)
//        c) "best-cover-k" hubs (maximise hub × demand reachability)
//        All three are evaluated with near-neighbor demand assignment.
//   2. Stochastic restarts (default 500) with random hub count, inventory
//        fractions, anchor assignments, and W-weight vectors.
//
// CLI:   greedy_baseline <instance.json> [--out <path>] [--restarts N]
//                                        [--seed S]
// ---------------------------------------------------------------------------

struct Solution {
  double Z1 = 0, Z2 = 0, CV = 0;
  vector<int> X;
  vector<double> R;
  vector<int> A;
  vector<double> W;
  string meta;
};

bool dominates(const Solution &a, const Solution &b) {
  return a.Z1 <= b.Z1 && a.Z2 <= b.Z2 && (a.Z1 < b.Z1 || a.Z2 < b.Z2);
}

// Keep only non-dominated, feasible solutions.
vector<Solution> pareto_filter(const vector<Solution> &pool) {
  vector<Solution> front;
  for (const auto &s : pool) {
    if (s.CV > 1e-9)
      continue;
    bool dominated = false;
    for (const auto &f : pool) {
      if (&f == &s || f.CV > 1e-9)
        continue;
      if (dominates(f, s)) {
        dominated = true;
        break;
      }
    }
    if (!dominated)
      front.push_back(s);
  }
  std::sort(front.begin(), front.end(),
            [](const Solution &a, const Solution &b) {
              return a.Z1 < b.Z1 || (a.Z1 == b.Z1 && a.Z2 < b.Z2);
            });
  front.erase(std::unique(front.begin(), front.end(),
                          [](const Solution &a, const Solution &b) {
                            return std::abs(a.Z1 - b.Z1) < 1e-6 &&
                                   std::abs(a.Z2 - b.Z2) < 1e-6;
                          }),
              front.end());
  return front;
}

// ── Helper: evaluate a hub subset ────────────────────────────────────────────
// opens the hubs in open_set, assigns each demand to its nearest open hub,
// applies uniform inventory fill r_fill, and runs the decoder.
Solution evaluate_subset(const vector<int> &open_set, double r_fill,
                         const DRNDInstance &inst, const string &meta) {
  int num_H = inst.num_H, num_I = inst.num_I;
  Individual ind(num_H, num_I);
  ind.X.assign(num_H, 0);
  for (int ki : open_set)
    ind.X[ki] = 1;

  // Uniform inventory fill
  ind.R.assign(num_H, 0.0);
  for (int ki : open_set)
    ind.R[ki] = r_fill;

  // Nearest-hub assignment (Euclidean)
  for (int ii = 0; ii < num_I; ii++) {
    int di = inst.demand_idx[ii];
    double best = 1e18;
    int best_ki = open_set[0];
    for (int ki : open_set) {
      int hi = inst.hub_idx[ki];
      double dx = inst.lat[di] - inst.lat[hi];
      double dy = inst.lon[di] - inst.lon[hi];
      double d = dx * dx + dy * dy;
      if (d < best) {
        best = d;
        best_ki = ki;
      }
    }
    ind.A[ii] = best_ki;
  }
  ind.W = {0.5, 0.5, 0.5, 0.5, 0.5, 0.5};
  decode_legacy(ind, inst);

  Solution s;
  s.Z1 = ind.Z1;
  s.Z2 = ind.Z2;
  s.CV = ind.CV;
  s.X = ind.X;
  s.R = ind.R;
  s.A = ind.A;
  s.W = ind.W;
  s.meta = meta;
  return s;
}

// ── Systematic cardinality sweep
// ────────────────────────────────────────────── For each k=1..num_H, evaluates
// three hub selections:
//   (a) cheapest-k  (sorted by F_hub ascending)
//   (b) safest-k    (sorted by min-scenario risk ascending)
//   (c) coverage-k  (heuristic: sorted by # demand nodes "closest" to hub)
vector<Solution> systematic_sweep(const DRNDInstance &inst) {
  int num_H = inst.num_H, num_I = inst.num_I;

  // Precompute sort orders
  // (a) by cost
  vector<int> by_cost(num_H);
  std::iota(by_cost.begin(), by_cost.end(), 0);
  std::sort(by_cost.begin(), by_cost.end(),
            [&](int a, int b) { return inst.F_hub[a] < inst.F_hub[b]; });

  // (b) by safety: use average risk across scenarios as proxy
  vector<double> avg_risk(num_H, 0.0);
  int num_S = inst.num_S;
  for (int s = 0; s < num_S; s++)
    for (int ki = 0; ki < num_H; ki++) {
      int hi = inst.hub_idx[ki];
      avg_risk[ki] += inst.scenarios[s].risk[hi];
    }
  for (auto &r : avg_risk)
    r /= std::max(1, num_S);
  vector<int> by_safety(num_H);
  std::iota(by_safety.begin(), by_safety.end(), 0);
  std::sort(by_safety.begin(), by_safety.end(),
            [&](int a, int b) { return avg_risk[a] < avg_risk[b]; });

  // (c) by coverage: count how many demands are "nearest" to each hub
  vector<int> nearest_count(num_H, 0);
  for (int ii = 0; ii < num_I; ii++) {
    int di = inst.demand_idx[ii];
    double best = 1e18;
    int best_ki = 0;
    for (int ki = 0; ki < num_H; ki++) {
      int hi = inst.hub_idx[ki];
      double dx = inst.lat[di] - inst.lat[hi], dy = inst.lon[di] - inst.lon[hi];
      double d = dx * dx + dy * dy;
      if (d < best) {
        best = d;
        best_ki = ki;
      }
    }
    nearest_count[best_ki]++;
  }
  vector<int> by_coverage(num_H);
  std::iota(by_coverage.begin(), by_coverage.end(), 0);
  std::sort(by_coverage.begin(), by_coverage.end(),
            [&](int a, int b) { return nearest_count[a] > nearest_count[b]; });

  vector<Solution> pool;
  // Two inventory fills: full (1.0) and half (0.5) per sweep
  for (double r_fill : {1.0, 0.5}) {
    for (int k = 1; k <= num_H; k++) {
      // (a) cheapest-k
      pool.push_back(evaluate_subset(
          vector<int>(by_cost.begin(), by_cost.begin() + k), r_fill, inst,
          "cheapest_k" + std::to_string(k) + "_r" +
              std::to_string((int)(r_fill * 10))));

      // (b) safest-k
      pool.push_back(evaluate_subset(
          vector<int>(by_safety.begin(), by_safety.begin() + k), r_fill, inst,
          "safest_k" + std::to_string(k) + "_r" +
              std::to_string((int)(r_fill * 10))));

      // (c) coverage-k
      pool.push_back(evaluate_subset(
          vector<int>(by_coverage.begin(), by_coverage.begin() + k), r_fill,
          inst,
          "coverage_k" + std::to_string(k) + "_r" +
              std::to_string((int)(r_fill * 10))));
    }
  }
  cerr << "[Greedy] Systematic sweep: " << pool.size() << " candidates.\n";
  return pool;
}

int main(int argc, char *argv[]) {
  if (argc < 2) {
    cerr << "Usage: greedy_baseline <instance.json> [--out <path>]"
            " [--restarts N] [--seed S]\n";
    return 1;
  }

  string inst_path = argv[1];
  string out_path = "";
  int restarts = 500;
  int base_seed = 42;

  for (int i = 2; i < argc; i++) {
    const string arg = argv[i];
    if (arg == "--out" && i + 1 < argc)
      out_path = argv[++i];
    if (arg == "--restarts" && i + 1 < argc)
      restarts = std::stoi(argv[++i]);
    if (arg == "--seed" && i + 1 < argc)
      base_seed = std::stoi(argv[++i]);
  }

  DRNDInstance inst;
  try {
    inst = load_instance(inst_path);
  } catch (const std::exception &e) {
    cerr << "Error loading instance: " << e.what() << "\n";
    return 1;
  }

  const int num_H = inst.num_H;
  const int num_I = inst.num_I;
  set_rolling_seed(base_seed);

  vector<Solution> pool;

  auto push_solution = [&](const Individual &ind, const string &meta) {
    Solution s;
    s.Z1 = ind.Z1;
    s.Z2 = ind.Z2;
    s.CV = ind.CV;
    s.X = ind.X;
    s.R = ind.R;
    s.A = ind.A;
    s.W = ind.W;
    s.meta = meta;
    pool.push_back(s);
  };

  // ── 1. Systematic cardinality sweep ──────────────────────────────────────
  auto sweep_pool = systematic_sweep(inst);
  for (auto &s : sweep_pool)
    pool.push_back(s);

  // ── 2. Stochastic multi-restart ───────────────────────────────────────────
  std::mt19937 rng(base_seed + 1);
  std::uniform_real_distribution<double> udist(0.0, 1.0);
  std::uniform_int_distribution<int> k_dist(1, num_H);

  cerr << "[Greedy] Running " << restarts << " stochastic restarts...\n";
  for (int r = 0; r < restarts; r++) {
    int k = k_dist(rng);

    vector<int> idx(num_H);
    std::iota(idx.begin(), idx.end(), 0);
    std::shuffle(idx.begin(), idx.end(), rng);

    Individual ind(num_H, num_I);
    ind.X.assign(num_H, 0);
    vector<int> open_ki;
    for (int i = 0; i < k; i++) {
      ind.X[idx[i]] = 1;
      open_ki.push_back(idx[i]);
    }

    ind.R.assign(num_H, 0.0);
    for (int ki : open_ki)
      ind.R[ki] = 0.1 + 0.9 * udist(rng);

    for (int ii = 0; ii < num_I; ii++)
      ind.A[ii] = open_ki[std::uniform_int_distribution<int>(
          0, (int)open_ki.size() - 1)(rng)];

    ind.W.resize(6);
    for (auto &w : ind.W)
      w = udist(rng);

    set_rolling_seed(base_seed + r + 10);
    decode_legacy(ind, inst);
    push_solution(ind, "stochastic_r" + std::to_string(r));
  }

  cerr << "[Greedy] Pool size: " << pool.size()
       << ". Filtering Pareto front...\n";
  vector<Solution> front = pareto_filter(pool);
  cerr << "[Greedy] Pareto front: " << front.size() << " solutions.\n";

  // ── JSON dump ─────────────────────────────────────────────────────────────
  json j;
  j["meta"]["solver"] = "GreedyBaseline_SweepStochastic";
  j["meta"]["restarts"] = restarts;
  j["meta"]["seed"] = base_seed;
  j["meta"]["sweep_k"] = num_H;
  json jfront = json::array();
  for (const auto &s : front) {
    json jsol;
    jsol["Z1"] = s.Z1;
    jsol["Z2"] = s.Z2;
    jsol["CV"] = s.CV;
    jsol["rank"] = 1;
    jsol["meta"] = s.meta;
    jsol["X"] = s.X;
    jsol["R"] = s.R;
    jsol["A"] = s.A;
    jsol["W"] = s.W;
    jfront.push_back(std::move(jsol));
  }
  j["pareto_front"] = jfront;

  if (out_path.empty()) {
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
  return 0;
}
