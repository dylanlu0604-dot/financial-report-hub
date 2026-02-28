import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    print("🔍 正在爬取 Refinitiv Lipper Alpha - 🎯 TJ Dhillon 企業財報追蹤 (兩層式深入點擊)...")
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
            # 第一層：進入主頁，收集「文章網址」
            # ==========================================
            try:
                # Refinitiv 的網站有時載入較慢，使用 domcontentloaded 提升效率
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000) 
            except Exception:
                print("  ⚠️ 主頁載入超時，嘗試強制解析現有畫面...")
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            
            # 尋找頁面上的所有連結
            article_links = soup.find_all('a', href=True)
            valid_articles = []
            
            # 過濾掉雜訊、導覽列、作者頁面等
            exclude_keywords = ['privacy', 'cookie', 'terms', 'contact', 'about', 'author', 'category', 'tag']
            
            for a in article_links:
                href = a.get('href', '')
                full_url = urljoin(base_url, href)
                
                # 只保留網址中帶有年份月份 (例如 /2023/10/ 或 /reports/) 的可能文章連結，或者排除明顯非文章的網址
                clean_href = href.split('?')[0].rstrip('/')
                if any(kw in clean_href.lower() for kw in exclude_keywords) or clean_href.endswith('tj-dhillon'):
                    continue
                
                raw_title = clean_text(a.get_text(separator=' '))
                
                # 如果 <a> 標籤本身沒有文字，試著從外層找 (例如點擊圖片的連結)
                if len(raw_title) < 5:
                    parent_container = a.find_parent('article') or a.find_parent('div', class_=re.compile(r'post|entry', re.I))
                    if parent_container:
                        headings = parent_container.find_all(['h2', 'h3', 'h4'])
                        if headings:
                            raw_title = clean_text(headings[0].get_text())

                # 過濾過短的標題
                if len(raw_title) > 10 and full_url not in seen_links:
                    # 嘗試從標題或是外層抓取日期 (例如 May 5, 2022)
                    container = a.find_parent('article') or a.find_parent('li') or a.parent
                    parent_text = clean_text(container.get_text(separator=' ')) if container else raw_title
                    
                    date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),\s+(\d{4})', parent_text, re.IGNORECASE)
                    
                    report_date = datetime.now().strftime("%Y-%m-%d") # 預設今天
                    if date_match:
                        try:
                            month_str = date_match.group(1)[:3].title()
                            date_obj = datetime.strptime(f"{month_str} {date_match.group(2)}, {date_match.group(3)}", "%b %d, %Y")
                            report_date = date_obj.strftime("%Y-%m-%d")
                        except Exception:
                            pass

                    # 如果這個連結看起來像是一篇實質文章，就存入清單
                    valid_articles.append((raw_title, report_date, full_url))
                    seen_links.add(full_url)

            # 只取前 10 篇最新的報告，避免爬取過久
            valid_articles = valid_articles[:10]
            print(f"  👉 找到 {len(valid_articles)} 篇報告文章，準備逐一點擊進入尋找 PDF...")
            
            # ==========================================
            # 第二層：點進每一篇文章，開始挖掘 PDF 按鈕
            # ==========================================
            for title, article_date, article_url in valid_articles:
                print(f"    🕵️ 正在進入文章: {title[:25]}... ({article_date})")
                try:
                    page.goto(article_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    
                    article_soup = BeautifulSoup(page.content(), 'html.parser')
                    
                    # 掃描網頁中所有的超連結，尋找 PDF 下載點
                    pdf_href = None
                    for a_tag in article_soup.find_all('a', href=True):
                        href_val = a_tag.get('href', '')
                        text_val = clean_text(a_tag.get_text()).lower()
                        
                        # 只要網址有 .pdf 或按鈕寫著 download full report
                        if '.pdf' in href_val.lower() or 'download the full report' in text_val or 'view the full report' in text_val:
                            pdf_href = href_val
                            break
                    
                    if pdf_href:
                        full_pdf_url = urljoin(base_url, pdf_href)
                        reports.append({
                            "Source": "Refinitiv (Lipper)",
                            "Date": article_date,
                            "Name": f"Refinitiv - {title[:60]}",
                            "Link": full_pdf_url,
                            "Type": "PDF"
                        })
                        print(f"      ✅ 成功挖出實體 PDF 載點！")
                    else:
                        print(f"      ⚠️ 內頁未提供官方 PDF，已標記為【網頁轉印模式】")
                        # 如果沒有附 PDF (有些短評只有網頁文字)，就交給 main.py 印成 PDF
                        reports.append({
                            "Source": "Refinitiv (Lipper)",
                            "Date": article_date,
                            "Name": f"Refinitiv - {title[:60]}",
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
