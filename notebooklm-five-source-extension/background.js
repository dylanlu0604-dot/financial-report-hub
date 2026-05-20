const NOTEBOOKLM_URL = "https://notebooklm.google.com/";

const SOURCE_URLS = [
  "https://raw.githubusercontent.com/dylanlu0604-dot/financial-report-hub/refs/heads/main/merged_plain_text_html/source1.html",
  "https://raw.githubusercontent.com/dylanlu0604-dot/financial-report-hub/refs/heads/main/merged_plain_text_html/source2.html",
  "https://raw.githubusercontent.com/dylanlu0604-dot/financial-report-hub/refs/heads/main/merged_plain_text_html/source3.html",
  "https://raw.githubusercontent.com/dylanlu0604-dot/financial-report-hub/refs/heads/main/merged_plain_text_html/source4.html",
  "https://raw.githubusercontent.com/dylanlu0604-dot/financial-report-hub/refs/heads/main/merged_plain_text_html/source5.html"
];

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
    urls: SOURCE_URLS
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
