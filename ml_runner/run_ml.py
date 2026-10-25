"""Run the three supplied notebooks against local PostgreSQL; export to web folder."""
import argparse, os, sys, shutil
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
NOTEBOOKS = {'ml1': 'ML1_RFM_KMeans.ipynb', 'ml2': 'ML2_RandomForest_GiaoHang.ipynb', 'ml3': 'ML3_GoiY_SanPham.ipynb'}
EXPECTED = {
 'ml1': ['ml1_customer_segments.csv','ml1_cluster_summary.csv','ml1_k_selection.csv','ml1_model.joblib'],
 'ml2': ['ml2_model_comparison.csv','ml2_feature_importance.csv','ml2_model.joblib'],
 'ml3': ['ml3_metrics_A_leave_last_out.csv','ml3_metrics_B_temporal.csv','ml3_category_cooccurrence.csv','ml3_recommendations_top5.csv'],
}

def main():
 parser=argparse.ArgumentParser(description='Run EcomInsight ML notebooks and copy exported artifacts to web')
 parser.add_argument('--only', choices=['ml1','ml2','ml3','all'], default='all')
 parser.add_argument('--copy-web', action='store_true')
 args=parser.parse_args()
 try:
  from dotenv import load_dotenv
  from sqlalchemy import create_engine, text
  import nbformat
  from nbclient import NotebookClient
 except ImportError as e:
  sys.exit(f'Thiếu thư viện {e}. Chạy: py -m pip install -r ml_runner/requirements.txt')
 env=PROJECT/'.env'
 if not env.exists(): sys.exit(f'Không thấy {env}; cần file .env có POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB (không commit Git).')
 load_dotenv(env, override=False)
 user=os.getenv('POSTGRES_USER','ecom'); pw=os.getenv('POSTGRES_PASSWORD')
 if not pw:sys.exit('Thiếu POSTGRES_PASSWORD trong .env')
 db=os.getenv('POSTGRES_DB','ecom_dwh')
 host='localhost'; port='5433'
 url=f'postgresql+psycopg2://{quote_plus(user)}:{quote_plus(pw)}@{host}:{port}/{quote_plus(db)}'
 try:
  with create_engine(url,connect_args={'connect_timeout':5}).connect() as conn:
   print('PostgreSQL OK:',conn.execute(text('select count(*) from dw.fact_sales')).scalar(),'sales rows')
 except Exception as exc:sys.exit(f'Không kết nối được PostgreSQL localhost:5433/{db}: {type(exc).__name__}: {exc}')
 selected=NOTEBOOKS if args.only=='all' else {args.only: NOTEBOOKS[args.only]}
 for group,file in selected.items():
  fp=ROOT/'notebooks'/file
  if not fp.exists():sys.exit(f'Không thấy notebook: {fp}')
  print(f'\n=== RUN {group}: {file} ===',flush=True)
  nb=nbformat.read(fp,as_version=4)
  # Notebook uses Path.cwd() for its outputs. Set cwd to project root.
  try:
   client=NotebookClient(nb,timeout=None,kernel_name='python3',resources={'metadata':{'path':str(PROJECT)}})
   executed=client.execute()
  except Exception as exc:
   print(f'Notebook {group} lỗi: {type(exc).__name__}: {exc}',file=sys.stderr)
   print('Các notebook đã hoàn thành trước đó vẫn giữ outputs trong outputs/nb/.',file=sys.stderr)
   sys.exit(1)
  executed_path=PROJECT/'outputs'/'executed_notebooks';executed_path.mkdir(parents=True,exist_ok=True)
  nbformat.write(executed,executed_path/file)
  source=PROJECT/'outputs'/'nb'/group
  missing=[n for n in EXPECTED[group] if not (source/n).is_file()]
  if missing:sys.exit(f'{group}: thiếu output {missing}; kiểm tra cell SAVE cuối notebook.')
  for name in EXPECTED[group]:print('OK',source/name)
  if args.copy_web:
   dest=PROJECT/'backend'/'ml_outputs'/group
   if not (PROJECT/'backend').is_dir():sys.exit('Không có backend/ trong project, bỏ --copy-web hoặc thêm backend từ ZIP web.')
   dest.mkdir(parents=True,exist_ok=True)
   for name in EXPECTED[group]:shutil.copy2(source/name,dest/name)
   print('Copied to',dest)
 print('\nDONE: Notebook + CSV/model output generated.')
if __name__=='__main__':main()
