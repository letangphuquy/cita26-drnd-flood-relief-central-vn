# Technical Summary: PB-NSGA-II Algorithm
## MO-IHLNDP — Disaster Relief Hub Network Design

**Document type:** Internal reference — current algorithm as-implemented
**Date:** 2026-03-04
**Purpose:** Ground-truth baseline before designing algorithm changes

---

## 1. Problem Recap (What the Algorithm Solves)

The **Multi-Objective Incomplete Hub Location Network Design Problem (MO-IHLNDP)** is a two-stage stochastic combinatorial optimization problem. The goal is to decide, before a disaster strikes, which hubs to open and how much inventory to pre-position — then evaluate these decisions across multiple disaster scenarios.

### 1.1 Decision Variables

| Variable | Type | Stage | Meaning |
|---|---|---|---|
| $x_k$ | Binary | 1 (pre-disaster) | Open planned hub $k$ |
| $q_k$ | Continuous ≥ 0 | 1 (pre-disaster) | Pre-positioned inventory at hub $k$ (kg) |
| $y_{ks}$ | Binary | 2 (per-scenario) | Open reactive hub $k$ in scenario $s$ |
| $z_{iks}$ | Binary | 2 (per-scenario) | Assign demand $i$ to hub $k$ in scenario $s$ |
| $z_{jks}$ | Binary | 2 (per-scenario) | Assign origin $j$ to hub $k$ in scenario $s$ |
| $f_{khms}$ | Continuous ≥ 0 | 2 (per-scenario) | Trans-shipment flow from hub $k$ to hub $h$ via mode $m$ in scenario $s$ |

### 1.2 Two Objectives

**$Z_1$ — Expected Total Logistics Cost:**
$$Z_1 = \underbrace{\sum_k F_k x_k + \sum_k c_k q_k}_{\text{Stage 1: setup + holding}} + \sum_s \pi_s \left[ \underbrace{\sum_k F^a_{ks} y_{ks}}_{\text{reactive setup}} + \underbrace{\text{supply transport}}_{\text{origin→hub}} + \underbrace{\alpha \cdot \text{transshipment}}_{\text{hub↔hub}} + \underbrace{\Theta_{kis} z_{iks}}_{\text{Daganzo CA last-mile}} \right]$$

**$Z_2$ — Expected Maximum Deprivation Cost:**
$$Z_2 = \sum_s \pi_s \left( \max_{i \in \mathcal{I}} \left[ D_{is} \cdot \left(e^{\lambda_{is} \cdot \Omega_{is}} - 1\right) \right] \right)$$

where the waiting time $\Omega_{is} = \tau_{ks} + 2 \cdot \min_m \tau_{ikm}$ (hub processing time + round-trip travel time).

### 1.3 Key Structural Properties

- **Single-allocation**: each demand $i$ and each origin $j$ is assigned to exactly one hub per scenario.
- **Link accessibility**: $z_{iks} = 1$ only if $\exists m: a_{ikms} = 1$ (at least one traversable path exists in that scenario).
- **Hub safety**: a hub is eligible for activation only if its risk $r_{ks} \le \chi$ (safety threshold).
- **Flow conservation**: inventory at each hub must satisfy: pre-positioned stock + incoming supply + incoming transshipment ≥ outgoing demand-converted load + outgoing transshipment.
- **Non-anticipativity**: first-stage decisions ($x_k$, $q_k$) must be fixed before scenario realization — they cannot depend on which scenario occurs.

---

## 2. Chromosome Representation (Genotype)

### 2.1 Design Philosophy

The key insight driving the encoding: **only first-stage decisions need to be in the chromosome.** All second-stage variables ($y_{ks}$, $z_{iks}$, $z_{jks}$, $f_{khms}$) are deterministically reconstructed by a heuristic decoder for each scenario. This reduces search space from $O(|\mathcal{S}| \times |\mathcal{V}|^2)$ to $O(|\mathcal{H}|)$.

### 2.2 Current Chromosome Structure (As Implemented in Code)

The chromosome has **four segments** (note: the paper only describes three; the `A` segment is an implementation detail):

```
C = [ X | R | A | W ]
     |H| |H| |I| |3|
```

| Segment | Symbol | Type | Length | Domain | Meaning |
|---|---|---|---|---|---|
| Hub activation | **X** | Binary integer | $\|\mathcal{H}\|$ | $\{0,1\}$ | $X_k = 1$ iff hub $k$ is opened pre-disaster |
| Inventory ratio | **R** | Continuous | $\|\mathcal{H}\|$ | $[0,1]$ | $R_k$ encodes inventory as fraction of hub capacity: $q_k = R_k \cdot \kappa_k$ |
| Demand preference | **A** | Integer | $\|\mathcal{I}\|$ | $\{0,\ldots,\|\mathcal{H}\|-1\}$ | $A_i$ = preferred hub index for demand node $i$ (decoder tries this first) |
| Heuristic weights | **W** | Continuous | $3$ | $[0,1]^3$ | $(w_1, w_2, w_3)$ guide the decoder's priority scoring |

### 2.3 Inventory Encoding — Design History

The `R` segment went through two versions:

**Version 1 (original, in paper):**
$$q_k = R_k \cdot \frac{\hat{D}}{n_{\text{open}}}, \quad \hat{D} = \gamma \cdot \max_s \sum_i D_{is}$$
- $R_k$ encodes a share of total forecasted demand.
- Problem: $q_k$ is coupled to $X$ via $n_{\text{open}} = \sum_k X_k$. Reviewer flagged this as a design flaw — changing which hubs are open changes the meaning of $R_k$.

**Version 2 (current, in code — reviewer-corrected):**
$$q_k = R_k \cdot \kappa_k$$
- $R_k$ encodes the fill-fraction of hub $k$'s own physical capacity.
- Fully decoupled from $X$: the meaning of $R_k$ is independent of how many other hubs are open.
- $\kappa_k$ acts as the natural upper bound, so capacity constraint is structurally satisfied.

**Current code** (`decoder.hpp` Step 1):
```cpp
q[ki] = ind.R[ki] * inst.kappa[ki];
```

### 2.4 Weight Vector — Design History

**Original design** (from `algorithm-1st-thoughts.txt`): 4 weights $(w_1, w_2, w_3, w_4)$:
- $w_1$: demand urgency ($\lambda \cdot D$)
- $w_2$: risk index
- $w_3$: distance to nearest hub
- $w_4$: reactive hub activation threshold

**Current implementation** (`representation.hpp`): 3 weights $(w_1, w_2, w_3)$:
- $W[0]$: demand urgency weight in demand priority score
- $W[1]$: inverse-distance weight when scoring candidate hubs
- $W[2]$: residual capacity reward weight

$w_4$ (reactive hub threshold) was dropped; reactive hub activation is now triggered by feasibility need (capacity shortfall or unreachability), not by a weight.

### 2.5 The `A` Segment (Demand Preference)

The `A` segment is **not described in the paper** — it is a code-level optimization. For each demand node $i$, $A_i$ stores a preferred hub index. The decoder tries hub $A_i$ first during demand assignment, then falls back to other hubs ordered by increasing Euclidean distance from $i$.

This creates a richer search space beyond what the three $(X, R, W)$ segments alone could express: the allocation preference is co-evolved with hub strategy. It can be thought of as a warm-starting hint for the decoder.

---

## 3. Initialization

Random individual generation (`representation.hpp::random_individual()`):

```
X:  Randomly open n_open hubs, where n_open ~ Uniform(1, floor(|H| × 0.6))
    via Fisher-Yates shuffle of hub indices
R:  Each R_k ~ Uniform(0, 1) independently
A:  Each A_i ~ Uniform(0, |H|-1) randomly
W:  Each W_j ~ Uniform(0, 1) independently
```

Repair: at least one hub must be open in `X` (enforced after crossover and mutation too).

---

## 4. The Heuristic Decoder (7 Steps)

This is the most complex component — the function `decode(Individual&, DRNDInstance&)` in `decoder.hpp`. It is invoked once per individual per generation (for fitness evaluation) and once per offspring after operators.

The decoder runs the following steps **for each scenario** $s \in \mathcal{S}$:

### Step 1 — Decode Stage-1 Variables

```
For each hub k:
  x[k] = X[k]
  if x[k] == 1: q[k] = R[k] × κ[k]
  else:         q[k] = 0

Compute max_total_demand_kg = γ × max_s{ Σ_i D_{is} }   (for reactive inventory)

Add to Z1:
  Σ_k F_k × x[k]        (fixed hub costs)
  Σ_k c_k × q[k]        (inventory holding costs)
```

These costs are scenario-independent and computed once.

### Step 2 — Reactive Hub Activation ($y_{ks}$)

```
For each hub k:
  if x[k]==1 AND risk[k,s] ≤ χ:
    active[k] = true
    inventory[k] = q[k]

If no hub is active:
  Force-activate the hub with minimum risk (regardless of x[k])

# No explicit capacity-shortfall check here — reactive hubs are opened
# lazily in Step 4 only when a demand node cannot reach any active hub.
```

**Note:** The `y[k]` flags are only set to `true` when a hub is reactively opened during demand assignment (Step 4), not upfront. The `Z1` cost for reactive setup is added at that point.

### Step 3 — Priority Scoring for Demand Nodes

For each demand node $i$:
$$\text{Score}_i = W[0] \cdot \lambda_{is} \cdot D_{is} - W[1] \cdot \min_{k \in \text{active}} \tau_{ikm^*}$$

where $m^* = \arg\min_m \tau_{ikm}$ subject to $a_{ikms}=1$.

If no active hub is reachable from $i$ at this point, the distance term is set to 0 (handled in Step 4 reactively).

Demand nodes are **sorted descending** by Score — highest urgency / closest to hubs are assigned first.

### Step 4 — Demand Allocation ($z_{iks}$)

For each demand $i$ in priority order:

1. **Build candidate hub list**: `[A[i]] + [remaining hubs sorted by Euclidean distance to i]`
2. For each candidate hub $k$ (in that order):
   - Skip if not active
   - Check reachability: $\exists m: a_{ikms} = 1$
   - Compute hub score: $W[1] / (\tau_{ik} + \varepsilon) + W[2] \cdot \text{residual\_inventory}[k]$
   - Track the best-scoring reachable hub
3. If no active hub reaches $i$: try to open a new reactive hub:
   - Must be safe ($r_{ks} \le \chi$), must be reachable from $i$, must not already be open
   - Set $y[k]=\text{true}$, assign reactive inventory: $q_{\text{reactive}} = R_k \cdot \kappa_k$
   - Add reactive setup cost $F^a_{ks}$ to $Z_1$
4. If still no hub: infeasible — add BigM penalty to $Z_1$ and $Z_2$, increment CV by $\gamma D_{is}$
5. If assigned:
   - Record $z[i] = k$
   - Track hub load: `hub_load[k] += γ × D_{is}`
   - Add Daganzo CA cost $\Theta_{kis}$ to $Z_1$
   - Compute deprivation: $\Omega_{is} = \tau_{ks} + 2 \min_m \tau_{ikm}$; apply cap $\lambda \Omega \le 20$
   - Update $Z_2$: `Z2_s = max(Z2_s, D_is × expm1(λ × Ω))`

### Step 5 — Origin Assignment ($z_{jks}$)

For each origin $j$, assign to the active hub with the **largest deficit** (lowest net inventory) that is reachable via any mode. Add origin supply transport cost to $Z_1$.

```
net_inventory[k] = inventory[k] - hub_load[k]   (can be negative = deficit)

For each origin j:
  Find active hub k with min(net_inventory[k]) that is reachable from j
  Z1 += best_cost(j→k) × O_{js}
  net_inventory[k] += O_{js}
```

### Step 6 — Greedy Transshipment ($f_{khms}$)

Iteratively balance surplus→deficit until no improvement:

```
Repeat up to |H|×2 times:
  src = hub with max positive net_inventory
  dst = hub with max negative net_inventory
  if src or dst not found: break
  if no accessible arc (src→dst): break
  flow = min(surplus[src], deficit[dst])
  Z1 += α × cheapest_cost(src→dst) × flow
  update net_inventory[src] -= flow
  update net_inventory[dst] += flow

After loop:
  For each hub k: if net_inventory[k] < -ε: CV += |net_inventory[k]|
```

### Step 7 — Accumulate Expected Objectives

```
Z1 += π_s × Z1_s
Z2 += π_s × Z2_s
```

$Z2$ is the expected value of the scenario-wise maximum deprivation (not global maximum).

---

## 5. Genetic Operators

### 5.1 Selection

**Binary tournament**: randomly pick 2 individuals, keep the "constrained-better" one.

Constrained dominance order (Deb 2002):
1. Feasible (CV=0) always beats infeasible (CV>0)
2. Among infeasible: lower CV wins
3. Among feasible: lower Pareto rank wins; ties broken by crowding distance (higher is better)

### 5.2 Crossover (applied with probability $p_c = 0.90$)

| Segment | Operator | Details |
|---|---|---|
| **X** | Uniform Crossover | Each gene independently swapped with probability 0.5 |
| **R** | SBX (Simulated Binary Crossover) | $\eta_c = 20$; bounded to $[0,1]$ |
| **A** | Uniform Crossover | Each gene independently swapped with probability 0.5 |
| **W** | SBX | $\eta_c = 20$; bounded to $[0,1]$ |

After crossover: repair both children so at least one hub is open in `X`.

### 5.3 Mutation (applied with probability $p_m = 0.20 / \text{gene\_count}$ per gene)

where `gene_count = |H| + |H| + |I| + 3`.

| Segment | Operator | Details |
|---|---|---|
| **X** | Bit-flip | Flip $X_k$ from 0→1 or 1→0 |
| **R** | Polynomial Mutation | $\eta_m = 20$; bounded to $[0,1]$ |
| **A** | Random replacement | Replace $A_i$ with random hub index |
| **W** | Polynomial Mutation | $\eta_m = 20$; bounded to $[0,1]$ |

After mutation: repair `X` so at least one hub is open.

### 5.4 Survivor Selection (Elitist, each generation)

1. Combine parent population ($N$) + offspring ($N$) → combined pool of $2N$
2. Run fast non-dominated sort → Pareto fronts $F_1, F_2, \ldots$
3. Compute crowding distance within each front
4. Fill new population greedily: include entire fronts until the next front would overflow; then sort that front by crowding distance descending and take the top-$k$ needed

---

## 6. Main Loop (NSGA-II)

```
Initialize population P of size N
Decode all individuals in P
Elitist select P to size N

For gen = 1 to G:
  Create offspring Q of size N:
    While |Q| < N:
      p1 = tournament(P)
      p2 = tournament(P)
      if rand() < pc:
        (c1, c2) = crossover(p1, p2)
      else:
        (c1, c2) = (copy(p1), copy(p2))
      mutate(c1) with prob pm_base
      mutate(c2) with prob pm_base
      decode(c1); decode(c2)
      Q.append(c1, c2)

  P = elitist_select(P ∪ Q, N)

  If use_local_search:
    [See Section 7]

  Log every log_every generations
```

---

## 7. PB-NSMA Local Search Extension

When `--algo nsma` is used, after each generation's elitist selection:

```
ls_children = []
For each individual sol in P where sol.rank == 1:
  For t = 1 to ls_iters (default 5):
    nbr = copy(sol)
    if rand() < 0.5:
      # Perturbation type 1: flip a random hub bit
      k = random hub index
      nbr.X[k] ^= 1
      repair(nbr.X)   # ensure at least one hub open
    else:
      # Perturbation type 2: reassign A[i] for a random demand
      i = random demand index
      # Sort hubs by Euclidean distance from demand i
      # Assign nbr.A[i] to the next-closest hub (not the current preference)
    decode(nbr)
    if NOT sol.constrained_dominates(nbr):  # nbr is Pareto-improving
      ls_children.append(nbr)

If ls_children not empty:
  P = elitist_select(P ∪ ls_children, N)
```

**Acceptance criterion**: neighbour is accepted iff the original solution does NOT dominate it (i.e., the neighbour is at least as good on one objective). This is a Pareto-improvement condition — it accepts any non-dominated neighbour, which includes incomparable solutions and better solutions, but rejects dominated ones.

**Effect**: Local search concentrates effort on rank-1 solutions, helping refine the Pareto frontier without disrupting lower-ranked exploratory solutions.

---

## 8. Pareto Front Sorting

**Fast non-dominated sort** (Deb 2002): $O(N^2 \cdot M)$ where $M=2$ objectives.

1. For each pair $(i,j)$: check if $i$ constrained-dominates $j$; build dominance lists.
2. Extract front $F_1$ (those dominated by nobody), reduce domination counts, extract $F_2$, etc.
3. Assign integer ranks $1, 2, \ldots$ to each front.

**Crowding distance**: within each front, for each objective, sort by objective value and assign:
- Boundary solutions: $\infty$
- Interior solutions: $(f_{i+1} - f_{i-1}) / (\max f - \min f)$
- Total crowding = sum over both objectives.

Higher crowding distance = more isolated = preferred for diversity.

---

## 9. Constraint Violation (CV) Scoring

Two sources of CV:
1. **Demand infeasibility**: a demand node cannot be assigned to any hub (all hubs unreachable, or all safe hubs at capacity). CV += $\gamma \cdot D_{is}$ (kg equivalent of unserved demand).
2. **Inventory deficit**: after transshipment, some hub still has net negative inventory. CV += deficit (kg).

CV is accumulated across all scenarios (not per-scenario). The constrained-dominance principle ensures:
- Any solution with CV > 0 is always dominated by any solution with CV = 0.
- Among infeasible solutions: lower CV dominates higher CV.
- BigM penalties on $Z_1$, $Z_2$ additionally push infeasible solutions toward high objective values, ensuring the NSGA-II search steers away from infeasible regions even for the population diversity calculation.

---

## 10. Paper vs. Code Divergences

| Aspect | Paper Description | Actual Code | Impact |
|---|---|---|---|
| Chromosome segments | 3 segments: $(X, R, W)$ | 4 segments: $(X, R, A, W)$ | `A` segment improves decoder quality but is not described in paper |
| $R$ encoding | $q_k = R_k \cdot \hat{D}/n_{\text{open}}$ | $q_k = R_k \cdot \kappa_k$ | Code is reviewer-corrected; decoupled from $X$ |
| $W$ vector size | Not specified / "3 weights" in paper | $|W|=3$ | Match |
| Reactive hub activation | "if capacity insufficient, open hubs sorted by $w_4 \cdot r_{ks}$" | Opened lazily per demand when no active hub can reach it | Code is more reactive/conservative |
| Demand score formula | $\text{Score}_i = w_1(\lambda D) - w_2 \tau_{\min}$ | Same, using $W[0]$ and $W[1]$ | Match |
| Hub selection score | Not described in paper | $W[1]/(\tau+\varepsilon) + W[2] \cdot \text{residual}$ | Code has more elaborate hub scoring |
| Number of HV seeds | 3 seeds for CV-Small, 1 for benchmarks | Same | Inadequate per experiment strategy |
| Algorithm name | "PB-NSGA-II" for the main algorithm | `nsga2` mode = no LS, `nsma` mode = with LS | Naming inconsistency |

---

## 11. Known Weaknesses (From Reviewer Feedback)

### R1 — Baseline comparison missing
The paper reports HV for PB-NSGA-II only. Reviewer 2 explicitly requires comparison against a second algorithm (another metaheuristic such as MOEA/D, or an exact solver for small instances via $\epsilon$-constraint). Without a baseline, HV values are uninterpretable.

### R2 — Greedy decoder may cause false infeasibility
The greedy demand assignment can yield high CV not because the network is genuinely infeasible, but because the heuristic made a poor assignment early in the sequence (a capacity-hogging demand was greedily assigned to the only hub reachable by an isolated cluster). This creates high CV solutions that occupy infeasible regions unnecessarily, reducing effective population diversity.

### R3 — HV normalization
Current results table reports raw HV values (ranging $10^{12}$ to $10^{14}$) which are not comparable across instances. Reviewer 1 requires normalization by scaling objectives to $[0,1]$ before computing HV. The `analyze_results.py` already implements this but the paper's Table 2 uses raw values.

### R4 — Missing Pareto front plots
The paper has no Pareto front figures. Reviewer 1 explicitly requires them. `results/figures/` currently has no plots (generated but not referenced in the paper).

### R5 — CA assumption under local disruption
The Daganzo CA formula assumes a continuous, homogeneous local routing environment. Reviewer 2 points out that severe flooding disrupts micro-level road networks within a grid cell, making the CA assumption questionable for extreme scenarios. The paper does not address how $\Phi$ or $A_i$ are adjusted for disrupted cells.

### R6 — No linearization of $Z_2$
The paper claims $Z_2$ can be linearized for MILP via single-allocation property but does not provide the formulation. Without this, no lower bound or exact solver comparison is possible.

### R7 — Run count insufficient for statistical claims
Single-seed benchmark results cannot support claims about algorithm robustness or superiority. The experiment strategy calls for 20 seeds minimum.

---

## 12. Performance Snapshot (Current Results, Single Seeds)

From `results/summary.csv` (normalized HV, ref = (1.0, 1.0) in normalized space):

| Instance | Pareto Size | Normalized HV |
|---|---|---|
| AP10 | 100 | 0.5401 |
| AP20 | 100 | 0.0000 |
| AP25 | 100 | 1.0000 |
| AP40 | 100 | 0.0695 |
| AP50 | 100 | 0.1013 |
| AP100 | 25 | 0.4927 |
| TR81 | 2 | 0.0000 |
| CV-Small (3 seeds combined) | 152 | 0.9776 |
| CV-Large | 100 | 0.3407 |

**Notable observations:**
- AP20 and TR81 have HV = 0.000 in normalized space, meaning all Pareto solutions are co-linear or degenerate (no spread in objective space). This is suspicious and likely indicates a **decoder bug or a degenerate dataset transformation**.
- AP25 achieves perfect HV = 1.000, which means it dominates the reference front it is being measured against — expected since it defines that front with a single run.
- TR81's 2-point Pareto front is anomalously small for an 81-node network.
- The HV values are **not cross-instance comparable** in their current form — normalization is per-instance.

---

## 13. Complexity Analysis

**Decoder complexity per individual per generation:**
- Step 1: $O(|H|)$
- Step 2: $O(|H|)$
- Step 3: $O(|I| \cdot |H| \cdot |M|)$
- Step 4: $O(|I| \cdot |H| \cdot (|H| \log |H| + |M|))$
- Step 5: $O(|J| \cdot |H| \cdot |M|)$
- Step 6: $O(|H|^2 \cdot |M|)$ per transshipment iteration, $O(|H|)$ iterations → $O(|H|^3 \cdot |M|)$
- **Total per scenario**: $O(|H|^3 \cdot |M| + |I| \cdot |H|^2)$ (dominated by Step 4 for small $|H|$, Step 6 for large $|H|$)
- **Total per individual**: $O(|S| \cdot (|H|^3 \cdot |M| + |I| \cdot |H|^2))$

**Full algorithm per generation:**
- Crossover + mutation: $O(N \cdot |H|)$
- Decode offspring: $O(N \cdot |S| \cdot |H|^2 \cdot |I|)$ (dominant term for typical sizes)
- Non-dominated sort: $O(N^2)$ (usually not dominant for $N=100$, but grows with $N$)
- Local search (NSMA): $O(r_1 \cdot \text{ls\_iters} \cdot |S| \cdot |H|^2 \cdot |I|)$ where $r_1$ = rank-1 front size

For $N=100, G=200, |S|=3, |H|=20, |I|=100$: decode dominates, approximately $20^2 \times 100 \times 3 = 1.2M$ operations per generation, $\times 200 = 240M$ total. Consistent with observed ~60s runtimes.
