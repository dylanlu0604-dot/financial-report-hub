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
    
    # 🌟 暴力清空法：強迫機器人刪除舊資料夾
    import shutil
    bad_folders = ["all report pdf", "data"]
    for folder in bad_folders:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"🧹 已強行刪除損壞的資料夾: {folder}")
    os.makedirs("all report pdf", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    
    all_reports = []
    
    # 🌟 測試名單設定 (想跑全部時，請把 target_scrapers 相關行註解掉)
    for _, module_name, _ in pkgutil.iter_modules(scrapers.__path__):
        if module_name == "utils": continue
        
        測試指定的爬蟲
        target_scrapers = ["ctbc","jri"] 
        if module_name not in target_scrapers: 
            continue 
            
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
        
        match = re.search(r'(\d{4})[^\d]*(\d{1,2})[^\d]*(\d{1,2})', raw_date)
        if match:
            clean_date = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
            try:
                dt_obj = datetime.strptime(clean_date, "%Y-%m-%d")
                report['Date'] = dt_obj.strftime("%Y-%m-%d")
            except: pass
            
        if "Top of Mind" in report.get('Name', ''):
            days_limit = 90  # 高盛 Top of Mind 放寬到近 90 天
        else:
            days_limit = 30  # 其他所有銀行的報告維持近 30 天
            
        if report.get('Date') == "未知日期" or not report.get('Date') or (dt_obj and (datetime.now() - dt_obj).days <= days_limit):
            unique_reports.append(report)
            seen_links.add(report['Link'])

    print(f"\n📊 總共找到 {len(unique_reports)} 筆符合條件的報告。")
    
    # ==========================================
    # 📥 終極修正：物理隔離下載與轉檔模式
    # ==========================================
    print(f"\n{'='*60}\n📥 啟動【物理隔離】下載與轉檔模式...\n")
    pdf_folder = "all report pdf"
    os.makedirs(pdf_folder, exist_ok=True)
    
    try:
        for i, report in enumerate(unique_reports, 1):
            original_url = report.get('Link', '')
            report['PageCount'] = "未知" 
            
            is_web_article = report.get('Type') == 'Web' or not ('.pdf' in original_url.lower() or 'download' in original_url.lower() or 'downpdf' in original_url.lower())

            safe_title = re.sub(r'[\\/*?:"<>|]', "_", str(report.get('Name', 'Unknown'))).strip()
            local_filename = f"{safe_title}.pdf"
            local_filepath = os.path.join(pdf_folder, local_filename)
            encoded_filename = urllib.parse.quote(local_filename)
            
            report['OriginalLink'] = original_url
            base_url = GITHUB_RAW_BASE if 'GITHUB_RAW_BASE' in globals() else ""
            report['Link'] = f"{base_url}/{encoded_filename}"
            report['LocalPath'] = f"{pdf_folder}/{encoded_filename}"

            if os.path.exists(local_filepath):
                print(f"[{i}/{len(unique_reports)}] ✅ 檔案已存在: {report.get('Name', '')[:15]}...")
            else:
                try:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        context = browser.new_context(
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                            accept_downloads=True
                        )
                        page = context.new_page()
                        Stealth().apply_stealth_sync(page)

                        if is_web_article:
                            print(f"[{i}/{len(unique_reports)}] 🖨️ 網頁轉PDF中: {report.get('Name', '')[:15]}...")
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

                        else:
                            print(f"[{i}/{len(unique_reports)}] 🕵️ 實體 PDF 下載: {report.get('Name', '')[:15]}...")
                            
                            if "hankyung.com" in original_url:
                                page.goto("https://consensus.hankyung.com", wait_until="domcontentloaded", timeout=15000)
                                res = page.request.get(original_url, headers={"Referer": "https://consensus.hankyung.com/analysis/list"})
                                if b'%PDF' in res.body()[:10]:
                                    with open(local_filepath, "wb") as f: f.write(res.body())
                                    print("    ✅ 韓國券商 PDF 秒抓成功！")
                                else:
                                    print("    ❌ 抓取失敗 (內容非 PDF)")
                            
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
                                        safe_referer = urllib.parse.quote(original_url, safe=':/=?&')
                                        try:
                                            res = context.request.get(original_url, headers={"Referer": safe_referer})
                                            if b'%PDF' in res.body()[:10]:
                                                with open(local_filepath, "wb") as f: f.write(res.body())
                                                print("    ✅ 備案轉存成功！")
                                            else:
                                                print("    ❌ 備案下載失敗: 檔案非 PDF")
                                        except Exception as backup_e:
                                            print(f"    ❌ 備案轉存也失敗: {str(backup_e)[:30]}")

                        browser.close()

                except Exception as e:
                    print(f"    ❌ Playwright 執行失敗: {str(e)[:50]}")

            if os.path.exists(local_filepath):
                try:
                    with pdfplumber.open(local_filepath) as pdf:
                        report['PageCount'] = len(pdf.pages)
                except:
                    report['PageCount'] = "讀取失敗"

    except Exception as major_e:
        print(f"🔥 下載迴圈發生重大崩潰: {major_e}")

    # 🤖 摘要邏輯
    for report in unique_reports: report['Summary'] = "未執行 AI 摘要"
    
    # 📝 輸出生成
    os.makedirs('data', exist_ok=True)
    unique_reports.sort(key=lambda x: x.get('Date', ''), reverse=True)
    with open('data/reports.json', 'w', encoding='utf-8') as f:
        json.dump(unique_reports, f, ensure_ascii=False, indent=2)

    md_content = "# 📊 最新財經報告總覽\n\n"
    for report in unique_reports:
        md_content += f"### {report['Name']}\n來源: {report['Source']} | 日期: {report['Date']} | 頁數: {report['PageCount']} 頁\n"
        md_content += f"[📥 查看報告]({report['Link']})\n\n"
    with open('data/reports_for_notebooklm.md', 'w', encoding='utf-8') as f: f.write(md_content)

    html_content = """<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8"><title>最新財經報告總覽</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f5f7fa; }
        table { width: 100%; border-collapse: collapse; background: white; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
        th, td { padding: 15px; text-align: left; border-bottom: 1px solid #ecf0f1; }
        th { background-color: #2c3e50; color: white; cursor: pointer; transition: background 0.3s; }
        th:hover { background-color: #34495e; }
        .page-badge { background: #e8f4fd; color: #2980b9; padding: 2px 8px; border-radius: 12px; font-weight: bold; }
    </style></head><body>
    <h1>📊 最新財經報告總覽 (GitHub 存檔)</h1>
    <table id="reportTable"><thead><tr>
        <th onclick="sortTable(0)">機構 ↕</th>
        <th onclick="sortTable(1)">日期 ↕</th>
        <th onclick="sortTable(2)">頁數 ↕</th>
        <th onclick="sortTable(3)">報告名稱 ↕</th>
        <th>AI 摘要</th>
    </tr></thead><tbody>\n"""
    
    for r in unique_reports:
        html_content += f"<tr><td><b>{r['Source']}</b></td><td>{r['Date']}</td><td><span class='page-badge'>{r['PageCount']}</span></td>"
        html_content += f"<td><a href='{r['Link']}' target='_blank'>{r['Name']}</a></td><td>{r['Summary']}</td></tr>\n"

    html_content += """</tbody></table><script>
    let sortDir = {}; // 記錄各欄位的排序方向
    function sortTable(n){
        const table = document.getElementById("reportTable");
        const tbody = table.querySelector("tbody");
        const rows = Array.from(tbody.querySelectorAll("tr"));
        
        // 切換升降冪方向
        sortDir[n] = sortDir[n] === "asc" ? "desc" : "asc";
        const dir = sortDir[n];
        
        // 🌟 核心修正：使用高效能的陣列排序法 (O(N log N))
        rows.sort((rowA, rowB) => {
            let valA = rowA.cells[n].innerText.trim().toLowerCase();
            let valB = rowB.cells[n].innerText.trim().toLowerCase();
            
            // 頁數需要當作數字來排序
            if(n === 2){ 
                valA = parseInt(valA) || 0; 
                valB = parseInt(valB) || 0; 
            }
            
            if(valA < valB) return dir === "asc" ? -1 : 1;
            if(valA > valB) return dir === "asc" ? 1 : -1;
            return 0;
        });
        
        // 🌟 將排序好的資料一次性貼回表格中 (不會觸發災難性的畫面重繪)
        rows.forEach(row => tbody.appendChild(row));
    }
    </script></body></html>"""
    with open('index.html', 'w', encoding='utf-8') as f: f.write(html_content)

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
            rss_content += f"<item><title>{r['Name']}</title><link>{r['Link']}</link><description><![CDATA[📄 頁數：{r['PageCount']}]]></description><pubDate>{r['Date']}</pubDate></item>\n"
        rss_content += "</channel></rss>"
        with open(rss_filename, 'w', encoding='utf-8') as f: f.write(rss_content)
            
    print(f"\n✅ 任務完成！")

if __name__ == "__main__": main()
