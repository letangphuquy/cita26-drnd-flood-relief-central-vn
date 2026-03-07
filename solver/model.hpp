// model.hpp — DRND data model and JSON loader
// Disaster Relief Network Design (MO-IHLNDP)
// Reads instances produced by data/generate_synthetic.py or
// data/process_benchmark.py
//
// Input JSON format (see generate_synthetic.py for full spec):
//   dimensions.num_I, num_H, num_J, num_S, num_M
//   nodes.demand_indices, hub_indices, origin_indices, coords
//   hub_params.capacity, fixed_cost, hold_cost
//   global_params.alpha, chi, gamma, big_M, daganzo_phi, daganzo_eta
//   transport.cost[m][u][v], transport.time[m][u][v]
//   scenarios[s].probability, risk[u], accessibility[m][u][v],
//               demand[i], supply[j], hub_reactive_cost[k], hub_process_time[k]
//   theta[h_idx][i_idx][s_idx]
//   lambda["{i}_{s}"]
#pragma once

#include "json.hpp"
#include "template.hpp"


#include <cassert>
#include <fstream>
#include <sstream>
#include <stdexcept>


using json = nlohmann::json;

// ---------------------------------------------------------------------------
// Scenario data
// ---------------------------------------------------------------------------
struct Scenario {
  string name;
  double prob; // π_s

  // risk[u] — risk index of node u in this scenario
  vector<double> risk;

  // accessibility[m][u][v] — 1 if link (u,v) via mode m is usable
  // stored as a[mode * n2 + u * n + v] for fast access
  int num_modes, n_total;
  vector<vector<vector<int>>> a; // a[m][u][v]

  inline int acc(int m, int u, int v) const { return a[m][u][v]; }

  // demand[i] — number of people at demand node i (absolute node index)
  vector<double> demand;
  // supply[j] — relief items at origin j
  vector<double> supply;

  // hub reactive setup cost F^a[k]  (absolute hub index → value)
  vector<double> hub_reactive_cost;
  // hub processing time τ_ks
  vector<double> hub_process_time;
};

// ---------------------------------------------------------------------------
// Full DRND instance
// ---------------------------------------------------------------------------
struct DRNDInstance {
  // ── Dimensions ──────────────────────────────────────────────────────
  int num_I;   // demand nodes
  int num_H;   // hub candidates
  int num_J;   // origins
  int num_S;   // scenarios
  int num_M;   // transport modes (3: road, water, air)
  int n_total; // = num_I + num_H + num_J

  // ── Node sets (absolute indices 0..n_total-1) ────────────────────────
  vector<int> demand_idx; // demand node indices
  vector<int> hub_idx;    // hub candidate indices
  vector<int> origin_idx; // origin indices

  // For fast lookup: is_hub[u] = position in hub_idx, -1 if not hub
  vector<int> hub_pos; // hub_pos[u] = local hub index ki if u is hub, else -1

  // ── Node coordinates ─────────────────────────────────────────────────
  vector<double> lat, lon;

  // ── Global parameters ────────────────────────────────────────────────
  double alpha; // inter-hub economies-of-scale discount
  double chi;   // max acceptable risk threshold for active hub
  double gamma; // conversion factor (relief items per person)
  double big_M; // penalty cost
  double daganzo_phi;
  double daganzo_eta;

  // ── Hub parameters (indexed by local hub index ki = 0..num_H-1) ─────
  vector<double> kappa;  // capacity κ_k
  vector<double> F_hub;  // fixed cost F_k
  vector<double> c_hold; // holding cost c_k

  // ── Transport matrices (mode, u, v) ──────────────────────────────────
  // C_cost[m][u][v] = unit transportation cost
  // C_time[m][u][v] = travel time in hours
  vector<vector<vector<double>>> C_cost; // [num_M][n_total][n_total]
  vector<vector<vector<double>>> C_time;

  // ── Scenarios ────────────────────────────────────────────────────────
  vector<Scenario> scenarios;

  // ── Pre-computed Daganzo CA cost ─────────────────────────────────────
  // theta[ki][ii][si] = Theta_{k,i,s}  (local hub idx, local demand idx,
  // scenario idx)
  vector<vector<vector<double>>> theta;

  // ── Deprivation sensitivity ──────────────────────────────────────────
  // lambda[ii][si] = λ_{i,s}
  vector<vector<double>> lambda;

  // ── Convenience accessors ─────────────────────────────────────────────
  double get_theta(int ki, int ii, int si) const { return theta[ki][ii][si]; }
  double get_lambda(int ii, int si) const { return lambda[ii][si]; }
  double get_cost(int m, int u, int v) const { return C_cost[m][u][v]; }
  double get_time(int m, int u, int v) const { return C_time[m][u][v]; }

  // Best feasible cost from u→v (min over modes with a[m][u][v]=1 in scenario
  // s)
  double best_cost(int u, int v, int si) const {
    double best = big_M;
    for (int m = 0; m < num_M; m++) {
      if (scenarios[si].acc(m, u, v))
        umin(best, C_cost[m][u][v]);
    }
    return best;
  }
  double best_time(int u, int v, int si) const {
    double best = big_M;
    for (int m = 0; m < num_M; m++) {
      if (scenarios[si].acc(m, u, v))
        umin(best, C_time[m][u][v]);
    }
    return best;
  }
};

// ---------------------------------------------------------------------------
// JSON Loading
// ---------------------------------------------------------------------------
DRNDInstance load_instance(const string &path) {
  std::ifstream fin(path);
  if (!fin.is_open())
    throw std::runtime_error("Cannot open instance file: " + path);

  json jv;
  fin >> jv;

  DRNDInstance inst;

  // Dimensions
  inst.num_I = jv["dimensions"]["num_I"];
  inst.num_H = jv["dimensions"]["num_H"];
  inst.num_J = jv["dimensions"]["num_J"];
  inst.num_S = jv["dimensions"]["num_S"];
  inst.num_M = jv["dimensions"]["num_M"];
  inst.n_total = inst.num_I + inst.num_H + inst.num_J;

  // Node sets
  inst.demand_idx = jv["nodes"]["demand_indices"].get<vector<int>>();
  inst.hub_idx = jv["nodes"]["hub_indices"].get<vector<int>>();
  inst.origin_idx = jv["nodes"]["origin_indices"].get<vector<int>>();

  // Coordinates
  const auto &coords_j = jv["nodes"]["coords"];
  inst.lat.resize(inst.n_total);
  inst.lon.resize(inst.n_total);
  for (int u = 0; u < inst.n_total; u++) {
    inst.lat[u] = coords_j[u][0];
    inst.lon[u] = coords_j[u][1];
  }

  // Hub position lookup
  inst.hub_pos.assign(inst.n_total, -1);
  for (int ki = 0; ki < (int)inst.hub_idx.size(); ki++)
    inst.hub_pos[inst.hub_idx[ki]] = ki;

  // Global params
  inst.alpha = jv["global_params"]["alpha"];
  inst.chi = jv["global_params"]["chi"];
  inst.gamma = jv["global_params"]["gamma"];
  inst.big_M = jv["global_params"]["big_M"];
  inst.daganzo_phi = jv["global_params"]["daganzo_phi"];
  inst.daganzo_eta = jv["global_params"]["daganzo_eta"];

  // Hub params (keyed by absolute index as string)
  inst.kappa.resize(inst.num_H);
  inst.F_hub.resize(inst.num_H);
  inst.c_hold.resize(inst.num_H);
  const auto &hpj = jv["hub_params"];
  for (int ki = 0; ki < inst.num_H; ki++) {
    string ks = std::to_string(inst.hub_idx[ki]);
    inst.kappa[ki] = hpj["capacity"][ks];
    inst.F_hub[ki] = hpj["fixed_cost"][ks];
    inst.c_hold[ki] = hpj["hold_cost"][ks];
  }

  // Transport matrices
  const auto &trj = jv["transport"];
  int M = inst.num_M, N = inst.n_total;
  inst.C_cost.assign(M, vector<vector<double>>(N, vector<double>(N, 0.0)));
  inst.C_time.assign(M, vector<vector<double>>(N, vector<double>(N, 0.0)));
  for (int m = 0; m < M; m++) {
    for (int u = 0; u < N; u++) {
      for (int v = 0; v < N; v++) {
        inst.C_cost[m][u][v] = trj["cost"][m][u][v];
        inst.C_time[m][u][v] = trj["time"][m][u][v];
      }
    }
  }

  // Scenarios
  inst.scenarios.resize(inst.num_S);
  for (int si = 0; si < inst.num_S; si++) {
    const auto &sj = jv["scenarios"][si];
    Scenario &sc = inst.scenarios[si];
    sc.name = sj["name"];
    sc.prob = sj["probability"];
    sc.num_modes = M;
    sc.n_total = N;

    sc.risk = sj["risk"].get<vector<double>>();

    // Accessibility a[m][u][v]
    sc.a.assign(M, vector<vector<int>>(N, vector<int>(N, 1)));
    for (int m = 0; m < M; m++)
      for (int u = 0; u < N; u++)
        for (int v = 0; v < N; v++)
          sc.a[m][u][v] = sj["accessibility"][m][u][v];

    // Demand & supply (key = absolute index as string)
    sc.demand.assign(N, 0.0);
    for (auto &[k, val] : sj["demand"].items())
      sc.demand[std::stoi(k)] = val;

    sc.supply.assign(N, 0.0);
    for (auto &[k, val] : sj["supply"].items())
      sc.supply[std::stoi(k)] = val;

    // Hub reactive cost and processing time (local hub index)
    sc.hub_reactive_cost.resize(inst.num_H);
    sc.hub_process_time.resize(inst.num_H);
    for (int ki = 0; ki < inst.num_H; ki++) {
      string ks = std::to_string(inst.hub_idx[ki]);
      sc.hub_reactive_cost[ki] = sj["hub_reactive_cost"][ks];
      sc.hub_process_time[ki] = sj["hub_process_time"][ks];
    }
  }

  // Theta[ki][ii][si]
  int num_h = inst.num_H, num_i = inst.num_I, num_s = inst.num_S;
  inst.theta.assign(num_h,
                    vector<vector<double>>(num_i, vector<double>(num_s, 0.0)));
  for (int ki = 0; ki < num_h; ki++)
    for (int ii = 0; ii < num_i; ii++)
      for (int si = 0; si < num_s; si++)
        inst.theta[ki][ii][si] = jv["theta"][ki][ii][si];

  // Lambda[ii][si]
  inst.lambda.assign(num_i, vector<double>(num_s, 0.0));
  for (int ii = 0; ii < num_i; ii++) {
    for (int si = 0; si < num_s; si++) {
      string key =
          std::to_string(inst.demand_idx[ii]) + "_" + std::to_string(si);
      if (jv["lambda"].contains(key))
        inst.lambda[ii][si] = jv["lambda"][key];
    }
  }

  cerr << "[model] Loaded: " << path << "\n";
  cerr << "  I=" << inst.num_I << " H=" << inst.num_H << " J=" << inst.num_J
       << " S=" << inst.num_S << " M=" << inst.num_M << "\n";

  return inst;
}
