import re
from urllib.parse import urljoin
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    print("🔍 正在爬取 Hankyung Consensus (韓國經濟共識) - 🎯 韓股指定標的 (過去 30 天)...")
    reports = []
    seen_links = set()
    base_url = "https://consensus.hankyung.com"
    
    # 🌟 自動計算過去 30 天的日期區間
    today = datetime.now()
    end_date = today.strftime("%Y-%m-%d")
    start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    
    # 您的韓股標的清單
    tickers = ['005930', '000660', '005380', '373220', '402340', '207940', '000270', '034020', '329180', '012450']

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 遍歷每一個股票代碼
            for ticker in tickers:
                print(f"  👉 正在搜尋標的代碼：{ticker} ...")
                
                # 組合 API 查詢網址
                target_url = f"https://consensus.hankyung.com/analysis/list?sdate={start_date}&edate={end_date}&now_page=1&search_value=&report_type=&pagenum=80&search_text={ticker}&business_code="
                
                try:
                    # 進入列表頁面
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1500) # 給予一點緩衝時間讓表格渲染
                    
                    soup = BeautifulSoup(page.content(), 'html.parser')
                    
                    # 尋找表格中的所有資料列 (tr)
                    rows = soup.select('table tbody tr')
                    
                    for tr in rows:
                        # 排除「查無資料 (nodata)」的空行
                        if "nodata" in tr.get('class', []) or tr.select_one('.nodata'):
                            continue
                            
                        tds = tr.select('td')
                        if len(tds) < 4:
                            continue
                            
                        # 1. 抓取日期 (通常在第 1 欄)
                        date_str = tds[0].get_text(strip=True)
                        
                        # 2. 抓取標題 (通常在第 2 欄)
                        title = clean_text(tds[1].get_text(separator=" ", strip=True))
                        
                        # 3. 抓取 PDF 連結 (尋找包含 downpdf 的下載點)
                        # Hankyung 的 PDF 網址通常長這樣: /apps.analysis/analysis.downpdf?report_idx=12345
                        pdf_tag = tr.find('a', href=re.compile(r'downpdf|\.pdf'))
                        if not pdf_tag:
                            continue
                            
                        href = pdf_tag.get('href')
                        full_url = urljoin(base_url, href)
                        
                        # 過濾重複並加入清單
                        if full_url not in seen_links:
                            reports.append({
                                "Source": f"Hankyung ({ticker})",
                                "Date": date_str,
                                "Name": title,
                                "Link": full_url
                            })
                            seen_links.add(full_url)
                            print(f"    ✅ 收錄報告: [{ticker}] {title[:20]}...")
                            
                except Exception as e:
                    print(f"    ⚠️ 抓取 {ticker} 時發生錯誤: {e}")
                    
            browser.close()
            
    except Exception as e:
        print(f"  ❌ Hankyung 爬取發生異常: {e}")

    print(f"  ✅ Hankyung 最終成功收錄 {len(reports)} 筆韓國券商報告")
    return reports

if __name__ == "__main__":
    scrape()
