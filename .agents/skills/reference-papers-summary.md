# Reference Papers Summary
## Seven Key Papers in Humanitarian Logistics / Disaster Relief Network Design

*Detailed per-paper summaries including key contributions, methodology, structure, and writing lessons.*

---

## Paper 1: A Roadmap for Higher Research Quality in Humanitarian Operations

**Citation**: Besiou, M., Stapleton, O., & Van Wassenhove, L. N. (2018). A roadmap for higher research quality in humanitarian operations: A methodological perspective. *European Journal of Operational Research*, 276(2), 731–744.

**Venue**: European Journal of Operational Research (EJOR) — top-tier OR journal

### Key Contribution
Provides a prescriptive methodological framework for humanitarian operations (HO) research, diagnosing systemic quality problems in the field and offering a "roadmap" for improvement. The paper identifies six quality dimensions and two research approach types, and advocates for a closed-loop research paradigm integrating field work with modeling.

### Methodology
- **Type**: Methodological / review / prescriptive framework paper (not a modeling paper)
- **Approach**: Analyzes a sample of HO papers across quality dimensions; proposes structured checklist
- **Data analysis**: Documents that 45% of HO papers use hypothetical data, 39% use real data, only 11% use field data — this empirical finding is used to motivate higher standards

### Six Methodological Quality Dimensions
1. **Problem definition and research design**: Is the research problem grounded in real humanitarian operations, or is it a mathematical exercise? Advocates problem-first approach (start from field observations) over model-first approach (start from mathematical interest).
2. **Contextual factors**: Do models account for geographic, cultural, institutional, and political factors? A model calibrated for earthquake response in Japan may not transfer to Pakistan.
3. **Acknowledging uncertainties**: Are all sources of uncertainty identified and acknowledged, even if not all are modeled? Four primary uncertainty types: (a) demand for aid, (b) supply quantity and availability, (c) infrastructure damage, (d) beneficiary behavior.
4. **Appropriate methods**: Is the method chosen because it is best suited to the research question, or because the author is familiar with it? Advocates triangulation across multiple methods.
5. **Incorporating uncertainty in modeling**: Once uncertainties are identified, are they properly incorporated using SP, RO, simulation, etc.? Identifies the tendency to use deterministic models as a gap.
6. **Enabling technologies**: Are models designed to be implementable with available data and technology? Do they interface with practitioner decision-support tools?

### Structure
1. Introduction — motivation for quality improvement
2. Background — two research approaches (model-first vs. problem-first)
3. Six methodological dimensions (one section each)
4. Closed-loop research diagram
5. Discussion and roadmap recommendations
6. Conclusion

### Writing Lessons
- **Use a conceptual framework figure**: The closed-loop diagram is the most memorable element of the paper — visual frameworks anchor theoretical contributions.
- **Ground prescriptions in empirical evidence**: The 45%/39%/11% data distribution finding makes the quality critique credible and specific.
- **Critique the field constructively**: The paper identifies weaknesses without naming/shaming individual papers — it aggregates statistics to describe systemic patterns.
- **Provide an actionable checklist**: Each of the six dimensions can function as a checklist item for authors and reviewers — practical tools increase citation and adoption.
- **Position against existing debates**: The model-first vs. problem-first framing directly positions the paper within ongoing methodological debates in OR/MS.

---

## Paper 2: On the Appropriate Objective Function for Post-Disaster Humanitarian Logistics Models

**Citation**: Holguin-Veras, J., Jaller, M., Van Wassenhove, L. N., Perez, N., & Wachtendorf, T. (2013). On the appropriate objective function for post-disaster humanitarian logistics models. *Journal of Operations Management*, 31(5), 262–280.

**Venue**: Journal of Operations Management (JOM) — top-tier OM journal (ABS 4*)

### Key Contribution
Establishes the theoretical foundation for objective function selection in post-disaster humanitarian logistics (PD-HL). Introduces "deprivation cost" as the economic valuation of human suffering from lack of access to critical goods. Proves that the social cost model (logistic cost + deprivation cost) is the only theoretically correct objective, and ranks five alternative proxy objective functions by soundness.

### Mathematical Framework
**Social Cost Function**:
```
SC = Ω_T(X,T) + Σ_ij Γ_ij(X,t_j) + Σ_i Γ_i(X,T)
```
- `Ω_T(X,T)`: total logistic cost (transportation, facility, inventory)
- `Γ_ij(X,t_j)`: deprivation cost accumulated at destination j from origin i up to delivery time t_j
- `Γ_i(X,T)`: terminal deprivation cost at end of planning horizon T (crucial for inter-temporal effects)

**Deprivation cost** γ(θ, δ_it, Z): a function of individual characteristics θ (e.g., age, health status), duration of deprivation δ_it, and supply level Z. Properties:
- Monotonically non-decreasing in δ_it
- Non-linear and convex (suffering accelerates with time)
- Non-additive across individuals
- Potentially **hysteretic**: history-dependent, suffering may persist even after relief is delivered

**Five Model Types Ranked**:
1. Social cost model (theoretically correct)
2. Variable penalty model (best proxy: penalty ∝ time, must include terminal cost)
3. Constant penalty model (misses timing dynamics)
4. Hard constraint model (service coverage constraints — cannot optimize equity-efficiency trade-off)
5. Unmet demand minimization (ignores timing entirely — worst)

### Methodology
- Analytical/theoretical framework
- Illustrative examples showing how different objectives lead to different — and sometimes perverse — decisions
- Review of prior PD-HL literature to categorize existing objective functions into the five types
- Economic analysis of material convergence (unsolicited donations) as a manifestation of externalities from wrong objective functions

### Writing Lessons
- **Theoretical papers need clear stakes**: The paper opens with real examples of deaths caused by suboptimal logistics decisions, establishing that the objective function choice has life-or-death consequences — not just academic interest.
- **Rank alternatives explicitly**: Providing a clear ranking (best to worst) of five objective types is more useful than simply advocating for one; it helps readers who cannot implement the ideal.
- **Use mathematical properties as a proof structure**: Demonstrating that deprivation cost is convex, monotonic, and hysteretic proves why proxy models fail — this is rigorous and reviewers cannot argue with mathematical properties.
- **Connect to real phenomena**: Material convergence (the problem of unsolicited aid flooding disaster sites) is explained as a predictable consequence of using the wrong objective — this practical grounding validates the theory.
- **Acknowledge calibration challenges**: The paper honestly notes that deprivation cost functions are difficult to calibrate empirically — this honesty enhances credibility rather than undermining the contribution.

---

## Paper 3: Design of Multimodal Hub-and-Spoke Transportation Network for Emergency Relief Under COVID-19 Pandemic

**Citation**: Li, Y., Tao, G., Fan, H., Moshood, T. G., & Ndzibah, E. (2023). Design of multimodal hub-and-spoke transportation network for emergency relief under COVID-19 pandemic: A meta-heuristic approach. *Applied Soft Computing*, 133, 109925.

**Venue**: Applied Soft Computing — Elsevier, CiteScore ~14

### Key Contribution
Formulates the emergency relief network design problem as a bi-objective MINLP with a multimodal hub-and-spoke structure and proposes a customized Grey Wolf Optimizer (GWO) with Hamming Distance move strategy. Validates on a real Hubei Province COVID-19 case.

### Mathematical Model
- **Network structure**: Supply nodes → Hubs → Demand nodes
- **Transportation modes**: Road (mode 1), Railway (mode 2), Air (mode 3)
- **Objective 1**: Minimize total transportation time = pickup time + transshipment time at hub + delivery time
- **Objective 2**: Minimize total transportation cost
- **Decision variables**: Hub selection (binary), mode assignment (binary), flow allocation (continuous)
- Model type: Bi-objective Mixed Integer Non-Linear Programming (MINLP)

### Algorithm: Customized GWO
- **Encoding**: Position vectors represent hub assignments and mode selections
- **Construction Stage**: Generates initial feasible solutions respecting hub-and-spoke topology
- **Improvement Stage**: Applies Hamming Distance (HD) moves to explore neighborhood in discrete space
- **Multi-objective handling**: Uses ε-constraint or weighted sum approach within GWO framework
- **Comparison**: GWO vs. Firefly Algorithm (FA) vs. Particle Swarm Optimization (PSO)
- **Result**: GWO consistently finds better Pareto solutions with lower cost and time

### Case Study: Hubei Province, China
- 5 supply nodes, 3 candidate hub locations, 5 demand nodes
- COVID-19 medical supplies: masks, ventilators, protective equipment
- Best solution: 16,049,594.34 CNY total cost, 336.53 hours total time
- Two hubs selected out of 3 candidates

### Structure
1. Introduction (COVID-19 motivation + research gap + contributions)
2. Literature Review (hub-and-spoke, multimodal, emergency logistics)
3. Problem Description and Mathematical Model
4. GWO Algorithm Description (with flowchart)
5. Computational Experiments (parameter tuning + Hubei case)
6. Conclusions and Future Work

### Writing Lessons
- **Leverage current events**: Framing as a COVID-19 paper significantly increases readership and reviewer interest. Connecting the model to a real ongoing crisis motivates the work without being opportunistic if the model genuinely addresses COVID-specific constraints.
- **Show algorithm flowchart**: The GWO flowchart is essential — it lets readers and reviewers verify the algorithm without reading the pseudocode line by line.
- **Parameter sensitivity within algorithm tuning**: Showing how GWO parameters (α decay rate, population size) affect solution quality demonstrates algorithmic understanding.
- **Three-way algorithm comparison**: Comparing against two alternatives (not just one) significantly strengthens the contribution claim for the algorithm.
- **Report both objectives in case study**: Always show the trade-off table, not just the "best" solution — this demonstrates Pareto awareness.

---

## Paper 4: A Novel Scenario-Based Robust Bi-Objective Optimization Model for Humanitarian Logistics Network Under Risk of Disruptions

**Citation**: Sun, H., Zheng, Z., Han, F., Li, M., & Gu, W. (2022). A novel scenario-based robust bi-objective optimization model for humanitarian logistics network under risk of disruptions. *Transportation Research Part E: Logistics and Transportation Review*, 157, 102578.

**Venue**: Transportation Research Part E (TRE) — top-tier logistics/transportation journal (ABS 3)

### Key Contribution
Proposes the Novel Scenario-Based Robust Bi-objective (NSRB) model integrating four decisions simultaneously: facility location, casualty transportation, relief commodity allocation, and triage classification. Combines interval robust optimization (for demand uncertainty) with scenario-based robust optimization (for facility disruption). Demonstrates 65% variance reduction in deprivation cost vs. baseline model.

### Mathematical Model
**Three-echelon network**: Disaster sites (I) → Temporary Medical Centers (J) → Hospitals (H)

**Triage**: Two casualty types:
- **Mild casualties**: lower deprivation cost rate, can wait longer
- **Serious casualties**: higher deprivation cost rate, require immediate attention

**Objective 1 (F1)**: Minimize total deprivation cost = Σ deprivation cost of transported casualties + Σ penalty cost for un-transferred casualties (those who cannot be served)

**Objective 2 (F2)**: Minimize total operation cost = facility setup cost + transportation cost + allocation cost

**Uncertainty handling**:
- Casualty numbers: interval [a^-, a^+] → interval robust optimization
- Facility disruptions: scenario-based (7 scenarios for Wenchuan case)

**Robustness formulation** (Mulvey et al. 1995 framework):
- Solution robustness: minimize variance of F1 across scenarios
- Model robustness: ensure feasibility across all scenarios

### Solution Method
- Epsilon-constraint method: fix F2 ≤ ε, minimize F1; vary ε to generate 11 Pareto solutions
- Compared against HRSB (Hybrid Robust Scenario-Based) model as baseline

### Case Study: Wenchuan Earthquake (2008)
- 10 disaster sites (I1-I10), 10 candidate TMCs (J1-J10), 4 candidate hospitals (H1-H4)
- 7 disruption scenarios (combinations of TMC failures)
- NSRB selects 3 TMC locations; HRSB selects only 2 → NSRB is more conservative but more robust
- NSRB: 65% lower variance in deprivation cost; comparable expected cost

### Writing Lessons
- **Name your model**: "NSRB model" creates a memorable label that reviewers and readers can reference. Always give your proposed model a distinct acronym.
- **Multi-uncertainty combination is a strong contribution**: Combining two different uncertainty paradigms (interval + scenario-based) in one paper is a clearly novel combination — make this explicit in the introduction.
- **Use variance reduction as a key result metric**: Reporting "65% lower variance" is more compelling than just showing a table of numbers — it quantifies the robustness benefit concretely.
- **Justify triage modeling**: Triage classification adds realism and is easy to motivate with real operational guidelines from disaster medicine — cite medical literature for the deprivation cost differentiation.
- **Compare robust vs. non-robust baseline**: Always compare your robust model against the deterministic or less-robust version, not just against other algorithms — this validates the need for robustness.

---

## Paper 5: An Integrated Relief Network Design Model Under Uncertainty: A Case of Iran

**Citation**: Hasani, A., & Mokhtari, H. (2019). An integrated relief network design model under uncertainty: A case of Iran. *Safety Science*, 111, 22–36.

**Venue**: Safety Science — Elsevier, CiteScore ~10

### Key Contribution
Develops a tri-objective robust optimization model for relief network design incorporating Fault Tree Analysis (FTA) for risk assessment. Novel contribution: inventory grouping optimization. Proposes HTNSGAII-VNDS hybrid algorithm with 10 neighborhood structures. Validates on Tehran earthquake scenario.

### Mathematical Model
**Three objectives**:
1. **Maximize total coverage**: Σ covered demand nodes across all scenarios
2. **Minimize total cost**: facility setup + transportation + inventory holding costs
3. **Minimize maximum risk**: worst-case vulnerability score across all relief centers

**Risk modeling via Fault Tree Analysis (FTA)**:
- Three failure events for each facility:
  - E1: Relief center not located at candidate site
  - E2: Located but outside coverage range of demand
  - E3: Located, within range, but facility itself disrupted during disaster
- FTA combines these into a composite vulnerability probability per candidate site

**Inventory grouping**: Group relief items by shelf life and demand urgency; optimize inventory decisions at group level rather than individual item level — reduces model size while maintaining operational realism.

**Scenario-based robust model**: S scenarios representing different earthquake severity levels; robustness objectives ensure coverage and cost targets are met across all scenarios.

### Algorithm: HTNSGAII-VNDS
- **NSGA-II**: Base multi-objective evolutionary algorithm managing Pareto frontier
- **VNDS (Variable Neighborhood Descent/Search)**: Local improvement operator applied within NSGA-II's improvement phase
- **10 neighborhood structures (k1-k10)**: Different types of solution perturbations (swap relief center locations, reassign demand nodes, change inventory groups)
- **Performance metrics**: HV (hypervolume), Setc (set coverage), SM (spacing metric)

### Case Study: Tehran Earthquake
- Tehran: population ~15 million, high seismic risk (located on multiple fault lines)
- Five test instances: small (20 demand, 15 relief centers) to large (140 demand, 120 relief centers)
- HTNSGAII-VNDS outperforms baseline NSGA-II and standalone VNDS on all three metrics across all instances

### Structure
1. Introduction (Tehran earthquake risk, research gap)
2. Literature Review
3. Problem Description (FTA, inventory grouping motivation)
4. Mathematical Model (three objectives, constraints, FTA integration)
5. HTNSGAII-VNDS Algorithm
6. Computational Experiments (5 instances, 3 metrics, statistical comparison)
7. Conclusions

### Writing Lessons
- **FTA provides a rigorous risk quantification method**: Instead of assigning arbitrary disruption probabilities, use FTA to derive vulnerability from operational logic — reviewers find this more defensible.
- **Hybrid algorithm requires dual justification**: Justify both components separately (why NSGA-II? why VNDS?) before justifying the combination. Show that neither alone is as effective.
- **Inventory grouping simplification must be validated**: When simplifying the model for computational tractability, show that the simplification does not significantly affect solution quality — compare grouped vs. ungrouped on small instances.
- **Multiple instance sizes demonstrate scalability**: Running 5 instances of increasing size and showing the algorithm scales well strengthens the practical contribution claim.
- **Report all three performance metrics**: Using HV + Setc + SM together is now the standard for multi-objective algorithm comparison in this domain.

---

## Paper 6: Disaster Relief Facility Network Design in Metropolises

**Citation**: Zhen, L., Wang, K., & Liu, H. C. (2014). Disaster relief facility network design in metropolises. *IEEE Transactions on Systems, Man, and Cybernetics: Systems*, 45(2), 207–219.

**Venue**: IEEE Transactions on Systems, Man, and Cybernetics: Systems (IEEE TSMC) — IEEE flagship journal

### Key Contribution
Integer programming model for simultaneous location of emergency shelters and supply/medical centers in metropolises. Proposes a Lagrangian relaxation decomposition into three independent subproblems, solved by subgradient method. Demonstrates ~2.7% optimality gap on Shanghai demo (500 residential areas, 300 shelter candidates, 60 supply center candidates).

### Mathematical Model
**Objective** (minimize total establishment cost):
```
min Σ_s∈S e_s·x_s + Σ_c∈C f_c·y_c + Σ_s∈S Σ_c∈C t_sc·h_sc
```
- `x_s ∈ {0,1}`: open shelter s
- `y_c ∈ {0,1}`: open supply/medical center c
- `h_sc ∈ {0,1}`: assign supply center c to shelter s
- `e_s`: establishment cost of shelter s
- `f_c`: establishment cost of supply/medical center c
- `t_sc`: assignment cost linking shelter s to center c

**Constraints**: Coverage radius constraints (shelter must be within radius of residents), assignment logic (each open shelter assigned to at least one open supply center), capacity constraints.

### Lagrangian Relaxation
- Relax: coupling constraints between x, y, h variables
- Results in three independent subproblems: M_LR_x (shelter location), M_LR_g (coverage assignment), M_LR_yhz (supply center location + shelter-center assignment)
- Subgradient method: update multipliers over up to 200 iterations
- Lagrangian gap: ~2.7% (near-optimal solutions)

### Case Study: Shanghai
- |A| = 500 residential areas, |S| = 300 possible shelter sites, |S'| = 10 selected shelters
- |C| = 60 possible supply center candidates, |C'| = 3 selected centers
- Proposed model achieves ~20% cost reduction vs. intuitive (non-optimized) method
- Sensitivity analysis: varying coverage radius, population distribution, facility costs

### Structure
1. Introduction (metropolis-specific challenges — dense population, road network complexity)
2. Problem Formulation
3. Lagrangian Relaxation Algorithm
4. Computational Results (Shanghai case + sensitivity analysis)
5. Conclusion

### Writing Lessons
- **Large-scale case studies need decomposition methods**: When problem scale makes exact solvers intractable, Lagrangian relaxation is the canonical approach. Always report the Lagrangian gap to validate solution quality.
- **Comparison with intuitive method is powerful**: Showing that the optimization model beats a "reasonable" intuitive benchmark by 20% motivates practitioners to adopt the model — pure algorithm comparison misses this practical angle.
- **Metropolis framing**: Emphasizing that the model is designed for large cities (dense populations, complex road networks, high facility costs) creates a clear positioning that differentiates from rural/general disaster relief models.
- **Sensitivity analysis should test managerial levers**: Test coverage radius (a policy decision), budget (a resource constraint), and population distribution (an input uncertainty) — these are the parameters that decision-makers actually control.
- **Report both the model and the solver**: Specify solver software, version, hardware, and time limits. This enables reproducibility and gives context for solution times.

---

## Paper 7: Humanitarian Facility Location Under Uncertainty: Critical Review and Future Prospects

**Citation**: Donmez, Z., & Ekici, A. (2021). Humanitarian facility location under uncertainty: Critical review and future prospects. *Omega*, 102, 102393.

**Venue**: Omega — The International Journal of Management Science; ABS 4*

### Key Contribution
Comprehensive systematic review of 108 articles on humanitarian facility location under uncertainty (2007-2019). Establishes a unified taxonomy of facility types, uncertainty sources, uncertainty paradigms, and optimization criteria. Identifies research gaps and future directions.

### Taxonomy and Key Statistics

**Facility Types Covered**:
- Suppliers (procurement nodes)
- Distribution Centers (DCs) — most studied
- Points of Distribution (PODs) — last-mile delivery
- Shelters — pre-disaster location
- Field hospitals — medical response
- Blood centers — specialized inventory

**Uncertainty Sources (count out of 108 papers)**:
- Demand uncertainty: dominant (85+ papers)
- Supply uncertainty: moderate (64 papers)
- Network connectivity/disruption: less common (33 papers)

**Uncertainty Paradigms**:
- Stochastic Programming (SP): ~64 papers (~60%)
- Robust Optimization (RO): ~26 papers (~24%)
- Chance-Constrained Programming (CCP): ~15 papers (~14%)
- Trend: RO and CCP are increasing over time

**Optimization Criteria**:
- Cost minimization: 97/108 papers (dominant)
- Equity: secondary criterion in ~30% of papers
- Reliability/coverage: tertiary criterion

**Cost Components**:
- Fixed setup cost: 80% of papers include this
- Transportation/assignment variable cost: 87% of papers include this
- Inventory holding cost: less common

**Network Structure**:
- Multiple allocation more common than single allocation
- Multi-commodity models: 44% of papers
- Pre-positioning under demand uncertainty: most studied problem type

### Methodology
- Systematic database search (Scopus, Web of Science)
- Inclusion criteria: journal articles, facility location + uncertainty + humanitarian/disaster context
- Classification table with 108 papers coded across 20+ attributes

### Writing Lessons
- **Systematic reviews need a classification table**: The 108-paper coding table is the core contribution — without it, the review is just narrative. Create detailed classification with clear coding rules.
- **Statistics should drive narrative**: Every claim in the review is backed by a count ("60% of papers use SP"). This makes the review authoritative and reviewers cannot dispute descriptive statistics.
- **Identify the dominant paradigm and the trend**: Noting that SP dominates but RO/CCP are increasing provides directional guidance to researchers choosing a paradigm — this is actionable insight.
- **Define facility types carefully**: The taxonomy of six facility types is useful because it shows researchers exactly where their work fits and what is under-studied (e.g., field hospitals are less studied than DCs).
- **Future directions must be specific**: Vague future directions ("more work is needed") are less useful than specific gaps ("no paper combines network disruption uncertainty with equity optimization for blood center location").
- **Position as a citation anchor**: By covering 108 papers in one place, the review becomes the standard citation for anyone needing to justify their literature review scope — design your review paper to function as this anchor.
