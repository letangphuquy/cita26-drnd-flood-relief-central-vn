// ccea.hpp — Co-evolutionary Algorithm with UCB1 W-bandit (ARCHIVED dead-end)
//
// Architecture:
//   Structure population (X, R, A): evolved via standard NSGA-II operators
//   W-pool (12 arms): UCB1 bandit selects one arm per offspring evaluation
//
// Each offspring receives a SINGLE W from the UCB1-selected arm, decoded once,
// and the arm's reward is updated from that result. No dual-eval, no archive,
// no final re-evaluation pass — each individual carries the Z1/Z2/CV from its
// last eval_with_ucb1 call. The final population is returned directly.
//
// Every 30 generations the arm with the lowest UCB score (excluding HoF) is
// replaced by a poly_mutate of the Hall-of-Fame arm's W — directed exploration.
//
// RESULT: HV = 0.049 ± 0.090 (20-seed, pop=200, gen=300) vs T19 baseline
// 0.403 ± 0.079. Root cause: W simultaneously drives Z1 (hub routing) and Z2
// (depriv scoring), so a global bandit cannot find a W coherent for both
// objectives across heterogeneous (X,R,A) structures. See audit/plan_improve_pbnsga.md
// §Post-T19 Structural Experiment for full post-mortem.
//
// Returns: final population (same format as run_nsga2).
#pragma once
#include "nsga2.hpp"

// ---------------------------------------------------------------------------
// W-arm: one candidate policy vector + UCB1 statistics
// ---------------------------------------------------------------------------
struct WArm {
    vector<double> W;
    double reward_sum = 0.0;
    int pulls = 0;

    double ucb(int total_pulls, double C = 0.5) const {
        if (pulls == 0) return 1e9;
        return reward_sum / pulls + C * std::sqrt(std::log((double)total_pulls) / pulls);
    }
    double mean_reward() const {
        return (pulls > 0) ? reward_sum / pulls : -1e9;
    }
};

// ---------------------------------------------------------------------------
// W-pool: 12-arm bandit
// ---------------------------------------------------------------------------
struct WPool {
    static constexpr int SIZE = 12;
    vector<WArm> arms;
    int hof_arm = 0;
    int total_pulls = 0;

    void init(int W_size = 7) {
        arms.resize(SIZE);
        // Seeded arms covering three qualitatively different policy regions
        arms[0].W = {0.5, 1.0, 0.0, 0.0, 0.0, 0.5, 0.0}; // speed-first
        arms[1].W = {0.5, 0.0, 1.0, 0.0, 0.0, 0.5, 0.0}; // capacity-first
        arms[2].W = {0.5, 0.8, 0.6, 0.0, 0.5, 0.5, 0.3}; // T19 region
        // Random arms
        for (int i = 3; i < SIZE; i++) {
            arms[i].W.resize(W_size);
            for (auto &w : arms[i].W) w = rand01();
        }
        hof_arm = 0;
    }

    // Force-explore unpulled arms first, then UCB1
    int select_ucb1(double C = 0.5) const {
        for (int i = 0; i < SIZE; i++)
            if (arms[i].pulls == 0) return i;
        int best = 0;
        double best_score = -1e18;
        for (int i = 0; i < SIZE; i++) {
            double s = arms[i].ucb(total_pulls, C);
            if (s > best_score) { best_score = s; best = i; }
        }
        return best;
    }

    void update(int arm_idx, double reward) {
        arms[arm_idx].reward_sum += reward;
        arms[arm_idx].pulls++;
        total_pulls++;
        for (int i = 0; i < SIZE; i++) {
            if (arms[i].pulls > 0 &&
                arms[i].mean_reward() > arms[hof_arm].mean_reward())
                hof_arm = i;
        }
    }

    // Replace the worst arm (lowest UCB, excluding HoF) with a mutation of HoF
    void refresh_worst() {
        if (total_pulls < SIZE) return;
        int worst = -1;
        double worst_score = 1e18;
        for (int i = 0; i < SIZE; i++) {
            if (i == hof_arm) continue;
            double s = arms[i].ucb(total_pulls, 0.5);
            if (worst < 0 || s < worst_score) { worst_score = s; worst = i; }
        }
        if (worst < 0) return;
        int W_size = (int)arms[hof_arm].W.size();
        arms[worst].W.resize(W_size);
        for (int w = 0; w < W_size; w++)
            arms[worst].W[w] = poly_mutate(arms[hof_arm].W[w], 8.0);
        arms[worst].reward_sum = 0.0;
        arms[worst].pulls = 0;
    }

    void log(int gen) const {
        cerr << "[CCEA gen=" << gen << "] HoF=arm" << hof_arm
             << " mean=" << std::fixed << std::setprecision(3)
             << arms[hof_arm].mean_reward()
             << " pulls=" << arms[hof_arm].pulls << "  top-3: ";
        vector<int> idx(SIZE);
        std::iota(idx.begin(), idx.end(), 0);
        std::sort(idx.begin(), idx.end(), [&](int a, int b) {
            return arms[a].mean_reward() > arms[b].mean_reward();
        });
        for (int t = 0; t < std::min(3, SIZE); t++) {
            int i = idx[t];
            cerr << "arm" << i << "(m=" << arms[i].mean_reward()
                 << " n=" << arms[i].pulls << ") ";
        }
        cerr << "\n";
    }
};

// ---------------------------------------------------------------------------
// Bandit reward — includes both Z1 and Z2 quality to avoid single-objective bias
// Thresholds derived from T19 solution range (Z1: 8-13M, Z2: 72K-95K)
// ---------------------------------------------------------------------------
static double ccea_reward(const Individual &ind) {
    if (ind.CV > 0) return -0.5;
    double r = 1.0;
    if (ind.Z2 < 90000.0)    r += 0.5;
    if (ind.Z2 < 75000.0)    r += 0.5;
    if (ind.Z1 < 14000000.0) r += 0.5;
    if (ind.Z1 < 11000000.0) r += 0.5;
    return r;
}

// ---------------------------------------------------------------------------
// run_ccea — main co-evolutionary loop
// ---------------------------------------------------------------------------
vector<Individual> run_ccea(const DRNDInstance &inst, const NSGAConfig &cfg) {
    set_rolling_seed(cfg.seed_iter);
    const int N = cfg.pop_size;
    const int W_SIZE = 7;

    WPool pool;
    pool.init(W_SIZE);

    // ── Tiered structure sampler (mirrors nsga2.hpp) ─────────────────────────
    int sample_tick = 0;
    auto sample_struct = [&]() {
        Individual ind(inst.num_H, inst.num_I);
        int max_open = std::max(1, inst.num_H * 3 / 5);
        int tier = sample_tick++ % 3;
        int lo = 1, hi = max_open;
        if (tier == 0) {
            hi = std::max(1, max_open / 3);
        } else if (tier == 1) {
            lo = std::max(1, max_open / 3);
            hi = std::max(lo, (2 * max_open) / 3);
        } else {
            lo = std::max(1, (2 * max_open) / 3);
            hi = max_open;
        }
        int n_open = (int)rand_int(lo, hi);

        vector<int> hubs(inst.num_H);
        std::iota(hubs.begin(), hubs.end(), 0);
        shuffle_vec(hubs);
        std::stable_sort(hubs.begin(), hubs.end(), [&](int a, int b) {
            return inst.F_hub[a] < inst.F_hub[b];
        });
        int pool_sz = (tier == 2) ? inst.num_H : std::max(n_open, inst.num_H / 2);
        pool_sz = std::clamp(pool_sz, n_open, inst.num_H);
        std::shuffle(hubs.begin(), hubs.begin() + pool_sz, rng);
        for (int i = 0; i < n_open; i++) ind.X[hubs[i]] = 1;

        for (int k = 0; k < inst.num_H; k++) {
            ind.R[k] = ind.X[k] ? std::clamp(0.45 + 0.5 * rand01(), 0.0, 1.0)
                                 : 0.25 * rand01();
        }
        vector<int> open;
        for (int k = 0; k < inst.num_H; k++) if (ind.X[k]) open.push_back(k);
        if (open.empty()) {
            int k = (int)rand_int(0, inst.num_H - 1);
            ind.X[k] = 1; open.push_back(k);
        }
        for (int ii = 0; ii < inst.num_I; ii++) {
            int chosen = open[0];
            double best_d = 1e100;
            int abs_i = inst.demand_idx[ii];
            for (int k : open) {
                int abs_h = inst.hub_idx[k];
                double dx = inst.lat[abs_i] - inst.lat[abs_h];
                double dy = inst.lon[abs_i] - inst.lon[abs_h];
                double d2 = dx * dx + dy * dy;
                if (d2 < best_d) { best_d = d2; chosen = k; }
            }
            if (rand01() < 0.20)
                chosen = open[(int)rand_int(0, (int)open.size() - 1)];
            ind.A[ii] = chosen;
        }
        for (auto &w : ind.W) w = rand01(); // W vestigial; overwritten at eval
        return ind;
    };

    // ── Single-arm evaluation via UCB1 ───────────────────────────────────────
    // One arm per offspring, selected by UCB1. Avoids cross-arm Z1/Z2 pollution
    // that occurs when dual eval mixes solutions from incompatible W policies.
    // The bandit still learns which W arms produce balanced (Z1, Z2, CV) outcomes
    // because the reward includes thresholds on both objectives.
    auto eval_with_ucb1 = [&](Individual &ind) {
        int arm_idx = pool.select_ucb1();
        ind.W = pool.arms[arm_idx].W;
        decode(ind, inst);
        pool.update(arm_idx, ccea_reward(ind));
    };

    // ── Initial population ────────────────────────────────────────────────────
    vector<Individual> pop;
    pop.reserve(N);
    cerr << "[PB-CCEA] Init pop N=" << N << " gen=" << cfg.num_gen
         << " pm=" << cfg.pm_high << "→" << cfg.pm_low
         << " W-arms=" << WPool::SIZE << "\n";

    while ((int)pop.size() < N) {
        Individual ind = sample_struct();
        eval_with_ucb1(ind);
        pop.push_back(ind);
    }
    elitist_select(pop, N, cfg);

    TimeVar t_start = time_now();
    string last_fp = rank1_fingerprint(pop);
    int stag_gens = 0;
    bool boosting = false;

    // ── Main loop ─────────────────────────────────────────────────────────────
    for (int gen = 1; gen <= cfg.num_gen; gen++) {
        double progress = (double)(gen - 1) / std::max(1, cfg.num_gen - 1);
        double cur_pm = cfg.pm_high - (cfg.pm_high - cfg.pm_low) * progress;

        string cur_fp = rank1_fingerprint(pop);
        if (cur_fp == last_fp) {
            ++stag_gens;
        } else {
            stag_gens = 0; last_fp = cur_fp; boosting = false;
        }
        int tourney = cfg.tournament_size;
        if (cfg.enable_stagnation_boost && stag_gens >= cfg.stagnation_threshold) {
            tourney = std::min(tourney + 1, 4);
            if (!boosting) {
                cerr << "[Gen " << gen << "] Stag boost tourney=" << tourney << "\n";
                boosting = true;
            }
        }

        vector<Individual> offspring;
        offspring.reserve(N);
        while ((int)offspring.size() < N) {
            const Individual &p1 = tournament(pop, tourney);
            const Individual &p2 = tournament(pop, tourney);
            Individual c1, c2;
            if (rand01() < cfg.pc) {
                auto [cx1, cx2] = crossover(p1, p2, cfg, inst);
                c1 = cx1; c2 = cx2;
            } else {
                c1 = p1; c2 = p2;
            }
            mutate(c1, cfg, inst, cur_pm);
            mutate(c2, cfg, inst, cur_pm);
            c1.age = 0; c2.age = 0;
            eval_with_ucb1(c1);
            eval_with_ucb1(c2);
            offspring.push_back(c1);
            if ((int)offspring.size() < N) offspring.push_back(c2);
        }

        for (auto &o : offspring) pop.push_back(o);
        elitist_select(pop, N, cfg);

        if (gen % 30 == 0) {
            pool.refresh_worst();
            pool.log(gen);
        }

        if (gen % cfg.log_every == 0 || gen == cfg.num_gen) {
            int r1_cnt = 0, feas = 0;
            double best_z1 = 1e18, best_z2 = 1e18;
            for (const auto &ind : pop) {
                if (ind.rank == 1) { r1_cnt++; umin(best_z1, ind.Z1); umin(best_z2, ind.Z2); }
                if (ind.CV == 0) feas++;
            }
            cerr << "[Gen " << std::setw(4) << gen << "] Pareto=" << r1_cnt
                 << " Feas=" << feas << "/" << N << " pm=" << std::fixed
                 << std::setprecision(3) << cur_pm << " stag=" << stag_gens
                 << " Z1=" << std::scientific << std::setprecision(3) << best_z1
                 << " Z2=" << best_z2 << " "
                 << std::fixed << std::setprecision(1)
                 << duration_ms(time_now() - t_start) / 1000.0 << "s\n";
        }
    }

    cerr << "[PB-CCEA] Done in " << std::fixed << std::setprecision(2)
         << duration_ms(time_now() - t_start) / 1000.0 << "s\n";
    pool.log(cfg.num_gen);

    // Each individual in pop already carries the Z1/Z2/CV from its last
    // eval_dual call, and ind.W is set to the arm that produced those values.
    // No re-evaluation needed: the final elitist_select has already ranked
    // these consistent per-individual results correctly.
    return pop;
}
