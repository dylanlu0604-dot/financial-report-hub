from bs4 import BeautifulSoup
import re
import json
from urllib.parse import urljoin
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==========================================
# 🛠️ 輔助工具函式
# ==========================================
def clean_title(title):
    return title.replace('\n', ' ').strip()

def is_within_30_days(date_text):
    if not date_text or date_text == "未知日期":
        return False
    try:
        dt = datetime.strptime(date_text, "%Y-%m-%d")
        return (datetime.now() - dt).days <= 30
    except:
        return True

def parse_date(raw):
    """嘗試多種格式解析日期，回傳 YYYY-MM-DD 或 '未知日期'"""
    if not raw:
        return "未知日期"
    raw = raw.strip()

    # YYYY-MM-DD
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # YYYY/MM/DD
    m = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})', raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # 民國 YYY/MM/DD 或 YYY.MM.DD
    m = re.search(r'(\d{3})[./](\d{1,2})[./](\d{1,2})', raw)
    if m:
        western_year = int(m.group(1)) + 1911
        return f"{western_year}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    return "未知日期"

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 Mega Bank (兆豐銀行 - 財經週報) - 🕵️‍♂️ API 封包攔截模式...")
    reports = []
    seen_links = set()

    base_url = "https://www.megabank.com.tw"
    target_url = "https://www.megabank.com.tw/personal/wealth/financial-service/bulletin/weekly-journal"

    # 三個目標分類
    CATEGORIES = ["匯率利率資訊", "投資研究週報", "國際經濟金融週報"]

    captured_api_responses = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                bypass_csp=True
            )

            page = context.new_page()
            Stealth().apply_stealth_sync(page)

            # ========== 封包攔截 ==========
            def handle_response(response):
                url = response.url
                # 攔截所有 XHR/Fetch 及可能含報告清單的 API
                if response.request.resource_type in ["xhr", "fetch"]:
                    try:
                        data = response.json()
                        captured_api_responses.append({
                            "url": url,
                            "data": data
                        })
                        print(f"    📡 攔截到 API: {url[:80]}")
                    except Exception:
                        # 可能是 PDF 或圖片，跳過
                        pass

            page.on("response", handle_response)

            print(f"  🌐 正在前往財經週報頁面...")
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            # 嘗試滾動觸發懶加載
            try:
                page.evaluate("window.scrollTo(0, 600)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)
            except Exception:
                pass

            # ===== 嘗試逐一點選每個分類標籤，觸發更多 API =====
            html_content = page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # 找尋分類 Tab（可能是 li / button / a 元素）
            tabs = soup.find_all(["li", "button", "a"], string=re.compile("匯率|投資研究|國際經濟"))
            print(f"  🗂️ 找到 {len(tabs)} 個分類標籤，嘗試逐一點擊...")

            for tab_text in CATEGORIES:
                try:
                    # 用文字定位並點選對應 Tab
                    tab_locator = page.get_by_text(tab_text, exact=False)
                    if tab_locator.count() > 0:
                        tab_locator.first.click()
                        page.wait_for_timeout(3000)
                        print(f"    ✅ 已點選分類: {tab_text}")
                    else:
                        print(f"    ⚠️ 找不到分類標籤: {tab_text}")
                except Exception as e:
                    print(f"    ⚠️ 點擊 {tab_text} 失敗: {e}")

            # 再等待一次確保所有 API 都已回傳
            page.wait_for_timeout(3000)

            # ===== 備用方案：解析最終 HTML（萬一沒有 API） =====
            final_html = page.content()
            browser.close()

        # ==========================================
        # 🧠 方法一：解析攔截到的 API JSON
        # ==========================================
        print(f"\n  [偵探回報] 共攔截到 {len(captured_api_responses)} 個 JSON 封包，開始分析...")

        def recursive_find_reports(obj, depth=0):
            """遞迴在 JSON 物件中找尋含有報告資訊的節點"""
            if depth > 10:
                return
            if isinstance(obj, dict):
                keys_lower = {k.lower(): v for k, v in obj.items()}

                # 如果這個 dict 含有標題 + 連結的組合，就視為一筆報告
                title_val = ""
                link_val = ""
                date_val = ""

                for k, v in obj.items():
                    if not isinstance(v, str):
                        continue
                    k_lower = k.lower()
                    if any(kw in k_lower for kw in ["title", "name", "subject", "fileName", "filename", "topic"]):
                        if re.search(r'[\u4e00-\u9fa5A-Za-z]', v) and len(v) > 2:
                            title_val = v.strip()
                    if any(kw in k_lower for kw in ["url", "link", "path", "href", "file"]):
                        if v.endswith(".pdf") or "pdf" in v.lower() or v.startswith("http") or v.startswith("/"):
                            link_val = v.strip()
                    if any(kw in k_lower for kw in ["date", "time", "publish", "update"]):
                        date_val = parse_date(v)

                if title_val and link_val:
                    full_link = urljoin(base_url, link_val) if not link_val.startswith("http") else link_val
                    if full_link not in seen_links:
                        reports.append({
                            "Source": "Mega Bank",
                            "Date": date_val if date_val else "未知日期",
                            "Name": clean_title(title_val),
                            "Link": full_link
                        })
                        seen_links.add(full_link)
                        print(f"    ✔️ [API] 抓到: {title_val[:40]}")

                for v in obj.values():
                    recursive_find_reports(v, depth + 1)

            elif isinstance(obj, list):
                for item in obj:
                    recursive_find_reports(item, depth + 1)

        for packet in captured_api_responses:
            recursive_find_reports(packet["data"])

        # ==========================================
        # 🧠 方法二（備用）：直接解析最終 HTML 頁面
        # ==========================================
        if not reports:
            print("  ℹ️ API 方法未找到報告，改用 HTML 解析備用方案...")
            soup = BeautifulSoup(final_html, "html.parser")

            # 找所有 PDF 連結（Mega Bank 的報告通常直接以 PDF 連結呈現）
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ".pdf" not in href.lower():
                    continue

                full_url = urljoin(base_url, href)
                if full_url in seen_links:
                    continue

                # 找標題：先抓 <a> 本身文字，再往父層找
                title = a.get_text(strip=True)
                if not title or len(title) < 3:
                    parent = a.find_parent(["li", "tr", "div", "td"])
                    if parent:
                        title = parent.get_text(separator=" ", strip=True)[:80]

                # 找日期
                date_text = "未知日期"
                context_text = ""
                parent = a.find_parent(["li", "tr", "div", "td"])
                if parent:
                    context_text = parent.get_text()
                date_text = parse_date(context_text) if context_text else "未知日期"

                # 判斷分類
                category_found = ""
                for cat in CATEGORIES:
                    if cat in context_text or cat in title:
                        category_found = cat
                        break

                clean = clean_title(title)
                if len(clean) < 3:
                    clean = f"Mega Bank 財經週報_{full_url.split('/')[-1].replace('.pdf', '')}"

                reports.append({
                    "Source": "Mega Bank",
                    "Date": date_text,
                    "Name": clean,
                    "Link": full_url
                })
                seen_links.add(full_url)
                print(f"    ✔️ [HTML] 抓到: {clean[:40]}")

        # ==========================================
        # 🗓️ 日期過濾：只保留 30 天內的報告
        # ==========================================
        before_filter = len(reports)
        reports = [r for r in reports if is_within_30_days(r["Date"]) or r["Date"] == "未知日期"]
        filtered_out = before_filter - len(reports)
        if filtered_out > 0:
            print(f"  🗓️ 已過濾掉 {filtered_out} 筆超過 30 天的舊報告")

    except Exception as e:
        print(f"  ❌ Mega Bank 爬取失敗: {e}")
        import traceback
        traceback.print_exc()

    print(f"  ✅ Mega Bank 最終成功收錄 {len(reports)} 筆報告")
    return reports
