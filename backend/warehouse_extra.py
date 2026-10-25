"""Read-only warehouse breakdowns. Group by known columns only."""
import os
from fastapi import APIRouter, Query, HTTPException
import psycopg2
from psycopg2.extras import RealDictCursor

router=APIRouter(prefix='/api/v1/shipping',tags=['Shipping drilldown'])
@router.get('/warehouse-performance')
def warehouse_performance(start:str=Query('2020-01',alias='from',pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),end:str=Query('2025-12',alias='to',pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),group_by:str='warehouse'):
    if group_by not in ('warehouse','vehicle','shipping_type'):raise HTTPException(422,'group_by phải là warehouse, vehicle hoặc shipping_type')
    if start>end:raise HTTPException(422,'Khoảng tháng không hợp lệ')
    # warehouse, vehicle are in staging.orders, which remains the source-of-truth for logistics fields.
    sql=f'''SELECT COALESCE(NULLIF(o.{group_by}::text,''),'UNKNOWN') group_name,
      COUNT(*)::int order_count, ROUND(AVG(o.delivery_days)::numeric,2) avg_delivery_days,
      ROUND(AVG(o.shipping_fee)::numeric,2) avg_shipping_fee,
      COUNT(*) FILTER(WHERE o.delivery_days IS NULL)::int missing_delivery_days
      FROM staging.orders o WHERE o.order_date >= to_date(%s || '-01','YYYY-MM-DD')
      AND o.order_date < (to_date(%s || '-01','YYYY-MM-DD') + INTERVAL '1 month')
      GROUP BY 1 ORDER BY order_count DESC'''
    try:
        with psycopg2.connect(host=os.getenv('DB_HOST','postgres'),port=os.getenv('DB_PORT','5432'),dbname=os.getenv('POSTGRES_DB','ecom_dwh'),user=os.getenv('POSTGRES_USER','ecom'),password=os.getenv('POSTGRES_PASSWORD',''),connect_timeout=5) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('BEGIN READ ONLY')
                cur.execute(sql,(start,end))
                data=cur.fetchall()
        for x in data:
            for k,v in x.items():
                if hasattr(v,'as_tuple'):x[k]=float(v)
        return {'group_by':group_by,'period':{'from':start,'to':end},'items':data}
    except psycopg2.Error as exc:
        raise HTTPException(503,f'Warehouse source unavailable ({exc.pgcode or "connection"})') from exc
