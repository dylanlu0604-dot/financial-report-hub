import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from datetime import datetime, timedelta

# ================= 🔧 配置區域 =================
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

REPORT_WINDOW_DAYS = 45
CUTOFF_DATE = datetime.now() - timedelta(days=REPORT_WINDOW_DAYS)

# ================= 🛠️ 工具函數 =================
def parse_date(date_str):
    if not date_str or date_str == "未知日期":
        return None
    
    match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日?', date_str)
    if match:
        year, month, day = match.groups()
        try: return datetime(int(year), int(month), int(day))
        except: return None
    
    match = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', date_str)
    if match:
        year, month, day = match.groups()
        try: return datetime(int(year), int(month), int(day))
        except: return None
    
    match = re.search(r'(\d{4})年(\d{1,2})-(\d{1,2})', date_str)
    if match:
        year, start_month, end_month = match.groups()
        try:
            if int(end_month) in [1, 3, 5, 7, 8, 10, 12]: day = 31
            elif int(end_month) == 2: day = 28
            else: day = 30
            return datetime(int(year), int(end_month), day)
        except: return None
    
    match = re.search(r'(\d{4})年(\d{1})-(\d{1})', date_str)
    if match:
        year, start_month, end_month = match.groups()
        try:
            if int(end_month) in [1, 3, 5, 7, 8, 10, 12]: day = 31
            elif int(end_month) == 2: day = 28
            else: day = 30
            return datetime(int(year), int(end_month), day)
        except: return None
    
    return None

def is_within_reporting_window(date_str):
    date_obj = parse_date(date_str)
    if not date_obj:
        return True
    return date_obj >= CUTOFF_DATE

def fetch_real_pdf_link(page_url):
    if str(page_url).lower().endswith('.pdf') or "#" in page_url:
        return page_url
    try:
        response = requests.get(page_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        pdf_tag = soup.find('a', href=re.compile(r'\.pdf$', re.IGNORECASE))
        if not pdf_tag:
            pdf_tag = soup.find('a', string=re.compile(r'PDF', re.IGNORECASE))
        if pdf_tag:
            return urljoin(page_url, pdf_tag['href'])
        return page_url
    except:
        return page_url
