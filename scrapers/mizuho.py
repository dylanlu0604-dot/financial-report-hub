import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from datetime import datetime
from scrapers.utils import HEADERS, is_within_30_days, fetch_real_pdf_link

def scrape():
    print("🔍 正在爬取 Mizuho RT (瑞穗)...")
    base_url = "https://www.mizuho-rt.co.jp"
    current_year = datetime.now().year
    target_url = f"https://www.mizuho-rt.co.jp/publication/{current_year}/index.html"
    reports = []
    
    try:
        resp = requests.get(target_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        for item in soup.find_all('li'):
            date_match = re.search(r'20\d{2}年\d{1,2}月\d{1,2}日', item.get_text())
            if not date_match: continue
            date_text = date_match.group(0)
            
            if not is_within_30_days(date_text): continue
            
            link_tag = item.find('a', href=True)
            if not link_tag: continue
                
            title = link_tag.get_text(strip=True)
            if len(title) < 5 or any(kw in title for kw in ["Eyes", "週次版", "コラム"]): continue
            
            full_link = urljoin(base_url, link_tag['href'])
            final_pdf = full_link if full_link.endswith('.pdf') else fetch_real_pdf_link(full_link)
                
            reports.append({"Source": "Mizuho", "Date": date_text, "Name": title, "Link": final_pdf})
        
    except Exception as e:
        print(f"  ❌ Mizuho 失敗: {e}")
    
    print(f"  ✅ Mizuho 找到 {len(reports)} 筆報告")
    return reports
