# V3 — Lọc tin theo mức độ liên quan (không NLP, không gọi lại Media Cloud)

## Tại sao cần sửa?
V2 chỉ xét có từ khóa trong tiêu đề và nguồn có bị nghi ngờ hay không. Ví dụ “WiFi giả ở sân bay” dễ bị tính là tin ngành thiết bị mạng; tiêu đề “Galaxy ... GPU” có thể bị nhận là card đồ họa PC. Các bài trùng tiêu đề nhưng khác URL **không** bị loại khi chỉ khử trùng theo URL.

## Kết quả V3
- `DIRECT`: tin trực tiếp về sản phẩm / thị trường linh kiện, hiển thị mặc định (`quality_status='candidate'`).
- `INDIRECT`: tin liên quan gián tiếp, giữ trong dữ liệu, không lên dashboard mặc định.
- `IRRELEVANT`: tin không phù hợp, giữ lại trong raw/staging để kiểm toán.
- `relevance_reason`: lý do bằng mã có thể giải thích.
- Phân loại dựa vào tiêu đề, không đọc toàn văn và KHÔNG khẳng định chính xác tuyệt đối.

## Cài đặt trên project hiện có (PowerShell)
1. `cd D:\vietnam_ecom_dwh_project`
2. **Sao lưu** PostgreSQL trước khi áp dụng:
   `docker compose exec postgres pg_dump -U ecom -d ecom_dwh -Fc -f /tmp/backup_before_relevance_v3.dump`
   `docker cp "$(docker compose ps -q postgres):/tmp/backup_before_relevance_v3.dump" .\backup_before_relevance_v3.dump`
3. Giải nén ZIP bản vá vào `D:\vietnam_ecom_dwh_project` (ghi đè file trùng tên). **Không** xóa `.env`, `data`, volume; **không** `docker compose down -v`.
4. Tránh chạy DAG news cùng lúc áp dụng: `docker compose --profile scheduler stop airflow` (nếu service hiện đang chạy).
5. `docker compose --profile tools build pipeline`
6. `docker compose --profile tools run --rm pipeline python -m app.cli bootstrap`
7. `docker compose --profile tools run --rm pipeline python -m app.cli reclassify-news`
8. `docker compose --profile tools run --rm pipeline python -m app.cli marts`
9. `docker compose --profile tools run --rm pipeline python -m app.cli validate`
10. Bật lại Airflow (nếu đã dừng): `docker compose --profile scheduler up -d airflow`

Các bước 6–9 không gọi lại Media Cloud, không tái tải Excel, không xóa snapshot và không chèn sự kiện giả vào bảng CDC (`ops.news_change_log`). Cơ chế nạp API những lần sau vẫn đọc quy tắc mới vì `app/core.py` đã cập nhật.

## Kiểm tra trong PostgreSQL

```
docker compose exec postgres psql -P pager=off -U ecom -d ecom_dwh -c "SELECT relevance_level, quality_status, COUNT(*) FROM staging.news_articles GROUP BY 1,2 ORDER BY 1,2;"

docker compose exec postgres psql -P pager=off -U ecom -d ecom_dwh -c "SELECT published_date,title,relevance_level,relevance_reason,category_codes FROM staging.news_articles WHERE title ILIKE '%camera%' ORDER BY published_date DESC LIMIT 20;"

docker compose exec postgres psql -P pager=off -U ecom -d ecom_dwh -c "SELECT c.category_code, COUNT(DISTINCT b.article_key) AS direct_articles FROM dw.bridge_news_category b JOIN dw.dim_category c ON c.category_key=b.category_key JOIN dw.fact_news n ON n.article_key=b.article_key WHERE n.quality_status='candidate' GROUP BY 1 ORDER BY 2 DESC;"

docker compose exec postgres psql -P pager=off -U ecom -d ecom_dwh -c "SELECT change_type, COUNT(*) FROM ops.news_change_log GROUP BY 1;"
```

## Các giới hạn quan trọng
1. Rule-based chỉ là phiên bản đầu; cần gán nhãn mẫu 100–200 bài để đo **precision của DIRECT và recall đối với các bài thật sự có ích**. Đừng đánh giá chỉ bằng số ứng viên.
2. Trùng tiêu đề/ngày khác URL vẫn có thể tồn tại trong PostgreSQL; nên chỉ hiển thị mỗi cụm tiêu đề/ngày một lần tại web. Không xóa raw hoặc sửa CDC log tùy tiện.
3. `reclassify-news` giữ `raw.news_snapshots` và `ops.news_change_log` nguyên trạng. Cột `record_hash` trên staging được đồng bộ theo bộ quy tắc mới để lần API sau không sinh UPDATE giả chỉ do đổi thuật toán phân loại. Nếu muốn mô hình CDC học thuật thuần chỉ phát hiện thay đổi từ nguồn, tách riêng source hash và enrichment hash là cải tiến kiến trúc tiếp theo.
4. V3 không tác động `PARTIAL_PAGE_CAP`: các tháng bị giới hạn phân trang vẫn là một vấn đề độc lập.
5. Bản vá có thay đổi `app/core.py`, `app/cli.py`, `sql/001_schema.sql`; nên sao lưu project/mã nguồn trước khi giải nén. Airflow mount source `./app` nên sẽ tự thấy code mới khi bật lại.
