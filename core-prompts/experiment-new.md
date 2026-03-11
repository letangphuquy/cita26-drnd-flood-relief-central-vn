NOTE: THIS IS THE CANONICAL VERSION. IMPLEMENT THIS.

Update: The newest paper structure
section Computational Experiments
subsection Experimental Setup
- modify the parameters to match newest

subsection Dataset Description
- unchanged from previous experimental baselines, but you can audit just to make sure
- [Important Decision design question] We move up the SAA and OOS strategy up here in the first two subsection. Need to modify the code so that training happen on the 50-scenario datasets.

subsection Experiment 1: Benchmark comparision
textbf Baseline algorithms
- MILP solver implemented in pymoo with Adaptive Weighted Sum method (cite) produces a true Pareto front for the CV-Small instance.
- Greedy heuristic method simulates a council of decision makers with different weight profiles (please explain in a highly simple and easy to understand manner)
- VNS-TS (cite) is a meta-heuristic baseline in the literature that shown effectiveness in the flood relief model ...

table 1 Metrics on CV-Small (same as before, just change number and algorithm)

- Result interpretation: The exact solver defined the Pareto front for the CV-Small instance. Greedy runs blazing fast but has poor result. VNS-TS performs better, but still inadequate. The proposed PB-NSGA outperforms with faster run time and near-optimal Pareto approximation. As can be seen in figure 1, PB-NSGA consistently find solutions with optimal Z2 deprivation cost, and within a small optimality gap on Z1 logistic cost.

subsection Experiment 2: Case study on Central Vietnam
- brief prose text summarizing the parameters that are set differently than Exp. 1

figure 1 Pareto front

- prose on trade-off analysis and re-affirms proposed PB-NSGA superiority. Talk about knee point -- the "balanced" solution.

- removed table 2 (still keep the values for analysis), instead write a paragraph to report stddev values and confirm algorithm stability. The VNS-TS remains in a close gap with the proposed algorithm, but its run-time is much worse (180s compared to 8s)

figure 2 Visualization of a solution accross three repr. scenarios
- prose text: 
  - The algorithm evolved and learnt that earlier investment is cheapier than any reactive fallback resolution. The hub structure remains the same across scenario, and is robust enough to serve the demands well under different scenarios. 
  - The algorithm favors in-place rescue and need not rely on lateral hub trans-shipment. (comment: The interactivity between hubs structure shall be a future work)

- decision support framework: suggestion for disaster relief management. Adjust the old writing so that new insights match current data perfectly.


figure 3 Convergence analysis.

section Conclusion and future work
- contributions brief (modeling, solving and DSS framework)
- Limitation: Lack of real-world dataset (keep it as it is, but should reduce writing to be cleaner and more compact)
- Future work:
 - Incorporating real-world data and into an DSS ecosystem that can simulate and operate on real-time insights.
 - Improve the model to better account for risk and assess the effect of "black swan" event, and quantify the effects into relief operation (for e.g., increased time and cost at hubs with higher risk)
 - Improve the proposed algorithm so that it works well when scale allowed budget runtime to 1 hour, ensuring continous convergence for meaningful practical implementation.

================

Narrative, thông điệp chính muốn truyền tải thông qua phần Thực nghiệm:
1. The proposed algorithm is effective and efficient for solving the DRND problem (specifically, the proposed MO-IHLNDP model).
2. The joint framework (model and solver) produces useful results and practical managerial insights for flood prevention in Central Vietnam.

Một số vấn đề của phần thực nghiệm hiện tại (commit e9f8844ac7e6e1ae8a08502acbb4d9d2c1a2ad51):
- Chèn vào quá nhiều hình, biểu và kết quả thí nghiệm (data dumping), trong khi phân tích chưa đủ sâu.
- Đang dành khá nhiều space và thời lượng để mô tả thiết lập thực nghiệm và phương pháp làm dữ liệu, dù đây không phải là phần quan trọng nhất của bài báo.

Đề xuất hướng thực nghiệm mới:
- Loại bỏ map `figures/cv_network_map.pdf` để tiết kiệm không gian.
- (temporarily) removing benchmark experiments (Experiment 1).
- Focus on the case study in Central Vietnam (Experiment 2).
- For message 1., develop a baseline algorithm (e.g., a simple greedy algorithm and/or a single-objective optimization algorithm, like epsilon-constraint method) to compare with the proposed algorithm.
  - evaluate on small instances of case study dataset.
  - measuring HV, IGD+ and running time (in CPU seconds).
  - output: a table
  - conclusion should claim the superiority of the proposed algorithm over the baseline algorithm.
- For message 2., i.e. the case study in Central Vietnam
  - evaluate on the full case study dataset (large instance).
  - putting Sample Average Approximation (SAA) and Out-of-sampling as the main method for experiment design. Add a single citation to credit the two techniques. 
  - For illustration, analysis and insight, pick three representative scenarios from the SAA set, corresponding to three levels: mild, severe and catastrophic (extreme).
  - The solution found by our proposed algorithm PB-NSGA for the three representative scenarios should be presented in a single figure, with three subfigures, each showing the solution for one scenario. Requirement on the illustration of the solutions:
    - Each solution is overlayed on Vietnamese map with real coordinates (collected from dataset)
    - The decision variable should be depicted and annotated correctly, showing all information: planned hub, reactive hub, hub-demand assignment, orign-hub assignment, inter-hub flow. The three transportation mode established on each link (u,v) should be clearly visible (e.g., using different colors or line styles).
    - The total cost and total deprivation cost should be annotated on the figure.
    - The figure should be well-designed, clear, and easy to understand.
  - Analysis on the solution produced by algorithm per each representative case (in the three cases) should explain the decision made, imply its meaning. From that, concludes on the "flexibility" and practicality of the model, and derive suggestions for managerial insights.
  - The sensitivity analysis can be incorporated to the analysis subsection above, further validating the problem formulation.

