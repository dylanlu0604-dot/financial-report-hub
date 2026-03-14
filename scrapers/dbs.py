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
            
            # 🌟 無敵遞迴搜尋器：不管星展把資料藏在 JSON 的第幾層，全部挖出來！
            def find_hits(obj):
                if isinstance(obj, dict):
                    # 只要發現目標特徵，立刻攔截並回傳
                    if 'fetchedInitialArticles' in obj and 'hits' in obj['fetchedInitialArticles']:
                        return obj['fetchedInitialArticles']['hits']
                    # 否則繼續往下挖
                    for k, v in obj.items():
                        res = find_hits(v)
                        if res is not None:
                            return res
                elif isinstance(obj, list):
                    # 如果遇到陣列，就逐個檢查裡面的物件
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
            
            valid_articles = []
            
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
