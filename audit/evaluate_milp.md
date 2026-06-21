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

### D5 — Z2 Uses Fastest Mode (Air); Decoder Uses Road-First

**Paper (Equation for $\Omega_{is}$):**
$$\Omega_{is} = \sum_{k} z_{iks} \left( \tau_{ks} + 2 \cdot \min_{m \mid a_{ikms}=1} \tau_{kim} \right)$$
The paper uses $\min_m \tau_{kim}$ — the **fastest accessible mode** — for deprivation time calculation.

**MILP (line 142):**
```python
min_t = min(transport.time[m][k][i] for m accessible)
```
Correctly implements the paper's formula: uses the minimum travel time (always air, since helicopter is 3–7× faster than road).

**C++ decoder (`decoder.hpp`, CLAUDE.md §5):**
Road (0) → Water (1) → Air (2) priority. Air is last resort.

**Consequence:** The LP is **faithful to the paper's math**. The C++ decoder **deviates from the paper** by imposing an operational mode preference not in the formal model. This creates a model-algorithm gap:

- LP-optimal Z2 values assume air speed for all demand nodes → Z2 is systematically **underestimated** vs. what the decoder would achieve.
- All `lp_assignments` show mode=2 for nodes where air is fastest — this is correct per the paper's $\Omega$ formula, but contradicts the decoder's road-first policy.
- The Pareto front comparison in Table 1 (MILP vs. PB-NSGA) uses Z2 values computed under different mode assumptions. The MILP's Z2 is more optimistic.

**Severity:** High — affects the validity of quantitative comparison between MILP and PB-NSGA in the experiments. Should be noted as a limitation or the $\Omega$ formula should be aligned.

---

### D6 — Throughput Capacity Constraint Missing

**Paper (Constraint 9):**
$$q_k + \sum_{j} O_{js} z_{jks} + \sum_{h,m} f_{hkms} \le \kappa_k (x_k + y_{ks}) \quad \forall k, s$$
Total flow through hub $k$ (inventory + incoming supply + incoming transshipment) is bounded by hub capacity $\kappa_k$.

**MILP:** This constraint is absent. The only capacity bound is on pre-positioned inventory (Constraint 2: `q[ki] <= K_hub[ki] * x[ki]`). There is no per-hub bound on aggregate flow-through volume. Transshipment variables `f_khms` are bounded only by `tot_cap = sum(K_hub)` — the total capacity of all hubs combined (line 80).

**Severity:** Moderate. A hub could in principle route more supply through it than its physical capacity allows. For CV-Small (small instance, few scenarios), this is unlikely to bind. For large-scale instances it may lead to solutions that are infeasible under the paper's full constraint set.

---

## 3. Summary Table

| ID | Discrepancy | Direction | Severity |
|---|---|---|---|
| D1 | Demand equality → penalty slack `u_is` | Relaxation | Moderate |
| D2 | Origin equality → inequality (can leave unassigned) | Relaxation | Moderate |
| D3 | Force-safest hub active even if risk > χ | Extension | Minor |
| D4 | Air-mode quota (15%) — extra heuristic constraint | Tightening | Informational |
| D5 | Z2 uses min-time mode (air); decoder uses road-first | Model-algorithm gap | **High** |
| D6 | Throughput capacity (Constraint 9) missing | Omission | Moderate |

---

## 4. Recommended Actions

**D5 (high priority):** Add a note in the paper that MILP Z2 values represent a lower bound under the assumption that the fastest available mode is always used, while PB-NSGA Z2 values follow the road-first decoder policy. The comparison in Table 1 should acknowledge this mode-policy difference.

**D6 (medium priority):** Add the throughput capacity constraint to `build_and_solve_milp`. Without it, the MILP is solving a relaxation of the paper's model.

```python
# Constraint (9): total flow through hub <= hub capacity
solver.Add(
    q[ki] + sum_supply_items + sum_trans_in
    <= K_hub[ki] * (x[ki] + y[ki, si])
)
```

**D1/D2 (medium priority):** Document explicitly that the MILP treats infeasibility via big-M penalty (D1) and allows origin non-assignment (D2). These are standard solver-tractability choices but diverge from the paper's formal statement and should be mentioned in the experimental setup.

**D3/D4 (low priority):** These are implementation choices that prevent degenerate solutions and match the decoder's operational logic. Document as implementation notes rather than errors.
