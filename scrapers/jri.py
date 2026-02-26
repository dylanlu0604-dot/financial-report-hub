import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from scrapers.utils import HEADERS, is_within_30_days, fetch_real_pdf_link

def scrape():
    print("🔍 正在爬取 JRI (Year List)...")
    base_url = "https://www.jri.co.jp"
    target_url = "https://www.jri.co.jp/report/year/"
    reports = []
    
    try:
        resp = requests.get(target_url, headers=HEADERS)
        soup = BeautifulSoup(resp.content, 'html.parser')
        links = soup.find_all('a', href=True)
        
        for tag in links:
            href = tag['href']
            title = tag.get_text(strip=True)
            
            # 1. 基本排除：太短、非報告的關鍵字
            if len(title) < 5: continue
            if any(kw in title for kw in ["一覧", "List", "YouTube", "Twitter", "採用", "お知らせ", "Column", "コラム"]): continue
            if href.startswith('#') or href.endswith('/'): continue
            
            # 2. 嚴格尋找日期
            date_text = None
            parent = tag.find_parent()
            if parent:
                # 擴大搜尋範圍：找尋父節點與前一個節點的文字
                txt = parent.get_text()
                prev_sibling = parent.find_previous_sibling()
                if prev_sibling:
                    txt += " " + prev_sibling.get_text()
                    
                # 匹配精確格式：2026年02月06日 或 2026.02.06
                match = re.search(r'20\d{2}[./年]\d{1,2}[./月]\d{1,2}日?', txt)
                if match: 
                    date_text = match.group(0)

            # 3. 核心修正：如果「找不到日期」，代表它絕對不是報告，直接跳過！
            if not date_text:
                continue
                
            # 4. 日期區間檢查（超過30天就過濾掉）
            if not is_within_30_days(date_text):
                continue

            # 5. 確保是報告的專屬連結格式 (排除一般網頁)
            if "page.jsp?id=" not in href and ".pdf" not in href.lower():
                continue

            link = urljoin(base_url, href)
            final_pdf = fetch_real_pdf_link(link)
            reports.append({"Source": "JRI", "Date": date_text, "Name": title, "Link": final_pdf})
                
    except Exception as e:
        print(f"  ❌ JRI 失敗: {e}")
    
    print(f"  ✅ JRI 找到 {len(reports)} 筆報告")
    return reports
