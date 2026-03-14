import os
import re
import json
import time
import requests
import urllib.parse as urlparse
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime


def parse_hits(hits, base_url, seen_links):
    valid = []
    for hit in hits:
        try:
            src       = hit.get("_source", {})
            results   = src.get("results_data", {})
            search    = src.get("search_data", {})
            date_sort = src.get("date_sort", {})

            title    = results.get("Title", "").strip()
            rel_path = results.get("RelativeDCRPath", "").strip()
            fmt      = results.get("Format", "").lower()

            video_url = search.get("VideoDetails", {}).get("VideoURL", "")
            if "youtube" in video_url.lower():
                continue
            if fmt == "video":
                continue
            if not rel_path or not title:
                continue

            raw_date = date_sort.get("PublishedDate", "")
            try:
                pub_date = datetime.strptime(raw_date[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
            except Exception:
                pub_date = raw_date[:10] if raw_date else "unknown"

            article_url = f"{base_url}/personal/aics/archive/{rel_path}"
            if article_url in seen_links:
                continue
            seen_links.add(article_url)
            valid.append((title, article_url, pub_date))
        except Exception:
            pass
    return valid


def scrape():
    print("🔍 正在爬取 DBS (星展銀行) - API 攔截全量模式...")
    reports    = []
    seen_links = set()
    download_path = os.path.abspath("all report pdf")
    os.makedirs(download_path, exist_ok=True)

    target_url = "https://www.dbs.com.tw/personal/aics/archive/index.page"
    base_url   = "https://www.dbs.com.tw"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                accept_downloads=True
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)

            # ==========================================
            # STEP 1: 攔截所有 API 請求（在 goto 之前就掛上）
            # ==========================================
            all_api_requests = []   # 收集所有 twarticlesvc 請求

            def on_request(request):
                url = request.url
                if "twarticlesvc" in url:
                    all_api_requests.append({
                        "url":     url,
                        "headers": dict(request.headers),
                    })
                    print(f"  🎯 攔截 API 請求: {url[:100]}")

            # ✅ 關鍵：在 goto 之前就掛上監聽器
            page.on("request", on_request)

            print("  🌐 載入 Archive 首頁...")
            try:
                page.goto(target_url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"    ⚠️ 首頁載入: {str(e)[:50]}")

            # 從 __NEXT_DATA__ 取初始資料
            raw_json = page.evaluate(
                "() => document.getElementById('__NEXT_DATA__') ? "
                "document.getElementById('__NEXT_DATA__').innerText : ''"
            )
            next_data  = json.loads(raw_json) if raw_json else {}
            page_env   = next_data.get("props", {}).get("pageEnv", {})
            article_api = page_env.get("ARTICLE_API_BASE_URL", "").rstrip("/")
            print(f"  📡 Article API Base: {article_api}")

            def find_key(obj, key):
                if isinstance(obj, dict):
                    if key in obj: return obj[key]
                    for v in obj.values():
                        r = find_key(v, key)
                        if r is not None: return r
                elif isinstance(obj, list):
                    for i in obj:
                        r = find_key(i, key)
                        if r is not None: return r
                return None

            initial    = find_key(next_data, "fetchedInitialArticles") or {}
            total      = initial.get("total", {}).get("value", 0)
            first_hits = initial.get("hits", [])
            print(f"  📊 總文章數: {total}，首批: {len(first_hits)} 筆")

            all_articles = parse_hits(first_hits, base_url, seen_links)
            for t, u, d in all_articles:
                print(f"    📄 [{d}] {t[:60]}")

            # ==========================================
            # STEP 2: 若首頁載入沒攔到，手動捲動觸發第二頁請求
            # ==========================================
            if not all_api_requests:
                print("\n  🔄 首頁未攔到 API，嘗試捲動觸發...")
                for _ in range(5):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)
                    if all_api_requests:
                        break

            print(f"\n  📡 共攔截到 {len(all_api_requests)} 個 API 請求")

            # ==========================================
            # STEP 3: 用攔截到的 URL 解析出 base，循環取全部分頁
            # ==========================================
            if all_api_requests and article_api:
                # 取第一個攔截到的請求作為範本
                template     = all_api_requests[0]
                api_base_url = template["url"]
                api_headers  = template["headers"]

                parsed      = urlparse.urlparse(api_base_url)
                params      = dict(urlparse.parse_qsl(parsed.query))
                size        = int(params.get("size", 10))
                total_pages = (total + size - 1) // size

                print(f"  🔄 共 {total_pages} 頁，每頁 {size} 筆，開始逐頁抓取...\n")

                session = requests.Session()
                session.headers.update({
                    "User-Agent": api_headers.get("user-agent", "Mozilla/5.0"),
                    "Referer":    "https://www.dbs.com.tw/",
                    "Origin":     "https://www.dbs.com.tw",
                })
                for k, v in api_headers.items():
                    if k.lower() in ("authorization", "x-requested-with", "accept", "cookie"):
                        session.headers[k] = v

                for page_num in range(1, total_pages + 1):
                    params["page"] = str(page_num)
                    api_url = urlparse.urlunparse(
                        parsed._replace(query=urlparse.urlencode(params))
                    )
                    try:
                        resp = session.get(api_url, timeout=20)
                        if resp.status_code != 200:
                            print(f"    ⚠️ 第 {page_num} 頁失敗: HTTP {resp.status_code}")
                            continue

                        body = resp.json()
                        hits = body.get("hits", [])
                        if not hits:
                            hits = find_key(body, "hits") or []

                        new = parse_hits(hits, base_url, seen_links)
                        all_articles.extend(new)
                        print(f"    📥 第 {page_num}/{total_pages} 頁，新增 {len(new)} 篇，累計 {len(all_articles)} 篇")
                        for t, u, d in new:
                            print(f"      📄 [{d}] {t[:55]}")
                        time.sleep(0.5)

                    except Exception as e:
                        print(f"    ❌ 第 {page_num} 頁失敗: {e}")

            else:
                # ==========================================
                # 備案：直接用 article_api 自己組 URL
                # ==========================================
                print(f"\n  ⚠️ 未攔截到 API 請求，改用 article_api 直接組 URL...")

                if article_api:
                    size        = 10
                    total_pages = (total + size - 1) // size

                    # 常見的 endpoint 格式，逐一嘗試
                    candidate_paths = [
                        "/archive",
                        "/api/archive",
                        "/articles",
                        "/api/articles",
                        "",
                    ]
                    candidate_params = [
                        {"segment": "personal", "page": "1", "size": str(size)},
                        {"segment": "personal", "page": "1", "size": str(size), "category": "archive"},
                        {"page": "1", "size": str(size)},
                    ]

                    working_url    = None
                    working_params = None

                    for path in candidate_paths:
                        for param_set in candidate_params:
                            test_url = f"{article_api}{path}?{urlparse.urlencode(param_set)}"
                            try:
                                r = requests.get(test_url, headers={
                                    "User-Agent": "Mozilla/5.0",
                                    "Referer": "https://www.dbs.com.tw/",
                                }, timeout=10)
                                if r.status_code == 200:
                                    body = r.json()
                                    hits = find_key(body, "hits") or []
                                    if hits:
                                        print(f"  ✅ 找到可用 endpoint: {test_url[:80]}")
                                        working_url    = f"{article_api}{path}"
                                        working_params = param_set.copy()
                                        break
                            except Exception:
                                pass
                        if working_url:
                            break

                    if working_url:
                        for page_num in range(1, total_pages + 1):
                            working_params["page"] = str(page_num)
                            api_url = f"{working_url}?{urlparse.urlencode(working_params)}"
                            try:
                                resp = requests.get(api_url, headers={
                                    "User-Agent": "Mozilla/5.0",
                                    "Referer": "https://www.dbs.com.tw/",
                                }, timeout=20)
                                body = resp.json()
                                hits = find_key(body, "hits") or []
                                new  = parse_hits(hits, base_url, seen_links)
                                all_articles.extend(new)
                                print(f"    📥 第 {page_num}/{total_pages} 頁，新增 {len(new)} 篇，累計 {len(all_articles)} 篇")
                                time.sleep(0.5)
                            except Exception as e:
                                print(f"    ❌ 第 {page_num} 頁失敗: {e}")
                    else:
                        print("  ❌ 所有備案 endpoint 均失敗，只能用首批 10 筆")
                else:
                    print("  ❌ 沒有 article_api，只能用首批 10 筆")

            print(f"\n  📋 共 {len(all_articles)} 篇有效文章，開始下載 PDF...\n")

            # ==========================================
            # STEP 4: 進入每篇文章內頁，找 PDF 連結下載
            # ==========================================
            session_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Referer": "https://www.dbs.com.tw/",
            }

            for title, article_url, pub_date in all_articles:
                safe_title     = re.sub(r'[\\/*?:"<>|]', "_", f"{title} ({pub_date})").strip()
                local_filename = f"{safe_title}.pdf"
                local_filepath = os.path.join(download_path, local_filename)

                print(f"    🔎 [{pub_date}] {title[:50]}...")

                if os.path.exists(local_filepath):
                    print(f"      ✅ 已存在，跳過下載")
                    reports.append({
                        "Source":    "DBS",
                        "Date":      pub_date,
                        "Name":      f"{title} ({pub_date})",
                        "Link":      article_url,
                        "Type":      "PDF",
                        "LocalPath": local_filepath,
                    })
                    continue

                for attempt in range(2):
                    try:
                        page.goto(article_url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(3000)

                        pdf_url = page.evaluate("""
                            () => {
                                let links = [...document.querySelectorAll('a[href]')];

                                // 優先：wrapperapi download-pdf
                                let w = links.find(a =>
                                    a.href.includes('wrapperapi') &&
                                    a.href.includes('download-pdf')
                                );
                                if (w) return w.href;

                                // 備援：文章專屬 PDF
                                let d = links.find(a =>
                                    a.href.toLowerCase().endsWith('.pdf') &&
                                    (a.href.includes('/pdf/AIO/') || a.href.includes('/article/pdf/'))
                                );
                                if (d) return d.href;

                                return null;
                            }
                        """)

                        if not pdf_url:
                            print(f"      ⚠️  無 PDF 連結，略過")
                            break

                        print(f"      🔗 {pdf_url[:80]}")

                        cookies = {c['name']: c['value'] for c in context.cookies()}
                        resp = requests.get(
                            pdf_url,
                            headers=session_headers,
                            cookies=cookies,
                            timeout=30,
                            stream=True
                        )

                        if resp.status_code == 200:
                            first_bytes = b""
                            chunks = []
                            for chunk in resp.iter_content(chunk_size=8192):
                                if not first_bytes:
                                    first_bytes = chunk[:4]
                                chunks.append(chunk)

                            is_pdf = (
                                "pdf" in resp.headers.get("Content-Type", "").lower() or
                                first_bytes.startswith(b"%PDF")
                            )

                            if is_pdf:
                                with open(local_filepath, "wb") as f:
                                    for chunk in chunks:
                                        f.write(chunk)
                                reports.append({
                                    "Source":    "DBS",
                                    "Date":      pub_date,
                                    "Name":      f"{title} ({pub_date})",
                                    "Link":      article_url,
                                    "Type":      "PDF",
                                    "LocalPath": local_filepath,
                                })
                                print(f"      ✅ 下載成功 → {local_filename}")
                            else:
                                print(f"      ❌ 非 PDF (開頭: {first_bytes})")
                        else:
                            print(f"      ❌ HTTP {resp.status_code}")
                        break

                    except Exception as e:
                        print(f"    ⚠️ 第 {attempt+1} 次失敗: {str(e)[:60]}")
                        page.wait_for_timeout(1500)

            browser.close()

    except Exception as e:
        print(f"  ❌ 爬取總體異常: {e}")

    print(f"\n✅ 爬取完畢，共下載 {len(reports)} 份 PDF。")
    return reports


if __name__ == "__main__":
    results = scrape()
    print("\n=== 結果預覽 ===")
    for r in results:
        print(r)
