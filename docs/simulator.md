# 封包模擬器的模型與測量方式

`src/simulator.mjs` 是使用 Node.js 內建功能的離散事件教學模型。圖表由封包入列、排程、序列化、到達、ACK 和丟包事件計算，沒有預先填好的改善數字。相同設定與 seed 會產生相同的完整事件記錄。

**這不是實際家用網路測試，也不是 Linux CAKE、CoDel 或完整 TCP 實作。** 真正的流量測試應另外在 Linux lab 執行，資料分開標示。

## 共用瓶頸與流量

上傳與下載各有一個固定速率的共用瓶頸。同一方向的會議封包、室友封包與探測封包都必須經過該瓶頸。預設下載 20 Mbps、上傳 5 Mbps、基礎往返傳播延遲 40 ms。任何已在服務中的封包不可搶先中斷，服務時間為 `packetBytes / (Mbps × 125)` 毫秒。

會議為固定速率 UDP 類型流量：下載 1.5 Mbps、上傳 1 Mbps，每個封包 1200 模型位元組。它不根據壅塞調低碼率。室友每個作用方向預設有四條 bulk flow，封包 1500 位元組。

Bulk 使用簡化、受壅塞控制的 ACK-paced AIMD：初始窗口 10 個封包，每個成功 ACK 增加 `1/cwnd`；丟包乘以 0.7、ECN 回饋乘以 0.75，窗口下限 2、上限 1024。同一 flow 每個基礎 RTT 最多減少窗口一次。ACK 延遲包含該資料封包的排隊時間以及固定基礎 RTT；不另外將 TCP ACK 放進反方向的佇列。丟包回饋延遲是 `max(100 ms, 2 × base RTT)`。這提供壅塞回饋，**並不實作 CUBIC、BBR、慢啟動、快速重傳或完整重傳資料語義**。每個成功 bulk 封包僅計算一次 wire throughput；丟棄的封包消耗的是提出的負載。

每 100 ms 發送一個 84 位元組往返探測：先排上傳佇列，經過半個基礎 RTT，再排下載佇列，經過另一半 RTT 才完成。探測與會議歸在同一 selected-device flow，優先政策也適用探測。因此這測量的是選定裝置的往返表現。探測可能被丟棄；沒有成功探測的 RTT 為 `null`，不填入零或前次數值。

Seed 只決定開始發送的相位和 bulk 啟動偏移；沒有加入未校準的無線隨機損失。不同 seed 的重複實驗是不同啟動相位的敏感度測試，不能當成真實家庭網路的統計信賴區間。

## 三種策略

1. **FIFO**：所有等待封包共用一個先進先出佇列，超過全域等待位元組預算時 tail drop。
2. **Fair**：每個 flow 有獨立佇列，依據位元組 virtual finish tags 選擇下一個封包，權重均為 1。全域滿載時，從等待位元組最多的 flow 尾端丟棄，避免單一 burst 佔滿整個緩衝。
3. **Priority**：同樣使用有限權重公平排程，會議／selected-device flow 權重預設為 3，其他 flow 仍為 1。它不是無上限的 strict priority；其他佇列有持續的服務機會。權重不會增加瓶頸容量。

Fair 與 Priority 同時使用**簡化 ECN-AQM**：bulk 在出列時，如果等待時間超過預設 10 ms，且該 flow 距離上次標記至少一個基礎 RTT，就標記一次 ECN，ACK 回饋後窗口減少。這不是 CoDel 的控制法，也不是 CAKE 的實際分類、hashing 或 queue disciplines。固定 UDP 不會回應 ECN；它只受到全域容量丟棄與排程影響，因此 UDP 超載仍可能有很高延遲或丟包。

等待佇列容量以 `capacity × queueMs` 模型位元組表示，最少一個 1500 位元組封包。容量不含正在序列化的封包。`queueMs` 是總等待位元組換算的時間預算，並不是每個 flow 排隊時間的上限；公平排程下，超過其份額的 flow 可能等待更久。

## 量測窗口與輸出

預設執行 30 秒、前 5 秒暖機。暖機仍正常產生流量，但摘要只包含 5–30 秒的指定窗口。停止產生流量後會排空佇列並完成 ACK／丟包回饋，以便核對守恆；排空期流量不加入測量窗口的 throughput。

- **Throughput**：以接收时间位於 `[warmup, duration)` 的位元組數計算。單位是模型中序列化封包位元組的 Mbps，不扣除協定 headers，也不是 codec 有效碼率。
- **Loss**：以發送時間位於該窗口的會議封包計算，包含排空期才完成的結果。這與 throughput 的接收窗口是不同定義。
- **RTT p50／p95**：以發送時間位於窗口、最終完成的 probe RTT 計算 nearest-rank percentile。probe 丟包率另行報告，避免忽略失敗探測。
- **Meeting jitter**：每個方向，計算相鄰成功會議封包的傳輸延遲差之絕對值平均。合併摘要依兩方向發送封包數加權。另提供 `rfc3550JitterMs` 的 1/16 平滑終值，避免混淆兩種統計。
- **時序圖**：每 500 ms 的實際接收位元組、收到的 probe RTT，以及該時刻佇列快照。會議丟包依發送時間分箱；最後一箱長度可能不足 500 ms。`samples[].raw` 保留分箱的位元組與 RTT 記錄。

`summary.roommateThroughputMbps` 與 `summary.meetingReceivedMbps` **是上傳加下載總和**。單獨方向數字在 `directions.up/down` 和 `summary.*UpMbps/*DownMbps`，不能拿雙向總和與單一下載容量比較。

`raw.meeting.up/down` 保留發送、接收、丟包、等待時間、位元組數；`raw.probes` 保留完整往返時間。每個方向的 `accounting` 提供提出、送達、丟棄的位元組與封包、序列化占用時間與容量。排空後应满足 `offered = delivered + dropped`，序列化总位元組不得超過容量乘以時間。

## 結論的適用範圍

公平排程本身可能已經足夠，Priority 的改善可以很小，甚至不同設定下没有改善。FIFO 可能延遲很高但 jitter 很低，因為長佇列近乎固定；不能把每個指標都說成必然改善。過高的固定影音負載也不可能被排程策略變成無損傳輸。

此模型沒有 Wi-Fi 訊號／競爭、ISP 斷線、實體網卡 offload、VPN、影音編碼、自適應碼率或實際通話品質。結果是可重現的網路排程實驗，用來提出假設和設計真實測試；不能宣稱 Zoom/Teams 通話一定不卡。

## 執行

```powershell
node --test tests/simulator.test.mjs
node --input-type=module -e "import {simulate} from './src/simulator.mjs'; console.log(simulate({mode:'fair'}).summary)"
```

函式：`simulate(config)`。預設值由 `DEFAULT_CONFIG` 匯出，設定採用平面欄位。支援 `scenario: 'idle' | 'upload' | 'download' | 'bidirectional'`，`mixed` 為 `bidirectional` 的別名。所有數值都檢查有限範圍；設定傳入字串數字、NaN、無限大、過長實驗或無效模式會拒絕。
