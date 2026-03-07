#include "decoder.hpp"
#include <algorithm>
#include <chrono>
#include <fstream>
#include <numeric>

using Clock = std::chrono::high_resolution_clock;
using Duration = std::chrono::duration<double>;

// ---------------------------------------------------------------------------
// Greedy Baseline for MO-IHLNDP
// ---------------------------------------------------------------------------
// Evaluates two configurations using the exact C++ decoder:
// 1. Min-Cost Greedy: Open the 3 cheapest hubs based on fixed cost F_hub.
// 2. Min-Deprivation Greedy: Open all hubs.
// ---------------------------------------------------------------------------

struct Solution {
  double Z1 = 0, Z2 = 0, CV = 0;
  vector<int> X;
  vector<double> R;
  vector<int> A;
  vector<double> W;
  string meta;
};

// Generates a random solution for a given X to get representative routing
void evaluate_greedy_config(const vector<int> &X, const DRNDInstance &inst,
                            const string &meta, vector<Solution> &pareto) {
  Individual ind(inst.num_H, inst.num_I);
  ind.X = X;

  // Set inventory to 1.0 everywhere open (max capacity available)
  ind.R.assign(inst.num_H, 0.0);
  for (int ki = 0; ki < inst.num_H; ki++) {
    if (X[ki] == 1)
      ind.R[ki] = 1.0;
  }

  // Nearest assignment A based on euclidean distance
  ind.A.assign(inst.num_I, 0);
  vector<int> open_ki;
  for (int ki = 0; ki < inst.num_H; ki++) {
    if (X[ki])
      open_ki.push_back(ki);
  }

  if (!open_ki.empty()) {
    for (int ii = 0; ii < inst.num_I; ii++) {
      int di = inst.demand_idx[ii];
      double best_dist = inst.big_M;
      int best_ki = open_ki[0];
      for (int ki : open_ki) {
        int hi = inst.hub_idx[ki];
        double dx = inst.lat[di] - inst.lat[hi];
        double dy = inst.lon[di] - inst.lon[hi];
        double dist = dx * dx + dy * dy;
        if (dist < best_dist) {
          best_dist = dist;
          best_ki = ki;
        }
      }
      ind.A[ii] = best_ki;
    }
  }

  // W: balanced weights
  ind.W = {0.5, 0.5, 0.5, 0.5, 0.5, 0.5};

  decode(ind, inst);

  Solution sol;
  sol.Z1 = ind.Z1;
  sol.Z2 = ind.Z2;
  sol.CV = ind.CV;
  sol.X = ind.X;
  sol.R = ind.R;
  sol.A = ind.A;
  sol.W = ind.W;
  sol.meta = meta;

  pareto.push_back(sol);
}

int main(int argc, char *argv[]) {
  if (argc < 2) {
    cerr << "Usage: greedy_baseline <instance.json> [--out <path>]\n";
    return 1;
  }

  string inst_path = argv[1];
  string out_path = "";

  for (int i = 2; i < argc; i++) {
    const string arg = argv[i];
    if (arg == "--out" && i + 1 < argc)
      out_path = argv[++i];
  }

  DRNDInstance inst;
  try {
    inst = load_instance(inst_path);
  } catch (const std::exception &e) {
    cerr << "Error loading instance: " << e.what() << "\n";
    return 1;
  }

  set_rolling_seed(42);
  vector<Solution> pareto;

  // 1. Min-Cost Greedy
  vector<int> X_min_cost(inst.num_H, 0);
  vector<pair<double, int>> cost_idx;
  for (int ki = 0; ki < inst.num_H; ki++) {
    cost_idx.push_back({inst.F_hub[ki], ki});
  }
  std::sort(cost_idx.begin(), cost_idx.end());
  int num_to_open = std::min(3, inst.num_H);
  for (int i = 0; i < num_to_open; i++) {
    X_min_cost[cost_idx[i].second] = 1;
  }
  evaluate_greedy_config(X_min_cost, inst, "min_cost_greedy", pareto);

  // 2. Min-Depriv Greedy
  vector<int> X_min_depriv(inst.num_H, 1);
  evaluate_greedy_config(X_min_depriv, inst, "min_depriv_greedy", pareto);

  // JSON dump
  json j;
  j["meta"]["solver"] = "GreedyBaselineCPP";
  json jfront = json::array();
  for (const auto &s : pareto) {
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
