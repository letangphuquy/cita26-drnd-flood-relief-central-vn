---
trigger: always_on
---

STRICTLY FOLLOW:
TẤT CẢ NHỮNG TÁC VỤ NÀY, BẠN PHẢI DÙNG AGENT TOOL VÀ KHÔNG ĐƯỢC PHÉP SỬ DỤNG TERMINAL COMMAND. TUYỆT ĐỐI KHÔNG. Danh sách:
- Search file
- Đọc nội dung của file
- Tạo tệp mới
- Edit file
- Delete và remove file

Hãy dùng agent tool được tích hợp!

Nếu bạn có dự định tạo script để khảo sát, print debug, print value, và những script đó có thể tái sử dụng lâu dài, hoặc có mức độ hữu ích cao. Hoặc: Chúng tương đối dài và phức tạp ( >= 7 dòng code). Hãy TẠO TỆP (ví dụ util-check-file.py) và lưu trong thư mục con `.agent` của current working directory và invoke tệp script đó thay vì chạy trực tiếp trên command line!!!!

Hạn chế việc yêu cầu tôi xác nhận lệnh chạy trên terminal (command line) khi không thật sự cần thiết.

Để hạn chế việc phải intterupt mạch làm việc, bạn có thể sử dụng "batching strategy" -- gom nhiều script lại và chạy một lần trong một command duy nhất.

NOTE: ESPECIALLY CAREFUL, TRÁNH CHẠY NHỮNG CÂU LỆNH NGUY HIỂM.

Với những câu lệnh delete data, delete file, cần phải cẩn thận và yêu cầu user xác nhận