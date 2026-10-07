# 補充診斷稽核：不良狀態仍持續

**11 次補充診斷、40 條 receiver flow 的資料完整性稽核通過；不良 RTT/UDP loss 在重測中仍持續，效能限制未解決。** 原始 36 次 batch 和這次診斷分開保留，沒有覆寫、不利 run 也沒有移除。

[diagnostic-audit.json](diagnostic-audit.json) 的 `passed: true` 代表 summary 與原始資料一致，不代表零丟包或實際會議品質已達標。稽核使用與 full batch 相同的 receiver bytes/time、timestamp ping、暖機、工作負載、共享 shaper、CAKE 設定及優先分類/tin counter 檢查；`--diagnostic` 另外要求精確的 11 個資料夾、兩次 SQM/idle 10 秒、九次 rotated mixed 15 秒，全部暖機 3 秒。

```sh
python3 lab/audit_results.py --input results/linux/diagnostic --output results/linux/diagnostic-audit.json --diagnostic
```

## 所有診斷結果

| Run | RTT p95 ms | UDP loss 上/下 % | 共用 qdisc drop 上/下 | 最大 vCPU 平均 busy % |
|---|---:|---:|---:|---:|
| idle-start：SQM | 92.3 | 19.49 / 0 | 580 / 1 | 4.50 |
| r1-fifo | 475.0 | 3.82 / 1.80 | 532 / 253 | 8.51 |
| r1-sqm | 93.0 | 25.06 / 29.03 | 1468 / 1698 | 7.55 |
| r1-meeting | 91.4 | 0 / 19.86 | 306 / 1167 | 9.82 |
| r2-sqm | 92.2 | 23.29 / 29.69 | 1382 / 1749 | 8.53 |
| r2-meeting | 93.6 | 0 / 15.57 | 295 / 1007 | 6.93 |
| r2-fifo | 480.0 | 1.62 / 0.65 | 316 / 214 | 8.40 |
| r3-meeting | 93.3 | 0 / 20.51 | 301 / 1230 | 7.07 |
| r3-fifo | 497.0 | 3.03 / 1.07 | 617 / 199 | 8.73 |
| r3-sqm | 93.1 | 25.42 / 31.43 | 1423 / 1795 | 6.64 |
| idle-end：SQM | 79.5 | 0 / 9.44 | 0 / 287 | 4.20 |

混合壅塞三次 p95 的平均：FIFO 484.0 ms，SQM 92.77 ms，Meeting 92.77 ms。UDP loss 平均上/下：FIFO 2.82% / 1.17%，SQM 24.59% / 30.05%，Meeting 0% / 18.65%。Meeting 沒有平均 RTT 增益；它保護了這些 run 的上傳 UDP，但下載仍有大量丟包。

高 loss 同時有接收 bytes 缺口、throughput 下降與核心 qdisc drop。與 [原 batch 稽核](BATCH_AUDIT.md) 相同，它不是 summary extraction 或原始 loss denominator 小差異能解釋的現象。兩端 idle 也異常，表示不能把所有不良結果單純歸因於室友大量下載。

## 計時與資源證據

計時 probe 在流量測試外執行，每次要求 100 次 10 ms sleep；原始 elapsed samples 見 [before](diagnostic/timing-before.json)／[after](diagnostic/timing-after.json)。

| Probe | 實際 sleep p50 ms | p95 ms | 最大 ms | Clocksource |
|---|---:|---:|---:|---|
| before | 15.431 | 16.221 | 16.668 | tsc |
| after | 15.564 | 16.262 | 18.398 | tsc |

在沒有測試流量的短 probe 中，10 ms sleep 的典型實際時間仍為約 15.5 ms。這提供了持續 wakeup timing 延遲的直接證據，但沒有證明它是 CAKE loss 的唯一原因，也不能據此確定是 Windows、QEMU TCG、kernel timer、power state 或其他元件。

Guest before/after snapshot 見 [environment-before.txt](diagnostic/environment-before.txt)／[environment-after.txt](diagnostic/environment-after.txt)：沒有 reported steal 增量；softnet 的 dropped counter 沒有增加，time_squeeze 計數合計增加 34。後者表示部分網路 softirq 處理遇到預算/時間界限，不能單獨等同實際封包 loss。欄位依據為 [Linux softnet 輸出實作](https://github.com/torvalds/linux/blob/master/net/core/net-procfs.c)。TIMER/NET_RX/NET_TX/HRTIMER 計數都有增加，不能將「中斷存在」誤解成定時器都準時。

[Host QEMU 5 秒 samples](../../artifacts/tests/host-diagnostic-samples.jsonl) 有 52 筆，跨 256.12 秒。以 process CPU seconds 增量除以 wall time，QEMU 平均使用約 0.383 個邏輯 CPU，即一顆 CPU 的 38.29%，或 16 顆邏輯 CPU 全機容量的 2.39%；五秒區間為一顆 CPU 的約 1.24%–87.81%。Process priority 是 Normal。Samples 比第一個 idle-start 約晚 28 秒開始，涵蓋大部分測試及結束後一段時間；它們不是完整、逐毫秒的 host 負載紀錄。

Guest 最大整次平均 busy 為 9.82%，沒有觸發既有 >85% 的 CPU 警告。Host/QEMU 或 guest 的平均 CPU 低，仍不能排除短暫排程等待、sleep wakeup 粒度或其他計時影響。

## 最終判斷

核心 policy、實際封包量測、限時恢復與原始資料稽核功能已驗證。**這個 Windows/QEMU TCG 執行環境的效能狀態仍不穩定，尚未證明能可靠改善雙向會議品質。** 不能把資料完整性通過或 RTT 比 FIFO 小，擴大解讀成「開會不卡」已被證明。

暫停其他 QA 後，這輪 rotated mixed 與前後 idle 仍呈現不良狀態，故沒有證據把原因確定歸咎於原先的並行 UIQA。未修改策略、頻寬、AQM target 或核心來掩蓋問題；原始 batch 與補充診斷都保留。

下一個有意義的驗證應在原生 Linux、硬體虛擬化 Linux VM 或實體 OpenWrt 路由器重複同容量/工作負載，並保存 idle baseline 與 timer 行為。目前的效能限制保留為未解決；後續換環境的結果與原資料分開呈現。補充診斷結果與家庭 Wi-Fi/WebRTC 體感仍須分開。
