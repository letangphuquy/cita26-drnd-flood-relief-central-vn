# MILP-AWS Baseline — Conformance Audit Against Paper MO-IHLNDP

**Files audited:**
- Implementation: `src/solver/milp_aws_baseline.py`
- Reference: `paper/main.tex` §2 (Problem Description and Mathematical Model)
- Audit date: 2026-06-21

---

## 1. What Conforms

| Component | Paper reference | Implementation | Status |
|---|---|---|---|
| Z1 first-stage costs | $\sum_k F_k x_k + \sum_k c_k q_k$ | `z1_expr` line 148 | ✓ |
| Z1 reactive hub costs | $\pi_s F^a_{ks} y_{ks}$ | line 151 | ✓ |
| Z1 supply routing cost | $\pi_s c_{jks} O_{js} z_{jks}$, $c_{jks}=\min_m C_{jkm}$ | lines 152–157 | ✓ |
| Z1 transshipment | $\pi_s \alpha C_{khm} f_{khms}$ | lines 158–162 | ✓ |
| Z1 last-mile CA cost | $\pi_s \Theta_{kis} z_{iks}$ (precomputed theta) | lines 163–165 | ✓ |
| Z2 linearization | $W_s \ge C^{\text{dep}}_{iks} \cdot z_{iks}$ | lines 133–145 | ✓ |
| Z2 deprivation formula | $C^{\text{dep}}_{iks} = D_{is}(e^{\lambda_{is}(\tau_{ks}+2\min_m\tau_{kim})}-1)$ | line 144 | ✓ |
| Hub mutual exclusivity | $x_k + y_{ks} \le 1$ | line 68 | ✓ |
| Inventory capacity | $q_k \le \kappa_k x_k$ | line 50 | ✓ |
| Reactive hub safety | $r_{ks} y_{ks} \le \chi \Leftrightarrow y_{ks}=0$ if $r_{ks}>\chi$ | lines 70–72 | ✓ |
| Demand accessibility | $z_{iks} \le \sum_m a_{ikms}$ | lines 92–93 | ✓ |
| Origin accessibility | $z_{jks} \le \sum_m a_{jkms}$ | lines 105–106 | ✓ |
| Transshipment path | $f_{khms} \le M \cdot a_{khms}$ | line 82 | ✓ |
| Flow balance | Constraint (8) in paper | lines 121–123 | ✓ |

---

## 2. Discrepancies

### D1 — Demand Single-Allocation Relaxed to Soft Penalty

**Paper (Constraint 4):**
$$\sum_{k \in \mathcal{H}} z_{iks} = 1 \quad \forall i \in \mathcal{I}, s \in \mathcal{S}$$
Every demand node must be assigned to exactly one hub — a hard equality constraint.

**MILP (line 89):**
```python
solver.Add(sum(z_iks[ii, ki, si] for ki in range(num_H)) + u_is[ii, si] == 1)
```
A slack variable `u_is[ii, si] ≥ 0` absorbs unmet demand. When the LP cannot feasibly assign demand node `i`, `u_is > 0` and the LP remains feasible, reporting `CV > 0`.

**Cascading effect — Z1 gets an extra term (line 166):**
```python
z1_expr += pi * sum(u_is[ii, si] * big_M for ii in range(num_I))
```
A `big_M` penalty per unit of unmet demand is added to Z1. This term does not appear in the paper's Z1 formulation.

**Severity:** Moderate. Changes the problem from a hard-assignment MIP to a penalty-based relaxation. CV in reported solutions reflects residual slack, not hard constraint violation.

---

### D2 — Origin Assignment Changed from Equality to Inequality

**Paper (Constraint 4):**
$$\sum_{k \in \mathcal{H}} z_{jks} = 1 \quad \forall j \in \mathcal{J}, s \in \mathcal{S}$$
Every origin must supply exactly one hub per scenario.

**MILP (line 102):**
```python
solver.Add(sum(z_jks[ji, ki, si] for ki in range(num_H)) <= 1)
```
Origins can be left completely unassigned ($z_{jks}=0$ for all $k$). Supply at origin $j$ is silently unused if no hub is reachable or beneficial.

**Comment in code (line 101):**
> "Match decoder semantics: origins may remain unused if no beneficial/reachable assignment exists."

**Severity:** Moderate. Relaxes the model's supply utilisation assumption. In scenarios where all routes from an origin to active hubs are severed, this is operationally realistic — but it departs from the paper's mathematical statement.

---

### D3 — Force-Activate Safest Hub Not in Paper

**Paper:** Hub availability filter $v_{ks} = 1 \iff r_{ks} \le \chi$, strict. No exception.

**MILP (lines 60–65):**
```python
min_risk_s = min(risk[hub] for hub in all_hubs)
is_safe_or_best = (sc["risk"][k_node] <= chi or sc["risk"][k_node] <= min_risk_s + 1e-7)
if not is_safe_or_best:
    solver.Add(x_act[ki, si] == 0)
else:
    solver.Add(x_act[ki, si] <= x[ki])
```
The hub with the globally minimum risk is allowed to be active even when its risk exceeds $\chi$. This mirrors the C++ decoder's Step 1 fallback (Algorithm 1, line 1: "force-activate $\arg\min_k r_{ks}$"), but is **not in the paper's constraint set**.

**Severity:** Minor. Slightly expands the feasible region vs. the paper. Prevents the LP from becoming infeasible in scenarios where all planned hubs exceed $\chi$. Consistent with the decoder's operational logic.

---

### D4 — Air-Mode Quota: Extra Constraint Not in Paper

**Paper:** No constraint on transport mode shares.

**MILP (lines 127–131):**
```python
h_i = sum(z_iks[...] if exclusively_air_accessible)
h_j = sum(z_jks[...] if exclusively_air_accessible)
h_t = sum(w_trans[ki, hi, 2, si] ...)
solver.Add(h_i + h_j + h_t <= 0.15 * tot_l + 0.999)
```
Limits the fraction of *exclusively air-accessible* assignments (demand nodes and origins with no road/water alternative) and air-mode transshipments to at most ~15% of total links.

**Note:** This counts only pairs that are **exclusively** air-accessible (no road or water alternative). Demand nodes that have both road and air access are **not** counted against this quota, even if they are implicitly served by air in the LP's optimal solution (see D5 below).

**Severity:** Informational. Tightens the LP vs. the paper's model. Added heuristically to prevent degenerate all-air solutions on open-link arcs; does not fully enforce the mode preference in the paper's decoder.

---

### D5 — Z2 Mode-Time Formula: No Gap

**Paper (Equation for $\Omega_{is}$):**
$$\Omega_{is} = \sum_{k} z_{iks} \left( \tau_{ks} + 2 \cdot \min_{m \mid a_{ikms}=1} \tau_{kim} \right)$$
The paper uses $\min_m \tau_{kim}$ — the **fastest accessible mode** — for deprivation time calculation.

**MILP (`build_and_solve_milp`, Z2 bounds section):**
```python
min_t = _mode_time(sc, inst["transport"]["time"], k_node, i_node, num_M, False)  # utopian
```
Always uses the minimum travel time across all accessible modes. Faithful to the paper's formula.

**C++ decoder (`decoder.hpp` lines 383–391, confirmed by source inspection):**
```cpp
double min_t = inst.big_M;
for (int m = 0; m < num_M; m++)
    umin(min_t, inst.C_time[m][i][bk]);   // loops ALL modes, picks minimum
double omega = sc.hub_process_time[best_ki] + 2.0 * min_t;
```
The decoder also uses **utopian min-time** for Z2. Road→water→air priority (`best_mode_time`) applies only to logistics assignment (which mode carries goods), not to the deprivation calculation.

**Consequence:** There is **no model-algorithm gap on Z2**. Both the MILP and the PB-NSGA decoder compute Z2 with the same utopian $\min_m \tau_{kim}$ formula. The Z2 comparison in Table 1 is valid as-is.

**`lp_assignments` mode extraction** uses `lp_assignments_priority=True` (default), which applies the decoder's road→water→air priority for selecting the visualised logistics mode — matching `best_mode_time()` in the decoder. This does **not** affect Z2 values.

**Note on road-first in Z2 (attempted and reverted):** Applying road→water→air priority to Z2 c_dep causes the deprivation formula to saturate (hit the `exp(20)` cap for most demand nodes since road is 7–8× slower than air), producing Z2 ≈ 10¹² and making the MILP numerically infeasible. This confirms that the utopian formula is load-bearing for LP tractability, not merely a modelling simplification.

**Severity:** Not a discrepancy. No action required.

---

### D6 — Throughput Capacity Constraint Missing

**Paper (Constraint 9):**
$$q_k + \sum_{j} O_{js} z_{jks} + \sum_{h,m} f_{hkms} \le \kappa_k (x_k + y_{ks}) \quad \forall k, s$$
Total flow through hub $k$ (inventory + incoming supply + incoming transshipment) is bounded by hub capacity $\kappa_k$.

**MILP:** This constraint is absent. The only capacity bound is on pre-positioned inventory (Constraint 2: `q[ki] <= K_hub[ki] * x[ki]`). There is no per-hub bound on aggregate flow-through volume. Transshipment variables `f_khms` are bounded only by `tot_cap = sum(K_hub)` — the total capacity of all hubs combined (line 80).

**Severity:** Moderate. A hub could in principle route more supply through it than its physical capacity allows. For CV-Small (small instance, few scenarios), this is unlikely to bind. For large-scale instances it may lead to solutions that are infeasible under the paper's full constraint set.

---

### D7 — Supply Routing: Binary z_jks vs Decoder's Fractional MCF ← ROOT CAUSE OF Z1 GAP

**Paper (Constraint 5):**
$$\sum_{k \in \mathcal{H}} z_{jks} \le 1 \quad \forall j \in \mathcal{J}, s \in \mathcal{S}$$
The paper leaves the interpretation of $z_{jks}$ ambiguous — it is a binary allocation indicator, but the actual supply volume routed is not specified as proportional to the full origin supply.

**MILP (`milp_aws_baseline.py`, lines 205–209):**
```python
min_c = min(C_cost[m][j][k] for m accessible)
z1_expr += pi * min_c * float(sc["supply"][str(j_node)]) * z_jks[ji, ki, si]
```
When $z_{jks}=1$, the MILP pays `π_s × C_cost × O_{js}` — the **full origin supply** regardless of actual need.

**Decoder (`decoder.hpp`, lines 460–513):**
The decoder runs a **min-cost flow (MCF)** solver for supply routing:
```cpp
mcf_add_edge(g, SRC, origin_node(jj), O, 0.0);               // origin capacity = full supply
mcf_add_edge(g, origin_node(jj), hub_node(ki), O, o2h_cost); // arc per accessible hub
min_cost_flow(g, SRC, SNK, total_deficit);                    // push only as much as needed
Z1_s += e.cost * used;                                         // pays only for actual flow
```
The MCF pushes only `total_deficit` units from origins — exactly what the hubs need to cover the gap. It pays `C_cost × actual_flow`, not `C_cost × full_supply`.

**Consequence — quantified on CV-Small v2, Z1-min solutions:**

| Quantity | Value |
|---|---|
| Scenario 2 (π=0.1) net deficit | 392,813 units |
| Origin 25 full supply in sc2 | 869,636 units |
| C_cost[water][25→hub0] | 89.85 per unit |
| **MILP binary cost** (pays for full supply) | **7,813,453** |
| **Decoder MCF cost** (pays for deficit only) | **≈ 3,529,321** |
| Binary overpayment | **4,284,132** |

The MILP residual (supply + transshipment + reactive) = 7,813,453 ≈ exactly one binary z_jks assignment in sc2. In scenarios 0 and 1 the pre-positioned inventory covers all demand so no supply routing is triggered. In scenario 2 the deficit forces one binary origin assignment paying for 869k units when only 393k are needed.

**Full Z1 gap breakdown (MILP 11,077,463 vs NSGA 9,500,081, gap = 1,577,382):**

| Component | MILP | NSGA | MILP − NSGA |
|---|---|---|---|
| Fixed hub costs | 869,780 | 869,780 | 0 |
| Inventory holding | 203,825 | 268,147 | −64,322 |
| Last-mile theta | 2,190,405 | 3,345,898 | −1,155,493 |
| Supply + trans + reactive | 7,813,453 | 5,016,256 | +2,797,197 |
| **Total Z1** | **11,077,463** | **9,500,081** | **+1,577,382** |

The MILP is actually **better** on fixed, holding, and theta (achieves lower last-mile cost). The entire gap — and more — comes from the binary supply routing overpayment.

**Implication for Table 1 comparison:** The NSGA's lower Z1 is **not** evidence that PB-NSGA finds better hub/inventory decisions than the MILP. It reflects that the decoder evaluates supply routing with fractional MCF (pay for need) while the MILP formulation pays for full origin supply (binary). The Z1 comparison is **not apples-to-apples**.

**Severity:** High. Directly explains the Z1 performance gap. The MILP is more constrained (must pay for full supply in binary), making its Z1 values systematically higher than those evaluated by the decoder.

---

## 3. Summary Table

| ID | Discrepancy | Direction | Severity |
|---|---|---|---|
| D1 | Demand equality → penalty slack `u_is` | Relaxation | Moderate |
| D2 | Origin equality → inequality (can leave unassigned) | Relaxation | Moderate |
| D3 | Force-safest hub active even if risk > χ | Extension | Minor |
| D4 | Air-mode quota (15%) — extra heuristic constraint | Tightening | Informational |
| D5 | Z2 mode formula | Both use utopian min-time — no gap | None |
| D6 | Throughput capacity (Constraint 9) missing | Omission | Moderate |
| D7 | Supply routing binary (MILP) vs fractional MCF (decoder) | Formulation gap | **High** |

---

## 4. Recommended Actions

**D5:** No action needed. Both MILP and decoder use the same utopian min-time Z2 formula. The comparison in Table 1 is valid.

**D6 (medium priority):** Add the throughput capacity constraint to `build_and_solve_milp`. Without it, the MILP is solving a relaxation of the paper's model.

```python
# Constraint (9): total flow through hub <= hub capacity
solver.Add(
    q[ki] + sum_supply_items + sum_trans_in
    <= K_hub[ki] * (x[ki] + y[ki, si])
)
```

**D7 (high priority — affects paper claims):** The Z1 comparison in Table 1 should note that MILP and PB-NSGA evaluate supply routing costs differently. Options:

1. **Fix the MILP (recommended):** Replace binary `z_jks ∈ {0,1}` with a continuous variable `z_jks ∈ [0,1]` or a fractional flow variable, mirroring the decoder's MCF. Cost becomes `π × C_cost × O_j × z_jks` where `z_jks` is a fraction of supply routed. This makes MILP and decoder Z1-comparable. Requires adding: `z_jks[ji, ki, si] = solver.NumVar(0, 1, ...)` and changing the flow balance to use proportional supply (`z_jks × O_j` as fractional contribution).

2. **Re-evaluate NSGA with MILP Z1 formula (partial fix):** Re-score NSGA solutions by applying the binary supply routing cost to their (X, R, A) decisions. This shows what NSGA solutions would cost under the MILP's more conservative accounting.

3. **Document in paper (minimum fix):** Add a note to the experimental setup explaining that MILP pays for full origin supply when routing (binary z_jks), while the decoder routes fractional amounts via MCF. Report this as a comparison limitation.

**D1/D2 (medium priority):** Document explicitly that the MILP treats infeasibility via big-M penalty (D1) and allows origin non-assignment (D2). These are standard solver-tractability choices but diverge from the paper's formal statement and should be mentioned in the experimental setup.

**D3/D4 (low priority):** These are implementation choices that prevent degenerate solutions and match the decoder's operational logic. Document as implementation notes rather than errors.
