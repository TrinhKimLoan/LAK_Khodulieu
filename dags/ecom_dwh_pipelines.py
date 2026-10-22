"""Two scheduled pipelines; manual bootstrap before first run; paused by default."""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from app import core
DEFAULT={'owner':'ecom-team','retries':1,'retry_delay':timedelta(minutes=5)}
with DAG('ecom_excel_refresh',start_date=datetime(2026,1,1),schedule='@weekly',catchup=False,default_args=DEFAULT,tags=['ecom','excel']) as dag_excel:
 stage=PythonOperator(task_id='stage_excel',python_callable=core.load_excel)
 marts=PythonOperator(task_id='refresh_warehouse',python_callable=core.build_marts)
 test=PythonOperator(task_id='validate_warehouse',python_callable=core.validate)
 stage >> marts >> test
with DAG('ecom_news_incremental',start_date=datetime(2026,1,1),schedule='@daily',catchup=False,default_args=DEFAULT,tags=['ecom','news','cdc']) as dag_news:
 fetch=PythonOperator(task_id='fetch_and_detect_changes',python_callable=core.live_news)
 marts=PythonOperator(task_id='refresh_news_mart',python_callable=core.build_marts)
 test=PythonOperator(task_id='validate_warehouse',python_callable=core.validate)
 fetch >> marts >> test
with DAG('ecom_source_health',start_date=datetime(2026,1,1),schedule='0 */6 * * *',catchup=False,default_args=DEFAULT,tags=['ecom','health']) as dag_health:
 PythonOperator(task_id='check_sources',python_callable=core.health)
