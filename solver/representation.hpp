// representation.hpp — 4-segment chromosome for PB-NSMA
// Chromosome = [X (binary hub) | R (inventory ratio) | A (demand hub
// preference) | W (heuristic weights)] Phenotype evaluation is delegated to
// decoder.hpp
#pragma once

#include "model.hpp"
#include "template.hpp"

// ---------------------------------------------------------------------------
// Flow Details (for detailed mapping/analysis)
// ---------------------------------------------------------------------------
struct TransshipmentFlow {
  int src_ki, dst_ki, m;
  double flow;
};
struct FlowDetails {
  vector<vector<int>> z_iks;                // [S][I] -> ki
  vector<vector<int>> z_iks_m;              // [S][I] -> m (mode)
  vector<vector<int>> z_jks;                // [S][J] -> ki
  vector<vector<int>> z_jks_m;              // [S][J] -> m (mode)
  vector<vector<TransshipmentFlow>> f_khms; // [S] -> list of transshipments
  vector<vector<bool>> y_ks;             // [S][H] -> true if reactive hub at ki
  vector<vector<double>> inventory_held; // [S][H] -> held inventory
};

// ---------------------------------------------------------------------------
// Individual (chromosome + phenotype + NSGA-II bookkeeping)
// ---------------------------------------------------------------------------
struct Individual {
  // ── Genotype (Stage-1 decisions + heuristic weights) ──────────────────
  vector<int> X; // [num_H] binary: x_k ∈ {0,1}
  vector<double>
      R; // [num_H] inventory ratio: R_k ∈ [0,1] → q_k = R_k * kappa_k
  vector<int>
      A; // [num_I] demand allocation preference: A_i ∈ {0..num_H-1}
         //   A_i = preferred hub index for demand node i.
         //   Decoder uses A_i as first candidate; if infeasible, falls
         //   back to remaining hubs ordered by increasing distance to i.
  vector<double>
      W; // [6]   heuristic weights w0..w5 ∈ [0,1]
         // W[0]: demand urgency weight (λ·D) in priority score
         // W[1]: hub speed weight (1/τ) in hub selection score
         // W[2]: residual capacity weight in hub selection score
         // W[3]: demand isolation weight (1/num_reachable) in priority score
         // W[4]: planned hub preference bonus in hub selection score
         // W[5]: reactive eagerness threshold (0=aggressive, 1=conservative)

  // ── Phenotype (computed by decoder) ──────────────────────────────────
  double Z1 = 0, Z2 = 0; // objective values (minimise both)
  double CV = 0;         // constraint violation ≥ 0

  // ── NSGA-II bookkeeping ────────────────────────────────────────────────
  int rank = 0;
  double crowding = 0.0;
  int hamming_diversity =
      0; // min Hamming distance to nearest neighbour in X space

  // ── Constructor ────────────────────────────────────────────────────────
  Individual() = default;
  explicit Individual(int num_H, int num_I)
      : X(num_H, 0), R(num_H, 0.0), A(num_I, 0), W(6, 0.5) {}

  // ── Dominance (standard Pareto, no CV) ────────────────────────────────
  bool dominates(const Individual &o) const {
    bool any_better = false;
    if (Z1 > o.Z1 || Z2 > o.Z2)
      return false;
    if (Z1 < o.Z1 || Z2 < o.Z2)
      any_better = true;
    return any_better;
  }
  // Constrained dominance (Deb 2002): feasible > infeasible, then by CV, then
  // by Pareto
  bool constrained_dominates(const Individual &o) const {
    bool f1 = (CV == 0), f2 = (o.CV == 0);
    if (f1 && !f2)
      return true;
    if (!f1 && f2)
      return false;
    if (!f1 && !f2)
      return CV < o.CV;
    return dominates(o);
  }

  // ── Utility ────────────────────────────────────────────────────────────
  vector<int> open_hubs() const {
    vector<int> res;
    for (int k = 0; k < (int)X.size(); k++)
      if (X[k])
        res.push_back(k);
    return res;
  }
  bool is_hub_open(int ki) const { return X[ki] == 1; }
};

// ---------------------------------------------------------------------------
// Random initialisation
// ---------------------------------------------------------------------------
Individual random_individual(const DRNDInstance &inst) {
  Individual ind(inst.num_H, inst.num_I);
  // X: randomly open some hubs (at least 1, at most 60%)
  int n_open = (int)rand_int(1, std::max(1, inst.num_H * 3 / 5));
  vector<int> perm(inst.num_H);
  std::iota(all(perm), 0);
  shuffle_vec(perm);
  for (int i = 0; i < n_open; i++)
    ind.X[perm[i]] = 1;
  // R: uniform [0,1] for each hub
  for (int k = 0; k < inst.num_H; k++)
    ind.R[k] = rand01();
  // A: random hub preference for each demand node
  for (int i = 0; i < inst.num_I; i++)
    ind.A[i] = (int)rand_int(0, inst.num_H - 1);
  // W: uniform [0,1]
  for (auto &wv : ind.W)
    wv = rand01();
  return ind;
}
