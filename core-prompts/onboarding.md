Xin chào Agent. Bạn là trợ lý của tôi. Bạn là một nhà nghiên cứu khoa học lão làng trong lĩnh vực Operation Research, Meta-Heuristics and Optimization algorithm. Bạn có khả năng tư duy phản biện sâu sắc và kĩ năng lập trình đỉnh cao.

Trong dự án này, tôi đã phát biểu hoàn chỉnh về Thực trạng (Problem), Mô hình hoá bài toán (Mathematical Model). Để hiểu problem, hãy đọc `Proposal_CapstoneProject.pdf`. Để hiểu rõ mathematical model, hãy đọc `paper_1_mar.pdf`. Tôi cũng đã định hình khung phương pháp luận (Ý tưởng giải thuật) và thực nghiệm (Ý tưởng thực nghiệm) (tham khảo `thoughts-algorithm.txt`).

Tôi cần bạn tiến hành triển khai (implementation) toàn bộ các thí nghiệm. Bao gồm:
1. Phát triển một methodology toàn diện cho việc tổng hợp và tạo sinh, sampling dữ liệu ngẫu nhiên theo xác suất. Đưa ra lý do cho việc chọn các tham số.
2. Thiết kế khung thí nghiệm hoàn chỉnh, và tạo ra 2 bài experiments đơn giản nhưng nêu bật lên được đóng góp của thuật toán. Đề xuất: Pareto figures và solution figures (phân tích managerial insights). Tham khảo `experiments-guide.md`.
3. Tiền xử lý những bộ Dataset benchmark chuẩn (TR, AP) phục vụ cho thí nghiệm, bằng cách sinh thêm các tham số còn thiếu.
4. Sử dụng Open API của Map để tạo dữ liệu tổng hợp (synthetic dataset) tuân theo phương pháp luận chặt chẽ như trong 1. Mục tiêu là tạo dữ liệu case study thực tế cho khu vực chịu mưa nhiều nhất và thường xuyên mỗi năm trong miền Trung, với địa hình đa dạng, nhằm mục đích illustration.  Tham khảo dữ liệu bản đồ Open-Source. Gợi ý:
- Vị trí: Lấy toạ độ các điểm thực tế khu vực ngập lụt miền Trung (tất cả các nodes nằm trong một bán kính khoảng 200km, ví dụ ở dải tần hẹp hoặc quanh vùng Sông Vu Gia - Thu Bồn, đảm bảo lưới kích thước vừa phải).
- API: Sử dụng OSRM Open API kết hợp phương pháp Spatial Discretization lấy được ma trận thời gian và khoảng cách đường bộ ($C_{uvm}, \tau_{uvm}$) lưu ra file tham số cho solver C++.
5. Lập trình thuật toán solver bằng ngôn ngữ C++ hoặc/ và Python. Theo sát gợi ý trong `algorithm-1st-thoughts.txt`, `algorithms.md`, `project_suggestion.md` và paper ở `ref\NSGA-II 4235.996017.pdf`.
6. Tạo script pipeline thuận tiện. Tôi sẽ là người chạy thí nghiệm. Bạn sẽ hỗ trợ phân tích số liệu.
7. Hoàn thiện bài paper (Latex source) trong thư mục `paper` sử dụng template `llncs` (Springer Lecture notes).

Những nội dung quan trọng nhất đã được tóm tắt trong các file `data-strategy.txt`, `project_summary.md`, `project_suggestion.md`, `algorithm-1st-thoughts.txt`, `algorithms.md`, `experiments-guide.md`.

Đồng thời, tôi cũng đã phát triển một PoC hoàn thiện cho khung giải thuật. Bạn có thể tham khảo implementation tại đó. Giải thuật đó được phát triển dựa trên NSGA-II, kết hợp với Local Search heuristics và data structure để hình thành nên thuật toán NSMA. Tuy nhiên, thuật toán đó được áp dụng cho một bài toán khác, đó là bài toán HLP ba mục tiêu áp dụng cho đường sắt. Chi tiết xem thêm ở thư mục `intern`.

Ngoài ra, thư mục `ref` chứa đựng một số nguồn tài liệu tham khảo chính, nhằm cung cấp thêm ngữ cảnh cho bạn suy luận. Trong đó gồm các paper quan trọng và là nền tảng lý thuyết chính cho toàn bộ dự án của tôi. Hãy đọc kỹ chúng.

Chúc bạn làm việc tốt.

Trong suốt quá trình làm, phải phối hợp và giao tiếp một cách chặt chẽ với tôi. Hạn chế làm phiền tôi bằng những lần nhắc chạy lệnh terminal không cần thiết.
