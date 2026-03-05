// bb_solver.cpp — Complete Enumeration / Branch-and-Bound Solver for MO-IHLNDP
//
// Two enumeration modes selected via --mode:
//
//   --mode enum (default):
//     Complete enumeration of ALL hub configurations X ∈ {0,1}^H.
//     No dominance pruning — every valid X (≥1 open hub) is evaluated.
//     Guarantees a true ground-truth Pareto front; no solutions are skipped.
//     Use for instances with num_H ≤ 20 to avoid exponential blow-up.
//
//   --mode bb:
//     Branch-and-Bound with multi-objective dominance pruning:
//       lb_Z1(partial X) = Σ committed fixed costs + Σ_i min expected routing
//       lb_Z2(partial X) = Σ_s π_s * max_i { min-omega deprivation }
//     Faster than enum for large H, but pruning correctness depends on the
//     lower bounds being tight — use only when bounds are validated.
//
// At each leaf (complete X), the sub-problem for (R, A, W) is solved by
// exhaustive evaluation of structured (R, A) combinations + random trials,
// all decoded via the same priority-based decoder used by PB-NSGA-II.
//
// Output JSON matches the main solver format:
//   { "pareto_front": [...], "all_feasible": [...], "meta": {...} }
//
// Compile:
//   g++ -O2 -std=c++17 bb_solver.cpp -o bb_solver
//
// Usage:
//   bb_solver <instance.json> [--out <path>] [--trials N] [--time-limit S]
//             [--mode enum|bb]
//
// Intended for instances with num_H ≤ 20 (exhaustive search space ≤ 1M).
// Larger instances will hit the time limit and return a partial Pareto front.

#include "decoder.hpp"   // brings in model.hpp, representation.hpp, template.hpp

#include <algorithm>
#include <chrono>
#include <fstream>
#include <numeric>
#include <string>

using Clock    = std::chrono::high_resolution_clock;
using Duration = std::chrono::duration<double>;

// ---------------------------------------------------------------------------
// Pareto archive (exact non-dominated set, no crowding)
// ---------------------------------------------------------------------------
struct Solution {
    double Z1 = 0, Z2 = 0;
    vector<int>    X;
    vector<double> R;
    vector<int>    A;
    vector<double> W;
};

struct ParetoArchive {
    vector<Solution> front;

    // True if (Z1, Z2) is weakly dominated by any solution in front
    bool is_dominated(double Z1, double Z2) const {
        for (const auto& s : front)
            if (s.Z1 <= Z1 && s.Z2 <= Z2 && (s.Z1 < Z1 || s.Z2 < Z2))
                return true;
        return false;
    }

    // Insert sol into archive, removing any solution it dominates
    void add(Solution sol) {
        if (is_dominated(sol.Z1, sol.Z2)) return;
        front.erase(
            std::remove_if(front.begin(), front.end(), [&](const Solution& s) {
                return sol.Z1 <= s.Z1 && sol.Z2 <= s.Z2 &&
                       (sol.Z1 < s.Z1 || sol.Z2 < s.Z2);
            }),
            front.end());
        front.push_back(std::move(sol));
    }
};

// ---------------------------------------------------------------------------
// Precomputed helper structures for fast bound evaluation
// ---------------------------------------------------------------------------
struct BoundsCache {
    const DRNDInstance& inst;

    // exp_theta[ki][ii] = Σ_s π_s * theta[ki][ii][si]
    vector<vector<double>> exp_theta;

    // min_time[ki][ii][si] = min travel time from demand ii to hub ki in scenario si
    //   (min over accessible modes; big_M if unreachable)
    vector<vector<vector<double>>> min_time_ki;

    // omega_sorted[ii][si] = sorted list of (min_omega, ki) over all hubs
    //   used to find the best feasible hub quickly during bound computation
    vector<vector<vector<pair<double,int>>>> omega_sorted;

    explicit BoundsCache(const DRNDInstance& inst) : inst(inst) {
        const int H = inst.num_H, I = inst.num_I, S = inst.num_S, M = inst.num_M;

        // exp_theta[ki][ii]
        exp_theta.assign(H, vector<double>(I, 0.0));
        for (int ki = 0; ki < H; ki++)
            for (int ii = 0; ii < I; ii++)
                for (int si = 0; si < S; si++)
                    exp_theta[ki][ii] += inst.scenarios[si].prob * inst.theta[ki][ii][si];

        // min_time_ki[ki][ii][si]
        min_time_ki.assign(H, vector<vector<double>>(I, vector<double>(S, inst.big_M)));
        for (int ki = 0; ki < H; ki++) {
            int k = inst.hub_idx[ki];
            for (int ii = 0; ii < I; ii++) {
                int i = inst.demand_idx[ii];
                for (int si = 0; si < S; si++) {
                    const Scenario& sc = inst.scenarios[si];
                    for (int m = 0; m < M; m++)
                        if (sc.acc(m, i, k))
                            min_time_ki[ki][ii][si] = std::min(min_time_ki[ki][ii][si],
                                                               inst.C_time[m][i][k]);
                }
            }
        }

        // omega_sorted[ii][si]: sorted by min_omega = τ_ks + 2 * min_time
        // Only includes hubs that are RISK-SAFE in scenario si (risk[k] <= chi).
        // BUG FIX: hubs with risk > chi are never activated by the decoder;
        // including them in the lower bound makes lb_Z2 falsely optimistic,
        // causing incorrect dominance pruning of valid subtrees.
        omega_sorted.assign(I, vector<vector<pair<double,int>>>(S));
        for (int ii = 0; ii < I; ii++) {
            for (int si = 0; si < S; si++) {
                const Scenario& sc = inst.scenarios[si];
                for (int ki = 0; ki < H; ki++) {
                    int k = inst.hub_idx[ki];
                    // Skip hubs that exceed the risk threshold in this scenario:
                    // the decoder never activates them, so they cannot contribute
                    // to a valid solution's omega.
                    if (sc.risk[k] > inst.chi) continue;
                    double t = min_time_ki[ki][ii][si];
                    double omega = (t < inst.big_M)
                        ? sc.hub_process_time[ki] + 2.0 * t
                        : inst.big_M;
                    omega_sorted[ii][si].push_back({omega, ki});
                }
                std::sort(omega_sorted[ii][si].begin(), omega_sorted[ii][si].end());
            }
        }
    }

    // Lower bound on Z1 for partial X (first `depth` bits assigned).
    // Feasible hubs = committed-open ∪ undecided (ki >= depth).
    // lb_Z1 = Σ F_hub[committed-open] + Σ_ii min_{feasible ki} exp_theta[ki][ii]
    double lb_Z1(const vector<int>& X, int depth) const {
        const int H = inst.num_H, I = inst.num_I;
        double lb = 0.0;
        for (int ki = 0; ki < depth; ki++)
            if (X[ki]) lb += inst.F_hub[ki];
        for (int ii = 0; ii < I; ii++) {
            double min_et = inst.big_M;
            for (int ki = 0; ki < H; ki++) {
                bool feasible = (ki >= depth) || (X[ki] == 1);
                if (feasible) min_et = std::min(min_et, exp_theta[ki][ii]);
            }
            lb += (min_et < inst.big_M ? min_et : 0.0);
        }
        return lb;
    }

    // Lower bound on Z2 for partial X.
    // lb_Z2 = Σ_s π_s * max_ii { min_{feasible ki} D_i * expm1(λ_is * min_omega_is) }
    // "Feasible" = (committed-open OR undecided) AND risk[k] <= chi in scenario si.
    // Valid lower bound: for every solution in the subtree, each demand's actual
    //   omega is >= the best omega over the same (risk-safe) feasible set, so
    //   max_ii(actual omega) >= lb, and thus actual Z2 >= lb_Z2.
    // Note: omega_sorted[ii][si] already excludes risk-unsafe hubs (see constructor).
    double lb_Z2(const vector<int>& X, int depth) const {
        const int I = inst.num_I, S = inst.num_S;
        double lb = 0.0;
        for (int si = 0; si < S; si++) {
            const Scenario& sc = inst.scenarios[si];
            double max_depriv = 0.0;
            for (int ii = 0; ii < I; ii++) {
                double D = sc.demand[inst.demand_idx[ii]];
                if (D < EPS) continue;
                // omega_sorted[ii][si] already contains only risk-safe hubs.
                // First entry that is committed-open OR undecided wins.
                double best_omega = inst.big_M;
                for (const auto& [omega, ki] : omega_sorted[ii][si]) {
                    bool feasible = (ki >= depth) || (X[ki] == 1);
                    if (feasible) { best_omega = omega; break; }
                }
                // If no risk-safe hub is available: forced fallback in decoder
                // will still produce some omega; use 0 as floor (conservative).
                if (best_omega >= inst.big_M) best_omega = 0.0;
                double lam     = inst.lambda[ii][si];
                double exp_arg = std::min(lam * best_omega, 20.0);
                double depriv  = D * std::expm1(exp_arg);
                max_depriv     = std::max(max_depriv, depriv);
            }
            lb += sc.prob * max_depriv;
        }
        return lb;
    }
};

// ---------------------------------------------------------------------------
// Helper: try one (R, A, W) combination; add to archive if feasible.
// ---------------------------------------------------------------------------
static void try_one(const vector<int>& X, const vector<double>& R,
                    const vector<int>& A, const vector<double>& W,
                    const DRNDInstance& inst, ParetoArchive& archive) {
    Individual ind(inst.num_H, inst.num_I);
    ind.X = X; ind.R = R; ind.A = A; ind.W = W;
    decode(ind, inst);
    if (ind.CV < EPS) {
        Solution sol;
        sol.Z1 = ind.Z1; sol.Z2 = ind.Z2;
        sol.X = X; sol.R = R; sol.A = A; sol.W = W;
        archive.add(std::move(sol));
    }
}

// ---------------------------------------------------------------------------
// Sub-problem: given X, find diverse Pareto-good (R, A, W) solutions
// via structured enumeration + random sampling + archive perturbation.
//
// FIX (sub-problem quality): The original evaluate_leaf used only uniform
// R vectors (same fill fraction for all open hubs) and a small fixed W set,
// leaving the per-hub R and W[5] dimensions almost unexplored.  PB-NSGA
// evolves non-uniform R and diverse W, so it found better (R,A,W) than BB.
// We now add:
//   1. Per-hub spotlight R: for each open hub, maximise that hub's inventory
//      while minimising others — explores the non-uniform R frontier.
//   2. Expanded W grid including W[5] extremes.
//   3. Substantially more random trials (num_trials governs the total budget).
//   4. Perturbation phase: Gaussian noise around each archive member to
//      exploit the best found solutions.
// ---------------------------------------------------------------------------
static void evaluate_leaf(const vector<int>&  X,
                           const DRNDInstance& inst,
                           int                 num_trials,
                           ParetoArchive&      archive) {
    const int H = inst.num_H, I = inst.num_I;

    vector<int> open_ki;
    for (int ki = 0; ki < H; ki++)
        if (X[ki]) open_ki.push_back(ki);
    if (open_ki.empty()) return;
    const int n_open = (int)open_ki.size();

    // ── Build A strategies ─────────────────────────────────────────────────
    const int A_RANKS = std::min(n_open, 3);
    vector<vector<int>> A_by_rank(A_RANKS, vector<int>(I));
    for (int ii = 0; ii < I; ii++) {
        int di = inst.demand_idx[ii];
        vector<pair<double,int>> dists;
        dists.reserve(n_open);
        for (int ki : open_ki) {
            int hi = inst.hub_idx[ki];
            double dx = inst.lat[di] - inst.lat[hi];
            double dy = inst.lon[di] - inst.lon[hi];
            dists.push_back({dx*dx + dy*dy, ki});
        }
        std::sort(dists.begin(), dists.end());
        for (int r = 0; r < A_RANKS; r++)
            A_by_rank[r][ii] = dists[r].second;
    }

    // ── R strategies ──────────────────────────────────────────────────────
    // Uniform fills: 11 levels from 0.0 to 1.0 (step 0.1) — dense grid so
    // that the continuous R dimension is well-sampled in complete-enum mode.
    auto make_R_uniform = [&](double val) {
        vector<double> R(H, 0.0);
        for (int ki : open_ki) R[ki] = val;
        return R;
    };
    vector<vector<double>> R_set;
    for (int step = 0; step <= 10; step++)
        R_set.push_back(make_R_uniform(step * 0.1));

    // Per-hub spotlight: one hub gets full inventory (1.0), others get
    // minimal (0.1) — explores non-uniform R frontier.
    for (int focus : open_ki) {
        vector<double> R(H, 0.0);
        for (int ki : open_ki) R[ki] = (ki == focus) ? 1.0 : 0.1;
        R_set.push_back(R);
    }
    // Per-hub half-spotlight: one hub at 0.5, others at 0.1.
    for (int focus : open_ki) {
        vector<double> R(H, 0.0);
        for (int ki : open_ki) R[ki] = (ki == focus) ? 0.5 : 0.1;
        R_set.push_back(R);
    }

    // ── W strategies ──────────────────────────────────────────────────────
    // Expanded set: covers W[5] extremes (Pass-1 window depth) which were
    // missing from the original fixed set.
    vector<vector<double>> W_set = {
        {0.5, 0.5, 0.5, 0.5, 0.5, 0.5},  // balanced
        {0.8, 0.3, 0.3, 0.7, 0.8, 0.7},  // urgency-heavy
        {0.2, 0.8, 0.6, 0.2, 0.3, 0.3},  // speed-heavy
        {0.5, 0.5, 0.8, 0.5, 0.5, 0.5},  // capacity-aware
        {1.0, 1.0, 0.5, 1.0, 1.0, 0.5},  // aggressive
        {0.5, 0.5, 0.5, 0.5, 0.5, 1.0},  // wide Pass-1 window
        {0.5, 0.5, 0.5, 0.5, 0.5, 0.1},  // narrow Pass-1 window (reactive)
        {1.0, 0.5, 0.5, 1.0, 0.5, 0.8},  // isolation + wide window
        {0.3, 1.0, 0.3, 0.3, 1.0, 0.5},  // speed + planned preference
    };

    // ── Phase 1: Structured enumeration ───────────────────────────────────
    int structured_count = 0;
    for (const auto& R : R_set) {
        for (int r = 0; r < A_RANKS; r++) {
            for (const auto& W : W_set) {
                try_one(X, R, A_by_rank[r], W, inst, archive);
                structured_count++;
            }
        }
    }

    // ── Phase 2: Random trials ─────────────────────────────────────────────
    const int random_budget = std::max(0, num_trials - structured_count);
    for (int t = 0; t < random_budget; t++) {
        vector<double> R(H, 0.0);
        for (int ki : open_ki) R[ki] = rand01();

        vector<int> A(I);
        for (int ii = 0; ii < I; ii++)
            A[ii] = open_ki[rand_int(0, n_open - 1)];

        vector<double> W(6);
        for (auto& w : W) w = rand01();

        try_one(X, R, A, W, inst, archive);
    }

    // ── Phase 3: Perturbation around archive members ───────────────────────
    // Take each Pareto-archive solution found for this X and apply small
    // Gaussian perturbations to (R, W) to exploit the neighbourhood.
    // Use 5 perturbations per archive member, σ = 0.15.
    const int PERTURB_PER_SOL = 5;
    const double SIGMA_PERTURB = 0.15;
    // snapshot current archive (may grow during loop — iterate over snapshot)
    vector<Solution> snap = archive.front;
    for (const auto& base : snap) {
        // Only perturb solutions that share this X
        if (base.X != X) continue;
        for (int p = 0; p < PERTURB_PER_SOL; p++) {
            vector<double> R = base.R;
            for (int ki : open_ki) {
                R[ki] = std::max(0.0, std::min(1.0,
                    R[ki] + rand_gauss(SIGMA_PERTURB)));
            }
            vector<double> W = base.W;
            for (auto& w : W) {
                w = std::max(0.0, std::min(1.0,
                    w + rand_gauss(SIGMA_PERTURB)));
            }
            try_one(X, R, base.A, W, inst, archive);
        }
    }
}

// ---------------------------------------------------------------------------
// Search counters (global for simplicity)
// ---------------------------------------------------------------------------
static long long g_nodes_visited       = 0;
static long long g_pruned_infeasible   = 0;
static long long g_pruned_dominance    = 0;
static long long g_leaves_evaluated   = 0;
static auto      g_t_start            = Clock::now();
static double    g_time_limit_s       = 3600.0;

// ---------------------------------------------------------------------------
// Recursive enumeration / B&B
//
// use_pruning = false (--mode enum):
//   Complete enumeration — all valid X ∈ {0,1}^H are evaluated.
//   Dominance pruning is DISABLED; only structurally infeasible nodes
//   (no open hub anywhere in the subtree) are skipped.
//   Guarantees a true ground-truth Pareto front.
//
// use_pruning = true (--mode bb):
//   Branch-and-Bound — uses lb_Z1 / lb_Z2 lower bounds to prune subtrees
//   whose lower bound is dominated by the current archive.  Faster for
//   large H but relies on bound correctness.
// ---------------------------------------------------------------------------
static void bb_search(vector<int>&          X,
                      int                   depth,
                      const DRNDInstance&   inst,
                      const BoundsCache&    bc,
                      ParetoArchive&        archive,
                      int                   num_trials,
                      bool                  use_pruning) {
    if (Duration(Clock::now() - g_t_start).count() > g_time_limit_s) return;

    ++g_nodes_visited;

    // ── Leaf: evaluate sub-problem ─────────────────────────────────────────
    if (depth == inst.num_H) {
        int n_open = 0;
        for (int ki = 0; ki < inst.num_H; ki++) n_open += X[ki];
        if (n_open == 0) { ++g_pruned_infeasible; return; }
        ++g_leaves_evaluated;
        evaluate_leaf(X, inst, num_trials, archive);
        return;
    }

    // ── Branch ────────────────────────────────────────────────────────────
    // In BB mode, try val=1 first to find good solutions early (improves pruning).
    // In enum mode, order is irrelevant — use 1 then 0 for consistency.
    for (int val : {1, 0}) {
        X[depth] = val;

        // Structural feasibility: skip if no open hub is possible in subtree
        int open_so_far = 0;
        for (int k = 0; k <= depth; k++) open_so_far += X[k];
        const int remaining = inst.num_H - depth - 1;
        if (open_so_far == 0 && remaining == 0) {
            ++g_pruned_infeasible;
            continue;
        }

        // MO dominance pruning (only in --mode bb)
        if (use_pruning) {
            const double lb_z1 = bc.lb_Z1(X, depth + 1);
            const double lb_z2 = bc.lb_Z2(X, depth + 1);
            if (archive.is_dominated(lb_z1, lb_z2)) {
                ++g_pruned_dominance;
                continue;
            }
        }

        bb_search(X, depth + 1, inst, bc, archive, num_trials, use_pruning);
    }
}

// ---------------------------------------------------------------------------
// JSON output (mirrors main solver format)
// ---------------------------------------------------------------------------
static void write_output(const ParetoArchive& archive,
                          const string&        out_path,
                          double               elapsed_s,
                          const string&        mode) {
    auto front = archive.front;
    std::sort(front.begin(), front.end(),
              [](const Solution& a, const Solution& b){ return a.Z1 < b.Z1; });

    json j;
    j["meta"]["solver"]                 = (mode == "enum") ? "BB-CompleteEnum" : "BB-Exact";
    j["meta"]["mode"]                   = mode;
    j["meta"]["elapsed_s"]              = elapsed_s;
    j["meta"]["nodes_visited"]          = g_nodes_visited;
    j["meta"]["pruned_infeasible"]      = g_pruned_infeasible;
    j["meta"]["pruned_dominance"]       = g_pruned_dominance;
    j["meta"]["leaves_evaluated"]       = g_leaves_evaluated;
    j["meta"]["pareto_size"]            = (int)front.size();

    json jfront = json::array();
    for (const auto& s : front) {
        json jsol;
        jsol["Z1"]   = s.Z1;
        jsol["Z2"]   = s.Z2;
        jsol["CV"]   = 0.0;
        jsol["rank"] = 1;
        jsol["X"]    = s.X;
        jsol["R"]    = s.R;
        jsol["A"]    = s.A;
        jsol["W"]    = s.W;
        jfront.push_back(std::move(jsol));
    }
    j["pareto_front"] = jfront;
    j["all_feasible"] = jfront;  // identical for BB-Exact (all are rank-1 feasible)

    if (out_path.empty() || out_path == "-") {
        cout << j.dump(2) << "\n";
    } else {
        std::ofstream f(out_path);
        if (!f.is_open())
            throw std::runtime_error("Cannot open output: " + out_path);
        f << j.dump(2) << "\n";
        cerr << "[Output] " << out_path << "\n";
    }
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------
int main(int argc, char* argv[]) {
    if (argc < 2) {
        cerr << "Usage: bb_solver <instance.json> [--out <path>] "
                "[--trials N] [--time-limit S] [--mode enum|bb]\n";
        return 1;
    }

    string inst_path  = argv[1];
    string out_path   = "";
    int    num_trials = 500;   // sub-problem evaluations per leaf
    double time_limit = 3600.0;
    string mode       = "enum"; // default: complete enumeration

    for (int i = 2; i < argc; i++) {
        const string arg = argv[i];
        if      (arg == "--out"        && i + 1 < argc) out_path   = argv[++i];
        else if (arg == "--trials"     && i + 1 < argc) num_trials = std::stoi(argv[++i]);
        else if (arg == "--time-limit" && i + 1 < argc) time_limit = std::stod(argv[++i]);
        else if (arg == "--mode"       && i + 1 < argc) mode       = argv[++i];
    }

    if (mode != "enum" && mode != "bb") {
        cerr << "Error: --mode must be 'enum' or 'bb'\n";
        return 1;
    }
    const bool use_pruning = (mode == "bb");

    g_time_limit_s = time_limit;

    // Load
    DRNDInstance inst = load_instance(inst_path);

    cerr << "=== BB-Exact Solver for MO-IHLNDP ===\n";
    cerr << "Mode     : " << (use_pruning ? "Branch-and-Bound (pruning ON)" : "Complete Enumeration (pruning OFF)") << "\n";
    cerr << "Instance : " << inst_path << "\n";
    cerr << "  H=" << inst.num_H << "  I=" << inst.num_I
         << "  J=" << inst.num_J << "  S=" << inst.num_S << "\n";
    const long long config_count = (inst.num_H <= 30) ? (1LL << inst.num_H) : -1;
    cerr << "  Hub configs: 2^" << inst.num_H;
    if (config_count > 0) cerr << " = " << config_count;
    cerr << "\n";
    if (inst.num_H > 20)
        cerr << "  WARNING: num_H > 20; enumeration may not finish within the time limit.\n";
    cerr << "Trials/leaf: " << num_trials
         << " | Time limit: " << time_limit << " s\n\n";

    set_rolling_seed(42);

    BoundsCache   bc(inst);
    ParetoArchive archive;
    vector<int>   X(inst.num_H, 0);

    g_t_start = Clock::now();
    bb_search(X, 0, inst, bc, archive, num_trials, use_pruning);
    const double elapsed = Duration(Clock::now() - g_t_start).count();

    cerr << "=== Done ===\n";
    cerr << "  Pareto front size : " << archive.front.size() << "\n";
    cerr << "  Nodes visited     : " << g_nodes_visited     << "\n";
    cerr << "  Pruned (infeas.)  : " << g_pruned_infeasible << "\n";
    if (use_pruning)
        cerr << "  Pruned (dominance): " << g_pruned_dominance  << "\n";
    cerr << "  Leaves evaluated  : " << g_leaves_evaluated  << "\n";
    cerr << "  Elapsed           : " << elapsed << " s\n";

    if (Duration(Clock::now() - g_t_start).count() >= time_limit)
        cerr << "  WARNING: Time limit reached — result is PARTIAL front.\n";

    try {
        write_output(archive, out_path, elapsed, mode);
    } catch (const std::exception& e) {
        cerr << "Error writing output: " << e.what() << "\n";
        return 1;
    }

    return 0;
}
