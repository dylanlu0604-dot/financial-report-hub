import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    print("🔍 正在爬取 Refinitiv Lipper Alpha - 🎯 TJ Dhillon 企業財報 (智能日期防呆版)...")
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
            
            print("  👉 正在展開更多報告清單 (自動向下捲動與點擊 Load More)...")
            # 增加捲動與點擊次數，確保能涵蓋超過 30 天的報告量
            for _ in range(5): 
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)
                try:
                    load_more = page.locator("button:has-text('Load More'), a:has-text('Load More'), text='Load More', text='LOAD MORE', text='Load more', .load-more").first
                    if load_more.is_visible():
                        load_more.click()
                        page.wait_for_timeout(3500)
                except Exception:
                    pass
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            article_links = soup.find_all('a', href=True)
            valid_articles = []
            
            current_year = datetime.now().year
            current_month = datetime.now().month
            
            for a in article_links:
                href = a.get('href', '')
                full_url = urljoin(base_url, href)
                
                if '/contributor/' in href or href == '#' or 'javascript' in href.lower():
                    continue
                
                raw_title = clean_text(a.get_text(separator=' '))
                if len(raw_title) < 5:
                    parent_container = a.find_parent('article') or a.find_parent('div', class_=re.compile(r'post|entry', re.I))
                    if parent_container:
                        headings = parent_container.find_all(['h2', 'h3', 'h4'])
                        if headings:
                            raw_title = clean_text(headings[0].get_text())

                # 🌟 關鍵修正 1：完美支援 Feb. 27 或是 February. 27 這種帶有句點的格式
                date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?', raw_title, re.IGNORECASE)
                
                if not date_match:
                    continue
                    
                if full_url not in seen_links:
                    try:
                        month_str = date_match.group(1)[:3].title()
                        day_str = date_match.group(2)
                        year_str = date_match.group(3)
                        
                        # 🌟 關鍵修正 2：智能推算年份。如果標題沒寫年份，且月份大於現在的月份(例如現在是2月，文章寫5月)，那它一定是去年的文章！
                        if not year_str:
                            month_num = datetime.strptime(month_str, "%b").month
                            if month_num > current_month:
                                year_str = str(current_year - 1)
                            else:
                                year_str = str(current_year)
                        
                        date_obj = datetime.strptime(f"{month_str} {day_str}, {year_str}", "%b %d, %Y")
                        report_date = date_obj.strftime("%Y-%m-%d")
                        
                        clean_title = raw_title[:date_match.start()].strip()
                        clean_title = re.sub(r'^[|\- ]+|[|\- ]+$', '', clean_title).strip()
                        if not clean_title: 
                            clean_title = raw_title
                        
                        valid_articles.append((clean_title, report_date, full_url))
                        seen_links.add(full_url)
                    except Exception:
                        pass

            # 🌟 關鍵修正 3：解除 10 篇的緊箍咒，擴大到 30 篇，確保近期的報告一篇都不漏
            valid_articles = valid_articles[:30]
            print(f"  👉 找到 {len(valid_articles)} 篇附有日期的正確報告，準備抽取 PDF...")
            
            # ==========================================
            # 第二層：點進每一篇文章，開始挖掘 PDF 按鈕
            # ==========================================
            for title, article_date, article_url in valid_articles:
                print(f"    🕵️ 正在進入文章: {title[:30]}... (精準日期: {article_date})")
                try:
                    page.goto(article_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    
                    article_soup = BeautifulSoup(page.content(), 'html.parser')
                    
                    pdf_href = None
                    for a_tag in article_soup.find_all('a', href=True):
                        href_val = a_tag.get('href', '')
                        text_val = clean_text(a_tag.get_text()).lower()
                        
                        if '.pdf' in href_val.lower() or 'download the full report' in text_val or 'view the full report' in text_val or 'click here to view' in text_val:
                            pdf_href = href_val
                            break
                    
                    if pdf_href:
                        full_pdf_url = urljoin(base_url, pdf_href)
                        reports.append({
                            "Source": "Refinitiv Lipper",
                            "Date": article_date,
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
