"""Read-only product prices for demo order value calculation."""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException
router=APIRouter(prefix='/api/v1/products', tags=['Products'])
@router.get('/unit-prices')
def unit_prices():
    try:
        with psycopg2.connect(host=os.getenv('DB_HOST','postgres'),port=os.getenv('DB_PORT','5432'),dbname=os.getenv('POSTGRES_DB','ecom_dwh'),user=os.getenv('POSTGRES_USER','ecom'),password=os.getenv('POSTGRES_PASSWORD',''),connect_timeout=5,options='-c statement_timeout=6000') as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('BEGIN READ ONLY')
                cur.execute('SELECT product_id, product_name, unit_price FROM dw.dim_product ORDER BY product_id')
                result=[]
                for r in cur.fetchall():
                    result.append({'product_id':r['product_id'],'product_name':r['product_name'],'unit_price':float(r['unit_price']) if r['unit_price'] is not None else None})
                return {'items':result, 'note':'Reference price from dw.dim_product, not necessarily historical transaction price.'}
    except psycopg2.Error as ex:
        raise HTTPException(503,'Không đọc được bảng giá sản phẩm') from ex
