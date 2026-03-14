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
                page.wait_for_timeout(3000) # 給網頁一點時間載入腳本
            except Exception as e:
                print(f"    ⚠️ 目錄載入超時: {str(e)[:30]}")
                return reports
            
            # ==========================================
            # 🌟 核心殺手鐧：直接抽取出底層的 JSON 資料庫
            # ==========================================
            raw_json = page.evaluate("() => document.getElementById('__NEXT_DATA__') ? document.getElementById('__NEXT_DATA__').innerText : ''")
            
            if not raw_json:
                print("  ❌ 找不到底層資料庫 (__NEXT_DATA__)，網頁結構可能已改變。")
                browser.close()
                return reports
                
            data = json.loads(raw_json)
            
            try:
                # 根據你提供的 HTML 結構，精準定位最新文章列表
                hits = data['props']['pageProps']['fetchedInitialArticles']['hits']
            except KeyError:
                print("  ❌ JSON 結構解析失敗，無法找到文章列表。")
                browser.close()
                return reports
            
            valid_articles = []
            
            # 遍歷資料庫裡的所有最新報告
            for hit in hits:
                source = hit.get('_source', {})
                res_data = source.get('results_data', {})
                date_sort = source.get('date_sort', {})
                
                title = res_data.get('Title', 'Unknown Title')
                fmt = res_data.get('Format', 'article')
                dcr_path = res_data.get('RelativeDCRPath', '')
                raw_date = date_sort.get('PublishedDate', '')
                
                # 🌟 秒殺 YouTube：只要 API 說它是影片 (video)，立刻踢掉，絕不浪費時間！
                if fmt == 'video':
                    print(f"    ⏭️ [API 過濾] 成功跳過影片: {title[:30]}...")
                    continue
                    
                # 擷取精準日期 (例如 "2026-03-11 11:19:00" -> "2026-03-11")
                pub_date = raw_date.split(' ')[0] if raw_date else datetime.now().strftime("%Y-%m-%d")
                
                # 構建真實的內頁網址
                actual_url = f"https://www.dbs.com.tw/personal/aics/article.page?dcrPath={dcr_path}"
                
                if actual_url not in seen_links:
                    valid_articles.append((title, actual_url, pub_date))
                    seen_links.add(actual_url)
            
            print(f"    🎯 API 萃取完畢！發現 {len(valid_articles)} 篇【非影片】的最新報告，準備下載...")
            
            # ==========================================
            # 開始進入內頁進行物理下載
            # ==========================================
            for title, article_url, pub_date in valid_articles:
                print(f"    🔎 尋找 Download PDF: {title[:25]}... ({pub_date})")
                
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
                                        if (btn) {
                                            btn.click();
                                            return true;
                                        }
                                        return false;
                                    }
                                """)
                                
                            if not clicked:
                                print("      ❌ 找不到 Download PDF 按鈕 (非 PDF 報告)")
                                success = True 
                                break
                                
                            download = download_info.value
                            save_path = os.path.join(download_path, f"{safe_title}.pdf")
                            download.save_as(save_path)
                            
                            reports.append({
                                "Source": "DBS",
                                "Date": pub_date,
                                "Name": f"{title} ({pub_date})",
                                "Link": article_url,
                                "Type": "PDF"
                            })
                            print(f"      ✅ [下載成功] {pub_date}")
                            success = True
                            break 
                            
                        except Exception as de:
                            print(f"      ❌ 下載超時或攔截失敗: {str(de)[:30]}")
                            success = True 
                            break
                            
                    except Exception as e:
                        print(f"    ⚠️ 內頁載入失敗 (第 {attempt+1} 次): {str(e)[:30]}")
                        page.wait_for_timeout(1000)
                        
                if not success:
                    print(f"    ❌ 內頁最終放棄: {article_url}")
                    
            browser.close()
            
    except Exception as e:
        print(f"  ❌ 爬取總體異常: {e}")

    return reports

if __name__ == "__main__":
    scrape()
