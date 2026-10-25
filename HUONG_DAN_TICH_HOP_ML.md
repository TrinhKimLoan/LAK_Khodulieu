# Tích hợp 3 notebook Machine Learning vào dashboard EcomInsight

## Tình trạng thực tế sau khi xem 3 notebook

| Notebook | Kết quả ghi trong notebook | Phần hiển thị web |
|---|---|---|
| ML1 RFM + K-Means | K=3; các cụm ổn định, phân khúc theo R/F/M | Trang **Khách hàng**: biểu đồ quy mô cụm, bảng summary, khách hàng đã gán nhãn |
| ML2 Random Forest Giao hàng | RF MAE 0,919 ngày, baseline TB theo loại giao hàng 0,914 ngày (baseline nhỉnh hơn) | Trang **Vận chuyển**: so sánh mô hình và feature importance; thêm endpoint dự đoán bằng model thực tế nếu có `ml2_model.joblib` |
| ML3 Gợi ý sản phẩm | Item-CF/Content-based không vượt MostPopular/Random tại 2 protocol | Trang **Sản phẩm**: hiển thị đánh giá thực nghiệm; **không** bật gợi ý cá nhân hóa như thể đã đạt hiệu quả |

**Không dùng 3 file `.ipynb` trực tiếp làm backend.** Notebook là nơi nghiên cứu/huấn luyện; khi chạy xong sẽ xuất CSV/model để API đọc. Việc mở dashboard không tự train lại mô hình.

## 1. Sao chép web đã tích hợp

Từ ZIP, sao chép `backend/` và `docker-compose.web.yml` vào thư mục gốc dự án `D:\vietnam_ecom_dwh_project`, thay thế bản web cũ sau khi sao lưu. `backend/ml_api.py` là module mới; `backend/main.py` đã đăng ký các endpoint ML.

## 2. Chạy notebook để xuất kết quả

Ba notebook đã có ô **SAVE = True ở gần cuối**. Chạy đầy đủ từ đầu đến cuối khi PostgreSQL `localhost:5433` có dữ liệu và đúng `POSTGRES_PASSWORD` của môi trường Python chạy notebook (notebook hiện đọc env, nhưng không tự gọi `load_dotenv()` trong ô đầu). Bạn ML có thể sửa cách load env an toàn trước khi chạy; tuyệt đối không commit password.

**Lưu ý đường dẫn**: notebook định nghĩa `OUT_DIR = Path.cwd() / 'outputs' / 'nb' / 'ml1'` (tương tự ml2, ml3), nên đường dẫn thật phụ thuộc **current working directory khi Jupyter chạy**; không nhất thiết cùng thư mục notebook. Sau khi hoàn tất, kiểm tra bằng `print(OUT_DIR.resolve())`.

Kỳ vọng các file được xuất:

```
outputs/nb/ml1/ml1_customer_segments.csv
outputs/nb/ml1/ml1_cluster_summary.csv
outputs/nb/ml1/ml1_k_selection.csv
outputs/nb/ml1/ml1_model.joblib
outputs/nb/ml2/ml2_model_comparison.csv
outputs/nb/ml2/ml2_feature_importance.csv
outputs/nb/ml2/ml2_model.joblib
outputs/nb/ml3/ml3_metrics_A_leave_last_out.csv
outputs/nb/ml3/ml3_metrics_B_temporal.csv
outputs/nb/ml3/ml3_category_cooccurrence.csv
outputs/nb/ml3/ml3_recommendations_top5.csv
```

*Không có các CSV/joblib chỉ vì đã nhận notebook.* Nếu output cell cuối của notebook in `Đã lưu vào ...` thì mới được xuất. Không cần đưa `ml3_recommendations_top5.csv` lên web vì notebook kết luận mô hình chưa vượt baseline.

## 3. Copy kết quả vào backend

Ví dụ notebook và repo cùng thư mục hiện hành (thay lại đường dẫn cho đúng trên máy bạn):

```powershell
# Chạy tại thư mục gốc repo, thay D:\ML_Results bằng thư mục chứa outputs do notebook tạo
Copy-Item 'D:\ML_Results\outputs\nb\ml1\*.csv' '.\backend\ml_outputs\ml1\' -Force
Copy-Item 'D:\ML_Results\outputs\nb\ml2\*.csv' '.\backend\ml_outputs\ml2\' -Force
Copy-Item 'D:\ML_Results\outputs\nb\ml2\ml2_model.joblib' '.\backend\ml_outputs\ml2\' -Force
Copy-Item 'D:\ML_Results\outputs\nb\ml3\ml3_metrics_*.csv' '.\backend\ml_outputs\ml3\' -Force
Copy-Item 'D:\ML_Results\outputs\nb\ml3\ml3_category_cooccurrence.csv' '.\backend\ml_outputs\ml3\' -Force
```

Không bắt buộc copy `.joblib` ML1 (web đọc nhãn đã xuất ra CSV). Nếu ML2 chỉ cần trình bày đánh giá, có thể chưa copy `.joblib`; API `/shipping/predict` sẽ báo chưa có mô hình. `joblib` chứa đối tượng Python được pickle: **chỉ nạp file do thành viên đáng tin cậy huấn luyện**.

## 4. Docker / FastAPI

```powershell
cd D:\vietnam_ecom_dwh_project
docker compose up -d postgres
docker compose -f docker-compose.yml -f docker-compose.web.yml up -d --build api
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/v1/ml/status
Invoke-RestMethod http://localhost:8000/api/v1/ml/customers/summary
Invoke-RestMethod http://localhost:8000/api/v1/ml/shipping/evaluation
Invoke-RestMethod http://localhost:8000/api/v1/ml/recommendations/evaluation
```

Mở `http://localhost:8000/`: **Khách hàng**, **Vận chuyển**, **Sản phẩm** có thêm khối ML. `http://localhost:8000/docs`: `POST /api/v1/ml/shipping/predict` để thử dự đoán (nhập đủ trường hợp lệ theo bộ dữ liệu; xem `staging.orders` cho ví dụ). Thư mục `ml_outputs` được COPY vào image khi build nên **khi cập nhật CSV/model phải chạy `up -d --build api` lại**. Không chạy Airflow hay Media Cloud để tích hợp ML.

## 5. Hợp đồng API ML mới

| API | Đầu ra |
|---|---|
| `GET /api/v1/ml/status` | file nào đã sẵn sàng |
| `GET /api/v1/ml/customers/segments?limit=40&offset=0` | danh sách khách + cluster theo ML1 |
| `GET /api/v1/ml/customers/summary` | thống kê từng cụm + chọn K |
| `GET /api/v1/ml/shipping/evaluation` | MAE/RMSE các model và feature importance |
| `POST /api/v1/ml/shipping/predict` | ngày giao dự đoán, chỉ khi có model ML2 |
| `GET /api/v1/ml/recommendations/evaluation` | kết quả đánh giá ML3 ở 2 protocol |

Chúng là kết quả **của một phiên bản mô hình huấn luyện trên bộ dữ liệu cố định**, không đổi khi người dùng điều chỉnh lọc tháng bên dashboard. `GET /api/v1/customers/rfm` (cũ) vẫn tính lại RFM theo khoảng tháng người dùng chọn — không nên lẫn với cụm ML1 đã train từ toàn bộ giai đoạn.

## 6. Kiểm tra chất lượng & diễn giải

- ML1: K-Means không có accuracy; trình bày silhouette, độ ổn định ARI và chân dung cụm; không mặc định cluster ID đại diện VIP.
- ML2: dữ liệu chỉ thuộc TP.HCM, không dùng ví dụ Hà Nội; RF không vượt baseline giao hàng, nên khối web trình bày minh bạch kết quả.
- ML3: sản phẩm chỉ có 15 loại; báo cáo thất bại có giá trị khoa học. Không xây đề xuất cá nhân hóa nếu chưa đánh giá có lợi ích.
- Chỉ nên ghi DB vào schema `ml` khi cần ML production/incremental. Gói web này **đọc CSV và model artifact** trong image, không tự thêm hoặc sửa schema DWH.
- Có thể commit CSV báo cáo nhỏ sau khi thống nhất với nhóm; tránh commit `.env`, dataset nhạy cảm hoặc model binary không rõ nguồn/quá lớn.

## 7. Nếu chưa hiển thị

1. Kiểm tra `GET /api/v1/ml/status`.
2. Kiểm tra `backend/ml_outputs/ml1/...` có file thật và có header đúng tên.
3. Build lại image `api`.
4. Đọc log `docker compose -f docker-compose.yml -f docker-compose.web.yml logs --tail=80 api`.
5. Nếu model ML2 không load do lệch phiên bản scikit-learn, notebook và Docker cần dùng phiên bản tương thích (không nạp file từ người lạ).
