'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const language = () => window.RoomFlowI18n?.language || 'zh-Hant';
  const locale = () => window.RoomFlowI18n?.locale || 'zh-TW';
  const tx = (value) => typeof value === 'object' && value !== null && 'zh' in value
    ? value[language() === 'en' ? 'en' : 'zh']
    : (window.RoomFlowI18n?.translateText(String(value)) || String(value));
  const bi = (zh, en) => ({ zh, en });
  const l = (zh, en) => tx(bi(zh, en));
  const errorText = (value, lang = language()) => window.RoomFlowDynamicLocalizeError?.(String(value), lang) || String(value);
  const feedbackMessages = new Map();
  const policies = {
    fifo: { label: '普通 FIFO', color: '#d49b5d' },
    fair: { label: '公平排隊模型', color: '#7b91b0' },
    priority: { label: '會議優先模型', color: '#328b68' },
  };
  const scenarioNames = { idle: '沒有背景傳輸', upload: '上傳檔案', download: '大量下載', mixed: '上傳與下載' };
  let serverSession = null;
  let serverPreview = null;
  let sessionBusy = false;
  let experimentBusy = false;
  let selectedExperimentId = null;
  let pollGeneration = 0;
  let connectionHealthy = false;
  let displayedSeries = null;
  let resizeFrame = null;
  let kernelEvidence = null;
  let kernelPollTimer = null;
  let displayedResult = null;
  let historyData = null;
  let historyError = null;
  let progressState = null;
  let connectionMessage = '';
  let kernelPendingState = null;

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(path, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        signal: controller.signal,
        cache: 'no-store',
      });
      let payload;
      try { payload = await response.json(); } catch { throw new Error('伺服器回應格式不正確。'); }
      if (!response.ok) throw new Error(typeof payload.error === 'string' ? payload.error : (payload.error?.message || `請求失敗（${response.status}）。`));
      return payload;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('請求逾時，請確認本機服務仍在執行。');
      if (error instanceof TypeError) throw new Error('無法連線到本機服務，請確認服務仍在執行。');
      throw error;
    } finally { clearTimeout(timeout); }
  }

  function feedback(id, message, error = false) {
    feedbackMessages.set(id, { message, error });
    const element = $(id);
    element.textContent = tx(message);
    element.classList.toggle('error', error);
  }

  function feedbackError(id, message, zhSuffix = '', enSuffix = '') {
    feedback(id, bi(errorText(message, 'zh-Hant') + zhSuffix, errorText(message, 'en') + enSuffix), true);
  }

  function setConnection(ok, message = '') {
    connectionHealthy = ok;
    connectionMessage = message;
    $('connection-alert').hidden = ok;
    $('connection-alert').textContent = errorText(message);
    renderSession();
  }

  function renderSession() {
    const active = serverSession?.mode === 'meeting';
    const remaining = active && Number.isFinite(serverSession.expiresAt) ? Math.max(0, Math.ceil((serverSession.expiresAt - Date.now()) / 1000)) : 0;
    $('session-pill').textContent = tx(!connectionHealthy ? '狀態未知' : active ? '會議模式啟用中' : '一般模式');
    $('session-pill').className = `pill${!connectionHealthy ? ' error' : active ? ' active' : ''}`;
    $('session-timer').textContent = active ? `${String(Math.floor(remaining / 60)).padStart(2, '0')}:${String(remaining % 60).padStart(2, '0')}` : '—';
    $('topology-policy').textContent = tx(!connectionHealthy ? '狀態未知' : active ? '會議優先模型' : '公平排隊模型');
    $('session-start').hidden = Boolean(active);
    $('session-stop').hidden = !active;
    $('session-start').disabled = sessionBusy || !connectionHealthy;
    $('session-stop').disabled = sessionBusy || !connectionHealthy;
    $('session-duration').disabled = sessionBusy || active;
    $('meeting-device').disabled = sessionBusy || active;
    const validPreview = connectionHealthy && serverPreview?.scope === 'fixed-workload-model';
    const previewMode = validPreview ? serverPreview.config?.mode : null;
    $('preview-policy').textContent = tx(previewMode === 'priority' ? '會議優先模型' : previewMode === 'fair' ? '公平排隊模型' : '等待有效快照');
    const previewValue = validPreview ? serverPreview.summary?.rttP95Ms : null;
    $('preview-rtt').replaceChildren(document.createTextNode(formatNumber(previewValue)), Object.assign(document.createElement('small'), { textContent: 'ms' }));
    if (active && remaining === 0 && connectionHealthy && !sessionBusy) {
      feedback('session-feedback', '時間已到，正在等待伺服器確認恢復一般模式。');
    }
  }

  async function refreshStatus({ quiet = false } = {}) {
    try {
      const status = await api('/api/status');
      if (!status.session || !['normal', 'meeting'].includes(status.session.mode)) throw new Error('伺服器回傳的模式狀態無效。');
      const previousMode = serverSession?.mode;
      serverSession = status.session;
      serverPreview = status.preview || null;
      setConnection(true);
      if (!quiet || previousMode !== serverSession.mode) {
        feedback('session-feedback', serverSession.mode === 'meeting' ? '已讀回伺服器狀態：模擬會議策略生效，到期將自動恢復公平排隊。' : '已讀回伺服器狀態：一般模式採用公平排隊模型。');
      }
      return status;
    } catch (error) {
      setConnection(false, error.message);
      if (!quiet) feedbackError('session-feedback', error.message);
      throw error;
    }
  }

  async function changeSession(action) {
    if (sessionBusy) return;
    sessionBusy = true;
    renderSession();
    feedback('session-feedback', action === 'start' ? '正在套用模擬策略並確認狀態…' : '正在恢復一般模式並確認狀態…');
    try {
      const body = action === 'start' ? { action, durationSeconds: Number($('session-duration').value), device: $('meeting-device').value } : { action };
      await api('/api/session', { method: 'POST', body: JSON.stringify(body) });
      const status = await refreshStatus();
      if (status.session.mode !== (action === 'start' ? 'meeting' : 'normal')) throw new Error('策略狀態與請求不一致，請重新讀取並確認。');
    } catch (error) {
      feedbackError('session-feedback', error.message);
      // The state shown always comes from a GET, even if a POST may have succeeded.
      try { await refreshStatus({ quiet: true }); } catch { /* connection indicator handles failure */ }
    } finally {
      sessionBusy = false;
      renderSession();
    }
  }

  function readExperimentInputs() {
    return {
      scenario: document.querySelector('input[name="scenario"]:checked').value,
      downMbps: Number($('down-mbps').value),
      upMbps: Number($('up-mbps').value),
      baseRttMs: Number($('base-rtt').value),
      durationSeconds: Number($('test-duration').value),
      repeats: Number($('repeats').value),
      seed: Number($('seed').value),
    };
  }

  function updateTopology() {
    const config = readExperimentInputs();
    $('topology-down').replaceChildren(document.createTextNode(`${config.downMbps} `), Object.assign(document.createElement('small'), { textContent: 'Mbps' }));
    $('topology-up').replaceChildren(document.createTextNode(`${config.upMbps} `), Object.assign(document.createElement('small'), { textContent: 'Mbps' }));
    $('topology-rtt').replaceChildren(document.createTextNode(`${config.baseRttMs} `), Object.assign(document.createElement('small'), { textContent: 'ms' }));
  }

  function setExperimentBusy(value) {
    experimentBusy = value;
    $('experiment-start').disabled = value;
    $('experiment-start').textContent = tx(value ? '實驗計算中…' : '↗ 開始比較實驗');
    $('experiment-form').querySelectorAll('input').forEach((input) => { input.disabled = value; });
  }

  function renderProgress(status, progress = 0) {
    progressState = { status, progress };
    const value = Math.min(100, Math.max(0, (Number(progress) || 0) * 100));
    $('experiment-progress').hidden = false;
    $('progress-bar').value = value;
    $('progress-number').textContent = `${Math.round(value)}%`;
    $('progress-text').textContent = tx(status === 'complete' ? '實驗已完成，結果已儲存' : status === 'queued' ? '實驗已排入佇列' : '正在以相同條件計算三種策略');
  }

  async function startExperiment(event) {
    event.preventDefault();
    if (experimentBusy || !$('experiment-form').reportValidity()) return;
    const config = readExperimentInputs();
    setExperimentBusy(true);
    renderProgress('queued', 0);
    feedback('experiment-feedback', '正在建立實驗…');
    try {
      const created = await api('/api/experiments', { method: 'POST', body: JSON.stringify(config) });
      if (!created.id) throw new Error('伺服器未提供實驗識別碼。');
      selectedExperimentId = created.id;
      feedback('experiment-feedback', '實驗已建立。圖表將在計算完成後使用實際輸出資料繪製。');
      void refreshHistory();
      await pollExperiment(created.id, ++pollGeneration);
    } catch (error) {
      feedbackError('experiment-feedback', error.message);
      setExperimentBusy(false);
    }
  }

  async function pollExperiment(id, generation) {
    let errors = 0;
    while (generation === pollGeneration) {
      try {
        const experiment = await api(`/api/experiments/${encodeURIComponent(id)}`);
        errors = 0;
        renderProgress(experiment.status, experiment.status === 'complete' ? 1 : experiment.progress);
        if (experiment.status === 'complete') {
          if (!experiment.result) throw new Error('實驗完成，但伺服器未提供結果。');
          renderResult(experiment.result, id, experiment);
          setExperimentBusy(false);
          feedback('experiment-feedback', '實驗完成。可以比較策略、查看原始指標，或下載結果。');
          void refreshHistory();
          return;
        }
        if (experiment.status === 'failed') throw new Error(experiment.error || '實驗執行失敗。');
        if (!['queued', 'running'].includes(experiment.status)) throw new Error('實驗狀態無法辨識。');
        await new Promise((resolve) => setTimeout(resolve, 700));
      } catch (error) {
        errors += 1;
        if (errors >= 3 || error.message.includes('實驗執行失敗') || error.message.includes('狀態無法辨識')) {
          setExperimentBusy(false);
          feedbackError('experiment-feedback', error.message, ' 可從「過去的實驗」重新查看。', ' Reopen it from Past experiments.');
          void refreshHistory();
          return;
        }
        feedbackError('experiment-feedback', error.message, ' 正在重新確認實驗狀態…', ' Checking the experiment status again…');
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
    }
  }

  function formatNumber(value, digits = 1) {
    return Number.isFinite(Number(value)) && value !== null && value !== '' ? Number(value).toLocaleString(locale(), { minimumFractionDigits: digits, maximumFractionDigits: digits }) : '—';
  }

  function svgElement(name, attributes = {}, content) {
    const element = document.createElementNS('http://www.w3.org/2000/svg', name);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
    if (content !== undefined) element.textContent = tx(content);
    return element;
  }

  function renderChart(series) {
    displayedSeries = series;
    const container = $('rtt-chart');
    container.replaceChildren();
    const points = series.filter((point) => policies[point.policy] && Number.isFinite(point.second) && Number.isFinite(point.rttMs));
    if (!points.length) {
      const text = document.createElement('p');
      text.className = 'muted';
      text.textContent = tx('本次結果沒有可用的 RTT 時間序列。摘要指標仍可在下表查看。');
      container.append(text);
      return;
    }
    const width = Math.max(340, container.clientWidth || 880);
    const height = width < 500 ? 220 : 250;
    const margin = { left: 44, right: 18, top: 12, bottom: 34 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    const maximumTime = Math.max(1, ...points.map((point) => Number(point.second)));
    const highestRtt = Math.max(1, ...points.map((point) => Number(point.rttMs)));
    const magnitude = 10 ** Math.floor(Math.log10(highestRtt));
    const maximumRtt = Math.ceil((highestRtt * 1.12) / magnitude) * magnitude;
    const x = (value) => margin.left + (value / maximumTime) * innerWidth;
    const y = (value) => height - margin.bottom - (value / maximumRtt) * innerHeight;
    const svg = svgElement('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-labelledby': 'chart-title chart-desc' });
    svg.append(svgElement('title', { id: 'chart-title' }, '三種網路策略的會議往返延遲比較'));
    svg.append(svgElement('desc', { id: 'chart-desc' }, l(`本次模型時間序列，橫軸為模擬秒數，縱軸為 RTT 毫秒，最大值 ${formatNumber(highestRtt)} 毫秒。詳細摘要見下方表格。`, `Model time series: simulated seconds on the horizontal axis and RTT in milliseconds on the vertical axis. The highest RTT is ${formatNumber(highestRtt)} ms. See the table below for details.`)));
    for (let index = 0; index <= 4; index += 1) {
      const value = (maximumRtt * index) / 4;
      svg.append(svgElement('line', { x1: margin.left, x2: width - margin.right, y1: y(value), y2: y(value), stroke: '#e7ede1', 'stroke-dasharray': index === 0 ? '' : '3 4' }));
      svg.append(svgElement('text', { x: margin.left - 10, y: y(value) + 3, 'text-anchor': 'end' }, formatNumber(value, maximumRtt < 10 ? 1 : 0)));
    }
    for (let index = 0; index <= 6; index += 1) {
      const value = (maximumTime * index) / 6;
      svg.append(svgElement('text', { x: x(value), y: height - 13, 'text-anchor': 'middle' }, `${formatNumber(value, 0)}s`));
    }
    for (const [key, policy] of Object.entries(policies)) {
      const raw = series.filter((point) => point.policy === key && Number.isFinite(point.second));
      // Average duplicate seconds (e.g. repeated runs) instead of drawing misleading backtracking.
      const grouped = new Map();
      raw.forEach((point) => { const second = Number(point.second); const values = grouped.get(second) || []; if (Number.isFinite(point.rttMs)) values.push(point.rttMs); grouped.set(second, values); });
      const ordered = [...grouped].sort((a, b) => a[0] - b[0]).map(([second, values]) => ({ second, rttMs: values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null }));
      if (!ordered.length) continue;
      let connected = false;
      const path = ordered.map((point) => {
        if (point.rttMs === null) { connected = false; return ''; }
        const command = `${connected ? 'L' : 'M'}${x(point.second).toFixed(2)} ${y(point.rttMs).toFixed(2)}`;
        connected = true;
        return command;
      }).join(' ');
      svg.append(svgElement('path', { d: path, fill: 'none', stroke: policy.color, 'stroke-width': 2.3, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
      ordered.forEach((point) => {
        if (point.rttMs === null) return;
        const hit = svgElement('circle', { cx: x(point.second), cy: y(point.rttMs), r: 4, fill: policy.color, opacity: 0 });
        hit.append(svgElement('title', {}, `${tx(policy.label)} · ${point.second}s · ${formatNumber(point.rttMs)} ms`));
        svg.append(hit);
      });
    }
    container.append(svg);
  }

  function makeMetric(title, value, unit, note) {
    const card = document.createElement('article');
    card.className = 'card metric-card';
    const label = document.createElement('div'); label.className = 'metric-title'; label.textContent = tx(title);
    const figure = document.createElement('div'); figure.className = 'metric-value'; figure.textContent = value;
    const unitElement = document.createElement('small'); unitElement.textContent = unit; figure.append(unitElement);
    const explanation = document.createElement('div'); explanation.className = 'metric-note'; explanation.textContent = tx(note);
    card.append(label, figure, explanation);
    return card;
  }

  function renderResult(result, id, experiment = {}) {
    displayedResult = { result, id, experiment };
    selectedExperimentId = id;
    // Reveal the chart container before measuring its responsive drawing width.
    $('empty-state').hidden = true;
    $('result-content').hidden = false;
    const summary = Array.isArray(result.summary) ? result.summary : [];
    const byPolicy = Object.fromEntries(summary.filter((row) => policies[row.policy]).map((row) => [row.policy, row]));
    const fifo = byPolicy.fifo;
    const fair = byPolicy.fair;
    const priority = byPolicy.priority;
    const delta = fifo && priority && Number.isFinite(fifo.meetingRttP95Ms) && Number.isFinite(priority.meetingRttP95Ms) && fifo.meetingRttP95Ms > 0 ? ((fifo.meetingRttP95Ms - priority.meetingRttP95Ms) / fifo.meetingRttP95Ms) * 100 : NaN;
    const deltaLabel = Number.isFinite(delta) ? `${delta < 0 ? '+' : '−'}${formatNumber(Math.abs(delta))}` : '—';
    $('metric-grid').replaceChildren(
      makeMetric('會議優先 · p95 RTT', formatNumber(priority?.meetingRttP95Ms), 'ms', '模型中較差時段的往返延遲'),
      makeMetric('相對 FIFO 的延遲變化', deltaLabel, '%', delta < 0 ? '優先策略的延遲較高，請檢查條件' : '同一條件下的模型比較結果'),
      makeMetric('會議優先 · 背景傳輸', formatNumber(priority?.backgroundMbps, 2), 'Mbps', '室友流量實際取得的模型吞吐量'),
    );
    if (Number.isFinite(fair?.meetingRttP95Ms) && Number.isFinite(priority?.meetingRttP95Ms)) {
      const difference = priority.meetingRttP95Ms - fair.meetingRttP95Ms;
      $('result-insight').textContent = l(`公平排隊的 p95 RTT 為 ${formatNumber(fair.meetingRttP95Ms)} ms；會議優先相對公平排隊${difference < 0 ? '降低' : '增加'} ${formatNumber(Math.abs(difference))} ms。請一起比較封包遺失與背景傳輸速度，再判斷是否需要額外優先策略。`, `Fair queueing has a p95 RTT of ${formatNumber(fair.meetingRttP95Ms)} ms. Meeting priority ${difference < 0 ? 'reduces' : 'increases'} it by ${formatNumber(Math.abs(difference))} ms. Compare packet loss and background throughput as well before deciding whether extra priority is worthwhile.`);
    } else {
      $('result-insight').textContent = tx('公平排隊或會議優先策略缺少有效 RTT 樣本，無法計算兩者差異。請查看原始資料與封包遺失。');
    }
    $('summary-body').replaceChildren();
    for (const [key, policy] of Object.entries(policies)) {
      const row = byPolicy[key];
      const tr = document.createElement('tr');
      const label = document.createElement('td');
      const dot = document.createElement('i'); dot.className = `policy-dot ${key}`; label.append(dot, document.createTextNode(tx(policy.label)));
      tr.append(label);
      for (const [field, digits] of [['meetingRttP95Ms', 1], ['meetingJitterMs', 2], ['meetingLossPct', 2], ['meetingMbps', 2], ['backgroundMbps', 2]]) {
        const cell = document.createElement('td'); cell.textContent = formatNumber(row?.[field], digits); tr.append(cell);
      }
      $('summary-body').append(tr);
    }
    renderChart(Array.isArray(result.series) ? result.series : []);
    $('limitations').replaceChildren();
    const label = document.createElement('strong'); label.textContent = tx('如何解讀這份結果');
    const list = document.createElement('ul');
    const limitationTranslations = {
      'This is a deterministic queue/transport model, not Linux CAKE or physical router telemetry.': '結果來自可重現的佇列／傳輸模型，非 Linux CAKE 或實體路由器量測。',
      'Fixed-rate UDP traffic approximates transport demand; it does not emulate WebRTC codecs, adaptation, or subjective video quality.': '固定速率 UDP 僅近似傳輸需求；未模擬 WebRTC 編碼、自適應機制或主觀視訊品質。',
      'The table averages per-run summaries; p95 values are means of per-run p95, not a pooled percentile.': '表格取每次測試摘要的平均值；p95 為每次 p95 的平均，並非合併所有封包後重算。',
      'Throughput is the sum of upload and download where both directions are active. The chart shows repetition one.': '混合情境的吞吐量為上傳與下載之和。延遲圖表顯示第一次重複測試。',
    };
    const limitations = Array.isArray(result.limitations) && result.limitations.length ? result.limitations.map((item) => limitationTranslations[item] || item) : ['結果來自離散事件佇列模型，不是 Linux CAKE 或實體路由器測試。', 'UDP 流量是會議的傳輸替代模型，不能直接保證 Zoom、Teams 或其他服務的通話品質。', '模型無法涵蓋 Wi-Fi 干擾、設備效能、ISP 與視訊應用的所有變因。'];
    for (const limitation of limitations) { const item = document.createElement('li'); item.textContent = tx(limitation); list.append(item); }
    $('limitations').append(label, list);
    const scenario = experiment.scenario || result.config?.scenario || summary[0]?.scenario;
    const count = Array.isArray(result.runs) ? result.runs.length : 0;
    $('results-description').textContent = l(`${scenarioNames[scenario] || '比較實驗'} · ${count ? `${count} 次策略執行 · ` : ''}報告 ${String(id).slice(0, 8)} · 模型輸出`, `${tx(scenarioNames[scenario] || '比較實驗')} · ${count ? `${count} strategy runs · ` : ''}Report ${String(id).slice(0, 8)} · model output`);
    $('export-csv').href = `/api/experiments/${encodeURIComponent(id)}/export.csv`;
    $('export-json').href = `/api/experiments/${encodeURIComponent(id)}/export.json`;
    $('export-csv').setAttribute('download', `experiment-${id}.csv`);
    $('export-json').setAttribute('download', `experiment-${id}.json`);
    $('export-actions').hidden = false;
    $('empty-state').hidden = true;
    $('result-content').hidden = false;
  }

  async function showHistoryExperiment(id) {
    if (experimentBusy) return;
    setExperimentBusy(true);
    feedback('experiment-feedback', '正在讀取實驗結果…');
    try {
      await pollExperiment(id, ++pollGeneration);
      $('results').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    } catch (error) {
      setExperimentBusy(false);
      feedbackError('experiment-feedback', error.message);
    }
  }

  async function refreshHistory() {
    try {
      const data = await api('/api/experiments');
      historyData = Array.isArray(data.experiments) ? data.experiments : [];
      historyError = null;
      renderHistory();
    } catch (error) {
      historyError = error.message;
      renderHistory();
    }
  }

  function renderHistory() {
    if (historyError) {
      const text = document.createElement('p'); text.className = 'muted'; text.textContent = l(`實驗紀錄讀取失敗：${errorText(historyError, 'zh-Hant')}`, `Could not load experiment history: ${errorText(historyError, 'en')}`); $('history-list').replaceChildren(text);
      return;
    }
    if (historyData === null) return;
    const experiments = historyData;
      $('history-list').replaceChildren();
      if (!experiments.length) {
        const text = document.createElement('p'); text.className = 'muted'; text.textContent = tx('還沒有實驗紀錄。完成第一次實驗後，報告會保存在這裡。'); $('history-list').append(text);
        return;
      }
      for (const experiment of experiments.slice(0, 10)) {
        const row = document.createElement('div'); row.className = 'history-row';
        const icon = document.createElement('span'); icon.className = 'history-row-icon'; icon.setAttribute('aria-hidden', 'true'); icon.textContent = '⌁';
        const info = document.createElement('div'); info.className = 'history-row-info';
        const title = document.createElement('strong'); title.textContent = tx(scenarioNames[experiment.scenario] || '網路比較實驗');
        const subtitle = document.createElement('small'); const date = new Date(experiment.createdAt); subtitle.textContent = `${Number.isNaN(date.getTime()) ? '' : `${date.toLocaleString(locale(), { timeZone: 'America/New_York', hour12: false })}${l('（紐約）', ' (New York)')}`} · ${String(experiment.id).slice(0, 8)}`; info.append(title, subtitle);
        const status = document.createElement('span'); status.className = 'history-row-status'; status.textContent = tx(({ queued: '等待中', running: '計算中', complete: '已完成', failed: '失敗' })[experiment.status] || experiment.status);
        row.append(icon, info, status);
        if (experiment.status !== 'failed') {
          const button = document.createElement('button'); button.type = 'button'; button.className = 'text-button'; button.textContent = tx(experiment.status === 'complete' ? '查看報告 ↗' : '查看進度 ↗'); button.setAttribute('aria-label', `${button.textContent}, ${title.textContent}, ${String(experiment.id).slice(0, 8)}`); button.disabled = experimentBusy; button.addEventListener('click', () => void showHistoryExperiment(experiment.id)); row.append(button);
        }
        $('history-list').append(row);
      }
  }

  const kernelPolicies = {
    fifo: { label: '普通 FIFO', colorClass: 'fifo' },
    sqm: { label: 'Linux CAKE（SQM）', colorClass: 'fair' },
    meeting: { label: 'CAKE＋會議分類', colorClass: 'priority' },
  };

  function renderKernelScenario() {
    if (!kernelEvidence || !Array.isArray(kernelEvidence.summary)) return;
    const scenario = $('kernel-scenario').value;
    const rows = Object.fromEntries(kernelEvidence.summary.filter((row) => row.scenario === scenario && kernelPolicies[row.policy]).map((row) => [row.policy, row]));
    $('kernel-summary').replaceChildren();
    $('kernel-jitter').replaceChildren();
    for (const [key, policy] of Object.entries(kernelPolicies)) {
      const row = rows[key];
      const createLabel = () => {
        const label = document.createElement('td');
        const dot = document.createElement('i'); dot.className = `policy-dot ${policy.colorClass}`;
        label.append(dot, document.createTextNode(tx(policy.label)));
        return label;
      };
      const tr = document.createElement('tr');
      tr.append(createLabel());
      const rtt = document.createElement('td');
      rtt.append(document.createTextNode(formatNumber(row?.rttP95MeanMs)));
      const range = document.createElement('small'); range.className = 'kernel-range';
      range.textContent = Number.isFinite(row?.rttP95MinMs) && Number.isFinite(row?.rttP95MaxMs) ? `${formatNumber(row.rttP95MinMs)}–${formatNumber(row.rttP95MaxMs)}` : tx('無有效區間');
      rtt.append(range);
      tr.append(rtt);
      for (const field of ['meetingUpLossMeanPct', 'meetingDownLossMeanPct', 'backgroundUpMeanMbps', 'backgroundDownMeanMbps']) {
        const cell = document.createElement('td'); cell.textContent = formatNumber(row?.[field], 2); tr.append(cell);
      }
      $('kernel-summary').append(tr);
      const jitterTr = document.createElement('tr'); jitterTr.append(createLabel());
      for (const field of ['meetingUpJitterMeanMs', 'meetingDownJitterMeanMs']) {
        const cell = document.createElement('td'); cell.textContent = formatNumber(row?.[field], 3); jitterTr.append(cell);
      }
      $('kernel-jitter').append(jitterTr);
    }
  }

  function renderKernelEvidence(evidence) {
    kernelEvidence = evidence;
    kernelPendingState = null;
    $('kernel-status').textContent = tx('已驗證的保存實測');
    $('kernel-status').className = 'pill active';
    $('kernel-pending').hidden = true;
    $('kernel-content').hidden = false;
    const environment = evidence.environment || {};
    const configuration = [
      ['Linux 核心', environment.kernel || '—'],
      ['虛擬化環境', environment.hypervisor || '—'],
      ['上／下行瓶頸', `${formatNumber(environment.upMbps, 0)} / ${formatNumber(environment.downMbps, 0)} Mbps`],
      ['基礎 RTT', `${formatNumber(environment.baseRttMs, 0)} ms`],
      ['測試／暖機', `${formatNumber(environment.durationSeconds, 0)} / ${formatNumber(environment.warmupSeconds, 0)} ${l('秒', 's')}`],
      ['重複／執行次數', `${formatNumber(environment.repeats, 0)} / ${formatNumber(environment.runCount, 0)}`],
      ['環境自我檢查', `${formatNumber(environment.selftestChecks, 0)} ${l('項', 'checks')}`],
    ];
    $('kernel-config').replaceChildren();
    for (const [label, value] of configuration) {
      const entry = document.createElement('div');
      const name = document.createElement('span'); name.textContent = tx(label);
      const result = document.createElement('strong'); result.textContent = value;
      entry.append(name, result); $('kernel-config').append(entry);
    }
    // Only same-origin export routes can be used for this local saved evidence.
    if (typeof evidence.rawCsvUrl === 'string' && evidence.rawCsvUrl.startsWith('/api/kernel-evidence/')) {
      $('kernel-export').href = evidence.rawCsvUrl;
      $('kernel-export').setAttribute('download', 'linux-kernel-evidence.csv');
      $('kernel-export').hidden = false;
    } else { $('kernel-export').hidden = true; }
    $('kernel-findings').replaceChildren();
    const heading = document.createElement('strong'); heading.textContent = tx('實測觀察與限制');
    const list = document.createElement('ul');
    const findings = Array.isArray(evidence.findings) ? evidence.findings : [];
    for (const finding of findings) { const item = document.createElement('li'); item.textContent = tx(finding); list.append(item); }
    $('kernel-findings').append(heading, list);
    $('kernel-findings').hidden = findings.length === 0;
    renderKernelScenario();
  }

  async function refreshKernelEvidence() {
    if (kernelPollTimer !== null) { clearTimeout(kernelPollTimer); kernelPollTimer = null; }
    try {
      const evidence = await api('/api/kernel-evidence');
      if (evidence.status === 'verified' && evidence.engine === 'linux-kernel' && Array.isArray(evidence.summary)) {
        renderKernelEvidence(evidence);
        return;
      }
      kernelEvidence = null;
      kernelPendingState = { evidence };
      renderKernelPending();
      if (evidence.status === 'pending') kernelPollTimer = setTimeout(() => void refreshKernelEvidence(), 15000);
    } catch (error) {
      kernelEvidence = null;
      kernelPendingState = { error: error.message };
      renderKernelPending();
    }
  }

  function renderKernelPending() {
    if (!kernelPendingState) return;
    const { evidence, error } = kernelPendingState;
    $('kernel-status').textContent = tx(error ? '尚未取得實測' : '實測尚未完成');
    $('kernel-status').className = 'pill';
    $('kernel-content').hidden = true;
    $('kernel-pending').hidden = false;
    $('kernel-pending-title').textContent = tx(error ? '暫時無法讀取實測證據。' : 'Linux 封包實測尚未完成。');
    $('kernel-message').textContent = error
      ? l(`實測證據暫時無法讀取：${errorText(error, 'zh-Hant')} 請重新整理頁面後確認。`, `Saved evidence could not be loaded: ${errorText(error, 'en')} Refresh the page to try again.`)
      : tx(evidence.message || '核心實驗仍在執行。完成後會載入保存的實測結果。');
  }

  document.addEventListener('roomflow:languagechange', () => {
    setExperimentBusy(experimentBusy);
    renderSession();
    $('connection-alert').textContent = errorText(connectionMessage);
    if (progressState) renderProgress(progressState.status, progressState.progress);
    if (displayedResult) renderResult(displayedResult.result, displayedResult.id, displayedResult.experiment);
    renderHistory();
    if (kernelEvidence) renderKernelEvidence(kernelEvidence);
    else renderKernelPending();
    for (const [id, { message, error }] of feedbackMessages) feedback(id, message, error);
  });

  $('session-form').addEventListener('submit', (event) => { event.preventDefault(); void changeSession('start'); });
  $('session-stop').addEventListener('click', () => void changeSession('stop'));
  $('experiment-form').addEventListener('submit', (event) => void startExperiment(event));
  $('experiment-form').addEventListener('input', updateTopology);
  $('history-refresh').addEventListener('click', () => void refreshHistory());
  $('kernel-scenario').addEventListener('change', renderKernelScenario);
  window.addEventListener('resize', () => {
    if (resizeFrame !== null) cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => { if (displayedSeries !== null) renderChart(displayedSeries); resizeFrame = null; });
  });
  for (const link of document.querySelectorAll('.sidebar-nav a')) {
    link.addEventListener('click', () => { document.querySelectorAll('.sidebar-nav a').forEach((item) => item.classList.remove('selected')); link.classList.add('selected'); });
  }
  setInterval(renderSession, 1000);
  setInterval(() => { if (!sessionBusy) void refreshStatus({ quiet: true }).catch(() => {}); }, 4000);
  updateTopology();
  void refreshStatus().catch(() => {});
  void refreshHistory();
  void refreshKernelEvidence();
})();
