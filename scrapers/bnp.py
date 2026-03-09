import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

# ==========================================
# 🛠️ 輔助工具：解析 RSS 標準日期格式
# ==========================================
def parse_rss_date(date_str):
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
    try:
        # 自動處理 "Mon, 02 Mar 2026 00:00:00 GMT" 轉換為 "2026-03-02"
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")

# ==========================================
# 🕷️ 主爬蟲程式 (BNP Paribas 統一輸出版)
# ==========================================
def scrape():
    print("🔍 正在爬取 BNP Paribas (法國巴黎銀行) - 🚀 啟動 RSS 訂閱與統一輸出模式...")
    reports = []
    seen_pdfs = set()
    download_path = os.path.abspath("all report pdf")
    os.makedirs(download_path, exist_ok=True)
    
    # 12 個 RSS 訂閱來源
    rss_feeds = [
        "https://economic-research.bnpparibas.com/RSS/en-US/Eco-Flash",
        "https://economic-research.bnpparibas.com/RSS/en-US/Eco-Perspectives",
        "https://economic-research.bnpparibas.com/RSS/en-US/Eco-Week",
        "https://economic-research.bnpparibas.com/RSS/en-US/Eco-Emerging",
        "https://economic-research.bnpparibas.com/RSS/en-US/Eco-Charts",
        "https://economic-research.bnpparibas.com/RSS/en-US/Charts-of-the-Week",
        "https://economic-research.bnpparibas.com/RSS/en-US/Eco-Brief",
        "https://economic-research.bnpparibas.com/RSS/en-US/Eco-Pulse",
        "https://economic-research.bnpparibas.com/RSS/en-US/Special-Edition",
        "https://economic-research.bnpparibas.com/RSS/en-US/Scenario-and-forecasts",
        "https://economic-research.bnpparibas.com/RSS/en-US/Eco-Insight",
        "https://economic-research.bnpparibas.com/RSS/en-US/Tariff-tracker"
    ]
    
    base_url = "https://economic-research.bnpparibas.com"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                accept_downloads=True
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            for feed_url in rss_feeds:
                cat_name = feed_url.split("/")[-1].replace("-", " ")
                print(f"\n  🌐 正在解析 RSS 分類: {cat_name}...")
                
                try:
                    # 1. 抓取 RSS XML
                    response = context.request.get(feed_url)
                    if response.status != 200:
                        print(f"    ⚠️ RSS 載入失敗 (HTTP {response.status})")
                        continue
                        
                    xml_content = response.text()
                    root = ET.fromstring(xml_content)
                    items = root.findall(".//item")
                    
                    # 每個 RSS 分類安全取前 5 篇最新報告
                    top_items = items[:5]
                    print(f"    🎯 鎖定前 {len(top_items)} 篇...")
                    
                    for item in top_items:
                        title_el = item.find("title")
                        link_el = item.find("link")
                        pubdate_el = item.find("pubDate")
                        
                        raw_title = title_el.text.strip() if title_el is not None else "Unknown Title"
                        article_url = link_el.text.strip() if link_el is not None else ""
                        pub_date_str = pubdate_el.text.strip() if pubdate_el is not None else ""
                        
                        final_date = parse_rss_date(pub_date_str)
                        safe_title = re.sub(r'[\\/*?:"<>|]', "_", f"{raw_title} ({final_date})").strip()
                        local_filename = f"{safe_title}.pdf"
                        save_path = os.path.join(download_path, local_filename)
                        
                        if not article_url:
                            continue
                            
                        print(f"    🔎 進入文章尋找 PDF: {raw_title[:25]}... ({final_date})")
                        
                        try:
                            # 進入文章內頁 (重試機制)
                            for attempt in range(2):
                                try:
                                    page.goto(article_url, wait_until="domcontentloaded", timeout=20000)
                                    page.wait_for_timeout(1000)
                                    break
                                except Exception:
                                    if attempt == 1: raise
                            
                            # 2. 🌟 核心：透過 user 指定的 <link rel="alternate"> 格式直接替換出 PDF 網址
                            pdf_link = page.evaluate("""
                                () => {
                                    // 尋找 alternate 標籤，並將 /html/ 替換為 /pdf/
                                    let altLink = document.querySelector('link[rel="alternate"][hreflang="en"]');
                                    if (altLink && altLink.href && altLink.href.includes('/html/')) {
                                        return altLink.href.replace('/html/', '/pdf/');
                                    }
                                    
                                    // 備案：直接尋找頁面上的 PDF 連結
                                    let pdfBtn = document.querySelector('a[href*="/pdf/"], a[href$=".pdf"]');
                                    if (pdfBtn) {
                                        return pdfBtn.href;
                                    }
                                    return null;
                                }
                            """)
                            
                            if pdf_link:
                                pdf_url = urllib.parse.urljoin(base_url, pdf_link)
                                
                                if pdf_url in seen_pdfs: 
                                    print(f"      ⏩ [跳過] 檔案已處理過")
                                    continue
                                seen_pdfs.add(pdf_url)
                                
                                # 3. 執行物理下載
                                pdf_res = context.request.get(pdf_url, headers={"Referer": article_url})
                                if pdf_res.status == 200 and b'%PDF' in pdf_res.body()[:10]:
                                    with open(save_path, "wb") as f:
                                        f.write(pdf_res.body())
                                        
                                    reports.append({
                                        "Source": "BNP Paribas", # 🌟 統一標記，不分類
                                        "Date": final_date,
                                        "Name": f"{raw_title} ({final_date})",
                                        "Link": pdf_url, 
                                        "Type": "PDF"
                                    })
                                    print(f"      ✅ [實體下載成功]")
                                else:
                                    print(f"      ❌ [下載失敗] 檔案無效或遭阻擋 (HTTP {pdf_res.status})")
                            else:
                                print(f"      ❌ [跳過] 頁面內找不到您指定的 PDF 連結結構")
                                
                        except Exception as e:
                            print(f"      ⚠️ 處理文章超時: {str(e)[:25]}")
                            
                except Exception as e:
                    print(f"    ⚠️ 解析 RSS 失敗: {str(e)[:25]}")
                    
            browser.close()
            
    except Exception as e:
        print(f"  ❌ BNP Paribas 爬取總體異常: {e}")

    print(f"  ✅ 任務結束：總共實體收錄 {len(reports)} 篇 BNP Paribas 報告")
    return reports

if __name__ == "__main__":
    scrape()
