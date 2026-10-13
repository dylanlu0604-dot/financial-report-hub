import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from scrapers.utils import HEADERS, is_within_reporting_window

def scrape():
    print("🔍 正在爬取 DIR (大和總研)...")
    base_url = "https://www.dir.co.jp"
    target_url = "https://www.dir.co.jp/report/research/economics/index.html"
    reports = []
    
    try:
        resp = requests.get(target_url, headers=HEADERS, timeout=15)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        news_list = soup.find('ul', class_='c-newsList')
        if not news_list: return reports
        
        for item in news_list.find_all('li', class_='c-newsList-item'):
            link_tag = item.find('a', class_='c-newsList-link')
            if not link_tag or not link_tag.get('href'): continue
            
            title_tag = link_tag.find('p', class_='title')
            if not title_tag: continue
            title = title_tag.get_text(strip=True)
            
            date_tag = link_tag.find('p', class_='date')
            date_text = date_tag.get_text(strip=True) if date_tag else "未知日期"
            
            if not is_within_reporting_window(date_text) or len(title) < 5 or any(kw in title for kw in ["データブック", "週次"]): continue
            
            pdf_url = link_tag.get('href').replace('.html', '.pdf')
            final_pdf = urljoin(base_url, pdf_url)
            
            reports.append({"Source": "DIR", "Date": date_text, "Name": title, "Link": final_pdf})
        
    except Exception as e:
        print(f"  ❌ DIR 失敗: {e}")
    
    print(f"  ✅ DIR 找到 {len(reports)} 筆報告")
    return reports
