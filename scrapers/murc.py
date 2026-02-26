import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from scrapers.utils import HEADERS, is_within_30_days, fetch_real_pdf_link

def scrape():
    print("🔍 正在爬取 MURC (三菱UFJリサーチ＆コンサルティング)...")
    base_url = "https://www.murc.jp"
    target_url = "https://www.murc.jp/library/economyresearch/"
    reports = []
    
    try:
        resp = requests.get(target_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        links = soup.find_all('a', href=True)
        seen_hrefs = set() # 用來避免同一個頁面抓到重複的連結
        
        for tag in links:
            href = tag['href']
            title = tag.get_text(strip=True)
            
            # 1. 基本排除：太短的標題、或是已經處理過的連結
            if len(title) < 5: continue
            if href in seen_hrefs: continue
            
            # 2. 確認是否為報告連結 (必須包含 /library/ 或是 pdf 結尾)
            if "/library/" not in href and not href.lower().endswith('.pdf'):
                continue
                
            # 排除非報告的導覽列與分頁按鈕
            if any(kw in title for kw in ["一覧", "List", "検索", "カテゴリ", "次へ", "前へ", "お知らせ"]): 
                continue
            
            # 3. 嚴格尋找日期
            date_text = None
            parent = tag.find_parent()
            if parent:
                # 擴大搜尋範圍：找尋父節點與前一個節點的文字
                txt = parent.get_text()
                prev_sibling = parent.find_previous_sibling()
                if prev_sibling:
                    txt += " " + prev_sibling.get_text()
                    
                # 匹配精確格式：2026年02月16日 或 2026.02.16 或 2026/02/16
                match = re.search(r'20\d{2}[./年]\d{1,2}[./月]\d{1,2}日?', txt)
                if match: 
                    date_text = match.group(0)

            # 4. 核心過濾：找不到日期，或者超過 30 天，就直接踢除
            if not date_text:
                continue
            if not is_within_30_days(date_text):
                continue

            # 5. 加入清單並抓取真實 PDF 連結
            seen_hrefs.add(href)
            link = urljoin(base_url, href)
            final_pdf = fetch_real_pdf_link(link)
            
            reports.append({
                "Source": "MURC", 
                "Date": date_text, 
                "Name": title, 
                "Link": final_pdf
            })
                
    except Exception as e:
        print(f"  ❌ MURC 失敗: {e}")
    
    print(f"  ✅ MURC 找到 {len(reports)} 筆報告")
    return reports
