# Linux selftest 原始資料稽核

稽核通過：12 組實際 Linux 核心量測、36 條 receiver flow 的 summary 與原始資料一致。沒有發現需要修改 receiver extraction 的程式錯誤；目前的完整 batch 可繼續執行。本文件只解讀這次單輪 selftest，不把它當成三次重複實驗的統計結論。

環境為 Linux `6.18.52-0-virt`、iperf3 `3.20`，共享上傳 5 Mbps／下載 20 Mbps，設定基礎 RTT 40 ms。每組測量 8 秒，另有 2 秒暖機。核心 selftest 的 16 項檢查通過，包括 12 種策略/情境、DSCP 信任邊界、背景 timer 自動恢復、重啟到期處理與提前結束。

## 獨立重算

稽核工具 [audit_results.py](../../lab/audit_results.py) 不引用 `netlab.py` 的統計函式，以匯出的 JSON/ping 重新計算。機器報告見 [selftest-audit.json](selftest-audit.json)。

```sh
python3 lab/audit_results.py --input results/linux/selftest --output results/linux/selftest-audit.json
```

逐項確認：

- 24 條 UDP 與 12 條 TCP 都選取實際接收端 `end.sum_received`：上傳讀 server，反向下載讀 client；`sender` 都是 false。
- Summary 各欄位與接收端原始 JSON 一致；throughput 以 `bytes × 8 / seconds` 獨立重算也一致。不能將發送速率當成接收速率。
- 每條流量的原始設定皆為 `omit: 2`、`duration: 8`；interval 明確同時有 omitted 與 measured 區間。UDP 工作負載為 600,000 bps、256-byte payload；TCP 為四條並行連線。
- Client/server endpoint 限於 `10.77.1.2`、`10.77.2.2`、`10.77.4.2`，符合 meeting／roommate／server 角色。
- RTT 依原始 timestamp 排除暖機回覆，再採 nearest-rank p95；12 組 sample count、mean、p95 都與 summary 一致。各組有效 RTT samples 為 76–79。
- Receiver 的實際開始 timestamp 與共用 ping 起點相差 0.111–0.174 秒。各流量不是完全同步啟動；以各自的 iperf omit interval 排除暖機，以共用時間排除 ping 暖機。這個差異已保留在原始資料，沒有假設所有時計完全重合。

## 原始 iperf 計數的注意事項

本次 iperf3 3.20 上傳 server 的 `end.sum` 可能出現 `bytes: 0`、`bits_per_second: 0`，但 `end.sum_received` 有真實接收量。因此目前程式優先取 `sum_received` 是正確的；若改取一般 `sum`，反而會破壞結果。

兩條反向 UDP 原始輸出中的 `sum_received.packets` 與 `lost_percent` 使用的總封包數不同。例如 [FIFO/both 下載](selftest/fifo-both/meeting-down.json)：接收 summary 為 lost 2、packets 2318、loss 0.0831947%；原始 `end.sum.packets` 為 2404，2 / 2404 正好等於該 reported loss。這是原始 iperf 輸出欄位的差異，稽核保留其語意，沒有擅自用 2 / 2318 改寫 loss。

另有三筆 measured interval bytes 加總與 final receiver bytes 不完全一致：兩條 UDP 各差一個 256-byte payload；一條 TCP 差 131,072 bytes。所有 final receiver throughput 都滿足原始 receiver bytes/time 方程，且 summary 確實引用 final record。Interval 與 final 統計不應當成能逐 byte 拼接的相同快照。

Jitter 是 iperf 最終回報的接收端統計，沒有把每秒 jitter 取算術平均。Ping loss 欄位明確包含暖機期間；UDP loss 則保留 iperf 自己的最終欄位，這兩個百分比不能混為同一種丟包量測。

## 共享瓶頸與核心 policy 證據

所有實驗的 `tc-before.json`／`tc-after.json` 都有 `router/wan` 上傳與 `delay/torouter` 下載兩個共用 shaper。CAKE 原始 readback 的容量分別為 `5Mbit`、`20Mbit`，SQM 為 `besteffort`，meeting 為 `diffserv4`。FIFO 的 HTB class 容量由執行時的 `verify_mode` 讀回確認；匯出的 snapshot 未額外保存 `tc class show`，因此 FIFO class rate 的靜態檔案證據不如 CAKE 完整。

原始 `meeting/both` 配置與計數見 [tc-after.json](selftest/meeting-both/tc-after.json)：上傳同時比對 `indev mlan` 與 meeting source IP，下載比對 meeting destination IP；其他 IPv4 強制 Best Effort。室友的 TCP raw 設定確認 TOS=192（CS6），仍未流入 Voice tin。

| 共用 shaper | 選定裝置 action / Voice packets | Default action / Best Effort packets | Bulk / Video packets |
|---|---:|---:|---:|
| 上傳 router/wan | 3073 / 3073 | 11133 / 11133 | 0 / 0 |
| 下載 delay/torouter | 3081 / 3081 | 15872 / 15872 | 0 / 0 |

Action 與實際 CAKE tin counters 一致，證明優先分類在兩個方向真正生效，並非只在控制介面改了一個狀態欄位。CAKE 整體/tin drops 包含 TCP 控制、ACK、ping 等多種封包，不能直接當成 meeting UDP 的丟包數。

拓樸的 source routing 配置、raw endpoint 及共享 shaper 都吻合。這次輸出沒有完整保存各 namespace 的 route/address dump、兩端 netem qdisc 與 offload readback；固定延遲/offload 由 setup 成功套用，idle RTT 約 43–45 ms 也符合 40 ms 加排程開銷，但不能只用這份匯出資料逐條重播全部核心設定。未來可補足這些 read-only snapshot。

## 單輪混合壅塞結果

| 策略 | RTT p95 ms | UDP 上/下 loss % | UDP 上/下 jitter ms | 室友上/下接收 Mbps |
|---|---:|---:|---:|---:|
| FIFO | 292.0 | 2.0798 / 0.0832 | 3.299 / 4.774 | 3.482 / 18.220 |
| SQM | 48.1 | 0 / 0 | 1.628 / 1.683 | 3.778 / 15.733 |
| Meeting | 48.2 | 0 / 0 | 0.967 / 1.148 | 3.780 / 15.993 |

這次實驗支持「CAKE 公平排隊大幅降低這個受控壅塞下的 RTT」。**不支持「指定裝置優先比 SQM 有額外 RTT 改善」**：48.2 與 48.1 ms 幾乎相同。Meeting 的最終 jitter 在這一輪較小，但單輪、8 秒量測不足以推論所有負載或真實會議都較好。

也不能省略吞吐量取捨：SQM/meeting 的室友下載接收速率比 FIFO 小。需要用正在執行的三次重複、較長量測 batch 判斷範圍與一致性。

## 計時恢復與資源

[Session event log](session-events.jsonl) 共有三個 session，分別為 timer expiry、停止 timer worker 後由新 process 處理 expiry、及提前 stop。Selftest 在每個情境都讀回核心 SQM 設定並通過。背景 worker 的完成事件比期限晚約 0.648 秒，包含 200 ms polling 與實際 qdisc 套用/讀回成本；這不是精確到毫秒的恢復承諾。重啟 reconciliation 的完成事件比期限晚約 1.385 秒，因為刻意等到下一次 status 才處理。

12 組的最大 guest CPU 平均 busy 為 20.75%，全部 `cpu_warning: false`；沒有持續 CPU 飽和的跡象。這是整段 guest CPU 的平均，不排除短暫 CPU burst、host QEMU 排程或虛擬化開銷。

最後，這些是真正的 Linux 核心封包實驗，仍然是有線 veth 與固定瓶頸。它們沒有模擬 Wi-Fi 無線干擾、ISP 故障、WebRTC 自適應與影音體感；只能驗證受控網路中的傳輸和限時 policy lifecycle。
