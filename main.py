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
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# ⚙️ 全域設定
# ==========================================
# 🌟 測試期間先關閉 AI，省時省 API 額度
ENABLE_AI_SUMMARY = False  

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
    """實時獲取 OpenRouter 免費模型清單"""
    if not VALID_KEYS:
        return ["google/gemini-2.0-flash-lite-preview-02-05:free", "google/gemma-3-27b-it:free", "meta-llama/llama-3.3-70b-instruct:free"]

    current_key = random.choice(VALID_KEYS)
    headers = {"Authorization": f"Bearer {current_key}"}
    try:
        res = requests.get(f"{BASE_URL}/models", headers=headers, timeout=10)
        if res.status_code == 200:
            models = res.json().get('data', [])
            free_models = [m['id'] for m in models if m.get('pricing', {}).get('prompt') == "0" and m.get('pricing', {}).get('completion') == "0"]
            return free_models if free_models else ["google/gemini-2.0-flash-lite-preview-02-05:free"]
    except:
        pass
    return ["google/gemini-2.0-flash-lite-preview-02-05:free"]

def summarize_report_with_openrouter(url, free_model_pool):
    """呼叫 OpenRouter AI 進行摘要"""
    if not VALID_KEYS:
        return "⚠️ 未設定 API Key，跳過摘要。"
        
    prompt = f"請繁體中文總結這份財經報告的核心觀點（3-5個重點），報告連結：{url}"
    
    for attempt in range(3):
        model = random.choice(free_model_pool)
        api_key = random.choice(VALID_KEYS)
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500
        }
        
        try:
            response = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=data, timeout=30)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'].strip()
        except:
            time.sleep(2)
            
    return "⚠️ AI 摘要生成失敗。"

# ==========================================
# 🚀 主程式執行區塊
# ==========================================
def main():
    print(f"\n{'='*60}\n🚀 開始執行自動化爬蟲程序...\n{'='*60}\n")
    
    all_reports = []
    
    # 🌟 在這裡設定您想單獨測試的爬蟲模組名稱
    target_scrapers = ["cathay","jri"] 
    
    for _, module_name, _ in pkgutil.iter_modules(scrapers.__path__):
        if module_name == "utils": continue
        
        # 🌟 過濾測試名單
        if module_name not in target_scrapers: 
            continue 

        try:
            module = importlib.import_module(f"scrapers.{module_name}")
            if hasattr(module, "scrape"):
                reports = module.scrape()
                if reports:
                    all_reports.extend(reports)
        except Exception as e:
            print(f"  ❌ 載入 {module_name} 失敗: {e}")

    # ==========================================
    # 🧹 資料清理：過濾重複與舊資料
    # ==========================================
    unique_reports = []
    seen_links = set()
    
    for report in all_reports:
        if report['Link'] in seen_links: continue
        
        try:
            raw_date = report.get('Date', '')
            if not raw_date or raw_date == "未知日期":
                unique_reports.append(report)
                seen_links.add(report['Link'])
                continue
                
            dt = datetime.strptime(raw_date, "%Y-%m-%d")
            if (datetime.now() - dt).days <= 30:
                unique_reports.append(report)
                seen_links.add(report['Link'])
        except:
            unique_reports.append(report)
            seen_links.add(report['Link'])

    print(f"\n📊 總共找到 {len(unique_reports)} 筆不重複報告。")
    
    # ==========================================
    # 📄 擷取 PDF 頁數 (含反阻擋機制)
    # ==========================================
    print(f"\n{'='*60}\n📄 開始擷取 PDF 頁數...\n")
    request_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.google.com/'
    }

    for i, report in enumerate(unique_reports, 1):
        link = report.get('Link', '')
        page_count = "未知"
        
        if '.pdf' in link.lower() or 'ctbcbank' in link.lower():
            try:
                print(f"[{i}/{len(unique_reports)}] 正在讀取頁數: {report['Name'][:20]}...")
                res = requests.get(link, headers=request_headers, allow_redirects=True, timeout=20)
                if res.status_code == 200:
                    with pdfplumber.open(io.BytesIO(res.content)) as pdf:
                        page_count = len(pdf.pages)
                else:
                    print(f"  ⚠️ HTTP 失敗: 狀態碼 {res.status_code}")
            except Exception as e:
                print(f"  ⚠️ 無法讀取頁數: {e}")
                
        report['PageCount'] = page_count

    # ==========================================
    # 🤖 執行 AI 摘要
    # ==========================================
    if ENABLE_AI_SUMMARY:
        print(f"\n{'='*60}\n🤖 啟動動態模型摘要...\n")
        free_model_pool = get_live_free_models()
        for i, report in enumerate(unique_reports, 1):
            print(f"[{i}/{len(unique_reports)}] 正在處理摘要: {report['Name']}")
            report['Summary'] = summarize_report_with_openrouter(report['Link'], free_model_pool)
            sleep_sec = 30
            print(f"💤 冷卻中，等待 {sleep_sec} 秒...")
            time.sleep(sleep_sec)
    else:
        for report in unique_reports:
            report['Summary'] = "未執行 AI 摘要"
    
    # 建立 data 資料夾
    os.makedirs('data', exist_ok=True)
    
    # 寫入 JSON
    with open('data/reports.json', 'w', encoding='utf-8') as f:
        json.dump(unique_reports, f, ensure_ascii=False, indent=2)

    # ==========================================
    # 📝 輸出 1：Markdown 生成
    # ==========================================
    md_content = "# 📊 最新財經報告總覽\n\n"
    for report in unique_reports:
        page_str = report.get('PageCount', '未知')
        summary = report.get('Summary', '')
        
        md_content += f"### {report['Name']}\n"
        md_content += f"來源: {report['Source']} | 日期: {report['Date']} | 頁數: {page_str} 頁\n"
        
        # 🌟 Markdown 中如果不顯示「未執行 AI 摘要」，版面會更乾淨
        if summary and summary != "未執行 AI 摘要":
            md_content += f"**AI 摘要:** {summary}\n"
            
        md_content += f"[查看原始報告]({report['Link']})\n\n"
        
    with open('data/reports_for_notebooklm.md', 'w', encoding='utf-8') as f:
        f.write(md_content)

# ==========================================
    # 🌐 輸出 2：HTML 生成 (支援動態排序的表格)
    # ==========================================
    # 預設先在 Python 端依照「日期」由大到小排序一次
    unique_reports.sort(key=lambda x: x.get('Date', ''), reverse=True)

    html_content = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>最新財經報告總覽</title>
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
    <h1>📊 最新財經報告總覽</h1>
    <table id="reportTable">
        <thead>
            <tr>
                <th onclick="sortTable(0)" style="width: 12%;" title="點擊排序">機構名稱 ↕</th>
                <th onclick="sortTable(1)" style="width: 12%;" title="點擊排序">日期 ↕</th>
                <th onclick="sortTable(2)" style="width: 8%;" title="點擊排序">頁數 ↕</th>
                <th style="width: 30%;">報告名稱</th>
                <th style="width: 38%;">AI 摘要</th>
            </tr>
        </thead>
        <tbody>
"""
    for report in unique_reports:
        page_str = report.get('PageCount', '未知')
        summary = report.get('Summary', '')
        if summary == "未執行 AI 摘要": summary = ""
        
        # 為了讓 JS 好排序，我們在頁數欄位只放數字或未知
        html_content += "            <tr>\n"
        html_content += f"                <td><b>{report.get('Source', '')}</b></td>\n"
        html_content += f"                <td>{report.get('Date', '')}</td>\n"
        html_content += f"                <td><span class=\"page-badge\">{page_str}</span></td>\n"
        html_content += f"                <td><a href=\"{report.get('Link', '')}\" target=\"_blank\">{report.get('Name', '')}</a></td>\n"
        html_content += f"                <td class=\"summary-text\">{summary.replace(chr(10), '<br>')}</td>\n"
        html_content += "            </tr>\n"

    html_content += """        </tbody>
    </table>

    <script>
        function sortTable(n) {
            var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
            table = document.getElementById("reportTable");
            switching = true;
            // 預設點擊時「由大到小 (降序)」排列
            dir = "desc"; 
            
            while (switching) {
                switching = false;
                rows = table.rows;
                
                for (i = 1; i < (rows.length - 1); i++) {
                    shouldSwitch = false;
                    x = rows[i].getElementsByTagName("TD")[n];
                    y = rows[i + 1].getElementsByTagName("TD")[n];
                    
                    // 取得欄位內的純文字
                    var valX = x.innerText.toLowerCase();
                    var valY = y.innerText.toLowerCase();
                    
                    // 如果是第3欄 (頁數，索引為2)，需要轉換成數字來比大小
                    if (n === 2) { 
                        var numX = isNaN(parseInt(valX)) ? -1 : parseInt(valX);
                        var numY = isNaN(parseInt(valY)) ? -1 : parseInt(valY);
                        if (dir === "desc") {
                            if (numX < numY) { shouldSwitch = true; break; }
                        } else {
                            if (numX > numY) { shouldSwitch = true; break; }
                        }
                    } else {
                        // 文字排序 (適用於機構名稱、日期)
                        if (dir === "desc") {
                            if (valX < valY) { shouldSwitch = true; break; }
                        } else {
                            if (valX > valY) { shouldSwitch = true; break; }
                        }
                    }
                }
                if (shouldSwitch) {
                    // 交換位置
                    rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
                    switching = true;
                    switchcount++;
                } else {
                    // 如果沒有任何交換發生，且本來是降序，就反轉成升序再跑一次
                    if (switchcount === 0 && dir === "desc") {
                        dir = "asc";
                        switching = true;
                    }
                }
            }
        }
    </script>
</body>
</html>"""
    
    # 寫入根目錄供 GitHub Pages 讀取
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)

    # ==========================================
    # 📡 輸出 3：個別機構 RSS (XML) 生成
    # ==========================================
    print(f"\n{'='*60}\n📡 開始生成個別機構的 RSS 訂閱源...\n")
    
    reports_by_source = {}
    for report in unique_reports:
        source = report.get('Source', 'Unknown')
        if source not in reports_by_source:
            reports_by_source[source] = []
        reports_by_source[source].append(report)
        
    for source, reports in reports_by_source.items():
        safe_source_name = source.lower().replace(" ", "_")
        rss_filename = f"data/rss_{safe_source_name}.xml"
        
        rss_content = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
  <title>{source} 財經研究報告</title>
  <link>https://github.com/</link>
  <description>{source} 最新經濟與金融分析報告自動訂閱源</description>
"""
        for r in reports:
            pub_date_str = r.get('Date', '')
            try:
                dt = datetime.strptime(pub_date_str, "%Y-%m-%d")
                pub_date = dt.strftime("%a, %d %b %Y 00:00:00 +0000")
            except:
                pub_date = pub_date_str

            title = str(r.get('Name', '')).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            link = str(r.get('Link', '')).replace("&", "&amp;")
            
            summary = r.get('Summary', '')
            page_count = r.get('PageCount', '未知')
            
            # 🌟 XML 徹底隱藏「未執行 AI 摘要」
            if summary == "未執行 AI 摘要" or not summary:
                description_html = f"📄 <b>報告頁數：</b>{page_count} 頁"
            else:
                description_html = f"📄 <b>報告頁數：</b>{page_count} 頁<br><br><b>🤖 AI 摘要：</b><br>{summary}"
            
            rss_content += f"""  <item>
    <title>{title}</title>
    <link>{link}</link>
    <description><![CDATA[{description_html}]]></description>
    <pubDate>{pub_date}</pubDate>
  </item>
"""
        rss_content += """</channel>\n</rss>"""
        
        with open(rss_filename, 'w', encoding='utf-8') as f:
            f.write(rss_content)
        
        print(f"  ✔️ 已生成 {rss_filename} (共 {len(reports)} 筆)")

    print(f"\n✅ 任務完成！所有資料（含 MD, HTML, RSS）已更新完畢。")

if __name__ == "__main__":
    main()
