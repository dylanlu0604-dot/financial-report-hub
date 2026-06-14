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
    print("🔍 正在爬取 DBS (星展銀行)...")
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
            # 用 route 攔截：讓請求繼續發出，同時記錄 URL
            # ==========================================
            captured = {"url": None, "headers": {}, "body_hits": []}

            def handle_route(route):
                url = route.request.url
                if "twarticlesvc" in url:
                    if captured["url"] is None:
                        captured["url"]     = url
                        captured["headers"] = dict(route.request.headers)
                        print(f"  🎯 攔截到 API URL: {url}")
                    # 繼續讓請求正常發出
                    route.continue_()
                else:
                    route.continue_()

            # 同時也攔截 response 拿 body
            def handle_response(response):
                url = response.url
                if "twarticlesvc" not in url:
                    return
                try:
                    body = response.json()
                    hits = body.get("hits", [])
                    if not hits:
                        def find_hits_deep(obj):
                            if isinstance(obj, dict):
                                if "hits" in obj and isinstance(obj["hits"], list) and obj["hits"]:
                                    return obj["hits"]
                                for v in obj.values():
                                    r = find_hits_deep(v)
                                    if r: return r
                            elif isinstance(obj, list):
                                for i in obj:
                                    r = find_hits_deep(i)
                                    if r: return r
                            return []
                        hits = find_hits_deep(body)

                    if hits:
                        captured["body_hits"].extend(hits)
                        print(f"  📥 response 拿到 {len(hits)} 筆，累計 {len(captured['body_hits'])} 筆")
                except Exception:
                    pass

            page.route("**/*", handle_route)
            page.on("response", handle_response)

            print("  🌐 載入 Archive 首頁...")
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
            except Exception as e:
                print(f"    ⚠️ 首頁載入: {str(e)[:50]}")

            # 取總筆數
            raw_json  = page.evaluate(
                "() => document.getElementById('__NEXT_DATA__') ? "
                "document.getElementById('__NEXT_DATA__').innerText : ''"
            )
            next_data   = json.loads(raw_json) if raw_json else {}
            page_env    = next_data.get("props", {}).get("pageEnv", {})
            article_api = page_env.get("ARTICLE_API_BASE_URL", "").rstrip("/")

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

            initial = find_key(next_data, "fetchedInitialArticles") or {}
            total   = initial.get("total", {}).get("value", 0)
            print(f"  📊 總文章數: {total}")
            print(f"  📡 API Base: {article_api}")
            print(f"  🔗 攔截到的 API URL: {captured['url']}")
            print(f"  📦 已從 response 收集: {len(captured['body_hits'])} 筆")

            # ==========================================
            # 用攔截到的真實 URL 直接用 requests 打全部分頁
            # ==========================================
            all_hits = list(captured["body_hits"])

            if captured["url"]:
                parsed      = urlparse.urlparse(captured["url"])
                params      = dict(urlparse.parse_qsl(parsed.query))
                size        = int(params.get("size", 10))
                total_pages = (total + size - 1) // size
                got_pages   = len(all_hits) // size if size else 0

                print(f"\n  🔄 用 requests 補齊剩餘分頁（已有約 {got_pages} 頁，共 {total_pages} 頁）...")

                session = requests.Session()
                session.headers.update({
                    "User-Agent": captured["headers"].get("user-agent", "Mozilla/5.0"),
                    "Referer":    "https://www.dbs.com.tw/",
                    "Origin":     "https://www.dbs.com.tw",
                    "Accept":     "application/json",
                })
                for k, v in captured["headers"].items():
                    if k.lower() in ("cookie", "authorization", "x-requested-with"):
                        session.headers[k] = v

                for page_num in range(got_pages, total_pages + 1):
                    params["page"] = str(page_num)
                    api_url = urlparse.urlunparse(
                        parsed._replace(query=urlparse.urlencode(params))
                    )
                    try:
                        resp = session.get(api_url, timeout=20)
                        if resp.status_code != 200:
                            print(f"    ⚠️ 第 {page_num} 頁 HTTP {resp.status_code}")
                            continue
                        body = resp.json()
                        hits = body.get("hits", [])
                        if not hits:
                            hits = find_key(body, "hits") or []
                        all_hits.extend(hits)
                        print(f"    📥 第 {page_num}/{total_pages} 頁 +{len(hits)} 筆，累計 {len(all_hits)}")
                        time.sleep(0.3)
                    except Exception as e:
                        print(f"    ❌ 第 {page_num} 頁失敗: {e}")

            elif article_api:
                # 完全沒攔到：用 __NEXT_DATA__ 裡的 SSR hits 作為起點
                # 並嘗試各種 endpoint 格式
                print(f"\n  ⚠️ 完全沒攔到 API URL，嘗試自行組裝...")
                first_hits = initial.get("hits", [])
                all_hits.extend(first_hits)

                size        = 10
                total_pages = (total + size - 1) // size

                candidate_endpoints = [
                    f"{article_api}/archive",
                    f"{article_api}/articles",
                    f"{article_api}",
                ]
                candidate_params = [
                    {"segment": "personal", "page": "0", "size": str(size)},
                    {"segment": "personal", "page": "0", "size": str(size),
                     "geography": "", "assetType": "", "sector": "",
                     "publication": "", "contentType": "", "searchKeyword": ""},
                ]

                working = None
                for ep in candidate_endpoints:
                    for pm in candidate_params:
                        test = f"{ep}?{urlparse.urlencode(pm)}"
                        try:
                            r = requests.get(test, headers={
                                "User-Agent": "Mozilla/5.0",
                                "Referer": "https://www.dbs.com.tw/",
                                "Accept": "application/json",
                            }, timeout=10)
                            if r.status_code == 200:
                                body = r.json()
                                hits = find_key(body, "hits") or []
                                if hits:
                                    print(f"  ✅ 找到可用 endpoint: {test[:80]}")
                                    working = (ep, pm.copy())
                                    break
                        except Exception:
                            pass
                    if working:
                        break

                if working:
                    ep, pm = working
                    for page_num in range(1, total_pages + 1):
                        pm["page"] = str(page_num)
                        api_url = f"{ep}?{urlparse.urlencode(pm)}"
                        try:
                            resp = requests.get(api_url, headers={
                                "User-Agent": "Mozilla/5.0",
                                "Referer": "https://www.dbs.com.tw/",
                            }, timeout=20)
                            body = resp.json()
                            hits = find_key(body, "hits") or []
                            all_hits.extend(hits)
                            print(f"    📥 第 {page_num}/{total_pages} 頁 +{len(hits)} 筆，累計 {len(all_hits)}")
                            time.sleep(0.3)
                        except Exception as e:
                            print(f"    ❌ 第 {page_num} 頁: {e}")
                else:
                    print("  ⚠️ 自行組裝 API 失敗，改用 SSR 首批資料")

            # ==========================================
            # 解析所有 hits
            # ==========================================
            all_articles = parse_hits(all_hits, base_url, seen_links)
            print(f"\n  📋 共解析出 {len(all_articles)} 篇有效文章，開始下載 PDF...\n")

            # ==========================================
            # 進入每篇文章內頁，找 PDF 連結下載
            # ==========================================
            session_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Referer":    "https://www.dbs.com.tw/",
            }

            for title, article_url, pub_date in all_articles:
                safe_title     = re.sub(r'[\\/*?:"<>|]', "_", f"{title} ({pub_date})").strip()
                local_filename = f"{safe_title}.pdf"
                local_filepath = os.path.join(download_path, local_filename)

                if os.path.exists(local_filepath):
                    print(f"    ✅ [{pub_date}] 已存在: {title[:50]}")
                    reports.append({
                        "Source":    "DBS",
                        "Date":      pub_date,
                        "Name":      f"{title} ({pub_date})",
                        "Link":      article_url,
                        "Type":      "PDF",
                        "LocalPath": local_filepath,
                    })
                    continue

                print(f"    🔎 [{pub_date}] {title[:50]}...")

                for attempt in range(2):
                    try:
                        page.goto(article_url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(3000)

                        pdf_url = page.evaluate("""
                            () => {
                                let links = [...document.querySelectorAll('a[href]')];
                                let w = links.find(a =>
                                    a.href.includes('wrapperapi') &&
                                    a.href.includes('download-pdf')
                                );
                                if (w) return w.href;
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

    print(f"\n✅ 爬取完畢，共回傳 {len(reports)} 份報告。")
    return reports


if __name__ == "__main__":
    results = scrape()
    print("\n=== 結果預覽 ===")
    for r in results:
        print(r)
