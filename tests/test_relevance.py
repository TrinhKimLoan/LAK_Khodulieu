from app.relevance import classify

def test_product_news():
 assert classify('Giá RAM DDR5 tăng mạnh')['level']=='DIRECT'
 assert classify('Giá SSD NVMe giảm mạnh')['level']=='DIRECT'

def test_false_positives():
 assert classify('TP.HCM lắp hơn 200 camera giám sát chợ đầu mối')['level']=='IRRELEVANT'
 assert classify('Người đàn ông tạo WiFi giả ở nhiều sân bay')['level']=='IRRELEVANT'
 assert classify('Galaxy A07 5G lộ hiệu năng GPU ấn tượng')['level']=='IRRELEVANT'

def test_indirect():
 assert classify('Windows 11 sắp nhận bản cập nhật giúp giảm ngốn RAM')['level']=='INDIRECT'
 assert classify('Đánh giá ROG Strix G16 bản RTX 5060')['level']=='INDIRECT'


def test_phone_camera_not_retail_security_camera():
 for title in [
  'OPPO Find X10 Series chuẩn bị ra mắt tại Việt Nam cùng camera kép 200MP',
  'Samsung Galaxy F70 5G ra mắt tại Ấn Độ: camera 50MP OIS',
  '6 điện thoại giá dưới 10 triệu giảm sâu tháng 10: camera 200MP',
  'Xe ga giá 62 triệu đồng có sẵn camera hành trình',
 ]:
  assert classify(title)['level'] == 'IRRELEVANT', title

def test_security_camera_product_still_direct():
 assert classify('Ezviz giới thiệu camera IP giám sát gia đình giá rẻ')['level']=='DIRECT'
 assert classify('Giá webcam máy tính giảm mạnh')['level']=='DIRECT'

def test_civic_camera_installation_still_excluded():
 assert classify('TP.HCM lắp hơn 200 camera giám sát chợ đầu mối')['level']=='IRRELEVANT'
