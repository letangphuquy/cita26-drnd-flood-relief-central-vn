# Quick Reference Card
## Writing Academic Papers in Humanitarian Logistics / Disaster Relief Network Design

*Distilled from 7 reference papers. Use this card when drafting or reviewing any section of a paper.*

---

## SECTION CHECKLIST

### Introduction
- [ ] Open with a real disaster statistic or event (cite EM-DAT, UN OCHA, IFRC)
- [ ] State the research question in one explicit sentence
- [ ] List contributions as a **numbered list** (not buried in prose)
- [ ] Each contribution must be falsifiable and verifiable
- [ ] End with "The remainder of this paper is organized as follows..."

### Literature Review
- [ ] Organize by **research streams**, not chronologically
- [ ] Include a **comparison table** for 10+ papers (columns: objective, uncertainty type, method, case study)
- [ ] Cover all three uncertainty paradigms: SP, RO, CCP (cite Donmez et al. 2021 for statistics)
- [ ] End with an explicit gap statement naming A, B, C limitations your paper addresses
- [ ] Avoid "no prior work exists" — instead show the specific combination is novel

### Mathematical Model
- [ ] Write a **verbal description** of the problem before the equations
- [ ] Include a **network diagram** showing the multi-echelon structure
- [ ] Present symbols in a table: Symbol | Definition | Unit/Domain
- [ ] Number all constraints
- [ ] Group constraints logically (location, flow balance, capacity, coverage, robustness, integrality)
- [ ] After the model, explain each constraint group in 2-4 plain sentences

### Algorithm
- [ ] Include **flowchart or pseudocode** (mandatory)
- [ ] Describe encoding scheme, initialization, move operators, parameter settings, termination
- [ ] Compare against at least **2 alternative algorithms**
- [ ] Report: objective value, computation time, optimality gap or % difference
- [ ] For multi-objective: report HV + Setc + SM (hypervolume, set coverage, spacing metric)

### Experiments
- [ ] Use real geographic data when possible; justify if hypothetical
- [ ] Include multiple instance sizes (small: exact validation; large: scalability)
- [ ] Perform sensitivity analysis on key managerial parameters
- [ ] Bold best result in each comparison table row/column
- [ ] Report solver name, version, hardware specs

### Conclusions
- [ ] Restate research question and key answer (not just repeat abstract)
- [ ] Dedicated paragraph on managerial implications with concrete numbers
- [ ] Explicitly list model limitations
- [ ] Provide 3-5 specific future research directions

---

## OBJECTIVE FUNCTION — MOST IMPORTANT RULES

### The Correct Objective (Holguin-Veras et al. 2013, JOM)
**Social Cost = Logistic Cost + Deprivation Cost**

```
SC = Ω_T(X,T) + Σ_ij Γ_ij(X,t_j) + Σ_i Γ_i(X,T)
```

The terminal cost term `Σ_i Γ_i(X,T)` is **critical** — omitting it causes inter-temporal externality errors.

### Deprivation Cost Properties (memorize these)
| Property | Meaning |
|---|---|
| Monotonic | Never decreases as deprivation time increases |
| Non-linear / convex | Suffering accelerates with time |
| Non-additive | Cannot simply sum across individuals |
| Potentially hysteretic | Suffering may persist even after aid is delivered |

### Five Objective Types Ranked (best to worst)
1. **Social cost** — logistic cost + deprivation cost (theoretically correct)
2. **Variable penalty** — penalty proportional to time (acceptable proxy if terminal cost included)
3. **Constant penalty** — fixed penalty per unmet unit (misses timing dynamics)
4. **Hard constraints** — service coverage constraints (cannot trade off equity vs. efficiency)
5. **Unmet demand minimization** — ignores timing entirely (worst)

**Rule**: If not using social cost model, explicitly state which proxy you use and justify. Cite Holguin-Veras et al. (2013) whenever mentioning deprivation cost.

---

## UNCERTAINTY PARADIGM SELECTION

| Paradigm | Use When | Key Citation |
|---|---|---|
| **Stochastic Programming (SP)** | Probability distributions known or estimable | Birge & Louveaux |
| **Robust Optimization (RO)** | Only intervals/bounds known; distribution-free | Ben-Tal et al. (2009) |
| **Chance-Constrained (CCP)** | Probabilistic service level guarantees needed | Charnes & Cooper |
| **Scenario-Based Robust** | Discrete disruption scenarios + variance control | Mulvey et al. (1995) |

**Statistics from 108-paper review (Donmez et al. 2021)**:
- SP: ~60% of papers; RO: ~24%; CCP: ~14%
- Trend: RO and CCP are increasing

**Combination pattern** (Sun et al. 2022, TRE):
- Uncertain demand numbers → Interval RO (Ben-Tal et al.)
- Facility disruptions → Scenario-based RO (Mulvey et al.)
- This combination avoids over-conservatism while handling combinatorial disruptions

---

## MULTI-OBJECTIVE OPTIMIZATION

### Epsilon-Constraint Method
- Fix secondary objective(s) as constraints: `F2 ≤ ε`
- Vary ε from `ε_min` to `ε_max` systematically
- Report the **number of Pareto solutions** generated (typically 10-20)
- Always plot the Pareto frontier with both objectives labeled on axes

### Performance Metrics (report at least 2)
| Metric | Symbol | Better When |
|---|---|---|
| Hypervolume | HV | Higher |
| Set Coverage | Setc | Higher |
| Spacing Metric | SM | Lower (more uniform) |
| Number of Pareto Solutions | NPS | Higher |

---

## UNCERTAINTY IN HUMANITARIAN CONTEXT

### Four Uncertainty Types (Besiou et al. 2018, EJOR)
1. **Demand for aid** — most common, modeled in 85/108 papers
2. **Supply quantity and availability** — modeled in 64/108 papers
3. **Infrastructure damage/network connectivity** — modeled in 33/108 papers
4. **Beneficiary behavior** — least modeled, important gap

### Six Methodological Quality Dimensions (Besiou et al. 2018)
1. Problem definition and research design (problem-first, not model-first)
2. Contextual factors (geographic, cultural, institutional)
3. Acknowledging uncertainties (list all uncertainties, even unmodeled ones)
4. Appropriate methods (match method to question; triangulate)
5. Incorporating uncertainty in modeling (use SP/RO/CCP; justify choice)
6. Enabling technologies (is the model implementable with available data?)

---

## COMMON MODEL STRUCTURES

### Three-Echelon Casualty Transportation Network (Sun et al. 2022)
```
Disaster Sites → Temporary Medical Centers (TMCs) → Hospitals
```
- TMCs: intermediate triage and treatment
- Triage: mild vs. serious casualties with different deprivation cost rates
- Decisions: open/close TMCs, assign casualties, allocate resources

### Hub-and-Spoke Relief Network (Li et al. 2023)
```
Supply Nodes → Hubs → Demand Nodes
```
- Multiple transportation modes: road, railway, air
- Hub selection is a binary decision
- Bi-objective: minimize time AND cost (competing objectives)

### Metropolis Network (Zhen et al. 2014)
```
Residential Areas → Emergency Shelters → Supply & Medical Centers
```
- Two facility types located simultaneously
- Coverage radius constraints
- Lagrangian relaxation for large-scale instances (500+ residential areas)

### Integrated Relief Network (Hasani & Mokhtari 2019)
```
Demand Points → Relief Centers → Higher-Level Centers
```
- Three objectives: coverage, cost, risk
- FTA for risk: failure events E1 (not located), E2 (out of range), E3 (disrupted)
- Inventory grouping for tractability

---

## ALGORITHM SELECTION GUIDE

| Problem Scale | Structure | Recommended Method |
|---|---|---|
| Small (<50 nodes) | Single objective | Exact: CPLEX/Gurobi |
| Medium (50-300 nodes) | Single objective | Lagrangian relaxation + subgradient |
| Large (300+ nodes) | Single objective | Meta-heuristic (GWO, PSO, GA) |
| Any scale | Bi-objective | ε-constraint (exact) or NSGA-II (heuristic) |
| Any scale | Tri-objective | NSGA-II + VNDS hybrid |

**Lagrangian Relaxation recipe** (Zhen et al. 2014):
1. Identify coupling constraints
2. Relax into objective with multipliers λ
3. Solve decomposed subproblems independently
4. Update λ via subgradient method (up to 200 iterations)
5. Report Lagrangian gap % (target: <5%)

**GWO customization for discrete problems** (Li et al. 2023):
1. Construction Stage: generate feasible initial solutions
2. Improvement Stage: Hamming Distance (HD) moves in discrete space
3. Compare against PSO and FA on same instances

---

## KEY CITATIONS TO ALWAYS INCLUDE

| Topic | Cite |
|---|---|
| Deprivation cost theory | Holguin-Veras et al. (2013), JOM |
| Social cost objective function | Holguin-Veras et al. (2013), JOM |
| HO research quality roadmap | Besiou et al. (2018), EJOR |
| Comprehensive uncertainty review | Donmez et al. (2021), Omega |
| Robust optimization (interval) | Ben-Tal et al. (2009) |
| Scenario-based robust optimization | Mulvey et al. (1995) |
| Two-stage stochastic programming | Birge & Louveaux |
| Chance-constrained programming | Charnes & Cooper |

---

## DATA QUALITY STANDARDS (Besiou et al. 2018)

| Data Type | Share in HO Literature | Quality Level |
|---|---|---|
| Hypothetical/simulated | 45% | Lowest |
| Real/archival data | 39% | Medium |
| Field data | 11% | Highest |

**Target**: Use real or field data. If hypothetical, justify explicitly and acknowledge as a limitation.

**Common real data sources for this domain**:
- Population: national census, WorldPop
- Road networks: OpenStreetMap, Google Maps Distance Matrix API
- Disaster events: EM-DAT (Centre for Research on Epidemiology of Disasters)
- Earthquake data: USGS Earthquake Catalog
- Hospital/facility capacity: Ministry of Health records, WHO Global Health Observatory

---

## FACILITY TYPE COVERAGE (Donmez et al. 2021 taxonomy)

Confirm your literature review mentions at least the relevant facility types:
- [ ] Suppliers (upstream procurement)
- [ ] Distribution Centers (DCs) — most studied in literature
- [ ] Points of Distribution (PODs) — last-mile delivery
- [ ] Shelters — pre-disaster evacuation
- [ ] Field hospitals — medical response
- [ ] Blood centers — specialized perishable inventory

---

## WRITING STYLE RULES

- Use **active voice** for your contributions ("We propose... We show...")
- Use **passive voice** for established facts ("It has been shown that...")
- Always write "to the best of our knowledge" before novelty claims
- Define every acronym on first use: humanitarian logistics (HL), temporary medical center (TMC)
- Name your model with an acronym: e.g., NSRB, HTNSGAII-VNDS, MINLP
- Use **present tense** for results that are always true; **past tense** for what was done in the study
- Avoid: "comprehensive", "novel framework" (overused), "it is worth noting that"
- Prefer: "specifically", "in contrast to", "this paper extends"

---

## CASE STUDY MINIMUM REQUIREMENTS

Every case study section must include:
1. **Background**: geographic context, event, scale of affected population
2. **Network setup table**: counts by node type (supply nodes, candidate facilities, demand nodes)
3. **Parameter table**: all input values with sources
4. **Solution figure**: map or network diagram showing optimal facility locations
5. **Pareto frontier plot** (if multi-objective): both objectives labeled, key solutions annotated
6. **Managerial insights paragraph**: what the results mean for practitioners

---

## SENSITIVITY ANALYSIS PARAMETERS (standard set)

Always test sensitivity to:
- [ ] Coverage/service radius (policy lever)
- [ ] Budget or capacity limit (resource constraint)
- [ ] Penalty weight / robustness trade-off parameter ω
- [ ] Number of disruption scenarios
- [ ] Transportation cost and time parameters
- [ ] Demand uncertainty level (interval width or variance)
