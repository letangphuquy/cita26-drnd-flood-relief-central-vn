# Academic Paper Writing Guidelines
## Humanitarian Logistics / Hub Location / Disaster Relief Network Design

*Synthesized from 7 reference papers in high-quality venues (EJOR, JOM, TRE, Omega, Applied Soft Computing, Safety Science, IEEE TSMC)*

---

## 1. Introduction Structure

### 1.1 Opening Hook and Motivation
- Open with a **real disaster statistic or event** to establish humanitarian urgency. Cite authoritative sources (UN OCHA, IFRC, EM-DAT).
- State the scale of the problem: number of people affected, economic losses, supply chain failures observed in real events.
- Transition from the general problem to the **specific gap** you are addressing.

### 1.2 Problem Statement
- Clearly distinguish your problem from prior work within 2-3 paragraphs.
- State the research question explicitly (e.g., "How should temporary medical centers be located under uncertainty of both demand and facility disruption?").
- Identify which real operational context motivates the model (earthquake, pandemic, flood, etc.).

### 1.3 Contributions
- Use a **numbered or bulleted list** of specific contributions — do NOT bury contributions in prose.
- Typical strong contribution patterns observed in the literature:
  1. A novel mathematical model combining two previously separate modeling streams
  2. A customized solution algorithm with proven advantages over benchmarks
  3. A real-world case study validating the model on field data
  4. Managerial insights or policy recommendations derived from computational analysis
- Ensure each contribution is falsifiable and verifiable — avoid vague language like "comprehensive framework."

### 1.4 Paper Organization
- Always end the introduction with a brief paragraph: "The remainder of this paper is organized as follows: Section 2 reviews the related literature... Section 3 presents the mathematical model... etc."

---

## 2. Literature Review Organization

### 2.1 Structure
- Organize by **research streams**, not chronologically. Common streams in this domain:
  - Facility location in humanitarian contexts
  - Uncertainty modeling approaches (stochastic, robust, chance-constrained)
  - Solution methodologies (exact, meta-heuristic, hybrid)
  - Real case studies / data sources
- Use a **comparison table** if reviewing more than 10 papers. Include columns for: objective(s), uncertainty type, solution method, case study.

### 2.2 Coverage Requirements (based on Donmez et al. 2021 taxonomy)
Ensure your review covers:
- **Facility types**: suppliers, distribution centers (DCs), points of distribution (PODs), shelters, field hospitals, blood centers
- **Uncertainty sources**: demand uncertainty (most common), supply uncertainty, network connectivity/disruption
- **Uncertainty paradigms**: Stochastic Programming (SP), Robust Optimization (RO), Chance-Constrained Programming (CCP)
- **Optimization criteria**: cost minimization, equity, reliability/coverage
- Cite the dominant paradigm from the review: as of 2021, SP covers ~60% of papers, RO ~24%, CCP ~14%

### 2.3 Identifying the Gap
- After each thematic subsection, write 1-2 sentences explicitly comparing your paper to that stream.
- The gap statement should reference **all** the limitations that your paper addresses.
- Avoid strawman gaps — do not claim "no prior work" when there is relevant work; instead show your specific combination is novel.

### 2.4 Closing the Literature Review
- End with a synthesis paragraph: "In summary, prior work has addressed X and Y, but no study has simultaneously considered A, B, and C under Z. This paper addresses this gap by..."
- Reference the review paper (Donmez et al. 2021, Omega) when surveying uncertainty frameworks — it covers 108 articles 2007-2019 with standardized taxonomy.

---

## 3. Problem Formulation Standards

### 3.1 Problem Description
- Before the mathematical model, write a **clear verbal description** of the problem: who are the decision makers, what decisions are being made, what constraints apply, what is being optimized.
- Include a **network diagram or figure** showing the multi-echelon structure (e.g., disaster sites → temporary medical centers → hospitals for casualty transportation networks).

### 3.2 Sets, Parameters, and Decision Variables
- Present in a structured table: Symbol | Definition | Unit/Domain
- Use consistent notation conventions:
  - Sets: uppercase italic (I, J, K, S)
  - Parameters: lowercase Greek or Roman
  - Binary decision variables: x, y, z (typically with subscripts)
  - Continuous decision variables: q, f, h (for flows, quantities)
- For uncertainty models, distinguish clearly between deterministic parameters, interval parameters [a, b], and stochastic parameters with distributions.

### 3.3 Objective Function Theory
- **Critical**: The choice of objective function has theoretical consequences. Following Holguin-Veras et al. (2013, JOM), the correct objective in post-disaster humanitarian logistics is:

  **Social Cost = Logistic Cost + Deprivation Cost**

  Mathematically: `SC = Ω_T(X,T) + Σ_ij Γ_ij(X,t_j) + Σ_i Γ_i(X,T)`

  Where:
  - `Ω_T(X,T)` = total logistic cost (transportation, inventory, facility)
  - `Γ_ij(X,t_j)` = deprivation cost accumulated up to delivery time t_j at node j
  - `Γ_i(X,T)` = terminal deprivation cost at end of planning horizon T

- **Properties of deprivation cost** (must acknowledge in the paper):
  - Monotonically non-decreasing in deprivation time
  - Non-linear (convex — accelerating suffering)
  - Non-additive across individuals (aggregation is complex)
  - Potentially **hysteretic**: even after receiving aid, survivors may not return to original utility level
  - Depends on: individual characteristics θ, deprivation duration δ_it, and supply level Z

- **Five objective function types** ranked by theoretical soundness (Holguin-Veras et al. 2013):
  1. **Social cost model** (best): explicitly includes deprivation cost function
  2. **Variable penalty model**: penalty proportional to time — acceptable if terminal costs included
  3. **Constant penalty model**: fixed penalty per unit unmet — misses inter-temporal effects
  4. **Hard constraints model**: enforces coverage constraints — cannot trade off equity vs. efficiency
  5. **Unmet demand minimization** (worst): ignores timing entirely, only counts quantity gaps

- If using a proxy objective (penalty, coverage), explicitly justify the choice and acknowledge the limitation.

### 3.4 Multi-Objective Formulation
- When using bi-objective or tri-objective models, clearly state:
  - Each objective's formula and units
  - The trade-off between objectives (why they conflict)
  - The solution approach (epsilon-constraint, weighted sum, Pareto)
- **Epsilon-constraint method**: convert secondary objectives to constraints with parameter ε; vary ε systematically to generate Pareto frontier. Note in the paper the number of Pareto solutions generated (e.g., "11 Pareto solutions generated by varying ε from ε_min to ε_max").

### 3.5 Constraints
- Number all constraints.
- Group constraints logically: (1) location/allocation logic, (2) flow balance, (3) capacity, (4) coverage/service, (5) robustness/feasibility, (6) integrality.
- After the model, write 2-4 sentences explaining each constraint group in plain language.

---

## 4. Algorithm Description Standards

### 4.1 Exact Methods
- **Lagrangian Relaxation** (pattern from Zhen et al. 2014):
  - Identify complicating constraints; relax them into the objective with multipliers λ.
  - Show the decomposed subproblems (e.g., 3 independent subproblems in Zhen et al.).
  - Describe the subgradient method for updating multipliers.
  - Report the Lagrangian gap (%) as evidence of solution quality (~2.7% in Zhen et al.).
  - Include iteration budget (e.g., "up to 200 iterations").

### 4.2 Meta-Heuristic Algorithms
- For any meta-heuristic, provide:
  1. **Flowchart or pseudocode** (mandatory)
  2. **Encoding scheme**: how solutions are represented (e.g., position vectors, permutation, binary string)
  3. **Initialization**: how the initial population/solution is generated
  4. **Move operators**: specific operators designed for this problem (e.g., Hamming Distance move in Li et al. 2023 for discrete hub assignment)
  5. **Parameter settings**: complete table of all tuned parameters and their values
  6. **Termination criterion**: iteration count, time limit, or convergence tolerance

- **Grey Wolf Optimizer (GWO)** customization pattern (Li et al. 2023):
  - Standard GWO uses continuous positions; for discrete hub selection, use a Construction Stage (CS) to generate initial feasible solutions followed by an Improvement Stage (IS) using Hamming Distance moves.
  - Report comparison with at least 2 alternative meta-heuristics (e.g., PSO, FA) on same instances.

- **NSGA-II hybrid** pattern (Hasani & Mokhtari 2019):
  - NSGA-II manages the Pareto frontier.
  - VNDS (Variable Neighborhood Descent/Search) performs local improvement within each generation.
  - Define k neighborhood structures (k = 10 in Hasani & Mokhtari).
  - Include convergence analysis showing fitness evolution over generations.

### 4.3 Performance Metrics for Multi-Objective Algorithms
Report at least two of:
- **Hypervolume (HV)**: area dominated by Pareto front relative to reference point; higher = better
- **Set Coverage (Setc)**: fraction of Algorithm B's solutions dominated by Algorithm A's solutions
- **Spacing Metric (SM)**: uniformity of solution distribution on Pareto front; lower = better (more uniform)
- **Number of Pareto solutions (NPS)**: count of non-dominated solutions found

---

## 5. Uncertainty Handling Methods

### 5.1 Choosing an Uncertainty Paradigm
Based on the Donmez et al. (2021) taxonomy:

| Paradigm | When to Use | Key Reference |
|---|---|---|
| Stochastic Programming (SP) | Probability distributions known or estimable | Birge & Louveaux |
| Robust Optimization (RO) | Only intervals/bounds known; distribution-free | Ben-Tal et al. 2009 |
| Chance-Constrained Programming (CCP) | Probabilistic service level guarantees needed | Charnes & Cooper |

- **Scenario-Based Robust Optimization** (Mulvey et al. 1995): Define s ∈ S scenarios; model both **solution robustness** (low variability in performance) and **model robustness** (feasibility across all scenarios). Use trade-off parameter ω to balance objective value vs. variance.
- **Interval Robust Optimization** (Ben-Tal et al. 2009): Represent uncertain parameters as intervals [a^-, a^+]; suitable for casualty numbers or demand when probability distribution is unknown.

### 5.2 Combining Multiple Uncertainty Sources
The NSRB model (Sun et al. 2022) provides a best-practice template for combining:
- **Demand uncertainty** (casualty numbers) → Interval robust optimization
- **Network disruption** (facility failures) → Scenario-based robust optimization with explicitly enumerated disruption scenarios

This combination avoids over-conservatism of purely robust approaches while capturing the combinatorial nature of facility disruptions.

### 5.3 Reporting Robustness Results
- Compare your robust model vs. a deterministic or less-robust baseline.
- Report variance reduction: "NSRB model reduces variance in deprivation cost by 65% compared to HRSB model."
- Report worst-case performance across all scenarios.
- Conduct sensitivity analysis on the robustness trade-off parameter.

---

## 6. Computational Experiment Standards

### 6.1 Instance Design
- Use **real geographic data** when possible (road network, population distribution, facility candidates).
- For datasets built from real events: cite the event (Wenchuan 2008, Tehran earthquake, Hubei COVID-19), the data source, and any preprocessing steps.
- Include multiple instance sizes: small (for exact method validation), medium (for algorithm comparison), large (for scalability demonstration).

### 6.2 Algorithm Benchmarking
- Compare against at least one exact method (for small instances) and 2+ heuristics (for large instances).
- Always report: objective value, computation time, optimality gap (or % difference from best known).
- Use ANOVA or statistical tests when comparing multiple algorithms on multiple instances.

### 6.3 Sensitivity Analysis
Standard sensitivity parameters for this domain:
- Coverage radius (for facility location models)
- Budget constraint level
- Penalty weight / robustness trade-off parameter
- Number of disruption scenarios
- Transportation mode costs and times

### 6.4 Reporting Tables
- One table per algorithm comparison.
- Include mean, standard deviation, and best values across multiple runs.
- Bold the best result in each row/column.
- Report exact solver (CPLEX, Gurobi, GLPK) version and hardware specifications.

---

## 7. Case Study Standards

### 7.1 Data Sourcing and Validation
- Clearly state the data source for each parameter type.
- If field data is unavailable, use **real-world proxies**: population census data, road network distances from GIS/Google Maps, hospital capacity from public health records.
- Besiou et al. (2018) categorize data quality: hypothetical (45%), real/archival (39%), field (11%). Aspire for real or field data; justify if using hypothetical.

### 7.2 Case Study Structure
Standard structure (observed across Papers 3, 4, 5, 6):
1. **Background**: geographic context, event description, scale of affected population
2. **Network setup**: number of nodes by type, candidate facility locations, transportation links
3. **Parameter values**: table of all input parameters with sources
4. **Results presentation**: best solution found, Pareto frontier plot (if multi-objective), facility location map
5. **Managerial insights**: what the results mean for practitioners — which facilities to open, how much inventory to pre-position, which routes to prioritize

### 7.3 Visualization
- Always include a **network/map figure** showing the optimal solution.
- For multi-objective results, plot the **Pareto frontier** with objectives on both axes.
- Label key points on the Pareto frontier (e.g., minimum cost solution, maximum equity solution, balanced solution).

---

## 8. Conclusions Structure

### 8.1 Summary (not repetition)
- Restate the research question and the key answer — do NOT simply repeat the abstract.
- Summarize what the results demonstrate, not what was done.

### 8.2 Managerial Implications
- Dedicate a paragraph to implications for humanitarian organizations, government agencies, or NGOs.
- Use concrete language: "Our model suggests pre-positioning X units at location Y reduces expected deprivation cost by Z%."

### 8.3 Limitations
- Acknowledge model assumptions explicitly: single disaster, single commodity, static demand, no dynamic routing.
- Acknowledge data limitations: proxy parameters, hypothetical scenarios.
- Do not bury limitations — reviewers will find them; address them proactively.

### 8.4 Future Research
- Provide 3-5 specific, actionable future directions:
  - Dynamic/multi-period extensions
  - Multi-hazard scenarios
  - Integration of real-time information (enabling technologies per EJOR roadmap)
  - Equity considerations / deprivation cost calibration from field data
  - Larger-scale instances or different geographic contexts

---

## 9. Cross-Cutting Quality Standards

### 9.1 Research Design (Besiou et al. 2018 EJOR Roadmap)
The six quality dimensions from the EJOR roadmap should be satisfied:
1. **Problem definition and research design**: problem-first (not model-first); grounded in real operational context
2. **Contextual factors**: acknowledge cultural, institutional, and geographic factors; avoid one-size-fits-all
3. **Acknowledging uncertainties**: explicitly list all uncertain parameters; justify modeling choices
4. **Appropriate methods**: match method to research question; triangulate across methods where possible
5. **Incorporating uncertainty in modeling**: use SP, RO, or CCP; justify paradigm choice
6. **Enabling technologies**: consider data availability, real-time information, practitioner interfaces

### 9.2 Notation Consistency
- Define every symbol before first use.
- Maintain a master notation table in the paper (often in an appendix).
- Use the same symbol for the same quantity throughout; never reuse a symbol for a different meaning.

### 9.3 Citation Practices
- When introducing deprivation cost: cite Holguin-Veras et al. (2013, JOM) as the foundational reference.
- When describing the uncertainty paradigm: cite Ben-Tal et al. (2009) for RO, Mulvey et al. (1995) for scenario-based robust, Charnes & Cooper for CCP.
- When situating your paper in the literature: cite Donmez et al. (2021, Omega) for the comprehensive review.
- Use the EJOR roadmap (Besiou et al. 2018) when justifying methodological choices.

### 9.4 Writing Style
- Use active voice for describing your contributions; passive voice is acceptable for established facts.
- Define all acronyms on first use: "humanitarian logistics (HL)", "temporary medical center (TMC)".
- Avoid overclaiming: "to the best of our knowledge" before novelty claims.
- Use the present tense for results that are always true; past tense for what you did in the study.
