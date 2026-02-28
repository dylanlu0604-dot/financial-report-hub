import json
import os
import importlib
import pkgutil
import scrapers
import requests
import pdfplumber
import io
import random
import time
import re
import urllib.parse
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

load_dotenv()

# ==========================================
# ⚙️ 全域設定 (請確認您的 GitHub 資訊)
# ==========================================
ENABLE_AI_SUMMARY = False  
GITHUB_USER = "dylanlu0604-dot"
GITHUB_REPO = "financial-report-hub"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/all%20report%20pdf"

# ==========================================
# 🚀 主程式執行區塊
# ==========================================
def main():
    print(f"\n{'='*60}\n🚀 開始執行自動化爬蟲程序...\n{'='*60}\n")
    
    # 🌟 暴力清空法：強迫機器人刪除舊資料夾，解決網站不讓刪的問題
    import shutil
    bad_folders = ["all report pdf", "data"]
    for folder in bad_folders:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"🧹 已強行刪除損壞的資料夾: {folder}")
    os.makedirs("all report pdf", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    
    all_reports = []
    # ... 後面的程式碼維持不變 ...
    
    # 🌟 重新加回：測試名單設定 (想跑全部時，請把下面 if 那行註解掉) 🎯 🎯 🎯 🎯 🎯 🎯 🎯 🎯 🎯 🎯 🎯 🎯 🎯
    
    for _, module_name, _ in pkgutil.iter_modules(scrapers.__path__):
        if module_name == "utils": continue
        
        # 🌟 重新加回：選取部分爬蟲測試
        #target_scrapers = ["refinitiv"] 

        #if module_name not in target_scrapers: 
            #continue 
            
        try:
            module = importlib.import_module(f"scrapers.{module_name}")
            if hasattr(module, "scrape"):
                results = module.scrape()
                if results: all_reports.extend(results)
        except Exception as e:
            print(f"❌ 載入 {module_name} 失敗: {e}")

    if not all_reports:
        print("\n❌ 未抓到任何資料"); return

    # 🧹 資料清理：Regex 日期標準化與動態天數過濾
    unique_reports = []
    seen_links = set()
    for report in all_reports:
        if report['Link'] in seen_links: continue
        raw_date = str(report.get('Date', '')).strip()
        dt_obj = None
        # 強制抓取 YYYY-MM-DD 數字
        match = re.search(r'(\d{4})[^\d]*(\d{1,2})[^\d]*(\d{1,2})', raw_date)
        if match:
            clean_date = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
            try:
                dt_obj = datetime.strptime(clean_date, "%Y-%m-%d")
                report['Date'] = dt_obj.strftime("%Y-%m-%d")
            except: pass
            
        # 🌟 關鍵修改：針對不同報告設定專屬的天數限制
        if "Top of Mind" in report.get('Name', ''):
            days_limit = 90  # 高盛 Top of Mind 放寬到近 90 天
        else:
            days_limit = 30  # 其他所有銀行的報告維持近 30 天
            
        # 根據上面設定的 days_limit 來過濾日期
        if report.get('Date') == "未知日期" or not report.get('Date') or (dt_obj and (datetime.now() - dt_obj).days <= days_limit):
            unique_reports.append(report)
            seen_links.add(report['Link'])

    print(f"\n📊 總共找到 {len(unique_reports)} 筆符合條件的報告。")
    
    # ==========================================
    # 📥 終極修正：物理隔離下載與轉檔模式 (支援韓股秒抓)
    # ==========================================
    print(f"\n{'='*60}\n📥 啟動【物理隔離】下載與轉檔模式...\n")
    pdf_folder = "all report pdf"
    os.makedirs(pdf_folder, exist_ok=True)
    
    for i, report in enumerate(unique_reports, 1):
        original_url = report.get('Link', '')
        report['PageCount'] = "未知" 
        
        # 🌟 修正 1：把 'downpdf' 加入判斷，讓系統知道這是實體 PDF，不要把它當網頁印！
        is_web_article = report.get('Type') == 'Web' or not ('.pdf' in original_url.lower() or 'download' in original_url.lower() or 'downpdf' in original_url.lower())

        safe_title = re.sub(r'[\\/*?:"<>|]', "_", report['Name']).strip()
        local_filename = f"{safe_title}.pdf"
        local_filepath = os.path.join(pdf_folder, local_filename)
        encoded_filename = urllib.parse.quote(local_filename)
        
        report['OriginalLink'] = original_url
        report['Link'] = f"{GITHUB_RAW_BASE}/{encoded_filename}"
        report['LocalPath'] = f"{pdf_folder}/{encoded_filename}"

        if os.path.exists(local_filepath):
            print(f"[{i}/{len(unique_reports)}] ✅ 檔案已存在: {report['Name'][:15]}...")
        else:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        accept_downloads=True
                    )
                    page = context.new_page()
                    Stealth().apply_stealth_sync(page)

                    # 🌐 路線 A：網頁文章 -> 直接列印成 PDF
                    if is_web_article:
                        print(f"[{i}/{len(unique_reports)}] 🖨️ 網頁轉PDF中: {report['Name'][:15]}...")
                        try:
                            page.goto(original_url, wait_until="domcontentloaded", timeout=15000)
                            page.wait_for_timeout(3000)
                        except: pass
                        
                        try:
                            page.evaluate("""
                                const junk = document.querySelectorAll('header, footer, nav, aside, .ad, .sidebar, iframe');
                                junk.forEach(el => el.style.display = 'none');
                            """)
                        except: pass
                        
                        page.pdf(
                            path=local_filepath, 
                            format="A4", 
                            print_background=True, 
                            margin={"top": "20px", "bottom": "20px", "left": "20px", "right": "20px"}
                        )
                        print("    ✅ 網頁自動轉 PDF 成功！")

                    # 📥 路線 B：傳統 PDF -> 直接下載
                    else:
                        print(f"[{i}/{len(unique_reports)}] 🕵️ 實體 PDF 下載: {report['Name'][:15]}...")
                        
                        # 🌟 修正 2：Hankyung 專屬秒抓通道 (繞過防盜鏈，不需等待 30 秒)
                        if "hankyung.com" in original_url:
                            # 1. 先進入首頁取得通行證 (Cookies)
                            page.goto("https://consensus.hankyung.com", wait_until="domcontentloaded", timeout=15000)
                            # 2. 直接發送帶有防盜鏈 (Referer) 的請求抓檔案
                            res = page.request.get(original_url, headers={"Referer": "https://consensus.hankyung.com/analysis/list"})
                            
                            # 確認抓下來的內容真的是 PDF 格式
                            if b'%PDF' in res.body()[:10]:
                                with open(local_filepath, "wb") as f: f.write(res.body())
                                print("    ✅ 韓國券商 PDF 秒抓成功！")
                            else:
                                print("    ❌ 抓取失敗 (內容非 PDF，可能被阻擋)")
                        
                        # 其他銀行的正常下載邏輯
                        else:
                            if "ctbcbank" in original_url:
                                page.goto("https://www.ctbcbank.com/twrbo/zh_tw/index.html", wait_until="networkidle", timeout=30000)
                                time.sleep(random.uniform(2, 4))

                            try:
                                with page.expect_download(timeout=30000) as download_info:
                                    cache_buster = f"&t={int(time.time() * 1000)}" if "?" in original_url else f"?t={int(time.time() * 1000)}"
                                    page.goto(original_url + cache_buster, wait_until="domcontentloaded", timeout=45000)
                                
                                download = download_info.value
                                download.save_as(local_filepath)
                                print(f"    ✅ 下載成功")
                            except Exception:
                                if original_url.startswith("http"):
                                    res = context.request.get(original_url, headers={"Referer": original_url})
                                    if b'%PDF' in res.body()[:10]:
                                        with open(local_filepath, "wb") as f: f.write(res.body())
                                        print("    ✅ 備案轉存成功！")

                    browser.close()

                except Exception as e:
                    print(f"    ❌ 下載或轉檔失敗: {str(e)[:50]}")

        # 讀取本地 PDF 頁數
        if os.path.exists(local_filepath):
            try:
                with pdfplumber.open(local_filepath) as pdf:
                    report['PageCount'] = len(pdf.pages)
            except:
                report['PageCount'] = "讀取失敗"

        # 🌟 修正點：刪除這裡原本的 browser.close()，因為上面已經 closed 了

    # 🤖 摘要邏輯
    for report in unique_reports: report['Summary'] = "未執行 AI 摘要"
    
    # 📝 輸出生成
    os.makedirs('data', exist_ok=True)
    unique_reports.sort(key=lambda x: x.get('Date', ''), reverse=True)
    with open('data/reports.json', 'w', encoding='utf-8') as f:
        json.dump(unique_reports, f, ensure_ascii=False, indent=2)

    # ==========================================
    # 📝 輸出 1：Markdown 生成 (統一使用 GitHub Raw 連結)
    # ==========================================
    md_content = "# 📊 最新財經報告總覽\n\n"
    for report in unique_reports:
        md_content += f"### {report['Name']}\n來源: {report['Source']} | 日期: {report['Date']} | 頁數: {report['PageCount']} 頁\n"
        # 🌟 修正：確保使用 Link (https://raw.githubusercontent.com/...)
        md_content += f"[📥 查看報告]({report['Link']})\n\n"
    with open('data/reports_for_notebooklm.md', 'w', encoding='utf-8') as f: f.write(md_content)

    # ==========================================
    # 🌐 輸出 2：HTML 生成 (將點擊網址改為 Raw 連結)
    # ==========================================
    html_content = """<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8"><title>最新財經報告總覽</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f5f7fa; }
        table { width: 100%; border-collapse: collapse; background: white; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
        th, td { padding: 15px; text-align: left; border-bottom: 1px solid #ecf0f1; }
        th { background-color: #2c3e50; color: white; cursor: pointer; }
        .page-badge { background: #e8f4fd; color: #2980b9; padding: 2px 8px; border-radius: 12px; font-weight: bold; }
    </style></head><body>
    <h1>📊 最新財經報告總覽 (GitHub 存檔)</h1>
    <table id="reportTable"><thead><tr>
        <th onclick="sortTable(0)">機構 ↕</th><th onclick="sortTable(1)">日期 ↕</th>
        <th onclick="sortTable(2)">頁數 ↕</th><th>報告名稱</th><th>AI 摘要</th>
    </tr></thead><tbody>\n"""
    
    for r in unique_reports:
        html_content += f"<tr><td><b>{r['Source']}</b></td><td>{r['Date']}</td><td><span class='page-badge'>{r['PageCount']}</span></td>"
        # 🌟 修正：將 href 從 LocalPath 改成 r['Link']，解決網址變成 .github.io 的問題
        html_content += f"<td><a href='{r['Link']}' target='_blank'>{r['Name']}</a></td><td>{r['Summary']}</td></tr>\n"

    html_content += """</tbody></table><script>
    function sortTable(n){
        var table=document.getElementById("reportTable"), rows=table.rows, switching=true, dir="desc";
        while(switching){
            switching=false; 
            for(var i=1; i<(rows.length-1); i++){
                var x=rows[i].getElementsByTagName("TD")[n], y=rows[i+1].getElementsByTagName("TD")[n], should=false;
                var vX=x.innerText.toLowerCase(), vY=y.innerText.toLowerCase();
                if(n===2){ vX=parseInt(vX)||0; vY=parseInt(vY)||0; }
                if(dir==="desc"){ if(vX<vY){ should=true; break; } } else { if(vX>vY){ should=true; break; } }
            }
            if(should){ rows[i].parentNode.insertBefore(rows[i+1], rows[i]); switching=true; }
            else if(dir==="desc"){ dir="asc"; switching=true; }
        }
    }
    </script></body></html>"""
    with open('index.html', 'w', encoding='utf-8') as f: f.write(html_content)

    # ==========================================
    # 📡 輸出 3：RSS 生成 (統一使用 GitHub Raw 連結)
    # ==========================================
    reports_by_source = {}
    for report in unique_reports:
        source = report.get('Source', 'Unknown')
        if source not in reports_by_source: reports_by_source[source] = []
        reports_by_source[source].append(report)
        
    for source, reports in reports_by_source.items():
        safe_source_name = source.lower().replace(" ", "_")
        rss_filename = f"data/rss_{safe_source_name}.xml"
        rss_content = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"><channel><title>{source} 財經報告</title><link>https://github.com/{GITHUB_USER}/{GITHUB_REPO}</link>
<description>{source} 自動更新源</description>\n"""
        for r in reports:
            # 🌟 修正：這裡的 r['Link'] 確保是 https://raw.githubusercontent.com/...
            rss_content += f"<item><title>{r['Name']}</title><link>{r['Link']}</link><description><![CDATA[📄 頁數：{r['PageCount']}]]></description><pubDate>{r['Date']}</pubDate></item>\n"
        rss_content += "</channel></rss>"
        with open(rss_filename, 'w', encoding='utf-8') as f: f.write(rss_content)
            
    print(f"\n✅ 任務完成！")

if __name__ == "__main__": main()
