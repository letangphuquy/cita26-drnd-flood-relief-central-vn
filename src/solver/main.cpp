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
//   --pc       <f>   crossover probability (default: 0.98)
//   --pm-high  <f>   initial mutation rate base (default: 0.40)
//   --pm-low   <f>   final mutation rate base   (default: 0.10)
//   --sbx-eta-rw  <f> SBX distribution index for R/W segments (default: 1.5)
//   --pm-eta-rw   <f> polynomial mutation index for R/W segments (default: 8)
//   --stag     <N>   stagnation threshold in gens (default: 20)
//   --tourney  <N>   base tournament size (2=binary, default: 2)
//   --hyper-pulse        enable hypermutation pulse/cooldown
//   --no-stag-boost      disable stagnation diversity boost
//   --no-hyper-pulse     disable hypermutation pulse/cooldown
//   --no-hamming         disable Hamming tiebreak in elitist selection
//   --no-x-niche         disable X-niche quota preservation
//   --no-immigrants      disable partial random immigrants
//   --aega-pop           enable AEGA-style adaptive population control
//   --aega-min  <N>      minimum adaptive population size
//   --aega-max  <N>      maximum adaptive population size
//   --aega-step <N>      adaptation step for population size
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
  double pc = 0.98;
  double pm_high = 0.40;
  double pm_low = 0.10;
  double sbx_eta_rw = 1.5;
  double pm_eta_rw = 8.0;
  int stag_threshold = 20;
  int tournament_sz = 2;
  bool enable_stag_boost = true;
  bool enable_hyper_pulse = false;
  bool enable_hamming_tiebreak = true;
  bool enable_x_niche_quota = true;
  bool enable_random_immigrants = true;
  bool enable_aega_pop = false;
  int aega_min = 120;
  int aega_max = 320;
  int aega_step = 30;
};

Args parse_args(int argc, char *argv[]) {
  auto print_usage = []() {
    cerr << "Usage: solver <instance.json> [--pop N] [--gen N] [--seed N] "
            "[--out output.json] [--algo nsma|nsga2] [--ls N] "
            "[--pc f] [--pm-high f] [--pm-low f] "
            "[--sbx-eta-rw f] [--pm-eta-rw f] "
            "[--stag N] [--tourney N] "
            "[--hyper-pulse] [--no-stag-boost] [--no-hyper-pulse] [--no-hamming] "
            "[--no-x-niche] [--no-immigrants] [--aega-pop] [--aega-min N] "
            "[--aega-max N] [--aega-step N]\n";
  };

  if (argc < 2) {
    print_usage();
    exit(1);
  }
  if (string(argv[1]) == "--help" || string(argv[1]) == "-h") {
    print_usage();
    exit(0);
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
    else if (flag == "--pc" && i + 1 < argc)
      a.pc = std::stod(argv[++i]);
    else if (flag == "--pm-high" && i + 1 < argc)
      a.pm_high = std::stod(argv[++i]);
    else if (flag == "--pm-low" && i + 1 < argc)
      a.pm_low = std::stod(argv[++i]);
    else if (flag == "--sbx-eta-rw" && i + 1 < argc)
      a.sbx_eta_rw = std::stod(argv[++i]);
    else if (flag == "--pm-eta-rw" && i + 1 < argc)
      a.pm_eta_rw = std::stod(argv[++i]);
    else if (flag == "--stag" && i + 1 < argc)
      a.stag_threshold = std::stoi(argv[++i]);
    else if (flag == "--tourney" && i + 1 < argc)
      a.tournament_sz = std::stoi(argv[++i]);
    else if (flag == "--no-stag-boost")
      a.enable_stag_boost = false;
    else if (flag == "--hyper-pulse")
      a.enable_hyper_pulse = true;
    else if (flag == "--no-hyper-pulse")
      a.enable_hyper_pulse = false;
    else if (flag == "--no-hamming")
      a.enable_hamming_tiebreak = false;
    else if (flag == "--no-x-niche")
      a.enable_x_niche_quota = false;
    else if (flag == "--no-immigrants")
      a.enable_random_immigrants = false;
    else if (flag == "--aega-pop")
      a.enable_aega_pop = true;
    else if (flag == "--aega-min" && i + 1 < argc)
      a.aega_min = std::stoi(argv[++i]);
    else if (flag == "--aega-max" && i + 1 < argc)
      a.aega_max = std::stoi(argv[++i]);
    else if (flag == "--aega-step" && i + 1 < argc)
      a.aega_step = std::stoi(argv[++i]);
    else
      cerr << "[Warn] Unknown/ignored option: " << flag << "\n";
  }
  if (a.aega_min > a.aega_max)
    std::swap(a.aega_min, a.aega_max);
  a.aega_step = std::max(1, a.aega_step);
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
  j["meta"]["pc"] = args.pc;
  j["meta"]["pm_high"] = args.pm_high;
  j["meta"]["pm_low"] = args.pm_low;
  j["meta"]["sbx_eta_rw"] = args.sbx_eta_rw;
  j["meta"]["pm_eta_rw"] = args.pm_eta_rw;
  j["meta"]["stag_threshold"] = args.stag_threshold;
  j["meta"]["tournament_size"] = args.tournament_sz;
  j["meta"]["solver"] = string(args.use_local_search ? "PB-NSMA" : "PB-NSGA");

  // De-duplicate the Pareto front
  vector<Individual> p_front;
  for (const auto &ind : pop) {
    if (ind.rank == 1)
      p_front.push_back(ind);
  }
  std::sort(p_front.begin(), p_front.end(), [](const Individual &a, const Individual &b) {
    return a.Z1 < b.Z1 || (a.Z1 == b.Z1 && a.Z2 < b.Z2);
  });
  p_front.erase(std::unique(p_front.begin(), p_front.end(), [](const Individual &a, const Individual &b) {
    return std::abs(a.Z1 - b.Z1) < 1e-6 && std::abs(a.Z2 - b.Z2) < 1e-6;
  }), p_front.end());

  j["pareto_front"] = json::array();
  for (const auto &ind : p_front) {
    json sol;
    sol["Z1"] = ind.Z1;
    sol["Z2"] = ind.Z2;
    sol["CV"] = ind.CV;
    sol["rank"] = 1;
    sol["X"] = ind.X;
    sol["R"] = ind.R;
    sol["A"] = ind.A;
    sol["W"] = ind.W;
    j["pareto_front"].push_back(sol);
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
  cerr << "pc          : " << args.pc << "\n";
  cerr << "pm          : " << args.pm_high << "→" << args.pm_low << "\n";
  cerr << "eta_rw      : sbx_rw=" << args.sbx_eta_rw
       << " pm_rw=" << args.pm_eta_rw << "\n";
  cerr << "Tournament  : " << args.tournament_sz << "-way\n";
  cerr << "Stag thresh : " << args.stag_threshold << " gens\n";
  cerr << "Diversity   :"
      << " stag_boost=" << (args.enable_stag_boost ? "on" : "off")
      << " hyper_pulse=" << (args.enable_hyper_pulse ? "on" : "off")
      << " hamming=" << (args.enable_hamming_tiebreak ? "on" : "off")
      << " x_niche=" << (args.enable_x_niche_quota ? "on" : "off")
      << " immigrants=" << (args.enable_random_immigrants ? "on" : "off")
      << " aega_pop=" << (args.enable_aega_pop ? "on" : "off")
      << "\n";
  if (args.enable_aega_pop) {
    cerr << "AEGA-pop    : min=" << args.aega_min << " max=" << args.aega_max
         << " step=" << args.aega_step << "\n";
  }

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
  cfg.pc = args.pc;
  cfg.pm_high = args.pm_high;
  cfg.pm_low = args.pm_low;
  cfg.sbx_eta_rw = args.sbx_eta_rw;
  cfg.pm_eta_rw = args.pm_eta_rw;
  cfg.stagnation_threshold = args.stag_threshold;
  cfg.tournament_size = args.tournament_sz;
  cfg.enable_stagnation_boost = args.enable_stag_boost;
  cfg.enable_hypermutation_pulse = args.enable_hyper_pulse;
  cfg.enable_hamming_tiebreak = args.enable_hamming_tiebreak;
  cfg.enable_x_niche_quota = args.enable_x_niche_quota;
  cfg.enable_random_immigrants = args.enable_random_immigrants;
  cfg.enable_aega_adaptive_pop = args.enable_aega_pop;
  cfg.aega_pop_min = args.aega_min;
  cfg.aega_pop_max = args.aega_max;
  cfg.aega_pop_step = args.aega_step;

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
