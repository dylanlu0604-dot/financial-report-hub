import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    # 🌟 請認明這行字：日期標題完美解析版
    print("🔍 正在爬取 Goldman Sachs (高盛) - 🎯 深度挖掘與日期標題完美解析模式...")
    reports = []
    seen_links = set()
    base_url = "https://www.goldmansachs.com"
    target_url = "https://www.goldmansachs.com/insights/top-of-mind"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000) 
            except Exception as e:
                print(f"  ⚠️ 主頁載入超時，嘗試強制解析...")
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            article_links = soup.find_all('a', href=True)
            valid_articles = []
            
            exclude_keywords = ['exchanges', 'the markets', 'talks at gs', 'macroeconomics', 'explore insights', 'more +', 'subscribe', 'careers', 'privacy', 'terms']
            
            for a in article_links:
                href = a.get('href', '')
                
                # 🌟 修正 1：加上 separator=' '，確保不同標籤文字不會黏在一起
                raw_text = clean_text(a.get_text(separator=' '))
                
                clean_href = href.split('?')[0].rstrip('/')
                if clean_href in ['/insights/top-of-mind', '/insights', '/']:
                    continue
                    
                if '/insights/' in href:
                    # 🌟 修正 2：用正則表達式萃取日期 (例如 Feb 3, 2026)
                    date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),\s+(\d{4})', raw_text, re.IGNORECASE)
                    
                    report_date = datetime.now().strftime("%Y-%m-%d") # 預設今天
                    clean_title = raw_text

                    # 將英文日期轉為標準的 YYYY-MM-DD
                    if date_match:
                        try:
                            month_str = date_match.group(1)[:3].title()
                            day_str = date_match.group(2)
                            year_str = date_match.group(3)
                            date_obj = datetime.strptime(f"{month_str} {day_str}, {year_str}", "%b %d, %Y")
                            report_date = date_obj.strftime("%Y-%m-%d")
                            
                            # 把標題後面的日期文字切掉
                            clean_title = raw_text[:date_match.start()].strip()
                        except:
                            pass
                    
                    # 🌟 修正 3：切除標題前面重複的 "Top of Mind"
                    clean_title = re.sub(r'^(Top of Mind\s*-?\s*)+', '', clean_title, flags=re.IGNORECASE).strip()

                    # 過濾空標題或黑名單
                    if not clean_title or len(clean_title) < 5:
                        continue
                    if any(kw in clean_title.lower() for kw in exclude_keywords):
                        continue
                        
                    full_url = urljoin(base_url, href)
                    if full_url not in seen_links:
                        valid_articles.append((clean_title, report_date, full_url))
                        seen_links.add(full_url)

            valid_articles = valid_articles[:10]
            print(f"  👉 找到 {len(valid_articles)} 篇真實文章，準備挖掘 PDF...")
            
            # 2. 點進文章挖掘 PDF
            for title, article_date, article_url in valid_articles:
                print(f"    🕵️ 正在進入文章: {title[:20]}... ({article_date})")
                try:
                    page.goto(article_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    
                    article_soup = BeautifulSoup(page.content(), 'html.parser')
                    
                    pdf_href = None
                    for a_tag in article_soup.find_all('a', href=True):
                        href_val = a_tag.get('href', '')
                        text_val = clean_text(a_tag.get_text()).lower()
                        
                        if '.pdf' in href_val.lower() or 'download pdf' in text_val or 'download report' in text_val:
                            pdf_href = href_val
                            break
                    
                    if pdf_href:
                        full_pdf_url = urljoin(base_url, pdf_href)
                        reports.append({
                            "Source": "Goldman Sachs",
                            "Date": article_date, # 🌟 填入正確解析出來的日期
                            "Name": f"Top of Mind - {title}",
                            "Link": full_pdf_url,
                            "Type": "PDF" 
                        })
                        print(f"      ✅ 挖出實體 PDF 載點！")
                    else:
                        print(f"      ⚠️ 未提供官方 PDF 按鈕，跳過。")
                        
                except Exception as e:
                    print(f"      ❌ 進入文章失敗: {str(e)[:30]}")
                    
            browser.close()
            
    except Exception as e:
        print(f"  ❌ Goldman Sachs 爬取異常: {e}")

    print(f"  ✅ 高盛最終成功收錄 {len(reports)} 篇【真實 PDF 報告】")
    return reports

if __name__ == "__main__":
    scrape()
