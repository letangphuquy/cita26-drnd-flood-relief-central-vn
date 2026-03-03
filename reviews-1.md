Reviewer 1:
- Phần Related Works chưa đủ cơ sở (số lượng bài báo) để nói lên bức tranh tình hình nghiên cứu hiện tại về bài toán DRND trong cứu trợ nhân đạo (Humanitarian Logistics). Nó chưa chỉ rõ được research gaps, và vẫn đang giải thích hơi kỹ cho Continuous Approximation và Deprivation Cost, mà việc giải thích quá kĩ như vậy là không cần thiết.
- Chromosome encoding của R đang ngầm định rằng mỗi hub không được đóng góp quá bình quân $q_k = R_k \cdot \frac{\hat{D}}{n_{\text{open}}}, \quad n_{\text{open}} = \textstyle\sum_{k}$. Ngoài ra, vector biểu diễn $R$ đang bị phụ thuộc vào vector biểu diễn $X$. Hãy de-couple hai cái này ra.
- Cân nhắc chuyển đổi các bước của Decoder thành một khối thuật toán tường minh, trình bày khoa học và gãy gọn hơn.
- Phần dataset description chưa mô tả rõ phương pháp sinh parameters bị thiếu để tạo instance cho bài toán DRND từ instance cho bài toán HLP.
- Phần thí nghiệm: Giá trị HV cần được normalize, bằng cách normalize 2 hàm mục tiêu. 
Code giải thuật vẫn còn lổ hổng, do đó kết quả Pareto Front size chưa chính xác.
- Việc phân tích results ở mục 4.3: Thiếu Pareto plot để minh họa. 
- Phân tích managerial insights: cần có bản đồ Việt Nam và phương án lời giải tìm được bởi thuật toán annotate ở trên hình đó.


Reviewer 2:

Chào tác giả. Bài báo "Modeling the disaster relief hub network design problem: A case of Central Vietnam" giải quyết một bài toán có tính thực tiễn cao và độ phức tạp đáng kể trong lĩnh vực logistics nhân đạo. Việc tích hợp xấp xỉ liên tục (Continuous Approximation - CA) của Daganzo và chi phí thiếu hụt (deprivation cost) vào mô hình ngẫu nhiên hai giai đoạn cho bài toán vị trí trung tâm không đầy đủ (MO-IHLNDP) là một điểm sáng, cho thấy sự đầu tư nghiêm túc vào việc mô hình hóa.

Tuy nhiên, dưới góc độ đánh giá khắt khe về tính logic, ký hiệu toán học và cấu trúc giải thuật, bài báo bộc lộ một số lỗ hổng cần được giải quyết triệt để trước khi có thể được chấp nhận tại một hội nghị chuyên ngành như CITA 2026.

Dưới đây là các nhận xét chi tiết:

### 1. Vấn đề về Ký hiệu và Logic Mô hình Toán học

* 
**Mâu thuẫn trong giả định Xấp xỉ Liên tục (CA):** Bạn sử dụng công thức CA của Daganzo $\Theta_{kis}$ để tính toán chi phí sơ tán dặm cuối. Công thức này giả định mạng lưới di chuyển cục bộ là liên tục và đồng nhất. Tuy nhiên, trọng tâm của bài báo là mạng lưới bị gián đoạn do thảm họa. Bạn định nghĩa biến $a_{uvms}$ cho sự gián đoạn của các cung đường vĩ mô , nhưng không làm rõ sự gián đoạn vi mô (đường xá địa phương) ảnh hưởng thế nào đến tính hợp lệ của tham số $\Phi$ và diện tích $A_i$ trong công thức CA. Nếu một khu vực ngập nặng, công thức $\Theta_{kis}$ sẽ bị sai lệch nghiêm trọng.


* 
**Tính phi tuyến của $Z_2$:** Hàm mục tiêu $Z_2$ sử dụng hàm mũ để đo lường chi phí thiếu hụt. Bạn có đề cập rằng mô hình có thể tuyến tính hóa thành MILP bằng cách tận dụng tính chất phân bổ đơn (single-allocation) $\sum_{k\in\mathcal{H}}z_{iks}=1$. Tuy nhiên, bạn không hề trình bày công thức tuyến tính hóa này. Việc khuyết thiếu định dạng MILP chuẩn xác khiến việc đánh giá giới hạn dưới (lower bound) trở nên bất khả thi.


* 
**Ràng buộc bảo toàn dòng chảy:** Ràng buộc (13) có vẻ đang kết hợp việc đáp ứng nhu cầu (được chuyển đổi qua hệ số $\gamma$) và luân chuyển hàng hóa (trans-shipment). Cần kiểm tra lại logic ở phía vế trái của phương trình: $\sum_{i\in\mathcal{I}}\gamma D_{is}z_{iks}$. Biến $z_{iks}$ là nhị phân (phân bổ nhu cầu $i$ cho trung tâm $k$). Việc nhân trực tiếp tổng nhu cầu với biến phân bổ mà không có biến dòng chảy nội hạt cụ thể có thể dẫn đến việc đánh giá sai lượng hàng tồn kho thực tế bị trừ đi tại trung tâm $k$.



### 2. Lỗ hổng trong Cấu trúc Giải thuật PB-NSGA-II

* 
**Chiến lược giải mã tham lam (Greedy Decoding):** Thuật toán sử dụng phương pháp mã hóa ẩn rất thông minh để giảm không gian tìm kiếm xuống $O(|\mathcal{H}|)$. Tuy nhiên, bước giải mã (Bước 2 và 3) lại hoàn toàn là thuật toán tham lam (greedy). Việc phân bổ nhu cầu cho trung tâm có điểm ưu tiên cao nhất  không đảm bảo tính tối ưu cho quyết định giai đoạn hai (second-stage recourse decision). Điều này có nghĩa là mức độ vi phạm ràng buộc (CV penalty) $\gamma D_{is}$  có thể sinh ra không phải do năng lực mạng lưới yếu kém, mà do heuristic giải mã của bạn bị rơi vào bẫy tối ưu cục bộ.


* 
**Đánh giá mức độ vi phạm (CV):** Cách xử lý cá thể không hợp lệ bằng nguyên tắc "constrained-dominance" là tiêu chuẩn. Tuy nhiên, với một heuristic tham lam, quần thể có thể bị thống trị bởi các giải pháp an toàn nhưng chi phí cực cao, làm mất đi tính đa dạng cần thiết để khám phá màng Pareto.



### 3. Thiết kế Thực nghiệm (Computational Experiments)

* 
**Thiếu Baseline so sánh:** Bạn báo cáo chỉ số Hypervolume (HV) cho các bộ dữ liệu AP, TR81 và CV. Tuy nhiên, việc chỉ báo cáo HV của PB-NSGA-II mà không có đối chuẩn (baseline) là vô nghĩa trong nghiên cứu OR. Đối với các tập dữ liệu nhỏ như AP10, AP20 hoặc CV-Small (chỉ có 5 hubs, 20 điểm cầu), một solver chính xác (như Gurobi hoặc CPLEX) hoàn toàn có thể tìm ra nghiệm tối ưu (hoặc tập Pareto thực sự) thông qua phương pháp $\epsilon$-constraint. Việc thiếu vắng sự so sánh với exact solver hoặc ít nhất là một meta-heuristic khác (ví dụ: MOEA/D) làm suy yếu hoàn toàn tuyên bố về "hiệu suất" của thuật toán.



Bạn có muốn tôi đi sâu vào việc thiết lập công thức toán học tuyến tính hóa cho hàm mục tiêu $Z_2$ để bạn có thể lập trình nghiệm chứng minh với exact solver cho tập dữ liệu CV-Small không?