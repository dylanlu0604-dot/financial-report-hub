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
    """提取日期，並給予一個預設標題（當找不到真實標題時的保底）"""
    title, date_text = "", ""
    match = re.search(r'([0-9]{4})([0-9]{2})([0-9]{2})-[A-Za-z]', url)
    if match:
        date_text = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        title = f"CTBC 市場評論_{match.group(1)}{match.group(2)}{match.group(3)}"
    return title, date_text

def clean_title(title):
    return title.replace('\n', ' ').strip()

# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 CTBC (中國信託銀行 - 市場評論) - 🕵️‍♂️ 封包攔截與標題解析模式...")
    reports = []
    seen_urls = set()
    
    base_url = "https://www.ctbcbank.com"
    target_url = "https://www.ctbcbank.com/twrbo/zh_tw/wm_index/wm_investreport/market-comment.html"
    
    captured_api_json = []

    try:
        with sync_playwright() as p:
            # 💡 提醒：如果在 GitHub Actions 上跑會報錯，記得把 headless 暫時改成 True
            browser = p.chromium.launch(
                headless=True, # 可以看著它跑，穩定後改 True
                args=["--disable-blink-features=AutomationControlled", "--disable-infobars"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080},
                bypass_csp=True
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # 🌟 攔截器：這次我們直接將攔截到的資料轉換為 JSON 格式儲存
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
            page.wait_for_timeout(3000) 
            
            print("  🌐 步驟 2: 轉往「市場評論」頁面載入資料，並攔截 API 封包...")
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            
            print("  ⏳ 等待資料 API 回傳 (8秒)...")
            page.wait_for_timeout(8000) 
            
            # 滾動畫面觸發可能存在的動態載入
            try:
                page.evaluate("window.scrollTo(0, 500)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
            except:
                pass
            
            browser.close()

        # ==========================================
        # 🧠 JSON 智能解析器：在封包中尋找 ID 與對應的真實標題
        # ==========================================
        print(f"  [偵探回報] 成功攔截到 {len(captured_api_json)} 個 JSON 封包，開始配對標題...")
        
        # 👇 新增的除錯區塊：印出含有關鍵字的真實 JSON 片段
        print("\n=== 🕵️ 偷看原始 JSON 中疑似包含標題的區塊 ===")
        found_clue = False
        for packet in captured_api_json:
            packet_str = json.dumps(packet, ensure_ascii=False)
            if "市場評論" in packet_str or "投資" in packet_str:
                print(packet_str[:2000]) # 印出前 2000 字
                print("-" * 40)
                found_clue = True
        if not found_clue:
            print("❌ 沒有在任何 JSON 中找到 '市場評論' 或 '投資' 等字眼，可能是目標網址真的換了。")
        print("==========================================\n")
        
        id_to_title_map = {}
        
        # 遞迴函數：自動在複雜的 JSON 樹狀結構中挖出我們想要的資訊
        def extract_reports_from_json(data):
            if isinstance(data, dict):
                report_id = None
                # 1. 先找找看有沒有長得像 ID 的值
                for k, v in data.items():
                    if isinstance(v, str):
                        match = re.search(r'([0-9]{8}-[A-Za-z]-[0-9]{1,3}-[0-9]{1,2})', v)
                        if match:
                            report_id = match.group(1)
                            break
                
                if report_id:
                    # 2. 如果找到了 ID，就在「同一個區塊」裡面找中文標題！
                    title = ""
                    for k, v in data.items():
                        # 如果這個值是字串，且包含中文字（這通常就是我們要的標題）
                        if isinstance(v, str) and re.search(r'[\u4e00-\u9fa5]', v) and len(v) > 4:
                            # 避開一些不可能是標題的雜訊
                            if not re.search(r'<[a-z]+', v): 
                                title = v
                                break
                    if title:
                        id_to_title_map[report_id] = title.strip()
                
                # 繼續往下層挖
                for v in data.values():
                    extract_reports_from_json(v)
            elif isinstance(data, list):
                for item in data:
                    extract_reports_from_json(item)

        # 啟動智能解析
        for packet in captured_api_json:
            extract_reports_from_json(packet)
            
        print(f"  🎯 完美解析出 {len(id_to_title_map)} 組真實報告標題！")

        # ==========================================
        # 🔨 組裝並過濾最終報告名單
        # ==========================================
        for r_id, real_title in id_to_title_map.items():
            # 🌟 關鍵修正：在網址結尾掛上 #.pdf，讓 main.py 辨識為實體檔案，且不影響原始 API 請求
            hidden_url = f"https://www.ctbcbank.com/IB/api/adapters/IB_Adapter/resource/report/{r_id}#.pdf"
            
            # 從 ID 或是剛剛寫好的工具萃取日期
            _, date_text = extract_info_from_url(hidden_url)
            
            if not date_text or not is_within_30_days(date_text):
                continue
                
            reports.append({
                "Source": "CTBC",
                "Date": date_text,
                "Name": clean_title(real_title),  
                "Link": hidden_url,
                "Type": "PDF" # 明確標示為實體 PDF
            })

    except Exception as e:
        print(f"  ❌ CTBC 爬取失敗: {e}")
        import traceback
        traceback.print_exc()

    print(f"  ✅ CTBC 最終成功收錄 {len(reports)} 筆報告")
    return reports

if __name__ == "__main__":
    scrape()
