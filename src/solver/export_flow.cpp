#include "decoder.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>


using std::cerr;
using std::cout;
using std::string;

int main(int argc, char *argv[]) {
  if (argc < 4) {
    cerr << "Usage: export_flow <instance.json> <results.json> "
            "<out_flow.json>\n";
    return 1;
  }

  string inst_path = argv[1];
  string res_path = argv[2];
  string out_path = argv[3];

  DRNDInstance inst;
  try {
    inst = load_instance(inst_path);
  } catch (const std::exception &e) {
    cerr << "Error loading instance: " << e.what() << "\n";
    return 1;
  }

  std::ifstream f(res_path);
  if (!f.is_open()) {
    cerr << "Could not open " << res_path << "\n";
    return 1;
  }
  json j_res;
  f >> j_res;

  // Pick median Z1 from pareto_front
  auto pf = j_res["pareto_front"];
  if (pf.empty()) {
    cerr << "pareto_front is empty in " << res_path << "\n";
    return 1;
  }

  // Sort by Z1 to find median
  std::sort(pf.begin(), pf.end(), [](const json &a, const json &b) {
    return a["Z1"].get<double>() < b["Z1"].get<double>();
  });

  json sol = pf[pf.size() / 2]; // median
  cerr << "Selected solution from " << res_path << " with Z1=" << sol["Z1"]
       << " Z2=" << sol["Z2"] << "\n";

  Individual ind(inst.num_H, inst.num_I);
  for (int k = 0; k < inst.num_H; k++)
    ind.X[k] = sol["X"][k].get<int>();
  for (int k = 0; k < inst.num_H; k++)
    ind.R[k] = sol["R"][k].get<double>();
  for (int i = 0; i < inst.num_I; i++)
    ind.A[i] = sol["A"][i].get<int>();
  for (int w = 0; w < 6; w++)
    ind.W[w] = sol["W"][w].get<double>();

  FlowDetails fd;
  decode(ind, inst, &fd);

  // Dump FlowDetails to json
  json j_out;
  j_out["meta"] = {{"Z1", ind.Z1},
                   {"Z2", ind.Z2},
                   {"CV", ind.CV},
                   {"X", ind.X},
                   {"R", ind.R}};

  j_out["scenarios"] = json::array();
  for (int si = 0; si < inst.num_S; si++) {
    json j_s;
    j_s["scenario"] = si;

    j_s["y_ks"] = fd.y_ks[si];
    j_s["inventory_held"] = fd.inventory_held[si];

    j_s["demand_assignments"] = json::array();
    for (int ii = 0; ii < inst.num_I; ii++) {
      json a;
      a["demand_idx"] = inst.demand_idx[ii];
      a["hub_idx"] =
          fd.z_iks[si][ii] != -1 ? inst.hub_idx[fd.z_iks[si][ii]] : -1;
      a["mode"] = fd.z_iks_m[si][ii];
      j_s["demand_assignments"].push_back(a);
    }

    j_s["origin_assignments"] = json::array();
    for (int jj = 0; jj < inst.num_J; jj++) {
      json a;
      a["origin_idx"] = inst.origin_idx[jj];
      a["hub_idx"] =
          fd.z_jks[si][jj] != -1 ? inst.hub_idx[fd.z_jks[si][jj]] : -1;
      a["mode"] = fd.z_jks_m[si][jj];
      j_s["origin_assignments"].push_back(a);
    }

    j_s["transshipment"] = json::array();
    for (const auto &tr : fd.f_khms[si]) {
      json t;
      t["src_hub_idx"] = inst.hub_idx[tr.src_ki];
      t["dst_hub_idx"] = inst.hub_idx[tr.dst_ki];
      t["mode"] = tr.m;
      t["flow"] = tr.flow;
      j_s["transshipment"].push_back(t);
    }

    j_out["scenarios"].push_back(j_s);
  }

  std::ofstream outf(out_path);
  if (!outf.is_open()) {
    cerr << "Cannot open Output file " << out_path << "\n";
    return 1;
  }
  outf << j_out.dump(2);
  cerr << "Dumped flows to " << out_path << "\n";

  return 0;
}
