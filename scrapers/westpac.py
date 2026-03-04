import os
import re
import urllib.parse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def clean_title(title):
    return re.sub(r'\s+', ' ', title).strip() if title else ""

def parse_english_date(date_text):
    date_text = re.sub(r'\s+', ' ', date_text).strip().replace(',', '').replace('.', '')
    for fmt in ["%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y", "%B %Y", "%b %Y"]:
        try: return datetime.strptime(date_text, fmt).strftime("%Y-%m-%d")
        except: continue
    return date_text

def extract_date_from_text(text, time_text=""):
    combined_text = f"{time_text} {text}"
    if not combined_text.strip(): return "未知日期"
    
    # 找 YYYY/MM/DD
    date_match = re.search(r'([0-9]{4}[/.-][0-9]{2}[/.-][0-9]{2})', combined_text)
    if date_match: return date_match.group(1).replace('/', '-').replace('.', '-')
    
    # 🌟 找澳洲格式 DD/MM/YYYY
    aus_match = re.search(r'\b([0-9]{1,2})[/.-]([0-9]{1,2})[/.-]([0-9]{4})\b', combined_text)
    if aus_match:
        d, m, y = aus_match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    
    MONTHS = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
    for pat in [rf'(\d{{1,2}}\s+{MONTHS}\.?\s+\d{{4}})', rf'({MONTHS}\.?\s+\d{{1,2}},?\s+\d{{4}})', rf'({MONTHS}\.?\s+\d{{4}})']:
        match = re.search(pat, combined_text, re.IGNORECASE)
        if match: return parse_english_date(match.group(1))
        
    return "未知日期" # 拿掉那個自作聰明的網址判斷

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 Westpac IQ (西太平洋銀行) - 🚀 啟用真·無盲區防誤殺引擎...")
    reports = []
    seen_links = set()
    
    base_url = "https://www.westpaciq.com.au"
    target_urls = [
        "https://www.westpaciq.com.au/topic.australia.html",
        "https://www.westpaciq.com.au/economics.html"
    ]
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, 
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            potential_articles = []
            
            for target_url in target_urls:
                print(f"  🌐 正在載入主頁: {target_url}...")
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(4000)
                    
                    try:
                        agree_btn = page.locator("button:has-text('I Agree'), button:has-text('Accept'), a:has-text('I Agree'), a:has-text('Accept')").first
                        if agree_btn.is_visible(timeout=2000):
                            agree_btn.click()
                            page.wait_for_timeout(2000)
                    except:
                        pass
                    
                    print("    ⏳ 準備尋找並點擊 'Show more' 按鈕...")
                    for i in range(5):
                        try:
                            page.evaluate("window.scrollBy(0, 1500)")
                            page.wait_for_timeout(1000)
                            
                            clicked = page.evaluate("""
                                () => {
                                    let btns = Array.from(document.querySelectorAll('button, a'));
                                    let target = btns.find(b => b.innerText && (b.innerText.toLowerCase().includes('show more') || b.innerText.toLowerCase().includes('load more')));
                                    if (target && target.offsetParent !== null) {
                                        target.click();
                                        return true;
                                    }
                                    return false;
                                }
                            """)
                            if clicked:
                                print(f"      🖱️ 成功觸發載入更多 (第 {i+1} 次)...")
                                page.wait_for_timeout(3000)
                            else:
                                break
                        except:
                            break
                            
                except Exception as e:
                    print(f"  ⚠️ 載入或點擊超時: {e}")
                    
                print("    📡 正在從瀏覽器記憶體中直接抽提連結...")
                links_data = page.evaluate("""
                    () => {
                        return Array.from(document.querySelectorAll('a')).map(a => {
                            let container = a.closest('article, div.card, div.item, li, tr') || a.parentElement;
                            let timeElem = container ? container.querySelector('time, .date, .time') : null;
                            return {
                                href: a.href,
                                text: a.innerText.trim(),
                                parentText: container ? container.innerText.trim() : a.innerText.trim(),
                                timeText: timeElem ? timeElem.innerText.trim() : ''
                            };
                        });
                    }
                """)
                
                for data in links_data:
                    href = data.get('href', '').strip()
                    if not href or href.startswith('#') or href.lower().startswith('javascript'): continue
                        
                    full_url = urllib.parse.urljoin(base_url, href)
                    clean_full_url = full_url.split('#')[0].split('?')[0].rstrip('/')
                    
                    if clean_full_url in seen_links: continue
                    if any(x in clean_full_url.lower() for x in ['/author', '/search', 'login', 'subscribe', 'privacy', 'terms', 'contact']): continue
                    
                    if re.search(r'/(economics|article|research|strategy)/', clean_full_url.lower()) or '.pdf' in clean_full_url.lower():
                        
                        parent_text = data.get('parentText', '')
                        time_text = data.get('timeText', '')
                        if len(parent_text) > 400: parent_text = data.get('text', '')
                            
                        date_str = extract_date_from_text(parent_text, time_text)
                        
                        # 🌟 最強防刪保險：如果抓不到日期，給今天的日期！絕對不讓它被 main.py 當作過期刪除！
                        if date_str == "未知日期":
                            date_str = datetime.now().strftime("%Y-%m-%d")
                            
                        title = clean_title(data.get('text', ''))
                        if len(title) < 5: 
                            title = urllib.parse.unquote(clean_full_url.split('/')[-1].replace('.html', '').replace('.pdf', '').replace('-', ' '))
                            
                        potential_articles.append({"title": title, "url": clean_full_url, "date": date_str})
                        seen_links.add(clean_full_url)
            
            print(f"  🎯 雙主頁共發現 {len(potential_articles)} 篇潛在報告，啟動智慧判斷引擎...")
            
            for item in potential_articles[:100]:
                url = item["url"]
                title = item["title"]
                date_str = item["date"]
                
                date_match = re.search(r'([A-Z][a-z]{2,8}\.?\s+\d{1,2},?\s+\d{4})', title, re.IGNORECASE)
                if date_match: title = title.replace(date_match.group(1), '').strip()
                title = re.sub(r'^[|\- ]+|[|\- ]+$', '', title).strip()
                
                if not title or len(title) < 3: title = "Westpac Report"
                title = f"{title} ({date_str})"
                
                if '.pdf' in url.lower():
                    reports.append({"Source": "Westpac IQ", "Date": date_str, "Name": title, "Link": url, "Type": "PDF"})
                    print(f"    📄 [直接 PDF] 收錄: {title[:40]}...")
                    continue
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(1000)
                    
                    has_youtube = page.evaluate("() => document.body.innerHTML.toLowerCase().includes('youtube.com/embed') || document.body.innerHTML.toLowerCase().includes('youtu.be')")
                    if has_youtube:
                        print(f"    🚫 [跳過] 偵測到 YouTube: {title[:30]}...")
                        continue
                        
                    pdf_href = page.evaluate("""
                        () => {
                            let pdf = Array.from(document.querySelectorAll('a')).find(a => a.href.toLowerCase().includes('.pdf'));
                            return pdf ? pdf.href : null;
                        }
                    """)
                    
                    if pdf_href:
                        inner_pdf_url = urllib.parse.urljoin(url, pdf_href)
                        reports.append({"Source": "Westpac IQ", "Date": date_str, "Name": title, "Link": inner_pdf_url, "Type": "PDF"})
                        print(f"    🕵️ [內頁 PDF] 成功挖出實體: {title[:40]}...")
                    else:
                        reports.append({"Source": "Westpac IQ", "Date": date_str, "Name": title, "Link": url})
                        print(f"    🌐 [純網頁轉印] 收錄: {title[:40]}...")
                    
                except Exception as inner_e:
                    reports.append({"Source": "Westpac IQ", "Date": date_str, "Name": title, "Link": url})
                    print(f"    🌐 [純網頁轉印] (內頁解析超時): {title[:40]}...")
                    
            browser.close()
            
    except Exception as e:
        print(f"  ❌ Westpac 爬取異常: {e}")

    print(f"  ✅ 總共收錄 {len(reports)} 篇 Westpac 報告")
    return reports

if __name__ == "__main__":
    scrape()