// evaluate_oos.cpp — Out-Of-Sample & SAA Evaluator
// Reads a Pareto front JSON (generated from 3 scenarios) and evaluates
// the contained individuals (X, R, A, W) on a new instance JSON (e.g., SAA100
// or OOS).
//
// Usage: evaluate_oos <instance.json> <pareto_front.json> <output.json>
//
// Compile: g++ -O2 -std=c++17 evaluate_oos.cpp -o evaluate_oos

#include "decoder.hpp"
#include <fstream>
#include <iostream>
#include <string>

using namespace std;

int main(int argc, char *argv[]) {
  if (argc < 4) {
    cerr << "Usage: evaluate_oos <instance.json> <pareto_front.json> "
            "<output.json>\n";
    return 1;
  }

  string inst_path = argv[1];
  string pareto_path = argv[2];
  string out_path = argv[3];

  cerr << "=== Out-Of-Sample Evaluator ===\n";
  cerr << "Instance : " << inst_path << "\n";
  cerr << "Pareto   : " << pareto_path << "\n";

  // 1. Load Instance
  DRNDInstance inst;
  try {
    inst = load_instance(inst_path);
  } catch (const exception &e) {
    cerr << "Error loading instance: " << e.what() << "\n";
    return 1;
  }
  cerr << "Instance loaded. I=" << inst.num_I << " H=" << inst.num_H
       << " J=" << inst.num_J << " S=" << inst.num_S << "\n";

  // 2. Load Pareto Front
  ifstream fin(pareto_path);
  if (!fin.is_open()) {
    cerr << "Error opening pareto JSON: " << pareto_path << "\n";
    return 1;
  }
  json pareto_json;
  fin >> pareto_json;

  auto pareto_array = pareto_json["pareto_front"];
  cerr << "Loaded " << pareto_array.size() << " solutions from Pareto front.\n";

  // 3. Evaluate each individual
  json out_json;
  out_json["meta"]["instance"] = inst_path;
  out_json["meta"]["pareto_source"] = pareto_path;
  out_json["evaluations"] = json::array();

  int idx = 0;
  for (const auto &jsol : pareto_array) {
    Individual ind(inst.num_H, inst.num_I);
    ind.X = jsol["X"].get<vector<int>>();
    ind.R = jsol["R"].get<vector<double>>();
    ind.A = jsol["A"].get<vector<int>>();
    ind.W = jsol["W"].get<vector<double>>();

    // Decode on the new instance
    decode(ind, inst);

    json result;
    result["idx"] = idx++;
    result["orig_Z1"] = jsol.contains("Z1") ? jsol["Z1"].get<double>() : -1;
    result["orig_Z2"] = jsol.contains("Z2") ? jsol["Z2"].get<double>() : -1;
    result["new_Z1"] = ind.Z1;
    result["new_Z2"] = ind.Z2;
    result["new_CV"] = ind.CV;
    result["X"] = ind.X;
    result["W"] = ind.W;

    out_json["evaluations"].push_back(result);
  }

  // 4. Save
  ofstream fout(out_path);
  if (!fout.is_open()) {
    cerr << "Error opening output file: " << out_path << "\n";
    return 1;
  }
  fout << out_json.dump(2) << "\n";

  cerr << "Evaluation complete. Saved to " << out_path << "\n";
  return 0;
}
