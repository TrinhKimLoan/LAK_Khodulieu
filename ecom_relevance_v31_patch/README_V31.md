# V3.1 relevance hotfix (CAMERA phone/car false positives)

This patch replaces only `app/relevance.py` and adds `tests/test_relevance.py`. Apply to V3, **not** initial V2.

Changes:
- `CAMERA` posts mentioning phones and their embedded cameras, or cars/motorbikes and dashcams, are excluded from CAMERA market categorization.
- Retains direct security/retail cameras and webcams.
- Retains the V3 classification API. Other categories unchanged except RAM-phone hints become INDIRECT.
- The classifier is still title-based rules, not a guarantee of accuracy. Test with labeled samples.

Windows PowerShell, from project root:
1. Optionally stop Airflow to avoid concurrent ingestion:
   `docker compose --profile scheduler stop airflow`
2. Copy patch files over project files (keep env and Docker volumes).
3. `docker compose --profile tools build pipeline`
4. `docker compose --profile tools run --rm pipeline python -m app.cli reclassify-news`
5. `docker compose --profile tools run --rm pipeline python -m app.cli marts`
6. `docker compose --profile tools run --rm pipeline python -m app.cli validate`
7. `docker compose --profile scheduler up -d airflow`

Verify:
`docker compose exec postgres psql -P pager=off -U ecom -d ecom_dwh -c "SELECT title,relevance_level,category_codes FROM staging.news_articles WHERE title ILIKE '%OPPO Find X10%' LIMIT 5;"`

`docker compose exec postgres psql -P pager=off -U ecom -d ecom_dwh -c "SELECT COUNT(*) AS staging_direct FROM staging.news_articles WHERE relevance_level='DIRECT';"`

`docker compose exec postgres psql -P pager=off -U ecom -d ecom_dwh -c "SELECT COUNT(*) AS dw_direct FROM dw.fact_news WHERE relevance_level='DIRECT';"`

`docker compose exec postgres psql -P pager=off -U ecom -d ecom_dwh -c "SELECT COUNT(*) FROM dw.bridge_news_category b JOIN dw.fact_news n USING(article_key) WHERE n.relevance_level<>'DIRECT';"`

Note bridge is currently populated for all levels; default web queries MUST filter `n.relevance_level='DIRECT'`, and count DISTINCT article_key if joining multiple categories. Category bridge counts can sum beyond direct article totals.

Reclassification changes analytics metadata; don't add artificial source CDC UPDATE log entries. Source CDC log pertains to media metadata changes.
