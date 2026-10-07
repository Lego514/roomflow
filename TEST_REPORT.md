# RoomFlow 完成與驗證報告

日期：2026-10-07。目的：在室友設備與路由器資訊尚未確認時，先完成可重現的「合租屋會議模式」實驗。

## 已完成的功能

- 本機中文操作介面：共用上／下行瓶頸、四種負載、三種策略對照、時間序列圖、室友吞吐量、CSV／JSON 匯出、可重新開啟的歷史報告。
- 模型限時會議模式：開始、提前停止、自動到期、服務重啟處理、套用讀回、失敗回復及重試。畫面標明這是模型，並顯示依目前策略重算的固定工作負載快照。
- Linux 真實封包 lab：meeting、roommate、router、delay、server 五個 namespaces，實際共享 HTB/FIFO 或 CAKE 瓶頸；延遲由獨立 netem link 加入。三個策略使用相同 5 Mbps 上行／20 Mbps 下行預算。
- Linux 獨立限時控制器：指定裝置分類、持久化期限、背景監督、到期回復、重新啟動處理、提前停止、讀回核心 qdisc。
- 下方實測區讀取已保存的 Linux 結果，獨立顯示環境、三次範圍、上／下行丟包及室友吞吐量。Web 的計時按鈕控制模型；Linux 控制器使用 CLI。

## 功能及資料驗證

| 驗證 | 結果 | 證據 |
|---|---:|---|
| Node.js 回歸與 HTTP 整合 | 24／24 通過 | [原始輸出](artifacts/tests/node-test.txt) |
| Python lab／控制器回歸 | 18／18 通過 | [原始輸出](artifacts/tests/python-test.txt) |
| Linux 核心 selftest | 16／16 通過 | [selftest.json](results/linux/selftest/selftest.json) |
| 模型矩陣 | 36 次完成及核對 | [報告](results/model/REPORT.md)、[獨立核對](results/model/AUDIT.md) |
| Linux 主矩陣 | 36 次完成，退出碼 0 | [CSV](results/linux/batch/measurements.csv)、[執行順序](results/linux/batch-progress.log) |
| Linux selftest 原始資料 | 12 次量測、36 條接收流核對通過 | [稽核](results/linux/SELFTEST_AUDIT.md) |
| Linux 主矩陣原始資料 | 36 次量測、108 條接收流核對通過 | [稽核](results/linux/BATCH_AUDIT.md) |
| Linux 補充診斷原始資料 | 11 次量測、40 條接收流核對通過 | [稽核](results/linux/DIAGNOSTIC_AUDIT.md) |

Node 測試涵蓋封包守恆、容量與佇列限制、可重現 seed、優先權不餓死背景流量、由原始紀錄重算指標、缺少樣本保留 null、輸入上限、真實 HTTP 匯出、到期與服務重啟、套用／讀回／磁碟失敗、損毀與遺失的已完成實驗結果、保存實測資料的 pending／失敗／恢復。

Python 測試涵蓋共享瓶頸、不同策略容量相同、受信任來源及入口分類、接收端統計、暖機排除、核心讀回失敗回復、外來拓樸拒絕清除、限時狀態恢復。這些是可在 Windows 執行的回歸；另外在真正 Linux 核心執行了 selftest，包含十二種負載／策略、室友偽造 CS6 不取得 Voice 優先權、獨立 timer 到期、停止 timer 後重新啟動處理、提前結束。

三個實際限時 session 的核心讀回均回到 SQM。背景 timer 的回復完成時間比期限晚約 0.648 秒，包含輪詢與核心設定成本；重啟處理是在下一次 status 才執行，並非毫秒級保證。見 [事件紀錄](results/linux/session-events.jsonl)。

## 瀏覽器操作

桌面與手機版實際操作涵蓋模型比較、10 秒到期恢復、提前停止、固定負載快照隨 fair → priority → fair 改變、歷史報告重開、Linux 保存結果由 pending 轉為已核對、混合／idle 情境切換、每方向 jitter 展開。

手機版在 390 × 844 viewport 的 document clientWidth 與 scrollWidth 都是 375，沒有整頁橫向溢出；沒有 console error／warning。缺失數值呈現「—」，真正的零呈現「0.00」。Linux CSV 端點回傳 HTTP 200、text/csv、37 行（表頭＋36 次測量），下載 headers 與 bytes 也通過 HTTP 回歸；瀏覽器下載完成事件未能確認，因此不宣稱已驗證檔案進入下載資料夾。

畫面：[桌面操作](artifacts/screenshots/desktop-preview.jpg)、[Linux 桌面報告](artifacts/screenshots/kernel-evidence-desktop.jpg)、[Linux 手機報告](artifacts/screenshots/kernel-evidence-mobile.jpg)。

## 模型結果

四情境 × 三策略 × 三個啟動相位，各測量 60 秒並排除前 5 秒。混合負載下，各次 p95 的平均為 FIFO **430.32 ms**、公平排隊 **48.51 ms**、有限優先 **47.42 ms**。會議丟包為 **0.510%／0%／0%**；室友合計上＋下行接收為 **22.50／22.42／22.41 Mbps**。

相對公平排隊，優先模式的 p95 額外改善只有約 **1.09 ms**。模型 jitter 也沒有全部改善，因此沒有將結果寫成「優先模式所有指標都較好」。共核對 2,160 個 interval、562,500 筆原始會議封包與 21,600 個探測，守恆、容量、佇列上限及指標重建通過。此模型是簡化封包排程與背景擁塞控制，不能稱為 Linux CAKE。

## Linux 主矩陣結果及異常

環境：專案內可攜 QEMU TCG、Alpine 3.24.2、Linux 6.18.52-0-virt、iperf3 3.20。每方向會議替代流量為 600 Kbps UDP／256-byte payload，背景每方向四條 TCP；每次暖機 3 秒、量測 15 秒，順序以 seed 22756 打散。

混合上下載的三次摘要如下。p95 是每次 p95 的平均，範圍是三次單次 p95；吞吐量分開呈現上下行。

| 策略 | p95 RTT 平均（範圍）ms | 會議 loss % 上／下 | 室友 Mbps 上／下 |
|---|---:|---:|---:|
| FIFO | 290.33（287–296） | 2.49／0.19 | 3.55／18.29 |
| CAKE SQM | 63.00（47.6–92.7） | 8.59／8.74 | 3.09／11.58 |
| CAKE＋會議分類 | 62.37（47.9–91.0） | 0／3.81 | 2.97／11.00 |

**主矩陣有未解釋的環境波動，不能宣稱效能驗證全部通過。** 後九次出現持續的 guest CPU 平均忙碌率下降、RTT 升高與吞吐量降低，甚至 idle 也受影響。接收端 byte 缺口與 CAKE drop 計數證明丟包真實存在；不是只因 iperf 百分比分母而造成的假象。這與虛擬環境計時／排程問題相容，但沒有足夠證據確定原因。沒有刪除異常執行或用較漂亮的一輪替換結果。

一般 SQM／優先模式多數次 p95 約 48 ms，但單次波動達 91–92.7 ms。兩者平均只差 0.63 ms，範圍重疊；這批資料不足以證明指定裝置優先比一般 SQM 有穩定額外價值。室友吞吐量及丟包也不能省略。

原始資料保留 ping 時間戳、iperf client/server JSON、核心 qdisc／分類計數與 metadata；稽核沒有引用 lab 的統計函式。iperf 原始 loss% 被保留，沒有將不一致的 packets 欄位擅自當成分母。部分 per-second bytes 與最終摘要不同，報告明確採用接收端最終摘要。詳見 [完整結果](results/linux/REPORT.md)、[主矩陣稽核](results/linux/BATCH_AUDIT.md)。

## 獨立保存的診斷補測

暫停瀏覽器操作後，執行 SQM idle 起點、三輪輪換順序的 FIFO／SQM／meeting 混合負載、SQM idle 終點，共 **11 次，退出碼 0**。原始 36 次矩陣仍完整保存，沒有替換。見 [診斷原始資料](results/linux/diagnostic/)、[診斷稽核](results/linux/DIAGNOSTIC_AUDIT.md)。

異常持續存在：三次混合 SQM p95 為 93.0／92.2／93.1 ms，上行 loss 約 23–25%、下行約 29–31%；meeting p95 為 91.4／93.6／93.3 ms，上行 loss 為零、下行約 16–21%；FIFO p95 為 475／480／497 ms。Idle 起點 p95 92.3 ms、上行 loss 19.49%；終點 p95 79.5 ms、下行 loss 9.44%。停止 UI 操作並沒有使測量恢復前段狀態，不能宣稱 UI 就是原因。

前後各 100 次、要求等待 10 ms 的 guest probe，p50 約 15.43／15.56 ms、p95 約 16.22／16.26 ms。Clocksource 為 tsc。這是粗略排程等待的證據，沒有直接測量 netem 或 CAKE timer，不能據此確定丟包原因。保存 `/proc/stat`、softirq、softnet、interrupt、uptime 與 host 每 5 秒的 QEMU CPU 累計值；沒有修改主機 timer、電源模式或 AQM target。

因此此版本完成的是功能、可重現執行及真實資料核對。**效能穩定性尚未在可靠 Linux 時序環境／實際家用設備上確認。** 後續應在原生 Linux 或適合的硬體虛擬化環境重測，再談家庭網路效能與會議體感。

## 重現與使用界線

執行 `node src/server.mjs`，開啟 <http://127.0.0.1:3210>。沒有第三方 Node 依賴，無須 npm install。模型矩陣用 `node scripts/run-matrix.mjs`；Linux 命令與可攜 VM 步驟見 [README](README.md)、[Linux lab](docs/linux-lab.md)、[Windows VM](docs/portable-vm.md)。

此專案尚未測量家中 Wi-Fi 或真實 Zoom／Teams，也沒有完整 WebRTC 自適應負載。模型與核心測試的負載和 jitter 定義不同，不能把數字直接混用。路由器支援能力、線路速度、室友同意及居家實測仍要等設備資訊確認。現階段能展示的是可重現的網路排程實驗、失敗處理與限時回復。

所有 lab 角色位於隔離 VM。Windows 與家用路由器未被套用 QoS；沒有安裝系統級 WSL／Docker／QEMU。

結束時，Linux 限時模式已停止、五個測試 namespace 全部清除、VM 正常關機、artifact bridge 關閉。Web 服務仍開啟，狀態為 normal 且沒有有效期限。見 [清理核對](artifacts/tests/cleanup-verification.json)。
