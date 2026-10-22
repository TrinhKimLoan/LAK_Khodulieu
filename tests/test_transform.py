import unittest
from pathlib import Path
from app.core import ROOT, xlsx_rows, find_cats, record_from, canonical, product_cat
class TransformTests(unittest.TestCase):
 def test_excel_headers_and_counts(self):
  rows=xlsx_rows(ROOT/'data/excel/01_don_hang.xlsx')
  self.assertEqual(len(rows),10000)
  self.assertEqual(rows[0]['Ma_Don'],'DH000001')
 def test_categories(self):
  self.assertIn('CPU',find_cats('Nhu cầu CPU Ryzen tăng mạnh'))
  self.assertEqual(find_cats('Nvidia tăng giá cổ phiếu'),[])
  self.assertEqual(product_cat('Card màn hình RTX 4060 Ti'),'GPU')
 def test_article_keys(self):
  x={'title':'Giá SSD giảm mạnh','publish_date':'2024-01-10','url':'https://example.com/a?utm_source=test'}
  a=record_from(x);self.assertEqual(a['category_codes'],['SSD'])
  self.assertEqual(canonical(x['url']),'https://example.com/a')
  self.assertEqual(a['record_hash'],record_from(x)['record_hash'])
if __name__=='__main__':unittest.main()
