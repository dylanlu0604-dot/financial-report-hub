import os
import re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 財政部 (MOF) - 🚀 啟動「財政貿易統計」物理抓取模式...")
    reports = []
    seen_links = set()
    download_path = os.path.abspath("all report pdf")
    os.makedirs(download_path, exist_ok=True)
    
    target_url = "https://www.mof.gov.tw/multiplehtml/384fb3077bb349ea973e7fc6f13b6974"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                accept_downloads=True
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            print(f"  🌐 進入財政部統計清單頁面...")
            page.goto(target_url, wait_until="networkidle", timeout=60000)
            
            # 確保「財政貿易統計」已選取
            try:
                if not page.locator("#categoryCode9").is_checked():
                    page.check("#categoryCode9")
                    page.click("input[value='查 詢']")
                    page.wait_for_timeout(3000)
            except: pass

            # 🌟 步驟 1：先抓取表格中所有的項目數據，不要在 loop 裡操作 DOM
            rows_data = page.evaluate("""
                () => {
                    let results = [];
                    document.querySelectorAll('table.table-list tbody tr').forEach(row => {
                        let linkEl = row.querySelector('td[data-title="標題："] a');
                        let dateEl = row.querySelector('td[data-title="發布日期："] span');
                        if (linkEl && dateEl) {
                            results.push({
                                title: linkEl.innerText.trim(),
                                url: linkEl.href,
                                date: dateEl.innerText.trim()
                            });
                        }
                    });
                    return results;
                }
            """)
            
            print(f"  🎯 表格共找到 {len(rows_data)} 筆報告項目，開始分類物理抓取...")
            
            for item in rows_data:
                article_url = item['url']
                raw_title = item['title']
                final_date = item['date']
                
                if article_url in seen_links: continue
                seen_links.add(article_url)
                
                # 檔名清理
                safe_title = re.sub(r'[\\/*?:"<>|]', "_", f"{raw_title} ({final_date})").strip()
                
                # 🌟 步驟 2：物理抓取邏輯
                if ".pdf" in article_url.lower() or "service.mof.gov.tw" in article_url.lower():
                    # A. 外連 PDF：不跳轉，直接用 Request API 抓回二進位檔
                    print(f"    📄 [外連 PDF] 物理抓取中: {raw_title[:20]}...")
                    try:
                        # 帶上 Referer 模擬正常點擊來源
                        response = context.request.get(article_url, headers={"Referer": target_url})
                        if response.status == 200:
                            with open(os.path.join(download_path, f"{safe_title}.pdf"), "wb") as f:
                                f.write(response.body())
                            reports.append({"Source": "MOF", "Date": final_date, "Name": f"{raw_title} ({final_date})", "Link": article_url, "Type": "PDF"})
                            print(f"      ✅ 物理抓取成功！")
                        else:
                            print(f"      ❌ 下載拒絕 (Status {response.status})")
                    except Exception as e:
                        print(f"      ❌ 下載失敗: {str(e)[:30]}")
                
                else:
                    # B. 這是分頁：進去點按鈕下載
                    print(f"    🔎 [進入分頁] 尋找檔案: {raw_title[:20]}...")
                    try:
                        sub_page = context.new_page()
                        Stealth().apply_stealth_sync(sub_page)
                        sub_page.goto(article_url, wait_until="domcontentloaded", timeout=30000)
                        
                        pdf_btn = sub_page.locator("a:has-text('PDF'), a:has-text('下載'), a[href*='Download']").first
                        if pdf_btn.is_visible(timeout=5000):
                            with sub_page.expect_download(timeout=15000) as download_info:
                                pdf_btn.click()
                            download = download_info.value
                            download.save_as(os.path.join(download_path, f"{safe_title}.pdf"))
                            reports.append({"Source": "MOF", "Date": final_date, "Name": f"{raw_title} ({final_date})", "Link": article_url, "Type": "PDF"})
                            print(f"      ✅ 分頁下載成功！")
                        else:
                            print(f"      ❌ 找不到檔案")
                        sub_page.close()
                    except:
                        if 'sub_page' in locals(): sub_page.close()
                        continue
                
                # 禮貌等待，避免被封 IP
                page.wait_for_timeout(1000)
                        
            browser.close()
            
    except Exception as e:
        print(f"  ❌ 爬取異常: {e}")

    print(f"  ✅ 任務完成，總共收錄 {len(reports)} 篇 MOF 報告")
    return reports

if __name__ == "__main__":
    scrape()