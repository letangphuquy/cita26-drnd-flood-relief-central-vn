// main.cpp — PB-NSMA / NSGA-II solver entry point
// Usage: solver.exe <instance.json> [options]
//
// Options:
//   --pop  <N>    population size (default: 100)
//   --gen  <N>    number of generations (default: 200)
//   --seed <N>    rolling seed iteration (default: 0)
//   --out  <path> output JSON path (default: stdout)
//   --algo <name> algorithm: nsma (PB-NSMA) or nsga2 (default: nsga2)
//   --ls   <N>    local search iters per generation (default: 5, NSMA only)
//
// Output JSON:
//   { "pareto_front": [ {Z1, Z2, CV, X, R, A, W}, ... ] }
//
// Compile (Windows/MSYS2 or Linux):
//   g++ -O2 -std=c++17 main.cpp -o solver
//   g++ -O2 -std=c++17 -fopenmp main.cpp -o solver   (with OpenMP)

#include "nsga2.hpp"

#include <fstream>
#include <sstream>
#include <stdexcept>

// ---------------------------------------------------------------------------
// CLI argument parsing
// ---------------------------------------------------------------------------
struct Args {
  string instance_path;
  string output_path = "";
  int pop_size = 100;
  int num_gen = 200;
  int seed_iter = 0;
  int log_every = 10;
  bool use_local_search = false; // --algo nsma
  int ls_iters = 5;              // --ls N
};

Args parse_args(int argc, char *argv[]) {
  if (argc < 2) {
    cerr << "Usage: solver <instance.json> [--pop N] [--gen N] [--seed N] "
            "[--out output.json] [--algo nsma|nsga2] [--ls N]\n";
    exit(1);
  }
  Args a;
  a.instance_path = argv[1];
  for (int i = 2; i < argc; i++) {
    string flag = argv[i];
    if (flag == "--pop" && i + 1 < argc)
      a.pop_size = std::stoi(argv[++i]);
    else if (flag == "--gen" && i + 1 < argc)
      a.num_gen = std::stoi(argv[++i]);
    else if (flag == "--seed" && i + 1 < argc)
      a.seed_iter = std::stoi(argv[++i]);
    else if (flag == "--out" && i + 1 < argc)
      a.output_path = argv[++i];
    else if (flag == "--log" && i + 1 < argc)
      a.log_every = std::stoi(argv[++i]);
    else if (flag == "--algo" && i + 1 < argc) {
      string algo = argv[++i];
      a.use_local_search = (algo == "nsma");
    } else if (flag == "--ls" && i + 1 < argc)
      a.ls_iters = std::stoi(argv[++i]);
  }
  return a;
}

// ---------------------------------------------------------------------------
// Output: write Pareto front to JSON
// ---------------------------------------------------------------------------
void write_output(const vector<Individual> &pop, std::ostream &out) {
  json j;
  j["pareto_front"] = json::array();
  for (const auto &ind : pop) {
    if (ind.rank == 1) {
      json sol;
      sol["Z1"] = ind.Z1;
      sol["Z2"] = ind.Z2;
      sol["CV"] = ind.CV;
      sol["rank"] = ind.rank;
      sol["X"] = ind.X;
      sol["R"] = ind.R;
      sol["A"] = ind.A;
      sol["W"] = ind.W;
      j["pareto_front"].push_back(sol);
    }
  }
  // Also write all feasible solutions for analysis
  j["all_feasible"] = json::array();
  for (const auto &ind : pop) {
    if (ind.CV == 0) {
      json sol;
      sol["Z1"] = ind.Z1;
      sol["Z2"] = ind.Z2;
      sol["rank"] = ind.rank;
      sol["crowding"] = ind.crowding;
      sol["X"] = ind.X;
      sol["R"] = ind.R;
      sol["A"] = ind.A;
      sol["W"] = ind.W;
      j["all_feasible"].push_back(sol);
    }
  }
  out << j.dump(2) << "\n";
}

// ---------------------------------------------------------------------------
// MAIN
// ---------------------------------------------------------------------------
int main(int argc, char *argv[]) {
  Args args = parse_args(argc, argv);

  cerr << "=== PB-NSMA Solver for MO-IHLNDP ===\n";
  cerr << "Instance : " << args.instance_path << "\n";
  cerr << "Algorithm: " << (args.use_local_search ? "PB-NSMA" : "NSGA-II")
       << "\n";
  cerr << "Pop size : " << args.pop_size << "\n";
  cerr << "Generations: " << args.num_gen << "\n";
  cerr << "Seed iter: " << args.seed_iter << "\n";

  // Load instance
  DRNDInstance inst;
  try {
    inst = load_instance(args.instance_path);
  } catch (const std::exception &e) {
    cerr << "Error loading instance: " << e.what() << "\n";
    return 1;
  }

  // Configure and run
  NSGAConfig cfg;
  cfg.pop_size = args.pop_size;
  cfg.num_gen = args.num_gen;
  cfg.seed_iter = args.seed_iter;
  cfg.log_every = args.log_every;
  cfg.use_local_search = args.use_local_search;
  cfg.ls_iters = args.ls_iters;

  auto population = run_nsga2(inst, cfg);

  // Output results
  if (args.output_path.empty()) {
    write_output(population, cout);
  } else {
    std::ofstream fout(args.output_path);
    if (!fout.is_open()) {
      cerr << "Cannot open output file: " << args.output_path << "\n";
      return 1;
    }
    write_output(population, fout);
    cerr << "[Output] Written to: " << args.output_path << "\n";
  }

  return 0;
}
