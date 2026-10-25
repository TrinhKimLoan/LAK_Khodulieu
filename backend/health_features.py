"""Authenticated, rate-limited on-demand connectivity probe. No ingestion/API search quota."""
import os, time, hmac, threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from fastapi import APIRouter, Header, HTTPException
import psycopg2

router = APIRouter(prefix='/api/v1/pipeline', tags=['Source Health'])
_lock=threading.Lock()
_last_check=0.0
_MIN_INTERVAL=60

@router.post('/health-check')
def health_check(x_health_token: str | None = Header(None)):
    global _last_check
    expected=os.environ.get('HEALTH_ADMIN_TOKEN','')
    if len(expected)<20:
        raise HTTPException(503,'Admin token chưa được cấu hình đủ an toàn (>=20 ký tự).')
    if not x_health_token or not hmac.compare_digest(x_health_token, expected):
        raise HTTPException(403, 'Mã quản trị không hợp lệ.')
    with _lock:
        now=time.monotonic()
        if now-_last_check < _MIN_INTERVAL:
            raise HTTPException(429,f'Giới hạn tối đa 1 lần kiểm tra mỗi {_MIN_INTERVAL} giây.')
        _last_check=now
    checked_at=datetime.now(timezone.utc).isoformat()
    results=[]
    started=time.perf_counter()
    try:
        with psycopg2.connect(host=os.getenv('DB_HOST','postgres'),port=os.getenv('DB_PORT','5432'),dbname=os.getenv('POSTGRES_DB','ecom_dwh'),user=os.getenv('POSTGRES_USER','ecom'),password=os.getenv('POSTGRES_PASSWORD',''),connect_timeout=4) as conn:
            with conn.cursor() as c:
                c.execute('SELECT 1')
                ok=c.fetchone()[0]==1
        results.append({'name':'postgres','status':'healthy' if ok else 'unhealthy','latency_ms':round((time.perf_counter()-started)*1000,1),'detail':'SELECT 1'})
    except Exception as exc:
        results.append({'name':'postgres','status':'unhealthy','latency_ms':round((time.perf_counter()-started)*1000,1),'detail':f'Không kết nối được ({type(exc).__name__})'})

    folder=Path(os.getenv('EXCEL_SOURCE_DIR','/srv/excel'))
    names=[p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.xlsx','.xls')] if folder.is_dir() else []
    count=len(names)
    results.append({'name':'excel','status':'healthy' if count==6 else 'unhealthy','files_found':count,'detail':'Đếm file .xls/.xlsx tại thư mục mounted; không xác thực nội dung từng file'})

    started=time.perf_counter()
    # Fixed URL. No user supplied endpoints, no Media Cloud Search API consumption.
    try:
        request=Request('https://search.mediacloud.org/',headers={'User-Agent':'EcomInsight-HealthCheck/1.0'})
        with urlopen(request,timeout=6) as response:
            code=response.status
        status='reachable' if 200<=code<500 else 'unhealthy'
        detail=f'HTTP {code} – connectivity only, API key/search chưa kiểm tra'
    except HTTPError as exc:
        code=exc.code;status='reachable' if code in (401,403,404,405,429) else 'unhealthy'
        detail=f'HTTP {code} – website phản hồi, không đồng nghĩa Search API hoạt động'
    except (URLError,TimeoutError,OSError) as exc:
        status='unhealthy'; detail=f'HTTP không kết nối được ({type(exc).__name__})'
    results.append({'name':'mediacloud','status':status,'latency_ms':round((time.perf_counter()-started)*1000,1),'detail':detail})
    return {'checked_at':checked_at,'sources':results,'note':'Connectivity checks only; không gọi Search API, không phát hiện dữ liệu bài báo mới và không xác thực Media Cloud API key.'}
