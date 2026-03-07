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
// Greedy Baseline for MO-IHLNDP  (multi-restart / stochastic version)
// ---------------------------------------------------------------------------
// Generates a diverse pool of candidate solutions via randomised greedy
// restarts, then keeps the non-dominated front.
//
// Each restart uses:
//   • A randomly-sampled subset of k hubs to open (k drawn U[k_min, num_H]).
//   • Random weights W drawn from U[0,1]^6 (feeds the decoder's priority
//     scoring and window depth).
//   • Random anchor assignment A (uniform random over open hubs).
//   • Random inventory R (uniform U[0,1] per open hub).
//   • The existing stochastic decoder (DECODER_NOISE_SIGMA already adds
//     noise to priority scores on each call).
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

// Keep only the non-dominated frontier among feasible solutions (CV==0).
vector<Solution> pareto_filter(const vector<Solution> &pool) {
  vector<Solution> front;
  for (const auto &s : pool) {
    if (s.CV > 1e-9)
      continue; // skip infeasible
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
  // De-duplicate on (Z1, Z2)
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

  // ── Deterministic anchor (two classic heuristics kept for reproducibility)
  // ──
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

  // 1. Min-Cost Greedy: open the 3 cheapest hubs
  {
    vector<pair<double, int>> ci;
    for (int ki = 0; ki < num_H; ki++)
      ci.push_back({inst.F_hub[ki], ki});
    std::sort(ci.begin(), ci.end());
    int n_open = std::min(3, num_H);

    Individual ind(num_H, num_I);
    ind.X.assign(num_H, 0);
    for (int i = 0; i < n_open; i++)
      ind.X[ci[i].second] = 1;
    ind.R.assign(num_H, 0.0);
    for (int ki = 0; ki < num_H; ki++)
      if (ind.X[ki])
        ind.R[ki] = 1.0;
    // nearest-hub assignment
    vector<int> open_ki;
    for (int ki = 0; ki < num_H; ki++)
      if (ind.X[ki])
        open_ki.push_back(ki);
    for (int ii = 0; ii < num_I; ii++) {
      int di = inst.demand_idx[ii];
      double best = inst.big_M;
      int best_ki = open_ki[0];
      for (int ki : open_ki) {
        int hi = inst.hub_idx[ki];
        double dx = inst.lat[di] - inst.lat[hi],
               dy = inst.lon[di] - inst.lon[hi];
        double d = dx * dx + dy * dy;
        if (d < best) {
          best = d;
          best_ki = ki;
        }
      }
      ind.A[ii] = best_ki;
    }
    ind.W = {0.5, 0.5, 0.5, 0.5, 0.5, 0.5};
    decode(ind, inst);
    push_solution(ind, "min_cost_greedy");
  }

  // 2. Min-Depriv Greedy: open all hubs
  {
    Individual ind(num_H, num_I);
    ind.X.assign(num_H, 1);
    ind.R.assign(num_H, 1.0);
    for (int ii = 0; ii < num_I; ii++) {
      int di = inst.demand_idx[ii];
      double best = inst.big_M;
      int best_ki = 0;
      for (int ki = 0; ki < num_H; ki++) {
        int hi = inst.hub_idx[ki];
        double dx = inst.lat[di] - inst.lat[hi],
               dy = inst.lon[di] - inst.lon[hi];
        double d = dx * dx + dy * dy;
        if (d < best) {
          best = d;
          best_ki = ki;
        }
      }
      ind.A[ii] = best_ki;
    }
    ind.W = {0.5, 0.5, 0.5, 0.5, 0.5, 0.5};
    decode(ind, inst);
    push_solution(ind, "min_depriv_greedy");
  }

  // 3. Multi-restart stochastic greedy
  std::mt19937 rng(base_seed + 1);
  std::uniform_real_distribution<double> udist(0.0, 1.0);
  std::uniform_int_distribution<int> k_dist(1, num_H);

  cerr << "[Greedy] Running " << restarts << " stochastic restarts...\n";
  for (int r = 0; r < restarts; r++) {
    // Randomise how many hubs to open
    int k = k_dist(rng);

    // Randomly pick k hubs to open (Fisher-Yates style)
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

    // Random inventory fractions for open hubs
    ind.R.assign(num_H, 0.0);
    for (int ki : open_ki)
      ind.R[ki] = 0.1 + 0.9 * udist(rng);

    // Random anchor assignment (pick a random open hub as anchor)
    for (int ii = 0; ii < num_I; ii++)
      ind.A[ii] = open_ki[std::uniform_int_distribution<int>(
          0, (int)open_ki.size() - 1)(rng)];

    // Random weights
    ind.W.resize(6);
    for (auto &w : ind.W)
      w = udist(rng);

    // Set the global rolling seed so the decoder noise is different each
    // restart
    set_rolling_seed(base_seed + r + 10);
    decode(ind, inst);
    push_solution(ind, "stochastic_r" + std::to_string(r));
  }

  cerr << "[Greedy] Pool size: " << pool.size()
       << " (feasible+infeasible). Filtering Pareto front...\n";

  vector<Solution> front = pareto_filter(pool);
  cerr << "[Greedy] Pareto front: " << front.size() << " solutions.\n";

  // ── JSON dump ────────────────────────────────────────────────────────────
  json j;
  j["meta"]["solver"] = "GreedyBaselineCPP_MultiRestart";
  j["meta"]["restarts"] = restarts;
  j["meta"]["seed"] = base_seed;
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
