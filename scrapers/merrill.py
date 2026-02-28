import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    print("🔍 正在爬取 Merrill Lynch (美林) - 🎯 PDF 網址精準日期萃取模式...")
    reports = []
    seen_links = set()
    base_url = "https://www.ml.com"
    target_url = "https://www.ml.com/capital-market-outlook.html"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # ==========================================
            # 第一層：進入主頁，收集「文章網址」與「標題」
            # ==========================================
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                pass 
                
            print("  👉 正在等待主頁渲染文章清單...")
            try:
                page.wait_for_function("() => !document.body.innerText.includes('{{title}}') && document.querySelectorAll('a').length > 20", timeout=20000)
                page.wait_for_timeout(3000)
            except Exception:
                pass
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            article_links = soup.find_all('a', href=re.compile(r'capital-market-outlook|insights|article', re.IGNORECASE))
            valid_articles = []
            
            for a in article_links:
                href = a.get('href', '')
                full_url = urljoin(base_url, href)
                
                clean_href = href.split('?')[0].rstrip('/')
                if clean_href in ['/capital-market-outlook.html', '/capital-market-outlook', '/']:
                    continue
                
                # 簡單抓取標題，不理會首頁的日期了
                raw_title = clean_text(a.get_text(separator=' '))
                if len(raw_title) < 5:
                    parent_container = a.find_parent('div', class_=re.compile(r'content|text', re.I)) or a.find_parent('li') or a.parent
                    if parent_container:
                        headings = parent_container.find_all(['h2', 'h3', 'h4', 'strong', 'p'])
                        for h in headings:
                            t = clean_text(h.get_text())
                            if len(t) > 10: 
                                raw_title = t
                                break
                
                # 清除可能殘留的日期文字 (以防萬一) 與多餘字眼
                raw_title = re.sub(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),\s+(\d{4})', '', raw_title, flags=re.IGNORECASE)
                raw_title = re.sub(r'Read more|Download.*', '', raw_title, flags=re.IGNORECASE).strip()
                
                if raw_title and full_url not in seen_links:
                    valid_articles.append((raw_title, full_url))
                    seen_links.add(full_url)

            valid_articles = valid_articles[:10]
            print(f"  👉 找到 {len(valid_articles)} 篇報告文章，準備進入內頁抽取 PDF...")
            
            # ==========================================
            # 第二層：進入內頁，尋找 PDF 並直接從網址萃取日期
            # ==========================================
            for title, article_url in valid_articles:
                print(f"    🕵️ 正在進入文章: {title[:20]}...")
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
                        report_date = datetime.now().strftime("%Y-%m-%d") # 預設今天
                        
                        # 🌟 終極殺手鐧：直接從 PDF 網址抓出日期 (例如 02-23-2026)
                        # 網址範例: /content/dam/ML/ecomm/pdf/CMO_Merrill_02-23-2026_ada.pdf
                        url_date_match = re.search(r'(\d{2})-(\d{2})-(\d{4})', full_pdf_url)
                        if url_date_match:
                            month, day, year = url_date_match.groups()
                            report_date = f"{year}-{month}-{day}" # 轉換為 YYYY-MM-DD
                        
                        reports.append({
                            "Source": "Merrill Lynch (CMO)",
                            "Date": report_date,
                            "Name": f"CMO - {title[:60]}",
                            "Link": full_pdf_url,
                            "Type": "PDF"
                        })
                        print(f"      ✅ 成功挖出 PDF！ (精準日期: {report_date})")
                    else:
                        print(f"      ⚠️ 內頁未提供官方 PDF，跳過。")
                        
                except Exception as e:
                    print(f"      ❌ 進入文章失敗: {str(e)[:30]}")
                    
            browser.close()
            
    except Exception as e:
        print(f"  ❌ Merrill Lynch 爬取異常: {e}")

    print(f"  ✅ 美林最終成功收錄 {len(reports)} 篇報告")
    return reports

if __name__ == "__main__":
    scrape()
