'use strict';

(() => {
  const pairs = {
    '普通 FIFO': 'Standard FIFO',
    '公平排隊模型': 'Fair queueing model',
    '會議優先模型': 'Meeting priority model',
    '沒有背景傳輸': 'No background traffic',
    '上傳檔案': 'Uploading files',
    '大量下載': 'Heavy downloads',
    '上傳與下載': 'Uploads and downloads',
    '伺服器回應格式不正確。': 'The server returned an invalid response.',
    '請求逾時，請確認本機服務仍在執行。': 'The request timed out. Check that the local service is running.',
    '無法連線到本機服務，請確認服務仍在執行。': 'Cannot connect to the local service. Check that it is running.',
    '狀態未知': 'Status unknown',
    '會議模式啟用中': 'Meeting mode active',
    '一般模式': 'Normal mode',
    '等待有效快照': 'Waiting for a valid preview',
    '時間已到，正在等待伺服器確認恢復一般模式。': 'Time is up. Waiting for the server to confirm normal mode.',
    '伺服器回傳的模式狀態無效。': 'The server returned an invalid mode.',
    '已讀回伺服器狀態：模擬會議策略生效，到期將自動恢復公平排隊。': 'Server readback confirmed: meeting priority is active in the model. Fair queueing will resume at expiry.',
    '已讀回伺服器狀態：一般模式採用公平排隊模型。': 'Server readback confirmed: normal mode uses the fair queueing model.',
    '正在套用模擬策略並確認狀態…': 'Applying the model strategy and checking its state…',
    '正在恢復一般模式並確認狀態…': 'Restoring normal mode and checking its state…',
    '策略狀態與請求不一致，請重新讀取並確認。': 'The strategy does not match the request. Refresh and check its state.',
    '實驗計算中…': 'Calculating…',
    '↗ 開始比較實驗': '↗ Compare strategies',
    '實驗已完成，結果已儲存': 'Experiment complete; results saved',
    '實驗已排入佇列': 'Experiment queued',
    '正在以相同條件計算三種策略': 'Calculating all three strategies under the same conditions',
    '正在建立實驗…': 'Creating the experiment…',
    '伺服器未提供實驗識別碼。': 'The server did not return an experiment ID.',
    '實驗已建立。圖表將在計算完成後使用實際輸出資料繪製。': 'Experiment created. Charts will use the actual output once calculation finishes.',
    '實驗完成，但伺服器未提供結果。': 'The experiment completed, but the server returned no results.',
    '實驗完成。可以比較策略、查看原始指標，或下載結果。': 'Experiment complete. Compare strategies, inspect the measured metrics, or download the results.',
    '實驗執行失敗。': 'The experiment failed.',
    '實驗狀態無法辨識。': 'The experiment status is not recognized.',
    '本次結果沒有可用的 RTT 時間序列。摘要指標仍可在下表查看。': 'No RTT time series is available for this run. Summary metrics remain available below.',
    '三種網路策略的會議往返延遲比較': 'Meeting round-trip latency under three network strategies',
    '會議優先 · p95 RTT': 'Meeting priority · p95 RTT',
    '模型中較差時段的往返延遲': 'Round-trip latency at the 95th percentile in the model',
    '相對 FIFO 的延遲變化': 'Latency change versus FIFO',
    '優先策略的延遲較高，請檢查條件': 'Priority produced higher latency; inspect the conditions',
    '同一條件下的模型比較結果': 'Model comparison under identical conditions',
    '會議優先 · 背景傳輸': 'Meeting priority · background traffic',
    '室友流量實際取得的模型吞吐量': 'Modeled throughput actually received by roommate traffic',
    '公平排隊或會議優先策略缺少有效 RTT 樣本，無法計算兩者差異。請查看原始資料與封包遺失。': 'Fair queueing or meeting priority has no valid RTT samples. Their difference cannot be calculated; inspect the raw data and packet loss.',
    '如何解讀這份結果': 'How to read these results',
    '結果來自可重現的佇列／傳輸模型，非 Linux CAKE 或實體路由器量測。': 'This is a deterministic queue/transport model, not Linux CAKE or physical router telemetry.',
    '固定速率 UDP 僅近似傳輸需求；未模擬 WebRTC 編碼、自適應機制或主觀視訊品質。': 'Fixed-rate UDP traffic approximates transport demand; it does not emulate WebRTC codecs, adaptation, or subjective video quality.',
    '表格取每次測試摘要的平均值；p95 為每次 p95 的平均，並非合併所有封包後重算。': 'The table averages per-run summaries; p95 values are means of per-run p95, not a pooled percentile.',
    '混合情境的吞吐量為上傳與下載之和。延遲圖表顯示第一次重複測試。': 'Throughput is the sum of upload and download where both directions are active. The chart shows repetition one.',
    '結果來自離散事件佇列模型，不是 Linux CAKE 或實體路由器測試。': 'Results come from a discrete-event queue model, not Linux CAKE or physical router tests.',
    'UDP 流量是會議的傳輸替代模型，不能直接保證 Zoom、Teams 或其他服務的通話品質。': 'UDP is a surrogate for meeting transport demand. It cannot guarantee call quality in Zoom, Teams, or other services.',
    '模型無法涵蓋 Wi-Fi 干擾、設備效能、ISP 與視訊應用的所有變因。': 'The model does not cover every factor in Wi-Fi interference, device performance, ISPs, or video applications.',
    '比較實驗': 'Strategy comparison',
    '正在讀取實驗結果…': 'Loading experiment results…',
    '還沒有實驗紀錄。完成第一次實驗後，報告會保存在這裡。': 'No experiments yet. Reports will be saved here after your first experiment.',
    '網路比較實驗': 'Network comparison',
    '等待中': 'Queued',
    '計算中': 'Running',
    '已完成': 'Complete',
    '失敗': 'Failed',
    '查看報告 ↗': 'View report ↗',
    '查看進度 ↗': 'View progress ↗',
    'Linux CAKE（SQM）': 'Linux CAKE (SQM)',
    'CAKE＋會議分類': 'CAKE + meeting classification',
    '無有效區間': 'No valid range',
    '已驗證的保存實測': 'Audited saved measurements',
    'Linux 核心': 'Linux kernel',
    '虛擬化環境': 'Virtualization',
    '上／下行瓶頸': 'Upload / download limit',
    '基礎 RTT': 'Configured base RTT',
    '測試／暖機': 'Measurement / warmup',
    '重複／執行次數': 'Repeats / total runs',
    '環境自我檢查': 'Environment self-checks',
    '實測觀察與限制': 'Observations and limitations',
    '實測尚未完成': 'Measurements pending',
    'Linux 封包實測尚未完成。': 'Linux packet measurements are not complete yet.',
    '核心實驗仍在執行。完成後會載入保存的實測結果。': 'Kernel experiments are still running. Saved measurements will load when complete.',
    '尚未取得實測': 'Measurements unavailable',
    '暫時無法讀取實測證據。': 'Saved measurement evidence is temporarily unavailable.',
    'Linux 重複實驗尚在執行': 'The repeated Linux experiments are still running.',
    '存在無有效 RTT 的實驗，無法比較會議優先與 SQM 的 p95 增益。': 'Some runs have no valid RTT samples. A p95 RTT benefit of meeting priority over SQM cannot be calculated.',
    '延遲統計來自選定會議裝置的 ping；丟包、抖動及吞吐量來自 iperf3 接收端，沒有以預設數字填入。': 'Latency statistics come from ping on the selected meeting device. Packet loss, jitter, and throughput come from iperf3 receivers; no default values were substituted.',
    '上傳與下載的吞吐量分開顯示；每次實驗先暖機 3 秒，再量測 15 秒。': 'Upload and download throughput are shown separately. Each run has 3 seconds of warmup followed by 15 seconds of measurement.',
    '這批測量後段出現持續的 RTT、丟包與吞吐量波動，包含沒有室友背景流量的情境；原始結果全部保留。資料已核對，但異常原因尚未確定，不能將這批平均值解讀成真實家庭網路的效能保證。': 'Later runs showed sustained variation in RTT, loss, and throughput, including scenarios without roommate background traffic. All raw results are preserved. The data has been audited, but the cause remains unresolved; these averages are not a performance guarantee for a real home network.',
    '另存的 11 次診斷補測仍出現延遲與丟包；目前沒有足夠證據證明會議分類比一般 SQM 有穩定額外收益。': 'The 11 separately saved diagnostic reruns still showed latency and packet loss. There is not enough evidence to demonstrate a reliable additional benefit from meeting classification over standard SQM.',
  };
  const errorPairs = {
    '保存的會議模式狀態無效，請先檢查狀態檔再重新啟動。': 'Invalid persisted session state; inspect the session file before restarting.',
    '讀回的策略與要求的模式不一致。': 'Strategy readback did not match the requested mode.',
    '目前只能選擇實驗中的會議裝置。': 'Only the meeting lab device can be selected.',
    '持續時間必須是 1 到 7200 秒的整數。': 'Duration must be an integer between 1 and 7200 seconds.',
    '會議模式正在啟用中，請先結束再重新開始。': 'A meeting session is already active; end it before starting another.',
    '實驗設定格式必須是物件。': 'Experiment configuration must be an object.',
    '不支援這個負載情境。': 'Unknown scenario.',
    '請使用 application/json 格式。': 'Use application/json.',
    '請求內容超過大小限制。': 'Request body too large.',
    'JSON 格式無效。': 'Invalid JSON.',
    '伺服器正在關閉。': 'The server is shutting down.',
    '請使用本機 localhost 位址。': 'Use the localhost address.',
    '不允許來自其他來源的寫入請求。': 'Cross-origin writes are not allowed.',
    '實驗因伺服器重新啟動而中斷，請重新執行。': 'The experiment was interrupted by a server restart; start a new run.',
    '保存的實驗結果遺失，請重新執行。': 'The saved experiment result is missing; start a new run.',
    'Linux 實測資料暫時無法讀取，請稍後重試。': 'Linux experiment evidence is temporarily unavailable; retry shortly.',
    'Linux 實測 CSV 尚未提供。': 'Linux experiment CSV is not available yet.',
    '保存的 Linux 核心實測資料無效。': 'Invalid saved kernel evidence.',
    '會議模式指令格式無效。': 'Invalid session command.',
    '不支援這個會議模式操作。': 'Unknown session action.',
    '實驗正在執行，請等待完成。': 'An experiment is already running. Wait for it to finish.',
    '找不到這個實驗。': 'Experiment not found.',
    '保存的實驗結果無效。': 'Invalid saved experiment result.',
    '實驗成功完成後才能匯出。': 'Export is available after successful completion.',
    '不支援這個請求方法。': 'Method not allowed.',
    '找不到內容。': 'Not found.',
    '策略必須是 fifo、fair 或 priority。': 'mode must be fifo, fair, or priority',
    '情境必須是 idle、upload、download 或 bidirectional。': 'scenario must be idle, upload, download, or bidirectional',
    '暖機時間必須小於實驗總時間。': 'warmupSeconds must be less than durationSeconds',
  };
  Object.assign(pairs, errorPairs);
  const reverse = Object.fromEntries(Object.entries(pairs).map(([zh, en]) => [en, zh]));
  window.RoomFlowDynamicTranslations = Object.freeze(pairs);
  window.RoomFlowDynamicTranslate = (value, language) => {
    const source = String(value);
    if (language !== 'en') return reverse[source] || source;
    if (pairs[source]) return pairs[source];
    let match = source.match(/^雙向壅塞的 p95 RTT 平均：FIFO ([\d.]+|—) ms、SQM ([\d.]+|—) ms、會議優先 ([\d.]+|—) ms。$/);
    if (match) return `Mean per-run p95 RTT under bidirectional congestion: FIFO ${match[1]} ms, SQM ${match[2]} ms, meeting priority ${match[3]} ms.`;
    match = source.match(/^會議優先相對 SQM 的 p95 平均(降低|增加) ([\d.]+) ms；請同時查看三次測量範圍，這不是統計顯著性或通話體感的結論。$/);
    if (match) return `Meeting priority ${match[1] === '降低' ? 'decreased' : 'increased'} mean per-run p95 RTT by ${match[2]} ms versus SQM. Check the ranges of all three runs; this does not establish statistical significance or perceived call quality.`;
    return source;
  };
  const fields = {durationSeconds:'實驗總時間（秒）',warmupSeconds:'暖機時間（秒）',repeats:'重複次數',seed:'隨機種子',upMbps:'上行頻寬（Mbps）',downMbps:'下行頻寬（Mbps）',baseRttMs:'基礎往返延遲（ms）',queueMs:'佇列容量（ms）',roommateFlows:'室友背景連線數',meetingDownMbps:'會議下行負載（Mbps）',meetingUpMbps:'會議上行負載（Mbps）',packetBytes:'封包大小（bytes）',sampleIntervalMs:'取樣間隔（ms）',priorityWeight:'會議優先權重',aqmTargetMs:'佇列管理目標（ms）'};
  window.RoomFlowDynamicLocalizeError = (value, language) => {
    const source = String(value);
    if (language === 'en') {
      const failedRequest = source.match(/^請求失敗（(\d+)）。$/);
      return pairs[source] || (failedRequest ? `Request failed (${failedRequest[1]}).` : source);
    }
    if (reverse[source]) return reverse[source];
    const nested = text => window.RoomFlowDynamicLocalizeError(text, language);
    for (const [prefix, translated] of [
      ['Apply failed and rollback requires attention: ', '套用失敗，回復原策略也需要處理：'],
      ['Strategy could not be applied: ', '無法套用策略：'],
      ['Could not persist experiment: ', '無法保存實驗：'],
      ['The saved experiment result could not be loaded: ', '無法讀取保存的實驗結果：'],
    ]) if (source.startsWith(prefix)) return translated + nested(source.slice(prefix.length));
    const metadata = source.match(/^(.*?) Metadata could not be persisted: (.*)$/s);
    if (metadata) return `${nested(metadata[1])} 無法保存實驗狀態：${nested(metadata[2])}`;
    let match = source.match(/^Experiment worker exited \(([^)]+)\) without a result\.$/);
    if (match) return `實驗工作程序已結束（代碼 ${match[1]}），但沒有產生結果。`;
    match = source.match(/^(\w+) must be (an integer|a number) between ([\d.]+) and ([\d.]+)\.$/);
    if (match) return `${fields[match[1]] || match[1]} 必須是 ${match[3]} 到 ${match[4]} 之間的${match[2] === 'an integer' ? '整數' : '數字'}。`;
    match = source.match(/^(\w+) must be a finite number from ([\d.]+) to ([\d.]+)$/);
    if (match) return `${fields[match[1]] || match[1]} 必須是 ${match[2]} 到 ${match[3]} 之間的有限數值。`;
    match = source.match(/^(\w+) must be an integer$/);
    if (match) return `${fields[match[1]] || match[1]} 必須是整數。`;
    match = source.match(/^Unknown event (.*)$/);
    if (match) return `未知的模擬事件：${match[1]}`;
    return source;
  };
})();
