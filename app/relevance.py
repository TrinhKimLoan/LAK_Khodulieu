"""Conservative title-based relevance for electronic-components market intelligence.
Rules are explainable, NOT a trained NLP model. Priority: exclusions > indirect > direct.
"""
import re
import unicodedata

KEYWORDS = {
 'GPU': [r'\b(?:rtx|gtx)\s*\d{3,4}\b', r'\b(?:geforce|radeon\s+rx)\b', r'card\s+(?:đồ họa|màn hình)', r'\bgraphics card\b', r'\bgpu\b'],
 'CPU': [r'\b(?:cpu|ryzen|intel core|core i[3579])\b',r'\bvi xử lý\b',r'\bbộ xử lý\b'],
 'RAM': [r'\b(?:ram|dram|ddr[345]|camm2)\b',r'\bbộ nhớ ram\b'],
 'SSD': [r'\b(?:ssd|nvme|solid.state drive)\b',r'ổ cứng thể rắn'],
 'HDD': [r'\bhdd\b',r'ổ cứng cơ',r'\bhard disk\b'],
 'NETWORK': [r'\brouter\b',r'\bbộ định tuyến\b',r'\b(?:wifi|wi-fi)\s*[67]\b',r'\baccess point\b',r'\bswitch\s+(?:mạng|cisco)\b',r'thiết bị mạng',r'\b(?:tp-link|mercusys)\b'],
 'MONITOR':[r'màn hình máy tính',r'\bmonitor\b',r'\b(?:144|165|240)\s*hz\b',r'\bultragear\b'],
 'MOTHERBOARD':[r'\bmainboard\b',r'bo mạch chủ',r'\bmotherboard\b'],
 'PERIPHERAL':[r'bàn phím',r'chuột máy tính',r'\bkeyboard\b',r'\bmouse gaming\b'],
 'CAMERA':[r'\bwebcam\b',r'\b(?:camera|máy quay)\s+(?:ip|hikvision|ezviz|wifi|wi-fi|an ninh|giám sát)\b',r'\b(?:hikvision|ezviz|imou|camera)\b'],
 'PSU':[r'nguồn máy tính',r'\b(?:psu|power supply)\b',r'nguồn corsair'],
}
GENERAL_EXCLUDE = [r'\btiki.taka\b',r'\bcổ phiếu\b',r'\bchứng khoán\b',r'\bcrypto\b.*\bchứng khoán\b']
EXCLUDE_BY_CATEGORY = {
 'GPU':[r'\b(?:điện thoại|smartphone|galaxy\s+[as]\d+|iphone|chip điện thoại)\b',r'\b(?:cổ phiếu|chứng khoán)\b'],
 'CPU':[r'\b(?:cổ phiếu|chứng khoán)\b'],
 'NETWORK':[r'\b(?:wifi giả|wi-fi giả|lừa đảo|đánh cắp thông tin|mật khẩu wifi|tấn công mạng)\b'],
 'CAMERA':[r'\b(?:lắp đặt|lắp hơn|giám sát giao thông|xử lý nghiêm xe|phạt nguội|an ninh trật tự|công an|hệ thống camera giám sát ở|giám sát chợ|giám sát đường phố)\b',r'\b(?:điện thoại|smartphone|iphone|ipad|galaxy|oppo|reno|oneplus|tecno|xiaomi|redmi|realme|vivo|pixel|selfie|cụm camera|camera kép|camera sau|camera trước)\b',r'\b(?:xe ga|xe máy|ô tô|xe hơi|camera hành trình|dashcam|camera lùi)\b'],
}
INDIRECT_BY_CATEGORY={
 'RAM':[r'\bwindows\b',r'\bđiện thoại\b',r'\bsmartphone\b',r'\biphone\b',r'\b(?:galaxy|oppo|reno|oneplus|tecno|xiaomi|redmi|realme|vivo)\b'],
 'GPU':[r'\b(?:laptop|máy tính xách tay|rog strix|predator triton)\b'],
 'CPU':[r'\b(?:laptop|máy tính xách tay)\b'],
 'NETWORK':[r'\b(?:hạ tầng|triển khai|lắp đặt)\b'],
 'CAMERA':[r'\b(?:lắp đặt|hệ thống camera)\b'],
}
# Direct market/product information, not just an incidental term in a title.
MARKET_TERMS=[r'\bgiá\b',r'\btăng giá\b',r'\bgiảm giá\b',r'\bkhan hiếm\b',r'\bcháy hàng\b',r'\bbão giá\b',r'\bra mắt\b',r'\bgiới thiệu\b',r'\bcông bố\b',r'\bđánh giá\b',r'\bnhược điểm\b',r'\bso sánh\b',r'\bđáng mua\b',r'\bchọn mua\b',r'\bngừng sản xuất\b',r'\bđóng cửa\b',r'\bnhu cầu\b',r'\bsăn lùng\b',r'\blỗi\b',r'\bnguồn cung\b',r'\bthị trường\b',r'\bthế hệ mới\b',r'\btuổi thọ\b',r'\btráo\b',r'\bthiếu hụt\b',r'\bdung lượng\b',r'\bhiệu năng\b',r'\bnâng cấp\b',r'\bđắt\b',r'\brẻ\b']

def normalize(text):
 text=unicodedata.normalize('NFKC',str(text or '')).lower()
 return re.sub(r'\s+',' ',text).strip()

def matches(text,patterns):return any(re.search(p,text,re.I) for p in patterns)

def classify(title,source_domain='',suspicious=()):
 t=normalize(title)
 if not t:return {'level':'IRRELEVANT','categories':[],'reason':'EMPTY_TITLE'}
 if matches(t,GENERAL_EXCLUDE):return {'level':'IRRELEVANT','categories':[],'reason':'GENERAL_EXCLUSION'}
 matched=[cat for cat,terms in KEYWORDS.items() if matches(t,terms)]
 if not matched:return {'level':'IRRELEVANT','categories':[],'reason':'NO_PRODUCT_CATEGORY_IN_TITLE'}
 if source_domain in suspicious:return {'level':'IRRELEVANT','categories':matched,'reason':'SUSPECT_SOURCE_METADATA'}
 kept=[c for c in matched if not matches(t,EXCLUDE_BY_CATEGORY.get(c,[]))]
 if not kept:return {'level':'IRRELEVANT','categories':matched,'reason':'OUT_OF_SCOPE_CONTEXT'}
 indirect=[c for c in kept if matches(t,INDIRECT_BY_CATEGORY.get(c,[]))]
 direct=[c for c in kept if c not in indirect]
 if indirect and not direct:
  return {'level':'INDIRECT','categories':kept,'reason':'RELATED_DOWNSTREAM_DEVICE'}
 if direct and matches(t,MARKET_TERMS):
  return {'level':'DIRECT','categories':direct,'reason':'PRODUCT_WITH_MARKET_SIGNAL'}
 if direct and matches(t,[r'\b(?:rtx|gtx)\s*\d{3,4}\b',r'\b(?:ddr4|ddr5|ssd|nvme|ryzen)\b',r'\brouter\b',r'\bmainboard\b',r'bo mạch chủ']):
  return {'level':'DIRECT','categories':direct,'reason':'SPECIFIC_PRODUCT_MODEL'}
 return {'level':'INDIRECT','categories':kept,'reason':'RELATED_BUT_NO_DIRECT_MARKET_SIGNAL'}
