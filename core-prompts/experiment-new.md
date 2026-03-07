NOTE: THIS IS THE CANONICAL VERSION. IMPLEMENT THIS.

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

