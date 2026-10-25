# Chạy 3 notebook ML để xuất CSV/joblib vào web

1. Giải nén thư mục `ml_runner` vào thư mục gốc `D:\vietnam_ecom_dwh_project`. Đảm bảo cấu trúc `ml_runner/run_ml.py`, `ml_runner/notebooks/*.ipynb`, `.env`, `backend/`, `docker-compose.yml`.
2. Trong PowerShell: `cd D:\vietnam_ecom_dwh_project`; `docker compose up -d postgres`.
3. `py -m pip install -r .\ml_runner\requirements.txt` (nếu Python mới gặp xung đột gói, dùng Python 3.11/3.12 trong venv).
4. `py .\ml_runner\run_ml.py --only ml1 --copy-web`, sau đó làm tương tự `ml2`, `ml3` (ML2 gồm GridSearchCV, có thể nặng hơn).
5. CSV/joblib được tạo ở `outputs/nb/ml1`, `outputs/nb/ml2`, `outputs/nb/ml3`, và tự chép vào `backend/ml_outputs/`. File notebook có kết quả đã chạy lưu ở `outputs/executed_notebooks/`.
6. Khởi động lại web: `docker compose -f docker-compose.yml -f docker-compose.web.yml up -d --build api`. Kiểm tra `http://localhost:8000/api/v1/ml/status` và dashboard.

**Điểm đã kiểm tra trong notebook:** Cả ba cell cuối đều `SAVE=True`. ML1 xuất 3 CSV và model; ML2 2 CSV + model; ML3 4 CSV. Chúng đọc `localhost:5433/ecom_dwh` bằng biến môi trường `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`. Vì notebook không gọi `load_dotenv()`, runner này nạp `.env` trước khi khởi động kernel.

**Chú ý:** Script chỉ chạy notebook và sao chép file, không ghi vào PostgreSQL, không gọi Media Cloud, không chạy Airflow. Chỉ chạy file .joblib tin cậy từ đồng đội. Nếu API dự đoán ML2 báo khác phiên bản sklearn, đối chiếu `py -m pip show scikit-learn` và version trong Docker image web. Không bắt buộc tải lại dữ liệu tin tức.

Chỉ copy và lưu trữ kết quả ML sau khi xem lại các metric đánh giá. Số liệu notebook phụ thuộc nội dung database lúc chạy và phiên bản thư viện.
