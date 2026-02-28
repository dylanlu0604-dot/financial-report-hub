import re
from urllib.parse import urljoin
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    print("🔍 正在爬取 Hankyung Consensus - 🎯 韓股精準標題模式...")
    reports = []
    seen_links = set()
    base_url = "https://consensus.hankyung.com"
    
    today = datetime.now()
    end_date = today.strftime("%Y-%m-%d")
    start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    
    tickers = ['005930', '000660', '005380', '373220', '402340', '207940', '000270', '034020', '329180', '012450']

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            Stealth().apply_stealth_sync(page)
            
            for ticker in tickers:
                target_url = f"https://consensus.hankyung.com/analysis/list?sdate={start_date}&edate={end_date}&now_page=1&search_value=&report_type=&pagenum=80&search_text={ticker}&business_code="
                
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000) 
                    
                    soup = BeautifulSoup(page.content(), 'html.parser')
                    rows = soup.select('table tbody tr')
                    
                    for tr in rows:
                        if "nodata" in tr.get('class', []) or tr.select_one('.nodata'):
                            continue
                            
                        tds = tr.select('td')
                        if len(tds) < 6: continue
                            
                        # 1. 日期
                        date_str = tds[0].get_text(strip=True)
                        
                        # 🌟 2. 修正標題：抓取「公司名稱」+「報告主題」
                        company_name = clean_text(tds[2].get_text(strip=True)) # 第三欄通常是公司名
                        raw_title = clean_text(tds[1].get_text(strip=True))   # 第二欄是報告主題
                        
                        # 組合成唯一名稱：[代碼] 公司名 - 報告標題
                        full_title = f"[{ticker}] {company_name} - {raw_title}"
                        
                        # 3. PDF 連結
                        pdf_tag = tr.find('a', href=re.compile(r'downpdf'))
                        if not pdf_tag: continue
                            
                        full_url = urljoin(base_url, pdf_tag.get('href'))
                        
                        if full_url not in seen_links:
                            reports.append({
                                "Source": f"Hankyung",
                                "Date": date_str,
                                "Name": full_title, # 使用組合後的唯一標題
                                "Link": full_url
                            })
                            seen_links.add(full_url)
                            print(f"    ✅ 收錄: {full_title[:30]}...")
                            
                except Exception as e:
                    print(f"    ⚠️ 搜尋 {ticker} 異常")
                    
            browser.close()
    except Exception as e:
        print(f"  ❌ 爬取異常: {e}")

    return reports
