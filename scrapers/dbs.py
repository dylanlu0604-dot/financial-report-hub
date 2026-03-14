import os
import re
import json
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

# ==========================================
# 🕷️ 主爬蟲程式：終極 JSON API 直連解析模式
# ==========================================
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

            # ==========================================
            # 🌟 核心：直接抽取底層 JSON 資料庫
            # ==========================================
            raw_json = page.evaluate(
                "() => document.getElementById('__NEXT_DATA__') ? "
                "document.getElementById('__NEXT_DATA__').innerText : ''"
            )

            if not raw_json:
                print("  ❌ 找不到底層資料庫 (__NEXT_DATA__)。")
                browser.close()
                return reports

            data = json.loads(raw_json)

            # 無敵遞迴搜尋器
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

            # ==========================================
            # ✅ 核心修復：解析每篇文章的標題、連結、日期
            # ==========================================
            valid_articles = []
            for hit in hits:
                try:
                    src        = hit.get("_source", {})
                    results    = src.get("results_data", {})
                    date_sort  = src.get("date_sort", {})

                    title      = results.get("Title", "").strip()
                    rel_path   = results.get("RelativeDCRPath", "").strip()
                    fmt        = results.get("Format", "").lower()  # "article" / "video"

                    # 日期：取 PublishedDate，格式 "2026-03-11 11:19:00"
                    raw_date   = date_sort.get("PublishedDate", "")
                    try:
                        pub_date = datetime.strptime(raw_date[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
                    except Exception:
                        pub_date = raw_date[:10] if raw_date else "unknown"

                    # 組出完整文章 URL
                    # rel_path 長得像 templatedata/article/generic/data/en/CIO/...xml
                    # DBS 網站的文章 URL 樣式：
                    #   https://www.dbs.com.tw/personal/aics/templatedata/article/generic/data/en/...xml
                    if rel_path:
                        article_url = f"{base_url}/personal/aics/{rel_path}"
                    else:
                        continue

                    if not title or article_url in seen_links:
                        continue

                    seen_links.add(article_url)
                    valid_articles.append((title, article_url, pub_date, fmt))
                    print(f"    📄 [{pub_date}] [{fmt.upper()}] {title[:60]}")

                except Exception as e:
                    print(f"    ⚠️ 解析單篇文章失敗: {e}")

            print(f"\n  📋 共解析出 {len(valid_articles)} 篇有效文章")
            print(f"  ⬇️  開始嘗試進入內頁下載 PDF...\n")

            # ==========================================
            # 開始進入內頁進行物理下載（僅 article 格式）
            # ==========================================
            for title, article_url, pub_date, fmt in valid_articles:

                # 影片類跳過（無 PDF 可下載）
                if fmt == "video":
                    print(f"    ⏭️  略過影片: {title[:40]}")
                    reports.append({
                        "Source": "DBS",
                        "Date": pub_date,
                        "Name": title,
                        "Link": article_url,
                        "Type": "Video"
                    })
                    continue

                print(f"    🔎 尋找 Download PDF: {title[:40]}... ({pub_date})")

                success = False
                for attempt in range(2):
                    try:
                        page.goto(article_url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(3000)

                        safe_title = re.sub(r'[\\/*?:"<>|]', "_", f"{title} ({pub_date})").strip()

                        try:
                            with page.expect_download(timeout=10000) as download_info:
                                clicked = page.evaluate("""
                                    () => {
                                        let btn = document.querySelector('[data-testid="download"]');
                                        if (btn) { btn.click(); return true; }
                                        return false;
                                    }
                                """)

                            if not clicked:
                                print("      ❌ 找不到 Download PDF 按鈕 (非 PDF 報告)")
                                # 仍記錄連結
                                reports.append({
                                    "Source": "DBS",
                                    "Date": pub_date,
                                    "Name": title,
                                    "Link": article_url,
                                    "Type": "Article (No PDF)"
                                })
                                success = True
                                break

                            download = download_info.value
                            save_path = os.path.join(download_path, f"{safe_title}.pdf")
                            download.save_as(save_path)

                            reports.append({
                                "Source": "DBS",
                                "Date": pub_date,
                                "Name": title,
                                "Link": article_url,
                                "Type": "PDF"
                            })
                            print(f"      ✅ [下載成功] {pub_date}")
                            success = True
                            break

                        except Exception as de:
                            print(f"      ❌ 下載超時或攔截失敗: {str(de)[:50]}")
                            reports.append({
                                "Source": "DBS",
                                "Date": pub_date,
                                "Name": title,
                                "Link": article_url,
                                "Type": "Article (Download Failed)"
                            })
                            success = True
                            break

                    except Exception as e:
                        print(f"    ⚠️ 內頁載入失敗 (第 {attempt+1} 次): {str(e)[:50]}")
                        page.wait_for_timeout(1000)

                if not success:
                    print(f"    ❌ 內頁最終放棄: {article_url}")

            browser.close()

    except Exception as e:
        print(f"  ❌ 爬取總體異常: {e}")

    print(f"\n✅ 爬取完畢，共回傳 {len(reports)} 筆記錄。")
    return reports


if __name__ == "__main__":
    results = scrape()
    print("\n=== 結果預覽 ===")
    for r in results[:5]:
        print(r)
