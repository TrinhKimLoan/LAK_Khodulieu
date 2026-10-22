# Vietnam E-commerce DWH + Media Cloud — Docker Project

**Scope:** completed code up through Data Warehouse, schema/ops tables, Airflow DAG definitions. Frontend, dashboard API and ML models are NOT implemented; design in `docs/WEB_AND_ML.md`.

## Requirements
Docker Desktop + Docker Compose, 4–6GB free memory recommended if Airflow UI used, and internet for pulling images. No personal customer names/phone/address loaded. These are synthetic Excel transactions and real market news: comparing series does NOT establish causality.

## Quick start (PowerShell at the project directory)
```powershell
Copy-Item .env.example .env
# Edit .env: local DB password; optional MEDIACLOUD_API_KEY for live fetching
# Run locally, no Airflow required for first successful end-to-end DWH:
docker compose up -d postgres
docker compose --profile tools build pipeline
docker compose --profile tools run --rm pipeline python -m app.cli all-offline
```

This imports **the six included xlsx files** and 360 historical news rows from the provided `media_api_2024.csv` seed. Can run repeatedly: staged inserts are upserts; only newly discovered or changed articles emit change log rows. The historical seed is a demo/validation dataset, not verified coverage of 2020–2025. SQL creates schemas `raw`, `staging`, `dw`, `ops` and views.

## Verify (PowerShell)
```powershell
docker compose exec postgres psql -U ecom -d ecom_dwh -c "SELECT count(*) FROM dw.fact_sales;"
docker compose exec postgres psql -U ecom -d ecom_dwh -c "SELECT count(*) FROM dw.fact_news;"
docker compose exec postgres psql -U ecom -d ecom_dwh -c "SELECT * FROM dw.v_category_market_dashboard LIMIT 10;"
docker compose exec postgres psql -U ecom -d ecom_dwh -c "SELECT change_type,count(*) FROM ops.news_change_log GROUP BY 1;"
```
Change `ecom` values if you edited `.env` credentials. DB host on Windows `localhost:5433`; inside Docker Compose `postgres:5432`.

## Live Media Cloud fetch
Set `MEDIACLOUD_API_KEY` in `.env`, then:
```powershell
docker compose --profile tools run --rm pipeline python -m app.cli fetch-news
docker compose --profile tools run --rm pipeline python -m app.cli marts
docker compose --profile tools run --rm pipeline python -m app.cli validate
```
By default searches Jan/Apr/Jul/Oct 2024 (short test) across five product keyword groups. Use `.env`: `MEDIA_NEWS_YEAR=2026`, `MEDIA_NEWS_MONTHS=7,8,9,10`, `MEDIA_PER_QUERY=15` for a rolling demo. WARNING: this is a **sample** fetch, not full historical backfill or a guaranteed complete incremental feed. Production-grade polling needs reliable pagination, indexed-date watermarks, overlap and bounded backfills; results missing from a page must NEVER be interpreted as DELETES. Check API quotas before larger runs.

## Airflow schedule (optional)
```powershell
docker compose --profile scheduler up -d airflow
# Open http://localhost:8080
# First-time standalone admin password printed in container logs:
docker compose logs airflow
```
Unpause DAGs in Airflow UI AFTER offline bootstrap. `ecom_excel_refresh` weekly; `ecom_news_incremental` daily; `ecom_source_health` 6-hourly. The live DAG has the same limited sampling controls as manual API fetch; to capture current months edit `.env` and restart. Airflow standalone is a **single-container teaching setup** using SQLite metadata + SequentialExecutor; it is not HA/production. For robust deployments use Postgres metadata, separate scheduler/webserver/worker.

`ops.pipeline_runs` stores successful ingestion runs; Airflow retains failed attempts. Source health task checks HTTP reachability, with an optional webhook. Ingestion does not report `DELETE`: no authoritative API deletion feed exists. This is **snapshot-diff / polling-based change detection**, not transaction-log CDC. Kafka/Debezium are unnecessary for this bounded demo, and cannot retroactively access the upstream Media Cloud WAL.

## Check idempotency
Run `seed-news` again, check the new run log shows `unchanged` and INSERT/UPDATE counts 0. To demonstrate UPDATE on a copy, modify a seed article's title (same URL), import again, and check `ops.news_change_log`. Do not modify originals without backup. Title-only news matching is intentionally conservative and manual relevance review is still needed before using it for decisions.

## Tests without Docker
At repository root:
```powershell
py -m unittest discover -s tests -v
```
Tests use the stdlib and included Excel; Docker ETL needs external packages installed in its image.

## Known limitations and honest boundaries
- Source workbook stores a single `Ma_San_Pham` per `Ma_Don`, so `fact_sales` grain is order not line-item. This is dataset-specific, do not assert multi-line orders.
- Source data has no true inventory / COGS / ad spend / click history. `goods_amount` is gross goods value, `total_paid` includes VAT and shipping, and neither is net profit.
- News candidate `quality_status` comes from title heuristics (not verified relevance). Exclude suspicious lamdongtv.vn. Headlines about firms/share prices should not be assumed to describe retail product demand.
- Reporting news by multiple categories double-counts across categories intentionally. DISTINCT articles per category, do not sum across category for global unique total.
- News API data is real but Excel business transactions are synthetic; their co-movement is NOT evidence of causal influence.
- Privacy: customer names / phones / street addresses never copied into staging or mart in this demo.
- No description/full-text enrichment implemented; API fields provide title, date, URL, source.

## Project map
`data/excel/`: six source XLSX; `data/news_seed/`: sample API CSV + human review.
`config/category_rules.json`: editable keywords, exclusions and API queries for switching product sectors; `app/core.py`: ingest and transform; `app/cli.py`: CLI; `sql/001_schema.sql`: PostgreSQL warehouse; `dags/`: orchestration; `docs/WEB_AND_ML.md`: complete web endpoint / ML recommendations.

## Change the product industry
Edit `config/category_rules.json` to change category names, matching keywords, exclusions and Media Cloud queries. For a **different Excel dataset**, additionally update `load_excel()` column mapping in `app/core.py` and the order grain/schema: simply changing the keywords will not make arbitrary spreadsheets structurally compatible.

## Manual DWH integrity SQL
```sql
SELECT count(*) FROM staging.orders;
SELECT count(*) FROM dw.fact_sales;
SELECT year_month,category_code,goods_revenue FROM dw.v_monthly_sales ORDER BY year_month LIMIT 10;
SELECT quality_status,count(*) FROM dw.fact_news GROUP BY 1;
SELECT change_type,count(*) FROM ops.news_change_log GROUP BY 1;
```
