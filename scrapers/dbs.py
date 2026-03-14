import os
import re
import json
import requests
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def parse_hits(hits, base_url, seen_links):
    """解析 hits 陣列，回傳 valid_articles list"""
    valid = []
    for hit in hits:
        try:
            src      = hit.get("_source", {})
            results  = src.get("results_data", {})
            search   = src.get("search_data", {})
            date_sort = src.get("date_sort", {})

            title    = results.get("Title", "").strip()
            rel_path = results.get("RelativeDCRPath", "").strip()
            fmt      = results.get("Format", "").lower()

            # 排除 YouTube
            video_url = search.get("VideoDetails", {}).get("VideoURL", "")
            if "youtube" in video_url.lower():
                print(f"    ⏭️  略過 YouTube: {title[:50]}")
                continue

            # 排除 video 格式
            if fmt == "video":
                print(f"    ⏭️  略過影片: {title[:50]}")
                continue

            if not rel_path or not title:
                continue

            raw_date = date_sort.get("PublishedDate", "")
            try:
                pub_date = datetime.strptime(raw_date[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
            except Exception:
                pub_date = raw_date[:10] if raw_date else "unknown"

            # ✅ 正確 URL：/personal/aics/archive/{RelativeDCRPath}
            article_url = f"{base_url}/personal/aics/archive/{rel_path}"

            if article_url in seen_links:
                continue
            seen_links.add(article_url)

            valid.append((title, article_url, pub_date))
            print(f"    📄 [{pub_date}] {title[:60]}")

        except Exception as e:
            print(f"    ⚠️ 解析單篇失敗: {e}")
    return valid


def scrape():
    print("🔍 正在爬取 DBS (星展銀行) - 全量分頁抓取模式...")
    reports = []
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
            # STEP 1：載入首頁，取初始 10 筆 + API 資訊
            # ==========================================
            print("  🌐 載入 Archive 首頁...")

            # 攔截 API 請求，找出分頁 endpoint
            api_endpoint = {"url": None, "post_body": None}
            intercepted_responses = []

            def handle_response(response):
                url = response.url
                # 找包含 article 關鍵字的 API 請求
                if ("twarticlesvc" in url or "archiv" in url.lower()) and response.status == 200:
                    try:
                        body = response.json()
                        if "hits" in body or "fetchedInitialArticles" in str(body)[:200]:
                            intercepted_responses.append({"url": url, "body": body})
                            print(f"    🎯 攔截到 API: {url[:80]}")
                    except Exception:
                        pass

            page.on("response", handle_response)

            try:
                page.goto(target_url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(3000)
            except Exception as e:
                print(f"    ⚠️ 首頁載入超時: {str(e)[:50]}")

            # 從 __NEXT_DATA__ 取初始資料
            raw_json = page.evaluate(
                "() => document.getElementById('__NEXT_DATA__') ? "
                "document.getElementById('__NEXT_DATA__').innerText : ''"
            )
            if not raw_json:
                print("  ❌ 找不到 __NEXT_DATA__。")
                browser.close()
                return reports

            next_data = json.loads(raw_json)

            # 找 ARTICLE_API_BASE_URL
            page_env    = next_data.get("props", {}).get("pageEnv", {})
            article_api = page_env.get("ARTICLE_API_BASE_URL", "").rstrip("/")
            print(f"  📡 Article API: {article_api}")

            # 找初始 hits 和總筆數
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

            initial   = find_key(next_data, "fetchedInitialArticles") or {}
            total     = initial.get("total", {}).get("value", 0)
            first_hits = initial.get("hits", [])
            print(f"  📊 總文章數: {total}，首批: {len(first_hits)} 筆")

            # ==========================================
            # STEP 2：解析首批 10 筆
            # ==========================================
            all_articles = parse_hits(first_hits, base_url, seen_links)

            # ==========================================
            # STEP 3：捲動頁面觸發後續分頁載入
            # 每次捲到底，等待新文章載入，重複直到拿齊
            # ==========================================
            print(f"\n  🔄 開始捲動分頁載入（目標: {total} 筆）...")

            max_scrolls = (total // 10) + 5  # 多幾次保險
            prev_count  = len(all_articles)

            for scroll_i in range(max_scrolls):
                if len(seen_links) >= total:
                    print(f"  ✅ 已達總筆數 {total}，停止捲動")
                    break

                # 捲到底部觸發 lazy load
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2500)

                # 嘗試點擊 "Load More" 按鈕（如果有的話）
                try:
                    load_more = page.query_selector(
                        "button:has-text('Load More'), button:has-text('load more'), "
                        "[data-testid='load-more'], .load-more"
                    )
                    if load_more:
                        load_more.click()
                        page.wait_for_timeout(2500)
                        print(f"    🖱️  點擊 Load More (第 {scroll_i+1} 次)")
                except Exception:
                    pass

                # 從頁面 DOM 抓取新載入的文章卡片連結
                new_links = page.evaluate("""
                    () => {
                        // 找所有文章卡片的連結
                        let cards = [...document.querySelectorAll('a[href*="templatedata/article"]')];
                        return cards.map(a => a.href);
                    }
                """)

                # 把新的連結加入（先記錄，之後再進內頁）
                new_count = 0
                for link in new_links:
                    if link not in seen_links:
                        seen_links.add(link)
                        new_count += 1

                curr_count = len(seen_links)
                if curr_count > prev_count:
                    print(f"    📥 第 {scroll_i+1} 次捲動，新增 {curr_count - prev_count} 篇，累計 {curr_count}/{total}")
                    prev_count = curr_count
                else:
                    print(f"    ⏸️  第 {scroll_i+1} 次捲動無新內容")
                    # 連續 3 次無新內容就停止
                    if scroll_i > 2:
                        break

            # ==========================================
            # STEP 4：重新從 DOM 抓取所有文章完整資訊
            # ==========================================
            print(f"\n  📋 從 DOM 抓取所有文章完整資訊...")

            # 先重置，改從 DOM 直接掃
            all_article_urls = page.evaluate("""
                () => {
                    let cards = [...document.querySelectorAll('a[href*="templatedata/article"]')];
                    // 去重
                    return [...new Set(cards.map(a => a.href))];
                }
            """)

            print(f"  🔗 DOM 中找到 {len(all_article_urls)} 個文章連結")

            # 補上從 __NEXT_DATA__ 解析的首批（因為 DOM 可能沒顯示日期等資訊）
            # 用 all_article_urls 作為最終清單，已在 seen_links 的都算
            final_articles = []
            for url in all_article_urls:
                # 從 URL 推算日期（粗略）
                final_articles.append((url, "unknown"))

            # 把 parse_hits 拿到的加回來（有正確日期和標題）
            known = {url: (title, pub_date) for title, url, pub_date in all_articles}

            print(f"\n  ⬇️  開始進入 {len(all_article_urls)} 篇文章內頁下載 PDF...\n")

            session_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            }

            for article_url in all_article_urls:
                title, pub_date = known.get(article_url, (article_url.split("/")[-1].replace(".xml",""), "unknown"))
                print(f"    🔎 {title[:50]}... ({pub_date})")

                for attempt in range(2):
                    try:
                        page.goto(article_url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(3000)

                        safe_title = re.sub(r'[\\/*?:"<>|]', "_", f"{title} ({pub_date})").strip()

                        # ✅ 找頁面中真實的 PDF 下載連結
                        pdf_url = page.evaluate("""
                            () => {
                                let links = [...document.querySelectorAll('a[href]')];

                                // wrapperapi download-pdf 連結
                                let wrapper = links.find(a =>
                                    a.href.includes('wrapperapi') && a.href.includes('download-pdf')
                                );
                                if (wrapper) return wrapper.href;

                                // 直接 .pdf 連結
                                let direct = links.find(a =>
                                    a.href.toLowerCase().endsWith('.pdf') &&
                                    !a.href.includes('service_fee') &&
                                    !a.href.includes('General%20Agreement')
                                );
                                if (direct) return direct.href;

                                return null;
                            }
                        """)

                        if not pdf_url:
                            print(f"      ⚠️  找不到 PDF 連結，略過")
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

                        content_type = resp.headers.get('Content-Type', '')
                        if resp.status_code == 200 and 'pdf' in content_type.lower():
                            save_path = os.path.join(download_path, f"{safe_title}.pdf")
                            with open(save_path, 'wb') as f:
                                for chunk in resp.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            reports.append({
                                "Source": "DBS",
                                "Date": pub_date,
                                "Name": title,
                                "Link": article_url,
                                "PDF_URL": pdf_url,
                                "Type": "PDF"
                            })
                            print(f"      ✅ 下載成功 → {safe_title}.pdf")
                        else:
                            print(f"      ❌ 下載失敗 (HTTP {resp.status_code}, {content_type})")
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
