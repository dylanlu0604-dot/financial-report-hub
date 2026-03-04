import os
import re
import urllib.parse
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime
from datetime import datetime

# ⚙️ 與 main.py 保持一致
GITHUB_USER = "dylanlu0604-dot"
GITHUB_REPO = "financial-report-hub"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/all%20report%20pdf"

# ==========================================
# 🛠️ 輔助工具：越南日期轉西元
# ==========================================
def convert_vn_date(date_text):
    if not date_text: return datetime.now().strftime("%Y-%m-%d")
    match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', date_text)
    if match:
        d, m, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return f"{y}-{m:02d}-{d:02d}"
    return datetime.now().strftime("%Y-%m-%d")

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 KBSV (越南 KB 證券) - 🚀 啟動「前 5 篇 + 自動重試」模式...")
    reports = []
    seen_pdfs = set()
    download_path = os.path.abspath("all report pdf")
    os.makedirs(download_path, exist_ok=True)
    
    target_categories = [
        {"name": "Weekly", "url": "https://www.kbsec.com.vn/vi/ban-tin-tuan.htm"},
        {"name": "Company", "url": "https://www.kbsec.com.vn/vi/bao-cao-cong-ty.htm"},
        {"name": "Sector", "url": "https://www.kbsec.com.vn/vi/bao-cao-nganh.htm"},
        {"name": "Macro", "url": "https://www.kbsec.com.vn/vi/bao-cao-trien-vong-kinh-te-vi-mo.htm"},
        {"name": "Strategy", "url": "https://www.kbsec.com.vn/vi/bao-cao-chien-luoc-thi-truong.htm"},
        {"name": "Thematic", "url": "https://www.kbsec.com.vn/vi/bao-cao-chuyen-de.htm"}
    ]
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            for cat in target_categories:
                print(f"  🌐 分類掃描: {cat['name']}...")
                
                success_load = False
                # 🌟 修正 1：失敗重試機制 (最多試 3 次)
                for attempt in range(3):
                    try:
                        # 降低等待門檻，只要 domcontentloaded 即可
                        page.goto(cat['url'], wait_until="domcontentloaded", timeout=40000)
                        page.wait_for_timeout(3000) # 給予緩衝時間讓 JS 渲染
                        
                        # 檢查關鍵容器是否存在
                        if page.locator(".itemNews").count() > 0 or page.locator(".item").count() > 0:
                            success_load = True
                            break
                        else:
                            print(f"    ⚠️ 第 {attempt+1} 次嘗試：頁面內容未完全加載，正在重試...")
                            page.reload()
                    except Exception as e:
                        print(f"    ⚠️ 第 {attempt+1} 次嘗試失敗: {str(e)[:50]}")
                        page.wait_for_timeout(2000)

                if not success_load:
                    print(f"    ❌ 分類載入最終失敗: {cat['name']}")
                    continue
                    
                # 🌟 修正 2：改用更精準的 CSS 選擇器提取資料
                items_data = page.evaluate("""
                    () => {
                        let results = [];
                        // 針對 KBSV 結構進行優化
                        let items = document.querySelectorAll('.itemNews .item, .list-news .item');
                        items.forEach(item => {
                            let titleEl = item.querySelector('h3 a, .name a');
                            let dateEl = item.querySelector('.date, .time, .thongKe');
                            let downloadBtn = item.querySelector('a.more, a[href$=".pdf"]');
                            
                            let url = downloadBtn ? downloadBtn.href : (titleEl ? titleEl.href : "");
                            
                            if (url && url.toLowerCase().includes('.pdf')) {
                                results.push({
                                    title: titleEl ? titleEl.innerText.trim() : "Untitled",
                                    pdf_url: url,
                                    date_text: dateEl ? dateEl.innerText.trim() : ""
                                });
                            }
                        });
                        return results;
                    }
                """)
                
                top_5 = items_data[:5]
                print(f"    🎯 找到 {len(items_data)} 篇，鎖定前 {len(top_5)} 篇下載...")
                
                for data in top_5:
                    pdf_url = data['pdf_url']
                    if pdf_url in seen_pdfs: continue
                    seen_pdfs.add(pdf_url)
                    
                    final_date = convert_vn_date(data['date_text'])
                    raw_title = data['title']
                    safe_title = re.sub(r'[\\/*?:"<>|]', "_", f"{raw_title} ({final_date})").strip()
                    save_path = os.path.join(download_path, f"{safe_title}.pdf")
                    
                    print(f"    📄 物理下載: {raw_title[:20]}... ({final_date})")
                    
                    try:
                        # 帶上來源 Referer，這是避開防爬蟲的關鍵
                        response = context.request.get(pdf_url, headers={"Referer": cat['url']})
                        if response.status == 200 and b'%PDF' in response.body()[:10]:
                            with open(save_path, "wb") as f:
                                f.write(response.body())
                            
                            encoded_filename = urllib.parse.quote(f"{safe_title}.pdf")
                            github_link = f"{GITHUB_RAW_BASE}/{encoded_filename}"
                            reports.append({
                                "Source": f"KBSV ({cat['name']})",
                                "Date": final_date,
                                "Name": f"{raw_title} ({final_date})",
                                "Link": github_link,
                                "Type": "PDF",
                                "LocalPath": save_path
                            })
                            print(f"      ✅ [下載成功]")
                        else:
                            print(f"      ❌ [檔案無效]")
                    except Exception as e:
                        print(f"      ❌ [出錯] {str(e)[:15]}")
                            
            browser.close()
            
    except Exception as e:
        print(f"  ❌ KBSV 總體錯誤: {e}")

    print(f"  ✅ 任務結束：總共實體收錄 {len(reports)} 篇越南報告")
    return reports

if __name__ == "__main__":
    scrape()
