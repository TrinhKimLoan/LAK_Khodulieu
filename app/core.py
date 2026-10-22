"""Pipeline ingestion, change detection and dimensional marts. No model training required."""
import csv, datetime as dt, hashlib, json, os, re, time, uuid, zipfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from .relevance import classify
from xml.etree import ElementTree as ET
ROOT=Path('/opt/project') if Path('/opt/project/data').exists() else Path(__file__).resolve().parents[1]
EPOCH=dt.datetime(1899,12,30)
CAT_TERMS={
 'GPU':['gpu','card đồ họa','card màn hình','rtx ','geforce','radeon','graphics card'],
 'CPU':['cpu','ryzen','vi xử lý','bộ xử lý','intel core','core i5','core i7','core i9'],
 'SSD':['ssd','ổ cứng thể rắn','solid state drive'],
 'HDD':['hdd','ổ cứng cơ','hard disk'],
 'RAM':[' ram ','ddr4','ddr5','bộ nhớ ram','dram','camm2'],
 'NETWORK':['router','bộ định tuyến','switch mạng','switch cisco','thiết bị mạng','wifi','wi-fi','tp-link'],
 'MONITOR':['màn hình máy tính','monitor','display 144hz','màn hình gaming'],
 'MOTHERBOARD':['mainboard','bo mạch chủ','motherboard'],
 'PERIPHERAL':['bàn phím','chuột máy tính','keyboard','mouse gaming'],
 'CAMERA':['camera giám sát','camera an ninh','camera ip','webcam','camera hikvision'],
 'PSU':['nguồn corsair','nguồn máy tính','power supply','psu'],
 'MONITOR':['màn hình máy tính','monitor','display 144hz','màn hình gaming','màn hình lg','ultragear'],
 'HDD':['hdd','ổ cứng cơ','hard disk','ổ cứng wd'],
 'PERIPHERAL':['bàn phím','chuột máy tính','keyboard','mouse gaming','chuột logitech']}
EXCLUDE=['tiki-taka','cổ phiếu','chứng khoán','giá cổ phiếu','thị trường chứng khoán']
SUSPICIOUS={'lamdongtv.vn'}

def db():
 import psycopg2
 return psycopg2.connect(host=os.getenv('DB_HOST','localhost'),port=os.getenv('DB_PORT','5433'),user=os.getenv('POSTGRES_USER','ecom'),password=os.getenv('POSTGRES_PASSWORD','change-this-local-password'),dbname=os.getenv('POSTGRES_DB','ecom_dwh'))

def xlsx_rows(path):
 """Minimal XLSX reader for source tables: no third-party spreadsheet dependency."""
 ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
 with zipfile.ZipFile(path) as z:
  shared=[]
  if 'xl/sharedStrings.xml' in z.namelist():
   root=ET.fromstring(z.read('xl/sharedStrings.xml'))
   shared=[''.join(t.text or '' for t in si.findall('.//m:t',ns)) for si in root.findall('m:si',ns)]
  sheet=next(n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',n))
  root=ET.fromstring(z.read(sheet)); rows=[]
  for row in root.findall('.//m:sheetData/m:row',ns):
   values={}
   for c in row.findall('m:c',ns):
    ref=c.attrib.get('r','A1'); letters=re.match(r'[A-Z]+',ref).group(); idx=0
    for ch in letters: idx=idx*26+ord(ch)-64
    typ=c.attrib.get('t'); v=c.find('m:v',ns)
    if typ=='inlineStr':
     out=''.join(t.text or '' for t in c.findall('.//m:t',ns))
    elif v is None:out=None
    elif typ=='s':out=shared[int(v.text)]
    elif typ=='b':out=(v.text=='1')
    elif typ in ('str','e'):out=v.text
    else:
     try:out=float(v.text);out=int(out) if out.is_integer() else out
     except (TypeError,ValueError):out=v.text
    values[idx-1]=out
   rows.append([values.get(i) for i in range(max(values,default=-1)+1)])
  if not rows:return []
  head=[str(x).strip() if x is not None else '' for x in rows[0]]
  return [{name:(row[i] if i<len(row) else None) for i,name in enumerate(head) if name} for row in rows[1:] if any(v is not None for v in row)]

def dateval(v):
 if v is None or v=='':return None
 if isinstance(v,(int,float)):return (EPOCH+dt.timedelta(days=float(v))).date()
 s=str(v).strip()
 try:return dt.date.fromisoformat(s[:10])
 except ValueError:
  try:return dt.datetime.strptime(s[:10],'%m/%d/%Y').date()
  except ValueError:return None

def money(v):return float(v) if v not in (None,'') else None

def file_path(prefix):
 p=list((ROOT/'data/excel').glob(prefix+'*.xlsx'))
 if len(p)!=1:raise ValueError('Expected exactly one Excel '+prefix+'*, found '+str(p))
 return p[0]

def bootstrap():
 with db() as c:
  with c.cursor() as q:q.execute((ROOT/'sql/001_schema.sql').read_text(encoding='utf-8'))
 print('Created/checked raw, staging, dw, ops schemas')

def load_excel():
 from psycopg2.extras import Json
 records={}
 for prefix in ('01','02','03','04','05','06'):
  p=file_path(prefix);records[prefix]=xlsx_rows(p);print(prefix,len(records[prefix]),p.name)
 cust={str(x['Ma_Khach_Hang']):x for x in records['02']}
 prod={str(x['Ma_San_Pham']):x for x in records['03']}
 times={str(x['Ma_Don']):x for x in records['04']}
 pays={str(x['Ma_Don']):x for x in records['05']}
 ships={str(x['Ma_Don']):x for x in records['06']}
 orders=records['01']
 if not all(str(o['Ma_Don']) in times and str(o['Ma_Don']) in pays and str(o['Ma_Don']) in ships and str(o['Ma_Khach_Hang']) in cust and str(o['Ma_San_Pham']) in prod for o in orders):raise ValueError('Missing joined order/customer/product rows; examine keys')
 with db() as conn:
  with conn.cursor() as q:
   for prefix,rows in records.items():
    for i,x in enumerate(rows):
     key=str(x.get({'01':'Ma_Don','02':'Ma_Khach_Hang','03':'Ma_San_Pham','04':'Ma_Don','05':'Ma_Don','06':'Ma_Don'}[prefix]) or i)
     # Avoid storing raw customer names, phone numbers and addresses in DWH demo.
     if prefix=='02':x={k:v for k,v in x.items() if k not in ('Ten_Khach_Hang','SDT','Dia_Chi_Giao')}
     if prefix=='06':x={k:v for k,v in x.items() if k!='Dia_Chi_Giao'}
     q.execute('INSERT INTO raw.excel_rows(source_file,business_key,payload) VALUES (%s,%s,%s) ON CONFLICT(source_file,business_key) DO UPDATE SET payload=excluded.payload,loaded_at=now()', (prefix,key,Json(x)))
   for x in records['02']:
    q.execute('INSERT INTO staging.customers VALUES (%s,%s,%s,%s) ON CONFLICT(customer_id) DO UPDATE SET gender=excluded.gender,city=excluded.city,district=excluded.district',(x['Ma_Khach_Hang'],x.get('Gioi_Tinh'),x.get('Tinh_Thanh'),x.get('Quan_Huyen')))
   for x in records['03']:
    code=product_cat(x.get('Ten_Hang_Hoa',''))
    q.execute('INSERT INTO staging.products VALUES (%s,%s,%s,%s,%s) ON CONFLICT(product_id) DO UPDATE SET product_name=excluded.product_name,category_code=excluded.category_code,unit_price=excluded.unit_price',(x['Ma_San_Pham'],x.get('Ten_Hang_Hoa'),x.get('Loai_Hang'),code,money(x.get('Don_Gia_San_Pham'))))
   for o in orders:
    oid=str(o['Ma_Don']);t=times[oid];p=pays[oid];s=ships[oid]
    started=dateval(t.get('Thoi_Gian_Dong_Goi'));arrived=dateval(t.get('Thoi_Gian_Nhan_Hang'))
    delivery=(arrived-started).days if (arrived and started) else None
    q.execute('''INSERT INTO staging.orders(order_id,customer_id,product_id,quantity,shipping_type,warehouse,vehicle,driver,order_date,shipped_date,expected_date,delivered_date,goods_amount,vat_amount,shipping_fee,total_paid,city,district,delivery_days)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT(order_id) DO UPDATE SET quantity=excluded.quantity,goods_amount=excluded.goods_amount,total_paid=excluded.total_paid,delivery_days=excluded.delivery_days''',
    (oid,o['Ma_Khach_Hang'],o['Ma_San_Pham'],money(o.get('So_Luong')),o.get('Loai_Giao_Hang'),s.get('Kho_Xuat'),s.get('Xe_Van_Chuyen'),s.get('Tai_Xe'),started,dateval(t.get('Thoi_Gian_Giao_Hang')),dateval(t.get('Thoi_Gian_Du_Kien_Toi')),arrived,money(p.get('Tong_Gia_Tri_Hang')),money(p.get('VAT_10')),money(p.get('Phi_Van_Chuyen')),money(p.get('Tong_Thanh_Toan')),s.get('Tinh_Thanh'),s.get('Quan_Huyen'),delivery))
 print('Excel staging finished:',len(orders),'orders')

# The config file is optional; edit it when switching datasets / industries.
RULES_FILE=ROOT/'config/category_rules.json'
if RULES_FILE.exists():
 cfg=json.loads(RULES_FILE.read_text(encoding='utf-8'))
 CAT_TERMS=cfg.get('categories',CAT_TERMS)
 EXCLUDE=cfg.get('exclude_keywords',EXCLUDE)

def norm(s):return ' '+re.sub(r'\s+',' ',str(s or '').lower()).strip()+' '

def find_cats(title):
 s=norm(title)
 if any(w in s for w in EXCLUDE):return []
 return [cat for cat,terms in CAT_TERMS.items() if any(term in s for term in terms)]

def product_cat(title):
 cats=find_cats(title)
 return cats[0] if cats else 'OTHER'

def canonical(url):
 try:
  p=urlsplit(url.strip());return urlunsplit((p.scheme.lower() or 'https',p.netloc.lower().removeprefix('www.'),p.path.rstrip('/'),urlencode([(k,v) for k,v in parse_qsl(p.query) if not k.startswith('utm_')]),''))
 except Exception:return str(url or '').strip()

def timestamp(s):
 if not s:return None
 try:return dt.datetime.fromisoformat(str(s).replace('Z','+00:00'))
 except ValueError:return None

def record_from(x):
 title=str(x.get('title') or '').strip();d=dateval(x.get('publish_date'))
 if not (title and d):return None
 url=canonical(x.get('url') or '')
 if not url:return None
 domain=(urlsplit(url).hostname or str(x.get('media_url') or '')).removeprefix('www.')
 result=classify(title, domain, SUSPICIOUS)
 cats=result['categories']
 level=result['level']
 status='candidate' if level=='DIRECT' and len(title)>14 else 'review'
 external=str(x.get('id') or '').strip()
 # Key by canonical URL to merge repeated records across API/CSV while retaining metadata external ID
 key=hashlib.sha256(url.encode('utf-8')).hexdigest()
 obj={'article_key':key,'external_id':external,'title':title,'canonical_url':url,'source_domain':domain,'published_date':d,'indexed_at':timestamp(x.get('indexed_date')),'category_codes':cats,'keyword_match':bool(cats),'quality_status':status,'relevance_level':level,'relevance_reason':result['reason']}
 digest=hashlib.sha256(json.dumps({k:str(v) for k,v in obj.items() if k not in ('indexed_at','external_id')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 obj['record_hash']=digest
 return obj

def ingest_news(rows,origin='seed'):
 from psycopg2.extras import Json
 run_id=f'{origin}-{dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")}-{uuid.uuid4().hex[:6]}'
 insert=update=same=invalid=0; seen=set()
 with db() as conn:
  with conn.cursor() as q:
   q.execute('INSERT INTO ops.pipeline_runs(run_id,pipeline,status) VALUES(%s,%s,%s)',(run_id,'news_'+origin,'RUNNING'))
   for raw in rows:
    obj=record_from(raw)
    if obj is None:invalid+=1;continue
    key=obj['article_key']
    if key in seen:continue
    seen.add(key)
    q.execute('INSERT INTO raw.news_snapshots(run_id,article_key,payload,record_hash) VALUES(%s,%s,%s,%s)',(run_id,key,Json(json.loads(json.dumps(raw,default=str))),obj['record_hash']))
    q.execute('SELECT record_hash FROM staging.news_articles WHERE article_key=%s',(key,))
    previous=q.fetchone()
    if previous and previous[0]==obj['record_hash']:
     q.execute('UPDATE staging.news_articles SET last_seen_at=now() WHERE article_key=%s',(key,));same+=1;continue
    typ='UPDATE' if previous else 'INSERT'
    q.execute('''INSERT INTO staging.news_articles(article_key,external_id,title,canonical_url,source_domain,published_date,indexed_at,category_codes,keyword_match,quality_status,relevance_level,relevance_reason,record_hash)
VALUES(%(article_key)s,%(external_id)s,%(title)s,%(canonical_url)s,%(source_domain)s,%(published_date)s,%(indexed_at)s,%(category_codes)s,%(keyword_match)s,%(quality_status)s,%(relevance_level)s,%(relevance_reason)s,%(record_hash)s)
ON CONFLICT(article_key) DO UPDATE SET external_id=excluded.external_id,title=excluded.title,source_domain=excluded.source_domain,published_date=excluded.published_date,indexed_at=excluded.indexed_at,category_codes=excluded.category_codes,keyword_match=excluded.keyword_match,quality_status=excluded.quality_status,relevance_level=excluded.relevance_level,relevance_reason=excluded.relevance_reason,record_hash=excluded.record_hash,last_seen_at=now()''',obj)
    q.execute('INSERT INTO ops.news_change_log(run_id,article_key,change_type,previous_hash,current_hash) VALUES (%s,%s,%s,%s,%s)',(run_id,key,typ,previous[0] if previous else None,obj['record_hash']))
    if previous:update+=1
    else:insert+=1
   q.execute("UPDATE ops.pipeline_runs SET status='SUCCESS', finished_at=now(),records_count=%s,message=%s WHERE run_id=%s",(insert+update,json.dumps({'insert':insert,'update':update,'unchanged':same,'invalid':invalid}),run_id))
 print(json.dumps({'run_id':run_id,'insert':insert,'update':update,'unchanged':same,'invalid':invalid,'sample_unique':len(seen)},ensure_ascii=False))
 return run_id

def reclassify_news():
 """Re-evaluate EXISTING staged articles without API calls or fake change-log events.
 Note: matches stored record_hash to the current ingestion rules for idempotency.
 """
 from psycopg2.extras import execute_batch
 counters={'DIRECT':0,'INDIRECT':0,'IRRELEVANT':0}
 modified=0
 with db() as conn:
  with conn.cursor(name='relevance_article_reader') as read:
   read.itersize=1000
   read.execute('SELECT article_key,title,canonical_url,published_date,source_domain,category_codes,quality_status,relevance_level,relevance_reason,record_hash FROM staging.news_articles ORDER BY article_key')
   with conn.cursor() as write:
    buffer=[]
    for key,title,url,published,domain,old_cats,old_status,old_level,old_reason,old_hash in read:
     obj=record_from({'title':title,'url':url,'publish_date':published.isoformat()})
     if not obj:continue
     counters[obj['relevance_level']]+=1
     changed=(list(old_cats or [])!=obj['category_codes'] or old_status!=obj['quality_status'] or old_level!=obj['relevance_level'] or old_reason!=obj['relevance_reason'] or old_hash!=obj['record_hash'])
     if changed:
      buffer.append((obj['category_codes'],obj['keyword_match'],obj['quality_status'],obj['relevance_level'],obj['relevance_reason'],obj['record_hash'],key))
     if len(buffer)>=500:
      execute_batch(write,'''UPDATE staging.news_articles SET category_codes=%s,keyword_match=%s,quality_status=%s,relevance_level=%s,relevance_reason=%s,record_hash=%s WHERE article_key=%s''',buffer,page_size=500)
      modified+=len(buffer);buffer.clear()
    if buffer:
     execute_batch(write,'''UPDATE staging.news_articles SET category_codes=%s,keyword_match=%s,quality_status=%s,relevance_level=%s,relevance_reason=%s,record_hash=%s WHERE article_key=%s''',buffer,page_size=500)
     modified+=len(buffer)
 print('RECLASSIFIED',json.dumps({'updated_rows':modified,'levels':counters},ensure_ascii=False))
 print('NEXT: python -m app.cli marts  (to refresh DW fact and category bridge)')

def seed_news():
 fn=ROOT/'data/news_seed/media_api_2024.csv'
 with fn.open(encoding='utf-8-sig',newline='') as f:return ingest_news(list(csv.DictReader(f)),'seed')

def _news_queries():
 return cfg.get('queries', {}) if RULES_FILE.exists() else {'GPU':'GPU OR RTX OR card đồ họa','CPU':'CPU OR Ryzen OR vi xử lý','SSD':'SSD OR ổ cứng','RAM':'RAM OR DDR5','NETWORK':'router OR switch OR thiết bị mạng'}

def _search_news_window(start, end, page_size=None, max_pages=None):
 """Search a bounded interval with actual API pagination. A cap means partial coverage."""
 import mediacloud.api
 key=os.getenv('MEDIACLOUD_API_KEY','').strip()
 if not key:raise RuntimeError('Missing MEDIACLOUD_API_KEY in .env')
 if page_size is None:page_size=int(os.getenv('MEDIA_PAGE_SIZE','100'))
 if max_pages is None:max_pages=int(os.getenv('MEDIA_MAX_PAGES_PER_QUERY','2'))
 if not 1<=page_size<=100:raise ValueError('MEDIA_PAGE_SIZE must be in range 1..100')
 if max_pages<0:raise ValueError('MEDIA_MAX_PAGES_PER_QUERY must be >= 0 (0 means no cap)')
 delay=float(os.getenv('MEDIA_REQUEST_DELAY_SECONDS','32'))
 client=mediacloud.api.SearchApi(key)
 cid=int(os.getenv('COLLECTION_ID','34412246'))
 records=[]; statistics={}; partial=False
 for group,query in _news_queries().items():
  page_no=0; token=None; seen_tokens=set(); count=0
  while True:
   # Rate limit applies to every page, including retries across groups.
   if delay>0:time.sleep(delay)
   stories, next_token=client.story_list(query=query,start_date=start,end_date=end,collection_ids=[cid],pagination_token=token,page_size=page_size)
   page_no+=1
   for article in stories:article['query_group']=group
   records.extend(stories);count+=len(stories)
   print(f'NEWS {start}..{end} {group} page={page_no} rows={len(stories)} total_group={count}',flush=True)
   if not next_token:break
   if next_token in seen_tokens:raise RuntimeError(f'Pagination token loop for {group}')
   seen_tokens.add(next_token)
   if max_pages and page_no>=max_pages:
    partial=True;break
   token=next_token
  statistics[group]={'rows':count,'pages':page_no,'complete':not bool(next_token)}
 return records,statistics,partial

def _month_end(year,month):
 if month==12:return dt.date(year,12,31)
 return dt.date(year,month+1,1)-dt.timedelta(days=1)

def backfill_month(year,month,force=False):
 """Idempotent monthly historical ingestion; complete months are skipped."""
 if not (2020<=year<=dt.date.today().year and 1<=month<=12):raise ValueError('Invalid year/month')
 start=dt.date(year,month,1);end=min(_month_end(year,month),dt.date.today())
 queries=_news_queries();cid=int(os.getenv('COLLECTION_ID','34412246'))
 config_signature=hashlib.sha256(json.dumps({'collection':cid,'queries':queries,'size':os.getenv('MEDIA_PAGE_SIZE','100'),'pages':os.getenv('MEDIA_MAX_PAGES_PER_QUERY','2')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
 with db() as conn:
  with conn.cursor() as q:
   q.execute('SELECT status,config_signature FROM ops.news_backfill_months WHERE year=%s AND month=%s',(year,month))
   previous=q.fetchone()
   if previous and previous[0]=='COMPLETE' and previous[1]==config_signature and not force:
    print(f'SKIP {year}-{month:02d} (COMPLETE with same settings; --force to recheck)',flush=True)
    return {'skipped':True}
 print(f'BACKFILL {start}..{end}',flush=True)
 # Only commit a month when every API query succeeds.
 rows,stats,partial=_search_news_window(start,end)
 run_id=ingest_news(rows,'backfill')
 with db() as conn:
  with conn.cursor() as q:
   q.execute("""INSERT INTO ops.news_backfill_months(year,month,status,config_signature,run_id,raw_rows,group_stats,completed_at)
VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,now()) ON CONFLICT(year,month) DO UPDATE SET status=excluded.status,config_signature=excluded.config_signature,run_id=excluded.run_id,raw_rows=excluded.raw_rows,group_stats=excluded.group_stats,completed_at=now()""",
    (year,month,'PARTIAL_PAGE_CAP' if partial else 'COMPLETE',config_signature,run_id,len(rows),json.dumps(stats,ensure_ascii=False)))
 print(f'BACKFILL {year}-{month:02d} status={"PARTIAL_PAGE_CAP" if partial else "COMPLETE"} raw={len(rows)}',flush=True)
 return {'skipped':False,'raw_rows':len(rows),'partial':partial}

def backfill_range(start_year=2020,end_year=2025,force=False):
 """Resume at month boundaries. On API quota failure restart same command later."""
 if start_year>end_year:raise ValueError('start-year must be <= end-year')
 for year in range(start_year,end_year+1):
  for month in range(1,13):
   if dt.date(year,month,1)>dt.date.today():return
   backfill_month(year,month,force=force)
 print('BACKFILL RANGE FINISHED (check PARTIAL_PAGE_CAP rows in PostgreSQL)',flush=True)

def live_news():
 """Rolling recent-window polling independent of historical backfill settings."""
 days=int(os.getenv('MEDIA_INCREMENTAL_LOOKBACK_DAYS','45'))
 if days<1 or days>365:raise ValueError('MEDIA_INCREMENTAL_LOOKBACK_DAYS must be 1..365')
 today=dt.date.today();start=today-dt.timedelta(days=days-1)
 rows,stats,partial=_search_news_window(start,today)
 if partial:print('WARNING incremental pagination capped; some matching stories could be missed',flush=True)
 print('INCREMENTAL',start,today,'raw',len(rows),'stats',json.dumps(stats,ensure_ascii=False),flush=True)
 return ingest_news(rows,'api')

def build_marts():
 with db() as conn:
  with conn.cursor() as q:
   q.execute("INSERT INTO dw.dim_date SELECT DISTINCT to_char(d,'YYYYMMDD')::integer,d,extract(year from d)::int,extract(quarter from d)::int,extract(month from d)::int,to_char(d,'YYYY-MM') FROM (SELECT order_date d FROM staging.orders UNION SELECT published_date FROM staging.news_articles) t WHERE d IS NOT NULL ON CONFLICT(date_key) DO NOTHING")
   q.execute("INSERT INTO dw.dim_customer(customer_id,gender,city,district) SELECT customer_id,gender,city,district FROM staging.customers ON CONFLICT(customer_id) DO UPDATE SET gender=excluded.gender,city=excluded.city,district=excluded.district")
   q.execute("INSERT INTO dw.dim_product(product_id,product_name,category_code,product_group,unit_price) SELECT product_id,product_name,category_code,product_group,unit_price FROM staging.products ON CONFLICT(product_id) DO UPDATE SET product_name=excluded.product_name,category_code=excluded.category_code,unit_price=excluded.unit_price")
   for code in set(CAT_TERMS)|{'OTHER'}:
    q.execute('INSERT INTO dw.dim_category(category_code,display_name) VALUES(%s,%s) ON CONFLICT(category_code) DO NOTHING',(code,code.title()))
   q.execute("INSERT INTO dw.dim_news_source(domain) SELECT DISTINCT source_domain FROM staging.news_articles WHERE source_domain IS NOT NULL ON CONFLICT(domain) DO NOTHING")
   q.execute('''INSERT INTO dw.fact_sales(order_id,date_key,customer_key,product_key,quantity,goods_amount,vat_amount,shipping_fee,total_paid,delivery_days,shipping_type,city)
SELECT o.order_id,to_char(o.order_date,'YYYYMMDD')::integer,c.customer_key,p.product_key,o.quantity,o.goods_amount,o.vat_amount,o.shipping_fee,o.total_paid,o.delivery_days,o.shipping_type,o.city FROM staging.orders o JOIN dw.dim_customer c ON c.customer_id=o.customer_id JOIN dw.dim_product p ON p.product_id=o.product_id WHERE o.order_date IS NOT NULL
ON CONFLICT(order_id) DO UPDATE SET date_key=excluded.date_key,quantity=excluded.quantity,goods_amount=excluded.goods_amount,vat_amount=excluded.vat_amount,shipping_fee=excluded.shipping_fee,total_paid=excluded.total_paid,delivery_days=excluded.delivery_days''')
   q.execute('''INSERT INTO dw.fact_news(article_key,date_key,source_key,title,url,quality_status,relevance_level,relevance_reason,last_seen_at)
SELECT n.article_key,to_char(n.published_date,'YYYYMMDD')::integer,s.source_key,n.title,n.canonical_url,n.quality_status,n.relevance_level,n.relevance_reason,n.last_seen_at FROM staging.news_articles n JOIN dw.dim_news_source s ON s.domain=n.source_domain
ON CONFLICT(article_key) DO UPDATE SET date_key=excluded.date_key,source_key=excluded.source_key,title=excluded.title,url=excluded.url,quality_status=excluded.quality_status,relevance_level=excluded.relevance_level,relevance_reason=excluded.relevance_reason,last_seen_at=excluded.last_seen_at''')
   q.execute('DELETE FROM dw.bridge_news_category')
   q.execute("INSERT INTO dw.bridge_news_category(article_key,category_key) SELECT n.article_key,c.category_key FROM staging.news_articles n CROSS JOIN LATERAL unnest(n.category_codes) category JOIN dw.dim_category c ON c.category_code=category")
   q.execute('SELECT (SELECT count(*) FROM dw.fact_sales),(SELECT count(*) FROM dw.fact_news),(SELECT count(*) FROM dw.bridge_news_category)')
   print('MART COUNTS sales/news/news-category',q.fetchone())

def validate():
 with db() as conn:
  with conn.cursor() as q:
   q.execute('SELECT count(*),count(DISTINCT order_id),min(date_key),max(date_key) FROM dw.fact_sales');r=q.fetchone()
   q.execute('SELECT count(*) FROM dw.fact_news');n=q.fetchone()[0]
   q.execute('SELECT count(*) FROM dw.v_category_market_dashboard');joined=q.fetchone()[0]
   q.execute('SELECT count(*) FROM staging.orders WHERE goods_amount IS DISTINCT FROM quantity * (SELECT unit_price FROM staging.products p WHERE p.product_id=staging.orders.product_id)');mismatch=q.fetchone()[0]
   print(json.dumps({'sales_rows':r[0],'unique_orders':r[1],'min_date_key':r[2],'max_date_key':r[3],'news_rows':n,'dashboard_rows':joined,'quantity_price_mismatch':mismatch},ensure_ascii=False))
   if r[0]!=r[1] or r[0]<1:raise AssertionError('Sales grain invalid')

def health():
 with db() as conn:
  with conn.cursor() as q:
   q.execute("SELECT pipeline,status,finished_at,records_count,message FROM ops.pipeline_runs ORDER BY started_at DESC LIMIT 5")
   print('RECENT RUNS',q.fetchall())
 # Health check probe is deliberately separate from content relevance/no-results checks.
 import requests
 url='https://search.mediacloud.org/'
 try:
  resp=requests.get(url,timeout=12);print('Media Cloud HTTP health',resp.status_code)
  if resp.status_code>=500:raise RuntimeError('Media Cloud HTTP '+str(resp.status_code))
 except Exception as exc:
  webhook=os.getenv('ALERT_WEBHOOK_URL','')
  if webhook:
   try:requests.post(webhook,json={'text':'Ecom DWH Media Cloud source check failed: '+str(exc)},timeout=8)
   except Exception as notify_exc:print('Notification failed',notify_exc)
  raise
