import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def scrape():
    # 🌟 請認明這行：兩層式點擊深入版
    print("🔍 正在爬取 Merrill Lynch (美林) - 🎯 兩層式深入點擊尋找 PDF 模式...")
    reports = []
    seen_links = set()
    base_url = "https://www.ml.com"
    target_url = "https://www.ml.com/capital-market-outlook.html"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            # ==========================================
            # 第一層：進入主頁，收集「文章網址」
            # ==========================================
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            except Exception: pass 
                
            print("  👉 正在等待主頁渲染文章清單...")
            try:
                # 等待 Angular 變數 {{title}} 消失，代表資料載入完成
                page.wait_for_function("() => !document.body.innerText.includes('{{title}}') && document.querySelectorAll('a').length > 20", timeout=20000)
                page.wait_for_timeout(3000)
            except Exception: pass
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            
            # 找出所有包含 capital-market-outlook 或 insights 的文章連結
            article_links = soup.find_all('a', href=re.compile(r'capital-market-outlook|insights|article', re.IGNORECASE))
            valid_articles = []
            
            for a in article_links:
                href = a.get('href', '')
                full_url = urljoin(base_url, href)
                
                # 排除完全等於首頁的網址
                clean_href = href.split('?')[0].rstrip('/')
                if clean_href in ['/capital-market-outlook.html', '/capital-market-outlook', '/']:
                    continue
                
                # 抓取標題與日期
                parent_container = a
