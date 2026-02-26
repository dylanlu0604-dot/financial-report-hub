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

load_dotenv()

# ==========================================
# ⚙️ 全域設定 (已為您的 GitHub 專案客製化)
# ==========================================
ENABLE_AI_SUMMARY = False  

# 🌟 您的專屬 GitHub 資訊
GITHUB_USER = "dylanlu0604-dot"
GITHUB_REPO = "financial-report-hub"

# 組合出 GitHub Raw 的基礎網址 (all report pdf 中間的空白在網址中是 %20)
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/all%20report%20pdf"

API_KEYS = [
    os.getenv("OPENROUTER_API_KEY"),
    os.getenv("OPENROUTER_API_KEY2"),
    os.getenv("OPENROUTER_API_KEY3"),
    os.getenv("OPENROUTER_API_KEY4"),
    os.getenv("OPENROUTER_API_KEY5"),
    os.getenv("OPENROUTER_API_KEY6")
]
VALID_KEYS = [k for k in API_KEYS if k]
BASE_URL = "https://openrouter.ai/api/v1"

def get_live_free_models():
    if not VALID_KEYS: return ["google/gemini-2.0-flash-lite-preview-02-05:free"]
    current_key = random.choice(VALID_KEYS)
    headers = {"Authorization": f"Bearer {current_key}"}
    try:
        res = requests.get(f"{BASE_URL}/models", headers=headers, timeout=10)
        if res.status_code == 200:
            return [m['id'] for m in res.json()['data'] if m['id'].endswith(':free')]
    except: pass
    return ["google/gemini-2.0-flash-lite-preview-02-05:free"]

def summarize_report_with_openrouter(report_url, model_pool):
    # 若啟用 AI，可直接讀取本地下載的 PDF，目前預設為 False
    return "未執行 AI 摘要"

# ==========================================
# 🚀 主程式執行區塊
# ==========================================
def main():
    print(f"\n{'='*60}\n🚀 開始執行自動化爬蟲程序...\n{'='*60}\n")
    
    all_reports = []
    target_scrapers = ["cathay", "ctbc", "ing"] 
    
    for _, module_name, _ in pkgutil.iter_modules(scrapers.__path__):
        if module_name == "utils" or module_name not in target_scrapers: continue
        try:
            module = importlib.import_module(f"scrapers.{module_name}")
            if hasattr(module, "scrape"):
                results = module.scrape()
                if results: all_reports.extend(results)
        except Exception as e:
            print(f"❌ 載入 {module_name} 失敗: {e}")

    if not all_reports:
        print("\n❌ 未抓到任何資料"); return

    # ==========================================
    # 🧹 資料清理：標準化日期、過濾重複與舊資料
    # ==========================================
    unique_reports = []
    seen_links = set()
    
    for report in all_reports:
        if report['Link'] in seen_links: continue
        raw_date = str(report.get('Date', '')).replace('年', '-').replace('月', '-').replace('日', '').replace('/', '-').replace('.', '-').replace(' ', '').strip().rstrip('-')
        dt_obj = None
        try:
            if '-' in raw_date:
                parts = raw_date.split('-')
                if len(parts) >= 3: raw_date = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                dt_obj = datetime.strptime(raw_date, "%Y-%m-%d")
                report['Date'] = dt_obj.strftime("%Y-%m-%d")
            elif len(raw_date) == 8 and raw_date.isdigit():
                dt_obj = datetime.strptime(raw_date, "%Y%m%d")
                report['Date'] = dt_obj.strftime("%Y-%m-%d")
        except: pass
            
        if report.get('Date') == "未知日期" or not report.get('Date') or (dt_obj and (datetime.now() - dt_obj).days <= 30):
            unique_reports.append(report)
            seen_links.add(report['Link'])

    print(f"\n📊 總共找到 {len(unique_reports)} 筆不重複報告。")
    
    # ==========================================
    # 📥 全新核心機制：將 PDF 下載到本地，並從本地讀取頁數
    # ==========================================
    print(f"\n{'='*60}\n📥 開始下載 PDF 並讀取本地頁數...\n")
    
    pdf_folder = "all report pdf"
    os.makedirs(pdf_folder, exist_ok=True)
    
    request_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://www.google.com/'
    }

    for i, report in enumerate(unique_reports, 1):
        original_link = report.get('Link', '')
        page_count = "未知"
        
        # 1. 產生安全的檔名 (過濾掉不能當作檔名的特殊字元)
        safe_title = re.sub(r'[\\/*?:"<>|]', "_", report['Name']).strip()
        local_filename = f"{safe_title}.pdf"
        local_filepath = os.path.join(pdf_folder, local_filename)
        
        # 將檔名進行 URL 編碼 (解決空白字元問題)
        encoded_filename = urllib.parse.quote(local_filename)
        
        # 先保存原始網址備用
        report['OriginalLink'] = original_link
        
        # 🌟 直接將報告網址替換成您的 GitHub 專屬網址
        report['Link'] = f"{GITHUB_RAW_BASE}/{encoded_filename}"
        
        # HTML 專用的相對路徑 (例如: all report pdf/報告.pdf)
        report['LocalPath'] = f"{pdf_folder}/{encoded_filename}"
        
        if '.pdf' in original_link.lower() or 'ctbcbank' in original_link.lower():
            try:
                print(f"[{i}/{len(unique_reports)}] 📥 處理檔案: {report['Name'][:20]}...")
                
                # 如果檔案還不存在，才發送網路請求去抓
                if not os.path.exists(local_filepath):
                    max_retries = 3
                    for attempt in range(max_retries):
                        res = requests.get(original_link, headers=request_headers, allow_redirects=True, timeout=20)
                        if res.status_code == 200:
                            with open(local_filepath, 'wb') as f:
                                f.write(res.content)
                            break 
                        elif res.status_code == 202:
                            print(f"  ⏳ 伺服器處理中，等待 3 秒... ({attempt+1}/{max_retries})")
                            time.sleep(3)
                        else:
                            print(f"  ⚠️ HTTP 失敗: 狀態碼 {res.status_code}")
                            break 
                
                # 2. 檔案已經在本地了！直接飛速讀取本地檔案的頁數
                if os.path.exists(local_filepath):
                    with pdfplumber.open(local_filepath) as pdf:
                        page_count = len(pdf.pages)
                        
            except Exception as e:
                print(f"  ⚠️ 下載或讀取失敗: {str(e)[:50]}")
                
        report['PageCount'] = page_count

    # ==========================================
    # 🤖 執行 AI 摘要
    # ==========================================
    if ENABLE_AI_SUMMARY:
        print(f"\n{'='*60}\n🤖 啟動動態模型摘要...\n")
        # 您原本的 AI 邏輯...
    else:
        for report in unique_reports: report['Summary'] = "未執行 AI 摘要"
    
    # 建立 data 資料夾寫入 JSON
    os.makedirs('data', exist_ok=True)
    unique_reports.sort(key=lambda x: x.get('Date', ''), reverse=True) # 預設依日期排序
    with open('data/reports.json', 'w', encoding='utf-8') as f:
        json.dump(unique_reports, f, ensure_ascii=False, indent=2)

    # ==========================================
    # 📝 輸出 1：Markdown 生成 (使用 GitHub 連結)
    # ==========================================
    md_content = "# 📊 最新財經報告總覽\n\n"
    for report in unique_reports:
        page_str = report.get('PageCount', '未知')
        summary = report.get('Summary', '')
        md_content += f"### {report['Name']}\n"
        md_content += f"來源: {report['Source']} | 日期: {report['Date']} | 頁數: {page_str} 頁\n"
        if summary and summary != "未執行 AI 摘要": md_content += f"**AI 摘要:** {summary}\n"
        # 這裡的 report['Link'] 已經是 GitHub 網址了！
        md_content += f"[📥 下載或查看報告]({report['Link']})\n\n"
        
    with open('data/reports_for_notebooklm.md', 'w', encoding='utf-8') as f:
        f.write(md_content)

    # ==========================================
    # 🌐 輸出 2：HTML 生成 (動態表格 + 本地相對路徑)
    # ==========================================
    html_content = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>最新財經報告總覽</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f5f7fa; }
        h1 { color: #2c3e50; text-align: center; margin-bottom: 30px; }
        table { width: 100%; border-collapse: collapse; background: white; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-radius: 8px; overflow: hidden; }
        th, td { padding: 15px; text-align: left; border-bottom: 1px solid #ecf0f1; vertical-align: top; }
        th { background-color: #2c3e50; color: white; cursor: pointer; user-select: none; transition: background 0.2s; }
        th:hover { background-color: #34495e; }
        tr:hover { background-color: #f8f9fa; }
        a { color: #2980b9; text-decoration: none; font-weight: bold; }
        a:hover { text-decoration: underline; }
        .summary-text { font-size: 0.9em; color: #555; line-height: 1.6; }
        .page-badge { display: inline-block; background: #e8f4fd; color: #2980b9; padding: 2px 8px; border-radius: 12px; font-weight: bold; font-size: 0.85em; }
    </style>
</head>
<body>
    <h1>📊 最新財經報告總覽 (檔案皆存於 GitHub)</h1>
    <table id="reportTable">
        <thead>
            <tr>
                <th onclick="sortTable(0)" style="width: 12%;">機構名稱 ↕</th><th onclick="sortTable(1)" style="width: 12%;">日期 ↕</th>
                <th onclick="sortTable(2)" style="width: 8%;">頁數 ↕</th><th style="width: 30%;">報告名稱</th><th style="width: 38%;">AI 摘要</th>
            </tr>
        </thead>
        <tbody>\n"""
    
    for report in unique_reports:
        summary = report.get('Summary', '')
        if summary == "未執行 AI 摘要": summary = ""
        html_content += f"            <tr>\n                <td><b>{report.get('Source', '')}</b></td>\n                <td>{report.get('Date', '')}</td>\n"
        html_content += f"                <td><span class=\"page-badge\">{report.get('PageCount', '未知')}</span></td>\n"
        # 🌟 HTML 使用相對路徑，點擊時會直接打開 GitHub 儲存庫裡的 PDF
        html_content += f"                <td><a href=\"{report.get('LocalPath', '')}\" target=\"_blank\">{report.get('Name', '')}</a></td>\n"
        html_content += f"                <td class=\"summary-text\">{summary.replace(chr(10), '<br>')}</td>\n            </tr>\n"

    html_content += """        </tbody></table>
    <script>
        function sortTable(n) {
            var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
            table = document.getElementById("reportTable"); switching = true; dir = "desc"; 
            while (switching) {
                switching = false; rows = table.rows;
                for (i = 1; i < (rows.length - 1); i++) {
                    shouldSwitch = false; x = rows[i].getElementsByTagName("TD")[n]; y = rows[i + 1].getElementsByTagName("TD")[n];
                    var valX = x.innerText.toLowerCase(); var valY = y.innerText.toLowerCase();
                    if (n === 2) { 
                        var numX = isNaN(parseInt(valX)) ? -1 : parseInt(valX); var numY = isNaN(parseInt(valY)) ? -1 : parseInt(valY);
                        if (dir === "desc") { if (numX < numY) { shouldSwitch = true; break; } } else { if (numX > numY) { shouldSwitch = true; break; } }
                    } else {
                        if (dir === "desc") { if (valX < valY) { shouldSwitch = true; break; } } else { if (valX > valY) { shouldSwitch = true; break; } }
                    }
                }
                if (shouldSwitch) { rows[i].parentNode.insertBefore(rows[i + 1], rows[i]); switching = true; switchcount++;
                } else { if (switchcount === 0 && dir === "desc") { dir = "asc"; switching = true; } }
            }
        }
    </script></body></html>"""
    with open('index.html', 'w', encoding='utf-8') as f: f.write(html_content)

    # ==========================================
    # 📡 輸出 3：個別機構 RSS (XML 生成)
    # ==========================================
    print(f"\n{'='*60}\n📡 開始生成個別機構的 RSS 訂閱源...\n")
    reports_by_source = {}
    for report in unique_reports:
        source = report.get('Source', 'Unknown')
        if source not in reports_by_source: reports_by_source[source] = []
        reports_by_source[source].append(report)
        
    for source, reports in reports_by_source.items():
        safe_source_name = source.lower().replace(" ", "_")
        rss_filename = f"data/rss_{safe_source_name}.xml"
        rss_content = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"><channel><title>{source} 財經研究報告</title><link>https://github.com/{GITHUB_USER}/{GITHUB_REPO}</link><description>{source} 最新分析報告自動訂閱源</description>\n"""
        
        for r in reports:
            pub_date_str = r.get('Date', '')
            try: pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d").strftime("%a, %d %b %Y 00:00:00 +0000")
            except: pub_date = pub_date_str

            title = str(r.get('Name', '')).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            link = str(r.get('Link', '')).replace("&", "&amp;") # 這裡已經是 GitHub Raw 連結了
            summary = r.get('Summary', '')
            page_count = r.get('PageCount', '未知')
            
            if summary == "未執行 AI 摘要" or not summary: description_html = f"📄 <b>報告頁數：</b>{page_count} 頁"
            else: description_html = f"📄 <b>報告頁數：</b>{page_count} 頁<br><br><b>🤖 AI 摘要：</b><br>{summary}"
            
            rss_content += f"  <item><title>{title}</title><link>{link}</link><description><![CDATA[{description_html}]]></description><pubDate>{pub_date}</pubDate></item>\n"
            
        rss_content += "</channel>\n</rss>"
        with open(rss_filename, 'w', encoding='utf-8') as f: f.write(rss_content)
        print(f"  ✔️ 已生成 {rss_filename}")

    print(f"\n✅ 任務完成！所有 PDF 已下載，且所有連結已成功替換為 GitHub 來源。")

if __name__ == "__main__":
    main()
