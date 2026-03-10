// greedy_baseline.cpp
// -----------------------------------------------------------------------------
// Manager-style rule-based baseline for MO-IHLNDP.
//
// Design intent:
// - Keep the heuristic simple and explainable (no metaheuristics).
// - Avoid MCF/decoder internals; use lightweight constructive logic.
// - Produce a small Pareto approximation for Exp1 comparisons.
//
// Workflow:
// 1) Score hubs with normalized cost/risk/coverage proxies.
// 2) Build candidate plans from fixed policies and top-k opened hubs.
// 3) Set inventory by simple pressure-based fill rules.
// 4) Evaluate each plan over scenarios using nearest-feasible assignments,
//    deficit-driven origin dispatch, and aggregate shortage penalties.
// 5) Keep non-dominated solutions and export JSON in the standard format.
// -----------------------------------------------------------------------------

#include "model.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <numeric>

using Clock = std::chrono::high_resolution_clock;
using Duration = std::chrono::duration<double>;

struct Solution {
  double Z1 = 0.0;
  double Z2 = 0.0;
  double CV = 0.0;
  vector<int> X;
  vector<double> R;
  vector<int> A;
  vector<double> W;
  string meta;
};

static bool dominates(const Solution &a, const Solution &b) {
  return a.Z1 <= b.Z1 && a.Z2 <= b.Z2 && (a.Z1 < b.Z1 || a.Z2 < b.Z2);
}

static void normalize_to_unit(vector<double> &v) {
  if (v.empty())
    return;
  double mn = *std::min_element(v.begin(), v.end());
  double mx = *std::max_element(v.begin(), v.end());
  double rg = mx - mn;
  if (rg <= 1e-12) {
    std::fill(v.begin(), v.end(), 0.5);
    return;
  }
  for (double &x : v)
    x = (x - mn) / rg;
}

static vector<Solution> pareto_filter(const vector<Solution> &pool) {
  vector<Solution> feasible;
  for (const auto &s : pool) {
    if (s.CV <= 1e-9)
      feasible.push_back(s);
  }
  const vector<Solution> &src = feasible.empty() ? pool : feasible;

  vector<Solution> front;
  for (size_t i = 0; i < src.size(); ++i) {
    bool dominated_flag = false;
    for (size_t j = 0; j < src.size(); ++j) {
      if (i == j)
        continue;
      if (dominates(src[j], src[i])) {
        dominated_flag = true;
        break;
      }
    }
    if (!dominated_flag)
      front.push_back(src[i]);
  }

  std::sort(front.begin(), front.end(), [](const Solution &a, const Solution &b) {
    return a.Z1 < b.Z1 || (a.Z1 == b.Z1 && a.Z2 < b.Z2);
  });

  front.erase(std::unique(front.begin(), front.end(), [](const Solution &a, const Solution &b) {
                return std::abs(a.Z1 - b.Z1) < 1e-6 && std::abs(a.Z2 - b.Z2) < 1e-6;
              }),
              front.end());
  return front;
}

static inline double best_cost(const DRNDInstance &inst, const Scenario &sc, int u, int v) {
  double best = inst.big_M;
  for (int m = 0; m < inst.num_M; ++m) {
    if (sc.acc(m, u, v))
      best = std::min(best, inst.C_cost[m][u][v]);
  }
  return best;
}

static inline double best_time(const DRNDInstance &inst, const Scenario &sc, int u, int v) {
  double best = inst.big_M;
  for (int m = 0; m < inst.num_M; ++m) {
    if (sc.acc(m, u, v))
      best = std::min(best, inst.C_time[m][u][v]);
  }
  return best;
}

static Solution evaluate_constructive(const DRNDInstance &inst, const vector<int> &open_set,
                                      const vector<double> &r_vals, const string &meta) {
  Solution out;
  out.X.assign(inst.num_H, 0);
  out.R.assign(inst.num_H, 0.0);
  out.A.assign(inst.num_I, 0);
  out.W = {0.5, 0.5, 0.5, 0.5, 0.5, 0.5};

  for (int ki : open_set)
    out.X[ki] = 1;
  for (size_t t = 0; t < open_set.size(); ++t)
    out.R[open_set[t]] = r_vals[t];

  vector<double> exp_demand(inst.num_I, 0.0);
  for (int si = 0; si < inst.num_S; ++si) {
    const auto &sc = inst.scenarios[si];
    for (int ii = 0; ii < inst.num_I; ++ii) {
      exp_demand[ii] += sc.prob * sc.demand[inst.demand_idx[ii]];
    }
  }

  for (int ii = 0; ii < inst.num_I; ++ii) {
    int i = inst.demand_idx[ii];
    double best_t = inst.big_M;
    int best_ki = open_set.empty() ? 0 : open_set[0];
    for (int ki : open_set) {
      int h = inst.hub_idx[ki];
      double t = 0.0;
      for (int si = 0; si < inst.num_S; ++si) {
        const auto &sc = inst.scenarios[si];
        t += sc.prob * best_time(inst, sc, i, h);
      }
      if (t < best_t) {
        best_t = t;
        best_ki = ki;
      }
    }
    out.A[ii] = best_ki;
  }

  for (int ki = 0; ki < inst.num_H; ++ki) {
    if (out.X[ki]) {
      out.Z1 += inst.F_hub[ki] + inst.c_hold[ki] * (out.R[ki] * inst.kappa[ki]);
    }
  }

  for (int si = 0; si < inst.num_S; ++si) {
    const auto &sc = inst.scenarios[si];
    double z1s = 0.0;
    double z2s = 0.0;

    vector<int> active;
    vector<double> stock(inst.num_H, 0.0);
    for (int ki = 0; ki < inst.num_H; ++ki) {
      if (!out.X[ki])
        continue;
      int h = inst.hub_idx[ki];
      if (sc.risk[h] <= inst.chi) {
        active.push_back(ki);
        stock[ki] = out.R[ki] * inst.kappa[ki];
      }
    }

    if (active.empty()) {
      int safest = 0;
      double best_r = 1e18;
      for (int ki = 0; ki < inst.num_H; ++ki) {
        int h = inst.hub_idx[ki];
        if (sc.risk[h] < best_r) {
          best_r = sc.risk[h];
          safest = ki;
        }
      }
      active.push_back(safest);
      z1s += sc.hub_reactive_cost[safest];
    }

    vector<double> hub_demand(inst.num_H, 0.0);
    vector<double> hub_supply(inst.num_H, 0.0);
    double total_demand_kg = 0.0;

    for (int ii = 0; ii < inst.num_I; ++ii) {
      int i = inst.demand_idx[ii];
      double D = sc.demand[i];
      double Dkg = inst.gamma * D;
      total_demand_kg += Dkg;

      int best_ki = -1;
      double best_c = inst.big_M;
      double best_t = inst.big_M;
      for (int ki : active) {
        int h = inst.hub_idx[ki];
        double c = best_cost(inst, sc, i, h);
        if (c < best_c) {
          best_c = c;
          best_t = best_time(inst, sc, i, h);
          best_ki = ki;
        }
      }

      if (best_ki < 0 || best_c >= inst.big_M * 0.5) {
        z1s += inst.big_M;
        out.CV += sc.prob * Dkg;
        continue;
      }

      hub_demand[best_ki] += Dkg;
      // Keep manager-style cost proxy simple and in decoder-like scale.
      z1s += inst.get_theta(best_ki, ii, si);

      // Deprivation proxy follows decoder's form (max across assigned demands).
      double omega = sc.hub_process_time[best_ki] + 2.0 * (best_t < inst.big_M ? best_t : 0.0);
      double lam = inst.get_lambda(ii, si);
      double depriv = D * std::expm1(std::min(lam * omega, 20.0));
      z2s = std::max(z2s, depriv);
    }

    vector<double> deficit(inst.num_H, 0.0);
    for (int ki = 0; ki < inst.num_H; ++ki) {
      deficit[ki] = std::max(0.0, hub_demand[ki] - stock[ki]);
    }

    for (int jj = 0; jj < inst.num_J; ++jj) {
      int j = inst.origin_idx[jj];
      double remaining = sc.supply[j];
      if (remaining <= 0.0)
        continue;

      while (remaining > 1e-9) {
        int best_ki = -1;
        double best_c = inst.big_M;
        for (int ki : active) {
          if (deficit[ki] <= 1e-9)
            continue;
          int h = inst.hub_idx[ki];
          double c = best_cost(inst, sc, j, h);
          if (c < best_c) {
            best_c = c;
            best_ki = ki;
          }
        }

        if (best_ki < 0 || best_c >= inst.big_M * 0.5)
          break;

        double send = std::min(remaining, deficit[best_ki]);
        if (send <= 1e-9)
          break;

        hub_supply[best_ki] += send;
        deficit[best_ki] -= send;
        remaining -= send;
        z1s += best_c * send;
      }
    }

    // Manager-style balancing: assume hubs can coordinate redistribution,
    // so we penalize only aggregate shortages, not per-hub mismatches.
    double total_available = 0.0;
    for (int ki = 0; ki < inst.num_H; ++ki)
      total_available += stock[ki] + hub_supply[ki];

    double shortage = std::max(0.0, total_demand_kg - total_available);
    if (shortage > 0.0) {
      double avg_hold = 0.0;
      for (double c : inst.c_hold)
        avg_hold += c;
      avg_hold /= std::max(1, inst.num_H);
      z1s += shortage * 10.0 * std::max(1.0, avg_hold);
      out.CV += sc.prob * shortage;
    }

    out.Z1 += sc.prob * z1s;
    out.Z2 += sc.prob * z2s;
  }

  out.meta = meta;
  return out;
}

int main(int argc, char *argv[]) {
  if (argc < 2) {
    cerr << "Usage: greedy_baseline <instance.json> [--out <path>]\n";
    return 1;
  }

  string inst_path = argv[1];
  string out_path;
  for (int i = 2; i < argc; ++i) {
    string a = argv[i];
    if (a == "--out" && i + 1 < argc)
      out_path = argv[++i];
  }

  DRNDInstance inst;
  try {
    inst = load_instance(inst_path);
  } catch (const std::exception &e) {
    cerr << "Error loading instance: " << e.what() << "\n";
    return 1;
  }

  auto t0 = Clock::now();

  vector<double> avg_risk(inst.num_H, 0.0);
  vector<double> exp_cover(inst.num_H, 0.0);
  for (int si = 0; si < inst.num_S; ++si) {
    const auto &sc = inst.scenarios[si];
    for (int ki = 0; ki < inst.num_H; ++ki) {
      int h = inst.hub_idx[ki];
      avg_risk[ki] += sc.prob * sc.risk[h];
    }
    for (int ii = 0; ii < inst.num_I; ++ii) {
      int i = inst.demand_idx[ii];
      double Dkg = inst.gamma * sc.demand[i];
      int best_ki = 0;
      double best_c = inst.big_M;
      for (int ki = 0; ki < inst.num_H; ++ki) {
        int h = inst.hub_idx[ki];
        double c = best_cost(inst, sc, i, h);
        if (c < best_c) {
          best_c = c;
          best_ki = ki;
        }
      }
      exp_cover[best_ki] += sc.prob * Dkg;
    }
  }

  vector<double> cost_norm = inst.F_hub;
  vector<double> risk_norm = avg_risk;
  vector<double> cover_norm = exp_cover;
  normalize_to_unit(cost_norm);
  normalize_to_unit(risk_norm);
  normalize_to_unit(cover_norm);

  struct Policy {
    double w_cost;
    double w_risk;
    double w_cover;
    double inv_base;
    const char *name;
  };

      vector<Policy> policies = {
        {0.75, 0.15, 0.10, 0.40, "lean_cost"},
          {0.25, 0.50, 0.25, 0.70, "risk_guard"},
      };

  vector<Solution> pool;
  for (const auto &p : policies) {
    vector<pair<double, int>> scored;
    scored.reserve(inst.num_H);
    for (int ki = 0; ki < inst.num_H; ++ki) {
      double score = -p.w_cost * cost_norm[ki] - p.w_risk * risk_norm[ki] + p.w_cover * cover_norm[ki];
      scored.push_back({score, ki});
    }
    std::sort(scored.begin(), scored.end(), [](auto &a, auto &b) { return a.first > b.first; });

    const int max_open = std::min(4, inst.num_H);
    for (int k = 1; k <= max_open; ++k) {
      vector<int> open_set;
      open_set.reserve(k);
      for (int t = 0; t < k; ++t)
        open_set.push_back(scored[t].second);

      vector<double> r_vals(k, p.inv_base);
      for (int t = 0; t < k; ++t) {
        int ki = open_set[t];
        double pressure = std::min(1.0, exp_cover[ki] / std::max(1.0, inst.kappa[ki]));
        r_vals[t] = std::min(1.0, std::max(0.05, 0.6 * p.inv_base + 0.4 * pressure));
      }

      pool.push_back(evaluate_constructive(inst, open_set, r_vals,
                                           string(p.name) + "_k" + std::to_string(k)));
    }
  }

  vector<Solution> front = pareto_filter(pool);
  auto t1 = Clock::now();
  double elapsed = Duration(t1 - t0).count();

  cerr << "[Greedy] Rule-based constructive pool: " << pool.size() << " candidates.\n";
  cerr << "[Greedy] Pareto front: " << front.size() << " solutions.\n";

  json j;
  j["meta"]["solver"] = "GreedyBaseline_ManagerStyle";
  j["meta"]["strategy"] = "rule_based_constructive";
  j["meta"]["elapsed_s"] = elapsed;

  json arr = json::array();
  for (const auto &s : front) {
    json row;
    row["Z1"] = s.Z1;
    row["Z2"] = s.Z2;
    row["CV"] = s.CV;
    row["rank"] = 1;
    row["meta"] = s.meta;
    row["X"] = s.X;
    row["R"] = s.R;
    row["A"] = s.A;
    row["W"] = s.W;
    arr.push_back(std::move(row));
  }
  j["pareto_front"] = arr;

  if (out_path.empty()) {
    cout << j.dump(2) << "\n";
  } else {
    std::ofstream fout(out_path);
    if (!fout.is_open()) {
      cerr << "Cannot open output: " << out_path << "\n";
      return 1;
    }
    fout << j.dump(2) << "\n";
    cerr << "[Output] " << out_path << "\n";
  }
  return 0;
}
