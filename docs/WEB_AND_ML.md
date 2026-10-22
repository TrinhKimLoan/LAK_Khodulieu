# Web dashboard / API contract (implementation roadmap, web not included)

## Architecture
Browser (React/Next or Streamlit) -> backend FastAPI (read-only) -> PostgreSQL `dw` views/facts. NEVER connect a browser directly to the Docker DB, and do not ship DB credentials client-side. FastAPI Docker would use `postgres:5432`; host-local backend would use `127.0.0.1:5433`.

Recommended query parameters: `from=2024-01&to=2024-12&category=GPU`, limit/pagination on article lists. Return units and `data_as_of` in JSON. Use prepared statements, 100 records max per page, DB account with SELECT on `dw`/safe `ops` views only.

| Page | Questions answered | Proposed endpoint | DB source |
|--|--|--|--|
| Overview | How much did we sell, where, and when? | `GET /api/v1/overview?from=2024-01&to=2024-12` | `dw.fact_sales` + `dw.dim_date` |
| Sales | Which product categories contribute to goods revenue? | `GET /api/v1/sales/trends?category=GPU&group_by=month` | `dw.v_monthly_sales` |
| Products | Top products by units/revenue? | `GET /api/v1/products/top?metric=goods_revenue&limit=10` | `dw.fact_sales` + `dw.dim_product` |
| Customers | What are RFM segments and their spend? | `GET /api/v1/customers/segments` | derived RFM/ML result table (not yet populated) |
| Shipping | Which shipping types/cities have long delivery times? | `GET /api/v1/shipping/performance?city=...` | `dw.fact_sales` |
| Market Intel | What relevant articles appeared for our category this month? | `GET /api/v1/market/articles?category=GPU&month=2024-07&page=1` | `dw.fact_news` + `dw.bridge_news_category` |
| Market comparison | How did revenue/units and article volume vary together? | `GET /api/v1/market/compare?category=GPU&from=2024-01&to=2024-12` | `dw.v_category_market_dashboard` |
| Pipeline monitor | Did API poll, CDC and refresh succeed? | `GET /api/v1/pipeline/runs?limit=20` | `ops.pipeline_runs` |
| Change log | How many inserted/updated news articles? | `GET /api/v1/pipeline/changes?from=...` | `ops.news_change_log` |

The APIs above are an implementation SPEC, not endpoints already running. The included deliverable stops at the Data Warehouse. Suggestions like inventory liquidation, repricing or purchase quantities require data on inventory, costs, price history and reliable demand estimates NOT present in the six workbooks.

## Recommended 3 ML tasks

1. **Customer RFM + K-Means**: multiple orders per customer, amount and dates permit recency/frequency/monetary features. Standardize/log-transform; compare k via silhouette, stability; explain cluster business meaning. K-Means suitable for numeric unsupervised segments; supervised models require an observed ground-truth segment label. Note: transactions are simulated, and customer file's aggregate counts are not assumed to be consistent with transaction-derived RFM.
2. **Delivery time regression**: target observed `delivery_days` (pack date to receipt), features shipping type, city, product size, quantity, warehouse, vehicle. Train chronological holdout where feasible and compare simple median baseline / linear model versus RandomForestRegressor. Random forest captures nonlinear category interactions without imposing a linear relationship. Critical: **exclude any actual post-delivery fields and target-leaking promised/received date from features**; ensure timestamps represent planning stage realistically. Report MAE and holdout error, and check simulated time distributions.
3. **Item recommendation from purchases**, after checking co-purchase diversity: implicit user–item matrix `customer_id × product_id` with weighted counts or binary purchased flags. Test item-item cosine similarity with popularity baseline and held-out interactions; if sparsity makes collaborative filtering uninformative (only 15 products), use category / attribute similarity and explain limitations. No view/click history required. Never claim there is behavior browsing data.

Avoid: sentiment predicting synthetic sales (no causal link); supervised churn without labels and horizon; inventory optimization without inventory; true margin/profit prediction without costs; personalized click-through prediction with no clicks.

## Source lineage and ML scope
Excel six sheets -> raw / staging -> `fact_sales` + dimensions.
Media Cloud -> JSON snapshots / staging + change log -> `fact_news`, source/category dimensions + bridge.
Aggregating at `month + category` prevents multiplying sales by article counts. One fact_news article can map to multiple categories; count DISTINCT article_key for news volume.

## Future API sample (for backend implementation)
`GET /api/v1/market/compare?category=GPU&from=2024-01&to=2024-03`
```json
{"category":"GPU","currency":"VND","series":[{"month":"2024-01","goods_revenue":0,"units":0,"article_count":0}],"note":"numbers shown only as response shape"}
```
