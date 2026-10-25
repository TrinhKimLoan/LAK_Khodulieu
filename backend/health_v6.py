"""On-demand source check for LOCAL EcomInsight demo; not authentication or full API validation."""
import logging, os, time, threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError
from fastapi import APIRouter, HTTPException, Request
import psycopg2
router=APIRouter(prefix='/api/v1/pipeline',tags=['Source Health'])
LOG=logging.getLogger('ecom.health')
_lock=threading.Lock(); _last=0.0; _last_result=None
COOLDOWN=60

@router.post('/health-check-v6')
def health_check(request: Request):
    """Separated V6 path to avoid stale V4/V5 FastAPI duplicate route registrations."""
    global _last, _last_result
    host=request.headers.get('host','').split(':')[0].lower()
    origin=request.headers.get('origin','')
    if host not in ('localhost','127.0.0.1') or (origin and origin not in ('http://localhost:8000','http://127.0.0.1:8000')):
        raise HTTPException(403,'Chỉ hỗ trợ demo trên localhost:8000')
    if request.headers.get('x-requested-with')!='EcomInsight':raise HTTPException(403,'Yêu cầu không hợp lệ')
    with _lock:
        now=time.monotonic()
        if now-_last < COOLDOWN:
            if _last_result:
                return {**_last_result,'cached':True,'retry_after_seconds':int(COOLDOWN-(now-_last))+1}
            raise HTTPException(429,'Đang trong khoảng giới hạn kiểm tra')
        _last=now
    checks=[]
    def add(name,status,detail,latency_ms=None,**extra):
        item={'name':name,'status':status,'detail':detail}
        if latency_ms is not None:item['latency_ms']=latency_ms
        item.update(extra);checks.append(item)
    start=time.perf_counter()
    try:
        with psycopg2.connect(host=os.getenv('DB_HOST','postgres'),port=int(os.getenv('DB_PORT','5432')),dbname=os.getenv('POSTGRES_DB','ecom_dwh'),user=os.getenv('POSTGRES_USER','ecom'),password=os.getenv('POSTGRES_PASSWORD',''),connect_timeout=4) as conn:
            with conn.cursor() as cur:cur.execute('SELECT 1'); healthy=cur.fetchone()[0]==1
        add('PostgreSQL','healthy' if healthy else 'unhealthy','Truy vấn SELECT 1',round((time.perf_counter()-start)*1000))
    except Exception as ex:
        LOG.warning('Database health check failed: %s',type(ex).__name__)
        add('PostgreSQL','unhealthy','Không truy vấn được PostgreSQL',round((time.perf_counter()-start)*1000))
    source=Path(os.getenv('EXCEL_SOURCE_DIR','/srv/excel'))
    try:
        files=sorted(p.name for p in source.iterdir() if p.is_file() and p.suffix.lower() in ('.xls','.xlsx')) if source.is_dir() else []
        add('6 file Excel','healthy' if len(files)==6 else 'unhealthy',f'Tìm thấy {len(files)}/6 file Excel; không kiểm tra nội dung',files_found=len(files),expected=6)
    except OSError as ex:
        LOG.warning('Excel source health check failed: %s',type(ex).__name__)
        add('6 file Excel','unhealthy','Không đọc được thư mục Excel',files_found=0,expected=6)
    start=time.perf_counter()
    try:
        with urlopen(UrlRequest('https://search.mediacloud.org/',headers={'User-Agent':'EcomInsight-local-health/1.0'}),timeout=6) as response:
            code=response.status
        add('Media Cloud website','reachable' if code<500 else 'unhealthy',f'HTTP {code}; không kiểm tra API Search/key',round((time.perf_counter()-start)*1000))
    except HTTPError as ex:
        status='reachable' if ex.code in (401,403,404,405,429) else 'unhealthy'
        add('Media Cloud website',status,f'HTTP {ex.code}; không kiểm tra API Search/key',round((time.perf_counter()-start)*1000))
    except (URLError, TimeoutError, OSError) as ex:
        LOG.warning('Media Cloud connectivity check failed: %s',type(ex).__name__)
        add('Media Cloud website','unhealthy','Timeout / không kết nối được trang tìm kiếm',round((time.perf_counter()-start)*1000))
    response={'checked_at':datetime.now(timezone.utc).isoformat(),'sources':checks,'overall':'degraded' if any(x['status']=='unhealthy' for x in checks) else 'reachable','cached':False,'mode':'local_connectivity'}
    if response['overall']=='degraded':LOG.warning('EcomInsight source check DEGRADED: %s', [(x['name'],x['status']) for x in checks])
    with _lock:_last_result=response
    return response
