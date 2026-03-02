import os
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, unquote
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def clean_title(title):
    return title.replace('\n', ' ').strip()

def sanitize_filename(filename):
    """清除會導致存檔失敗的特殊字元"""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 Allianz Trade (安聯貿易) - 🛡️ 啟動 CloudFront 隱形穿透下載模式...")
    reports = []
    seen_pdfs = set()
    
    base_url = "https://www.allianz-trade.com"
    list_url = "https://www.allianz-trade.com/en_global/news-insights/economic-insights.html"
    
    # 確保儲存檔案的資料夾存在
    output_dir = "all report pdf"
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            # 建立帶有擬人化特徵的瀏覽器環境
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            print(f"  🌐 正在載入文章列表...")
            page.goto(list_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000) 
            
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            article_links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/news-insights/economic-insights/' in href and href.endswith('.html'):
                    full_url = urljoin(base_url, href)
                    if full_url != list_url and full_url not in article_links:
                        article_links.append(full_url)
            
            print(f"  🎯 找到 {len(article_links)} 篇文章，準備進入內頁尋找 PDF...")
            
            for article_url in article_links[:15]: 
                try:
                    page.goto(article_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1500) 
                    
                    inner_html = page.content()
                    inner_soup = BeautifulSoup(inner_html, 'html.parser')
                    
                    pdf_link = None
                    for a in inner_soup.find_all('a', href=True):
                        if '.pdf' in a['href'].lower():
                            pdf_link = urljoin(base_url, a['href'])
                            break 
                    
                    if not pdf_link or pdf_link in seen_pdfs:
                        continue
                        
                    title_tag = inner_soup.find('h1')
                    title = title_tag.get_text(strip=True) if title_tag else unquote(pdf_link.split('/')[-1].replace('.pdf', ''))
                    
                    # === 多層次日期抓取邏輯 ===
                    date_text = "未知日期"
                    meta_date = inner_soup.find('meta', {'property': 'article:published_time'})
                    if meta_date and meta_date.get('content'):
                        date_text = meta_date['content'].split('T')[0]
                    if date_text == "未知日期":
                        time_tag = inner_soup.find('time')
                        if time_tag and time_tag.get('datetime'):
                            date_text = time_tag['datetime'].split('T')[0]
                    if date_text == "未知日期":
                        date_match = re.search(r'([A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Z][a-z]{2,8}\s+\d{4})', inner_html)
                        if date_match:
                            raw_date = date_match.group(1).replace(',', '').strip()
                            formats_to_try = ["%b %d %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y"]
                            for fmt in formats_to_try:
                                try:
                                    dt = datetime.strptime(raw_date, fmt)
                                    date_text = dt.strftime("%Y-%m-%d")
                                    break
                                except ValueError:
                                    continue
                    
                    seen_pdfs.add(pdf_link)
                    clean_t = clean_title(title)
                    
                    # 🌟🌟🌟 全新核心：物理隔離下載 (Pre-download) 🌟🌟🌟
                    print(f"    📥 正在繞過防火牆下載實體 PDF...")
                    # 使用 Playwright 的 APIContext 請求，完美繼承隱形斗篷與 Cookie
                    pdf_response = context.request.get(pdf_link, timeout=20000)
                    
                    if pdf_response.status == 200:
                        pdf_bytes = pdf_response.body()
                        
                        # 嚴格驗證檔案標頭是否為真實 PDF (%PDF)
                        if pdf_bytes.startswith(b'%PDF'):
                            safe_name = sanitize_filename(f"Allianz Trade_{date_text}_{clean_t}")
                            local_path = os.path.join(output_dir, f"{safe_name}.pdf")
                            
                            # 直接寫入硬碟
                            with open(local_path, "wb") as f:
                                f.write(pdf_bytes)
                            
                            reports.append({
                                "Source": "Allianz Trade",
                                "Date": date_text,
                                "Name": clean_t,
                                "Link": pdf_link,
                                "Type": "Pre-Downloaded", # 🌟 告訴主程式：我已經載好了，請跳過
                                "LocalPath": local_path   # 🌟 直接把真實路徑交給系統
                            })
                            print(f"    ✔️ 成功捕獲並保存實體 PDF: {clean_t[:20]}...")
                        else:
                            print(f"    ❌ 下載失敗: 拿到的不是 PDF (可能仍被防火牆攔截)")
                    else:
                        print(f"    ❌ 伺服器拒絕下載，狀態碼: {pdf_response.status}")
                    
                except Exception as inner_e:
                    print(f"    ⚠️ 進入內頁解析失敗 ({article_url}): {inner_e}")
                
            browser.close()

    except Exception as e:
        print(f"  ❌ Allianz Trade 爬取失敗: {e}")

    print(f"  ✅ Allianz Trade 最終成功收錄 {len(reports)} 筆 PDF 報告")
    return reports
