# 中英版本驗證 / Bilingual UI verification

2026-10-07。介面支援繁體中文與 English，使用右上角語言選單，瀏覽器保存 `roomflow-language` 選擇。 / The top-right selector supports Traditional Chinese and English and saves the browser's choice.

## 實作 / Implementation

- [i18n.js](../public/i18n.js)：靜態文字、標題、document.lang、無障礙標籤、語言保存；保留圖示與既有 HTML 結構。 / Static copy, title, document language, accessibility labels, persistence, and preserved markup.
- [dynamic-i18n.js](../public/dynamic-i18n.js)：操作提示、API 錯誤、參數化訊息、模型限制、實測數值與未解決異常的說明。 / Runtime copy, parameterized API errors, model limits, and audited evidence caveats.
- [app.js](../public/app.js)：語言切換後重畫已快取的狀態與報告，保留輸入、會議期限、實驗及實測情境。 / Re-renders cached status and reports without resetting inputs, leases, experiments, or the selected evidence scenario.
- 原始 JSON／CSV 欄位和值不翻譯、不改寫。 / Raw JSON/CSV identifiers and values remain unchanged.

## 已完成的檢查 / Completed checks

Node 測試 **29／29 通過**，包含原有 24 項與新增 [5 項語言完整性測試](../tests/i18n.test.mjs)。 / All **29 Node tests passed**, including the existing 24 and five localization integrity tests.

新增檢查涵蓋實際 HTML 靜態及無障礙文字、保存語言與重新初始化、localStorage 無法使用時仍可切換、參數化驗證錯誤及多行 OS 診斷、缺失 RTT 與「—」、未解決實測限制、表單識別／值／選項／匯出連結與原始測量內容不變。 / Coverage includes actual HTML/accessibility copy, persistence and reinitialization, unavailable storage, parameterized errors and multiline OS details, missing RTT markers, honest caveats, and unchanged form/export/data identifiers.

瀏覽器存取被拒絕前，已完成： / Before browser access was denied, the following checks completed:

- 英文靜態／動態介面、已載入模型報告及 Linux 實測說明皆有翻譯；剩餘中文字為語言選單中刻意保留的「繁體中文」。 / English static/runtime copy, loaded model reports, and saved kernel evidence were translated; the intentional Chinese language choice remained.
- 會議啟用中切換語言，API 會議狀態與數值保持一致；期限到達後恢復一般模式。 / Switching during an active lease preserved API state and values; expiry restored normal mode.
- 實驗執行中切換語言，實驗仍完成；歷史報告可顯示。 / An in-flight experiment completed across a language change, and history reports rendered.
- 重新整理保留英文選擇、document.lang 與標題。 / Reload preserved English, document language, and title.
- 英文桌面 clientWidth 與 scrollWidth 均為 1265，沒有整頁橫向溢出。 / English desktop clientWidth and scrollWidth both measured 1265, with no page-wide horizontal overflow.
- [英文桌面畫面](../artifacts/screenshots/bilingual-en-desktop.jpg) 已保存。 / An English desktop screenshot was saved.

## 尚未完成的目視檢查 / Remaining visual checks

瀏覽器安全檢查拒絕存取本機 URL，回傳原因為權限被拒絕；所有後續瀏覽器操作已停止，沒有透過其他瀏覽器或間接方法繼續。 / Browser security rejected the local URL because permission was denied. Further browser interaction stopped, without alternate-surface or indirect workarounds.

手機英文／中文的最終 overflow／畫面檢查尚未完成，不能據此宣稱手機版目視 QA 通過。QA Chrome 的暫時 viewport 留在 390×844，語言為英文；權限拒絕後沒有再操作它。此選擇與使用者的 in-app browser 分開。 / Final mobile overflow and screenshot checks remain incomplete. The QA Chrome viewport was left at 390×844 with English selected because further interaction was blocked. Its preference is separate from the user's in-app browser.

此次只改動呈現與語言；原本 Linux 實驗的延遲／丟包波動仍未解決，英譯完整保留此限制。 / This change localizes presentation; the original kernel timing/loss limitations remain unresolved and are retained in English.
