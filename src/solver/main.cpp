// main.cpp — PB-NSGA / PB-NSMA solver entry point
// Usage: solver.exe <instance.json> [options]
//
// Options:
//   --pop      <N>   population size (default: 200)
//   --gen      <N>   number of generations (default: 300)
//   --seed     <N>   rolling seed iteration (default: 0)
//   --out      <path> output JSON path (default: stdout)
//   --algo     <name> algorithm: nsma (PB-NSMA) or nsga2 (default: nsga2)
//   --ls       <N>   local search iters per generation (default: 5, NSMA only)
//   --pm-high  <f>   initial mutation rate base (default: 0.40)
//   --pm-low   <f>   final mutation rate base   (default: 0.10)
//   --stag     <N>   stagnation threshold in gens (default: 20)
//   --tourney  <N>   base tournament size (2=binary, default: 2)
//
// Output JSON:
//   { "pareto_front": [ {Z1, Z2, CV, X, R, A, W}, ... ] }
//
// Compile (Windows/MSYS2 or Linux):
//   g++ -O2 -std=c++17 main.cpp -o solver.exe

#include "nsga2.hpp"

#include <chrono>
#include <ctime>
#include <fstream>
#include <sstream>
#include <stdexcept>

// ---------------------------------------------------------------------------
// CLI argument parsing
// ---------------------------------------------------------------------------
struct Args {
  string instance_path;
  string output_path = "";
  int pop_size = 200; // ↑ from 100
  int num_gen = 300;  // ↑ from 200
  int seed_iter = 0;
  int log_every = 10;
  bool use_local_search = false;
  int ls_iters = 5;
  double pm_high = 0.40;
  double pm_low = 0.10;
  int stag_threshold = 20;
  int tournament_sz = 2;
};

Args parse_args(int argc, char *argv[]) {
  if (argc < 2) {
    cerr << "Usage: solver <instance.json> [--pop N] [--gen N] [--seed N] "
            "[--out output.json] [--algo nsma|nsga2] [--ls N] "
            "[--pm-high f] [--pm-low f] [--stag N] [--tourney N]\n";
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
    else if (flag == "--pm-high" && i + 1 < argc)
      a.pm_high = std::stod(argv[++i]);
    else if (flag == "--pm-low" && i + 1 < argc)
      a.pm_low = std::stod(argv[++i]);
    else if (flag == "--stag" && i + 1 < argc)
      a.stag_threshold = std::stoi(argv[++i]);
    else if (flag == "--tourney" && i + 1 < argc)
      a.tournament_sz = std::stoi(argv[++i]);
  }
  return a;
}

// ---------------------------------------------------------------------------
// Output: write Pareto front to JSON
// ---------------------------------------------------------------------------
void write_output(const vector<Individual> &pop, std::ostream &out,
                  double elapsed_s, double cpu_s, const Args &args) {
  json j;
  j["meta"]["elapsed_s"] = elapsed_s;
  j["meta"]["cpu_time_s"] = cpu_s;
  j["meta"]["seed"] = args.seed_iter;
  j["meta"]["pop_size"] = args.pop_size;
  j["meta"]["num_gen"] = args.num_gen;
  j["meta"]["pm_high"] = args.pm_high;
  j["meta"]["pm_low"] = args.pm_low;
  j["meta"]["stag_threshold"] = args.stag_threshold;
  j["meta"]["tournament_size"] = args.tournament_sz;
  j["meta"]["solver"] = string(args.use_local_search ? "PB-NSMA" : "PB-NSGA");

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

  cerr << "=== PB-NSGA Solver for MO-IHLNDP ===\n";
  cerr << "Instance    : " << args.instance_path << "\n";
  cerr << "Algorithm   : " << (args.use_local_search ? "PB-NSMA" : "PB-NSGA")
       << "\n";
  cerr << "Pop size    : " << args.pop_size << "\n";
  cerr << "Generations : " << args.num_gen << "\n";
  cerr << "Seed        : " << args.seed_iter << "\n";
  cerr << "pm          : " << args.pm_high << "→" << args.pm_low << "\n";
  cerr << "Tournament  : " << args.tournament_sz << "-way\n";
  cerr << "Stag thresh : " << args.stag_threshold << " gens\n";

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
  cfg.pm_high = args.pm_high;
  cfg.pm_low = args.pm_low;
  cfg.stagnation_threshold = args.stag_threshold;
  cfg.tournament_size = args.tournament_sz;

  auto t_start = std::chrono::steady_clock::now();
  std::clock_t c_start = std::clock();
  auto population = run_nsga2(inst, cfg);
  std::clock_t c_end = std::clock();
  auto t_end = std::chrono::steady_clock::now();
  double elapsed_s = std::chrono::duration<double>(t_end - t_start).count();
  double cpu_s = 1.0 * (c_end - c_start) / CLOCKS_PER_SEC;
  cerr << "[Time] " << elapsed_s << " s (CPU: " << cpu_s << " s)\n";

  // Output results
  if (args.output_path.empty()) {
    write_output(population, cout, elapsed_s, cpu_s, args);
  } else {
    std::ofstream fout(args.output_path);
    if (!fout.is_open()) {
      cerr << "Cannot open output file: " << args.output_path << "\n";
      return 1;
    }
    write_output(population, fout, elapsed_s, cpu_s, args);
    cerr << "[Output] Written to: " << args.output_path << "\n";
  }

  return 0;
}
