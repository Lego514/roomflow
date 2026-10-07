# 36 次 Linux batch 稽核與異常分析

**資料完整性稽核通過；這批效能結果含持續的運行環境變化，不能據此宣稱 CAKE/SQM 零丟包或會議優先一定較好。** 36 次量測、108 條 receiver flow 均保留，沒有刪除不利結果。

[batch-audit.json](batch-audit.json) 由 [獨立稽核工具](../../lab/audit_results.py) 產生；工具不引用 netlab 的計算函式。所有 receiver 欄位都符合原始 `end.sum_received`；throughput 的 bytes/time 方程、原始 ping timestamp 的 mean/p95、三策略 × 四情境、15 秒量測/3 秒 omit、600 Kbps UDP、四條 TCP、端點、共享容量、CAKE 策略與優先規則/tin counter 均通過。

```sh
python3 lab/audit_results.py --input results/linux/batch --output results/linux/batch-audit.json
```

## 沒有發現 summary extraction 錯誤

UDP counter denominator 與 interval/end bytes 的差異仍存在，與 [selftest 稽核](SELFTEST_AUDIT.md) 相同：summary 保留 iperf 原始值，沒有以不同分母改寫 loss%。這些差異不能解釋數十百分比的 loss。

高 loss run 同時存在明顯的接收 bytes 缺口與實際 CAKE drop counters。例如 `r3-sqm-both`：

| 方向 | Sender bytes | Receiver bytes | iperf loss | 共用 CAKE dropped packets |
|---|---:|---:|---:|---:|
| 上傳 | 1,124,608 | 839,936 | 25.77% | 1558 |
| 下載 | 1,129,216 | 829,696 | 26.21% | 1540 |

Sender/receiver 有各自的暖機與結束邊界，不能做精確逐 byte conservation，但這種接近四分之一的接收量差距遠大於邊界差異。CAKE drop counts 包含全部 TCP/UDP/ping，不能逐個對應到 UDP；它們與原始 UDP 丟包及接收速率下降一致。

另一個有力例子是 `r2-sqm-idle`：沒有室友背景工作，上/下 UDP loss 16.17% / 14.27%，CAKE 上/下 drop 715 / 639。這不是把 TCP sender 的假設 bitrate 誤當成 UDP receiver，也不是表格欄位搞錯。

## 異常集中在最後九次量測

依 metadata 的 `started_at_unix` 排序，而非依資料夾名稱排序，可看見環境分段：

- 前 27 次，多數 SQM/meeting RTT p95 為 43–49 ms，UDP loss 為零；第 19 次 `r2-meeting-download` 曾有 73.9 ms 的 p95，但 loss 只有 0.068%。
- 第 28–36 次，SQM/meeting 的 idle/upload/both/download 都出現約 78–93 ms RTT，guest CPU busy 降為約 5–9%。高 loss 持續存在於每秒 receiver interval，並非只有最初暖機數秒。
- 同期兩個 FIFO/upload run 的 p95 也由早期的 235 ms 增至 261–263 ms，guest CPU 由約 11% 降到約 6%。變化跨越不同策略，不是只發生在一個 meeting filter。

| 執行序號 | Run | RTT p95 ms | UDP loss 上/下 % | 共用 qdisc drop 上/下 | 最大 vCPU 平均 busy % |
|---:|---|---:|---:|---:|---:|
| 28 | r3-meeting-idle | 78.5 | 0 / 11.43 | 0 / 510 | 5.66 |
| 29 | r1-sqm-download | 92.4 | 17.48 / 32.14 | 794 / 1723 | 6.17 |
| 30 | r2-fifo-upload | 263.0 | 2.85 / 0 | 256 / 0 | 6.07 |
| 31 | r2-meeting-idle | 79.3 | 0 / 7.04 | 0 / 319 | 5.75 |
| 32 | r1-fifo-upload | 261.0 | 0.83 / 0 | 155 / 0 | 6.32 |
| 33 | r2-sqm-idle | 89.7 | 16.17 / 14.27 | 715 / 639 | 4.86 |
| 34 | r2-meeting-both | 91.0 | 0 / 11.42 | 325 / 818 | 8.52 |
| 35 | r1-meeting-upload | 92.1 | 0 / 17.78 | 263 / 810 | 6.71 |
| 36 | r3-sqm-both | 92.7 | 25.77 / 26.21 | 1558 / 1540 | 9.14 |

`r3-sqm-both` 上傳的多個完整一秒 interval 為約 409–455 Kbps，loss 約 72–92 packets/second；最後一秒才回到約 597 Kbps。`r2-sqm-idle` 約第三秒後接收量持續降為約 460–475 Kbps。這是持續或變化中的實際資料路徑效果，不能只丟掉第一秒或延長 omit 就說異常消失。

## 能確認與不能確認的原因

已確認：

- 原始 CAKE readback 仍是 5/20 Mbps，SQM `besteffort`、meeting `diffserv4`；優先/default action 與各自 Voice/Best Effort tin packets 一致。
- [最後拓樸 snapshot](final-topology.txt) 的五個 namespace、route、兩個共用 shaper 與兩端 20 ms netem 符合設計。兩個 netem 的累積 dropped 都是零。
- Snapshot 中兩個共用 shaper 的 GSO/GRO/TSO 為 off；此檔是 batch 後的讀回，不能當成每次量測全程的歷史證據。
- 高 loss 在實際 CAKE queue 有對應 drop，並有接收 throughput 下降；不是只有 iperf 顯示的百分比異常。
- 沒有單一 guest vCPU 的整次平均 busy 超過 85%；全 batch 最大平均 busy 為 20.44%。

尚未確認：

- 這次沒有同步記錄 host/QEMU process CPU、host timer precision、vCPU 排程等待與 host 其他工作，因此不能將原因確定歸咎於 UIQA、Windows 排程、TCG、timer resolution 或 power state。
- guest 平均 CPU 不高，不能證明 host/guest 沒有計時延遲；AQM 與 netem 對封包排程時間敏感。跨策略與 idle 都出現後段變化，符合外部運行環境變化的假說，但仍需要隔離重測。
- 最後的 netem delay 沒被改成 40 ms；約翻倍的實測 RTT 不能直接解讀成我們的設定自行翻倍。

目前沒有足夠證據支持修改 receiver extraction、流量分類或藉由放寬 AQM target 掩蓋 loss。先保留原配置與資料，隔離測試環境再重測。

## 全部三次結果的誠實解讀

| 雙向壅塞策略 | 各次 p95 的平均 ms | 單次 p95 範圍 ms | UDP loss 平均 上/下 % |
|---|---:|---:|---:|
| FIFO | 290.33 | 287.0–296.0 | 2.49 / 0.19 |
| SQM | 63.00 | 47.6–92.7 | 8.59 / 8.74 |
| Meeting | 62.37 | 47.9–91.0 | 0 / 3.81 |

CAKE 模式在這個實驗中的 RTT 平均仍較 FIFO 低，但全部 batch 的 SQM UDP loss 平均比 FIFO 高。Meeting 的上傳 loss 為零，下載也有不良 run。平均 p95 相差 0.63 ms，遠小於各次約 45 ms 的運行差異，不能宣稱指定裝置優先相對 SQM 有可靠 RTT 增益。

這些是各次 p95 的平均，不是合併 percentile；三次結果也不足以建立統計顯著性。不能只保留前段零 loss 的資料做成功宣傳，也不能只根據這個不穩定的 TCG 環境判定真實路由器的 CAKE 不適合會議。

## 重測建議

保留 36 次原始 batch，另存獨立 rerun 資料夾與報告。暫停其他重型 QA/繪圖後，對 SQM 和 meeting/both 各做至少三次；每次 mixed run 前後都補一段同策略 idle measurement，確認環境是否仍維持約 40 ms 的基礎 RTT及穩定接收率。若所有 idle 也持續變慢或丟包，先診斷虛擬機計時環境，不能把重測當成可靠家庭網路驗證。

同步記錄 host QEMU process CPU 與 guest timer/clock 行為；僅靠平均 guest CPU 不夠。若可取得原生 Linux、Linux 硬體虛擬化 VM 或實體 OpenWrt 設備，應在那裡重複同容量/流量的實驗。新結果與原 batch 分開呈現，不能覆寫或挑選一組結果取代整個實驗。
