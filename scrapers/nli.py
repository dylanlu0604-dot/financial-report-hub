import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import urljoin
from scrapers.utils import HEADERS, fetch_real_pdf_link

def scrape():
    print("🔍 正在爬取 NLI (ニッセイ)...")
    base_url = "https://www.nli-research.co.jp"
    list_url = "https://www.nli-research.co.jp/report_category/tag_category_id=6?site=nli"
    reports = []
    
    try:
        resp = requests.get(list_url, headers=HEADERS)
        soup = BeautifulSoup(resp.content, 'html.parser')
        articles = soup.find_all('a', href=re.compile(r'/report/detail/'))
        
        for idx, tag in enumerate(articles[:30]):
            title = tag.get_text(strip=True)
            if not title: continue
            
            link = urljoin(base_url, tag['href'])
            date_text = "待確認"
            try:
                detail_resp = requests.get(link, headers=HEADERS, timeout=10)
                detail_soup = BeautifulSoup(detail_resp.content, 'html.parser')
                date_match = re.search(r'20\d{2}年\d{1,2}月\d{1,2}日', detail_soup.get_text())
                if date_match: date_text = date_match.group(0)
                time.sleep(0.5)
            except: pass
            
            final_pdf = fetch_real_pdf_link(link)
            reports.append({"Source": "NLI", "Date": date_text, "Name": title, "Link": final_pdf})
            
    except Exception as e:
        print(f"  ❌ NLI 失敗: {e}")
    
    print(f"  ✅ NLI 找到 {len(reports)} 筆報告")
    return reports
