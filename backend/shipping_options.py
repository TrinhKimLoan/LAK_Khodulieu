"""Read-only options taken from the actual warehouse for ML demo input controls."""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException
router=APIRouter(prefix='/api/v1/shipping',tags=['Shipping'])
@router.get('/prediction-options')
def prediction_options():
    columns={'shipping_type':'shipping_type','product_id':'product_id','district':'district','warehouse':'warehouse','vehicle':'vehicle'}
    data={}
    try:
        with psycopg2.connect(host=os.getenv('DB_HOST','postgres'),port=os.getenv('DB_PORT','5432'),dbname=os.getenv('POSTGRES_DB','ecom_dwh'),user=os.getenv('POSTGRES_USER','ecom'),password=os.getenv('POSTGRES_PASSWORD',''),connect_timeout=5, options='-c statement_timeout=6000') as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('BEGIN READ ONLY')
                for key,col in columns.items():
                    cur.execute(f"SELECT DISTINCT {col}::text AS value FROM staging.orders WHERE {col} IS NOT NULL AND {col}::text <> '' ORDER BY 1 LIMIT 250")
                    data[key]=[r['value'] for r in cur.fetchall()]
    except psycopg2.Error as exc:
        raise HTTPException(503,'Không đọc được danh sách lựa chọn từ staging.orders') from exc
    return {'options':data,'city':'TP Hồ Chí Minh','source':'staging.orders'}
