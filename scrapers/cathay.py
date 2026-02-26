# ==========================================
# 🕷️ 主爬蟲程式
# ==========================================
def scrape():
    print("🔍 正在爬取 Cathay (國泰世華) - 🎯 精準鎖定『投資研究週報』...")
    reports = []
    seen_pdfs = set()
    
    base_url = "https://www.cathaybk.com.tw"
    target_url = "https://www.cathaybk.com.tw/cathaybk/personal/wealth/market/report/#tab1"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, 
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000) 
            
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 🌟 核心修正：先在整個頁面中尋找共用的備註日期
            global_date_str = "未知日期"
            remark_div = soup.find('div', class_='cubinvest-l-remark__item', string=re.compile("資料日期"))
            if remark_div:
                global_date_str = extract_date_from_text(remark_div.get_text(strip=True))

            for a in soup.find_all('a', href=True):
                href = a['href']
                
                if '.pdf' in href.lower():
                    # 處理標題
                    title = a.get_text(strip=True)
                    if not title:
                        title = a.get('title', '')
                    if not title:
                        title = unquote(href.split('/')[-1].replace('.pdf', '').replace('.PDF', ''))
                        
                    if "投資研究週報" not in title and "投資研究週報" not in unquote(href):
                        continue
                        
                    full_url = urljoin(base_url, href)
                    if full_url in seen_pdfs:
                        continue
                        
                    # 依序套用日期尋找策略
                    date_str = extract_date_from_text(title)
                    
                    if date_str == "未知日期" and a.parent:
                        date_str = extract_date_from_text(a.parent.get_text(strip=True))
                    
                    if date_str == "未知日期":
                        date_str = extract_date_from_text(unquote(href))
                        
                    # 🌟 如果上面都找不到，套用剛剛找到的全域備註日期
                    if date_str == "未知日期":
                        date_str = global_date_str
                        
                    reports.append({
                        "Source": "Cathay",
                        "Date": date_str,
                        "Name": clean_title(title),
                        "Link": full_url
                    })
                    seen_pdfs.add(full_url)
                    
            browser.close()

    except Exception as e:
        print(f"  ❌ Cathay 爬取失敗: {e}")

    print(f"  ✅ Cathay 最終成功收錄 {len(reports)} 筆『投資研究週報』")
    return reports
