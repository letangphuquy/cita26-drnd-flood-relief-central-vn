Xin chào AI.

Trong dự án này, tôi đã phát biểu hoàn chỉnh về Thực trạng (Problem), Mô hình hoá bài toán (Mathematical Model).

Tôi cần bạn tiến hành triển khai (implementation) toàn bộ các thí nghiệm. Bao gồm:
1. Phát triển một methodology toàn diện cho việc tổng hợp và tạo sinh, sampling dữ liệu ngẫu nhiên theo xác suất. Đưa ra lý do cho việc chọn các tham số.
2. Thiết kế khung thí nghiệm hoàn chỉnh, và tạo ra 2 bài experiments đơn giản nhưng nêu bật lên được đóng góp của thuật toán. Đề xuất: Pareto figures và solution figures (phân tích managerial insights).
3. Tiền xử lý những bộ Dataset benchmark chuẩn (TR, AP) phục vụ cho thí nghiệm
4. Sử dụng Open API của Map để tạo dữ liệu tổng hợp (synthetic dataset) tuân theo phương pháp luận chặt chẽ như trong 1. Mục tiêu là tạo dữ liệu case study thực tế cho khu vực chịu mưa nhiều nhất và thường xuyên mỗi năm trong miền Trung, với địa hình đa dạng, nhằm mục đích illustration.
5. Lập trình thuật toán solver bằng ngôn ngữ C++ hoặc/ và Python.
6. Chạy thí nghiệm, phân tích số liệu.
7. Hoàn thiện bài paper (Latex source) trong thư mục `src`

Những nội dung quan trọng nhất đã được tóm tắt trong file `project_summary.md`

Đồng thời, tôi cũng đã phát triển một PoC hoàn thiện cho khung giải thuật. Giải thuật được phát triển dựa trên NSGA-II, kết hợp với Local Search heuristics và data structure để hình thành nên thuật toán NSMA. Tuy nhiên, Thuật toán NSMA được áp dụng cho một bài toán khác, đó là bài toán HLP ba mục tiêu áp dụng cho đường sắt. Chi tiết xem thêm ở thư mục `intern`.

Ngoài ra, thư mục `ref` chứa đựng một số nguồn tài liệu tham khảo chính, nhằm cung cấp thêm ngữ cảnh cho bạn suy luận.

Chúc bạn làm việc tốt.

Trong suốt quá trình làm, phải phối hợp và giao tiếp một cách chặt chẽ với tôi.
