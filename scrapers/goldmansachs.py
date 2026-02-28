import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    print("🔍 正在爬取 Goldman Sachs (高盛) - 🎯 深度尋找真實 PDF 按鈕模式 (修正超時與導覽列)...")
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
            
            # 1. 進入 Top of Mind 列表主頁 (🌟 改用 domcontentloaded 避免超時卡死)
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000) # 給網頁 3 秒鐘渲染文章清單
            except Exception as e:
                print(f"  ⚠️ 主頁載入超時，嘗試強制解析已載入的部分...")
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            
            # 尋找所有文章連結 (通常放在 /insights/ 之下)
            article_links = soup.find_all('a', href=re.compile(r'/insights/.*'))
            valid_articles = []
            
            # 🌟 排除名單：過濾掉網頁上方的「導覽列選單」，只抓真正的文章
            exclude_keywords = ['exchanges', 'the markets', 'talks at gs', 'macroeconomics', 'explore insights', 'more +']
            
            for a in article_links:
                href = a.get('href')
                title = clean_text(a.get_text())
                
                # 過濾掉無效連結、標題，或是導覽列按鈕
                if not title or len(title) < 5 or 'top-of-mind' in href:
                    continue
                    
                if any(kw in title.lower() for kw in exclude_keywords):
                    continue
                    
                full_url = urljoin(base_url, href)
                if full_url not in seen_links:
                    valid_articles.append((title, full_url))
                    seen_links.add(full_url)

            # 設定處理上限為前 10 篇
            valid_articles = valid_articles[:10]
            print(f"  👉 找到 {len(valid_articles)} 篇真實文章，準備進入內頁挖掘官方 PDF...")
            
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            # 2. 點進每一篇文章，開始尋找真實的 PDF 按鈕
            for title, article_url in valid_articles:
                print(f"    🕵️ 正在進入文章: {title[:20]}...")
                try:
                    # 🌟 同樣改為 domcontentloaded 避免內頁卡死，並加上 try...except 防護
                    page.goto(article_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    
                    article_soup = BeautifulSoup(page.content(), 'html.parser')
                    
                    # 暴力掃描所有超連結，尋找「下載 PDF」的蛛絲馬跡
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
                            "Date": today_str,
                            "Name": f"Top of Mind - {title}",
                            "Link": full_pdf_url,
                            "Type": "PDF" 
                        })
                        print(f"      ✅ 成功挖出實體 PDF 載點！")
                    else:
                        print(f"      ⚠️ 這篇文章未提供官方 PDF 按鈕，直接跳過。")
                        
                except Exception as e:
                    print(f"      ❌ 進入文章失敗: {str(e)[:30]}")
                    
            browser.close()
            
    except Exception as e:
        print(f"  ❌ Goldman Sachs 爬取異常: {e}")

    print(f"  ✅ 高盛最終成功收錄 {len(reports)} 篇【真實 PDF 報告】")
    return reports

if __name__ == "__main__":
    scrape()
