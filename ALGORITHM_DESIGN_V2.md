# Algorithm Design V2 — PB-NSGA-II
## Key Changes from V1

---

## 1. Chromosome (unchanged structure, extended W)

```
C = [ X | R | A | W ]
     |H| |H| |I| |6|
```

| Seg | Type | Semantics |
|-----|------|-----------|
| X[k] | Binary | 1 = open planned hub k |
| R[k] | [0,1] | Inventory fill fraction: q_k = R_k × κ_k |
| A[i] | {0…\|H\|-1} | **Rotation offset** into distance-sorted hub list for demand i |
| W[0..5] | [0,1]^6 | Heuristic weights (see below) |

---

## 2. Weight Semantics (W expanded 3 → 6)

| # | Name | Used in | High value means |
|---|------|---------|-----------------|
| W[0] | Demand urgency | Step 3 demand sort | Prioritise high λ·D demands first |
| W[1] | Hub speed | Step 4 hub score | Prefer faster-to-reach hubs |
| W[2] | Hub capacity | Step 4 hub score | Prefer hubs with more residual inventory |
| W[3] | Demand isolation | Step 3 demand sort | Prioritise demands with fewer reachable hubs (most-constrained-first) |
| W[4] | Hub type bonus | Step 4 hub score | Prefer planned (type-1) hubs over reactive |
| W[5] | Reactive eagerness | Step 4 reactive check | Conservative (never open proactively); 0 = very aggressive |

---

## 3. Demand Priority Score (Step 3) — Normalised + Stochastic

All three raw components are normalised to [0,1] across the demand set before weighting:

$$\text{urgency}_i = \lambda_{is} \cdot D_{is}$$
$$\text{isolation}_i = \frac{1}{\left|\{k \in \mathcal{H}_{\text{act}} : \exists m,\ a_{ikms}=1\}\right|}$$
$$\text{dist}_i = \min_{k \in \mathcal{H}_{\text{act}},\ m:\ a_{ikms}=1} \tau_{ikm}$$

$$\text{Score}_i = W_0 \cdot \tilde{\text{urgency}}_i + W_3 \cdot \tilde{\text{isolation}}_i - W_1 \cdot \tilde{\text{dist}}_i + \varepsilon_i, \quad \varepsilon_i \sim \mathcal{N}(0,\ \sigma=0.05)$$

Sort demands **descending** by Score. Stochastic noise breaks ties differently each evaluation → counters phenotype collapse (Fix #1A).

---

## 4. Tiered Hub Selection (Step 4) — New A semantics

**Pre-computation (once, before scenario loop):**
For each demand $i$, sort hubs by Euclidean distance → `order[i][0...|H|-1]`.

**Rotation:** starting index = `A[i] % |H|`, wrap around.
```
candidate[j] = order[i][ (A[i] + j) % |H| ],  j = 0, 1, ..., |H|-1
```

**Hub selection score (Pass 1):**
$$\text{HubScore}(k) = W_1 \cdot \frac{1}{\tau_{ikm^*} + \varepsilon} + W_2 \cdot \text{residual}_k + W_4 \cdot \mathbf{1}[x_k = 1]$$

**Pass 1** — window of first K=3 candidates:
- Eligible: active, reachable, residual capacity > 0
- Pick: `argmax HubScore` within window

**Pass 2** — fallback over remaining candidates (j = K…|H|-1):
- Eligible: active, reachable (capacity ignored → may incur CV)
- Pick: first eligible hub

**W[5] proactive reactive check** (after Pass 1/2 finds `best_ki`):
$$\text{open reactive hub } k' \text{ if } \tau_{ik'} < (1 - W_5) \cdot \tau_{\text{best}}$$
Open the best (fastest) such safe inactive hub found. Adds $F^a_{k's}$ to $Z_1$.

**Forced reactive / infeasible** (no active hub reachable at all): existing logic unchanged.

---

## 5. Diversity Fixes

### Fix A — Stochastic Decoder
Gaussian noise $\mathcal{N}(0, 0.05)$ on normalised demand priority scores each evaluation. Same chromosome → different phenotypes across generations → sustained objective-space diversity.

### Fix D — Hamming Diversity Tiebreaker (Elitist Selection)
When the partial Pareto front must be trimmed, tiebreaker order is:
1. Pareto rank (lower = better)
2. Crowding distance (higher = better)
3. **Min Hamming distance to nearest neighbour in X space** (higher = better — prefer genotypically isolated individuals)

Computed once per generation over the combined 2N pool. Cost: O(N² |H|).

---

## 6. Genetic Operators — What Changed

| | V1 | V2 |
|--|----|----|
| W crossover | `for w in 0..2` | `for w in 0..W.size()-1` |
| W mutation | same | same |
| gene_count | `|H|+|H|+|I|+3` | `|H|+|H|+|I|+6` |
| LS A-perturbation | reassign A[i] to next-closest hub index | `A[i] = (A[i] ± 1) mod |H|` (±1 step in rotation space) |
