from bs4 import BeautifulSoup
import re
import json
from urllib.parse import urljoin, unquote
from datetime import datetime
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth

# ==========================================
# 🛠️ 輔助工具函式區
# ==========================================
def is_within_30_days(date_text):
    if not date_text: return False
    try:
        dt = datetime.strptime(date_text, "%Y-%m-%d")
        return (datetime.now() - dt).days <= 30
    except:
        return True

def extract_info_from_url(url):
    """提取日期，並給予一個預設標題"""
    title, date_text = "", ""
    match = re.search(r'([0-9]{4})([0-9]{2})([0-9]{2})-[A-Za-z]', url)
    if match:
        date_text = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        title = f"CTBC 市場評論_{match.group(1)}{match.group(2)}{match.group(3)}"
    return title, date_text

def clean_title(title):
    # 移除換行符號並清理空白
    return title.replace('\n', ' ').strip()

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 CTBC (中國信託銀行) - 🕵️‍♂️ 封包攔截與精準標題配對模式...")
    reports = []
    captured_api_json = []

    target_url = "https://www.ctbcbank.com/twrbo/zh_tw/wm_index/wm_investreport/market-comment.html"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 🌟 攔截器：監聽所有 XHR/Fetch 請求並存入 list
            def handle_response(response):
                if response.request.resource_type in ["xhr", "fetch"]:
                    try:
                        data = response.json()
                        captured_api_json.append(data)
                    except:
                        pass
                        
            page.on("response", handle_response)
            
            print("  🔑 步驟 1: 前往中信首頁取得合法 Cookie...")
            page.goto("https://www.ctbcbank.com/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000) 
            
            print("  🌐 步驟 2: 進入「市場評論」頁面攔截 API 封包...")
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            
            print("  ⏳ 等待 API 回傳資料 (8秒)...")
            page.wait_for_timeout(8000) 
            
            browser.close()

        # ==========================================
        # 🧠 核心修正：精準 ID 與標題配對邏輯
        # ==========================================
        print(f"  [偵探回報] 成功攔截到 {len(captured_api_json)} 個 JSON 封包，開始精準配對...")
        
        # 💡 雙管齊下除錯法
        import os
        os.makedirs("data", exist_ok=True)
        # 1. 嘗試存進 data 資料夾，跟著 reports.json 一起推回 GitHub
        with open("data/ctbc_debug.json", "w", encoding="utf-8") as f:
            json.dump(captured_api_json, f, ensure_ascii=False, indent=2)
            print("  [提示] 已將原始 JSON 儲存為 data/ctbc_debug.json")
        
        # 2. 🚨 最保險的做法：直接把前 2500 個字元印在 GitHub 的記錄檔 (Log) 裡！
        print(f"\n{'='*40}\n🕵️ [緊急除錯] 中信 API JSON 內容片段：\n{json.dumps(captured_api_json, ensure_ascii=False)[:2500]}\n{'='*40}\n")

        id_to_title_map = {}
        
        def extract_reports_from_json(data):
            if isinstance(data, dict):
                # 放寬標題與 ID 的鍵值搜尋範圍
                title = data.get('title') or data.get('reportTitle') or data.get('name') or data.get('docName')
                r_id = data.get('reportId') or data.get('fileId') or data.get('id') or data.get('docId')
                
                if title and r_id and isinstance(r_id, str):
                    # 放寬正規表達式：只尋找 8 位數字日期開頭
                    match = re.search(r'(\d{8}[-A-Za-z0-9_]*)', r_id) 
                    
                    if match:
                        found_id = match.group(1)
                        if re.search(r'[\u4e00-\u9fa5]', str(title)):
                            id_to_title_map[found_id] = str(title).strip()
                    else:
                        pass # 👈 這裡加上 pass 來避免 IndentationError，或者你可以把下面這行取消註解
                        # print(f"  [Debug] 找到標題 '{title}' 但 ID '{r_id}' 不符合格式。")
                
                for v in data.values():
                    if isinstance(v, (dict, list)):
                        extract_reports_from_json(v)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        extract_reports_from_json(item)

        # 啟動智能解析
        for packet in captured_api_json:
            extract_reports_from_json(packet)
            
        print(f"  🎯 解析完成！共計 {len(id_to_title_map)} 組唯一標題與網址綁定成功。")

        # ==========================================
        # 🔨 組裝最終結果
        # ==========================================
        for r_id, real_title in id_to_title_map.items():
            hidden_url = f"https://www.ctbcbank.com/IB/api/adapters/IB_Adapter/resource/report/{r_id}"
            
            # 從網址提取日期進行過濾
            _, date_text = extract_info_from_url(hidden_url)
            
            if not date_text or not is_within_30_days(date_text):
                continue
                
            reports.append({
                "Source": "CTBC",
                "Date": date_text,
                "Name": clean_title(real_title),
                "Link": hidden_url
            })

    except Exception as e:
        print(f"  ❌ CTBC 爬取失敗: {e}")

    print(f"  ✅ CTBC 最終收錄 {len(reports)} 筆不重複報告")
    return reports
