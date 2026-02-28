import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    # 🌟 請認明這行：精準過濾與自動翻頁版
    print("🔍 正在爬取 Refinitiv Lipper Alpha - 🎯 TJ Dhillon 企業財報 (精準過濾與 Load More 版)...")
    reports = []
    seen_links = set()
    base_url = "https://lipperalpha.refinitiv.com"
    target_url = "https://lipperalpha.refinitiv.com/contributor/tj-dhillon/"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # ==========================================
            # 第一層：進入主頁，並點擊 Load More 載入更多
            # ==========================================
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000) 
            except Exception:
                pass
            
            # 🌟 關鍵修正 1：自動向下捲動並點擊 Load More 按鈕 (執行 4 次，抓滿 30 天絕對夠)
            print("  👉 正在展開更多報告清單 (自動向下捲動與點擊 Load More)...")
            for _ in range(4):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)
                try:
                    # 尋找畫面上各種可能的 Load More 按鈕
                    load_more = page.locator("button:has-text('Load More'), a:has-text('Load More'), text='Load More', text='LOAD MORE', text='Load more'").first
                    if load_more.is_visible():
                        load_more.click()
                        page.wait_for_timeout(3000) # 給網頁 3 秒鐘載入新文章
                except Exception:
                    pass
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            article_links = soup.find_all('a', href=True)
            valid_articles = []
            
            current_year = datetime.now().year
            
            for a in article_links:
                href = a.get('href', '')
                full_url = urljoin(base_url, href)
                
                # 排除明顯非文章網址
                if '/contributor/' in href or href == '#' or 'javascript' in href.lower():
                    continue
                
                raw_title = clean_text(a.get_text(separator=' '))
                if len(raw_title) < 5:
                    parent_container = a.find_parent('article') or a.find_parent('div', class_=re.compile(r'post|entry', re.I))
                    if parent_container:
                        headings = parent_container.find_all(['h2', 'h3', 'h4'])
                        if headings:
                            raw_title = clean_text(headings[0].get_text())

                # 🌟 關鍵修正 2：貫徹黃金守則「標題裡面有日期的才是真報告」
                # 解析標題中的日期，格式支援：May 5 或 May. 5, 2022
                date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z\.]*\s+(\d{1,2})(?:,?\s+(\d{4}))?', raw_title, re.IGNORECASE)
                
                # 🚨 如果標題裡面沒有日期，直接無情淘汰，絕對不收錄！
                if not date_match:
                    continue
                    
                if full_url not in seen_links:
                    try:
                        month_str = date_match.group(1)[:3].title()
                        day_str = date_match.group(2)
                        # 如果標題沒有寫年份 (例如只寫 May 5)，就自動補上今年
                        year_str = date_match.group(3) if date_match.group(3) else str(current_year)
                        
                        date_obj = datetime.strptime(f"{month_str} {day_str}, {year_str}", "%b %d, %Y")
                        report_date = date_obj.strftime("%Y-%m-%d")
                        
                        # 把標題後面的「 | May 5」切掉，保持報告名稱乾淨
                        clean_title = raw_title[:date_match.start()].strip()
                        clean_title = re.sub(r'^[|\- ]+|[|\- ]+$', '', clean_title).strip()
                        
                        if clean_title:
                            valid_articles.append((clean_title, report_date, full_url))
                            seen_links.add(full_url)
                    except Exception:
                        pass

            print(f"  👉 找到 {len(valid_articles)} 篇附有日期的正確報告，準備抽取 PDF...")
            
            # ==========================================
            # 第二層：點進每一篇文章，開始挖掘 PDF 按鈕
            # ==========================================
            for title, article_date, article_url in valid_articles:
                print(f"    🕵️ 正在進入文章: {title[:20]}... (標題日期: {article_date})")
                try:
                    page.goto(article_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    
                    article_soup = BeautifulSoup(page.content(), 'html.parser')
                    
                    pdf_href = None
                    for a_tag in article_soup.find_all('a', href=True):
                        href_val = a_tag.get('href', '')
                        text_val = clean_text(a_tag.get_text()).lower()
                        
                        # 尋找 Download the full report 或是 .pdf 結尾的連結
                        if '.pdf' in href_val.lower() or 'download the full report' in text_val or 'view the full report' in text_val or 'click here to view' in text_val:
                            pdf_href = href_val
                            break
                    
                    if pdf_href:
                        full_pdf_url = urljoin(base_url, pdf_href)
                        reports.append({
                            "Source": "Refinitiv Lipper",
                            "Date": article_date, # 🌟 使用從標題解析出來的絕對精準日期
                            "Name": f"Lipper - {title[:60]}",
                            "Link": full_pdf_url,
                            "Type": "PDF"
                        })
                        print(f"      ✅ 成功挖出實體 PDF！")
                    else:
                        print(f"      ⚠️ 未提供官方 PDF，標記為【網頁轉印】")
                        reports.append({
                            "Source": "Refinitiv Lipper",
                            "Date": article_date,
                            "Name": f"Lipper - {title[:60]}",
                            "Link": article_url,
                            "Type": "Web"
                        })
                        
                except Exception as e:
                    print(f"      ❌ 進入文章失敗: {str(e)[:30]}")
                    
            browser.close()
            
    except Exception as e:
        print(f"  ❌ Refinitiv 爬取異常: {e}")

    print(f"  ✅ Refinitiv (Lipper) 最終成功收錄 {len(reports)} 篇報告")
    return reports

if __name__ == "__main__":
    scrape()
