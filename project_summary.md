# PROJECT BLUEPRINT: DISASTER RELIEF HUB NETWORK DESIGN

## 1. References & Resources
* **Primary Framework:** Non-dominated Sorting Genetic Algorithm II (NSGA-II) combined with Local Search (NSMA).
* **Base Methodology Reference:** `paper.pdf`, `FullVersion_IncompleteUncapacitated.pdf` (Railway HLP applied in Thailand).
* **Key Academic References:**
  * Holguín-Veras, J., et al. (2013). On the appropriate objective function for post-disaster humanitarian logistics models (Deprivation Cost).
  * Daganzo, C.F. (2005). Logistics systems analysis (Continuous Approximation).
  * Yahyaei, M., & Bozorgi-Amiri, A. (2019). Robust reliable humanitarian relief network design.

## 2. Project Title
**A Two-Stage Stochastic Multi-Objective Hub Location Network Design Model for Disaster Relief: A Case of Central Vietnam**

## 3. Introduction & Problem Description
The Disaster Relief Network Design (DRND) problem involves establishing an optimal and reliable humanitarian logistics network under severe environmental constraints and uncertainties. Focusing on flood response in Central Vietnam, the problem is formulated as a Multi-Objective Incomplete Hub Location Network Design Problem (MO-IHLNDP).

**Key Problem Characteristics:**
* **Three-Echelon Network:** Origins (volunteers/suppliers) $\rightarrow$ Hubs (rescue stations) $\rightarrow$ Demands (distress clusters).
* **Two-Stage Stochasticity:** Decisions are split into Phase 1 (pre-disaster proactive hub establishment) and Phase 2 (post-disaster reactive hub setup, origin-to-hub supply, and hub-to-demand evacuation across multiple disruption scenarios).
* **Infrastructure Disruption:** Modeled via scenario-dependent accessibility matrices ($a_{uvms}$) representing blocked paths.
* **Dual Objectives:** Balancing pure logistics/financial costs ($Z_1$) against social equity and human suffering ($Z_2$).

## 4. Mathematical Formulation
*The model adopts a grid-based spatial discretization to maintain computational linearity for logistics costs while utilizing Daganzo's Continuous Approximation for last-mile routing.*

### 4.1. Objectives
**Objective 1: Minimize Total Expected Logistics Cost**
$$
\begin{aligned}
    \text{Min } Z_1 = & \sum_{k \in \mathcal{H}} F_k x_k + \sum_{k \in \mathcal{H}} c_k q_k \\
    & + \sum_{s \in \mathcal{S}} \pi_s \Bigg[ \sum_{k \in \mathcal{H}} F_{ks}^a y_{ks} 
    + \sum_{j \in \mathcal{J}} \sum_{k \in \mathcal{H}} \left( \min_{m \in \mathcal{M} \mid a_{jkms}=1} C_{jkm} \right) O_{js} z_{jks} \\
    & + \sum_{k \in \mathcal{H}} \sum_{h \in \mathcal{H}} \sum_{m \in \mathcal{M}} \alpha C_{khm} f_{khms} 
    + \sum_{k \in \mathcal{H}} \sum_{i \in \mathcal{I}} \Theta_{kis} z_{iks} \Bigg]
\end{aligned}
$$
*(Note: $\Theta_{kis}$ is the pre-computed Daganzo CA routing cost).*

**Objective 2: Minimize Expected Maximum Deprivation Cost**
$$
\text{Min } Z_2 = \sum_{s \in \mathcal{S}} \pi_s \left( \max_{i \in \mathcal{I}} \left[ D_{is} \cdot \left( e^{\lambda_{is} \cdot \Omega_{is}} - 1 \right) \right] \right)
$$
*(Note: $\Omega_{is} = \sum_{k} z_{iks} ( \tau_{ks} + 2 \cdot \min_{m} \tau_{kim} )$).*

### 4.2. Core Constraints
1. **Hub Safety & Configuration:** $x_k + y_{ks} \le 1$; $r_{ks} \cdot (x_k + y_{ks}) \le \chi$.
2. **Single Allocation:** $\sum_k z_{iks} = 1$; $\sum_k z_{jks} = 1$.
3. **Accessibility:** Assignments $z_{iks}$ and $z_{jks}$ are bounded by traversable paths $\sum_m a_{ikms}$.
4. **Flow Conservation:** Local consumption ($\gamma D_{is}$) + Outgoing flows $\le$ Pre-positioned Inventory ($q_k$) + Incoming external supply ($O_{js}$) + Incoming trans-shipments.

## 5. Algorithmic Framework: NSGA-II with Local Search (NSMA)


### 5.1. Chromosome Representation (Scenario-Stacked Encoding)
A single chromosome represents a complete DRND strategy. It is represented as an integer array combining Stage-1 decisions and Stage-2 scenario-specific responses.
* **Part 1 (Strategic):** Binary array of length $|\mathcal{H}|$ representing $x_k$ (Proactive Hubs).
* **Part 2 (Operational - repeated for each scenario $s$):**
  * **Reactive Hubs:** Binary array of length $|\mathcal{H}|$ for $y_{ks}$. (Masked by risk threshold $\chi$).
  * **Demand Allocation:** Integer array of length $|\mathcal{I}|$ representing $z_{iks}$. Value at index $i$ is the assigned Hub ID $k$.
  * **Origin Allocation:** Integer array of length $|\mathcal{J}|$ representing $z_{jks}$. Value at index $j$ is the assigned Hub ID $k$.
*(Total Chromosome Length = $|\mathcal{H}| + |\mathcal{S}| \times (|\mathcal{H}| + |\mathcal{I}| + |\mathcal{J}|)$).*

### 5.2. Fitness Evaluation & Inner Decoding
* Extract $x, y, z$ directly from the chromosome.
* **$Z_2$ Evaluation:** Calculated instantly using the assignment vectors and pre-computed time matrices.
* **$Z_1$ Evaluation:** Calculates fixed costs and last-mile CA costs directly. The lateral trans-shipment flows ($f_{khms}$) are resolved via an inner Greedy Heuristic (or linear relaxation) to satisfy flow balance constraints optimally.

### 5.3. Genetic Operators
* **Selection:** Binary Tournament Selection based on Non-dominated Rank and Crowding Distance.
* **Crossover:** Uniform Crossover applied independently to the strategic part and each operational scenario block to preserve structural logic.
* **Mutation:** Random Resetting Mutation. A gene (allocation) is randomly selected and reassigned to another active hub within the permissible radius.

### 5.4. Local Search (Incremental Evaluation)

Applied to a subset of newly generated offspring. 
* **Mechanism:** Single-node relocation. Iteratively attempts to reassign demand node $i$ from its current hub $k_1$ to an adjacent hub $k_2$.
* **Complexity Reduction:** Instead of re-evaluating the entire objective function $O(N^3)$, the algorithm computes only the differential delta ($\Delta Z_1, \Delta Z_2$) for the affected grids $i$ and hubs $k_1, k_2$. This achieves $O(N)$ evaluation time, significantly accelerating convergence.

## 6. Experimental Instructions (Survival Mode Implementation)

### 6.1. Dataset Generation (Synthetic)
**Goal:** Create a controlled, deterministic dataset representing a localized coastal area to bypass extensive GIS preprocessing.
* **Scale:** $|\mathcal{I}| = 20$ (Demand nodes), $|\mathcal{H}| = 5$ (Candidate Hubs), $|\mathcal{J}| = 2$ (External Origins). Grid size: $50 \times 50$ km.
* **Scenarios ($|\mathcal{S}| = 3$):**
  * *S1 (Mild - 60%):* Low demand, $a_{uvms} = 1$ for 95% of links, risk indices $r_{us} \in [0.1, 0.3]$.
  * *S2 (Severe - 30%):* Medium demand, 30% road links disrupted (forces water mode), risk $r_{us} \in [0.4, 0.7]$.
  * *S3 (Extreme - 10%):* High demand, 60% links disrupted, reactive hubs highly restricted, risk $r_{us} \in [0.8, 1.0]$.
* **Execution:** Use Python (`numpy`, `scipy.spatial.distance`) to generate coordinates, distance matrices, and CSV files for parameters.

### 6.2. Experimental Settings & Execution
* **Algorithm Parameters:** Population Size = 100, Generations = 200, Crossover Rate = 0.9, Mutation Rate = 0.1.
* **Metrics to Capture (Must-haves for the paper):**
  1. **Pareto Front Plot:** Scatter plot showing the trade-off between $Z_1$ (Logistics Cost) and $Z_2$ (Expected Max Deprivation Cost). Emphasize the "knee point".
  2. **Network Topology Visualization:** Extract one "balanced" solution from the Pareto front. Plot two simple node-edge graphs demonstrating how the network dynamically adapts from Scenario 1 (road-heavy, many reactive hubs) to Scenario 3 (water-heavy, consolidated trans-shipment, origin dependency).