const NOTEBOOKLM_URL = "https://notebooklm.google.com/";

const SOURCE_URLS = [
  "https://raw.githubusercontent.com/dylanlu0604-dot/financial-report-hub/refs/heads/main/merged_plain_text_html/source1.html",
  "https://raw.githubusercontent.com/dylanlu0604-dot/financial-report-hub/refs/heads/main/merged_plain_text_html/source2.html",
  "https://raw.githubusercontent.com/dylanlu0604-dot/financial-report-hub/refs/heads/main/merged_plain_text_html/source3.html",
  "https://raw.githubusercontent.com/dylanlu0604-dot/financial-report-hub/refs/heads/main/merged_plain_text_html/source4.html",
  "https://raw.githubusercontent.com/dylanlu0604-dot/financial-report-hub/refs/heads/main/merged_plain_text_html/source5.html"
];

const FIRST_QUESTION = `步驟 1（只產生 85 個主題）


請建立一份機構級總體經濟簡報主題清單。請使用以下精確數量：

* 美國 10 個主題
* 歐洲 5 個主題
* 中國 5 個主題
* 日本 5 個主題
* 印度 5 個主題
* 東南亞 5 個主題
* 亞洲四小龍 10 個主題（台灣／韓國／香港／新加坡）
* 澳洲 5 個主題
* 南美洲 5 個主題
* 中東 5 個主題
* 科技／美國股市板塊／財報 5 個主題
* 加密貨幣  5 個主題
* 行情波動大的全球重要公司 10 個主題
* 大宗商品（銅、黃金、原油、天然氣等） 5 個主題

總計 = 85 個主題。

每個主題標題都必須清楚連結經濟層面的影響（成長／通膨／就業／貿易／政策）與金融市場層面的影響（利率／匯率／股票／信用／大宗商品／波動）。只輸出清單，並依地區分組。先不要製作投影片。最後停下來並詢問：「你想先展開哪個地區？」



步驟 2（只展開一個地區）


只將使用者選定的單一地區展開成投影片。該地區中的每個主題都要製作 5 張投影片。每張投影片需包含：1 個標題、2 個副標，以及兩段約 100 字的分析文字（驅動因素 + 對經濟／市場的影響）。每張投影片加入 6 個圖表參考，而且每一個圖表都必須來自 notebook 來源：請列出圖表標題 + 來源報告名稱（若有頁碼／圖號／章節也請附上）。不要虛構圖表或來源。`;

function taipeiDateString() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date());
  const data = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${data.year}-${data.month}-${data.day}`;
}

function notebookTitle() {
  return `${taipeiDateString()}報告集(近30天報告)`;
}

async function setBadge(text, color = "#1a73e8") {
  await chrome.action.setBadgeBackgroundColor({ color });
  await chrome.action.setBadgeText({ text });
}

async function getNotebookTab() {
  const tabs = await chrome.tabs.query({ url: "https://notebooklm.google.com/*" });
  return tabs.find((tab) => tab.url && tab.url.startsWith(NOTEBOOKLM_URL));
}

async function waitForTabComplete(tabId, timeoutMs = 60000) {
  const existing = await chrome.tabs.get(tabId);
  if (existing.status === "complete") return;

  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error("NotebookLM 分頁載入逾時"));
    }, timeoutMs);

    function listener(updatedTabId, info) {
      if (updatedTabId === tabId && info.status === "complete") {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }

    chrome.tabs.onUpdated.addListener(listener);
  });
}

function sendMessage(tabId, payload) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, payload, (response) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message });
      } else {
        resolve(response || { ok: false, error: "content script 無回應" });
      }
    });
  });
}

async function inject(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["content.js"]
  });
}

async function runImport() {
  await setBadge("RUN", "#1a73e8");

  let tab = await getNotebookTab();
  if (tab) {
    tab = await chrome.tabs.update(tab.id, { active: true, url: NOTEBOOKLM_URL });
  } else {
    tab = await chrome.tabs.create({ active: true, url: NOTEBOOKLM_URL });
  }

  await waitForTabComplete(tab.id);
  await inject(tab.id);

  const response = await sendMessage(tab.id, {
    type: "RUN_NOTEBOOKLM_REPORT_IMPORT",
    title: notebookTitle(),
    urls: SOURCE_URLS,
    firstQuestion: FIRST_QUESTION
  });

  if (response.ok) {
    await setBadge("OK", "#188038");
  } else {
    console.error("NotebookLM import failed:", response.error || response.text);
    await setBadge("ERR", "#d93025");
  }

  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 6000);
}

chrome.action.onClicked.addListener(() => {
  runImport().catch(async (error) => {
    console.error(error);
    await setBadge("ERR", "#d93025");
    setTimeout(() => chrome.action.setBadgeText({ text: "" }), 6000);
  });
});
