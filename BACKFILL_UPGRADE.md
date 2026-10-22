# Upgrade v2 — historical Media Cloud 2020–2025

## Important
- Replace **app/core.py**, **app/cli.py**, **sql/001_schema.sql**, **docker-compose.yml** from this update. **Keep your existing .env, data, and Docker volumes**. No `down -v`.
- Merge new options into existing `.env` (see `.env.example`). Remove obsolete `MEDIA_NEWS_YEAR`, `MEDIA_NEWS_MONTHS`, `MEDIA_PER_QUERY`.
- Backfill covers every month 2020–2025; query results can still be incomplete if capped, or source indexing is incomplete.
- API calls are deliberately throttled to 32s; historical loading can take hours and quota may require multiple runs.

## Commands (PowerShell in project root)
```powershell
docker compose --profile scheduler stop airflow
# replace project files, add env options
docker compose --profile tools build pipeline
docker compose --profile tools run --rm pipeline python -m app.cli bootstrap
docker compose --profile tools run --rm pipeline python -m app.cli backfill-month --year 2020 --month 1
docker compose --profile tools run --rm pipeline python -m app.cli marts
docker compose --profile tools run --rm pipeline python -m app.cli validate
# next, run all history, resuming completed months automatically
docker compose --profile tools run --rm pipeline python -m app.cli backfill-range --start-year 2020 --end-year 2025
docker compose --profile tools run --rm pipeline python -m app.cli marts
docker compose --profile scheduler up -d --build --force-recreate airflow
```

## Completeness vs sampling
Default `MEDIA_PAGE_SIZE=100`, `MEDIA_MAX_PAGES_PER_QUERY=2` means up to 200 results **per query per month**, not exhaustive. Partial months recorded as `PARTIAL_PAGE_CAP`. Set `MEDIA_MAX_PAGES_PER_QUERY=0` for unlimited pagination, subject to time/quota, or increase cap gradually. Refresh config by restarting/rebuilding containers and rerun. Only `COMPLETE` months with same config are skipped.

## Monitor PostgreSQL
```powershell
docker compose exec postgres psql -U ecom -d ecom_dwh -c "SELECT min(full_date),max(full_date) FROM dw.dim_date;"
docker compose exec postgres psql -U ecom -d ecom_dwh -c "SELECT extract(year from published_date)::int AS year,count(*) FROM staging.news_articles GROUP BY 1 ORDER BY 1;"
docker compose exec postgres psql -U ecom -d ecom_dwh -c "SELECT year,status,count(*) FROM ops.news_backfill_months GROUP BY 1,2 ORDER BY 1,2;"
docker compose exec postgres psql -U ecom -d ecom_dwh -c "SELECT change_type,count(*) FROM ops.news_change_log GROUP BY 1;"
```

## Airflow metadata vs warehouse
`sqlite:////opt/airflow/state/airflow.db` stores **Airflow's job metadata only**; the project pipeline uses DB_HOST=postgres, DB_PORT=5432 and PostgreSQL schemas raw/staging/dw/ops for source records, snapshots, change logs and data warehouse. SQLite is not used for news CDC.

## DAG behavior
`ecom_news_incremental` fetches a **rolling 45-day window** daily and upserts to staging. Historical `backfill-range` is deliberately an explicit batch command, not a scheduled daily DAG; it avoids 72 months of costly requests per daily run. After backfill, refresh marts. Existing scheduled DAGs stay separate.

## Limitations
- Media Cloud contains late-indexed articles; long backfill range and 45-day lookback are not a strict guarantee of completeness.
- The model does not classify industry event types or claim business impact, and query groups are independent of relevance filtering by title.
- One run fetches entire month into RAM then commits. It can resume **by month** after failure, not within an unfinished month.
- News absent from one query is **not** a DELETE event.
- Changing year ranges does not retroactively guarantee articles in all categories/months; check coverage by category.
