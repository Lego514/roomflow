'use strict';

(() => {
  const root = document.getElementById('observations');
  if (!root) return;
  const offline = Object.prototype.hasOwnProperty.call(window, 'ROOMFLOW_OFFLINE_DATA');
  const offlineSources = offline && window.ROOMFLOW_OFFLINE_SOURCES && typeof window.ROOMFLOW_OFFLINE_SOURCES === 'object' ? window.ROOMFLOW_OFFLINE_SOURCES : null;
  const bundledDrills = offlineSources && ['delay','loss','dns'].filter(key => offlineSources[`drill-${key}`]);
  const copy = {
    eyebrow: ['HOME NETWORK / OBSERVATION LOG', 'HOME NETWORK / OBSERVATION LOG'],
    title: ['每次異常，都有一段可追查的紀錄。', 'A record for every network incident.'],
    description: ['用保存的量測看異常何時開始、影響哪些探測，以及何時恢復。', 'See when an anomaly started, which probes were affected, and how recovery was recorded.'],
    source: ['資料來源', 'Evidence source'], demo: ['去識別化居家歷史', 'De-identified home history'], local: ['本機量測紀錄', 'Local measurement history'], drill: ['隔離故障演練', 'Isolated fault drill'],
    scenario: ['演練情境', 'Drill scenario'], delay: ['延遲增加', 'Added latency'], loss: ['探測丟失', 'Probe loss'], dns: ['DNS 無回應', 'DNS silence'],
    refresh: ['重新讀取', 'Refresh'], loading: ['正在讀取量測與事件紀錄…', 'Loading observations and incident records…'],
    error: ['無法讀取資料。尚未取得有效的量測，請重新讀取。', 'Evidence could not be loaded. No valid measurements are displayed; try refreshing.'],
    empty: ['這個來源還沒有量測紀錄。沒有資料不能判定網路故障或正常。', 'This source has no measurements yet. Missing data establishes neither failure nor health.'],
    collect: ['先用 python -m homenet dashboard 重新匯出現有紀錄；要新增實際探測，請用 python -m homenet check。', 'Rebuild existing history with python -m homenet dashboard. To collect a new network sample, run python -m homenet check.'],
    historical: ['歷史快照', 'HISTORICAL SNAPSHOT'], stale: ['資料已過期', 'STALE OBSERVATIONS'], current: ['近期採樣', 'RECENT SAMPLE'], lab: ['隔離 LAB 紀錄', 'ISOLATED LAB RECORD'], nodata: ['尚無資料', 'NO OBSERVATIONS'],
    historicalNote: ['這是保存的歷史證據，不代表現在的網路狀態；快照內的未結案事件也不代表現在仍異常。', 'Saved historical evidence, not the network’s present condition. An open incident in this snapshot does not establish an ongoing problem today.'],
    staleNote: ['最近一次採樣已超過時效。可能是量測停止或電腦休眠；不會因缺少資料自動判定故障或結案。', 'The last sample is outside the freshness window. Collection may have stopped or the computer may be asleep; missing data neither opens nor resolves an incident.'],
    currentNote: ['顯示本機已保存的最近採樣；此頁只讀取紀錄，不會啟動網路探測。', 'The most recent saved local sample. This page reads records and does not start network probes.'],
    labNote: ['隔離 Linux 拓樸內注入已知故障後保存的探測，不代表居家連線或實際通話品質。', 'Saved probes from known faults inside an isolated Linux topology; not home connectivity or real call quality.'],
    clockSkew: ['採樣時間在讀取時間之後，無法確認時效；請先核對採樣端時鐘。', 'The sample timestamp is in the future; freshness cannot be established. Check the collector clock.'],
    truncated: ['圖表只顯示最近 {shown} / {total} 筆採樣；事件清單仍依完整紀錄重播。', 'The chart shows the latest {shown} of {total} samples; incidents are replayed from the complete history.'],
    period: ['觀察期間', 'Observation window'], latest: ['最近採樣', 'Latest sample'], noTime: ['尚無採樣時間', 'No sample timestamp'],
    gateway: ['Gateway 延遲', 'Gateway latency'], internet: ['外部 TCP 延遲', 'External TCP latency'], dnsMetric: ['DNS 延遲', 'DNS latency'], failures: ['未成功探測', 'Unsuccessful probes'],
    unknown: ['資料不足', 'Insufficient data'], ok: ['本次未觸發門檻', 'No threshold crossed in sample'], degraded: ['本次觸發異常門檻', 'Threshold crossed in sample'],
    p50: ['p50', 'p50'], p95: ['p95', 'p95'], noAttempts: ['沒有有效嘗試次數', 'No attempted-probe count'], failedOf: ['{failed} / {attempts} 次嘗試', '{failed} / {attempts} attempts'],
    failureNote: ['所有探測合計；不是連線停機率', 'Across all probes; not network downtime'],
    chart: ['延遲與事件，放在同一條時間線。', 'Latency and incidents, on one timeline.'], chartDesc: ['每次採樣的 p95；陰影為事件持續區間。', 'Per-sample p95 latency; shaded areas mark incident windows.'],
    chartAccess: ['Gateway 與外部 TCP 延遲歷史。缺少量測與過長採樣間隔保留斷線，事件詳情可用下方按鈕查看。', 'Gateway and external TCP latency history. Missing measurements and long sampling gaps break the lines. Use the incident buttons below to inspect details.'],
    linearScale: ['線性刻度', 'Linear scale'], logScale: ['對數刻度 (1 + ms)', 'Log scale (1 + ms)'], scaleSwitch: ['切換圖表刻度', 'Switch chart scale'],
    chartNote: ['缺值不補成 0；長時間未採樣不連線。卡片 p50 是可用目標 p50 的平均，p95 是目標 p95 的最大值，不是合併探測的百分位數。Gateway 與 TCP 的絕對值不直接比較。', 'Missing values and long sampling gaps break the lines. Card p50 is the mean of available target p50 values; p95 is the largest target p95, not a pooled percentile. Gateway and TCP values are not directly comparable.'],
    noChart: ['這個來源沒有可繪製的 Gateway 或外部延遲數值。', 'No gateway or external latency values are available to plot.'], eventRegion: ['事件區間', 'Incident window'],
    timeline: ['事件紀錄', 'Incident log'], selectIncident: ['選擇一個事件，檢視證據與排查步驟。', 'Select an incident to inspect its evidence and next checks.'],
    noIncidents: ['這段紀錄沒有達到連續異常門檻的事件。這不等於期間內所有探測都正常。', 'No incident met the consecutive-anomaly rule in this window. This does not establish that every probe was normal.'],
    detail: ['事件詳情', 'Incident detail'], resolved: ['已恢復', 'Recovered'], open: ['快照內未結案', 'Open in snapshot'], openCurrent: ['尚未恢復', 'Awaiting recovery'],
    began: ['首筆異常', 'First abnormal sample'], opened: ['確認建立事件', 'Incident confirmed'], recovered: ['確認恢復', 'Recovery confirmed'], lastSeen: ['最後觀察', 'Last observed'], duration: ['觀察持續時間', 'Observed duration'],
    layers: ['受影響探測', 'Affected probes'], observations: ['觀察到什麼', 'What was observed'], unknowns: ['還不能確定什麼', 'What remains unknown'], nextChecks: ['下一步查什麼', 'What to check next'],
    noDetails: ['未提供；請回查原始採樣。', 'Not provided; inspect the raw samples.'],
    evidenceGaps: ['採樣空窗', 'Evidence gaps'], gapNote: ['{count} 段缺少證據；持續時間已扣除空窗，不代表連續停機時間。', '{count} gaps in evidence; the duration excludes gaps and is not proven continuous outage time.'],
    durationNote: ['持續時間是有證據的觀察區間，包含確認恢復的採樣；不是連續停機時間。', 'Duration is the observed monitoring interval, including recovery-confirmation samples; not continuous outage time.'],
    transitions: ['{count} 筆狀態轉換；同一事件不重複建立告警。', '{count} state transitions; repeated abnormal samples do not create duplicate opening alerts.'],
    policy: ['事件規則', 'Incident policy'], policyText: ['連續 {open} 次異常才建立事件，連續 {recover} 次完整正常才結案。超過 {gap} 分鐘的間隔重設連續計數；缺少量測不能當作恢復。', 'Open after {open} consecutive abnormal samples; resolve after {recover} complete normal samples. Gaps over {gap} minutes reset streaks; missing probes cannot count as recovery.'],
    sourceNotes: ['資料備註', 'Evidence notes'], modelNext: ['下方為另一個獨立的佇列模型實驗室', 'A separate queue-model lab follows below'],
    evidenceDetails: ['證據詳情', 'Evidence details'], nav: ['量測紀錄', 'Observations'],
    clock: ['所有日期以 UTC 顯示', 'All timestamps are UTC'], minute: ['分', 'm'], hour: ['小時', 'h'], second: ['秒', 's'], day: ['天', 'd'],
    service: ['服務 TCP', 'Service TCP'], dnsLayer: ['DNS 探測', 'DNS probes'], incidentCount: ['{count} 個事件', '{count} incidents'], incidentSingle: ['1 個事件', '1 incident'],
    measuredEvidence: ['事件實測數字', 'Measured incident evidence'], evidenceScope: ['首筆至最後一筆異常：{start} → {end}；{count} 筆採樣。恢復確認不計入下表。', 'First through last abnormal sample: {start} → {end}; {count} samples. Recovery confirmation is excluded below.'],
    noEvidence: ['此舊版事件未保存數字證據；無法從截短時間線推算完整事件，請重新匯出原始紀錄。', 'This older incident has no numerical evidence. A truncated timeline cannot reconstruct the whole event; re-export the original records.'],
    evidenceLayer: ['探測層', 'Probe layer'], peakLatency: ['最高採樣 p95 / 門檻', 'Peak sample p95 / threshold'], evidenceFailures: ['未成功 / 嘗試', 'Unsuccessful / attempted'], sampleOutcomes: ['採樣狀態對照', 'Sample outcomes'],
    latencyBound: ['門檻 > {value} ms', 'Threshold > {value} ms'], failureBound: ['門檻 > {value}%', 'Threshold > {value}%'],
    peakAt: ['出現於 {at}', 'Recorded at {at}'], partialCounts: ['部分次數：{known}/{total} 筆有次數；{missing} 筆缺少。', 'Partial counts: {known}/{total} samples counted; {missing} missing.'],
    completeCounts: ['{count} 筆次數完整', 'Counts complete for {count} samples'], layerOutcomes: ['正常 {healthy} · 異常 {abnormal} · 未知 {unknown}', 'Healthy {healthy} · abnormal {abnormal} · unknown {unknown}'],
    breaches: ['延遲超標 {latency} · 未成功比例超標 {failure}', 'Latency breaches {latency} · failure-ratio breaches {failure}'],
    evidenceSemantics: ['最高值是每筆採樣 p95 的最大值，不是合併探測的 p95。門檻逐一套用至各目標；表中未成功比例依已知嘗試次數加權，因此合計比例未超標時，仍可能有個別目標超標。各層可對照同期正常／異常／未知次數；不能據此確定根因。部分次數的比例僅適用於已知嘗試；— 代表資料不足。', 'Peak is the maximum per-sample p95, not a pooled percentile. Thresholds apply to individual targets; the reported failure ratio is weighted across known attempts, so a target can breach even when the combined ratio does not. Compare healthy, abnormal and unknown samples across layers; this does not establish a root cause. Partial-count ratios cover known attempts only; — means insufficient data.'],
    focusedWindow: ['事件前後視窗', 'Incident context window'], fullWindow: ['完整可用歷史', 'Full available history'], fullHistory: ['完整歷史', 'Full history'],
    contextClipped: ['前後脈絡超出已保存的時間線；僅顯示可用部分，未補造資料。', 'Context extends beyond the saved timeline; only available evidence is shown. No history is invented.'],
    focusUnavailable: ['這個事件的區間不在已保存的圖表採樣內。請重新匯出涵蓋事件的時間線，或查看完整可用歷史。', 'This incident window has no samples in the saved chart timeline. Re-export a timeline covering the incident, or return to full available history.'],
    replayTitle: ['逐筆回放故障演練', 'Replay the saved fault drill'], replayNote: ['回放已保存採樣，不會發起新探測。卡片、圖表與事件只顯示目前步驟已知的證據。', 'Saved replay; no new probes. Cards, chart and incidents show only evidence available at this step.'],
    play: ['播放', 'Play'], pause: ['暫停', 'Pause'], previous: ['上一步', 'Previous'], next: ['下一步', 'Next'], restart: ['從頭開始', 'Restart'],
    replayPosition: ['採樣 {current} / {total}', 'Sample {current} / {total}'], replayStatus: ['事件引擎狀態', 'Incident-engine state'],
    stageNormal: ['正常採樣', 'Normal sample'], stagePending: ['異常待確認', 'Pending confirmation'], stageOpen: ['事件已開案', 'Incident open'], stageRecovering: ['恢復確認中（仍未結案）', 'Confirming recovery (still open)'], stageResolved: ['恢復已確認，事件結案', 'Recovery confirmed; incident resolved'], stageUnknown: ['證據不足', 'Insufficient evidence'],
    pendingStreaks: ['連續異常 {abnormal} / {open} · 連續恢復 {recovery} / {recover}', 'Abnormal streak {abnormal} / {open} · recovery streak {recovery} / {recover}'],
    replayUnavailable: ['這份演練沒有可用的逐筆狀態；顯示完整保存快照，請重新匯出以啟用回放。', 'No step-by-step state is available for this drill. Showing the complete saved snapshot; re-export to enable replay.'],
  };
  const refs = {};
  const evidenceTranslations = {
    'De-identified saved home observations': '去識別化的居家歷史量測',
    'Local saved observations': '本機保存的觀察紀錄',
    'Read-only SQLite snapshot of previously saved completed checks; no new probes were run.': '由已保存的完整採樣唯讀匯出，沒有新增探測。',
    'Only per-layer aggregates are published; endpoint addresses, SSID, MAC and raw errors are excluded.': '僅保留各層彙總值；不含目標位址、SSID、MAC 或原始錯誤。',
    'Incident policy replays historical observations; local transition records are not historical messages that were actually sent.': '事件規則重播歷史資料；本機轉換紀錄不代表當時真的傳送過通知。',
    'Checks are sequential samples; conditions between checks were not continuously observed.': '這些是離散採樣，兩次採樣之間的網路狀態沒有連續觀察。',
    'Selected probes do not establish a root cause, an ISP fault, a service-wide outage, or real call quality.': '這些探測不足以確定根因、ISP 故障、整體服務中斷或實際通話品質。',
    'Collection gaps or incomplete checks interrupt evidence; missing time is excluded from observed duration and does not prove recovery.': '採樣空窗或不完整探測會中斷證據；缺少的時間不計入觀察持續時間，也不能證明已恢復。',
    'Compare gateway echo responses over wired and Wi-Fi paths; check host and gateway behavior.': '比較有線與 Wi-Fi 的 Gateway 回應，並檢查本機與 Gateway 行為。',
    'Compare multiple public TCP targets and a wired path before assigning an upstream cause.': '比較多個外部 TCP 目標與有線連線，再評估是否來自上游。',
    'Compare resolver responses and distinguish name lookup failure from IP connectivity.': '比較不同 DNS 解析器的回應，區分名稱解析失敗與 IP 連線問題。',
    'Compare service TCP connection results with DNS and public-IP probes; verify the application separately.': '將服務 TCP 連線結果與 DNS、外部 IP 探測對照；應用程式仍需另外驗證。',
  };
  let language = window.RoomFlowI18n?.language || (document.documentElement.lang === 'zh-Hant' ? 'zh-Hant' : 'en');
  if (!window.RoomFlowI18n) {
    try { const stored = localStorage.getItem('roomflow-language'); if (['en', 'zh-Hant'].includes(stored)) language = stored; } catch { /* Optional storage. */ }
  }
  let payload = null;
  // Homepage history opens the actual local record; portable demos keep their
  // fixed historical source, and arbitrary URL values are never file paths.
  let source = !offline && /(?:^\?|&)source=local(?:&|$)/.test(window.location?.search ?? '') ? 'local' : 'demo';
  let scenario = 'delay';
  let selectedIncident = null;
  let request = null;
  let errorState = false;
  let chartScale = 'auto';
  let fullPayload = null;
  let focusedIncident = null;
  let replayIndex = null;
  let replayTimer = null;
  let playing = false;
  const t = (key, params = {}) => (copy[key]?.[language === 'en' ? 1 : 0] || key).replace(/\{(\w+)\}/g, (match, name) => Object.hasOwn(params, name) ? String(params[name]) : match);
  function evidenceText(value) {
    if (language === 'en' || typeof value !== 'string') return value;
    if (Object.hasOwn(evidenceTranslations,value)) return evidenceTranslations[value];
    const observation = /^(gateway|internet|dns|service): selected probes exceeded the configured latency or unsuccessful-probe threshold\.$/.exec(value);
    return observation ? `${t(observation[1] === 'dns' ? 'dnsLayer' : observation[1])}：選定探測超過設定的延遲或未成功比例門檻。` : value;
  }
  const list = value => Array.isArray(value) ? value : [];
  const finite = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
  const metric = value => finite(value) ? new Intl.NumberFormat(language === 'en' ? 'en-US' : 'zh-TW', {maximumFractionDigits:1}).format(value) : '—';
  const stamp = value => {
    if (value === null || value === undefined || value === '') return null;
    const ms = new Date(value).getTime(); return Number.isFinite(ms) ? ms : null;
  };
  function time(value, compact = false, shortWindow = false) {
    const ms = stamp(value);
    if (ms === null) return t('noTime');
    return new Intl.DateTimeFormat(language === 'en' ? 'en-GB' : 'zh-TW', {timeZone:'UTC', month:'short', day:'2-digit', ...(compact ? {} : {year:'numeric'}), hour:'2-digit', minute:'2-digit', ...(!compact || shortWindow ? {second:'2-digit'} : {}), hourCycle:'h23'}).format(ms) + ' UTC';
  }
  function duration(value) {
    if (!finite(value)) return '—';
    let seconds = Math.round(value);
    const units = [[86400, 'day'], [3600, 'hour'], [60, 'minute']];
    const parts = [];
    for (const [size, key] of units) { const count = Math.floor(seconds / size); if (count) parts.push(`${count}${t(key)}`); seconds %= size; }
    if (!parts.length) parts.push(`${seconds}${t('second')}`);
    return parts.slice(0, 2).join(' ');
  }
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function svg(tag, attributes = {}, text) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function setFlash(key, error = false) {
    refs.flash.replaceChildren();
    refs.flash.hidden = !key;
    refs.flash.setAttribute('role', error ? 'alert' : 'status');
    if (key) refs.flash.append(el('p', '', t(key)));
    if (key === 'empty' && source === 'local') refs.flash.append(el('code', '', t('collect')));
  }
  function replayFrames() {
    if (fullPayload?.source?.kind !== 'lab-drill' || fullPayload.timelineTruncated || fullPayload.replay?.available === false) return [];
    const frames = list(fullPayload.replay?.frames);
    return frames.length && frames.every(frame => Number.isInteger(frame.sampleCount) && frame.sampleCount >= 0 && frame.sampleCount <= list(fullPayload.timeline).length && Array.isArray(frame.incidents) && Array.isArray(frame.notifications)) ? frames : [];
  }
  function stopReplay() {
    if (replayTimer !== null) clearTimeout(replayTimer);
    replayTimer = null; playing = false;
  }
  function resetView() {
    stopReplay(); replayIndex = null; selectedIncident = null; focusedIncident = null;
  }
  function acceptPayload(data) {
    fullPayload = data;
    replayIndex = replayFrames().length ? 0 : null;
  }
  function displayedPayload() {
    const frame = replayFrames()[replayIndex];
    if (!frame) return fullPayload;
    const prefix = fullPayload.timeline.slice(0, frame.sampleCount);
    // Never mix a saved prefix with the final event, metrics or shaded windows.
    // Frames come from the Python incident engine; the UI does not infer state.
    return {...fullPayload, timeline:prefix, latest:prefix.at(-1) || null,
      timelineTotal:prefix.length, timelineTruncated:false, incidents:frame.incidents, notifications:frame.notifications,
      source:{...fullPayload.source, windowStart:prefix[0]?.at || null, windowEnd:frame.at},
      monitor:{...fullPayload.monitor, lastObservedAt:frame.at,
        pendingAbnormalChecks:frame.pendingAbnormalChecks, pendingRecoveryChecks:frame.pendingRecoveryChecks}};
  }
  function setReplayFrame(index) {
    const frames = replayFrames();
    if (!frames.length) return;
    replayIndex = Math.max(0, Math.min(frames.length - 1, index));
    render();
  }
  function scheduleReplay() {
    if (!playing || replayTimer !== null) return;
    replayTimer = setTimeout(() => {
      replayTimer = null;
      const frames = replayFrames();
      if (!playing || replayIndex === null || replayIndex >= frames.length - 1) { stopReplay(); render(); return; }
      replayIndex += 1;
      if (replayIndex === frames.length - 1) playing = false;
      render(); scheduleReplay();
    }, 1000);
  }
  function replayControls() {
    if (fullPayload?.source?.kind !== 'lab-drill') return null;
    const card = el('section', 'rf-card rf-replay'); card.setAttribute('aria-labelledby', 'rf-replay-title');
    const heading = cardHeading(t('replayTitle'), t('replayNote')); heading.querySelector('h3').id = 'rf-replay-title'; card.append(heading);
    const frames = replayFrames(), frame = frames[replayIndex];
    if (!frame) { card.append(el('p', 'rf-chart-note', t('replayUnavailable'))); return card; }
    const state = el('div', 'rf-replay-state'); state.setAttribute('aria-live','polite');
    const stageKey = {normal:'stageNormal',pending:'stagePending',open:'stageOpen',recovering:'stageRecovering',resolved:'stageResolved',unknown:'stageUnknown'}[frame.stage] || 'stageUnknown';
    state.append(el('strong', 'rf-replay-status', `${t('replayStatus')}: ${t(stageKey)}`), el('span', 'rf-replay-position', t('replayPosition',{current:frame.sampleCount,total:fullPayload.replay.totalSamples ?? fullPayload.timeline.length})));
    state.dataset.stage = frame.stage; state.dataset.sampleCount = String(frame.sampleCount);
    card.append(state, el('p', 'rf-chart-note', `${time(frame.at)} · ${t('pendingStreaks',{abnormal:frame.pendingAbnormalChecks ?? '—',open:payload.policy?.openAfter ?? 3,recovery:frame.pendingRecoveryChecks ?? '—',recover:payload.policy?.recoverAfter ?? 2})}`));
    const controls = el('div', 'rf-replay-controls');
    const action = (key, callback, disabled = false) => { const button = el('button', `rf-action rf-replay-${key}`, t(key)); button.id = `rf-replay-${key}`; button.type = 'button'; button.disabled = disabled; button.addEventListener('click',callback); controls.append(button); return button; };
    action('restart', () => { stopReplay(); selectedIncident = null; focusedIncident = null; setReplayFrame(0); });
    action('previous', () => { stopReplay(); setReplayFrame(replayIndex - 1); }, replayIndex === 0);
    const play = action(playing ? 'pause' : 'play', () => {
      if (playing) stopReplay();
      else { if (replayIndex >= frames.length - 1) { replayIndex = 0; selectedIncident = null; focusedIncident = null; } playing = true; scheduleReplay(); }
      render();
    });
    play.setAttribute('aria-pressed', String(playing));
    action('next', () => { stopReplay(); setReplayFrame(replayIndex + 1); }, replayIndex >= frames.length - 1);
    card.append(controls); return card;
  }
  function build() {
    const navLabel = document.querySelector('#rf-nav-observations .rf-nav-label');
    if (navLabel) navLabel.textContent = t('nav');
    root.setAttribute('aria-labelledby', 'rf-title');
    const heading = el('div', 'rf-heading');
    const intro = el('div');
    intro.append(el('p', 'rf-eyebrow', t('eyebrow')));
    const title = el('h2', '', t('title')); title.id = 'rf-title'; intro.append(title, el('p', '', t('description')));
    const tools = el('div', 'rf-tools');
    const sourceField = el('div', 'rf-field');
    const label = el('label', '', t('source')); label.htmlFor = 'rf-source';
    const select = el('select'); select.id = 'rf-source';
    const availableSources = offline ? ['demo', ...(bundledDrills?.length ? ['drill'] : [])] : ['demo','local','drill'];
    for (const value of availableSources) { const option = el('option', '', t(value)); option.value = value; select.append(option); }
    select.value = source;
    select.addEventListener('change', () => { source = select.value; selectedIncident = null; refs.scenarioField.hidden = source !== 'drill'; load(); });
    sourceField.append(label, select); tools.append(sourceField); refs.sourceField = sourceField;
    const scenarioField = el('div', 'rf-field rf-drill-field'); scenarioField.hidden = source !== 'drill';
    const scenarioLabel = el('label', '', t('scenario')); scenarioLabel.htmlFor = 'rf-scenario';
    const scenarioSelect = el('select'); scenarioSelect.id = 'rf-scenario';
    for (const value of offline && bundledDrills?.length ? bundledDrills : ['delay','loss','dns']) { const option = el('option', '', t(value)); option.value = value; scenarioSelect.append(option); }
    scenarioSelect.value = scenario; scenarioSelect.addEventListener('change', () => { scenario = scenarioSelect.value; selectedIncident = null; load(); });
    scenarioField.append(scenarioLabel, scenarioSelect); tools.append(scenarioField); refs.scenarioField = scenarioField;
    const refresh = el('button', 'rf-action rf-refresh', `↻ ${t('refresh')}`); refresh.type = 'button'; refresh.addEventListener('click', load); tools.append(refresh); refs.refresh = refresh;
    refresh.disabled = root.getAttribute('aria-busy') === 'true';
    if (offline) { sourceField.hidden = !bundledDrills?.length; scenarioField.hidden = source !== 'drill'; refresh.hidden = true; }
    heading.append(intro, tools);
    refs.provenance = el('div', 'rf-provenance');
    refs.flash = el('div', 'rf-flash'); refs.flash.setAttribute('aria-live', 'polite'); refs.flash.hidden = true;
    refs.content = el('div');
    root.replaceChildren(heading, refs.provenance, refs.flash, refs.content);
    if (!document.body.classList.contains('rf-standalone')) root.append(el('p', 'rf-next-section', t('modelNext')));
  }
  function provenance() {
    const kind = payload?.source?.kind;
    let state = payload?.monitor?.status || 'empty';
    if (kind === 'historical-demo') state = 'historical';
    if (kind === 'lab-drill') state = 'lab';
    if (offline && kind !== 'lab-drill') state = 'historical';
    if (!payload?.latest && !['historical', 'lab'].includes(state)) state = 'empty';
    // Only recent LOCAL observations may receive the green freshness treatment.
    if (state === 'current' && kind !== 'local-history') state = 'historical';
    const labelKey = {historical:'historical', stale:'stale', current:'current', lab:'lab', empty:'nodata'}[state] || 'nodata';
    refs.provenance.dataset.state = state;
    const body = el('div');
    body.append(el('strong', '', evidenceText(payload?.source?.label) || t(source)));
    body.append(el('p', '', t({historical:'historicalNote', stale:'staleNote', current:'currentNote', lab:'labNote'}[state] || 'empty')));
    if (replayFrames()[replayIndex]) body.append(el('p', 'rf-source-note', t('replayNote')));
    if (payload?.latest) body.append(el('p', 'rf-source-note', `${t('latest')}: ${time(payload.latest.at)} · ${t('clock')}`));
    if (payload?.source?.windowStart || payload?.source?.windowEnd) body.append(el('p', 'rf-source-note', `${t('period')}: ${time(payload.source.windowStart)} → ${time(payload.source.windowEnd)}`));
    const notes = list(payload?.source?.notes).filter(note => typeof note === 'string');
    if (notes.length) {
      const details = el('details', 'rf-evidence-details'); details.append(el('summary', '', t('evidenceDetails')));
      for (const note of notes) details.append(el('p', 'rf-source-note', evidenceText(note)));
      body.append(details);
    }
    if (payload?.monitor?.clockSkew) body.append(el('p', 'rf-source-note', t('clockSkew')));
    if (payload?.timelineTruncated) body.append(el('p', 'rf-source-note', t('truncated',{shown:list(payload.timeline).length,total:payload.timelineTotal ?? '—'})));
    refs.provenance.replaceChildren(el('span', 'rf-source-badge', t(labelKey)), body);
  }
  function statusLabel(status) { return t(['ok', 'degraded'].includes(status) ? status : 'unknown'); }
  function metrics() {
    const grid = el('div', 'rf-metrics');
    const layers = payload.latest?.layers || {};
    for (const [name, icon] of [['gateway', '⌁'], ['internet', '↗'], ['dns', '◇']]) {
      const sample = layers[name] || {};
      const card = el('article', 'rf-metric'); card.dataset.status = sample.status || 'unknown';
      const label = el('div', 'rf-metric-label', t(name === 'dns' ? 'dnsMetric' : name)); label.append(el('span', 'rf-metric-icon', icon));
      const value = el('strong', 'rf-metric-value', metric(sample.p50Ms)); value.append(el('small', '', 'ms'));
      card.append(label, value, el('p', '', `${t('p50')} · ${t('p95')} ${metric(sample.p95Ms)} ms`), el('p', 'rf-metric-state', statusLabel(sample.status))); grid.append(card);
    }
    const total = Object.values(layers).reduce((counts, sample) => {
      if (finite(sample?.attempts) && finite(sample?.failed)) { counts.attempts += sample.attempts; counts.failed += sample.failed; }
      return counts;
    }, {attempts:0, failed:0});
    const card = el('article', 'rf-metric'); card.dataset.status = total.attempts ? (total.failed ? 'degraded' : 'ok') : 'unknown';
    const value = el('strong', 'rf-metric-value', total.attempts ? metric(100 * total.failed / total.attempts) : '—'); value.append(el('small', '', '%'));
    card.append(el('div', 'rf-metric-label', t('failures')), value, el('p', '', total.attempts ? t('failedOf', total) : t('noAttempts')), el('p', 'rf-metric-state', t('failureNote'))); grid.append(card);
    return grid;
  }
  function cardHeading(title, description, kicker) {
    const head = el('div', 'rf-card-head'); const text = el('div'); text.append(el('h3', '', title));
    if (description) text.append(el('p', '', description)); head.append(text);
    if (kicker) head.append(el('span', 'rf-card-kicker', kicker)); return head;
  }
  function chartWindow(history) {
    const availableStart = stamp(history[0]?.at), availableEnd = stamp(history.at(-1)?.at);
    const incident = list(payload.incidents).find(item => item.id === focusedIncident);
    if (!incident || availableStart === null || availableEnd === null) return {timeline:history,start:availableStart,end:availableEnd,focused:false,clipped:false};
    const a = stamp(incident.startedAt), b = stamp(incident.resolvedAt || incident.lastObservedAt || incident.lastAbnormalAt || incident.openedAt);
    if (a === null || b === null) return {timeline:history,start:availableStart,end:availableEnd,focused:false,clipped:false};
    const maxGap = (payload.policy?.maxGapSeconds ?? 900) * 1000;
    const gaps = history.slice(1).map((row,index) => stamp(row.at)-stamp(history[index].at)).filter(value => value > 0 && value <= maxGap).sort((x,y) => x-y);
    // Two typical sample intervals of context, bounded between 2 s and 10 min.
    const padding = Math.max(2000, Math.min(600000, 2 * (gaps[Math.floor(gaps.length/2)] || 60000)));
    const requestedStart = a-padding, requestedEnd = Math.max(a,b)+padding;
    const start = Math.max(availableStart,requestedStart), end = Math.min(availableEnd,requestedEnd);
    if (start > end) return {timeline:[],start:requestedStart,end:requestedEnd,focused:true,clipped:true};
    return {timeline:history.filter(row => stamp(row.at) >= start && stamp(row.at) <= end), start,end,focused:true,
      clipped:requestedStart < availableStart || requestedEnd > availableEnd, requestedStart,requestedEnd};
  }
  function chart() {
    const card = el('article', 'rf-card');
    const heading = cardHeading(t('chart'), t('chartDesc')); card.append(heading);
    const history = list(payload.timeline).filter(row => stamp(row.at) !== null).slice().sort((a,b) => stamp(a.at) - stamp(b.at));
    const interval = chartWindow(history), timeline = interval.timeline;
    const windowNote = el('p', 'rf-chart-note rf-window-note', `${t(interval.focused ? 'focusedWindow' : 'fullWindow')}: ${time(interval.start)} → ${time(interval.end)}`);
    windowNote.id = 'rf-chart-window'; windowNote.dataset.start = String(interval.start); windowNote.dataset.end = String(interval.end);
    card.append(windowNote);
    if (interval.focused) {
      const reset = el('button', 'rf-action rf-full-history', t('fullHistory')); reset.id = 'rf-full-history'; reset.type = 'button';
      reset.addEventListener('click', () => { focusedIncident = null; render(); refs.content.querySelector('.rf-incident-button[aria-pressed="true"]')?.focus({preventScroll:true}); }); heading.append(reset);
      if (interval.clipped) card.append(el('p','rf-chart-note rf-context-clipped',t('contextClipped')));
    }
    const plottable = (row, key) => row.layers?.[key]?.status !== 'unknown' && finite(row.layers?.[key]?.p95Ms);
    const values = timeline.flatMap(row => ['gateway', 'internet'].filter(key => plottable(row,key)).map(key => row.layers[key].p95Ms));
    if (!timeline.length || !values.length) { card.append(el('p', 'rf-chart-note', t(interval.focused && !timeline.length ? 'focusUnavailable' : 'noChart'))); return card; }
    const frame = el('div', 'rf-chart');
    const w = 900, height = 225, pad = {left:44, right:18, top:15, bottom:30};
    const start = interval.start, end = interval.end;
    const span = end - start || 60000;
    const max = Math.max(10, ...values) * 1.12;
    const ordered = values.slice().sort((a,b) => a-b);
    const median = ordered[Math.floor(ordered.length/2)] || 1;
    const scale = chartScale === 'auto' ? (max > 1000 && max / median > 20 ? 'log' : 'linear') : chartScale;
    const scaleButton = el('button','rf-action rf-scale-button',t(scale === 'log' ? 'logScale' : 'linearScale'));
    scaleButton.type = 'button'; scaleButton.title = t('scaleSwitch');
    scaleButton.setAttribute('aria-label',`${t('scaleSwitch')}: ${t(scale === 'log' ? 'linearScale' : 'logScale')}`);
    scaleButton.setAttribute('aria-pressed',String(scale === 'log'));
    scaleButton.addEventListener('click',() => { chartScale = scale === 'log' ? 'linear' : 'log'; const position = window.scrollY; render(); window.scrollTo({top:position,behavior:'instant'}); refs.content.querySelector('.rf-scale-button')?.focus({preventScroll:true}); });
    heading.append(scaleButton);
    const x = at => pad.left + ((at - start) / span) * (w - pad.left - pad.right);
    const y = value => height - pad.bottom - (scale === 'log' ? Math.log1p(value)/Math.log1p(max) : value/max) * (height - pad.top - pad.bottom);
    const graph = svg('svg', {viewBox:`0 0 ${w} ${height}`, role:'img', 'aria-labelledby':'rf-chart-title rf-chart-desc'});
    graph.append(svg('title', {id:'rf-chart-title'}, t('chart')), svg('desc', {id:'rf-chart-desc'}, `${t('chartAccess')} ${t(scale === 'log' ? 'logScale' : 'linearScale')}`));
    const ticks = scale === 'log' ? [0,10,100,1000,10000,100000].filter(value => value < max).concat(max) : [0,max/3,2*max/3,max];
    for (const value of ticks) {
      graph.append(svg('line', {x1:pad.left, x2:w-pad.right, y1:y(value), y2:y(value), class:'rf-grid-line'}));
      graph.append(svg('text', {x:pad.left-8, y:y(value)+3, 'text-anchor':'end'}, String(Math.round(value))));
    }
    const maxGap = finite(payload.policy?.maxGapSeconds) ? payload.policy.maxGapSeconds * 1000 : 900000;
    const unobservedIntervals = [];
    for (let index = 1; index < timeline.length; index++) {
      const previous = timeline[index-1], current = timeline[index];
      if (previous.status === 'unknown' || current.status === 'unknown' || stamp(current.at)-stamp(previous.at) > maxGap) {
        unobservedIntervals.push({from:previous.at,to:current.at});
      }
    }
    for (const incident of list(payload.incidents)) {
      const a = stamp(incident.startedAt), b = stamp(incident.resolvedAt || incident.lastObservedAt);
      if (a === null || b === null || b < start || a > end) continue;
      let intervals = [[Math.max(start,a), Math.min(end,b)]];
      // Do not shade collection/unknown gaps as a continuous known anomaly.
      // Incomplete-check markers can have from===to. Both adjacent intervals
      // remain unobserved, matching the backend's bounded duration accounting.
      for (const gap of [...list(incident.evidenceGaps), ...unobservedIntervals]) {
        const from = stamp(gap.from), to = stamp(gap.to);
        if (from === null || to === null || to <= from) continue;
        intervals = intervals.flatMap(([left,right]) => to <= left || from >= right ? [[left,right]] : [[left,Math.min(from,right)],[Math.max(to,left),right]].filter(([l,r]) => r > l));
      }
      for (const [left,right] of intervals) if (right > left) graph.append(svg('rect', {x:x(left), y:pad.top, width:x(right)-x(left), height:height-pad.top-pad.bottom, class:'rf-incident-region'}));
    }
    for (const key of ['gateway', 'internet']) {
      let path = '', previous = null;
      for (const row of timeline) {
        const at = stamp(row.at), value = row.layers?.[key]?.p95Ms;
        if (!plottable(row,key)) { previous = null; continue; }
        const continuous = previous !== null && at - previous <= maxGap;
        path += `${continuous ? 'L' : 'M'}${x(at).toFixed(2)},${y(value).toFixed(2)} `;
        // Show isolated measurements too; an unconnected point is still evidence.
        graph.append(svg('circle', {cx:x(at), cy:y(value), r:1.9, fill:key === 'gateway' ? '#538365' : '#607f9b', class:'rf-point'}));
        previous = at;
      }
      graph.append(svg('path', {d:path.trim(), class:`rf-data-line rf-${key}-line`}));
    }
    const timeTicks = start === end ? [[start,'start']] : [[start,'start'],[start+span/2,'middle'],[end,'end']];
    for (const [at, anchor] of timeTicks) graph.append(svg('text', {x:x(at), y:height-7, 'text-anchor':anchor}, time(at, true,span < 120000).replace(' UTC','')));
    frame.append(graph); card.append(frame);
    const legend = el('div', 'rf-chart-legend');
    for (const [key, className] of [['gateway',''],['internet','rf-internet-key'],['eventRegion','rf-incident-key']]) { const item = el('span'); item.append(el('i', className), document.createTextNode(t(key))); legend.append(item); }
    card.append(legend, el('p', 'rf-chart-note', t('chartNote'))); return card;
  }
  function incidentStatus(incident) { return incident.status === 'resolved' ? t('resolved') : t(!offline && payload.monitor?.status === 'current' && payload.source?.kind === 'local-history' ? 'openCurrent' : 'open'); }
  function layerNames(incident) { return list(incident.affectedLayers).map(key => key === 'dns' ? t('dnsLayer') : copy[key] ? t(key) : String(key)).join(' · ') || '—'; }
  function measuredEvidence(incident) {
    const section = el('section', 'rf-measured-evidence'); section.setAttribute('aria-labelledby','rf-evidence-title');
    const title = el('h4','',t('measuredEvidence')); title.id = 'rf-evidence-title'; section.append(title);
    const evidence = incident.evidence;
    if (!evidence || !evidence.layers) { section.append(el('p','rf-chart-note rf-evidence-missing',t('noEvidence'))); return section; }
    const table = el('table','rf-evidence-table');
    const caption = el('caption','',t('evidenceScope',{start:time(evidence.startAt),end:time(evidence.endAt),count:metric(evidence.checkCount)})); table.append(caption);
    const labels = ['evidenceLayer','peakLatency','evidenceFailures','sampleOutcomes'];
    const head = el('thead'), headRow = el('tr');
    for (const key of labels) { const cell = el('th','',t(key)); cell.scope = 'col'; headRow.append(cell); } head.append(headRow); table.append(head);
    const body = el('tbody');
    for (const key of ['gateway','internet','dns','service']) {
      const item = evidence.layers[key] || {}, row = el('tr'); row.dataset.layer = key;
      const name = el('th','',t(key === 'dns' ? 'dnsLayer' : key)); name.scope = 'row'; row.append(name);
      const peak = el('td'); peak.dataset.label = t('peakLatency');
      peak.append(el('strong','',`${metric(item.peakP95Ms)} ms`),el('small','',t('latencyBound',{value:metric(item.latencyThresholdMs)})));
      if (stamp(item.peakP95At) !== null) peak.append(el('small','',t('peakAt',{at:time(item.peakP95At)})));
      const counts = el('td'); counts.dataset.label = t('evidenceFailures');
      const knownCounts = finite(item.attempts) && finite(item.failed);
      counts.append(el('strong','',knownCounts ? `${metric(item.failed)} / ${metric(item.attempts)} (${metric(item.failurePct)}%)` : t('unknown')),
        el('small','',t('failureBound',{value:metric(item.failureThresholdPct)})),
        el('small',item.countsComplete ? '' : 'rf-partial-counts',item.countsComplete ? t('completeCounts',{count:metric(item.countedChecks)}) : t('partialCounts',{known:metric(item.countedChecks),total:metric(evidence.checkCount),missing:metric(item.missingCountChecks)})));
      const outcomes = el('td'); outcomes.dataset.label = t('sampleOutcomes');
      outcomes.append(el('strong','',t('layerOutcomes',{healthy:metric(item.healthyChecks),abnormal:metric(item.abnormalChecks),unknown:metric(item.unknownChecks)})),el('small','',t('breaches',{latency:metric(item.latencyBreaches),failure:metric(item.failureBreaches)})));
      row.append(peak,counts,outcomes); body.append(row);
    }
    table.append(body); section.append(table,el('p','rf-chart-note',t('evidenceSemantics'))); return section;
  }
  function detail(incident) {
    const card = el('article', 'rf-card rf-detail'); card.id = 'rf-incident-detail'; card.setAttribute('aria-labelledby', 'rf-detail-title');
    const head = el('div', 'rf-card-head'); const heading = el('h3', '', t('detail')); heading.id = 'rf-detail-title'; heading.tabIndex = -1; head.append(heading);
    if (!incident) { card.append(head, el('p', 'rf-chart-note', t('selectIncident'))); return card; }
    const state = el('span', 'rf-state', incidentStatus(incident)); state.dataset.status = incident.status; head.append(state); card.append(head);
    const meta = el('dl', 'rf-detail-meta');
    for (const [key, value] of [['began',time(incident.startedAt)], ['opened',time(incident.openedAt)], [incident.resolvedAt ? 'recovered' : 'lastSeen',time(incident.resolvedAt || incident.lastObservedAt)], ['duration',duration(incident.durationSeconds)]]) {
      const item = el('div'); item.append(el('dt', '', t(key)), el('dd', '', value)); meta.append(item);
    }
    card.append(meta);
    const affected = el('p', 'rf-chart-note', `${t('layers')}: ${layerNames(incident)}`); card.append(affected);
    card.append(el('p', 'rf-chart-note', list(incident.evidenceGaps).length ? t('gapNote',{count:incident.evidenceGaps.length}) : t('durationNote')));
    card.append(measuredEvidence(incident));
    for (const key of ['observations', 'unknowns', 'nextChecks']) {
      const section = el('section', 'rf-detail-block'); section.dataset.kind = key;
      section.append(el('h4', '', t(key))); const bullets = el('ul');
      const items = list(incident[key]).filter(value => typeof value === 'string');
      for (const value of items.length ? items : [t('noDetails')]) bullets.append(el('li', '', evidenceText(value))); section.append(bullets); card.append(section);
    }
    card.append(el('p', 'rf-transition-note', `${t('transitions',{count:list(incident.transitions).length})} · ${String(incident.id || '')}`)); return card;
  }
  function workspace() {
    const group = el('div', 'rf-workspace');
    const incidents = list(payload.incidents).slice().sort((a,b) => (stamp(b.startedAt) || 0) - (stamp(a.startedAt) || 0));
    if (!incidents.some(incident => incident.id === selectedIncident)) selectedIncident = incidents[0]?.id || null;
    const log = el('article', 'rf-card'); const head = cardHeading(t('timeline'), t('selectIncident')); head.append(el('span', 'rf-count', incidents.length === 1 ? t('incidentSingle') : t('incidentCount', {count:incidents.length}))); log.append(head);
    if (!incidents.length) log.append(el('p', 'rf-chart-note', t('noIncidents')));
    const entries = el('ol', 'rf-incident-list');
    for (const incident of incidents) {
      const item = el('li'); const button = el('button', 'rf-incident-button'); button.type = 'button'; button.dataset.incidentId = String(incident.id);
      button.setAttribute('aria-pressed', String(incident.id === selectedIncident)); button.setAttribute('aria-controls', 'rf-incident-detail');
      const row = el('span', 'rf-incident-row'); const status = el('span', 'rf-state', incidentStatus(incident)); status.dataset.status = incident.status;
      row.append(el('span', 'rf-incident-date', time(incident.startedAt, true)), status);
      button.append(row, el('span', 'rf-incident-sub', `${layerNames(incident)} · ${duration(incident.durationSeconds)}`));
      button.addEventListener('click', () => {
        selectedIncident = incident.id; focusedIncident = incident.id;
        render();
        refs.content.querySelector('#rf-detail-title')?.focus({preventScroll:true});
      });
      item.append(button); entries.append(item);
    }
    log.append(entries); group.append(log, detail(incidents.find(incident => incident.id === selectedIncident))); return group;
  }
  function render() {
    const activeControl = document.activeElement?.id;
    payload = displayedPayload();
    if (focusedIncident !== null && !list(payload?.incidents).some(item => item.id === focusedIncident)) focusedIncident = null;
    provenance(); refs.content.replaceChildren();
    if (errorState) { setFlash('error', true); return; }
    if (!payload) { setFlash('loading'); return; }
    if (!payload.latest && !list(payload.timeline).length) { setFlash('empty'); return; }
    setFlash(null);
    const replay = replayControls(); if (replay) refs.content.append(replay);
    refs.content.append(metrics(), chart(), workspace());
    const policy = el('div', 'rf-policy'); const body = el('p'); body.append(el('strong', '', `${t('policy')}. `), document.createTextNode(t('policyText',{open:payload.policy?.openAfter ?? 3,recover:payload.policy?.recoverAfter ?? 2,gap:metric((payload.policy?.maxGapSeconds ?? 900)/60)})));
    const icon = el('span', '', '↳'); icon.setAttribute('aria-hidden','true'); policy.append(icon, body); refs.content.append(policy);
    if (activeControl?.startsWith('rf-replay-')) {
      const id = ['rf-replay-play','rf-replay-pause'].includes(activeControl) ? `rf-replay-${playing ? 'pause' : 'play'}` : activeControl;
      const replacement = document.getElementById(id);
      (replacement?.disabled ? document.getElementById('rf-replay-play') : replacement)?.focus({preventScroll:true});
    }
  }
  async function load() {
    resetView();
    if (offline) {
      const data = offlineSources?.[source === 'drill' ? `drill-${scenario}` : 'demo'] || (source === 'demo' ? window.ROOMFLOW_OFFLINE_DATA : null);
      acceptPayload(data);
      errorState = !data || data.schemaVersion !== 1;
      render(); return;
    }
    request?.abort();
    const controller = new AbortController(); request = controller;
    const timeout = setTimeout(() => controller.abort(), 15000);
    fullPayload = null; errorState = false; refs.refresh.disabled = true; root.setAttribute('aria-busy', 'true'); render();
    try {
      const query = new URLSearchParams({source}); if (source === 'drill') query.set('scenario',scenario);
      const response = await fetch(`/api/observations?${query}`, {signal:controller.signal, cache:'no-store'});
      if (!response.ok) throw new Error(`Evidence request returned ${response.status}`);
      const data = await response.json();
      if (!data || data.schemaVersion !== 1 || !data.source || !Array.isArray(data.timeline) || !Array.isArray(data.incidents)) throw new Error('Invalid observation payload');
      if (request !== controller) return;
      acceptPayload(data);
    } catch {
      if (request !== controller) return;
      errorState = true;
    } finally {
      clearTimeout(timeout);
      if (request === controller) { refs.refresh.disabled = false; root.setAttribute('aria-busy', 'false'); render(); }
    }
  }
  function languageChanged(event) {
    language = event.detail?.language === 'en' ? 'en' : 'zh-Hant';
    const active = document.activeElement?.id;
    build(); render();
    if (active) document.getElementById(active)?.focus({preventScroll:true});
  }
  document.addEventListener('roomflow:languagechange', languageChanged);
  if (!window.RoomFlowI18n) {
    document.documentElement.lang = language;
    const selector = document.getElementById('ui-language');
    if (selector) {
      selector.value = language;
      selector.addEventListener('change', () => {
        language = selector.value === 'en' ? 'en' : 'zh-Hant'; document.documentElement.lang = language;
        try { localStorage.setItem('roomflow-language',language); } catch { /* Storage is optional offline. */ }
        document.dispatchEvent(new CustomEvent('roomflow:languagechange',{detail:{language}}));
      });
    }
  }
  build(); load();
  // Local mode only reads the collector's latest saved rows; demo/lab remain fixed.
  if (!offline) setInterval(() => { if (source === 'local' && !document.hidden && !root.getAttribute('aria-busy')?.includes('true')) load(); }, 60000);
})();
