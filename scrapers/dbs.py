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
    print("🔍 正在爬取 DBS (星展銀行) - Response 攔截全量模式...")
    reports    = []
    seen_links = set()
    download_path = os.path.abspath("all report pdf")
    os.makedirs(download_path, exist_ok=True)

    target_url = "https://www.dbs.com.tw/personal/aics/archive/index.page"
    base_url   = "https://www.dbs.com.tw"

    # ==========================================
    # 先掃描已存在的 DBS PDF，保底不讓舊報告消失
    # ==========================================
    existing_reports = {}
    dbs_pattern = re.compile(r"^(.+) \((\d{4}-\d{2}-\d{2})\)\.pdf$")
    for fname in os.listdir(download_path):
        if not fname.endswith(".pdf"):
            continue
        fpath = os.path.join(download_path, fname)
        m = dbs_pattern.match(fname)
        if m:
            title_part = m.group(1)
            date_part  = m.group(2)
            existing_reports[fname] = {
                "Source":    "DBS",
                "Date":      date_part,
                "Name":      f"{title_part} ({date_part})",
                "Link":      f"{base_url}/personal/aics/archive/",
                "Type":      "PDF",
                "LocalPath": fpath,
            }
    print(f"  📂 已存在 {len(existing_reports)} 個 DBS PDF（保底加入）")
    reports.extend(existing_reports.values())

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
            # STEP 1: 攔截 response（不是 request）
            # 這樣可以直接拿到 API 回傳的 JSON 資料
            # ==========================================
            api_template   = {"url": None, "headers": {}}
            all_hits_found = []   # 從 response 直接收集到的 hits

            def on_response(response):
                url = response.url
                if "twarticlesvc" not in url:
                    return
                try:
                    body = response.json()
                    # 找 hits
                    hits = body.get("hits", [])
                    if not hits:
                        # 嘗試更深層
                        def find_hits_in(obj):
                            if isinstance(obj, dict):
                                if "hits" in obj and isinstance(obj["hits"], list):
                                    return obj["hits"]
                                for v in obj.values():
                                    r = find_hits_in(v)
                                    if r: return r
                            elif isinstance(obj, list):
                                for i in obj:
                                    r = find_hits_in(i)
                                    if r: return r
                            return []
                        hits = find_hits_in(body)

                    if hits:
                        all_hits_found.extend(hits)
                        print(f"  🎯 攔截 response: {url[:80]}")
                        print(f"     → 拿到 {len(hits)} 筆 hits，累計 {len(all_hits_found)} 筆")

                    # 記錄 URL 範本供後續分頁用
                    if api_template["url"] is None:
                        api_template["url"]     = url
                        api_template["headers"] = dict(response.request.headers)

                except Exception:
                    pass

            # ✅ 在 goto 之前掛上 response 攔截
            page.on("response", on_response)

            print("  🌐 載入 Archive 首頁...")
            try:
                page.goto(target_url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(3000)
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

            # ==========================================
            # STEP 2: 捲動讓瀏覽器自動打後續分頁 API
            # 每次捲到底，等待 response 攔截器收到新資料
            # ==========================================
            print(f"  🔄 開始捲動觸發分頁載入...")
            prev_count   = len(all_hits_found)
            no_new_count = 0

            while len(all_hits_found) < total:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2500)

                # 嘗試點擊 Load More
                try:
                    btn = page.query_selector(
                        "button:has-text('Load More'), button:has-text('Show More'), "
                        "[data-testid='load-more'], .load-more, .loadmore"
                    )
                    if btn and btn.is_visible():
                        btn.click()
                        page.wait_for_timeout(2500)
                        print(f"    🖱️  點擊 Load More")
                except Exception:
                    pass

                curr_count = len(all_hits_found)
                if curr_count > prev_count:
                    print(f"    📥 累計 {curr_count}/{total} 筆")
                    prev_count   = curr_count
                    no_new_count = 0
                else:
                    no_new_count += 1
                    if no_new_count >= 4:
                        print(f"    ⏹️  連續 4 次無新資料，停止捲動")
                        break

            print(f"\n  📡 捲動結束，從 response 共收集到 {len(all_hits_found)} 筆 hits")

            # ==========================================
            # STEP 3: 若捲動仍不足，用 requests 直接打 API 補齊
            # ==========================================
            if len(all_hits_found) < total and api_template["url"]:
                print(f"  🔧 捲動只拿到 {len(all_hits_found)}/{total}，改用 requests 補齊...")

                parsed      = urlparse.urlparse(api_template["url"])
                params      = dict(urlparse.parse_qsl(parsed.query))
                size        = int(params.get("size", 10))
                total_pages = (total + size - 1) // size

                # 計算已拿到幾頁
                got_pages   = len(all_hits_found) // size

                session = requests.Session()
                session.headers.update({
                    "User-Agent": api_template["headers"].get("user-agent", "Mozilla/5.0"),
                    "Referer":    "https://www.dbs.com.tw/",
                    "Origin":     "https://www.dbs.com.tw",
                })
                for k, v in api_template["headers"].items():
                    if k.lower() in ("authorization", "x-requested-with", "accept", "cookie"):
                        session.headers[k] = v

                for page_num in range(got_pages, total_pages + 1):
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
                        all_hits_found.extend(hits)
                        print(f"    📥 補齊第 {page_num}/{total_pages} 頁，+{len(hits)} 筆，累計 {len(all_hits_found)}")
                        time.sleep(0.5)
                    except Exception as e:
                        print(f"    ❌ 第 {page_num} 頁失敗: {e}")

            # ==========================================
            # STEP 4: 解析所有 hits
            # ==========================================
            all_articles = parse_hits(all_hits_found, base_url, seen_links)
            print(f"\n  📋 共解析出 {len(all_articles)} 篇有效文章，開始下載 PDF...\n")

            # ==========================================
            # STEP 5: 進入每篇文章內頁，找 PDF 連結下載
            # ==========================================
            session_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Referer":    "https://www.dbs.com.tw/",
            }

            # 已在保底 reports 裡的檔名
            existing_fnames = set(existing_reports.keys())

            for title, article_url, pub_date in all_articles:
                safe_title     = re.sub(r'[\\/*?:"<>|]', "_", f"{title} ({pub_date})").strip()
                local_filename = f"{safe_title}.pdf"
                local_filepath = os.path.join(download_path, local_filename)

                # 已在保底清單裡，更新 Link 為真實 URL 後跳過
                if local_filename in existing_fnames:
                    for r in reports:
                        if r.get("LocalPath") == local_filepath:
                            r["Link"] = article_url
                    continue

                # 已下載但不在保底清單（本次新爬到的舊檔）
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

    # 去重（同 LocalPath 只保留一筆）
    seen_paths = set()
    deduped    = []
    for r in reports:
        key = r.get("LocalPath", r.get("Link", ""))
        if key not in seen_paths:
            seen_paths.add(key)
            deduped.append(r)
    reports = deduped

    print(f"\n✅ 爬取完畢，共回傳 {len(reports)} 份報告。")
    return reports


if __name__ == "__main__":
    results = scrape()
    print("\n=== 結果預覽 ===")
    for r in results:
        print(r)
