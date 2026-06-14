import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from scrapers.utils import HEADERS, is_within_30_days, fetch_real_pdf_link

def normalize_date(date_text):
    match = re.search(r'(20\d{2})年(\d{1,2})月(\d{1,2})日', date_text or "")
    if match:
        year, month, day = match.groups()
        return f"{year}年{int(month)}月{int(day)}日"

    match = re.search(r'(20\d{2})[./-](\d{1,2})[./-](\d{1,2})', date_text or "")
    if match:
        year, month, day = match.groups()
        return f"{year}年{int(month)}月{int(day)}日"

    return "未知日期"

def clean_title(title):
    return re.sub(r'\s+', ' ', title or "").strip()

def scrape():
    print("🔍 正在爬取 Mizuho RT (瑞穗)...")
    base_url = "https://www.mizuhobank.co.jp"
    current_year = datetime.now().year
    target_urls = [
        "https://www.mizuhobank.co.jp/corporate/mhri/research/report/index.html",
        "https://www.mizuhobank.co.jp/corporate/mhri/research/report/archive/index.html",
        f"https://www.mizuho-rt.co.jp/publication/{current_year}/index.html",
    ]
    reports = []
    seen_links = set()
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1440, "height": 1100},
                locale="ja-JP",
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)

            for target_url in target_urls:
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(3500)
                except Exception as e:
                    print(f"  ⚠️ Mizuho 頁面載入失敗: {target_url} ({str(e)[:60]})")
                    continue

                if "access denied" in page.title().lower() or "access denied" in page.content().lower()[:1000]:
                    print(f"  ⚠️ Mizuho 官方站拒絕自動化請求，略過: {target_url}")
                    continue

                soup = BeautifulSoup(page.content(), 'html.parser')

                for link_tag in soup.find_all('a', href=True):
                    title = clean_title(link_tag.get_text(" ", strip=True))
                    href = link_tag.get('href', '')
                    if not href or href.startswith('#') or href.startswith('javascript'):
                        continue

                    full_link = urljoin(target_url, href)
                    if full_link in seen_links:
                        continue
                    if "mizuhobank.co.jp" not in full_link and "mizuho-rt.co.jp" not in full_link:
                        continue

                    item = link_tag.find_parent(['li', 'article', 'div', 'tr'])
                    item_text = item.get_text(" ", strip=True) if item else title
                    date_text = normalize_date(item_text)
                    if date_text == "未知日期":
                        date_text = normalize_date(full_link)
                    if date_text == "未知日期":
                        continue
                    if not is_within_30_days(date_text):
                        continue

                    if len(title) < 5:
                        title = clean_title(full_link.rsplit('/', 1)[-1].replace('.pdf', ''))
                    if len(title) < 5 or any(kw in title for kw in ["採用", "お問い合わせ", "個人情報"]):
                        continue

                    final_pdf = full_link
                    if not final_pdf.lower().split('?', 1)[0].endswith('.pdf'):
                        try:
                            page.goto(full_link, wait_until="domcontentloaded", timeout=20000)
                            page.wait_for_timeout(1000)
                            inner_soup = BeautifulSoup(page.content(), 'html.parser')
                            pdf_tag = inner_soup.find('a', href=re.compile(r'\.pdf(\?|$)', re.IGNORECASE))
                            if not pdf_tag:
                                continue
                            final_pdf = urljoin(full_link, pdf_tag['href'])
                        except Exception:
                            final_pdf = fetch_real_pdf_link(full_link)

                    if final_pdf in seen_links:
                        continue
                    seen_links.add(full_link)
                    seen_links.add(final_pdf)
                    reports.append({"Source": "Mizuho", "Date": date_text, "Name": title, "Link": final_pdf})

            browser.close()
        
    except Exception as e:
        print(f"  ❌ Mizuho 失敗: {e}")
    
    print(f"  ✅ Mizuho 找到 {len(reports)} 筆報告")
    return reports
