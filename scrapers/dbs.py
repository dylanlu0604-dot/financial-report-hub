import os
import re
import json
import requests
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def scrape():
    print("🔍 正在爬取 DBS (星展銀行) - ⚡️ 終極 JSON API 直連解析模式...")
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

            print(f"  🌐 掃描目錄: Archive 總表")

            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)
            except Exception as e:
                print(f"    ⚠️ 目錄載入超時: {str(e)[:50]}")
                return reports

            raw_json = page.evaluate(
                "() => document.getElementById('__NEXT_DATA__') ? "
                "document.getElementById('__NEXT_DATA__').innerText : ''"
            )

            if not raw_json:
                print("  ❌ 找不到底層資料庫 (__NEXT_DATA__)。")
                browser.close()
                return reports

            data = json.loads(raw_json)

            def find_hits(obj):
                if isinstance(obj, dict):
                    if 'fetchedInitialArticles' in obj and 'hits' in obj['fetchedInitialArticles']:
                        return obj['fetchedInitialArticles']['hits']
                    for v in obj.values():
                        res = find_hits(v)
                        if res is not None:
                            return res
                elif isinstance(obj, list):
                    for item in obj:
                        res = find_hits(item)
                        if res is not None:
                            return res
                return None

            hits = find_hits(data)

            if not hits:
                print("  ❌ JSON 結構解析失敗，無法找到文章列表。")
                browser.close()
                return reports

            print(f"  ✅ 找到 {len(hits)} 篇文章，開始解析...")

            valid_articles = []
            for hit in hits:
                try:
                    src       = hit.get("_source", {})
                    results   = src.get("results_data", {})
                    date_sort = src.get("date_sort", {})
                    search    = src.get("search_data", {})

                    title    = results.get("Title", "").strip()
                    rel_path = results.get("RelativeDCRPath", "").strip()
                    fmt      = results.get("Format", "").lower()

                    # ✅ 排除 YouTube 連結
                    video_url = search.get("VideoDetails", {}).get("VideoURL", "")
                    if "youtube" in video_url.lower():
                        print(f"    ⏭️  略過 YouTube: {title[:50]}")
                        continue

                    # ✅ 排除 video 格式
                    if fmt == "video":
                        print(f"    ⏭️  略過影片: {title[:50]}")
                        continue

                    raw_date = date_sort.get("PublishedDate", "")
                    try:
                        pub_date = datetime.strptime(raw_date[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
                    except Exception:
                        pub_date = raw_date[:10] if raw_date else "unknown"

                    if not rel_path or not title:
                        continue

                    # ✅ 修正：正確的 URL 要包含 /archive/
                    article_url = f"{base_url}/personal/aics/archive/{rel_path}"

                    if article_url in seen_links:
                        continue
                    seen_links.add(article_url)

                    valid_articles.append((title, article_url, pub_date))
                    print(f"    📄 [{pub_date}] {title[:60]}")

                except Exception as e:
                    print(f"    ⚠️ 解析單篇文章失敗: {e}")

            print(f"\n  📋 共 {len(valid_articles)} 篇，開始進入內頁抓取 PDF 連結...\n")

            session_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            }

            for title, article_url, pub_date in valid_articles:
                print(f"    🔎 [{pub_date}] {title[:45]}...")

                success = False
                for attempt in range(2):
                    try:
                        page.goto(article_url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(3000)

                        # ✅ 從頁面 HTML 中找出真實的 PDF 下載連結
                        # 文章頁面的 PDF 連結格式：
                        #   https://www.dbs.com.sg/wrapperapi/generic/download-pdf?pdf_path=content/article/pdf/...
                        pdf_url = page.evaluate("""
                            () => {
                                // 找所有 <a> 連結
                                let links = [...document.querySelectorAll('a[href]')];

                                // 優先：找 dbs.com.sg/wrapperapi 的 PDF 連結
                                let wrapper = links.find(a =>
                                    a.href.includes('wrapperapi') && a.href.includes('download-pdf')
                                );
                                if (wrapper) return wrapper.href;

                                // 備援：找任何 href 直接是 .pdf 的連結
                                let direct = links.find(a =>
                                    a.href.toLowerCase().endsWith('.pdf')
                                );
                                if (direct) return direct.href;

                                return null;
                            }
                        """)

                        if not pdf_url:
                            print(f"      ⚠️  頁面找不到 PDF 連結，略過")
                            success = True
                            break

                        print(f"      🔗 PDF 連結: {pdf_url[:80]}")

                        # ✅ 用 requests 直接下載 PDF（不靠瀏覽器點擊）
                        safe_title = re.sub(r'[\\/*?:"<>|]', "_", f"{title} ({pub_date})").strip()
                        save_path = os.path.join(download_path, f"{safe_title}.pdf")

                        cookies = {c['name']: c['value'] for c in context.cookies()}
                        resp = requests.get(pdf_url, headers=session_headers, cookies=cookies, timeout=30, stream=True)

                        if resp.status_code == 200 and 'pdf' in resp.headers.get('Content-Type', '').lower():
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
                            print(f"      ❌ PDF 下載失敗 (HTTP {resp.status_code}, Content-Type: {resp.headers.get('Content-Type', '?')})")

                        success = True
                        break

                    except Exception as e:
                        print(f"    ⚠️ 內頁載入失敗 (第 {attempt+1} 次): {str(e)[:60]}")
                        page.wait_for_timeout(1500)

                if not success:
                    print(f"    ❌ 最終放棄: {article_url}")

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
