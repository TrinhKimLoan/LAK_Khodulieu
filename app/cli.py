import argparse
from . import core

def main():
 p=argparse.ArgumentParser(description='Ecommerce DWH local Docker pipeline')
 p.add_argument('command',choices=['bootstrap','excel','seed-news','fetch-news','marts','validate','health','all-offline','backfill-month','backfill-range','reclassify-news'])
 p.add_argument('--year',type=int,default=2024)
 p.add_argument('--month',type=int,default=1)
 p.add_argument('--start-year',type=int,default=2020)
 p.add_argument('--end-year',type=int,default=2025)
 p.add_argument('--force',action='store_true')
 args=p.parse_args();cmd=args.command
 if cmd=='bootstrap':core.bootstrap()
 elif cmd=='excel':core.load_excel()
 elif cmd=='seed-news':core.seed_news()
 elif cmd=='fetch-news':core.live_news()
 elif cmd=='marts':core.build_marts()
 elif cmd=='reclassify-news':core.reclassify_news()
 elif cmd=='validate':core.validate()
 elif cmd=='health':core.health()
 elif cmd=='backfill-month':core.backfill_month(args.year,args.month,force=args.force)
 elif cmd=='backfill-range':core.backfill_range(args.start_year,args.end_year,force=args.force)
 elif cmd=='all-offline':
  core.bootstrap();core.load_excel();core.seed_news();core.build_marts();core.validate()
if __name__=='__main__':main()
