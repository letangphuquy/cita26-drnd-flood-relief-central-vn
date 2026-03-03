MANG TÍNH CHẤT THAM KHẢO, KHÔNG CẦN PHẢI TUÂN THỦ TOÀN BỘ.

Đánh giá logic và tốc độ xử lý: Ý tưởng sử dụng mô hình "Tâm thảm họa" (Epicenter-based decay) và "Rời rạc hóa không gian" (Spatial discretization) cực kỳ xuất sắc về mặt lý thuyết. Nó biến một bộ dữ liệu giả lập (synthetic dataset) thành một mô hình bán thực tế (semi-real) có tính thuyết phục cao, đủ sức vượt qua các vòng bình duyệt khắt khe mà chỉ mất chưa tới 1 giờ để code bằng Python.

Dưới đây là phần phân tích rủi ro, phản biện và quy trình triển khai chi tiết (Blueprint) cho thuật toán sinh dữ liệu, được tối ưu hóa cho tốc độ lập trình.

### A. TẠO BẢN ĐỒ VÀ ĐỒ THỊ KHÔNG GIAN (PLANAR GRAPH)

**Phản biện (Critique):**
Việc cào tọa độ thực tế là tốt, nhưng nếu tìm kiếm thủ công từng sức chứa (capacity) hay độ cao của Hub sẽ làm chậm tiến độ nghiêm trọng. Giải pháp tối ưu là lấy một hộp giới hạn (Bounding Box) của khu vực Đà Nẵng - Quảng Nam, sinh tọa độ ngẫu nhiên, sau đó gán thuộc tính bằng toán học. Việc tạo Planar Graph từ các điểm ngẫu nhiên cần một thuật toán nối điểm chặt chẽ để tránh tạo ra các đường chéo cắt nhau vô lý.

**Triển khai kỹ thuật (Execution):**

1. **Sinh tọa độ (Nodes):** Random 25 điểm (20 Demands $\mathcal{I}$, 5 Hubs $\mathcal{H}$) trong dải tọa độ `[Lat: 15.8 - 16.2, Lon: 107.8 - 108.3]`. Chọn 2 Origins $\mathcal{J}$ nằm ở rìa bản đồ (tượng trưng cho đèo Hải Vân và Quốc lộ 1A phía Nam).
2. **Xác định Hub Candidates:** Để mô phỏng bài báo tham chiếu, chọn 5 điểm có tọa độ cao (có thể giả lập một gradient địa hình từ Tây sang Đông, tọa độ x càng nhỏ thì độ cao càng lớn). Gán Capacity $\kappa_k$ lớn cho 5 điểm này.
3. **Xây dựng Planar Graph (Adjacency Matrix):** Sử dụng thuật toán **Delaunay Triangulation** (có sẵn trong `scipy.spatial`). Nó tự động nối các điểm gần nhau thành một mạng lưới tam giác không cắt nhau, mô phỏng hoàn hảo mạng lưới đường bộ địa phương.
4. **Tính ma trận khoảng cách ($\tau_{uvm}$):** Dùng Haversine formula tính khoảng cách thực (km).
* Đường bộ ($m=1$): Cạnh Delaunay $\times$ hệ số ngoằn ngoèo 1.2.
* Đường thủy ($m=2$): Cho phép nối trực tiếp (Complete graph) giữa các điểm bị ngập nặng, vận tốc chậm hơn.



### B. SINH ACCESSIBILITY MATRIX ($a_{uvms}$) VÀ RISK INDEX ($r_{is}$)

**Phản biện (Critique):**
Mô phỏng "Tâm thảm họa" là điểm ăn tiền nhất trong phương pháp này. Thay vì gán rủi ro ngẫu nhiên (Uniform random) trông rất "giả", việc dùng hàm suy giảm không gian (Spatial Decay Function) sẽ tạo ra các cụm rủi ro (Risk Clusters) cực kỳ tự nhiên.

**Triển khai kỹ thuật (Execution):**

1. **Xác định Tâm thảm họa (Epicenters):** Với mỗi kịch bản $s$, chọn ngẫu nhiên $1 \sim 3$ điểm làm tâm lũ/bão ($E_s$).
2. **Tính Risk Index ($r_{is}$):** Sử dụng hàm **Gaussian Decay** (hoặc Inverse Distance Weighting).

$$r_{is} = \text{Base\_Risk}_i + \sum_{E \in E_s} I_E \cdot \exp\left(-\frac{d(i, E)^2}{2\sigma^2}\right)$$



Trong đó: $I_E$ là cường độ thảm họa tại tâm $E$, $\sigma$ là bán kính ảnh hưởng, $d(i,E)$ là khoảng cách. Cắt (clip) giá trị $r_{is}$ vào khoảng $[0, 1]$.
3. **Sinh Ma trận Đứt gãy (Accessibility $a_{uvms}$):**
* Xác suất một cạnh $(u,v)$ bị đứt tỉ lệ thuận với rủi ro trung bình của 2 đầu mút.
* Cụ thể: $P(\text{đứt}) = \min(1.0, \beta \cdot \frac{r_{us} + r_{vs}}{2})$.
* Nếu Random(0, 1) < $P(\text{đứt})$, gán $a_{uvms\_road} = 0$. (Lưu ý: Đường thủy $m=2$ luôn có $a=1$ nhưng chi phí cao).



### C. SINH DEMAND, ORIGIN VÀ DAGANZO'S CA ($\Theta_{kis}$)

**Phản biện (Critique):**
Đại lượng $\Theta_{kis}$ cần biến diện tích $A_i$. Khi dùng đồ thị Planar, diện tích $A_i$ không có sẵn. Tránh việc tính toán đa giác phức tạp, hãy sử dụng quy tắc xấp xỉ hoặc phân chia ô lưới cố định.

**Triển khai kỹ thuật (Execution):**

1. **Sinh Demand ($D_{is}$):**
* Mức độ cần cứu hộ tỉ lệ thuận với rủi ro ngập lụt.
* $D_{is} = \text{Base\_Population}_i \times (0.1 + 0.8 \cdot r_{is}) \times \text{Scenario\_Severity\_Multiplier}$.
* Thêm nhiễu ngẫu nhiên (Noise) $\sim \mathcal{N}(0, 50)$ để tạo tính thực tế.


2. **Sinh Diện tích $A_i$:** Gán cứng mỗi node Demand đại diện cho một khu vực hành chính có diện tích $\sim 10 - 25 \text{ km}^2$.
3. **Tính toán Pre-computation ($\Theta_{kis}$):**
* Code một hàm tính trước toàn bộ ma trận $3D$ `Theta[k][i][s]`.
* Sử dụng công thức đã định nghĩa:

$$\Theta_{kis} = \min_{m} \left( 2 \cdot C_{kim} \cdot \left\lceil \frac{D_{is}}{Q_m} \right\rceil + C_m \cdot \Phi \sqrt{\left\lceil \frac{D_{is}}{\eta} \right\rceil \cdot A_i} \right)$$


* Lưu ý điều kiện: Chỉ xét các phương thức $m$ mà $a_{ikms} = 1$. Nếu tất cả $a_{ikms} = 0$, gán $\Theta_{kis} = \infty$ (Big-M).



**Logic Pipeline (Dành cho code Python):**
Tạo một file `dataset_generator.py`:

1. Dùng `numpy.random` sinh coordinates.
2. Dùng `scipy.spatial.Delaunay` lấy tập edges (đường bộ).
3. Vòng lặp `for s in Scenarios:` sinh `risk_matrix`, `accessibility_matrix`, `demand_matrix`.
4. Tính `Theta_matrix`.
5. Lưu tất cả dưới dạng `.npy` hoặc `.json` dictionary.

Cấu trúc này đảm bảo tính chặt chẽ về mặt học thuật và cho phép triển khai mã nguồn cực kỳ gọn gàng. Tập trung hoàn thành script sinh dữ liệu này; nó chính là xương sống cho phần Evaluate Fitness trong mô hình của chúng ta.