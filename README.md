# CapCut Automation Studio Pro

Hệ sinh thái tự động hóa dựng video và xuất Cloud CapCut tốc độ cao, hỗ trợ quy mô công nghiệp từ 100 đến 200+ video/ngày.

---

## 1. Cấu trúc thư mục dự án

```text
CapCut_Automation_Studio/
├── config/                  # Cấu hình, presets, accounts, session, hằng số hệ thống
│   ├── settings.py          # Tập trung toàn bộ hằng số API ByteDance, timeouts, limits
│   ├── presets.json         # Danh mục preset hiệu ứng video (TikTok Fire, Movie Recap...)
│   ├── accounts.json        # Danh sách tài khoản PRO luân phiên
│   ├── session.json         # Session token & cookies đang hoạt động
│   └── voices.json          # Danh mục giọng đọc Text-to-Speech
│
├── core/                    # Toàn bộ lõi nghiệp vụ backend CapCut Cloud
│   ├── auth.py              # Quản lý xác thực, Web signing, tự động làm mới session
│   ├── account_manager.py   # Quản lý hồ sơ & luân chuyển nhiều tài khoản PRO
│   ├── uploader.py          # Dynamic multipart upload (20MB/part, 8 workers, 100MB/s)
│   ├── cloud_draft.py       # Đóng gói Protobuf & lưu Cloud Draft (/video_draft/save)
│   ├── draft_builder.py     # Tạo timeline, áp hiệu ứng, âm thanh, chỉnh màu
│   ├── render_client.py     # Khởi tạo render task, polling batch_get, tải file CDN
│   ├── chunk_engine.py      # Stream copy splitter & concat demuxer fallback
│   ├── effects_catalog.py   # Danh mục hiệu ứng CapCut
│   ├── voice_studio.py      # Bộ tạo giọng đọc TTS
│   └── pipeline.py          # Điều phối toàn bộ quy trình tự động hóa khép kín
│
├── cli/                     # Trình chạy dòng lệnh headless tốc độ cao
│   └── batch_runner.py      # Xử lý hàng loạt không cần giao diện
│
├── gui/                     # Giao diện đồ họa người dùng
│   └── app.py               # CapCut Studio GUI (CustomTkinter Dark Mode)
│
├── utils/                   # Bộ công cụ trợ giúp
│   └── media_info.py        # FFprobe đọc metadata, tính MD5 & CRC32
│
├── run_gui.py               # 1-click khởi chạy giao diện GUI
├── run_gui.bat              # Shortcut Windows mở GUI tiện lợi
├── run_cli.py               # 1-lệnh chạy Batch CLI
└── requirements.txt         # Thư viện phụ thuộc
```

---

## 2. Hướng dẫn sử dụng

### Cách 1: Sử dụng giao diện đồ họa (GUI)
Nhấp đúp chuột vào file `run_gui.bat` hoặc gõ lệnh:
```powershell
py run_gui.py
```
Trong giao diện GUI:
- **Tab 1: 🎬 Create Job**: Thiết lập chi tiết từng video đơn lẻ hoặc thử nghiệm các công thức render (Recipe, Hiệu ứng, Màu sắc, Overlay).
- **Tab 2: ⚡ Batch Automation (MỚI)**: Trực tiếp vận hành hàng loạt 100–200 video/ngày với giao diện trực quan:
  - Chọn Folder chứa hàng loạt video nguồn hoặc Thêm từng File video.
  - Chọn thư mục xuất thành phẩm (tự động mở Explorer).
  - Chọn Preset (TikTok Fire v3, Movie Recap...), độ phân giải (1080p, 2K, 4K), số luồng render song song (1-8 workers).
  - Bật/tắt "Xoay vòng Account Pro" để phân bổ hạn mức Cloud.
  - Bảng hàng đợi thời gian thực: Hiển thị trạng thái chi tiết từng video (Chờ, Uploading, Rendering %, Hoàn tất, Lỗi).
  - Nút Bắt đầu / Dừng khẩn cấp và 4 thẻ thống kê trực quan (Tổng, Đang chạy, Hoàn tất, Lỗi).

### Cách 2: Sử dụng dòng lệnh Batch CLI (Headless background)
Chạy tự động toàn bộ thư mục video mà không cần mở giao diện:
```powershell
# Xem danh sách preset hiện có:
py run_cli.py --list-presets

# Chạy toàn bộ thư mục video với 4 luồng song song:
py run_cli.py -i "E:\InputVideos" -o "E:\OutputVideos" -w 4 -p "TikTok Fire v3"

# Chạy danh sách các file cụ thể:
py run_cli.py -i video1.mp4 video2.mp4 -o "E:\OutputVideos" -w 3

# Kích hoạt xoay vòng nhiều tài khoản PRO (tránh rate-limit):
py run_cli.py -i "E:\InputVideos" -o "E:\OutputVideos" -w 4 --rotate-accounts
```

---

## 3. Đặc điểm kỹ thuật nổi bật

- **Render 1 lần (Single Pass):** Hỗ trợ render cloud trực tiếp video từ 10 phút đến 1 giờ 30 phút mà không cần cắt lát 60s, không lỗi 19070005.
- **Tốc độ Upload 100+ MB/s:** Tự động điều chỉnh chunk 20MB cho file lớn > 1GB và tải song song 8 luồng qua ByteDance TOS SigV4.
- **Kháng lỗi độc lập:** Trong chế độ hàng loạt, nếu 1 video bị lỗi nguồn thì hệ thống tự ghi nhận và tiếp tục các video khác mà không làm gián đoạn toàn bộ hàng đợi.
