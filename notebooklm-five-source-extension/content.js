if (!window.__fiveSourceNotebookLmImporterLoaded) {
  window.__fiveSourceNotebookLmImporterLoaded = true;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const norm = (value) => (value || "").replace(/\s+/g, " ").trim();
  window.__fiveSourceNlmStatusHidden = false;

  function ensureStatusPanel(force = false) {
    if (force) window.__fiveSourceNlmStatusHidden = false;
    if (window.__fiveSourceNlmStatusHidden) return null;

    let panel = document.getElementById("five-source-nlm-status");
    let body = document.getElementById("five-source-nlm-status-body");
    if (panel && body) return body;

    panel = document.createElement("div");
    panel.id = "five-source-nlm-status";
    panel.style.cssText = [
      "position:fixed",
      "right:16px",
      "bottom:16px",
      "z-index:2147483647",
      "width:360px",
      "max-height:45vh",
      "overflow:auto",
      "border-radius:10px",
      "box-shadow:0 8px 28px rgba(0,0,0,.22)",
      "background:#fff",
      "color:#202124",
      "font:12px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
      "white-space:pre-wrap"
    ].join(";");
    const header = document.createElement("div");
    header.style.cssText = [
      "display:flex",
      "align-items:center",
      "justify-content:space-between",
      "gap:8px",
      "padding:8px 10px",
      "border-bottom:1px solid #e8eaed",
      "font-weight:600"
    ].join(";");
    header.textContent = "NotebookLM 匯入器";

    const close = document.createElement("button");
    close.type = "button";
    close.setAttribute("aria-label", "關閉匯入器狀態框");
    close.textContent = "x";
    close.style.cssText = [
      "width:24px",
      "height:24px",
      "border:0",
      "border-radius:12px",
      "background:#f1f3f4",
      "color:#3c4043",
      "font:16px/24px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
      "cursor:pointer"
    ].join(";");
    close.addEventListener("click", () => {
      window.__fiveSourceNlmStatusHidden = true;
      panel.remove();
    });
    header.appendChild(close);

    body = document.createElement("div");
    body.id = "five-source-nlm-status-body";
    body.style.cssText = "padding:10px 12px;";
    body.textContent = "NotebookLM 匯入器準備中...\n";

    panel.appendChild(header);
    panel.appendChild(body);
    document.documentElement.appendChild(panel);
    return body;
  }

  function progress(text, cls = "") {
    const panel = ensureStatusPanel();
    if (!panel) {
      console.log("[NotebookLM 30-source importer]", text);
      return;
    }
    const line = document.createElement("div");
    line.textContent = text;
    if (cls === "ok") line.style.color = "#188038";
    if (cls === "warn") line.style.color = "#b06000";
    if (cls === "err") line.style.color = "#d93025";
    panel.appendChild(line);
    panel.scrollTop = panel.scrollHeight;
    console.log("[NotebookLM 30-source importer]", text);
  }

  async function waitFor(fn, timeoutMs = 20000, stepMs = 300) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const value = fn();
      if (value) return value;
      await sleep(stepMs);
    }
    return null;
  }

  function isVisible(el) {
    if (!el) return false;
    const style = getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none") return false;
    return Boolean(el.offsetParent || el.getClientRects().length);
  }

  function labelOf(el) {
    return norm(
      [
        el?.innerText,
        el?.textContent,
        el?.getAttribute?.("aria-label"),
        el?.getAttribute?.("title"),
        el?.getAttribute?.("placeholder")
      ].filter(Boolean).join(" ")
    );
  }

  function clickableElements() {
    return Array.from(document.querySelectorAll([
      "button",
      "a",
      "[role='button']",
      "[role='link']",
      "[role='menuitem']",
      "[tabindex]:not([tabindex='-1'])"
    ].join(","))).filter(isVisible);
  }

  function listClickableLabels(limit = 80) {
    const seen = new Set();
    const labels = [];
    for (const el of clickableElements()) {
      const label = labelOf(el);
      if (!label || seen.has(label)) continue;
      seen.add(label);
      labels.push(label);
      if (labels.length >= limit) break;
    }
    return labels;
  }

  function findClickable(texts) {
    const elements = clickableElements();
    for (const text of texts) {
      const exact = elements.find((el) => labelOf(el) === text);
      if (exact) return exact;
    }
    for (const text of texts) {
      const lower = text.toLowerCase();
      const partial = elements.find((el) => labelOf(el).toLowerCase().includes(lower));
      if (partial) return partial;
    }
    return null;
  }

  function scopedClickableElements(root) {
    return Array.from(root.querySelectorAll([
      "button",
      "a",
      "[role='button']",
      "[role='link']",
      "[role='menuitem']",
      "[tabindex]:not([tabindex='-1'])"
    ].join(","))).filter(isVisible);
  }

  function findClickableIn(root, texts, options = {}) {
    const elements = scopedClickableElements(root).filter((el) => !options.exclude?.(el));
    for (const text of texts) {
      const exact = elements.find((el) => labelOf(el) === text);
      if (exact) return exact;
    }
    for (const text of texts) {
      const lower = text.toLowerCase();
      const partial = elements.find((el) => labelOf(el).toLowerCase().includes(lower));
      if (partial) return partial;
    }
    return null;
  }

  function listLabelsIn(root, limit = 60) {
    const seen = new Set();
    const labels = [];
    for (const el of scopedClickableElements(root)) {
      const label = labelOf(el);
      if (!label || seen.has(label)) continue;
      seen.add(label);
      labels.push(label);
      if (labels.length >= limit) break;
    }
    return labels;
  }

  function activeSourceDialog() {
    const roots = Array.from(document.querySelectorAll([
      "[role='dialog']",
      "mat-dialog-container",
      ".cdk-overlay-pane",
      "[class*='dialog']",
      "[class*='Dialog']",
      "[class*='modal']",
      "[class*='Modal']"
    ].join(",")))
      .filter((el) => isVisible(el) && el.id !== "five-source-nlm-status")
      .filter((el) => /來源|source|網站|website|url|網址|YouTube|Drive|貼上|paste/i.test(norm(el.innerText || el.textContent || "")));
    return roots.at(-1) || null;
  }

  function dialogOrDocument() {
    return activeSourceDialog() || document;
  }

  async function clickText(texts, description, timeoutMs = 20000) {
    const button = await waitFor(() => findClickable(texts), timeoutMs);
    if (!button) {
      progress(`找不到 ${description}。目前可點文字：${listClickableLabels().join(" | ")}`, "warn");
      throw new Error(`找不到 ${description}`);
    }
    progress(`點擊 ${description}：${labelOf(button)}`);
    button.click();
    await sleep(900);
    return button;
  }

  function visibleText() {
    return norm(document.body?.innerText || "");
  }

  async function createNotebook() {
    progress("等待 NotebookLM 首頁載入...");
    await waitFor(() => document.body && visibleText().length > 20, 30000);

    await clickText([
      "建立筆記本",
      "建立新的筆記本",
      "新增筆記本",
      "建立新筆記本",
      "Create new notebook",
      "New notebook",
      "Create",
      "建立"
    ], "建立筆記本按鈕", 30000);

    const ready = await waitFor(() => (
      findClickable(["新增來源", "Add source", "新增", "Add"]) ||
      /新增來源|Add source|Sources|來源/.test(visibleText())
    ), 45000);

    if (!ready) throw new Error("已點建立筆記本，但等不到筆記本頁面或新增來源按鈕");
    progress("新筆記本已建立", "ok");
  }

  async function openAddSourceDialog() {
    const currentRoot = activeSourceDialog();
    if (currentRoot && (findUrlTextbox(currentRoot) || findClickableIn(currentRoot, ["網站", "Website", "網址", "YouTube", "貼上文字", "Paste text", "Copied text"]))) return;
    await clickText([
      "新增來源",
      "新增來源 +",
      "Add source",
      "Add sources",
      "Add",
      "新增"
    ], "新增來源按鈕", 25000);
  }

  async function selectWebsiteSource() {
    let root = dialogOrDocument();
    const existingTextbox = findUrlTextbox(root);
    if (existingTextbox) return existingTextbox;

    const website = findClickableIn(root, [
      "網站",
      "網站連結",
      "網址",
      "Website",
      "Web",
      "Link",
      "URL"
    ]);

    if (website) {
      progress(`選擇網址/網站來源：${labelOf(website)}`);
      website.click();
      await sleep(800);
    }

    const textbox = await waitFor(() => {
      root = dialogOrDocument();
      return findUrlTextbox(root);
    }, 15000);
    if (!textbox) {
      progress(`找不到 URL 輸入欄。對話框可點文字：${listLabelsIn(root).join(" | ")}`, "warn");
      throw new Error("找不到 URL 輸入欄");
    }
    return textbox;
  }

  function findUrlTextbox(root = document) {
    const fields = Array.from(root.querySelectorAll("input, textarea, [contenteditable='true'], [role='textbox']"))
      .filter(isVisible);

    const urlLike = fields.find((field) => {
      const label = [
        field.getAttribute("aria-label"),
        field.getAttribute("placeholder"),
        field.getAttribute("title"),
        field.textContent
      ].map(norm).join(" ").toLowerCase();
      return /url|網址|連結|link|website|http/.test(label);
    });
    if (urlLike) return urlLike;

    return fields.find((field) => {
      const tag = field.tagName;
      const type = (field.getAttribute("type") || "text").toLowerCase();
      return tag === "TEXTAREA" || type === "url" || type === "text" || field.getAttribute("contenteditable") === "true";
    }) || null;
  }

  function textFieldValue(field) {
    if (!field) return "";
    return "value" in field ? field.value : field.textContent || "";
  }

  function setFieldValue(field, value) {
    field.focus();
    field.click();
    if (field.getAttribute("contenteditable") === "true") {
      document.execCommand("selectAll", false, null);
      document.execCommand("insertText", false, value);
      field.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
      return;
    }

    const proto = field.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    setter ? setter.call(field, value) : (field.value = value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.dispatchEvent(new Event("change", { bubbles: true }));
  }

  async function pressEnter(field, description) {
    field.focus();
    await sleep(150);
    progress(`${description}：按 Enter 送出`);
    const eventOptions = {
      key: "Enter",
      code: "Enter",
      keyCode: 13,
      which: 13,
      bubbles: true,
      cancelable: true
    };
    field.dispatchEvent(new KeyboardEvent("keydown", eventOptions));
    field.dispatchEvent(new KeyboardEvent("keypress", eventOptions));
    field.dispatchEvent(new KeyboardEvent("keyup", eventOptions));
  }

  async function clickElement(el, description) {
    el.scrollIntoView({ block: "center", inline: "center" });
    await sleep(300);
    progress(`${description}：${labelOf(el) || "目標按鈕"}`);
    const rect = el.getBoundingClientRect();
    const options = {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: rect.left + rect.width / 2,
      clientY: rect.top + rect.height / 2
    };
    el.dispatchEvent(new MouseEvent("mouseover", options));
    el.dispatchEvent(new MouseEvent("mousemove", options));
    el.dispatchEvent(new MouseEvent("mousedown", options));
    el.dispatchEvent(new MouseEvent("mouseup", options));
    el.dispatchEvent(new MouseEvent("click", options));
    await sleep(300);
  }

  function findSourceSubmitButton(root = dialogOrDocument()) {
    const labels = [
      "插入",
      "新增",
      "新增來源",
      "匯入",
      "送出",
      "提交",
      "Insert",
      "Add",
      "Add source",
      "Import",
      "Submit"
    ];

    const matches = scopedClickableElements(root).filter((el) => {
      if (el.disabled || el.getAttribute("aria-disabled") === "true") return false;
      const label = labelOf(el);
      if (!label) return false;
      if (/網站|website|url|網址|link|連結|youtube|drive|貼上文字|paste text/i.test(label)) return false;
      return labels.some((text) => label.toLowerCase().includes(text.toLowerCase()));
    });

    return matches
      .map((el) => ({ el, rect: el.getBoundingClientRect() }))
      .sort((a, b) => (b.rect.top - a.rect.top) || (b.rect.left - a.rect.left))[0]?.el || null;
  }

  function chatInputCandidates() {
    return Array.from(document.querySelectorAll("textarea, [contenteditable='true'], [role='textbox'], input"))
      .filter(isVisible)
      .filter((field) => {
        const tag = field.tagName;
        const type = (field.getAttribute("type") || "text").toLowerCase();
        if (tag === "INPUT" && !["text", "search"].includes(type)) return false;

        const label = [
          field.getAttribute("aria-label"),
          field.getAttribute("placeholder"),
          field.getAttribute("title"),
          field.getAttribute("name"),
          field.getAttribute("data-placeholder"),
          field.textContent
        ].map(norm).join(" ").toLowerCase();

        if (/url|網址|連結|link|website|source|來源|title|標題|notebook|筆記本/.test(label)) return false;
        return true;
      });
  }

  function findChatTextbox() {
    const fields = chatInputCandidates();
    const preferred = fields.find((field) => {
      const label = [
        field.getAttribute("aria-label"),
        field.getAttribute("placeholder"),
        field.getAttribute("title"),
        field.getAttribute("data-placeholder"),
        field.textContent
      ].map(norm).join(" ").toLowerCase();
      return /ask|question|chat|message|prompt|提問|問題|詢問|訊息|輸入|傳送/.test(label);
    });
    if (preferred) return preferred;

    return fields.find((field) => {
      const rect = field.getBoundingClientRect();
      return rect.width >= 240 && rect.bottom > window.innerHeight * 0.45;
    }) || fields.at(-1) || null;
  }

  async function submitFirstQuestion(firstQuestion) {
    if (!firstQuestion) return;

    progress("等待 30 秒，讓 NotebookLM 處理來源...");
    await sleep(30000);
    progress("準備輸入第一個問題...");

    const textbox = await waitFor(() => findChatTextbox(), 30000, 500);
    if (!textbox) {
      progress(`找不到 NotebookLM 提問欄。目前可點文字：${listClickableLabels().join(" | ")}`, "warn");
      throw new Error("找不到 NotebookLM 提問欄");
    }

    textbox.scrollIntoView({ block: "center", inline: "center" });
    await sleep(300);
    setFieldValue(textbox, firstQuestion);
    await sleep(900);
    await pressEnter(textbox, "送出第一個問題");

    const sent = await waitFor(() => {
      const value = norm(textFieldValue(textbox));
      if (!value || !value.includes("步驟 1")) return true;
      if (visibleText().includes("你想先展開哪個地區")) return true;
      return null;
    }, 15000, 500);

    if (!sent) {
      progress("第一個問題可能尚未送出，請確認提問欄是否仍保留文字。", "warn");
      throw new Error("第一個問題送出未完成");
    }

    progress("第一個問題已送出", "ok");
  }

  function findSaveToNoteButton() {
    const labels = [
      "儲存至記事",
      "儲存到記事",
      "儲存為記事",
      "儲存至筆記",
      "儲存到筆記",
      "儲存為筆記",
      "Save to note",
      "Save to notes",
      "Save as note",
      "Save note"
    ];

    const matches = clickableElements().filter((el) => {
      if (el.disabled || el.getAttribute("aria-disabled") === "true") return false;
      if (el.closest?.("#five-source-nlm-status")) return false;

      const label = labelOf(el).toLowerCase();
      if (/已儲存|saved to note|saved/i.test(label)) return false;
      return labels.some((text) => label.includes(text.toLowerCase()));
    });

    return matches
      .map((el) => ({ el, rect: el.getBoundingClientRect() }))
      .sort((a, b) => (b.rect.top - a.rect.top) || (b.rect.left - a.rect.left))[0]?.el || null;
  }

  async function saveFirstAnswerToNote() {
    progress("等待步驟 1 回答完成：先固定等待 60 秒...");
    await sleep(60000);

    for (let attempt = 1; attempt <= 3; attempt += 1) {
      progress(`第 ${attempt}/3 次嘗試儲存至記事...`);

      const ready = await waitFor(() => {
        const saveButton = findSaveToNoteButton();
        if (saveButton && visibleText().includes("你想先展開哪個地區")) return saveButton;
        if (saveButton && /85 個主題|85個主題|美國 10|美國10|你想先展開哪個地區/.test(visibleText())) return saveButton;
        return null;
      }, 90000, 1500);

      if (!ready) {
        progress(`第 ${attempt}/3 次找不到「儲存至記事」按鈕。`, "warn");
        if (attempt < 3) {
          progress("再等待 30 秒後重試...");
          await sleep(30000);
          continue;
        }
        progress(`目前可點文字：${listClickableLabels().join(" | ")}`, "warn");
        throw new Error("找不到儲存至記事按鈕");
      }

      await clickElement(ready, "點擊儲存至記事");

      const saved = await waitFor(() => {
        const text = visibleText();
        if (/已儲存|儲存成功|已加入記事|記事已儲存|已新增至記事|saved|note saved/i.test(text)) return "confirmed";
        const stillHasButton = findSaveToNoteButton();
        return stillHasButton ? null : "button-gone";
      }, 15000, 500);

      if (saved) {
        progress("步驟 1 回答已儲存至記事", "ok");
        return;
      }

      progress(`第 ${attempt}/3 次已點擊，但尚未確認儲存完成。`, "warn");
      if (attempt < 3) {
        progress("再等待 30 秒後重試...");
        await sleep(30000);
      }
    }

    progress("已完成 3 次儲存嘗試；NotebookLM 沒有顯示確認提示，流程繼續。", "warn");
  }

  async function submitSourceUrl(url) {
    await openAddSourceDialog();
    const textbox = await selectWebsiteSource();
    const dialog = activeSourceDialog();
    progress(`填入 URL：${url}`);
    setFieldValue(textbox, url);
    await sleep(900);
    await pressEnter(textbox, "送出來源");

    const submitted = await waitFor(() => {
      const stillSameDialog = dialog && isVisible(dialog);
      const bodyText = visibleText();
      if (/無法|失敗|錯誤|invalid|failed|error|too long|字數|來源過長/i.test(bodyText)) return "error";
      if (!stillSameDialog) return "closed";
      const currentValue = textFieldValue(textbox);
      if (!norm(currentValue).includes(url.slice(0, 40))) return "cleared";
      return null;
    }, 20000, 500);

    if (submitted === "error") {
      throw new Error("NotebookLM 顯示來源匯入錯誤，請看頁面上的錯誤訊息");
    }
    if (!submitted) {
      progress("送出後對話框沒有關閉，可能沒有真正匯入。", "warn");
      throw new Error("URL 送出未完成");
    }

    await sleep(1500);
  }

  async function submitSourceUrlsBatch(urls) {
    await openAddSourceDialog();
    const textbox = await selectWebsiteSource();
    const dialog = activeSourceDialog();
    const joinedUrls = urls.join("\n");
    progress(`一次填入 ${urls.length} 個來源 URL（每行一個）`);
    setFieldValue(textbox, joinedUrls);
    await sleep(900);
    const submitButton = findSourceSubmitButton(dialog || dialogOrDocument());
    if (submitButton) {
      await clickElement(submitButton, "送出全部來源");
    } else {
      await pressEnter(textbox, "送出全部來源");
    }

    const submitted = await waitFor(() => {
      const stillSameDialog = dialog && isVisible(dialog);
      const bodyText = visibleText();
      if (/無法|失敗|錯誤|invalid|failed|error|too long|字數|來源過長/i.test(bodyText)) return "error";
      if (!stillSameDialog) return "closed";
      const currentValue = norm(textFieldValue(textbox));
      if (!currentValue.includes(urls[0].slice(0, 40))) return "cleared";
      return null;
    }, 30000, 500);

    if (submitted === "error") {
      throw new Error("NotebookLM 顯示來源匯入錯誤，請看頁面上的錯誤訊息");
    }
    if (!submitted) {
      progress("送出後對話框沒有關閉，可能沒有真正匯入。", "warn");
      throw new Error("批次 URL 送出未完成");
    }

    await sleep(1500);
  }

  async function importUrls(urls) {
    progress(`準備批次匯入 ${urls.length} 個來源...`);
    await submitSourceUrlsBatch(urls);
    progress(`${urls.length} 個來源已一次送出`, "ok");
  }

  function isEditableField(el) {
    return Boolean(el && (
      ("value" in el && /INPUT|TEXTAREA/.test(el.tagName)) ||
      el.getAttribute("contenteditable") === "true" ||
      el.getAttribute("role") === "textbox"
    ));
  }

  function titleCandidateText(el) {
    return norm([
      el?.innerText,
      el?.textContent,
      el?.value,
      el?.getAttribute?.("aria-label"),
      el?.getAttribute?.("title"),
      el?.getAttribute?.("placeholder"),
      el?.getAttribute?.("data-testid"),
      el?.className
    ].filter(Boolean).join(" "));
  }

  function isBadTitleCandidate(el) {
    if (!el || el.closest?.("#five-source-nlm-status")) return true;
    if (el.closest?.("[role='dialog'], mat-dialog-container, .cdk-overlay-pane")) return true;

    const text = titleCandidateText(el).toLowerCase();
    return /來源|source|新增|add|url|網址|website|link|chat|message|prompt|question|問題|提問|ask|share|分享|settings|設定/.test(text);
  }

  function notebookTitleCandidates() {
    const selectors = [
      "input",
      "[contenteditable='true']",
      "[role='textbox']",
      "h1",
      "h2",
      "button",
      "[role='button']",
      "[aria-label]",
      "[title]",
      "[data-testid]"
    ].join(",");

    return Array.from(document.querySelectorAll(selectors))
      .filter(isVisible)
      .filter((el) => !isBadTitleCandidate(el))
      .filter((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.top > Math.max(260, window.innerHeight * 0.35)) return false;
        const text = titleCandidateText(el);
        return /未命名|Untitled|notebook|筆記本|title|標題|name|名稱|rename|重新命名|edit/i.test(text) ||
          /H1|H2/.test(el.tagName);
      })
      .sort((a, b) => {
        const score = (el) => {
          const text = titleCandidateText(el);
          let value = 0;
          if (/未命名|Untitled/i.test(text)) value += 80;
          if (/notebook|筆記本|title|標題|name|名稱/i.test(text)) value += 45;
          if (/H1|H2/.test(el.tagName)) value += 30;
          if (isEditableField(el)) value += 20;
          value -= Math.max(0, el.getBoundingClientRect().top);
          return value;
        };
        return score(b) - score(a);
      });
  }

  function findActiveEditable() {
    const active = document.activeElement;
    if (isEditableField(active) && !isBadTitleCandidate(active)) return active;

    return Array.from(document.querySelectorAll("input, textarea, [contenteditable='true'], [role='textbox']"))
      .filter(isVisible)
      .filter((el) => !isBadTitleCandidate(el))
      .find((el) => {
        const rect = el.getBoundingClientRect();
        return rect.top <= Math.max(260, window.innerHeight * 0.35);
      }) || null;
  }

  async function commitTitleEdit(field) {
    await pressEnter(field, "送出筆記本名稱");
    field.blur?.();
    return waitFor(() => visibleText().includes(field.__targetNotebookTitle), 6000, 300);
  }

  async function trySetNotebookTitle(target, title) {
    target.scrollIntoView({ block: "center", inline: "center" });
    await sleep(200);
    target.click();
    await sleep(250);

    let field = isEditableField(target) ? target : findActiveEditable();
    if (!field) {
      target.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
      await sleep(450);
      field = findActiveEditable();
    }

    if (!field) return false;

    setFieldValue(field, title);
    field.__targetNotebookTitle = title;
    const confirmed = await commitTitleEdit(field);
    return Boolean(confirmed);
  }

  async function clickRenameButton() {
    const rename = findClickable([
      "重新命名",
      "重新命名筆記本",
      "編輯標題",
      "編輯名稱",
      "Rename",
      "Rename notebook",
      "Edit title",
      "Edit name"
    ]);
    if (!rename || isBadTitleCandidate(rename)) return false;

    const rect = rename.getBoundingClientRect();
    if (rect.top > Math.max(260, window.innerHeight * 0.35)) return false;
    progress(`點擊重新命名入口：${labelOf(rename)}`);
    rename.click();
    await sleep(600);
    return true;
  }

  async function renameNotebook(title) {
    progress(`嘗試命名筆記本：${title}`);
    await sleep(1200);

    try {
      if (visibleText().includes(title)) {
        progress("筆記本名稱已存在", "ok");
        return;
      }

      const candidates = notebookTitleCandidates();
      progress(`找到 ${candidates.length} 個可能的標題欄`);
      for (const candidate of candidates.slice(0, 6)) {
        if (await trySetNotebookTitle(candidate, title)) {
          progress("筆記本命名已確認", "ok");
          return;
        }
      }

      if (await clickRenameButton()) {
        const field = await waitFor(() => findActiveEditable(), 4000, 300);
        if (field) {
          setFieldValue(field, title);
          field.__targetNotebookTitle = title;
          if (await commitTitleEdit(field)) {
            progress("筆記本命名已確認", "ok");
            return;
          }
        }
      }

      progress(`自動命名未確認成功，請手動改名為：${title}`, "warn");
    } catch (error) {
      progress(`自動命名失敗，請手動改名為：${title}`, "warn");
    }
  }

  async function run({ title, urls, firstQuestion }) {
    ensureStatusPanel(true).textContent = "";
    progress("開始建立 NotebookLM 報告集...");
    progress(`目標名稱：${title}`);
    await createNotebook();
    await importUrls(urls);
    await renameNotebook(title);
    await submitFirstQuestion(firstQuestion);
    await saveFirstAnswerToNote();
    progress("流程完成。若 NotebookLM 還在處理來源，請等待它完成解析。", "ok");
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "RUN_NOTEBOOKLM_REPORT_IMPORT") return false;

    (async () => {
      try {
        await run(message);
        sendResponse({ ok: true });
      } catch (error) {
        progress(`錯誤：${error.message}`, "err");
        sendResponse({ ok: false, error: error.message });
      }
    })();
    return true;
  });
}
