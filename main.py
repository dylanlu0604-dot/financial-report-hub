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
from bs4 import BeautifulSoup

load_dotenv()

# ==========================================
# ⚙️ 全域設定
# ==========================================
ENABLE_AI_SUMMARY = True  

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
            return [m['id'] for m in res.json()['data'] if m['id'].endswith(':free')]
    except:
        pass
    return ["google/gemini-2.0-flash-lite-preview-02-05:free", "google/gemma-3-27b-it:free", "meta-llama/llama-3.3-70b-instruct:free"]

def summarize_report_with_openrouter(report_url, model_pool):
    """提取內容並生成摘要 (含多金鑰與多模型輪詢)"""
    extracted_text = ""
    try:
        print(f"   📥 讀取報告中...")
        web_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(report_url, headers=web_headers, timeout=30)
        response.raise_for_status()
        
        content_type = response.headers.get('Content-Type', '').lower()
        if '.pdf' in report_url.lower() or 'application/pdf' in content_type:
            with pdfplumber.open(io.BytesIO(response.content)) as pdf:
                pages_content = [page.extract_text() for page in pdf.pages[:3] if page.extract_text()]
                extracted_text = "\n".join(pages_content)
        else:
            soup = BeautifulSoup(response.content, 'html.parser')
            for script_or_style in soup(["script", "style", "header", "footer", "nav"]):
                script_or_style.decompose()
            extracted_text = soup.get_text(separator=' ', strip=True)

        if len(extracted_text.strip()) < 50:
            return "⚠️ 內容提取不足（無法解析文字）。"
    except Exception as e:
        return f"❌ 內容解析失敗: {str(e)[:30]}"

    if not VALID_KEYS:
        return "❌ 錯誤：未設定金鑰。"

    working_keys = VALID_KEYS.copy()
    # 限制嘗試的模型數量，避免過度觸發 429
    random.shuffle(model_pool)
    target_models = model_pool[:5] 

    for model_id in target_models:
        random.shuffle(working_keys)
        for current_key in working_keys:
            # 🌟 修正點：在每次嘗試前初始化 content 變數
            content = ""
            headers = {
                "Authorization": f"Bearer {current_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "Financial Report Bot"
            }
            payload = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": "你是一個專業的財經分析師。請用繁體中文摘要以下報告內容。"},
                    {"role": "user", "content": f"請提供 150 字內的精確摘要，用繁體中文：\n\n{extracted_text[:500]}"}
                ],
                "temperature": 0.3
            }

            print(f"   🤖 模型: {model_id[:20]}... (金鑰尾碼: ...{current_key[-4:]})", end=" ", flush=True)
            try:
                res = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=40)
                
                if res.status_code == 200:
                    data = res.json()
                    if 'choices' in data and len(data['choices']) > 0:
                        content = data['choices'][0]['message']['content'].strip()
                        if content:
                            print("✅ 成功！")
                            return content
                    print("❓ 回傳格式異常", end=" ")
                elif res.status_code == 429:
                    print(f"⏳ 429 塞車，換下一把金鑰...")
                    break # 換金鑰
                elif res.status_code == 402:
                    print(f"💸 欠費或額度用盡，換下一把...")
                    break
                else:
                    print(f"❌ 錯誤 {res.status_code}", end=" ")
            except Exception as e:
                print(f"💥 異常: {str(e)[:15]}", end=" ")
        time.sleep(1) # 組合切換間隔

    return "❌ 最終失敗：所有組合均嘗試過。"

def main():
    print(f"\n{'='*60}\n🚀 開始執行自動化爬蟲程序...\n{'='*60}\n")
    
    all_reports = []
    for _, module_name, _ in pkgutil.iter_modules(scrapers.__path__):
        if module_name == "utils": continue
        try:
            module = importlib.import_module(f"scrapers.{module_name}")
            if hasattr(module, "scrape"):
                results = module.scrape()
                if results: all_reports.extend(results)
        except Exception as e:
            print(f"❌ 載入 {module_name} 失敗: {e}")

    if not all_reports:
        print("\n❌ 未抓到任何資料"); return

    seen_links = set()
    unique_reports = [r for r in all_reports if not (r["Link"] in seen_links or seen_links.add(r["Link"]))]
    
    for r in unique_reports:
        raw_date = str(r.get('Date', '')).replace('年', '-').replace('月', '-').replace('日', '').replace('/', '-').replace('.', '-').replace(' ', '').strip()
        try:
            if '-' in raw_date:
                r['Date'] = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%Y-%m-%d")
            elif len(raw_date) == 8 and raw_date.isdigit():
                r['Date'] = datetime.strptime(raw_date, "%Y%m%d").strftime("%Y-%m-%d")
        except:
            pass

    print(f"\n📊 總共找到 {len(unique_reports)} 筆不重複報告。")
    
    if ENABLE_AI_SUMMARY:
        print(f"\n{'='*60}\n🤖 啟動動態模型摘要...\n")
        free_model_pool = get_live_free_models()
        
        for i, report in enumerate(unique_reports, 1):
            print(f"[{i}/{len(unique_reports)}] 正在處理: {report['Name']}")
            summary = summarize_report_with_openrouter(report['Link'], free_model_pool)
            report['Summary'] = summary
            
            # 🌟 建議：冷卻時間拉長到 30 秒，避免 IP 被封鎖
            sleep_sec = 30
            print(f"💤 冷卻中，等待 {sleep_sec} 秒...")
            time.sleep(sleep_sec)
    else:
        for report in unique_reports:
            report['Summary'] = "未執行 AI 摘要"
    
    os.makedirs('data', exist_ok=True)
    with open('data/reports.json', 'w', encoding='utf-8') as f:
        json.dump(unique_reports, f, ensure_ascii=False, indent=2)
        
    md_content = "# 📊 最新財經報告總覽\n\n"
    for report in unique_reports:
        md_content += f"### {report['Name']}\n"
        md_content += f"- **來源**: {report['Source']} | **日期**: {report['Date']}\n"
        md_content += f"- **AI 摘要**: {report.get('Summary', '無摘要')}\n"
        md_content += f"- [查看原始報告]({report['Link']})\n\n---\n"
        
    with open('data/reports_for_notebooklm.md', 'w', encoding='utf-8') as f:
        f.write(md_content)
        
    print(f"\n✅ 任務完成！資料已儲存至 data/ 資料夾。")

if __name__ == "__main__":
    main()