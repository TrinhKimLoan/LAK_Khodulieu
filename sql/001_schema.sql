CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS raw.excel_rows (source_file text NOT NULL, business_key text NOT NULL, payload jsonb NOT NULL, loaded_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(source_file,business_key));
CREATE TABLE IF NOT EXISTS staging.orders (order_id text PRIMARY KEY, customer_id text, product_id text, quantity numeric, shipping_type text, warehouse text, vehicle text, driver text, order_date date, shipped_date date, expected_date date, delivered_date date, goods_amount numeric, vat_amount numeric, shipping_fee numeric, total_paid numeric, city text, district text, delivery_days numeric);
CREATE TABLE IF NOT EXISTS staging.customers (customer_id text PRIMARY KEY, gender text, city text, district text);
CREATE TABLE IF NOT EXISTS staging.products (product_id text PRIMARY KEY, product_name text, product_group text, category_code text, unit_price numeric);
CREATE TABLE IF NOT EXISTS staging.news_articles (article_key text PRIMARY KEY, external_id text, title text NOT NULL, canonical_url text, source_domain text, published_date date NOT NULL, indexed_at timestamptz, category_codes text[] NOT NULL DEFAULT '{}', keyword_match bool NOT NULL DEFAULT false, quality_status text NOT NULL, record_hash text NOT NULL, first_seen_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS raw.news_snapshots (run_id text NOT NULL, article_key text NOT NULL, fetched_at timestamptz NOT NULL DEFAULT now(), payload jsonb NOT NULL, record_hash text NOT NULL, PRIMARY KEY(run_id,article_key));
CREATE TABLE IF NOT EXISTS ops.news_change_log (change_id bigserial PRIMARY KEY, run_id text NOT NULL, article_key text NOT NULL, change_type text NOT NULL CHECK(change_type IN ('INSERT','UPDATE')), detected_at timestamptz NOT NULL DEFAULT now(), previous_hash text, current_hash text NOT NULL);
CREATE TABLE IF NOT EXISTS ops.pipeline_runs (run_id text PRIMARY KEY, pipeline text NOT NULL, started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz, status text NOT NULL, records_count integer NOT NULL DEFAULT 0, message text);
CREATE TABLE IF NOT EXISTS dw.dim_date (date_key integer PRIMARY KEY, full_date date NOT NULL UNIQUE, year integer, quarter integer, month integer, year_month text);
CREATE TABLE IF NOT EXISTS dw.dim_customer (customer_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, customer_id text UNIQUE NOT NULL, gender text, city text, district text);
CREATE TABLE IF NOT EXISTS dw.dim_product (product_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, product_id text UNIQUE NOT NULL, product_name text, category_code text, product_group text, unit_price numeric);
CREATE TABLE IF NOT EXISTS dw.dim_news_source (source_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, domain text UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS dw.dim_category (category_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, category_code text UNIQUE NOT NULL, display_name text NOT NULL);
CREATE TABLE IF NOT EXISTS dw.fact_sales (order_id text PRIMARY KEY, date_key integer REFERENCES dw.dim_date(date_key), customer_key bigint REFERENCES dw.dim_customer(customer_key), product_key bigint REFERENCES dw.dim_product(product_key), quantity numeric, goods_amount numeric, vat_amount numeric, shipping_fee numeric, total_paid numeric, delivery_days numeric, shipping_type text, city text);
CREATE TABLE IF NOT EXISTS dw.fact_news (article_key text PRIMARY KEY, date_key integer REFERENCES dw.dim_date(date_key), source_key bigint REFERENCES dw.dim_news_source(source_key), title text, url text, quality_status text, last_seen_at timestamptz);
CREATE TABLE IF NOT EXISTS dw.bridge_news_category (article_key text REFERENCES dw.fact_news(article_key) ON DELETE CASCADE, category_key bigint REFERENCES dw.dim_category(category_key), PRIMARY KEY(article_key,category_key));
CREATE INDEX IF NOT EXISTS idx_sales_date ON dw.fact_sales(date_key);
CREATE INDEX IF NOT EXISTS idx_sales_product ON dw.fact_sales(product_key);
CREATE INDEX IF NOT EXISTS idx_news_date ON dw.fact_news(date_key);
CREATE INDEX IF NOT EXISTS idx_news_source ON dw.fact_news(source_key);
CREATE OR REPLACE VIEW dw.v_monthly_sales AS SELECT d.year_month, p.category_code, count(*)::integer order_count, sum(s.quantity) units, sum(s.goods_amount) goods_revenue, sum(s.total_paid) gross_collected, avg(s.delivery_days) avg_delivery_days FROM dw.fact_sales s JOIN dw.dim_date d ON d.date_key=s.date_key JOIN dw.dim_product p ON p.product_key=s.product_key GROUP BY d.year_month,p.category_code;
CREATE OR REPLACE VIEW dw.v_monthly_news AS SELECT d.year_month,c.category_code,count(DISTINCT n.article_key)::integer article_count,count(DISTINCT n.source_key)::integer source_count FROM dw.fact_news n JOIN dw.dim_date d ON d.date_key=n.date_key JOIN dw.bridge_news_category b ON b.article_key=n.article_key JOIN dw.dim_category c ON c.category_key=b.category_key WHERE n.quality_status='candidate' GROUP BY d.year_month,c.category_code;
CREATE OR REPLACE VIEW dw.v_category_market_dashboard AS SELECT x.year_month,x.category_code,x.order_count,x.units,x.goods_revenue,x.gross_collected,x.avg_delivery_days,coalesce(n.article_count,0) article_count,coalesce(n.source_count,0) source_count FROM dw.v_monthly_sales x LEFT JOIN dw.v_monthly_news n ON n.year_month=x.year_month AND n.category_code=x.category_code;

-- Tracks covered historical months. PARTIAL_PAGE_CAP means some API pagination remains.
CREATE TABLE IF NOT EXISTS ops.news_backfill_months (
 year integer NOT NULL, month integer NOT NULL CHECK(month BETWEEN 1 AND 12),
 status text NOT NULL, config_signature text NOT NULL,
 run_id text, raw_rows integer NOT NULL DEFAULT 0,
 group_stats jsonb, completed_at timestamptz,
 PRIMARY KEY(year,month)
);

-- Relevance classification is analytical enrichment, not CDC of source metadata.
ALTER TABLE staging.news_articles ADD COLUMN IF NOT EXISTS relevance_level text;
ALTER TABLE staging.news_articles ADD COLUMN IF NOT EXISTS relevance_reason text;
ALTER TABLE dw.fact_news ADD COLUMN IF NOT EXISTS relevance_level text;
ALTER TABLE dw.fact_news ADD COLUMN IF NOT EXISTS relevance_reason text;
CREATE INDEX IF NOT EXISTS idx_news_relevance ON staging.news_articles(relevance_level);
