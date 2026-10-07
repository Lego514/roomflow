'use strict';

(() => {
  const STORAGE_KEY = 'roomflow-language';
  // Static content is keyed separately from experiment data and runtime messages.
  // Bind text nodes instead of replacing parent HTML so icons, emphasis and line
  // breaks retain their structure. All translations are written as plain text.
  const catalogue = [
    ['page.title', '同住 NetTogether｜會議模式實驗室', 'NetTogether | Meeting Mode Lab'],
    ['brand.name', '同住', 'Together'],
    ['brand.footer', '同住 NetTogether', 'NetTogether'],
    ['brand.tagline', '讓共享網路，更好相處。', 'A shared connection. A calmer home.'],
    ['nav.meeting', '會議模式', 'Meeting mode'],
    ['nav.lab', '網路實驗室', 'Network lab'],
    ['nav.reports', '測試報告', 'Reports'],
    ['sidebar.note.title', '先量測，再下結論。', 'Measure before you decide.'],
    ['sidebar.note.body', '比較連線穩定性，也看其他室友的傳輸速度。好的策略需要一起衡量。', 'Compare meeting stability and everyone else’s transfer speeds. A useful policy considers both.'],
    ['sidebar.environment', '本機模擬環境', 'Local simulation'],
    ['sidebar.engine', '離散事件佇列模型', 'Discrete-event queue model'],
    ['breadcrumb.home', '居家網路 /', 'Home network /'],
    ['breadcrumb.lab', '會議模式實驗室', 'Meeting Mode Lab'],
    ['language.label', '語言', 'Language'],
    ['hero.first', '一起上網，', 'Share the connection. '],
    ['hero.second', '重要的時刻更穩。', 'Make room for meetings.'],
    ['hero.description', '模擬室友上傳與下載，看看流量策略能否減少會議延遲。', 'Simulate a roommate’s uploads and downloads to see whether traffic policies reduce meeting latency.'],
    ['hero.model', '模擬環境', 'Simulation'],
    ['hero.source', '結果來自佇列模型', 'Results from a queue model'],
    ['scope.before', '這裡控制的是', 'These controls apply a '],
    ['scope.emphasis', '模擬策略', 'model policy'],
    ['scope.after', '，不會修改家中路由器。公平排隊與優先模式是模型實作，非 Linux CAKE；結果不代表真實視訊通話品質。', '. Your home router is unchanged. Fair queuing and priority are model implementations, not Linux CAKE. Results do not establish real video-call quality.'],
    ['session.title', '留一點空間，給你的會議。', 'Make room for your meeting.'],
    ['common.loading', '讀取中', 'Loading'],
    ['session.description', '指定會議裝置與時間，到期後自動回到一般模式。', 'Choose a meeting device and duration. Normal mode resumes when the timer expires.'],
    ['session.device', '會議裝置', 'Meeting device'],
    ['device.me', '我的電腦', 'My computer'],
    ['device.description', '模擬會議端 · meeting', 'Simulated meeting client · meeting'],
    ['device.selected', '已選取', 'Selected'],
    ['session.duration', '模式持續時間', 'Mode duration'],
    ['session.duration.10', '10 秒 · 自動恢復測試', '10 seconds · expiry test'],
    ['session.duration.60', '1 分鐘 · 快速測試', '1 minute · quick test'],
    ['session.duration.300', '5 分鐘', '5 minutes'],
    ['session.duration.900', '15 分鐘', '15 minutes'],
    ['session.duration.3600', '60 分鐘', '60 minutes'],
    ['session.remaining', '剩餘時間', 'Time remaining'],
    ['session.start', '啟用模擬會議模式', 'Start simulated meeting mode'],
    ['session.stop', '提前結束，恢復一般模式', 'Stop and restore normal mode'],
    ['session.reading', '正在確認伺服器上的模式狀態…', 'Checking the mode stored on the server…'],
    ['session.preview', '目前策略快照', 'Current policy snapshot'],
    ['session.preview.waiting', '等待有效快照', 'Waiting for a snapshot'],
    ['session.preview.description', '固定混合負載的 5 秒模型試算；非即時網路量測。', 'A 5-second model run with a fixed mixed workload; not live network telemetry.'],
    ['topology.title', '同一條網路，兩種需求。', 'One connection, two needs.'],
    ['topology.meeting', '即時 UDP 流量', 'Real-time UDP traffic'],
    ['topology.roommate', '室友電腦', 'Roommate’s computer'],
    ['topology.tcp', 'TCP 背景傳輸', 'Background TCP transfers'],
    ['topology.router', '模擬路由器', 'Simulated router'],
    ['mode.normal', '一般模式', 'Normal mode'],
    ['topology.server', '虛擬伺服器', 'Virtual server'],
    ['topology.local', '同機內部流量', 'Traffic stays on this machine'],
    ['topology.download', '共用下載頻寬', 'Shared download capacity'],
    ['topology.upload', '共用上傳頻寬', 'Shared upload capacity'],
    ['topology.rtt', '基礎往返延遲', 'Base round-trip latency'],
    ['topology.note', '對照實驗固定比較三種策略；計時模式為模型控制示範，不影響比較條件。', 'Experiments always compare all three policies. The timer demonstrates model control and does not change the comparison conditions.'],
    ['experiment.title', '建立一次可重現的實驗', 'Build a repeatable experiment'],
    ['experiment.description', '固定頻寬與負載，讓三種策略在相同條件下比較。', 'Keep capacity and workload fixed for a like-for-like comparison.'],
    ['experiment.scenario', '室友正在做什麼？', 'What is your roommate doing?'],
    ['scenario.idle', '沒有背景傳輸', 'No background traffic'],
    ['scenario.idle.description', '正常連線基準', 'An unloaded baseline'],
    ['scenario.upload', '上傳檔案', 'Uploading files'],
    ['scenario.upload.description', '照片備份、雲端同步', 'Photo backups and cloud sync'],
    ['scenario.download', '大量下載', 'Heavy downloads'],
    ['scenario.download.description', '遊戲與大型檔案', 'Games and large files'],
    ['scenario.mixed', '上傳與下載', 'Uploads and downloads'],
    ['scenario.mixed.description', '混合壅塞情境', 'Congestion in both directions'],
    ['experiment.down', '下載頻寬', 'Download capacity'],
    ['experiment.up', '上傳頻寬', 'Upload capacity'],
    ['experiment.rtt', '基礎 RTT', 'Base RTT'],
    ['experiment.duration', '每次模擬', 'Model duration'],
    ['unit.seconds', '秒', 's'],
    ['experiment.repeats', '各策略重複', 'Repeats / policy'],
    ['unit.runs', '次', 'runs'],
    ['experiment.seed', '隨機種子', 'Random seed'],
    ['policy.fifo', '普通 FIFO', 'FIFO'],
    ['policy.fair', '公平排隊模型', 'Fair-queue model'],
    ['policy.priority', '會議優先模型', 'Meeting-priority model'],
    ['experiment.start', '開始比較實驗', 'Run comparison'],
    ['experiment.preparing', '準備實驗…', 'Preparing the experiment…'],
    ['experiment.time.note', '60 秒是模型中的時間，計算速度可能快於實際時間。', 'Duration is simulated time. Calculation may finish faster than real time.'],
    ['results.title', '改善了多少？用結果說話。', 'What changed? Look at the evidence.'],
    ['results.description', '完成實驗後，這裡會顯示模型實際輸出的指標。', 'Actual model outputs appear here when an experiment completes.'],
    ['results.csv', '匯出 CSV', 'Export CSV'],
    ['results.json', '匯出 JSON', 'Export JSON'],
    ['results.empty.title', '第一份實驗報告，從一次比較開始。', 'Your first report starts with a comparison.'],
    ['results.empty.body', '執行上方實驗，查看會議穩定性和室友傳輸速度的取捨。', 'Run an experiment above to compare meeting stability and background transfer speeds.'],
    ['results.configure', '設定實驗', 'Configure experiment'],
    ['chart.title', '會議往返延遲', 'Meeting round-trip latency'],
    ['chart.description', '顯示第一次重複測試的模型時間序列；數值越低越好。', 'Time series from the first model repetition. Lower latency is better.'],
    ['table.title', '三種策略，同時看穩定與速度。', 'Compare stability and speed across all three policies.'],
    ['table.caption', '各策略的會議延遲、抖動、封包遺失、會議流量與背景傳輸比較', 'Meeting latency, jitter, packet loss and throughput for each policy'],
    ['table.policy', '流量策略', 'Traffic policy'],
    ['table.loss', '封包遺失', 'Packet loss'],
    ['table.meeting', '會議傳輸', 'Meeting throughput'],
    ['table.background', '背景傳輸', 'Background throughput'],
    ['table.note', '各欄為每次重複測試指標的平均值，p95 RTT 並非合併所有封包後重算的百分位數。原始結果可下載核對。', 'Values are averages of per-run summaries. Mean p95 RTT is not a percentile recalculated from pooled packets. Download the raw results to inspect them.'],
    ['kernel.title', '保存的 Linux 封包實測', 'Saved Linux packet measurements'],
    ['kernel.scope', '隔離虛擬拓樸；非目前家中 Wi-Fi。上方 Web 計時卡仍控制模型。', 'An isolated virtual topology, not your current home Wi-Fi. The web timer above still controls the model.'],
    ['kernel.reading', '正在讀取已保存的封包實測。', 'Loading the saved packet measurements.'],
    ['kernel.initial', '尚未載入實測指標。這個區塊的資料與上方模型結果分開保存。', 'Measurements have not loaded yet. This evidence is stored separately from the model results above.'],
    ['kernel.policy.title', '三種核心排隊策略', 'Three kernel queueing policies'],
    ['kernel.policy.description', '每個情境採相同瓶頸、固定負載，各自重複量測。', 'Repeated measurements with the same bottleneck and fixed workload in each scenario.'],
    ['kernel.scenario', '實測情境', 'Measured scenario'],
    ['kernel.csv', '下載實測 CSV', 'Download measurements CSV'],
    ['kernel.table.caption', 'Linux 核心各策略的 RTT、各方向會議遺失率和背景傳輸速度', 'Linux policy RTT, per-direction meeting packet loss and background throughput'],
    ['kernel.policy', '核心策略', 'Kernel policy'],
    ['kernel.rtt', 'p95 RTT 平均', 'Mean p95 RTT'],
    ['kernel.up.loss', '會議上傳遺失', 'Meeting upload loss'],
    ['kernel.down.loss', '會議下載遺失', 'Meeting download loss'],
    ['kernel.up.background', '背景上傳', 'Background upload'],
    ['kernel.down.background', '背景下載', 'Background download'],
    ['kernel.table.note', 'RTT 為各次測試 p95 的平均；下方區間為各次 p95 的最小與最大值。遺失率與背景速度分別呈現上傳、下載，不與模型欄位合併。', 'RTT is the mean of per-run p95 values; the range below shows their minimum and maximum. Upload and download loss and background throughput stay separate from each other and from model metrics.'],
    ['kernel.jitter.details', '查看各方向 UDP jitter', 'View UDP jitter by direction'],
    ['kernel.jitter.note', '這裡使用 iperf3 報告的 jitter；與上方佇列模型的定義不同，請分別解讀。', 'These are iperf3 jitter values. Their definition differs from the queue model above; interpret them separately.'],
    ['kernel.jitter.caption', '各核心策略的上傳與下載 UDP jitter', 'Upload and download UDP jitter for each kernel policy'],
    ['kernel.up.jitter', '會議上傳 jitter', 'Meeting upload jitter'],
    ['kernel.down.jitter', '會議下載 jitter', 'Meeting download jitter'],
    ['history.title', '過去的實驗', 'Past experiments'],
    ['history.refresh', '重新整理 ↻', 'Refresh ↻'],
    ['history.reading', '正在讀取實驗紀錄…', 'Loading experiment history…'],
    ['footer.note', '從共享生活的問題出發，讓每次改善都有證據。', 'Start with a shared-home problem. Measure every improvement.'],
    ['footer.local', '本機實驗 · v1', 'Local lab · v1'],
    ['aria.project', '專案資訊', 'Project information'],
    ['aria.home', '同住首頁', 'NetTogether home'],
    ['aria.navigation', '頁面導覽', 'Page navigation'],
    ['aria.overview', '會議模式與模擬拓樸', 'Meeting mode and simulated topology'],
    ['aria.topology', '我的電腦與室友電腦共用一個模擬路由器，經過上下行頻寬瓶頸連到虛擬伺服器', 'My computer and a roommate’s computer share a simulated router and upload/download bottlenecks leading to a virtual server'],
    ['aria.progress', '實驗進度', 'Experiment progress'],
    ['aria.results', '實驗結果', 'Experiment results'],
  ];
  const byKey = new Map(catalogue.map(([key, zh, en]) => [key, { zh, en }]));
  const bySource = new Map(catalogue.map(([key, zh, en]) => [zh, { key, en }]));
  const fromEnglish = new Map(catalogue.map(([, zh, en]) => [en, zh]));
  let language = 'zh-Hant';
  let translatingDynamic = false;
  try { if (localStorage.getItem(STORAGE_KEY) === 'en') language = 'en'; } catch { /* Storage may be unavailable; keep the local default. */ }

  function translateText(text) {
    if (typeof text !== 'string') return text;
    if (!translatingDynamic && typeof window.RoomFlowDynamicTranslate === 'function') {
      try {
        translatingDynamic = true;
        const translated = window.RoomFlowDynamicTranslate(text, language);
        if (typeof translated === 'string' && translated !== text) return translated;
      } finally { translatingDynamic = false; }
    }
    const dynamic = window.RoomFlowDynamicTranslations || {};
    const dynamicEntries = dynamic instanceof Map ? [...dynamic] : Object.entries(dynamic);
    if (language === 'en') {
      const dynamicValue = dynamic instanceof Map ? dynamic.get(text) : Object.prototype.hasOwnProperty.call(dynamic, text) ? dynamic[text] : undefined;
      return typeof dynamicValue === 'string' ? dynamicValue : (bySource.get(text)?.en ?? text);
    }
    for (const [zh, en] of dynamicEntries) if (en === text) return zh;
    return fromEnglish.get(text) ?? text;
  }

  function t(key, params = {}) {
    const entry = byKey.get(key);
    const translated = entry ? (language === 'en' ? translateText(entry.zh) : entry.zh) : translateText(key);
    return String(translated).replace(/\{(\w+)\}/g, (match, name) => Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match);
  }

  function bindStaticContent() {
    const nodes = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (!node.parentElement || node.parentElement.closest('script,style,code,pre,[data-i18n-ignore]')) continue;
      const source = node.textContent.trim();
      const entry = bySource.get(source);
      if (entry) nodes.push({ node, source, key: entry.key });
    }
    for (const { node: textNode, key } of nodes) {
      const parent = textNode.parentElement;
      if (!parent) continue;
      if (parent.tagName === 'OPTION') {
        parent.dataset.i18n = key;
        continue;
      }
      const span = document.createElement('span');
      span.className = 'i18n-text';
      span.dataset.i18n = key;
      // Keep surrounding HTML whitespace independent of language-specific copy.
      const original = textNode.textContent;
      const leading = original.match(/^\s*/)[0];
      const trailing = original.match(/\s*$/)[0];
      const fragment = document.createDocumentFragment();
      if (leading) fragment.append(document.createTextNode(leading));
      fragment.append(span);
      if (trailing) fragment.append(document.createTextNode(trailing));
      textNode.replaceWith(fragment);
    }
    for (const element of document.querySelectorAll('[aria-label],[title],[placeholder]')) {
      for (const attribute of ['aria-label', 'title', 'placeholder']) {
        const source = element.getAttribute(attribute);
        const entry = bySource.get(source);
        if (entry) element.setAttribute(`data-i18n-${attribute}`, entry.key);
      }
    }
  }

  function setLanguage(nextLanguage) {
    language = nextLanguage === 'en' ? 'en' : 'zh-Hant';
    document.documentElement.lang = language;
    document.title = t('page.title');
    try { localStorage.setItem(STORAGE_KEY, language); } catch { /* The switch still works for this page. */ }
    for (const element of document.querySelectorAll('[data-i18n]')) element.textContent = t(element.dataset.i18n);
    for (const attribute of ['aria-label', 'title', 'placeholder']) {
      for (const element of document.querySelectorAll(`[data-i18n-${attribute}]`)) element.setAttribute(attribute, t(element.getAttribute(`data-i18n-${attribute}`)));
    }
    const selector = document.getElementById('ui-language');
    if (selector) selector.value = language;
    document.dispatchEvent(new CustomEvent('roomflow:languagechange', { detail: { language, locale: language === 'en' ? 'en-US' : 'zh-TW' } }));
  }

  window.RoomFlowI18n = Object.freeze({
    t,
    translateText,
    setLanguage,
    get language() { return language; },
    get locale() { return language === 'en' ? 'en-US' : 'zh-TW'; },
  });

  function initialize() {
    bindStaticContent();
    document.getElementById('ui-language')?.addEventListener('change', (event) => setLanguage(event.target.value));
    setLanguage(language);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
  else initialize();
})();
