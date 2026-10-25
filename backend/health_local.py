"""Demo-only local health checks: same-origin header + hostname gate and cooldown.

This route deliberately does not authenticate users. Do not expose it to the Internet.
"""
import os, time, threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from fastapi import APIRouter, HTTPException, Request
import psycopg2
router=APIRouter(prefix='/api/v1/pipeline',tags=['Source Health'])
_last=0.0
_lock=threading.Lock()
@router.post('/health-check')
def health_check(request:Request):
    global _last
    # This app is intended to be bound exclusively to 127.0.0.1:8000.
    host=request.headers.get('host','').split(':')[0].lower()
    if host not in {'localhost','127.0.0.1'}:raise HTTPException(403,'Chỉ được kiểm tra trong môi trường local.')
    origin=request.headers.get('origin')
    if origin and origin.rstrip('/') not in ('http://localhost:8000','http://127.0.0.1:8000'):raise HTTPException(403,'Origin không được phép.')
    if request.headers.get('x-requested-with')!='EcomInsight':raise HTTPException(403,'Thiếu header xác nhận yêu cầu từ giao diện.')
    with _lock:
        now=time.monotonic()
        if now-_last < 60:raise HTTPException(429,'Chỉ được kiểm tra tối đa một lần mỗi 60 giây.')
        _last=now
    checks=[];started=time.perf_counter()
    try:
        with psycopg2.connect(host=os.getenv('DB_HOST','postgres'),port=os.getenv('DB_PORT','5432'),dbname=os.getenv('POSTGRES_DB','ecom_dwh'),user=os.getenv('POSTGRES_USER','ecom'),password=os.getenv('POSTGRES_PASSWORD',''),connect_timeout=4) as conn:
            with conn.cursor() as cur:cur.execute('SELECT 1');ok=cur.fetchone()[0]==1
        checks.append({'name':'PostgreSQL','status':'healthy' if ok else 'unhealthy','latency_ms':round((time.perf_counter()-started)*1000),'detail':'Kết nối cơ sở dữ liệu'})
    except Exception:
        checks.append({'name':'PostgreSQL','status':'unhealthy','detail':'Không kết nối được cơ sở dữ liệu'})
    folder=Path(os.getenv('EXCEL_SOURCE_DIR','/srv/excel'))
    files=[p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.xls','.xlsx')] if folder.is_dir() else []
    checks.append({'name':'6 file Excel','status':'healthy' if len(files)==6 else 'unhealthy','files_found':len(files),'detail':'Kiểm tra sự tồn tại file nguồn'})
    started=time.perf_counter()
    try:
        req=Request('https://search.mediacloud.org/',headers={'User-Agent':'EcomInsight-HealthCheck/1.0'})
        with urlopen(req,timeout=5) as response: code=response.status
        ok=200<=code<500
        checks.append({'name':'Media Cloud','status':'reachable' if ok else 'unhealthy','latency_ms':round((time.perf_counter()-started)*1000),'detail':f'HTTP {code} · Chỉ kiểm tra website'})
    except HTTPError as exc:
        checks.append({'name':'Media Cloud','status':'reachable' if exc.code in (401,403,404,405,429) else 'unhealthy','detail':f'HTTP {exc.code} · Chỉ kiểm tra website'})
    except (URLError, TimeoutError, OSError):
        checks.append({'name':'Media Cloud','status':'unhealthy','detail':'Không kết nối được website'})
    return {'checked_at':datetime.now(timezone.utc).isoformat(),'sources':checks,'note':'Không sử dụng Search API, không xác minh API key; kết quả Excel chỉ tính số lượng file.'}
