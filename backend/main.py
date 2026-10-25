"""EcomInsight read-only dashboard API for existing dw/ops PostgreSQL schema.

All queries use bound SQL parameters. No credentials returned to the browser.
No ML estimates are fabricated: segments endpoint returns 501 until ML table exists.
"""
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="EcomInsight Dashboard API", version="0.1.0", description="Read-only Data Warehouse endpoints")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if x.strip()], allow_credentials=False, allow_methods=["GET"], allow_headers=["*"])


def connection():
    return psycopg2.connect(host=os.getenv('DB_HOST','localhost'),port=int(os.getenv('DB_PORT','5433')), user=os.getenv('POSTGRES_USER','ecom'),password=os.getenv('POSTGRES_PASSWORD',''),dbname=os.getenv('POSTGRES_DB','ecom_dwh'), connect_timeout=5, options='-c statement_timeout=12000')


def norm_value(value):
    if isinstance(value, Decimal): return float(value)
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, list): return [norm_value(v) for v in value]
    if isinstance(value, dict): return {k:norm_value(v) for k,v in value.items()}
    return value


def sql_all(query, params=()):
    try:
        with connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("BEGIN READ ONLY")
                cur.execute(query, params)
                return [norm_value(dict(row)) for row in cur.fetchall()]
    except psycopg2.Error as exc:
        raise HTTPException(status_code=503, detail=f"Database query failed ({exc.pgcode or 'connection'}). Check schema or API DB settings.") from exc


def sql_one(query, params=()):
    rows=sql_all(query,params)
    return rows[0] if rows else None


def months(start:str, end:str):
    if start>end: raise HTTPException(422, "from must be <= to")
    return start,end

Month = str  # YYYY-MM validation via FastAPI regex Query arguments.

@app.get('/health')
def health():
    return {'status':'ok','db':sql_one('SELECT 1 AS connected')['connected'] == 1}

@app.get('/api/v1/categories')
def categories():
    return sql_all('''SELECT p.category_code, COUNT(*)::int AS product_count FROM dw.dim_product p GROUP BY p.category_code ORDER BY p.category_code''')

@app.get('/api/v1/overview')
def overview(start: str = Query('2020-01',alias='from',pattern=r'^\d{4}-(0[1-9]|1[0-2])$'), end: str=Query('2025-12',alias='to',pattern=r'^\d{4}-(0[1-9]|1[0-2])$')):
    start,end=months(start,end)
    kpi=sql_one('''SELECT COUNT(*)::int AS order_count, COUNT(DISTINCT c.customer_id)::int AS customer_count,
    COALESCE(SUM(s.quantity),0) AS units, COALESCE(SUM(s.goods_amount),0) AS goods_revenue,
    COALESCE(SUM(s.total_paid),0) AS total_paid,
    COALESCE(AVG(s.total_paid),0) AS aov_paid
    FROM dw.fact_sales s JOIN dw.dim_date d ON d.date_key=s.date_key
    JOIN dw.dim_customer c ON c.customer_key=s.customer_key
    WHERE d.year_month BETWEEN %s AND %s''',(start,end))
    trend=sql_all('''SELECT d.year_month AS month, COUNT(*)::int order_count,
    COALESCE(SUM(s.goods_amount),0) AS goods_revenue, COALESCE(SUM(s.total_paid),0) AS total_paid
    FROM dw.fact_sales s JOIN dw.dim_date d ON d.date_key=s.date_key
    WHERE d.year_month BETWEEN %s AND %s GROUP BY 1 ORDER BY 1''',(start,end))
    category=sql_all('''SELECT p.category_code, COUNT(*)::int AS order_count, SUM(s.quantity) AS units,
    SUM(s.goods_amount) AS goods_revenue FROM dw.fact_sales s
    JOIN dw.dim_product p ON p.product_key=s.product_key JOIN dw.dim_date d ON d.date_key=s.date_key
    WHERE d.year_month BETWEEN %s AND %s GROUP BY 1 ORDER BY goods_revenue DESC''',(start,end))
    return {'period':{'from':start,'to':end},'currency':'VND','kpis':kpi,'monthly':trend,'categories':category,'note':'goods_revenue is product goods amount, not profit; total_paid includes VAT/shipping'}

@app.get('/api/v1/products/top')
def top_products(start: str = Query('2020-01',alias='from',pattern=r'^\d{4}-(0[1-9]|1[0-2])$'), end: str=Query('2025-12',alias='to',pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),category:str|None=None, metric:Literal['revenue','units']='revenue',limit:int=Query(10,ge=1,le=100)):
    start,end=months(start,end)
    rows=sql_all('''SELECT p.product_id,p.product_name,p.product_group,p.category_code,
    COUNT(*)::int order_count,SUM(s.quantity) AS units,SUM(s.goods_amount) AS goods_revenue,
    AVG(s.goods_amount) AS avg_order_goods_amount
    FROM dw.fact_sales s JOIN dw.dim_product p ON p.product_key=s.product_key
    JOIN dw.dim_date d ON d.date_key=s.date_key
    WHERE d.year_month BETWEEN %s AND %s AND (%s IS NULL OR p.category_code=%s)
    GROUP BY p.product_id,p.product_name,p.product_group,p.category_code
    ORDER BY CASE WHEN %s='units' THEN SUM(s.quantity) ELSE SUM(s.goods_amount) END DESC
    LIMIT %s''',(start,end,category,category,metric,limit))
    return {'period':{'from':start,'to':end},'metric':metric,'items':rows}

@app.get('/api/v1/customers/rfm')
def customer_rfm(start: str=Query('2020-01',alias='from',pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),end: str=Query('2025-12',alias='to',pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0)):
    start,end=months(start,end)
    # Reference date = day after most recent transaction in selected period (not today's date).
    rows=sql_all('''WITH base AS (
      SELECT c.customer_id,d.full_date,s.goods_amount FROM dw.fact_sales s
      JOIN dw.dim_customer c ON c.customer_key=s.customer_key
      JOIN dw.dim_date d ON d.date_key=s.date_key WHERE d.year_month BETWEEN %s AND %s
    ), reference AS (SELECT MAX(full_date)+1 AS as_of FROM base)
    SELECT b.customer_id,(r.as_of-MAX(b.full_date))::int AS recency_days,
       COUNT(*)::int AS frequency, SUM(b.goods_amount) AS monetary
    FROM base b CROSS JOIN reference r GROUP BY b.customer_id,r.as_of
    ORDER BY monetary DESC LIMIT %s OFFSET %s''',(start,end,limit,offset))
    return {'period':{'from':start,'to':end},'items':rows,'note':'Raw RFM features, NOT K-Means segment predictions; train model separately'}

@app.get('/api/v1/customers/segments')
def customer_segments():
    raise HTTPException(status_code=501,detail='Customer segments not trained/persisted yet. Use /api/v1/customers/rfm for features; create ml.customer_segments after training.')

@app.get('/api/v1/shipping/performance')
def shipping(start: str=Query('2020-01',alias='from',pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),end: str=Query('2025-12',alias='to',pattern=r'^\d{4}-(0[1-9]|1[0-2])$'), group_by:Literal['city','shipping_type']='city',limit:int=Query(50,ge=1,le=100)):
    start,end=months(start,end)
    # Explicit branch instead of interpolating arbitrary SQL identifiers.
    group_expr='s.city' if group_by=='city' else 's.shipping_type'
    q=f'''SELECT COALESCE({group_expr},'UNKNOWN') AS group_name,
       COUNT(*)::int AS order_count,ROUND(AVG(s.delivery_days)::numeric,2) AS avg_delivery_days,
       ROUND(AVG(s.shipping_fee)::numeric,2) AS avg_shipping_fee,
       COUNT(*) FILTER (WHERE s.delivery_days IS NULL)::int AS missing_delivery_days
       FROM dw.fact_sales s JOIN dw.dim_date d ON d.date_key=s.date_key
       WHERE d.year_month BETWEEN %s AND %s GROUP BY 1 ORDER BY order_count DESC LIMIT %s'''
    return {'period':{'from':start,'to':end},'group_by':group_by,'items':sql_all(q,(start,end,limit)),'note':'Cannot label late deliveries without promised-date SLA definition; avg_delivery_days is observed time only.'}

@app.get('/api/v1/market/articles')
def market_articles(category:str|None=None,level:Literal['DIRECT','INDIRECT','ALL']='DIRECT',start: str=Query('2020-01',alias='from',pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),end: str=Query('2025-12',alias='to',pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),page:int=Query(1,ge=1),limit:int=Query(20,ge=1,le=100)):
    start,end=months(start,end)
    offset=(page-1)*limit
    # DISTINCT via EXISTS ensures an article is returned once even if category-matched multiple times.
    query='''SELECT n.article_key,n.title,n.url,src.domain AS source,d.full_date AS published_date,
       n.quality_status,n.relevance_level
       FROM dw.fact_news n JOIN dw.dim_date d ON d.date_key=n.date_key
       JOIN dw.dim_news_source src ON src.source_key=n.source_key
       WHERE d.year_month BETWEEN %s AND %s
       AND (%s='ALL' OR n.relevance_level=%s)
       AND (%s IS NULL OR EXISTS(
            SELECT 1 FROM dw.bridge_news_category b JOIN dw.dim_category c ON c.category_key=b.category_key
            WHERE b.article_key=n.article_key AND c.category_code=%s))
       ORDER BY d.full_date DESC,n.article_key LIMIT %s OFFSET %s'''
    rows=sql_all(query,(start,end,level,level,category,category,limit,offset))
    count=sql_one('''SELECT COUNT(*)::int AS total FROM dw.fact_news n JOIN dw.dim_date d ON d.date_key=n.date_key
       WHERE d.year_month BETWEEN %s AND %s AND (%s='ALL' OR n.relevance_level=%s)
       AND (%s IS NULL OR EXISTS(SELECT 1 FROM dw.bridge_news_category b JOIN dw.dim_category c ON c.category_key=b.category_key WHERE b.article_key=n.article_key AND c.category_code=%s))''',(start,end,level,level,category,category))
    return {'category':category,'level':level,'period':{'from':start,'to':end},'page':page,'limit':limit,'total':count['total'],'items':rows,'note':'Rule-based relevance on headlines; open original article URL for complete context'}

@app.get('/api/v1/market/compare')
def market_compare(category:str=Query(...,min_length=1),start: str=Query('2020-01',alias='from',pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),end: str=Query('2025-12',alias='to',pattern=r'^\d{4}-(0[1-9]|1[0-2])$')):
    start,end=months(start,end)
    rows=sql_all('''SELECT year_month AS month,category_code,order_count,units,goods_revenue,gross_collected,avg_delivery_days,article_count,source_count
       FROM dw.v_category_market_dashboard
       WHERE category_code=%s AND year_month BETWEEN %s AND %s ORDER BY year_month''',(category,start,end))
    return {'category':category,'period':{'from':start,'to':end},'currency':'VND','series':rows,'note':'Sales are simulated; news is real; temporal co-occurrence does not imply impact or causation.'}

@app.get('/api/v1/pipeline/runs')
def pipeline_runs(limit:int=Query(30,ge=1,le=100),pipeline:str|None=None):
    rows=sql_all('''SELECT run_id,pipeline,status,started_at,finished_at,records_count,message FROM ops.pipeline_runs
       WHERE (%s IS NULL OR pipeline=%s) ORDER BY started_at DESC LIMIT %s''',(pipeline,pipeline,limit))
    summary=sql_all('''SELECT change_type,COUNT(*)::int AS events FROM ops.news_change_log GROUP BY change_type ORDER BY change_type''')
    backfill=sql_all('''SELECT status,COUNT(*)::int AS months FROM ops.news_backfill_months GROUP BY status ORDER BY status''')
    return {'runs':rows,'change_counts':summary,'historical_backfill':backfill,'note':'Airflow own task status is stored in its separate metadata DB; this endpoint shows pipeline-recorded runs only.'}

# Serve the dashboard from the same origin as the API (no Node server/CORS needed).
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
app.mount('/static', StaticFiles(directory='static'), name='static')

@app.get('/', include_in_schema=False)
def dashboard_index():
    return FileResponse('static/index.html')

from ml_api import router as ml_router
app.include_router(ml_router)

# EcomInsight UI upgrade routes
from warehouse_extra import router as warehouse_router
app.include_router(warehouse_router)

# EcomInsight V5 addons
from health_local import router as health_router
from shipping_options import router as shipping_options_router
app.include_router(health_router)
app.include_router(shipping_options_router)

# EcomInsight V6 health endpoint
from health_v6 import router as health_router_v6
app.include_router(health_router_v6)

from product_prices_v7 import router as prices_router_v7
app.include_router(prices_router_v7)
