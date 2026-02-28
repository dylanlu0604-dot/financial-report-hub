import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    print("🔍 正在爬取 Goldman Sachs (高盛) - 🎯 Top of Mind 報告 (最新 10 篇)...")
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
            
            # 1. 進入 Top of Mind 列表主頁
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000) # 給網頁 3 秒鐘渲染文章列表
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            
            # 尋找所有包含 insights 的文章連結
            article_links = soup.find_all('a', href=True)
            valid_articles = []
            
            for a in article_links:
                href = a.get('href')
                title = clean_text(a.get_text())
                
                # 過濾出真正的文章連結 (排除首頁、按鈕或無意義短連結)
                if '/insights/' in href and 'top-of-mind' not in href and len(title) > 5:
                    full_url = urljoin(base_url, href)
                    if full_url not in seen_links:
                        valid_articles.append((title, full_url))
                        seen_links.add(full_url)

            # 限制只處理前 10 篇，避免執行過久
            valid_articles = valid_articles[:10]
            print(f"  👉 找到 {len(valid_articles)} 篇潛在文章，準備進入點擊尋找 PDF...")
            
            # 取得今天的日期，確保能通過 main.py 的 30 天防線
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            # 2. 點進每一篇文章，尋找真實的 PDF 載點
            for title, article_url in valid_articles:
                print(f"    🕵️ 正在檢查: {title[:25]}...")
                try:
                    page.goto(article_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    article_soup = BeautifulSoup(page.content(), 'html.parser')
                    
                    # 尋找網頁內是否有實體 PDF 連結 (href 包含 .pdf)
                    pdf_link = article_soup.find('a', href=re.compile(r'\.pdf', re.IGNORECASE))
                    
                    if pdf_link:
                        # 路線 A：這篇文章有提供官方 PDF
                        pdf_href = urljoin(base_url, pdf_link.get('href'))
                        reports.append({
                            "Source": "Goldman Sachs",
                            "Date": today_str,
                            "Name": f"Top of Mind - {title}",
                            "Link": pdf_href,
                            "Type": "PDF"
                        })
                        print(f"      ✅ 成功找到官方實體 PDF！")
                    else:
                        # 路線 B：這篇文章只有網頁版，交給 main.py 把它列印成 PDF
                        reports.append({
                            "Source": "Goldman Sachs",
                            "Date": today_str,
                            "Name": f"Top of Mind - {title}",
                            "Link": article_url,
                            "Type": "Web" 
                        })
                        print(f"      🌐 無官方 PDF，已標記為【網頁轉印模式】")
                        
                except Exception as e:
                    print(f"      ❌ 進入文章失敗: {str(e)[:30]}")
                    
            browser.close()
            
    except Exception as e:
        print(f"  ❌ Goldman Sachs 爬取異常: {e}")

    print(f"  ✅ 高盛最終成功收錄 {len(reports)} 篇報告")
    return reports

if __name__ == "__main__":
    scrape()
