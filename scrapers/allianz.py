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

def extract_date_from_text(text):
    """嘗試從字串中萃取多種格式的日期"""
    # YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD
    match = re.search(r'(20[2-3][0-9])[/.\-]([0-9]{1,2})[/.\-]([0-9]{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    # 英文月份：February 25, 2026 / 25 February 2026
    months = {
        'january': '01', 'february': '02', 'march': '03', 'april': '04',
        'may': '05', 'june': '06', 'july': '07', 'august': '08',
        'september': '09', 'october': '10', 'november': '11', 'december': '12'
    }
    # "February 25, 2026" style
    match = re.search(
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+([0-9]{1,2}),?\s+(20[2-3][0-9])',
        text, re.IGNORECASE
    )
    if match:
        return f"{match.group(3)}-{months[match.group(1).lower()]}-{int(match.group(2)):02d}"

    # "25 February 2026" style
    match = re.search(
        r'([0-9]{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(20[2-3][0-9])',
        text, re.IGNORECASE
    )
    if match:
        return f"{match.group(3)}-{months[match.group(2).lower()]}-{int(match.group(1)):02d}"

    return "未知日期"

def is_within_30_days(date_text):
    if not date_text or date_text == "未知日期":
        return True
    try:
        dt = datetime.strptime(date_text, "%Y-%m-%d")
        return (datetime.now() - dt).days <= 30
    except:
        return True

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 Allianz Trade - Economic Insights...")
    reports = []
    seen_pdfs = set()

    list_url = "https://www.allianz-trade.com/en_global/news-insights/economic-insights.html"
    base_url = "https://www.allianz-trade.com"

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

            # ── 步驟 1：載入列表頁，蒐集所有文章連結 ──
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            print("  📋 步驟 1: 載入列表頁，蒐集文章連結...")
            page.goto(list_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)

            # 嘗試展開更多內容（若有「Load more」按鈕）
            for _ in range(3):
                try:
                    load_more = page.locator("button:has-text('Load more'), a:has-text('Load more'), button:has-text('Show more')")
                    if load_more.count() > 0:
                        load_more.first.click()
                        page.wait_for_timeout(3000)
                    else:
                        break
                except:
                    break

            soup = BeautifulSoup(page.content(), 'html.parser')

            # 蒐集所有站內文章連結（排除 PDF、外部連結）
            article_links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if not href:
                    continue
                full_url = urljoin(base_url, href)
                # 只要 allianz-trade.com 站內的 economic-insights 文章頁
                if (
                    'allianz-trade.com' in full_url
                    and 'economic-insights' in full_url
                    and full_url != list_url
                    and '.pdf' not in full_url.lower()
                    and full_url not in article_links
                ):
                    article_links.append(full_url)

            print(f"  🔗 找到 {len(article_links)} 個文章連結，開始逐一進入尋找 PDF...")

            # ── 步驟 2：逐一進入文章頁，找 PDF ──
            for idx, article_url in enumerate(article_links, 1):
                try:
                    art_page = context.new_page()
                    Stealth().apply_stealth_sync(art_page)
                    art_page.goto(article_url, wait_until="domcontentloaded", timeout=45000)
                    art_page.wait_for_timeout(3000)

                    art_soup = BeautifulSoup(art_page.content(), 'html.parser')

                    # 取得文章標題
                    title = ""
                    for sel in ['h1', 'h2', '.article-title', '.page-title', 'title']:
                        el = art_soup.select_one(sel)
                        if el:
                            title = el.get_text(strip=True)
                            if title and len(title) > 5:
                                break

                    # 取得日期：先找頁面中的 <time> 或含日期的元素
                    date_str = "未知日期"
                    time_el = art_soup.find('time')
                    if time_el:
                        date_str = extract_date_from_text(
                            time_el.get('datetime', '') or time_el.get_text(strip=True)
                        )
                    if date_str == "未知日期":
                        # 掃描頁面全文尋找日期
                        for candidate in art_soup.find_all(['span', 'p', 'div'], limit=30):
                            txt = candidate.get_text(strip=True)
                            if re.search(r'(20[2-3][0-9])', txt) and len(txt) < 80:
                                date_str = extract_date_from_text(txt)
                                if date_str != "未知日期":
                                    break
                    # 最後從 URL 嘗試
                    if date_str == "未知日期":
                        date_str = extract_date_from_text(article_url)

                    # 只保留 30 天內（未知日期也保留）
                    if not is_within_30_days(date_str):
                        art_page.close()
                        print(f"  [{idx}] ⏩ 跳過（超過30天）: {title[:30] or article_url}")
                        continue

                    # 找 PDF 連結
                    pdf_found = False
                    for a in art_soup.find_all('a', href=True):
                        href = a['href']
                        full_pdf_url = urljoin(base_url, href)
                        if '.pdf' in href.lower() and full_pdf_url not in seen_pdfs:
                            pdf_title = title or clean_title(a.get_text(strip=True)) or unquote(href.split('/')[-1].replace('.pdf', ''))
                            reports.append({
                                "Source": "Allianz Trade",
                                "Date": date_str,
                                "Name": clean_title(pdf_title),
                                "Link": full_pdf_url
                            })
                            seen_pdfs.add(full_pdf_url)
                            pdf_found = True
                            print(f"  [{idx}] ✅ PDF: {pdf_title[:40]}... ({date_str})")

                    if not pdf_found:
                        # 若找不到 PDF，嘗試觸發下載按鈕再掃描一次
                        try:
                            dl_btn = art_page.locator("a:has-text('Download'), button:has-text('Download'), a:has-text('PDF')")
                            if dl_btn.count() > 0:
                                art_page.wait_for_timeout(1000)
                                # 再次掃描
                                art_soup2 = BeautifulSoup(art_page.content(), 'html.parser')
                                for a in art_soup2.find_all('a', href=True):
                                    href = a['href']
                                    full_pdf_url = urljoin(base_url, href)
                                    if '.pdf' in href.lower() and full_pdf_url not in seen_pdfs:
                                        pdf_title = title or clean_title(a.get_text(strip=True))
                                        reports.append({
                                            "Source": "Allianz Trade",
                                            "Date": date_str,
                                            "Name": clean_title(pdf_title),
                                            "Link": full_pdf_url
                                        })
                                        seen_pdfs.add(full_pdf_url)
                                        pdf_found = True
                                        print(f"  [{idx}] ✅ PDF (二次掃描): {pdf_title[:40]}...")
                        except:
                            pass

                        if not pdf_found:
                            # 網頁文章本身當作「網頁轉PDF」來源
                            if article_url not in seen_pdfs and title:
                                reports.append({
                                    "Source": "Allianz Trade",
                                    "Date": date_str,
                                    "Name": clean_title(title),
                                    "Link": article_url,
                                    "Type": "Web"  # 讓 main.py 用網頁轉 PDF 模式處理
                                })
                                seen_pdfs.add(article_url)
                                print(f"  [{idx}] 🌐 網頁轉PDF: {title[:40]}... ({date_str})")

                    art_page.close()

                except Exception as e:
                    print(f"  [{idx}] ❌ 文章頁失敗: {str(e)[:60]}")
                    try:
                        art_page.close()
                    except:
                        pass

            browser.close()

    except Exception as e:
        print(f"  ❌ Allianz Trade 爬取失敗: {e}")
        import traceback
        traceback.print_exc()

    print(f"  ✅ Allianz Trade 最終成功收錄 {len(reports)} 筆報告")
    return reports


if __name__ == "__main__":
    import pprint
    result = scrape()
    print("\n📊 測試爬取結果：")
    pprint.pprint(result)
