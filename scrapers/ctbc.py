from bs4 import BeautifulSoup
import re
import json
import os
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
    print("🔍 正在爬取 CTBC (中國信託銀行) - 🕵️‍♂️ 雙網址封包攔截與結構分析模式...")
    reports = []
    
    # 儲存攔截到的 API 資訊，改為包含 URL 與 Response Data
    api_responses = []

    # 包含新舊兩個網址，確保不漏接
    target_urls = [
        "https://www.ctbcbank.com/twrbo/zh_tw/wm_index/wm_investreport/market-comment.html",
        "https://www.ctbcbank.com/twrbc/twrbc-general/ot010/020"
    ]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 🌟 升級版攔截器：過濾掉圖片/CSS/追蹤碼，只抓取真正的 API 請求
            def handle_response(response):
                if response.request.resource_type in ["xhr", "fetch"]:
                    url = response.url
                    # 排除常見的行銷追蹤與無用 API
                    if "analytics" not in url and "google-analytics" not in url:
                        try:
                            data = response.json()
                            api_responses.append({
                                "url": url,
                                "data": data
                            })
                        except:
                            pass
                            
            page.on("response", handle_response)
            
            print("  🔑 步驟 1: 前往中信首頁取得合法 Cookie...")
            page.goto("https://www.ctbcbank.com/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000) 
            
            print("  🌐 步驟 2: 依序巡邏目標網頁並攔截 API 封包...")
            for url in target_urls:
                print(f"    -> 正在前往: {url[:60]}...")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                print("    ⏳ 等待 API 回傳資料 (8秒)...")
                page.wait_for_timeout(8000) 
            
            browser.close()

        # ==========================================
        # 🧠 核心修正：API 網址與資料結構分析
        # ==========================================
        print(f"  [偵探回報] 巡邏完畢，共攔截到 {len(api_responses)} 個有效 API 回應！")
        
        # 1. 將完整的 API 回應存入 data 資料夾
        os.makedirs("data", exist_ok=True)
        with open("data/ctbc_debug.json", "w", encoding="utf-8") as f:
            json.dump(api_responses, f, ensure_ascii=False, indent=2)
            
        # 2. 印出所有命中的 API 網址，這才是我們尋找資料來源的關鍵
        print(f"\n{'='*60}\n🕵️ [結構分析] 以下是攔截到的 API 請求網址清單：")
        for i, res in enumerate(api_responses):
            print(f"  [{i+1}] {res['url']}")
        print(f"{'='*60}\n")

        id_to_title_map = {}
        
        # 泛用型資料提取：持續尋找看似標題與 ID 的組合
        def extract_reports_from_json(data):
            if isinstance(data, dict):
                # 廣泛搜尋所有可能代表標題的鍵值
                title = data.get('title') or data.get('reportTitle') or data.get('name') or data.get('docName') or data.get('fileName')
                # 廣泛搜尋所有可能代表檔案 ID 的鍵值
                r_id = data.get('reportId') or data.get('fileId') or data.get('id') or data.get('docId') or data.get('uuid')
                
                if title and r_id and isinstance(r_id, str):
                    # 只要 ID 夠長 (大於 5)，且標題含有中文，我們就先視為潛在目標收錄
                    if len(r_id) > 5 and re.search(r'[\u4e00-\u9fa5]', str(title)):
                        id_to_title_map[r_id] = str(title).strip()
                
                for v in data.values():
                    if isinstance(v, (dict, list)):
                        extract_reports_from_json(v)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        extract_reports_from_json(item)

        # 啟動泛用解析
        for res in api_responses:
            extract_reports_from_json(res['data'])
            
        print(f"  🎯 解析完成！共計 {len(id_to_title_map)} 組潛在標題與 ID。")

        # ==========================================
        # 🔨 組裝最終結果
        # ==========================================
        for r_id, real_title in id_to_title_map.items():
            # 這裡的下載網址格式若有變，需根據新的 API 分析結果調整
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
