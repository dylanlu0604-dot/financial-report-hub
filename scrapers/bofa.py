import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    print("🔍 正在爬取 Bank of America (美國銀行) - 🎯 年月精準解析與名額限制模式...")
    reports = []
    seen_article_links = set()
    base_url = "https://institute.bankofamerica.com"
    
    target_urls = [
        "https://institute.bankofamerica.com/economic-insights.html",
        "https://institute.bankofamerica.com/sustainability.html",
        "https://institute.bankofamerica.com/transformation.html",
        "https://institute.bankofamerica.com/on-the-move.html"
    ]

    exclude_keywords = ['careers', 'privacy', 'subscribe', 'form crs', 'businesses & institutions', 'small business check', 'research distribution', 'daily insights', 'institute insights']

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            valid_articles = []
            
            # ==========================================
            # 第一階段：掃描 4 個主分類頁，收集文章連結與【日期解析】
            # ==========================================
            for url in target_urls:
                print(f"  📂 正在掃描主頁面: {url.split('/')[-1]}")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(2000)
                    
                    soup = BeautifulSoup(page.content(), 'html.parser')
                    category_count = 0
                    
                    for a in soup.find_all('a', href=True):
                        if category_count >= 7:
                            break
                            
                        href = a.get('href', '')
                        if href.startswith('#') or href.startswith('javascript'):
                            continue
                            
                        full_url = urljoin(base_url, href)
                        
                        if full_url not in target_urls and '.html' in full_url:
                            raw_title = clean_text(a.get_text(separator=' '))
                            
                            if any(kw in raw_title.lower() for kw in exclude_keywords):
                                continue
                            
                            if full_url not in seen_article_links and len(raw_title) > 5:
                                
                                # 🌟 預設日期為今天，並保留原始標題
                                report_date = datetime.now().strftime("%Y-%m-%d")
                                clean_title = raw_title
                                
                                # 🌟 日期魔法：用 Regex 抓取開頭的 "march 2026", "february 2026"
                                date_match = re.search(r'^(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})\s*', raw_title, re.IGNORECASE)
                                
                                if date_match:
                                    # 取月份前三碼(例如 Mar)與年份
                                    month_str = date_match.group(1)[:3].title() 
                                    year_str = date_match.group(2)
                                    try:
                                        # 將文字轉為時間物件，並強制補上 1 號 (例如 2026-03-01)
                                        date_obj = datetime.strptime(f"{month_str} {year_str}", "%b %Y")
                                        report_date = date_obj.strftime("%Y-%m-01")
                                        # 把標題前面的日期文字切掉，還原乾淨標題
                                        clean_title = raw_title[date_match.end():].strip()
                                    except:
                                        pass
                                
                                # 存入待爬清單，這次多了 report_date
                                valid_articles.append((clean_title, full_url, report_date))
                                seen_article_links.add(full_url)
                                category_count += 1
                                
                except Exception as e:
                    print(f"  ⚠️ 主分類頁面載入異常: {e}")
            
            print(f"  👉 共收集到 {len(valid_articles)} 篇潛在文章，準備進入挖掘 PDF...")
            
            # ==========================================
            # 第二階段：點進每一篇文章，尋找隱藏的 PDF 載點
            # ==========================================
            for title, article_url, report_date in valid_articles:
                print(f"    🕵️ 正在進入內頁: {title[:20]}... (解析日期: {report_date})")
                try:
                    page.goto(article_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(1500)
                    
                    article_soup = BeautifulSoup(page.content(), 'html.parser')
                    
                    pdf_href = None
                    
                    for a_tag in article_soup.find_all('a', href=True):
                        href_val = a_tag.get('href', '')
                        
                        if '.pdf' in href_val.lower() or '/content/dam/' in href_val.lower():
                            pdf_href = href_val
                            break
                    
                    if pdf_href:
                        full_pdf_url = urljoin(base_url, pdf_href)
                        reports.append({
                            "Source": "Bank of America",
                            "Date": report_date,  # 🌟 填入我們剛剛萃取出來的正確年月
                            "Name": title,        # 🌟 填入切除日期後的乾淨標題
                            "Link": full_pdf_url,
                            "Type": "PDF"
                        })
                        print(f"      ✅ 成功挖出實體 PDF！")
                    else:
                        print(f"      ⚠️ 此文章未包含 /content/dam/ PDF 連結，跳過。")
                        
                except Exception as e:
                    print(f"      ❌ 進入文章失敗: {str(e)[:30]}")
                    
            browser.close()
            
    except Exception as e:
        print(f"  ❌ Bank of America 爬取發生重大崩潰: {e}")

    print(f"  ✅ 美國銀行最終成功收錄 {len(reports)} 篇【真實 PDF 報告】")
    return reports

if __name__ == "__main__":
    scrape()
